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
OTHER_SHA = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
CONTRACT = ROOT / "contracts/operations/item20-acceptance-v1.json"


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

    def verify(self, **overrides: object) -> dict[str, object]:
        values: dict[str, object] = {
            "candidate_sha": ACTIVE_SHA,
            "control_plane_sha": ACTIVE_SHA,
            "contract": self.contract,
            "branch": branch(),
            "quality_run": quality(),
            "item19_issue": issue(124, "closed", "completed"),
            "item20_issue": issue(135, "open"),
            "signing_issue": issue(115, "open"),
        }
        values.update(overrides)
        return verify_orchestration(**values)  # type: ignore[arg-type]

    def test_pure_orchestration_verifier_remains_non_live(self) -> None:
        evidence = self.verify()
        self.assertTrue(evidence["candidate_control_plane_exact_equality_verified"])
        self.assertTrue(evidence["non_live_candidate_artifact_build_authorized"])
        self.assertFalse(evidence["provider_mutation_authorized"])
        self.assertFalse(evidence["phone_mutation_authorized"])
        self.assertFalse(evidence["live_execution_authorized"])

    def test_distinct_candidate_and_control_plane_fail_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "candidate/control-plane SHA mismatch"):
            self.verify(candidate_sha=OTHER_SHA)

    def test_quality_selection_is_exact_and_unambiguous(self) -> None:
        selected = select_quality_run(ACTIVE_SHA, {"workflow_runs": [quality()]})
        self.assertEqual(selected["id"], 456789)
        duplicate = quality().copy()
        duplicate["id"] = 456790
        with self.assertRaises(ValueError):
            select_quality_run(ACTIVE_SHA, {"workflow_runs": [quality(), duplicate]})

    def test_issue_gates_remain_fail_closed_in_pure_verifier(self) -> None:
        with self.assertRaises(ValueError):
            self.verify(item19_issue=issue(124, "open"))
        with self.assertRaises(ValueError):
            self.verify(item20_issue=issue(135, "closed", "completed"))

    def test_retired_workflow_is_absent(self) -> None:
        self.assertFalse((ROOT / ".github/workflows/item20-session-orchestration.yml").exists())
        retirement = json.loads(
            (ROOT / "contracts/operations/historical-public-acceptance-retirement-v1.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertIn(
            ".github/workflows/item20-session-orchestration.yml",
            retirement["retired_workflows"],
        )


if __name__ == "__main__":
    unittest.main()
