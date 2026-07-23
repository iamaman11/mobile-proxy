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
        runtime_manifest: str = """[package]
name = "runtime-domain"
version = "0.1.0"

[dependencies]
serde = "1"
""",
        runtime_source: str = "pub enum RuntimeState { WaitingTunnel }\n",
        foundation_manifest: str = """[package]
name = "mobile-proxy-foundation"
version = "0.1.0"

[dependencies]
blake3 = "1"
serde = "1"
uuid = "1"
""",
        foundation_source: str = "pub struct RequestId;\n",
        application_manifest: str = """[package]
name = "mobile-proxy-application"
version = "0.1.0"

[dependencies]
mobile-proxy-foundation = "1"
proxy-core = "1"
""",
        application_source: str = "use proxy_core::DeviceCommand;\npub trait UseCase {}\n",
    ) -> Path:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        for relative, manifest, source in [
            ("crates/runtime-domain", runtime_manifest, runtime_source),
            ("crates/foundation", foundation_manifest, foundation_source),
            ("crates/application", application_manifest, application_source),
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

    def test_accepts_declared_pure_crates(self):
        self.assertEqual(self.check_fixture(self.create_repository()), [])

    def test_rejects_infrastructure_dependency_in_foundation(self):
        root = self.create_repository(
            foundation_manifest="""[package]
name = "mobile-proxy-foundation"
version = "0.1.0"

[dependencies]
serde = "1"
tokio = "1"
"""
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

    def test_allows_domain_dependency_but_rejects_transport_in_application(self):
        accepted = self.create_repository()
        self.assertEqual(self.check_fixture(accepted), [])
        rejected = self.create_repository(
            application_manifest="""[package]
name = "mobile-proxy-application"
version = "0.1.0"

[dependencies]
proxy-core = "1"
axum = "1"
"""
        )
        errors = self.check_fixture(rejected)
        self.assertTrue(any("forbidden dependency 'axum'" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
