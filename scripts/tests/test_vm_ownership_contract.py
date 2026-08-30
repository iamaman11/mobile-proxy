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
    "contracts/operations/production-topology-v1.json",
    "contracts/operations/github-control-plane-v1.json",
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

    def test_item18_live_provider_mutation_cannot_be_enabled(self):
        errors = self.validate_contract_changed(
            lambda contract: contract["item_18_execution"].update(
                {"live_provider_mutation": True}
            )
        )
        self.assertTrue(any("item 18 execution boundary" in error for error in errors))

    def test_item18_production_authority_cannot_be_enabled(self):
        errors = self.validate_contract_changed(
            lambda contract: contract["item_18_execution"].update(
                {"production_vultr_authority": True}
            )
        )
        self.assertTrue(any("item 18 execution boundary" in error for error in errors))

    def test_topology_cannot_regress_item18_adapter(self):
        errors = self.validate_json_changed(
            "contracts/operations/production-topology-v1.json",
            lambda topology: topology["migration_status"].update(
                {"vultr_adapter": "not_implemented"}
            ),
        )
        self.assertTrue(any("keep item 18 typed Vultr adapter" in error for error in errors))

    def test_topology_cannot_forge_item19_terminal_live_proof(self):
        errors = self.validate_json_changed(
            "contracts/operations/production-topology-v1.json",
            lambda topology: topology["migration_status"].update(
                {"vultr_live_lifecycle": "enabled"}
            ),
        )
        self.assertTrue(any("terminal item-19 live proof" in error for error in errors))

    def test_topology_cannot_reuse_terminal_item19_intent_for_item20(self):
        errors = self.validate_json_changed(
            "contracts/operations/production-topology-v1.json",
            lambda topology: topology["migration_status"].update(
                {"next_acceptance_lifecycle": "reuse_item_19_intent"}
            ),
        )
        self.assertTrue(any("fresh item-20 lifecycle intent" in error for error in errors))

    def test_control_plane_cannot_enable_item19_live_execution_early(self):
        errors = self.validate_json_changed(
            "contracts/operations/github-control-plane-v1.json",
            lambda control: control["vultr_lifecycle_adapter"].update(
                {"live_execution": "enabled"}
            ),
        )
        self.assertTrue(any("live_execution" in error for error in errors))

    def test_control_plane_cannot_gain_production_authority(self):
        errors = self.validate_json_changed(
            "contracts/operations/github-control-plane-v1.json",
            lambda control: control["vultr_lifecycle_adapter"].update(
                {"production_vultr_authority": True}
            ),
        )
        self.assertTrue(any("production_vultr_authority" in error for error in errors))

    def test_control_plane_cannot_relax_full_provider_enumeration(self):
        errors = self.validate_json_changed(
            "contracts/operations/github-control-plane-v1.json",
            lambda control: control["vultr_lifecycle_adapter"].update(
                {"full_provider_enumeration": "first_page_only"}
            ),
        )
        self.assertTrue(any("full_provider_enumeration" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
