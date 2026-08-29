import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "check_vm_ownership_contract.py"
SPEC = importlib.util.spec_from_file_location("vm_ownership_contract", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
REPO_ROOT = Path(__file__).resolve().parents[2]
CONTRACT_PATH = REPO_ROOT / "contracts/governance/vm-ownership-v1.json"


class VmOwnershipContractTests(unittest.TestCase):
    def validate_changed(self, change):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            contract_path = root / "contracts/governance/vm-ownership-v1.json"
            document_path = root / "docs/architecture/vm-ownership-boundary.md"
            contract_path.parent.mkdir(parents=True)
            document_path.parent.mkdir(parents=True)
            contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
            change(contract)
            contract_path.write_text(json.dumps(contract), encoding="utf-8")
            document_path.write_text(
                (REPO_ROOT / "docs/architecture/vm-ownership-boundary.md").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            return MODULE.check_repository(root)

    def test_repository_contract_passes(self):
        self.assertEqual(MODULE.check_repository(REPO_ROOT), [])

    def test_missing_tag_proof_is_rejected(self):
        errors = self.validate_changed(
            lambda contract: contract["operations"]["delete"].pop("requires_exact_required_tags")
        )
        self.assertTrue(any("delete must require" in error for error in errors))

    def test_arbitrary_operator_uuid_is_forbidden(self):
        errors = self.validate_changed(
            lambda contract: contract["forbidden"].remove("arbitrary_instance_uuid_from_operator_input")
        )
        self.assertTrue(any("forbidden set differs" in error for error in errors))

    def test_recreate_requires_atomic_binding_replacement(self):
        errors = self.validate_changed(
            lambda contract: contract["operations"]["recreate"].pop(
                "atomically_replace_uuid_and_generation_after_verification"
            )
        )
        self.assertTrue(any("recreate must verify" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
