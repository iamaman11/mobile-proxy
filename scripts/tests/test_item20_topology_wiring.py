import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "check_item20_topology_wiring.py"
SPEC = importlib.util.spec_from_file_location("item20_topology_wiring", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
ROOT = Path(__file__).resolve().parents[2]


def copy_tree(root: Path) -> None:
    shutil.copytree(ROOT / "contracts", root / "contracts")
    workflow = root / ".github/workflows/item20-session-orchestration.yml"
    workflow.parent.mkdir(parents=True)
    shutil.copy2(ROOT / ".github/workflows/item20-session-orchestration.yml", workflow)


class Item20TopologyWiringTests(unittest.TestCase):
    def test_repository_passes(self):
        self.assertEqual(MODULE.check_repository(ROOT), [])

    def test_github_wiring_cannot_acquire_acceptance_environment(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            copy_tree(root)
            path = root / "contracts/operations/github-control-plane-v1.json"
            contract = json.loads(path.read_text(encoding="utf-8"))
            contract["item20_non_live_orchestration"]["environment"] = "acceptance-vultr"
            path.write_text(json.dumps(contract), encoding="utf-8")
            errors = MODULE.check_repository(root)
        self.assertTrue(any("non-live orchestration wiring" in error for error in errors))

    def test_topology_cannot_claim_live_item20_session_ready(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            copy_tree(root)
            path = root / "contracts/operations/production-topology-v1.json"
            contract = json.loads(path.read_text(encoding="utf-8"))
            contract["migration_status"]["next_acceptance_lifecycle"] = "ready"
            path.write_text(json.dumps(contract), encoding="utf-8")
            errors = MODULE.check_repository(root)
        self.assertTrue(any("live-session gate" in error for error in errors))

    def test_workflow_cannot_consume_acceptance_vultr(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            copy_tree(root)
            path = root / ".github/workflows/item20-session-orchestration.yml"
            path.write_text(
                path.read_text(encoding="utf-8") + "\n# environment: acceptance-vultr\n",
                encoding="utf-8",
            )
            errors = MODULE.check_repository(root)
        self.assertTrue(any("forbidden live token" in error for error in errors))

    def test_item20_authorization_cannot_be_promoted(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            copy_tree(root)
            path = root / "contracts/operations/item20-acceptance-v1.json"
            contract = json.loads(path.read_text(encoding="utf-8"))
            contract["authorization"]["provider_mutation_authorized"] = True
            path.write_text(json.dumps(contract), encoding="utf-8")
            errors = MODULE.check_repository(root)
        self.assertTrue(any("non-live and non-mutating" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
