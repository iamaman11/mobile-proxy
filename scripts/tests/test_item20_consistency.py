from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from check_item20_consistency import (
    ITEM20_CANDIDATE_EVIDENCE,
    ITEM20_CONTRACT,
    PHYSICAL_RUNBOOK,
    check_item20_candidate_evidence_verifier_text,
    check_item20_contract,
    check_physical_runbook_text,
    check_repository,
)


class Item20ConsistencyTests(unittest.TestCase):
    def test_repository_item20_identity_and_gate_boundaries_are_consistent(self) -> None:
        self.assertEqual(check_repository(ROOT), [])

    def test_physical_runbook_matches_current_item20_state(self) -> None:
        physical = (ROOT / PHYSICAL_RUNBOOK).read_text(encoding="utf-8")
        self.assertEqual(check_physical_runbook_text(physical), [])

    def test_stale_item19_active_wording_fails_closed(self) -> None:
        physical = (ROOT / PHYSICAL_RUNBOOK).read_text(encoding="utf-8")
        stale = physical.replace(
            "Item 19 provider proof is COMPLETE",
            "while Item 19 is ACTIVE",
            1,
        )
        self.assertNotEqual(check_physical_runbook_text(stale), [])

    def test_stale_item19_execution_plane_fails_closed(self) -> None:
        physical = (ROOT / PHYSICAL_RUNBOOK).read_text(encoding="utf-8")
        stale = physical.replace(
            "protected typed Item 20 acceptance lifecycle",
            "GitHub-hosted item-19 Vultr acceptance lifecycle",
            1,
        )
        self.assertNotEqual(check_physical_runbook_text(stale), [])

    def test_item20_admission_contract_is_validation_only(self) -> None:
        contract = json.loads((ROOT / ITEM20_CONTRACT).read_text(encoding="utf-8"))
        self.assertEqual(check_item20_contract(contract), [])

    def test_item20_admission_contract_cannot_grant_provider_mutation(self) -> None:
        contract = json.loads((ROOT / ITEM20_CONTRACT).read_text(encoding="utf-8"))
        mutated = copy.deepcopy(contract)
        mutated["authorization"]["provider_mutation_authorized"] = True
        self.assertNotEqual(check_item20_contract(mutated), [])

    def test_item20_admission_contract_cannot_claim_endpoint_handoff(self) -> None:
        contract = json.loads((ROOT / ITEM20_CONTRACT).read_text(encoding="utf-8"))
        mutated = copy.deepcopy(contract)
        mutated["handoff"]["status"] = "implemented"
        self.assertNotEqual(check_item20_contract(mutated), [])

    def test_pure_candidate_verifier_contract_is_exact_and_not_wired(self) -> None:
        contract = json.loads((ROOT / ITEM20_CONTRACT).read_text(encoding="utf-8"))
        mutated = copy.deepcopy(contract)
        mutated["future_live_candidate_verifier"]["workflow_wiring"] = "implemented"
        self.assertNotEqual(check_item20_contract(mutated), [])

        mutated = copy.deepcopy(contract)
        mutated["future_live_candidate_verifier"]["selection"] = "latest_issue_comment_run"
        self.assertNotEqual(check_item20_contract(mutated), [])

    def test_historical_candidate_quality_identity_cannot_drift(self) -> None:
        contract = json.loads((ROOT / ITEM20_CONTRACT).read_text(encoding="utf-8"))
        mutated = copy.deepcopy(contract)
        mutated["immutable_candidate"]["item19_quality_run_id"] = 999
        self.assertNotEqual(check_item20_contract(mutated), [])

        mutated = copy.deepcopy(contract)
        mutated["future_live_candidate_verifier"]["candidate_quality_run_attempt"] = 2
        self.assertNotEqual(check_item20_contract(mutated), [])

    def test_pure_candidate_verifier_implementation_boundary_is_protected(self) -> None:
        verifier = (ROOT / ITEM20_CANDIDATE_EVIDENCE).read_text(encoding="utf-8")
        self.assertEqual(check_item20_candidate_evidence_verifier_text(verifier), [])

    def test_pure_candidate_verifier_missing_required_function_fails_closed(self) -> None:
        verifier = (ROOT / ITEM20_CANDIDATE_EVIDENCE).read_text(encoding="utf-8")
        mutated = verifier.replace(
            "def verify_artifact_metadata(",
            "def verify_artifact_metadata_removed(",
            1,
        )
        self.assertNotEqual(check_item20_candidate_evidence_verifier_text(mutated), [])

    def test_pure_candidate_verifier_external_io_token_fails_closed(self) -> None:
        verifier = (ROOT / ITEM20_CANDIDATE_EVIDENCE).read_text(encoding="utf-8")
        mutated = verifier + '\nrequests.get("https://example.invalid")\n'
        self.assertNotEqual(check_item20_candidate_evidence_verifier_text(mutated), [])

    def test_pure_candidate_verifier_provider_mutation_token_fails_closed(self) -> None:
        verifier = (ROOT / ITEM20_CANDIDATE_EVIDENCE).read_text(encoding="utf-8")
        mutated = verifier + "\ncreate_instance(candidate_sha)\n"
        self.assertNotEqual(check_item20_candidate_evidence_verifier_text(mutated), [])


if __name__ == "__main__":
    unittest.main()
