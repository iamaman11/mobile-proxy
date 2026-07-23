import importlib.util
from pathlib import Path
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "check_architecture_boundaries.py"
SPEC = importlib.util.spec_from_file_location("architecture_boundaries", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class ArchitectureBoundaryTests(unittest.TestCase):
    def create_repository(self, manifest: str, source: str) -> Path:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        crate = root / "crates/runtime-domain"
        (crate / "src").mkdir(parents=True)
        (crate / "Cargo.toml").write_text(manifest, encoding="utf-8")
        (crate / "src/lib.rs").write_text(source, encoding="utf-8")
        return root

    def test_accepts_pure_runtime_domain(self):
        root = self.create_repository(
            """[package]\nname = \"runtime-domain\"\nversion = \"0.1.0\"\n\n[dependencies]\nserde = \"1\"\n""",
            "pub enum RuntimeState { WaitingTunnel }\n",
        )
        self.assertEqual(MODULE.check_repository(root), [])

    def test_rejects_infrastructure_dependency(self):
        root = self.create_repository(
            """[package]\nname = \"runtime-domain\"\nversion = \"0.1.0\"\n\n[dependencies]\nserde = \"1\"\ntokio = \"1\"\n""",
            "pub enum RuntimeState { WaitingTunnel }\n",
        )
        errors = MODULE.check_repository(root)
        self.assertTrue(any("forbidden dependency 'tokio'" in error for error in errors))

    def test_rejects_adapter_specific_domain_vocabulary(self):
        root = self.create_repository(
            """[package]\nname = \"runtime-domain\"\nversion = \"0.1.0\"\n\n[dependencies]\nserde = \"1\"\n""",
            'pub const OWNER: &str = "wireguard";\n',
        )
        errors = MODULE.check_repository(root)
        self.assertTrue(any("forbidden domain token 'wireguard'" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
