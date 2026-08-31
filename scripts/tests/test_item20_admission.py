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

from verify_item20_admission import verify_admission, verify_contract


CANDIDATE = "d151dbdd156279e32a5361d304c90f996bd2d565"
CONTROL_PLANE = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
CONTRACT = ROOT / "contracts/operations/item20-acceptance-v1.json"


def branch() -> dict[str, object]:
    return {"name": "main", "protected": True, "commit": {"sha": CONTROL_PLANE}}


def quality() -> dict[str, object]:
    return {
        "id": 123456,
        "run_attempt": 1,
        "name": "Quality",
        "path": ".github/workflows/quality.yml",
        "event": "push",
        "head_branch": "main",
        "head_sha": CONTROL_PLANE,
        "status": "completed",
        "conclusion": "success",
        "repository": {"full_name": "iamaman11/mobile-proxy"},
    }


def issue(number: int, state: str, state_reason: str | None = None) -> dict[str, object]:
    return {"number": number, "state": state, "state_reason": state_reason}


def phone_preflight() -> dict[str, object]:
    return {
        "format_version": 1,
        "repository": "iamaman11/mobile-proxy",
        "canonical_sha": CONTROL_PLANE,
        "mode": "read_only",
        "required_runner_labels": ["self-hosted", "Linux", "X64", "android-production"],
        "required_tools": {"adb": True, "python": True, "git": True, "curl": True},
        "device": {
            "device_count": 1,
            "registered_device_match": True,
            "adb_state": "device",
            "shell_probe": True,
        },
        "raw_device_identifier_recorded": False,
        "mutation_performed": False,
        "accepted": True,
    }


class Item20AdmissionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
        self.item19 = issue(124, "closed", "completed")
        self.item20 = issue(135, "open")
        self.signing = issue(115, "closed", "completed")
        self.preflight = phone_preflight()

    def admit(self, **overrides: object) -> dict[str, object]:
        values: dict[str, object] = {
            "candidate_sha": CANDIDATE,
            "control_plane_sha": CONTROL_PLANE,
            "contract": self.contract,
            "branch": branch(),
            "quality_run": quality(),
            "item19_issue": self.item19,
            "item20_issue": self.item20,
            "signing_issue": self.signing,
            "phone_preflight": self.preflight,
        }
        values.update(overrides)
        return verify_admission(**values)  # type: ignore[arg-type]

    def test_contract_is_exact_and_validation_only(self) -> None:
        verify_contract(self.contract)
        evidence = self.admit()
        self.assertEqual(evidence["candidate_sha"], CANDIDATE)
        self.assertEqual(evidence["control_plane_sha"], CONTROL_PLANE)
        for field in (
            "fresh_acceptance_authority_verified",
            "fresh_vultr_readonly_preflight_verified",
            "provider_mutation_authorized",
            "phone_mutation_authorized",
            "endpoint_handoff_authorized",
            "live_execution_authorized",
            "final_production_authority",
            "transport_endpoint_recorded",
            "provider_identifier_recorded",
            "raw_phone_identifier_recorded",
        ):
            self.assertFalse(evidence[field])

    def test_open_signing_gate_fails_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "signing-continuity"):
            self.admit(signing_issue=issue(115, "open"))

    def test_candidate_mismatch_fails_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "Item 19 closeout"):
            self.admit(candidate_sha="b" * 40)

    def test_control_plane_must_be_exact_current_protected_main(self) -> None:
        bad_branch = branch()
        bad_branch["commit"] = {"sha": "b" * 40}
        with self.assertRaisesRegex(ValueError, "exact current protected main"):
            self.admit(branch=bad_branch)

    def test_quality_must_match_exact_control_plane(self) -> None:
        bad_quality = quality()
        bad_quality["head_sha"] = "b" * 40
        with self.assertRaisesRegex(ValueError, "Quality run"):
            self.admit(quality_run=bad_quality)

    def test_private_preflight_must_match_control_plane(self) -> None:
        bad = phone_preflight()
        bad["canonical_sha"] = "b" * 40
        with self.assertRaisesRegex(ValueError, "preflight evidence"):
            self.admit(phone_preflight=bad)

    def test_private_preflight_cannot_hide_mutation_or_identifier(self) -> None:
        for key, value in (
            ("mutation_performed", True),
            ("raw_device_identifier_recorded", True),
        ):
            bad = phone_preflight()
            bad[key] = value
            with self.assertRaisesRegex(ValueError, "preflight evidence"):
                self.admit(phone_preflight=bad)

    def test_private_preflight_requires_exact_runner_and_device_binding(self) -> None:
        bad_labels = phone_preflight()
        bad_labels["required_runner_labels"] = ["self-hosted", "android-production"]
        with self.assertRaisesRegex(ValueError, "preflight evidence"):
            self.admit(phone_preflight=bad_labels)

        bad_device = phone_preflight()
        bad_device["device"] = copy.deepcopy(bad_device["device"])
        assert isinstance(bad_device["device"], dict)
        bad_device["device"]["device_count"] = 2
        with self.assertRaisesRegex(ValueError, "one exact registered"):
            self.admit(phone_preflight=bad_device)

    def test_item19_must_remain_closed_completed(self) -> None:
        with self.assertRaisesRegex(ValueError, "Item 19"):
            self.admit(item19_issue=issue(124, "closed", None))

    def test_item20_tracker_must_remain_open(self) -> None:
        with self.assertRaisesRegex(ValueError, "Item 20"):
            self.admit(item20_issue=issue(135, "closed", "completed"))

    def test_contract_cannot_grant_live_authority(self) -> None:
        mutated = copy.deepcopy(self.contract)
        mutated["authorization"]["provider_mutation_authorized"] = True
        with self.assertRaisesRegex(ValueError, "validation-only"):
            verify_contract(mutated)

    def test_contract_cannot_claim_handoff_is_implemented(self) -> None:
        mutated = copy.deepcopy(self.contract)
        mutated["handoff"]["status"] = "implemented"
        with self.assertRaisesRegex(ValueError, "handoff boundary"):
            verify_contract(mutated)

    def test_future_live_window_requires_fresh_exact_candidate_authority(self) -> None:
        mutated = copy.deepcopy(self.contract)
        mutated["future_live_candidate_evidence"]["acceptance_authority"] = (
            "reuse_historical_item19_authority"
        )
        with self.assertRaisesRegex(ValueError, "fresh candidate authority"):
            verify_contract(mutated)

        mutated = copy.deepcopy(self.contract)
        mutated["future_live_candidate_evidence"]["vultr_readonly_preflight"] = (
            "reuse_historical_item19_preflight"
        )
        with self.assertRaisesRegex(ValueError, "fresh candidate authority"):
            verify_contract(mutated)

    def test_non_live_core_cannot_claim_fresh_external_gates_are_verified(self) -> None:
        evidence = self.admit()
        self.assertFalse(evidence["fresh_acceptance_authority_verified"])
        self.assertFalse(evidence["fresh_vultr_readonly_preflight_verified"])
        self.assertFalse(evidence["live_execution_authorized"])


if __name__ == "__main__":
    unittest.main()
