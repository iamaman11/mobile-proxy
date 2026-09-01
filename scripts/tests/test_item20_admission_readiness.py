from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "select_item20_candidate_evidence.py"
CONTRACT = ROOT / "contracts" / "operations" / "item20-admission-readiness-v1.json"
WORKFLOW = ROOT / ".github" / "workflows" / "item20-admission-readiness.yml"
SESSION_WORKFLOW = ROOT / ".github" / "workflows" / "item20-session-orchestration.yml"
ACTIVE_SHA = "a" * 40
OTHER_SHA = "b" * 40
HISTORICAL_ITEM19_SHA = "d151dbdd156279e32a5361d304c90f996bd2d565"

spec = importlib.util.spec_from_file_location("item20_readiness_selector", SCRIPT)
assert spec is not None and spec.loader is not None
selector = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = selector
spec.loader.exec_module(selector)


def artifact(kind: str, artifact_id: int, sha: str, created_at: str) -> dict[str, object]:
    prefix = {
        "acceptance": "vultr-acceptance-authority",
        "preflight": "vultr-readonly-preflight",
    }[kind]
    return {
        "id": artifact_id,
        "name": f"{prefix}-{sha}",
        "size_in_bytes": 512,
        "expired": False,
        "digest": "sha256:" + "c" * 64,
        "created_at": created_at,
        "workflow_run": {"id": artifact_id + 1000, "head_branch": "main", "head_sha": sha},
    }


class Item20AdmissionReadinessTests(unittest.TestCase):
    def test_contract_is_exact_single_sha_validation_only(self) -> None:
        contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
        selector.verify_readiness_contract(contract)
        workflow = contract["candidate_evidence_workflow"]
        self.assertEqual(workflow["candidate_sha"], "same_exact_current_protected_main_as_control_plane")
        self.assertTrue(workflow["candidate_control_plane_exact_equality_required"])
        self.assertEqual(workflow["control_plane_sha"], "exact_current_protected_main")
        self.assertEqual(workflow["admission_core_wiring"], "implemented_exact_result_match")
        self.assertEqual(workflow["session_workflow_wiring"], "implemented_exact_readiness_artifact_consumption")
        self.assertFalse(contract["authorization"]["provider_mutation_authorized"])
        self.assertFalse(contract["authorization"]["phone_mutation_authorized"])
        self.assertFalse(contract["authorization"]["live_execution_authorized"])

    def test_selector_uses_same_sha_candidate_and_run(self) -> None:
        payload = {
            "artifacts": [
                artifact("acceptance", 10, OTHER_SHA, "2026-08-31T10:00:00Z"),
                artifact("acceptance", 11, ACTIVE_SHA, "2026-08-31T10:01:00Z"),
                artifact("acceptance", 12, ACTIVE_SHA, "2026-08-31T10:02:00Z"),
            ]
        }
        selected = selector.select_artifact("acceptance", ACTIVE_SHA, ACTIVE_SHA, payload)
        self.assertEqual(selected["id"], 12)
        self.assertEqual(selected["workflow_run"]["head_sha"], ACTIVE_SHA)

    def test_selector_rejects_candidate_control_plane_mismatch(self) -> None:
        with self.assertRaisesRegex(ValueError, "candidate/control-plane SHA mismatch"):
            selector.select_artifact(
                "acceptance",
                ACTIVE_SHA,
                OTHER_SHA,
                {"artifacts": [artifact("acceptance", 10, ACTIVE_SHA, "2026-08-31T10:00:00Z")]},
            )

    def test_historical_item19_candidate_is_not_privileged(self) -> None:
        with self.assertRaisesRegex(ValueError, "candidate/control-plane SHA mismatch"):
            selector.select_artifact(
                "preflight",
                HISTORICAL_ITEM19_SHA,
                ACTIVE_SHA,
                {"artifacts": [artifact("preflight", 20, HISTORICAL_ITEM19_SHA, "2026-08-31T10:00:00Z")]},
            )

    def test_selector_rejects_expired_wrong_or_malformed_artifacts(self) -> None:
        wrong = artifact("preflight", 20, OTHER_SHA, "2026-08-31T10:03:00Z")
        expired = artifact("preflight", 21, ACTIVE_SHA, "2026-08-31T10:04:00Z")
        expired["expired"] = True
        malformed = artifact("preflight", 22, ACTIVE_SHA, "2026-08-31T10:05:00Z")
        malformed["digest"] = "bad"
        with self.assertRaises(ValueError):
            selector.select_artifact(
                "preflight", ACTIVE_SHA, ACTIVE_SHA, {"artifacts": [wrong, expired, malformed]}
            )

    def test_workflow_derives_candidate_from_exact_protected_main_and_is_read_only(self) -> None:
        workflow = WORKFLOW.read_text(encoding="utf-8")
        for required in (
            "name: Item 20 read-only admission readiness",
            "actions: read",
            "contents: read",
            "CANDIDATE_SHA: ${{ github.sha }}",
            "CONTROL_PLANE_SHA: ${{ github.sha }}",
            'test "$CANDIDATE_SHA" = "$CONTROL_PLANE_SHA"',
            "workflow SHA is not exact current protected main",
            "scripts/select_item20_candidate_evidence.py select-artifact",
            "scripts/verify_item20_candidate_evidence.py",
            "--control-plane-sha \"$CANDIDATE_SHA\"",
            "item20-admission-readiness-${{ github.sha }}",
            "Candidate/control-plane exact equality verified: true",
            "Provider mutation authorized: false",
            "Phone mutation authorized: false",
            "Live execution authorized: false",
        ):
            self.assertIn(required, workflow)

        for forbidden in (
            "d151dbdd156279e32a5361d304c90f996bd2d565",
            "Exact immutable Item 19-proven software candidate SHA",
            "environment: acceptance-vultr",
            "VULTR_API_KEY",
            "VULTR_SSH_PRIVATE_KEY",
            "ITEM20_PHONE_HANDOFF_TOKEN",
            "production-vultr",
            "/v2/instances",
            "gh workflow run",
            "actions/workflows/acceptance-authority.yml/dispatches",
            "actions/workflows/vultr-readonly-preflight.yml/dispatches",
            "adb ",
        ):
            self.assertNotIn(forbidden, workflow)

    def test_session_workflow_consumes_existing_readiness_without_dispatch(self) -> None:
        workflow = SESSION_WORKFLOW.read_text(encoding="utf-8")
        for required in (
            "scripts/select_item20_candidate_evidence.py verify-contract",
            "actions/artifacts?name=item20-admission-readiness-$CONTROL_PLANE_SHA&per_page=100",
            "scripts/verify_item20_readiness_artifact.py select-artifact",
            "scripts/verify_item20_readiness_artifact.py verify",
            "item20-admission-readiness-evidence.json",
            "Readiness artifact consumed: true",
            "Fresh acceptance authority verified: true",
            "Fresh Vultr read-only preflight verified: true",
        ):
            self.assertIn(required, workflow)

        for forbidden in (
            "environment: acceptance-vultr",
            "VULTR_API_KEY",
            "VULTR_SSH_PRIVATE_KEY",
            "ITEM20_PHONE_HANDOFF_TOKEN",
            "production-vultr",
            "/v2/instances",
            "gh workflow run",
            "/dispatches",
            "adb ",
        ):
            self.assertNotIn(forbidden, workflow)


if __name__ == "__main__":
    unittest.main()
