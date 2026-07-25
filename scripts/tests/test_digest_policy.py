from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from check_digest_policy import check_repository


class DigestPolicyTests(unittest.TestCase):
    def make_crate(self, root: Path, relative: str, manifest: str, source: str = "fn main() {}\n"):
        crate = root / relative
        (crate / "src").mkdir(parents=True)
        (crate / "Cargo.toml").write_text(manifest, encoding="utf-8")
        (crate / "src/main.rs").write_text(source, encoding="utf-8")
        return crate

    def add_required_enforcement_files(self, root: Path):
        fragments = {
            "crates/proxy-core/src/fingerprints.rs": [
                'DigestDomain::new("mobile-proxy/host-daemon-nonsecret-config/v1")',
                'DigestDomain::new("mobile-proxy/host-daemon-binary/v1")',
                "ConfigFingerprintInput",
                "BinaryFingerprintInput",
            ],
            "crates/proxy-core/src/records.rs": [
                "pub config_fingerprint: Option<ConfigFingerprint>",
                "pub binary_fingerprint: Option<BinaryFingerprint>",
            ],
            "services/host-daemon/src/fingerprints.rs": [
                "config_source_fingerprint",
                "current_binary_fingerprint",
                'Path::new("/proc/self/exe")',
            ],
            "crates/control-plane-sqlite/src/legacy_json_import.rs": [
                "LegacyJsonMigrationStats",
                "ConfigFingerprintInput",
                "BinaryFingerprintInput",
                "fingerprint_stats",
            ],
            "scripts/verify_physical_deployment.py": [
                '"comparison_contract": "exact-bytes"',
                "remote_bytes == (root / relative).read_bytes()",
                "cmp -s --",
            ],
            "scripts/switch_vm_proxy_transport.py": [
                '"exact_config_match": True',
                "sudo cmp -s --",
            ],
        }
        for relative, required in fragments.items():
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("\n".join(required), encoding="utf-8")

    def check(self, root: Path):
        self.add_required_enforcement_files(root)
        return check_repository(root)

    def test_typed_blake3_first_party_source_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_crate(
                root,
                "crates/foundation",
                '[package]\nname = "foundation"\nversion = "0.1.0"\n\n[dependencies]\nblake3 = "1"\n',
                'const FORMAT: &str = "b3:";\n',
            )
            self.assertEqual(self.check(root), [])

    def test_direct_blake3_dependency_outside_foundation_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_crate(
                root,
                "services/example",
                '[package]\nname = "example"\nversion = "0.1.0"\n\n[dependencies]\nblake3 = "1"\n',
            )
            errors = self.check(root)
            self.assertTrue(any("outside typed foundation" in error for error in errors))

    def test_sha_packages_are_rejected_in_all_dependency_tables(self):
        examples = [
            ('[dependencies]\nsha2 = "0.10"\n', "apps/example"),
            ('[target.\'cfg(unix)\'.dependencies]\ndigest_impl = { package = "sha2", version = "0.10" }\n', "services/example"),
            ('[dev-dependencies]\nsha256 = "1"\n', "crates/example"),
        ]
        for dependency, relative in examples:
            with self.subTest(relative=relative), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                self.make_crate(
                    root,
                    relative,
                    '[package]\nname = "example"\nversion = "0.1.0"\n\n' + dependency,
                )
                self.assertTrue(any("digest package" in error for error in self.check(root)))

    def test_direct_sha_operations_are_rejected_across_languages(self):
        examples = {
            "scripts/a.py": "import hashlib\nhashlib.sha256(b'x').hexdigest()\n",
            "scripts/b.py": "import hashlib\nhashlib.new('sha256', b'x')\n",
            "deploy/a.sh": "sha256sum file\n",
            "deploy/b.sh": "openssl dgst -sha256 file\n",
            "apps/android-app/src/main/kotlin/A.kt": 'MessageDigest.getInstance("SHA-256")\n',
            "services/example/src/main.rs": "let _ = Sha256::new();\n",
        }
        for relative, body in examples.items():
            with self.subTest(relative=relative), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(body, encoding="utf-8")
                errors = self.check(root)
                self.assertTrue(any("SHA-256 primitive" in error for error in errors))

    def test_direct_untyped_blake3_in_scripts_is_rejected(self):
        for relative, body in [
            ("scripts/a.py", "import blake3\n"),
            ("deploy/a.sh", "b3sum file\n"),
        ]:
            with self.subTest(relative=relative), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(body, encoding="utf-8")
                self.assertTrue(any("untyped" in error for error in self.check(root)))

    def test_internal_sha_contract_names_and_legacy_checksums_are_rejected(self):
        for body in [
            "config_sha256 = 'x'\n",
            "SHA256SUMS\n",
            "checksums.sha256\n",
        ]:
            with self.subTest(body=body), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                path = root / "scripts/example.py"
                path.parent.mkdir(parents=True)
                path.write_text(body, encoding="utf-8")
                self.assertTrue(self.check(root))

    def test_untyped_runtime_fingerprint_and_legacy_env_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_crate(
                root,
                "crates/example",
                '[package]\nname = "example"\nversion = "0.1.0"\n',
                "struct Record { config_fingerprint: Option<String>, binary_fingerprint: String }\n",
            )
            self.assertTrue(any("typed contracts" in error for error in self.check(root)))

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "scripts/example.py"
            path.parent.mkdir(parents=True)
            path.write_text("HOST_DAEMON_BINARY_FINGERPRINT\n", encoding="utf-8")
            self.assertTrue(any("environment-provided" in error for error in self.check(root)))

    def test_external_lockfile_checksums_are_outside_first_party_source_scan(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "Cargo.lock").write_text('checksum = "0123456789abcdef"\n', encoding="utf-8")
            self.assertEqual(self.check(root), [])


if __name__ == "__main__":
    unittest.main()
