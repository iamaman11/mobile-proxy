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
            copies = (
                "contracts/governance/vm-ownership-v1.json",
                "docs/architecture/vm-ownership-boundary.md",
                "crates/proxy-core/src/provider_lifecycle.rs",
                "apps/operator-cli/src/vultr_lifecycle.rs",
            )
            for relative in copies:
                source = REPO_ROOT / relative
                target = root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
            contract_path = root / "contracts/governance/vm-ownership-v1.json"
            contract = json.loads(contract_path.read_text(encoding="utf-8"))
            change(contract)
            contract_path.write_text(json.dumps(contract), encoding="utf-8")
            return MODULE.check_repository(root)

    def test_repository_contract_passes(self):
        self.assertEqual(MODULE.check_repository(REPO_ROOT), [])

    def test_missing_exact_ownership_proof_is_rejected(self):
        errors = self.validate_changed(
            lambda contract: contract["operations"]["delete"].pop(
                "requires_exact_ownership_metadata"
            )
        )
        self.assertTrue(any("delete must require" in error for error in errors))

    def test_missing_expected_generation_is_rejected(self):
        errors = self.validate_changed(
            lambda contract: contract["operations"]["stop"].pop("requires_expected_generation")
        )
        self.assertTrue(any("stop must require" in error for error in errors))

    def test_fuzzy_matching_must_remain_forbidden(self):
        errors = self.validate_changed(
            lambda contract: contract["forbidden"].remove("fuzzy_or_prefix_ownership_matching")
        )
        self.assertTrue(any("forbidden set differs" in error for error in errors))

    def test_duplicate_ownership_claim_rejection_is_permanent(self):
        errors = self.validate_changed(
            lambda contract: contract["fail_closed"].remove("duplicate_ownership_claim")
        )
        self.assertTrue(any("fail_closed set differs" in error for error in errors))

    def test_replace_requires_atomic_generation_cas(self):
        errors = self.validate_changed(
            lambda contract: contract["operations"]["replace"].pop(
                "atomically_replace_provider_identity_and_generation_with_compare_and_swap"
            )
        )
        self.assertTrue(any("replace must advance" in error for error in errors))

    def test_item18_live_provider_mutation_cannot_be_enabled(self):
        errors = self.validate_changed(
            lambda contract: contract["item_18_execution"].update(
                {"live_provider_mutation": True}
            )
        )
        self.assertTrue(any("item 18 execution boundary" in error for error in errors))

    def test_item18_production_authority_cannot_be_enabled(self):
        errors = self.validate_changed(
            lambda contract: contract["item_18_execution"].update(
                {"production_vultr_authority": True}
            )
        )
        self.assertTrue(any("item 18 execution boundary" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
