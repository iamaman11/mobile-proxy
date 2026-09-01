from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from verify_item20_orchestration import select_quality_run, verify_orchestration


ACTIVE_SHA = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
HISTORICAL_ITEM19_SHA = "d151dbdd156279e32a5361d304c90f996bd2d565"
CONTRACT = ROOT / "contracts/operations/item20-acceptance-v1.json"
WORKFLOW = ROOT / ".github/workflows/item20-session-orchestration.yml"


def branch() -> dict[str, object]:
    return {"name": "main", "protected": True, "commit": {"sha": ACTIVE_SHA}}


def quality() -> dict[str, object]:
    return {
        "id": 456789,
        "run_attempt": 1,
        "name": "Quality",
        "path": ".github/workflows/quality.yml",
        "event": "push",
        "head_branch": "main",
        "head_sha": ACTIVE_SHA,
        "status": "completed",
        "conclusion": "success",
        "repository": {"full_name": "iamaman11/mobile-proxy"},
    }


def issue(number: int, state: str, state_reason: str | None = None) -> dict[str, object]:
    return {"number": number, "state": state, "state_reason": state_reason}


class Item20NonLiveOrchestrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
        self.item19 = issue(124, "closed", "completed")
        self.item20 = issue(135, "open")

    def verify(self, signing: dict[str, object] | None = None, **overrides: object) -> dict[str, object]:
        values: dict[str, object] = {
            "candidate_sha": ACTIVE_SHA,
            "control_plane_sha": ACTIVE_SHA,
            "contract": self.contract,
            "branch": branch(),
            "quality_run": quality(),
            "item19_issue": self.item19,
            "item20_issue": self.item20,
            "signing_issue": signing or issue(115, "open"),
        }
        values.update(overrides)
        return verify_orchestration(**values)  # type: ignore[arg-type]

    def test_same_sha_open_signing_gate_allows_build_only_but_never_live_authority(self) -> None:
        evidence = self.verify()
        self.assertEqual(evidence["candidate_sha"], ACTIVE_SHA)
        self.assertEqual(evidence["control_plane_sha"], ACTIVE_SHA)
        self.assertTrue(evidence["candidate_control_plane_exact_equality_verified"])
        self.assertTrue(evidence["non_live_candidate_artifact_build_authorized"])
        self.assertFalse(evidence["phone_signing_gate_completed"])
        for field in (
            "fresh_acceptance_authority_verified",
            "fresh_vultr_readonly_preflight_verified",
            "provider_credential_access_performed",
            "provider_mutation_authorized",
            "phone_mutation_authorized",
            "endpoint_handoff_authorized",
            "live_execution_authorized",
            "final_production_authority",
            "provider_identifier_recorded",
            "transport_endpoint_recorded",
            "raw_phone_identifier_recorded",
        ):
            self.assertFalse(evidence[field])

    def test_closed_completed_signing_gate_still_does_not_grant_live_authority(self) -> None:
        evidence = self.verify(signing=issue(115, "closed", "completed"))
        self.assertTrue(evidence["phone_signing_gate_completed"])
        self.assertFalse(evidence["fresh_acceptance_authority_verified"])
        self.assertFalse(evidence["fresh_vultr_readonly_preflight_verified"])
        self.assertFalse(evidence["live_execution_authorized"])

    def test_distinct_candidate_and_control_plane_fail_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "candidate/control-plane SHA mismatch"):
            self.verify(candidate_sha="b" * 40)

    def test_historical_item19_sha_cannot_silently_become_active_item20_candidate(self) -> None:
        with self.assertRaisesRegex(ValueError, "candidate/control-plane SHA mismatch"):
            self.verify(candidate_sha=HISTORICAL_ITEM19_SHA)

    def test_protected_main_advance_invalidates_candidate(self) -> None:
        advanced = branch()
        advanced["commit"] = {"sha": "b" * 40}
        with self.assertRaisesRegex(ValueError, "exact current protected main"):
            self.verify(branch=advanced)

    def test_item_trackers_fail_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "Item 19"):
            self.verify(item19_issue=issue(124, "open"))
        with self.assertRaisesRegex(ValueError, "Item 20"):
            self.verify(item20_issue=issue(135, "closed", "completed"))

    def test_signing_gate_unknown_terminal_state_fails_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "neither OPEN nor closed completed"):
            self.verify(signing=issue(115, "closed", "not_planned"))

    def test_quality_selection_is_exact_and_unambiguous(self) -> None:
        selected = select_quality_run(ACTIVE_SHA, {"workflow_runs": [quality()]})
        self.assertEqual(selected["id"], 456789)

        wrong = quality()
        wrong["head_sha"] = "b" * 40
        with self.assertRaisesRegex(ValueError, "exactly one eligible"):
            select_quality_run(ACTIVE_SHA, {"workflow_runs": [wrong]})

        duplicate = quality().copy()
        duplicate["id"] = 456790
        with self.assertRaisesRegex(ValueError, "exactly one eligible"):
            select_quality_run(ACTIVE_SHA, {"workflow_runs": [quality(), duplicate]})

    def test_workflow_is_hosted_build_only_and_same_sha_bound(self) -> None:
        body = WORKFLOW.read_text(encoding="utf-8")
        for required in (
            "name: Item 20 non-live session orchestration",
            "workflow_dispatch:",
            "runs-on: ubuntu-latest",
            "verify_item20_orchestration.py",
            "ref: ${{ github.sha }}",
            "ref: ${{ needs.validate.outputs.candidate_sha }}",
            "item20-server-candidate-${{ env.CANDIDATE_SHA }}",
            "item19-acceptance-lifecycle prepare-artifact",
            "scripts/select_item20_candidate_evidence.py verify-contract",
            "scripts/verify_item20_readiness_artifact.py select-artifact",
            "scripts/verify_item20_readiness_artifact.py verify",
            "Readiness artifact consumed: true",
            "Fresh acceptance authority verified: true",
            "Fresh Vultr read-only preflight verified: true",
            "Provider mutation authorized: false",
            "Phone mutation authorized: false",
            "Endpoint handoff authorized: false",
            "Live execution authorized: false",
        ):
            self.assertIn(required, body)

        for forbidden in (
            "acceptance-vultr",
            "production-vultr",
            "VULTR_API_KEY",
            "VULTR_SSH_PRIVATE_KEY",
            "ITEM20_PHONE_HANDOFF_TOKEN",
            "self-hosted",
            "secrets.",
            "api.vultr.com",
            "/v2/instances",
            "gh workflow run",
            "/dispatches",
            "adb ",
        ):
            self.assertNotIn(forbidden, body)

    def test_contract_describes_only_same_sha_non_live_orchestration(self) -> None:
        self.assertEqual(
            self.contract["orchestration"],
            {
                "candidate_source": "same_exact_current_protected_main_as_control_plane",
                "control_plane_source": "exact_current_protected_main",
                "endpoint_handoff": "not_implemented",
                "executor": "github-hosted",
                "phone_execution": False,
                "provider_credentials": "forbidden",
                "provider_environment": "none",
                "provider_mutation": False,
                "server_artifact_name_template": "item20-server-candidate-<candidate_sha>",
                "status": "protected_validation_and_candidate_build_only",
                "trigger": "workflow_dispatch",
                "verifier": "scripts/verify_item20_orchestration.py",
                "workflow": ".github/workflows/item20-session-orchestration.yml",
            },
        )


if __name__ == "__main__":
    unittest.main()
