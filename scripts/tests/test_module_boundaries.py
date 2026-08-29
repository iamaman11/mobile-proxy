import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "check_module_boundaries.py"
SPEC = importlib.util.spec_from_file_location("module_boundaries", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class ModuleBoundaryTests(unittest.TestCase):
    def create_repository(
        self,
        *,
        members: list[str] | None = None,
        app_dependencies: str = 'foundation = { package = "foundation", path = "../foundation" }\n',
        app_allowed: list[str] | None = None,
        foundation_dependencies: str = "",
        foundation_allowed: list[str] | None = None,
    ) -> Path:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        members = members or ["crates/foundation", "crates/application"]
        app_allowed = ["foundation"] if app_allowed is None else app_allowed
        foundation_allowed = [] if foundation_allowed is None else foundation_allowed

        (root / "docs/architecture").mkdir(parents=True)
        (root / "docs/architecture/ARCHITECTURE_STANDARD.md").write_text(
            "# Architecture Quality Standard\n", encoding="utf-8"
        )
        member_lines = ",\n".join(f'    "{member}"' for member in members)
        (root / "Cargo.toml").write_text(
            f'[workspace]\nmembers = [\n{member_lines}\n]\nresolver = "2"\n',
            encoding="utf-8",
        )

        manifests = {
            "crates/foundation": (
                "foundation",
                foundation_dependencies,
            ),
            "crates/application": (
                "application",
                app_dependencies,
            ),
        }
        for relative, (package, dependencies) in manifests.items():
            crate = root / relative
            crate.mkdir(parents=True)
            crate.joinpath("Cargo.toml").write_text(
                f'[package]\nname = "{package}"\nversion = "0.1.0"\n\n[dependencies]\n{dependencies}',
                encoding="utf-8",
            )

        contract = {
            "schema_version": 1,
            "status": "normative",
            "architecture_standard": "docs/architecture/ARCHITECTURE_STANDARD.md",
            "workspace_manifest": "Cargo.toml",
            "policies": dict(MODULE.EXPECTED_POLICIES),
            "modules": [
                {
                    "path": "crates/foundation",
                    "package": "foundation",
                    "role": "foundation",
                    "allowed_internal_dependencies": foundation_allowed,
                },
                {
                    "path": "crates/application",
                    "package": "application",
                    "role": "application",
                    "allowed_internal_dependencies": app_allowed,
                },
            ],
        }
        contract_file = root / MODULE.CONTRACT_PATH
        contract_file.parent.mkdir(parents=True)
        contract_file.write_text(json.dumps(contract), encoding="utf-8")
        return root

    def test_accepts_exact_declared_graph(self):
        self.assertEqual(MODULE.validate_repository(self.create_repository()), [])

    def test_rejects_unclassified_workspace_member(self):
        root = self.create_repository(
            members=["crates/foundation", "crates/application", "crates/forgotten"]
        )
        errors = MODULE.validate_repository(root)
        self.assertTrue(any("Rust workspace classification differs" in error for error in errors))
        self.assertTrue(any("crates/forgotten" in error for error in errors))

    def test_rejects_undeclared_internal_dependency(self):
        root = self.create_repository(app_allowed=[])
        errors = MODULE.validate_repository(root)
        self.assertTrue(any("undeclared internal dependencies: ['foundation']" in error for error in errors))

    def test_rejects_stale_allowed_dependency(self):
        root = self.create_repository(app_dependencies="")
        errors = MODULE.validate_repository(root)
        self.assertTrue(any("stale allowed internal dependencies: ['foundation']" in error for error in errors))

    def test_rejects_internal_dependency_cycle(self):
        root = self.create_repository(
            foundation_dependencies='application = { path = "../application" }\n',
            foundation_allowed=["application"],
        )
        errors = MODULE.validate_repository(root)
        self.assertTrue(any("internal dependency cycle" in error for error in errors))

    def test_rejects_non_fail_closed_policy(self):
        root = self.create_repository()
        contract_file = root / MODULE.CONTRACT_PATH
        contract = json.loads(contract_file.read_text(encoding="utf-8"))
        contract["policies"]["unknown_workspace_member"] = "allow"
        contract_file.write_text(json.dumps(contract), encoding="utf-8")
        errors = MODULE.validate_repository(root)
        self.assertTrue(any("policies must remain fail-closed" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
