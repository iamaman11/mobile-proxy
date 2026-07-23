from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from check_digest_policy import check_repository


class DigestPolicyTests(unittest.TestCase):
    def test_blake3_first_party_source_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            crate = root / "crates/example"
            (crate / "src").mkdir(parents=True)
            (crate / "Cargo.toml").write_text(
                '[package]\nname = "example"\nversion = "0.1.0"\n',
                encoding="utf-8",
            )
            (crate / "src/lib.rs").write_text(
                'const FORMAT: &str = "b3:";\n', encoding="utf-8"
            )
            self.assertEqual(check_repository(root), [])

    def test_sha2_dependency_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            crate = root / "apps/example"
            (crate / "src").mkdir(parents=True)
            (crate / "Cargo.toml").write_text(
                '[package]\nname = "example"\nversion = "0.1.0"\n\n'
                '[dependencies]\nsha2 = "0.10"\n',
                encoding="utf-8",
            )
            (crate / "src/main.rs").write_text("fn main() {}\n", encoding="utf-8")
            errors = check_repository(root)
            self.assertTrue(any("sha2 dependency" in error for error in errors))

    def test_sha256_constructor_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "crates/example/src/lib.rs"
            source.parent.mkdir(parents=True)
            source.write_text("fn digest() { let _ = Sha256::new(); }\n", encoding="utf-8")
            errors = check_repository(root)
            self.assertTrue(any("SHA-256 usage" in error for error in errors))

    def test_legacy_device_checksum_contract_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "services/example/src/main.rs"
            source.parent.mkdir(parents=True)
            source.write_text(
                'const LEGACY: &str = "checksums.sha256";\n', encoding="utf-8"
            )
            errors = check_repository(root)
            self.assertTrue(any("SHA-256 usage" in error for error in errors))

    def test_legacy_vm_checksum_contract_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "apps/example/src/main.rs"
            source.parent.mkdir(parents=True)
            source.write_text(
                'const LEGACY: &str = "SHA256SUMS";\n', encoding="utf-8"
            )
            errors = check_repository(root)
            self.assertTrue(any("SHA-256 usage" in error for error in errors))

    def test_external_lockfile_checksums_are_outside_first_party_source_scan(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "Cargo.lock").write_text(
                'checksum = "0123456789abcdef"\n', encoding="utf-8"
            )
            self.assertEqual(check_repository(root), [])


if __name__ == "__main__":
    unittest.main()
