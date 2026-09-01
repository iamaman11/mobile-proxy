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
    HISTORICAL_ITEM19_SHA,
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
        stale = physical.replace("Item 19 provider proof is COMPLETE", "while Item 19 is ACTIVE", 1)
        self.assertNotEqual(check_physical_runbook_text(stale), [])

    def test_stale_item19_execution_plane_fails_closed(self) -> None:
        physical = (ROOT / PHYSICAL_RUNBOOK).read_text(encoding="utf-8")
        stale = physical.replace(
            "protected typed Item 20 acceptance lifecycle",
            "GitHub-hosted item-19 Vultr acceptance lifecycle",
            1,
        )
        self.assertNotEqual(check_physical_runbook_text(stale), [])

    def test_item20_contract_is_single_sha_validation_only(self) -> None:
        contract = json.loads((ROOT / ITEM20_CONTRACT).read_text(encoding="utf-8"))
        self.assertEqual(check_item20_contract(contract), [])

    def test_distinct_candidate_and_control_plane_fails_closed(self) -> None:
        contract = json.loads((ROOT / ITEM20_CONTRACT).read_text(encoding="utf-8"))
        mutated = copy.deepcopy(contract)
        mutated["identity"]["exact_equality_required"] = False
        self.assertNotEqual(check_item20_contract(mutated), [])

        mutated = copy.deepcopy(contract)
        mutated["admission"]["candidate_must_equal_control_plane_sha"] = False
        self.assertNotEqual(check_item20_contract(mutated), [])

    def test_historical_item19_sha_cannot_become_active_candidate(self) -> None:
        contract = json.loads((ROOT / ITEM20_CONTRACT).read_text(encoding="utf-8"))
        mutated = copy.deepcopy(contract)
        mutated["identity"]["candidate_sha"] = HISTORICAL_ITEM19_SHA
        self.assertNotEqual(check_item20_contract(mutated), [])

    def test_historical_item19_record_cannot_drift(self) -> None:
        contract = json.loads((ROOT / ITEM20_CONTRACT).read_text(encoding="utf-8"))
        mutated = copy.deepcopy(contract)
        mutated["historical_item19_proof"]["candidate_sha"] = "0" * 40
        self.assertNotEqual(check_item20_contract(mutated), [])

        mutated = copy.deepcopy(contract)
        mutated["historical_item19_proof"]["item19_quality_run_id"] = 999
        self.assertNotEqual(check_item20_contract(mutated), [])

    def test_retired_two_sha_contract_semantic_fails_closed(self) -> None:
        contract = json.loads((ROOT / ITEM20_CONTRACT).read_text(encoding="utf-8"))
        mutated = copy.deepcopy(contract)
        mutated["admission"]["control_plane_may_advance_without_redefining_candidate"] = True
        self.assertNotEqual(check_item20_contract(mutated), [])

    def test_item20_admission_contract_cannot_grant_provider_mutation(self) -> None:
        contract = json.loads((ROOT / ITEM20_CONTRACT).read_text(encoding="utf-8"))
        mutated = copy.deepcopy(contract)
        mutated["authorization"]["provider_mutation_authorized"] = True
        self.assertNotEqual(check_item20_contract(mutated), [])

    def test_pure_candidate_verifier_implementation_boundary_is_protected(self) -> None:
        verifier = (ROOT / ITEM20_CANDIDATE_EVIDENCE).read_text(encoding="utf-8")
        self.assertEqual(check_item20_candidate_evidence_verifier_text(verifier), [])

    def test_pure_candidate_verifier_missing_single_sha_guard_fails_closed(self) -> None:
        verifier = (ROOT / ITEM20_CANDIDATE_EVIDENCE).read_text(encoding="utf-8")
        mutated = verifier.replace(
            "candidate_sha != control_plane_sha",
            "False",
        )
        self.assertNotEqual(check_item20_candidate_evidence_verifier_text(mutated), [])

    def test_pure_candidate_verifier_external_io_token_fails_closed(self) -> None:
        verifier = (ROOT / ITEM20_CANDIDATE_EVIDENCE).read_text(encoding="utf-8")
        mutated = verifier + '\nrequests.get("https://example.invalid")\n'
        self.assertNotEqual(check_item20_candidate_evidence_verifier_text(mutated), [])

    def test_pure_candidate_verifier_cannot_hardcode_historical_item19_candidate(self) -> None:
        verifier = (ROOT / ITEM20_CANDIDATE_EVIDENCE).read_text(encoding="utf-8")
        mutated = verifier + f'\n_IMMUTABLE_CANDIDATE = "{HISTORICAL_ITEM19_SHA}"\n'
        self.assertNotEqual(check_item20_candidate_evidence_verifier_text(mutated), [])


if __name__ == "__main__":
    unittest.main()
