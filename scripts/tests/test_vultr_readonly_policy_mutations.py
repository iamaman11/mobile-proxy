import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "check_vultr_readonly_preflight_policy.py"
SPEC = importlib.util.spec_from_file_location("vultr_readonly_policy", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class VultrReadonlyPolicyMutationTests(unittest.TestCase):
    def copied_root(self, temporary: str) -> Path:
        root = Path(temporary)
        for relative in (
            "contracts/operations/vultr-readonly-preflight-v1.json",
            "contracts/operations/historical-public-acceptance-retirement-v1.json",
            "contracts/operations/github-control-plane-v2.json",
        ):
            destination = root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / relative, destination)
        return root

    def test_repository_passes(self):
        self.assertEqual(MODULE.check_repository(ROOT), [])

    def test_reintroduced_workflow_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = self.copied_root(temporary)
            workflow = root / ".github/workflows/vultr-readonly-preflight.yml"
            workflow.parent.mkdir(parents=True, exist_ok=True)
            workflow.write_text("name: resurrected\n", encoding="utf-8")
            errors = MODULE.check_repository(root)
        self.assertTrue(any("executable again" in error for error in errors))

    def test_retirement_contract_cannot_drop_workflow(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = self.copied_root(temporary)
            path = root / "contracts/operations/historical-public-acceptance-retirement-v1.json"
            contract = json.loads(path.read_text(encoding="utf-8"))
            contract["retired_workflows"].remove(".github/workflows/vultr-readonly-preflight.yml")
            path.write_text(json.dumps(contract), encoding="utf-8")
            errors = MODULE.check_repository(root)
        self.assertTrue(any("does not bind" in error for error in errors))

    def test_historical_contract_cannot_gain_final_production_authority(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = self.copied_root(temporary)
            path = root / "contracts/operations/vultr-readonly-preflight-v1.json"
            contract = json.loads(path.read_text(encoding="utf-8"))
            contract["authority_separation"]["final_production_authority"] = True
            path.write_text(json.dumps(contract), encoding="utf-8")
            errors = MODULE.check_repository(root)
        self.assertTrue(any("production authority" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
