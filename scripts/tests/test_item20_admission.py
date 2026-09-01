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


ACTIVE_SHA = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
HISTORICAL_ITEM19_SHA = "d151dbdd156279e32a5361d304c90f996bd2d565"
CONTRACT = ROOT / "contracts/operations/item20-acceptance-v1.json"


def branch() -> dict[str, object]:
    return {"name": "main", "protected": True, "commit": {"sha": ACTIVE_SHA}}


def quality() -> dict[str, object]:
    return {
        "id": 123456,
        "run_attempt": 1,
        "name": "Quality",
        "path": ".github/workflows/quality.yml",
        "event": "push",
        "head_branch": "main",
        "head_sha": ACTIVE_SHA,
        "status": "completed",
        "conclusion": "success",
        "created_at": "2026-08-31T10:00:00Z",
        "repository": {"full_name": "iamaman11/mobile-proxy"},
    }


def issue(number: int, state: str, state_reason: str | None = None) -> dict[str, object]:
    return {"number": number, "state": state, "state_reason": state_reason}


def phone_preflight() -> dict[str, object]:
    return {
        "format_version": 1,
        "repository": "iamaman11/mobile-proxy",
        "canonical_sha": ACTIVE_SHA,
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


def workflow_run(name: str, path: str, run_id: int, created_at: str) -> dict[str, object]:
    return {
        "id": run_id,
        "run_attempt": 1,
        "name": name,
        "path": path,
        "event": "issue_comment",
        "head_branch": "main",
        "head_sha": ACTIVE_SHA,
        "status": "completed",
        "conclusion": "success",
        "created_at": created_at,
        "repository": {"full_name": "iamaman11/mobile-proxy"},
    }


def acceptance_run() -> dict[str, object]:
    return workflow_run(
        "Vultr acceptance authority",
        ".github/workflows/acceptance-authority.yml",
        1000,
        "2026-08-31T10:05:00Z",
    )


def preflight_run() -> dict[str, object]:
    return workflow_run(
        "Vultr read-only acceptance preflight",
        ".github/workflows/vultr-readonly-preflight.yml",
        1100,
        "2026-08-31T10:10:00Z",
    )


def artifact(name: str, run_id: int, created_at: str, artifact_id: int) -> dict[str, object]:
    return {
        "id": artifact_id,
        "name": name,
        "size_in_bytes": 512,
        "expired": False,
        "digest": "sha256:" + "b" * 64,
        "created_at": created_at,
        "workflow_run": {"id": run_id, "head_branch": "main", "head_sha": ACTIVE_SHA},
    }


def acceptance_artifact() -> dict[str, object]:
    return artifact(f"vultr-acceptance-authority-{ACTIVE_SHA}", 1000, "2026-08-31T10:06:00Z", 2000)


def preflight_artifact() -> dict[str, object]:
    return artifact(f"vultr-readonly-preflight-{ACTIVE_SHA}", 1100, "2026-08-31T10:11:00Z", 2100)


def acceptance_evidence() -> dict[str, object]:
    return {
        "format_version": 1,
        "authority": "pre_release_acceptance",
        "candidate_sha": ACTIVE_SHA,
        "repository": "iamaman11/mobile-proxy",
        "executor": "github-hosted",
        "acceptance_workflow": "Vultr acceptance authority",
        "acceptance_workflow_run_id": "1000",
        "acceptance_workflow_run_attempt": "1",
        "command_issue": 90,
        "command_comment_id": "3000",
        "candidate_quality_run_id": "123456",
        "candidate_quality_run_attempt": "1",
        "candidate_evidence_artifact": f"software-release-candidate-{ACTIVE_SHA}",
        "candidate_evidence_file": "release-candidate-evidence.json",
        "final_production_authority": False,
        "production_environment_authorized": False,
        "final_release_tag_created": False,
        "vultr_api_access_performed": False,
        "vm_mutation_performed": False,
        "phone_mutation_performed": False,
    }


def preflight_evidence() -> dict[str, object]:
    return {
        "format_version": 1,
        "authority": "pre_release_acceptance_read_only",
        "candidate_sha": ACTIVE_SHA,
        "repository": "iamaman11/mobile-proxy",
        "executor": "github-hosted",
        "environment": "acceptance-vultr",
        "workflow": "Vultr read-only acceptance preflight",
        "workflow_run_id": "1100",
        "workflow_run_attempt": "1",
        "command_issue": 90,
        "command_comment_id": "3100",
        "acceptance_authority_run_id": "1000",
        "acceptance_authority_run_attempt": "1",
        "api_key_available": True,
        "ssh_private_key_available": True,
        "ssh_private_key_valid": True,
        "provider_api_method": "GET",
        "provider_api_path": "/v2/account",
        "provider_api_calls": 1,
        "account_endpoint_accessible": True,
        "account_response_body_recorded": False,
        "account_metadata_recorded": False,
        "secret_values_recorded": False,
        "secret_derived_identifiers_recorded": False,
        "vm_lifecycle_access_performed": False,
        "vm_mutation_performed": False,
        "phone_mutation_performed": False,
        "final_production_authority": False,
        "production_environment_authorized": False,
        "final_release_tag_created": False,
    }


def readiness_evidence() -> dict[str, object]:
    return {
        "format_version": 1,
        "authority": "item20_fresh_single_sha_candidate_evidence_verification",
        "repository": "iamaman11/mobile-proxy",
        "candidate_sha": ACTIVE_SHA,
        "control_plane_sha": ACTIVE_SHA,
        "candidate_control_plane_exact_equality_verified": True,
        "control_plane_quality_run_id": "123456",
        "candidate_quality_run_id": "123456",
        "candidate_quality_run_attempt": "1",
        "acceptance_authority_run_id": "1000",
        "acceptance_authority_artifact_id": "2000",
        "acceptance_authority_artifact_digest": "sha256:" + "b" * 64,
        "vultr_readonly_preflight_run_id": "1100",
        "vultr_readonly_preflight_artifact_id": "2100",
        "vultr_readonly_preflight_artifact_digest": "sha256:" + "b" * 64,
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


class Item20AdmissionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
        self.item19 = issue(124, "closed", "completed")
        self.item20 = issue(135, "open")
        self.signing = issue(115, "closed", "completed")

    def admit(self, **overrides: object) -> dict[str, object]:
        values: dict[str, object] = {
            "candidate_sha": ACTIVE_SHA,
            "control_plane_sha": ACTIVE_SHA,
            "contract": self.contract,
            "branch": branch(),
            "quality_run": quality(),
            "item19_issue": self.item19,
            "item20_issue": self.item20,
            "signing_issue": self.signing,
            "phone_preflight": phone_preflight(),
            "acceptance_artifact": acceptance_artifact(),
            "acceptance_run": acceptance_run(),
            "acceptance_evidence": acceptance_evidence(),
            "preflight_artifact": preflight_artifact(),
            "preflight_run": preflight_run(),
            "preflight_evidence": preflight_evidence(),
            "readiness_evidence": readiness_evidence(),
        }
        values.update(overrides)
        return verify_admission(**values)  # type: ignore[arg-type]

    def test_same_sha_admission_consumes_fresh_candidate_evidence(self) -> None:
        verify_contract(self.contract)
        evidence = self.admit()
        self.assertEqual(evidence["candidate_sha"], ACTIVE_SHA)
        self.assertEqual(evidence["control_plane_sha"], ACTIVE_SHA)
        self.assertTrue(evidence["candidate_control_plane_exact_equality_verified"])
        self.assertTrue(evidence["admission_readiness_result_verified"])
        self.assertTrue(evidence["fresh_exact_candidate_provider_proof_required_before_live_window"])
        self.assertFalse(evidence["live_execution_authorized"])

    def test_distinct_candidate_and_control_plane_fail_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "candidate/control-plane SHA mismatch"):
            self.admit(candidate_sha="b" * 40)

    def test_historical_item19_sha_cannot_be_active_candidate(self) -> None:
        with self.assertRaisesRegex(ValueError, "candidate/control-plane SHA mismatch"):
            self.admit(candidate_sha=HISTORICAL_ITEM19_SHA)

    def test_protected_main_advance_invalidates_admission(self) -> None:
        bad = branch()
        bad["commit"] = {"sha": "b" * 40}
        with self.assertRaisesRegex(ValueError, "exact current protected main"):
            self.admit(branch=bad)

    def test_quality_must_match_exact_same_sha(self) -> None:
        bad = quality()
        bad["head_sha"] = "b" * 40
        with self.assertRaisesRegex(ValueError, "Quality run"):
            self.admit(quality_run=bad)

    def test_open_signing_gate_fails_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "signing-continuity"):
            self.admit(signing_issue=issue(115, "open"))

    def test_item_trackers_fail_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "Item 19"):
            self.admit(item19_issue=issue(124, "closed", None))
        with self.assertRaisesRegex(ValueError, "Item 20"):
            self.admit(item20_issue=issue(135, "closed", "completed"))

    def test_private_preflight_must_match_same_sha_and_registered_device(self) -> None:
        bad = phone_preflight()
        bad["canonical_sha"] = "b" * 40
        with self.assertRaisesRegex(ValueError, "single-SHA control plane"):
            self.admit(phone_preflight=bad)

        bad = phone_preflight()
        bad["device"] = copy.deepcopy(bad["device"])
        assert isinstance(bad["device"], dict)
        bad["device"]["device_count"] = 2
        with self.assertRaisesRegex(ValueError, "one exact registered"):
            self.admit(phone_preflight=bad)

    def test_contract_cannot_grant_live_authority_or_restore_two_sha_semantics(self) -> None:
        mutated = copy.deepcopy(self.contract)
        mutated["authorization"]["provider_mutation_authorized"] = True
        with self.assertRaisesRegex(ValueError, "validation-only"):
            verify_contract(mutated)

        mutated = copy.deepcopy(self.contract)
        mutated["identity"]["exact_equality_required"] = False
        with self.assertRaisesRegex(ValueError, "single-SHA identity"):
            verify_contract(mutated)

    def test_fresh_candidate_authority_cannot_reuse_historical_item19_evidence(self) -> None:
        mutated = copy.deepcopy(self.contract)
        mutated["future_live_candidate_evidence"]["acceptance_authority"] = "reuse_historical_item19_authority"
        with self.assertRaisesRegex(ValueError, "fresh candidate authority requirements"):
            verify_contract(mutated)

    def test_readiness_result_must_exactly_match_independently_verified_chain(self) -> None:
        for field, value in (
            ("control_plane_quality_run_id", "999999"),
            ("candidate_control_plane_exact_equality_verified", False),
            ("provider_mutation_authorized", True),
        ):
            mutated = readiness_evidence()
            mutated[field] = value
            with self.assertRaisesRegex(ValueError, "readiness|candidate evidence|did not verify|violates"):
                self.admit(readiness_evidence=mutated)

        extra = readiness_evidence()
        extra["unexpected_field"] = "forbidden"
        with self.assertRaisesRegex(ValueError, "exactly match"):
            self.admit(readiness_evidence=extra)

    def test_contract_records_implemented_exact_readiness_consumption(self) -> None:
        verifier = self.contract["future_live_candidate_verifier"]
        assert isinstance(verifier, dict)
        self.assertEqual(verifier["workflow_wiring"], "implemented_exact_readiness_artifact_consumption")
        self.assertTrue(verifier["candidate_control_plane_exact_equality_required"])
        self.assertFalse(self.contract["authorization"]["live_execution_authorized"])


if __name__ == "__main__":
    unittest.main()
