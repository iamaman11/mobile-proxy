from __future__ import annotations

import copy
import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from verify_item20_candidate_evidence import verify_candidate_chain, verify_contract


CANDIDATE = "d151dbdd156279e32a5361d304c90f996bd2d565"
CONTROL_PLANE = "a" * 40
CONTRACT = ROOT / "contracts/operations/item20-acceptance-v1.json"


def branch(control_plane_sha: str = CONTROL_PLANE) -> dict[str, object]:
    return {"name": "main", "protected": True, "commit": {"sha": control_plane_sha}}


def workflow_run(
    *, name: str, path: str, run_id: int, created_at: str, control_plane_sha: str = CONTROL_PLANE
) -> dict[str, object]:
    return {
        "id": run_id,
        "run_attempt": 1,
        "name": name,
        "path": path,
        "event": "issue_comment",
        "head_branch": "main",
        "head_sha": control_plane_sha,
        "status": "completed",
        "conclusion": "success",
        "created_at": created_at,
        "repository": {"full_name": "iamaman11/mobile-proxy"},
    }


def control_quality(control_plane_sha: str = CONTROL_PLANE) -> dict[str, object]:
    return {
        "id": 900,
        "run_attempt": 1,
        "name": "Quality",
        "path": ".github/workflows/quality.yml",
        "event": "push",
        "head_branch": "main",
        "head_sha": control_plane_sha,
        "status": "completed",
        "conclusion": "success",
        "created_at": "2026-08-31T10:00:00Z",
        "repository": {"full_name": "iamaman11/mobile-proxy"},
    }


def acceptance_run(control_plane_sha: str = CONTROL_PLANE) -> dict[str, object]:
    return workflow_run(
        name="Vultr acceptance authority",
        path=".github/workflows/acceptance-authority.yml",
        run_id=1000,
        created_at="2026-08-31T10:05:00Z",
        control_plane_sha=control_plane_sha,
    )


def preflight_run(control_plane_sha: str = CONTROL_PLANE) -> dict[str, object]:
    return workflow_run(
        name="Vultr read-only acceptance preflight",
        path=".github/workflows/vultr-readonly-preflight.yml",
        run_id=1100,
        created_at="2026-08-31T10:10:00Z",
        control_plane_sha=control_plane_sha,
    )


def artifact(
    name: str,
    run_id: int,
    created_at: str,
    artifact_id: int,
    control_plane_sha: str = CONTROL_PLANE,
) -> dict[str, object]:
    return {
        "id": artifact_id,
        "name": name,
        "size_in_bytes": 512,
        "expired": False,
        "digest": "sha256:" + "b" * 64,
        "created_at": created_at,
        "workflow_run": {
            "id": run_id,
            "repository_id": 1231016170,
            "head_repository_id": 1231016170,
            "head_branch": "main",
            "head_sha": control_plane_sha,
        },
    }


def acceptance_artifact(control_plane_sha: str = CONTROL_PLANE) -> dict[str, object]:
    return artifact(
        f"vultr-acceptance-authority-{CANDIDATE}",
        1000,
        "2026-08-31T10:06:00Z",
        2000,
        control_plane_sha,
    )


def preflight_artifact(control_plane_sha: str = CONTROL_PLANE) -> dict[str, object]:
    return artifact(
        f"vultr-readonly-preflight-{CANDIDATE}",
        1100,
        "2026-08-31T10:11:00Z",
        2100,
        control_plane_sha,
    )


def acceptance_evidence() -> dict[str, object]:
    return {
        "format_version": 1,
        "authority": "pre_release_acceptance",
        "candidate_sha": CANDIDATE,
        "repository": "iamaman11/mobile-proxy",
        "executor": "github-hosted",
        "acceptance_workflow": "Vultr acceptance authority",
        "acceptance_workflow_run_id": "1000",
        "acceptance_workflow_run_attempt": "1",
        "command_issue": 90,
        "command_comment_id": "3000",
        "candidate_quality_run_id": "33341602485",
        "candidate_quality_run_attempt": "1",
        "candidate_evidence_artifact": f"software-release-candidate-{CANDIDATE}",
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
        "candidate_sha": CANDIDATE,
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


class Item20CandidateEvidenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.contract = json.loads(CONTRACT.read_text(encoding="utf-8"))

    def verify(self, **overrides: object) -> dict[str, object]:
        values: dict[str, object] = {
            "candidate_sha": CANDIDATE,
            "control_plane_sha": CONTROL_PLANE,
            "contract": self.contract,
            "branch": branch(),
            "control_plane_quality_run": control_quality(),
            "acceptance_artifact": acceptance_artifact(),
            "acceptance_run": acceptance_run(),
            "acceptance_evidence": acceptance_evidence(),
            "preflight_artifact": preflight_artifact(),
            "preflight_run": preflight_run(),
            "preflight_evidence": preflight_evidence(),
        }
        values.update(overrides)
        return verify_candidate_chain(**values)  # type: ignore[arg-type]

    def test_distinct_candidate_and_control_plane_chain_passes(self) -> None:
        self.assertEqual(verify_contract(self.contract), (33341602485, 1))
        evidence = self.verify()
        self.assertEqual(evidence["candidate_sha"], CANDIDATE)
        self.assertEqual(evidence["control_plane_sha"], CONTROL_PLANE)
        self.assertTrue(evidence["candidate_control_plane_separation_verified"])
        self.assertTrue(evidence["fresh_acceptance_authority_verified"])
        self.assertTrue(evidence["fresh_vultr_readonly_preflight_verified"])
        self.assertTrue(evidence["provider_probe_read_only_verified"])
        for field in (
            "provider_mutation_authorized",
            "phone_mutation_authorized",
            "endpoint_handoff_authorized",
            "live_execution_authorized",
            "final_production_authority",
            "transport_endpoint_recorded",
            "provider_identifier_recorded",
            "secret_derived_identifier_recorded",
        ):
            self.assertFalse(evidence[field])
        serialized = json.dumps(evidence)
        self.assertNotIn("VULTR_API_KEY", serialized)
        self.assertNotIn("VULTR_SSH_PRIVATE_KEY", serialized)
        self.assertNotIn("provider_uuid", serialized)

    def test_identity_roles_can_share_the_same_sha_value(self) -> None:
        evidence = self.verify(
            control_plane_sha=CANDIDATE,
            branch=branch(CANDIDATE),
            control_plane_quality_run=control_quality(CANDIDATE),
            acceptance_artifact=acceptance_artifact(CANDIDATE),
            acceptance_run=acceptance_run(CANDIDATE),
            preflight_artifact=preflight_artifact(CANDIDATE),
            preflight_run=preflight_run(CANDIDATE),
        )
        self.assertEqual(evidence["candidate_sha"], CANDIDATE)
        self.assertEqual(evidence["control_plane_sha"], CANDIDATE)
        self.assertTrue(evidence["candidate_control_plane_separation_verified"])

    def test_acceptance_run_must_use_exact_control_plane_not_candidate(self) -> None:
        run = acceptance_run()
        run["head_sha"] = CANDIDATE
        with self.assertRaisesRegex(ValueError, "exact Item 20 control plane"):
            self.verify(acceptance_run=run)

    def test_candidate_specific_acceptance_artifact_is_required(self) -> None:
        metadata = acceptance_artifact()
        metadata["name"] = "vultr-acceptance-authority-" + "c" * 40
        with self.assertRaisesRegex(ValueError, "exact candidate"):
            self.verify(acceptance_artifact=metadata)

    def test_artifact_must_be_non_expired_and_digest_bound(self) -> None:
        expired = acceptance_artifact()
        expired["expired"] = True
        with self.assertRaisesRegex(ValueError, "expired"):
            self.verify(acceptance_artifact=expired)

        bad_digest = acceptance_artifact()
        bad_digest["digest"] = "sha256:bad"
        with self.assertRaisesRegex(ValueError, "digest"):
            self.verify(acceptance_artifact=bad_digest)

    def test_artifact_run_binding_must_match_control_plane_and_run_id(self) -> None:
        metadata = acceptance_artifact()
        assert isinstance(metadata["workflow_run"], dict)
        metadata["workflow_run"]["id"] = 9999
        with self.assertRaisesRegex(ValueError, "exact control-plane run"):
            self.verify(acceptance_artifact=metadata)

        metadata = acceptance_artifact()
        assert isinstance(metadata["workflow_run"], dict)
        metadata["workflow_run"]["head_sha"] = CANDIDATE
        with self.assertRaisesRegex(ValueError, "exact control-plane run"):
            self.verify(acceptance_artifact=metadata)

    def test_acceptance_evidence_must_bind_protected_candidate_quality_run_and_attempt(self) -> None:
        evidence = acceptance_evidence()
        evidence["candidate_quality_run_id"] = "999"
        with self.assertRaisesRegex(ValueError, "acceptance-authority evidence"):
            self.verify(acceptance_evidence=evidence)

        evidence = acceptance_evidence()
        evidence["candidate_quality_run_attempt"] = "2"
        with self.assertRaisesRegex(ValueError, "acceptance-authority evidence"):
            self.verify(acceptance_evidence=evidence)

    def test_preflight_must_chain_to_same_acceptance_run(self) -> None:
        evidence = preflight_evidence()
        evidence["acceptance_authority_run_id"] = "999"
        with self.assertRaisesRegex(ValueError, "preflight evidence"):
            self.verify(preflight_evidence=evidence)

    def test_preflight_is_read_only_and_cannot_hide_provider_mutation(self) -> None:
        evidence = preflight_evidence()
        evidence["vm_mutation_performed"] = True
        with self.assertRaisesRegex(ValueError, "preflight evidence"):
            self.verify(preflight_evidence=evidence)

    def test_fresh_chain_must_follow_control_plane_quality(self) -> None:
        run = acceptance_run()
        run["created_at"] = "2026-08-31T09:59:00Z"
        with self.assertRaisesRegex(ValueError, "stale or out of order"):
            self.verify(acceptance_run=run)

        metadata = preflight_artifact()
        metadata["created_at"] = "2026-08-31T10:04:00Z"
        with self.assertRaisesRegex(ValueError, "stale or out of order"):
            self.verify(preflight_artifact=metadata)

    def test_pure_verifier_is_consumed_by_admission_but_workflow_wiring_remains_disabled(self) -> None:
        future = self.contract["future_live_candidate_evidence"]
        assert isinstance(future, dict)
        self.assertEqual(
            future["current_core_verification"],
            "protected_pure_verifier_consumed_by_admission_core",
        )

        verifier = self.contract["future_live_candidate_verifier"]
        assert isinstance(verifier, dict)
        self.assertEqual(
            verifier["status"], "protected_pure_verifier_consumed_by_admission_core"
        )
        self.assertFalse(verifier["candidate_control_plane_value_inequality_required"])
        self.assertEqual(verifier["verifier"], "scripts/verify_item20_candidate_evidence.py")
        self.assertEqual(verifier["workflow_wiring"], "not_implemented")
        self.assertFalse(verifier["performs_external_io"])
        self.assertFalse(verifier["grants_live_authority"])

        mutated = copy.deepcopy(self.contract)
        mutated["future_live_candidate_verifier"]["workflow_wiring"] = "enabled"
        with self.assertRaisesRegex(ValueError, "pure candidate evidence verifier"):
            verify_contract(mutated)


if __name__ == "__main__":
    unittest.main()
