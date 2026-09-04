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
COPIES = (
    "contracts/governance/vm-ownership-v1.json",
    "contracts/operations/historical-public-acceptance-retirement-v1.json",
    "contracts/operations/project-authority-v2.json",
    "contracts/operations/production-topology-v2.json",
    "docs/architecture/vm-ownership-boundary.md",
    "docs/architecture/acceptance-vm-binding-store.md",
    "crates/proxy-core/src/provider_lifecycle.rs",
    "apps/operator-cli/src/vultr_lifecycle.rs",
    "apps/operator-cli/src/vultr_client.rs",
    "apps/operator-cli/src/github_vm_binding_store.rs",
)


class VmOwnershipContractTests(unittest.TestCase):
    def validate_json_changed(self, relative, change):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for copied in COPIES:
                source = REPO_ROOT / copied
                target = root / copied
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
            target_path = root / relative
            document = json.loads(target_path.read_text(encoding="utf-8"))
            change(document)
            target_path.write_text(json.dumps(document), encoding="utf-8")
            return MODULE.check_repository(root)

    def validate_contract_changed(self, change):
        return self.validate_json_changed(
            "contracts/governance/vm-ownership-v1.json", change
        )

    def test_repository_contract_passes(self):
        self.assertEqual(MODULE.check_repository(REPO_ROOT), [])

    def test_missing_exact_ownership_proof_is_rejected(self):
        errors = self.validate_contract_changed(
            lambda contract: contract["operations"]["delete"].pop(
                "requires_exact_ownership_metadata"
            )
        )
        self.assertTrue(any("delete must require" in error for error in errors))

    def test_missing_expected_generation_is_rejected(self):
        errors = self.validate_contract_changed(
            lambda contract: contract["operations"]["stop"].pop("requires_expected_generation")
        )
        self.assertTrue(any("stop must require" in error for error in errors))

    def test_fuzzy_matching_must_remain_forbidden(self):
        errors = self.validate_contract_changed(
            lambda contract: contract["forbidden"].remove("fuzzy_or_prefix_ownership_matching")
        )
        self.assertTrue(any("forbidden set differs" in error for error in errors))

    def test_duplicate_ownership_claim_rejection_is_permanent(self):
        errors = self.validate_contract_changed(
            lambda contract: contract["fail_closed"].remove("duplicate_ownership_claim")
        )
        self.assertTrue(any("fail_closed set differs" in error for error in errors))

    def test_replace_requires_atomic_generation_cas(self):
        errors = self.validate_contract_changed(
            lambda contract: contract["operations"]["replace"].pop(
                "atomically_replace_provider_identity_and_generation_with_compare_and_swap"
            )
        )
        self.assertTrue(any("replace must advance" in error for error in errors))

    def test_contract_cannot_gain_runtime_execution_authority(self):
        errors = self.validate_contract_changed(
            lambda contract: contract["current_authority"].update(
                {"execution_authority": True}
            )
        )
        self.assertTrue(any("current authority binding differs" in error for error in errors))

    def test_contract_cannot_move_runtime_authority_back_public(self):
        errors = self.validate_contract_changed(
            lambda contract: contract["current_authority"].update(
                {"runtime_deployment_controller": "iamaman11/mobile-proxy"}
            )
        )
        self.assertTrue(any("current authority binding differs" in error for error in errors))

    def test_historical_item18_item19_chronology_cannot_become_current(self):
        errors = self.validate_contract_changed(
            lambda contract: contract["historical_execution_context"].update(
                {"item18_item19_public_acceptance_chronology": "current_runtime_authority"}
            )
        )
        self.assertTrue(any("historical execution chronology" in error for error in errors))

    def test_vm_target_must_keep_shared_private_controller_kernel(self):
        errors = self.validate_json_changed(
            "contracts/operations/production-topology-v2.json",
            lambda topology: topology["targets"]["vm-production"].update(
                {"reuses_same_controller_kernel": False}
            ),
        )
        self.assertTrue(any("fail-closed private controller kernel" in error for error in errors))

    def test_item19_binding_store_doc_must_remain_historical(self):
        errors = self.validate_json_changed(
            "contracts/operations/historical-public-acceptance-retirement-v1.json",
            lambda retirement: retirement["historical_execution_docs"].remove(
                "docs/architecture/acceptance-vm-binding-store.md"
            ),
        )
        self.assertTrue(any("classified as historical-only" in error for error in errors))

    def test_vm_doc_must_separate_current_safety_from_historical_chronology(self):
        errors = self.validate_json_changed(
            "contracts/operations/historical-public-acceptance-retirement-v1.json",
            lambda retirement: retirement["mixed_context_docs"].pop(
                "docs/architecture/vm-ownership-boundary.md"
            ),
        )
        self.assertTrue(any("separate current safety" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
