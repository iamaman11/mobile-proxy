import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "check_architecture_boundaries.py"
SPEC = importlib.util.spec_from_file_location("architecture_boundaries", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class ArchitectureBoundaryTests(unittest.TestCase):
    def create_repository(
        self,
        *,
        runtime_manifest: str = """[package]\nname = \"runtime-domain\"\nversion = \"0.1.0\"\n\n[dependencies]\nserde = \"1\"\n""",
        runtime_source: str = "pub enum RuntimeState { WaitingTunnel }\n",
        foundation_manifest: str = """[package]\nname = \"mobile-proxy-foundation\"\nversion = \"0.1.0\"\n\n[dependencies]\nblake3 = \"1\"\nserde = \"1\"\nuuid = \"1\"\n""",
        foundation_source: str = "pub struct RequestId;\n",
    ) -> Path:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        for relative, manifest, source in [
            ("crates/runtime-domain", runtime_manifest, runtime_source),
            ("crates/foundation", foundation_manifest, foundation_source),
        ]:
            crate = root / relative
            (crate / "src").mkdir(parents=True)
            (crate / "Cargo.toml").write_text(manifest, encoding="utf-8")
            (crate / "src/lib.rs").write_text(source, encoding="utf-8")
        return root

    def check_fixture(self, root: Path):
        with (
            patch.object(MODULE, "check_digest_policy", return_value=[]),
            patch.object(MODULE, "check_invariant_enforcement", return_value=[]),
        ):
            return MODULE.check_repository(root)

    def test_accepts_pure_crates(self):
        self.assertEqual(self.check_fixture(self.create_repository()), [])

    def test_rejects_infrastructure_dependency_in_foundation(self):
        root = self.create_repository(
            foundation_manifest="""[package]\nname = \"mobile-proxy-foundation\"\nversion = \"0.1.0\"\n\n[dependencies]\nserde = \"1\"\ntokio = \"1\"\n"""
        )
        errors = self.check_fixture(root)
        self.assertTrue(any("forbidden dependency 'tokio'" in error for error in errors))

    def test_rejects_adapter_specific_domain_vocabulary(self):
        root = self.create_repository(
            runtime_source='pub const OWNER: &str = "wireguard";\n'
        )
        errors = self.check_fixture(root)
        self.assertTrue(any("forbidden pure-crate token 'wireguard'" in error for error in errors))

    def test_rejects_identity_generation_inside_foundation(self):
        root = self.create_repository(
            foundation_source="pub fn generate() { let _ = Uuid::new_v4(); }\n"
        )
        errors = self.check_fixture(root)
        self.assertTrue(any("forbidden pure-crate token 'new_v4'" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
