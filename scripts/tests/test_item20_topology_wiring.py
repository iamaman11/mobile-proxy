import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "check_item20_topology_wiring.py"
SPEC = importlib.util.spec_from_file_location("item20_topology_wiring", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

COPY_FILES = (
    "contracts/operations/historical-public-acceptance-retirement-v1.json",
    "contracts/operations/item20-acceptance-v1.json",
    "contracts/operations/item20-private-handoff-v1.json",
    "contracts/operations/github-control-plane-v2.json",
    "contracts/operations/production-topology-v2.json",
    "scripts/item20_private_handoff.py",
)


def copy_tree(root: Path) -> None:
    for relative in COPY_FILES:
        source = ROOT / relative
        destination = root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)


class Item20TopologyWiringTests(unittest.TestCase):
    def test_repository_passes(self):
        self.assertEqual(MODULE.check_repository(ROOT), [])

    def test_retired_workflow_cannot_return(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            copy_tree(root)
            workflow = root / ".github/workflows/item20-session-orchestration.yml"
            workflow.parent.mkdir(parents=True, exist_ok=True)
            workflow.write_text("name: resurrected\n", encoding="utf-8")
            errors = MODULE.check_repository(root)
        self.assertTrue(any("executable again" in error for error in errors))

    def test_item20_authorization_cannot_be_promoted(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            copy_tree(root)
            path = root / "contracts/operations/item20-acceptance-v1.json"
            contract = json.loads(path.read_text(encoding="utf-8"))
            contract["authorization"]["provider_mutation_authorized"] = True
            path.write_text(json.dumps(contract), encoding="utf-8")
            errors = MODULE.check_repository(root)
        self.assertTrue(any("grants live or mutation authority" in error for error in errors))

    def test_private_handoff_cannot_be_enabled(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            copy_tree(root)
            path = root / "contracts/operations/item20-private-handoff-v1.json"
            contract = json.loads(path.read_text(encoding="utf-8"))
            contract["implementation"]["public_handoff_enabled"] = True
            path.write_text(json.dumps(contract), encoding="utf-8")
            errors = MODULE.check_repository(root)
        self.assertTrue(any("unexpectedly enables public_handoff_enabled" in error for error in errors))

    def test_v2_historical_classification_cannot_drift(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            copy_tree(root)
            path = root / "contracts/operations/github-control-plane-v2.json"
            contract = json.loads(path.read_text(encoding="utf-8"))
            contract["historical_acceptance_surfaces"]["public_item19_item20_workflows"] = "active"
            path.write_text(json.dumps(contract), encoding="utf-8")
            errors = MODULE.check_repository(root)
        self.assertTrue(any("historical public acceptance classification differs" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
