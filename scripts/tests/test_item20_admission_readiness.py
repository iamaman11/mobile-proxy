from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "select_item20_candidate_evidence.py"
CONTRACT = ROOT / "contracts" / "operations" / "item20-admission-readiness-v1.json"
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
    def test_contract_snapshot_remains_validation_only(self) -> None:
        contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
        selector.verify_readiness_contract(contract)
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

    def test_selector_rejects_expired_or_malformed_artifacts(self) -> None:
        expired = artifact("preflight", 21, ACTIVE_SHA, "2026-08-31T10:04:00Z")
        expired["expired"] = True
        malformed = artifact("preflight", 22, ACTIVE_SHA, "2026-08-31T10:05:00Z")
        malformed["digest"] = "bad"
        with self.assertRaises(ValueError):
            selector.select_artifact(
                "preflight", ACTIVE_SHA, ACTIVE_SHA, {"artifacts": [expired, malformed]}
            )

    def test_retired_workflow_is_absent(self) -> None:
        self.assertFalse((ROOT / ".github/workflows/item20-admission-readiness.yml").exists())
        retirement = json.loads(
            (ROOT / "contracts/operations/historical-public-acceptance-retirement-v1.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertIn(
            ".github/workflows/item20-admission-readiness.yml",
            retirement["retired_workflows"],
        )


if __name__ == "__main__":
    unittest.main()
