from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "verify_item20_readiness_artifact.py"
CANDIDATE = "d151dbdd156279e32a5361d304c90f996bd2d565"
CONTROL = "a" * 40
OLD_CONTROL = "b" * 40
QUALITY_RUN_ID = 12345

spec = importlib.util.spec_from_file_location("item20_readiness_artifact", SCRIPT)
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def artifact(artifact_id: int, control: str, created_at: str) -> dict[str, object]:
    return {
        "id": artifact_id,
        "name": f"item20-admission-readiness-{control}",
        "size_in_bytes": 1024,
        "expired": False,
        "digest": "sha256:" + "c" * 64,
        "created_at": created_at,
        "workflow_run": {"id": artifact_id + 1000, "head_branch": "main", "head_sha": control},
    }


def run(run_id: int, control: str = CONTROL) -> dict[str, object]:
    return {
        "id": run_id,
        "name": "Item 20 read-only admission readiness",
        "path": ".github/workflows/item20-admission-readiness.yml",
        "event": "workflow_dispatch",
        "head_branch": "main",
        "head_sha": control,
        "status": "completed",
        "conclusion": "success",
        "run_attempt": 1,
        "created_at": "2026-08-31T12:00:00Z",
        "repository": {"full_name": "iamaman11/mobile-proxy"},
    }


def evidence() -> dict[str, object]:
    return {
        "format_version": 1,
        "authority": "item20_fresh_candidate_evidence_verification",
        "repository": "iamaman11/mobile-proxy",
        "candidate_sha": CANDIDATE,
        "control_plane_sha": CONTROL,
        "control_plane_quality_run_id": str(QUALITY_RUN_ID),
        "candidate_quality_run_id": "33341602485",
        "candidate_quality_run_attempt": "1",
        "acceptance_authority_run_id": "1001",
        "acceptance_authority_artifact_id": "2001",
        "acceptance_authority_artifact_digest": "sha256:" + "d" * 64,
        "vultr_readonly_preflight_run_id": "1002",
        "vultr_readonly_preflight_artifact_id": "2002",
        "vultr_readonly_preflight_artifact_digest": "sha256:" + "e" * 64,
        "candidate_control_plane_separation_verified": True,
        "fresh_acceptance_authority_verified": True,
        "fresh_vultr_readonly_preflight_verified": True,
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
    def test_selects_newest_exact_control_plane_artifact(self) -> None:
        payload = {
            "artifacts": [
                artifact(10, OLD_CONTROL, "2026-08-31T10:00:00Z"),
                artifact(11, CONTROL, "2026-08-31T10:01:00Z"),
                artifact(12, CONTROL, "2026-08-31T10:02:00Z"),
            ]
        }
        selected = module.select_readiness_artifact(CANDIDATE, CONTROL, payload)
        self.assertEqual(selected["id"], 12)
        self.assertEqual(selected["workflow_run"]["head_sha"], CONTROL)

    def test_selector_rejects_expired_wrong_or_malformed_artifacts(self) -> None:
        expired = artifact(20, CONTROL, "2026-08-31T10:03:00Z")
        expired["expired"] = True
        wrong = artifact(21, OLD_CONTROL, "2026-08-31T10:04:00Z")
        malformed = artifact(22, CONTROL, "2026-08-31T10:05:00Z")
        malformed["digest"] = "bad"
        with self.assertRaises(ValueError):
            module.select_readiness_artifact(
                CANDIDATE, CONTROL, {"artifacts": [expired, wrong, malformed]}
            )

    def test_verifies_exact_run_and_bounded_evidence(self) -> None:
        selected = artifact(30, CONTROL, "2026-08-31T11:00:00Z")
        readiness_run = run(1030)
        result = module.verify_consumption(
            CANDIDATE, CONTROL, QUALITY_RUN_ID, selected, readiness_run, evidence()
        )
        self.assertEqual(result["authority"], "item20_readiness_artifact_validation")
        self.assertTrue(result["fresh_acceptance_authority_verified"])
        self.assertTrue(result["fresh_vultr_readonly_preflight_verified"])
        self.assertFalse(result["provider_mutation_authorized"])
        self.assertFalse(result["phone_mutation_authorized"])
        self.assertFalse(result["live_execution_authorized"])

    def test_rejects_wrong_readiness_run_provenance(self) -> None:
        selected = artifact(40, CONTROL, "2026-08-31T11:00:00Z")
        bad_run = run(1040)
        bad_run["path"] = ".github/workflows/other.yml"
        with self.assertRaises(ValueError):
            module.verify_consumption(
                CANDIDATE, CONTROL, QUALITY_RUN_ID, selected, bad_run, evidence()
            )

    def test_rejects_unsafe_or_mismatched_evidence(self) -> None:
        selected = artifact(50, CONTROL, "2026-08-31T11:00:00Z")
        readiness_run = run(1050)
        unsafe = evidence()
        unsafe["provider_mutation_authorized"] = True
        with self.assertRaises(ValueError):
            module.verify_consumption(
                CANDIDATE, CONTROL, QUALITY_RUN_ID, selected, readiness_run, unsafe
            )

        wrong_control = evidence()
        wrong_control["control_plane_sha"] = OLD_CONTROL
        with self.assertRaises(ValueError):
            module.verify_consumption(
                CANDIDATE, CONTROL, QUALITY_RUN_ID, selected, readiness_run, wrong_control
            )

    def test_rejects_unexpected_evidence_fields(self) -> None:
        selected = artifact(60, CONTROL, "2026-08-31T11:00:00Z")
        readiness_run = run(1060)
        expanded = evidence()
        expanded["transport_endpoint"] = "forbidden"
        with self.assertRaises(ValueError):
            module.verify_consumption(
                CANDIDATE, CONTROL, QUALITY_RUN_ID, selected, readiness_run, expanded
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
