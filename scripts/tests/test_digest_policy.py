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

    def test_blake3_first_party_source_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_crate(
                root,
                "crates/example",
                '[package]\nname = "example"\nversion = "0.1.0"\n',
                'const FORMAT: &str = "b3:";\n',
            )
            self.assertEqual(check_repository(root), [])

    def test_sha2_dependency_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_crate(
                root,
                "apps/example",
                '[package]\nname = "example"\nversion = "0.1.0"\n\n'
                '[dependencies]\nsha2 = "0.10"\n',
            )
            errors = check_repository(root)
            self.assertTrue(any("digest package" in error for error in errors))

    def test_renamed_sha2_dependency_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_crate(
                root,
                "services/example",
                '[package]\nname = "example"\nversion = "0.1.0"\n\n'
                '[target.\'cfg(unix)\'.dependencies]\n'
                'digest_impl = { package = "sha2", version = "0.10" }\n',
            )
            errors = check_repository(root)
            self.assertTrue(any("digest package" in error for error in errors))

    def test_sha256_package_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_crate(
                root,
                "crates/example",
                '[package]\nname = "example"\nversion = "0.1.0"\n\n'
                '[dev-dependencies]\nsha256 = "1"\n',
            )
            errors = check_repository(root)
            self.assertTrue(any("digest package" in error for error in errors))

    def test_sha256_source_spellings_are_rejected(self):
        for source in [
            "fn digest() { let _ = Sha256::new(); }\n",
            "fn digest() { let _ = sha256::digest(b\"x\"); }\n",
            "const ALGORITHM: &str = \"SHA-256\";\n",
            "const ALGORITHM: &str = \"sha_256\";\n",
        ]:
            with self.subTest(source=source), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                self.make_crate(
                    root,
                    "crates/example",
                    '[package]\nname = "example"\nversion = "0.1.0"\n',
                    source,
                )
                errors = check_repository(root)
                self.assertTrue(any("SHA-256 usage" in error for error in errors))

    def test_legacy_release_checksum_contracts_are_rejected(self):
        for legacy in ["checksums.sha256", "SHA256SUMS"]:
            with self.subTest(legacy=legacy), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                self.make_crate(
                    root,
                    "apps/example",
                    '[package]\nname = "example"\nversion = "0.1.0"\n',
                    f'const LEGACY: &str = "{legacy}";\n',
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
