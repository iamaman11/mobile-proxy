import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "check_vultr_readonly_preflight_policy.py"
SPEC = importlib.util.spec_from_file_location("vultr_readonly_policy", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
ROOT = Path(__file__).resolve().parents[2]


class VultrReadonlyPolicyMutationTests(unittest.TestCase):
    def copied_root(self, temporary: str) -> Path:
        root = Path(temporary)
        (root / "contracts/operations").mkdir(parents=True)
        (root / ".github/workflows").mkdir(parents=True)
        for relative in (
            "contracts/operations/vultr-readonly-preflight-v1.json",
            "contracts/operations/github-control-plane-v1.json",
            ".github/workflows/vultr-readonly-preflight.yml",
        ):
            destination = root / relative
            shutil.copy2(ROOT / relative, destination)
        return root

    def test_production_environment_substitution_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = self.copied_root(temporary)
            workflow = root / ".github/workflows/vultr-readonly-preflight.yml"
            workflow.write_text(
                workflow.read_text(encoding="utf-8").replace(
                    "environment: acceptance-vultr", "environment: production-vultr"
                ),
                encoding="utf-8",
            )
            errors = MODULE.check_repository(root)
        self.assertTrue(any("production" in error or "acceptance-vultr" in error for error in errors))

    def test_vm_endpoint_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = self.copied_root(temporary)
            workflow = root / ".github/workflows/vultr-readonly-preflight.yml"
            workflow.write_text(
                workflow.read_text(encoding="utf-8").replace(
                    "https://api.vultr.com/v2/account", "https://api.vultr.com/v2/instances"
                ),
                encoding="utf-8",
            )
            errors = MODULE.check_repository(root)
        self.assertTrue(any("read-only" in error or "provider" in error for error in errors))

    def test_mutating_method_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = self.copied_root(temporary)
            workflow = root / ".github/workflows/vultr-readonly-preflight.yml"
            workflow.write_text(
                workflow.read_text(encoding="utf-8").replace("--request GET", "--request POST"),
                encoding="utf-8",
            )
            errors = MODULE.check_repository(root)
        self.assertTrue(any("mutation" in error or "read-only" in error for error in errors))

    def test_contract_cannot_grant_final_production_authority(self):
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
