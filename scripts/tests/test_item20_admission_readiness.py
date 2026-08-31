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
CANDIDATE = "d151dbdd156279e32a5361d304c90f996bd2d565"
CONTROL = "a" * 40
OLD_CONTROL = "b" * 40

spec = importlib.util.spec_from_file_location("item20_readiness_selector", SCRIPT)
assert spec is not None and spec.loader is not None
selector = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = selector
spec.loader.exec_module(selector)


def artifact(kind: str, artifact_id: int, control: str, created_at: str) -> dict[str, object]:
    prefix = {
        "acceptance": "vultr-acceptance-authority",
        "preflight": "vultr-readonly-preflight",
    }[kind]
    return {
        "id": artifact_id,
        "name": f"{prefix}-{CANDIDATE}",
        "size_in_bytes": 512,
        "expired": False,
        "digest": "sha256:" + "c" * 64,
        "created_at": created_at,
        "workflow_run": {"id": artifact_id + 1000, "head_branch": "main", "head_sha": control},
    }


class Item20AdmissionReadinessTests(unittest.TestCase):
    def test_contract_is_exact_validation_only(self) -> None:
        contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
        selector.verify_readiness_contract(contract)
        self.assertEqual(
            contract["candidate_evidence_workflow"]["admission_core_wiring"], "not_implemented"
        )
        self.assertFalse(contract["authorization"]["provider_mutation_authorized"])
        self.assertFalse(contract["authorization"]["phone_mutation_authorized"])
        self.assertFalse(contract["authorization"]["live_execution_authorized"])

    def test_selector_uses_exact_candidate_then_control_plane(self) -> None:
        payload = {
            "artifacts": [
                artifact("acceptance", 10, OLD_CONTROL, "2026-08-31T10:00:00Z"),
                artifact("acceptance", 11, CONTROL, "2026-08-31T10:01:00Z"),
                artifact("acceptance", 12, CONTROL, "2026-08-31T10:02:00Z"),
            ]
        }
        selected = selector.select_artifact("acceptance", CANDIDATE, CONTROL, payload)
        self.assertEqual(selected["id"], 12)
        self.assertEqual(selected["workflow_run"]["head_sha"], CONTROL)

    def test_selector_rejects_old_or_invalid_artifacts(self) -> None:
        wrong_name = artifact("preflight", 20, CONTROL, "2026-08-31T10:03:00Z")
        wrong_name["name"] = "vultr-readonly-preflight-" + "0" * 40
        expired = artifact("preflight", 21, CONTROL, "2026-08-31T10:04:00Z")
        expired["expired"] = True
        old = artifact("preflight", 22, OLD_CONTROL, "2026-08-31T10:05:00Z")
        with self.assertRaises(ValueError):
            selector.select_artifact(
                "preflight", CANDIDATE, CONTROL, {"artifacts": [wrong_name, expired, old]}
            )

    def test_workflow_is_read_only_and_consumes_protected_verifier(self) -> None:
        workflow = WORKFLOW.read_text(encoding="utf-8")
        for required in (
            "name: Item 20 read-only admission readiness",
            "actions: read",
            "contents: read",
            "scripts/select_item20_candidate_evidence.py select-artifact",
            "scripts/verify_item20_candidate_evidence.py",
            "vultr-acceptance-authority-$CANDIDATE_SHA",
            "vultr-readonly-preflight-$CANDIDATE_SHA",
            "item20-admission-readiness-${{ github.sha }}",
            "Provider mutation authorized: false",
            "Phone mutation authorized: false",
            "Live execution authorized: false",
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
            "actions/workflows/acceptance-authority.yml/dispatches",
            "actions/workflows/vultr-readonly-preflight.yml/dispatches",
            "adb ",
        ):
            self.assertNotIn(forbidden, workflow)


if __name__ == "__main__":
    unittest.main()
