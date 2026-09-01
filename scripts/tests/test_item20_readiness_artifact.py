from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "verify_item20_readiness_artifact.py"
ACTIVE_SHA = "a" * 40
OTHER_SHA = "b" * 40
HISTORICAL_ITEM19_SHA = "d151dbdd156279e32a5361d304c90f996bd2d565"
QUALITY_RUN_ID = 12345

spec = importlib.util.spec_from_file_location("item20_readiness_artifact", SCRIPT)
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def artifact(artifact_id: int, sha: str, created_at: str) -> dict[str, object]:
    return {
        "id": artifact_id,
        "name": f"item20-admission-readiness-{sha}",
        "size_in_bytes": 1024,
        "expired": False,
        "digest": "sha256:" + "c" * 64,
        "created_at": created_at,
        "workflow_run": {"id": artifact_id + 1000, "head_branch": "main", "head_sha": sha},
    }


def run(run_id: int, sha: str = ACTIVE_SHA) -> dict[str, object]:
    return {
        "id": run_id,
        "name": "Item 20 read-only admission readiness",
        "path": ".github/workflows/item20-admission-readiness.yml",
        "event": "workflow_dispatch",
        "head_branch": "main",
        "head_sha": sha,
        "status": "completed",
        "conclusion": "success",
        "run_attempt": 1,
        "created_at": "2026-08-31T12:00:00Z",
        "repository": {"full_name": "iamaman11/mobile-proxy"},
    }


def evidence() -> dict[str, object]:
    return {
        "format_version": 1,
        "authority": "item20_fresh_single_sha_candidate_evidence_verification",
        "repository": "iamaman11/mobile-proxy",
        "candidate_sha": ACTIVE_SHA,
        "control_plane_sha": ACTIVE_SHA,
        "candidate_control_plane_exact_equality_verified": True,
        "control_plane_quality_run_id": str(QUALITY_RUN_ID),
        "candidate_quality_run_id": str(QUALITY_RUN_ID),
        "candidate_quality_run_attempt": "1",
        "acceptance_authority_run_id": "1001",
        "acceptance_authority_artifact_id": "2001",
        "acceptance_authority_artifact_digest": "sha256:" + "d" * 64,
        "vultr_readonly_preflight_run_id": "1002",
        "vultr_readonly_preflight_artifact_id": "2002",
        "vultr_readonly_preflight_artifact_digest": "sha256:" + "e" * 64,
        "fresh_acceptance_authority_verified": True,
        "fresh_vultr_readonly_preflight_verified": True,
        "fresh_exact_candidate_provider_proof_required_before_live_window": True,
        "source_freeze_required_after_evidence": True,
        "provider_probe_read_only_verified": True,
        "provider_mutation_authorized": False,
        "phone_mutation_authorized": False,
        "endpoint_handoff_authorized": False,
        "live_execution_authorized": False,
        "final_production_authority": False,
        "transport_endpoint_recorded": False,
        "provider_identifier_recorded": False,
        "secret_derived_identifier_recorded": False,
    }


class Item20ReadinessArtifactTests(unittest.TestCase):
    def test_selects_newest_exact_same_sha_artifact(self) -> None:
        payload = {
            "artifacts": [
                artifact(10, OTHER_SHA, "2026-08-31T10:00:00Z"),
                artifact(11, ACTIVE_SHA, "2026-08-31T10:01:00Z"),
                artifact(12, ACTIVE_SHA, "2026-08-31T10:02:00Z"),
            ]
        }
        selected = module.select_readiness_artifact(ACTIVE_SHA, ACTIVE_SHA, payload)
        self.assertEqual(selected["id"], 12)
        self.assertEqual(selected["workflow_run"]["head_sha"], ACTIVE_SHA)

    def test_distinct_candidate_and_control_plane_fail_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "candidate/control-plane SHA mismatch"):
            module.select_readiness_artifact(
                ACTIVE_SHA,
                OTHER_SHA,
                {"artifacts": [artifact(10, ACTIVE_SHA, "2026-08-31T10:00:00Z")]},
            )

    def test_historical_item19_candidate_cannot_bypass_same_sha_rule(self) -> None:
        with self.assertRaisesRegex(ValueError, "candidate/control-plane SHA mismatch"):
            module.select_readiness_artifact(
                HISTORICAL_ITEM19_SHA,
                ACTIVE_SHA,
                {"artifacts": [artifact(20, HISTORICAL_ITEM19_SHA, "2026-08-31T10:00:00Z")]},
            )

    def test_verifies_exact_run_and_bounded_evidence(self) -> None:
        selected = artifact(30, ACTIVE_SHA, "2026-08-31T11:00:00Z")
        readiness_run = run(1030)
        result = module.verify_consumption(
            ACTIVE_SHA, ACTIVE_SHA, QUALITY_RUN_ID, selected, readiness_run, evidence()
        )
        self.assertEqual(result["authority"], "item20_readiness_artifact_validation")
        self.assertTrue(result["candidate_control_plane_exact_equality_verified"])
        self.assertTrue(result["fresh_acceptance_authority_verified"])
        self.assertTrue(result["fresh_exact_candidate_provider_proof_required_before_live_window"])
        self.assertFalse(result["provider_mutation_authorized"])
        self.assertFalse(result["live_execution_authorized"])

    def test_rejects_wrong_readiness_run_provenance(self) -> None:
        selected = artifact(40, ACTIVE_SHA, "2026-08-31T11:00:00Z")
        bad_run = run(1040)
        bad_run["path"] = ".github/workflows/other.yml"
        with self.assertRaises(ValueError):
            module.verify_consumption(
                ACTIVE_SHA, ACTIVE_SHA, QUALITY_RUN_ID, selected, bad_run, evidence()
            )

    def test_rejects_unsafe_mismatched_or_extra_evidence(self) -> None:
        selected = artifact(50, ACTIVE_SHA, "2026-08-31T11:00:00Z")
        readiness_run = run(1050)

        unsafe = evidence()
        unsafe["provider_mutation_authorized"] = True
        with self.assertRaises(ValueError):
            module.verify_consumption(
                ACTIVE_SHA, ACTIVE_SHA, QUALITY_RUN_ID, selected, readiness_run, unsafe
            )

        wrong = evidence()
        wrong["control_plane_sha"] = OTHER_SHA
        with self.assertRaises(ValueError):
            module.verify_consumption(
                ACTIVE_SHA, ACTIVE_SHA, QUALITY_RUN_ID, selected, readiness_run, wrong
            )

        stale_quality = evidence()
        stale_quality["candidate_quality_run_id"] = "99999"
        with self.assertRaises(ValueError):
            module.verify_consumption(
                ACTIVE_SHA, ACTIVE_SHA, QUALITY_RUN_ID, selected, readiness_run, stale_quality
            )

        extra = evidence()
        extra["transport_endpoint"] = "forbidden"
        with self.assertRaises(ValueError):
            module.verify_consumption(
                ACTIVE_SHA, ACTIVE_SHA, QUALITY_RUN_ID, selected, readiness_run, extra
            )

    def test_module_has_no_external_or_live_execution_surface(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8").lower()
        for forbidden in (
            "subprocess.",
            "urllib.request",
            "requests.",
            "http.client",
            "socket.",
            "vultr_api_key",
            "vultr_ssh_private_key",
            "/v2/instances",
            "create_instance(",
            "delete_instance(",
            "adb ",
            "gh workflow run",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
