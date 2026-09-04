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
    FINAL_RELEASE_V1,
    HISTORICAL_ITEM19_SHA,
    ITEM20_CANDIDATE_EVIDENCE,
    ITEM20_CONTRACT,
    RETIREMENT,
    check_final_release_v1,
    check_item20_candidate_evidence_verifier_text,
    check_item20_contract,
    check_repository,
    check_retirement_contract,
)


class Item20ConsistencyTests(unittest.TestCase):
    def test_repository_retained_item20_boundaries_are_consistent(self) -> None:
        self.assertEqual(check_repository(ROOT), [])

    def test_retirement_registry_keeps_old_item20_execution_historical(self) -> None:
        retirement = json.loads((ROOT / RETIREMENT).read_text(encoding="utf-8"))
        self.assertEqual(check_retirement_contract(retirement), [])

        mutated = copy.deepcopy(retirement)
        mutated["historical_execution_docs"].remove(
            "docs/physical-phone-acceptance-runbook.md"
        )
        self.assertNotEqual(check_retirement_contract(mutated), [])

    def test_retirement_registry_keeps_final_release_v1_historical(self) -> None:
        retirement = json.loads((ROOT / RETIREMENT).read_text(encoding="utf-8"))
        mutated = copy.deepcopy(retirement)
        mutated["historical_contract_snapshots"].remove(
            "contracts/operations/final-release-authority-v1.json"
        )
        self.assertNotEqual(check_retirement_contract(mutated), [])

    def test_final_release_v1_cannot_regain_execution_authority(self) -> None:
        contract = json.loads((ROOT / FINAL_RELEASE_V1).read_text(encoding="utf-8"))
        self.assertEqual(check_final_release_v1(contract), [])

        mutated = copy.deepcopy(contract)
        mutated["execution_authority"] = True
        self.assertNotEqual(check_final_release_v1(mutated), [])

    def test_final_release_v1_cannot_stop_pointing_to_product_release_v2(self) -> None:
        contract = json.loads((ROOT / FINAL_RELEASE_V1).read_text(encoding="utf-8"))
        mutated = copy.deepcopy(contract)
        mutated["superseded_by"] = "contracts/operations/final-release-authority-v1.json"
        self.assertNotEqual(check_final_release_v1(mutated), [])

    def test_item20_contract_retains_single_sha_validation_only(self) -> None:
        contract = json.loads((ROOT / ITEM20_CONTRACT).read_text(encoding="utf-8"))
        self.assertEqual(check_item20_contract(contract), [])

    def test_distinct_candidate_and_control_plane_fails_closed(self) -> None:
        contract = json.loads((ROOT / ITEM20_CONTRACT).read_text(encoding="utf-8"))
        mutated = copy.deepcopy(contract)
        mutated["identity"]["exact_equality_required"] = False
        self.assertNotEqual(check_item20_contract(mutated), [])

    def test_historical_item19_record_cannot_drift(self) -> None:
        contract = json.loads((ROOT / ITEM20_CONTRACT).read_text(encoding="utf-8"))
        mutated = copy.deepcopy(contract)
        mutated["historical_item19_proof"]["candidate_sha"] = "0" * 40
        self.assertNotEqual(check_item20_contract(mutated), [])

        mutated = copy.deepcopy(contract)
        mutated["historical_item19_proof"]["item19_quality_run_id"] = 999
        self.assertNotEqual(check_item20_contract(mutated), [])

    def test_item20_contract_cannot_grant_provider_mutation(self) -> None:
        contract = json.loads((ROOT / ITEM20_CONTRACT).read_text(encoding="utf-8"))
        mutated = copy.deepcopy(contract)
        mutated["authorization"]["provider_mutation_authorized"] = True
        self.assertNotEqual(check_item20_contract(mutated), [])

    def test_item20_contract_cannot_promote_historical_item19_candidate(self) -> None:
        contract = json.loads((ROOT / ITEM20_CONTRACT).read_text(encoding="utf-8"))
        mutated = copy.deepcopy(contract)
        mutated["identity"]["candidate_sha"] = HISTORICAL_ITEM19_SHA
        self.assertEqual(
            mutated["authorization"]["live_execution_authorized"],
            False,
        )
        self.assertEqual(
            mutated["authorization"]["provider_mutation_authorized"],
            False,
        )

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
