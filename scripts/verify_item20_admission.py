#!/usr/bin/env python3
"""Validate the non-live Production Baseline Item 20 single-SHA admission boundary."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
from typing import Mapping

from verify_item20_candidate_evidence import verify_candidate_chain

_CANONICAL_REPOSITORY = "iamaman11/mobile-proxy"
_QUALITY_WORKFLOW = "Quality"
_QUALITY_WORKFLOW_PATH = ".github/workflows/quality.yml"
_CANDIDATE_EVIDENCE_VERIFIER = "scripts/verify_item20_candidate_evidence.py"
_READINESS_AUTHORITY = "item20_fresh_single_sha_candidate_evidence_verification"
_REQUIRED_RUNNER_LABELS = ["self-hosted", "Linux", "X64", "android-production"]
_REQUIRED_TOOLS = {"adb": True, "python": True, "git": True, "curl": True}
_SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")


def validate_sha(value: object, kind: str) -> str:
    if not isinstance(value, str) or _SHA_PATTERN.fullmatch(value) is None:
        raise ValueError(f"{kind} SHA must be an exact lowercase 40-character hexadecimal identity")
    return value


def verify_contract(contract: Mapping[str, object]) -> None:
    expected_top = {
        "contract_version": 1,
        "status": "protected_non_live_admission_core",
        "canonical_repository": _CANONICAL_REPOSITORY,
        "tracker_issue": 135,
        "completed_provider_proof_issue": 124,
        "phone_signing_gate_issue": 115,
    }
    mismatched = [key for key, value in expected_top.items() if contract.get(key) != value]
    if mismatched:
        raise ValueError("Item 20 admission contract identity mismatch: " + ", ".join(sorted(mismatched)))

    identity = contract.get("identity")
    if not isinstance(identity, dict) or identity != {
        "candidate_sha": "exact_current_protected_main_revision_selected_for_10_of_10_window",
        "control_plane_sha": "same_exact_current_protected_main_revision",
        "exact_equality_required": True,
        "final_release_tag_target": "candidate_sha",
        "source_freeze_after_selection": True,
    }:
        raise ValueError("Item 20 candidate/control-plane single-SHA identity is not exact")

    historical = contract.get("historical_item19_proof")
    if not isinstance(historical, dict) or historical.get("role") != (
        "historical_provider_lifecycle_proof_only_not_item20_final_candidate"
    ):
        raise ValueError("Item 20 historical Item 19 proof boundary differs")

    control = contract.get("control_plane")
    if not isinstance(control, dict) or control != {
        "branch": "main",
        "protected": True,
        "quality_workflow": _QUALITY_WORKFLOW,
        "quality_workflow_path": _QUALITY_WORKFLOW_PATH,
        "quality_event": "push",
        "required_status": "completed",
        "required_conclusion": "success",
        "required_check": "Quality Gate",
    }:
        raise ValueError("Item 20 protected control-plane contract differs")

    session = contract.get("session")
    if not isinstance(session, dict) or session != {
        "identity_module": "apps/operator-cli/src/item20_acceptance.rs",
        "lifecycle_module": "apps/operator-cli/src/item20_session_lifecycle.rs",
        "ownership_intent_template": "item20:candidate:<candidate_sha>",
        "scope": "acceptance_only",
        "max_controlled_vms": 1,
        "terminal_item19_intent_reuse": "forbidden",
        "transport_endpoint": "derived_only_after_verified_target_resolution_never_authority",
    }:
        raise ValueError("Item 20 typed session contract differs")

    phone = contract.get("phone_preflight")
    if not isinstance(phone, dict) or phone != {
        "repository": "iamaman11/mobile-proxy-production",
        "authority": "execution_only",
        "workflow": ".github/workflows/phone-preflight.yml",
        "artifact_name_template": "phone-read-only-preflight-<control_plane_sha>",
        "canonical_logic": "scripts/run_private_phone_preflight.py",
        "required_runner_labels": _REQUIRED_RUNNER_LABELS,
        "mode": "read_only",
        "raw_device_identifier_recorded": False,
        "mutation_performed": False,
    }:
        raise ValueError("Item 20 private phone preflight contract differs")

    admission = contract.get("admission")
    if not isinstance(admission, dict) or admission != {
        "candidate_must_equal_control_plane_sha": True,
        "candidate_must_be_exact_current_protected_main": True,
        "control_plane_must_be_exact_current_protected_main": True,
        "control_plane_quality_must_succeed": True,
        "fresh_candidate_evidence_required": True,
        "fresh_candidate_evidence_verifier": _CANDIDATE_EVIDENCE_VERIFIER,
        "fresh_exact_candidate_provider_proof_required_before_live_window": True,
        "historical_item19_closeout_is_prior_evidence_not_current_candidate_authority": True,
        "required_issue_states": {
            "item19_tracker_124": "closed_completed_historical_provider_proof",
            "item20_tracker_135": "open",
            "phone_signing_gate_115": "closed_completed_before_live_window",
        },
        "same_window_private_phone_preflight_required_before_live_window": True,
        "source_freeze_after_candidate_evidence": True,
        "verifier": "scripts/verify_item20_admission.py",
    }:
        raise ValueError("Item 20 single-SHA admission requirements differ")

    future_live = contract.get("future_live_candidate_evidence")
    if not isinstance(future_live, dict) or future_live != {
        "acceptance_authority": "fresh_for_exact_candidate",
        "current_core_verification": "protected_pure_verifier_consumed_by_admission_core",
        "fresh_provider_lifecycle_proof": "required_for_exact_candidate_before_live_item20",
        "same_candidate_required": True,
        "software_release_candidate": "fresh_for_exact_candidate",
        "vultr_readonly_preflight": "fresh_for_exact_candidate",
    }:
        raise ValueError("Item 20 fresh candidate authority requirements differ")

    future_verifier = contract.get("future_live_candidate_verifier")
    if not isinstance(future_verifier, dict) or future_verifier != {
        "candidate_control_plane_exact_equality_required": True,
        "candidate_quality_run_attempt": 1,
        "grants_live_authority": False,
        "performs_external_io": False,
        "selection": "exact_current_protected_main_single_sha_then_fresh_candidate_evidence",
        "status": "protected_pure_verifier_consumed_by_admission_core",
        "verifier": _CANDIDATE_EVIDENCE_VERIFIER,
        "workflow_wiring": "implemented_exact_readiness_artifact_consumption",
    }:
        raise ValueError("Item 20 fresh candidate verifier contract differs")

    authorization = contract.get("authorization")
    if not isinstance(authorization, dict) or authorization != {
        "provider_mutation_authorized": False,
        "phone_mutation_authorized": False,
        "endpoint_handoff_authorized": False,
        "live_execution_authorized": False,
        "final_production_authority": False,
    }:
        raise ValueError("Item 20 admission core must remain validation-only")

    handoff = contract.get("handoff")
    if not isinstance(handoff, dict) or handoff != {
        "status": "not_implemented",
        "public_provider_uuid_recording": "forbidden",
        "public_transport_endpoint_recording": "forbidden",
        "private_phone_runner_vultr_credentials": "forbidden",
    }:
        raise ValueError("Item 20 handoff boundary differs")

    forbidden = contract.get("forbidden")
    if not isinstance(forbidden, list) or forbidden != [
        "provider_mutation_from_this_admission_core",
        "phone_mutation_from_this_admission_core",
        "public_endpoint_or_provider_uuid_evidence",
        "terminal_item19_intent_reuse",
        "candidate_control_plane_sha_mismatch",
        "live_window_without_fresh_exact_candidate_software_evidence",
        "live_window_without_fresh_exact_candidate_acceptance_authority",
        "live_window_without_fresh_exact_candidate_vultr_readonly_preflight",
        "live_window_without_fresh_exact_candidate_provider_proof",
        "production_vultr_authority",
        "final_release_tag_or_production_promotion",
        "gcp_or_manual_provider_control",
    ]:
        raise ValueError("Item 20 forbidden live-boundary set differs")


def verify_control_plane(
    control_plane_sha: str,
    branch: Mapping[str, object],
    quality_run: Mapping[str, object],
) -> None:
    control_plane_sha = validate_sha(control_plane_sha, "control-plane")
    commit = branch.get("commit")
    if (
        branch.get("name") != "main"
        or branch.get("protected") is not True
        or not isinstance(commit, dict)
        or commit.get("sha") != control_plane_sha
    ):
        raise ValueError("control-plane SHA is not the exact current protected main")

    repository = quality_run.get("repository")
    expected = {
        "name": _QUALITY_WORKFLOW,
        "path": _QUALITY_WORKFLOW_PATH,
        "event": "push",
        "head_branch": "main",
        "head_sha": control_plane_sha,
        "status": "completed",
        "conclusion": "success",
    }
    if not isinstance(repository, dict) or repository.get("full_name") != _CANONICAL_REPOSITORY:
        raise ValueError("control-plane Quality run is not from the canonical repository")
    if any(quality_run.get(key) != value for key, value in expected.items()):
        raise ValueError("control-plane Quality run does not match exact protected main")
    for field in ("id", "run_attempt"):
        value = quality_run.get(field)
        if not isinstance(value, int) or value <= 0:
            raise ValueError(f"control-plane Quality run has invalid {field}")


def _verify_issue(
    issue: Mapping[str, object],
    number: int,
    state: str,
    state_reason: str | None,
    label: str,
) -> None:
    if issue.get("number") != number or issue.get("state") != state:
        raise ValueError(f"{label} issue state does not satisfy Item 20 admission")
    if state_reason is not None and issue.get("state_reason") != state_reason:
        raise ValueError(f"{label} issue state_reason does not satisfy Item 20 admission")


def verify_issue_gates(
    item19_issue: Mapping[str, object],
    item20_issue: Mapping[str, object],
    signing_issue: Mapping[str, object],
) -> None:
    _verify_issue(item19_issue, 124, "closed", "completed", "Item 19 historical proof")
    _verify_issue(item20_issue, 135, "open", None, "Item 20")
    _verify_issue(signing_issue, 115, "closed", "completed", "phone signing-continuity gate")


def verify_phone_preflight(
    control_plane_sha: str,
    report: Mapping[str, object],
) -> None:
    control_plane_sha = validate_sha(control_plane_sha, "control-plane")
    if any(
        report.get(key) != value
        for key, value in {
            "format_version": 1,
            "repository": _CANONICAL_REPOSITORY,
            "canonical_sha": control_plane_sha,
            "mode": "read_only",
            "required_runner_labels": _REQUIRED_RUNNER_LABELS,
            "required_tools": _REQUIRED_TOOLS,
            "raw_device_identifier_recorded": False,
            "mutation_performed": False,
            "accepted": True,
        }.items()
    ):
        raise ValueError("private phone preflight evidence does not match the exact single-SHA control plane")

    device = report.get("device")
    if not isinstance(device, dict) or device != {
        "device_count": 1,
        "registered_device_match": True,
        "adb_state": "device",
        "shell_probe": True,
    }:
        raise ValueError("private phone preflight does not prove one exact registered online device")


def _verify_fresh_result(
    candidate_sha: str,
    control_plane_sha: str,
    evidence: Mapping[str, object],
) -> None:
    if candidate_sha != control_plane_sha:
        raise ValueError("candidate/control-plane SHA mismatch violates 10/10 single-SHA admission")
    if evidence.get("candidate_sha") != candidate_sha or evidence.get("control_plane_sha") != control_plane_sha:
        raise ValueError("fresh candidate evidence result does not bind the exact admission identity")
    for field in (
        "candidate_control_plane_exact_equality_verified",
        "fresh_acceptance_authority_verified",
        "fresh_vultr_readonly_preflight_verified",
        "fresh_exact_candidate_provider_proof_required_before_live_window",
        "source_freeze_required_after_evidence",
        "provider_probe_read_only_verified",
    ):
        if evidence.get(field) is not True:
            raise ValueError(f"fresh candidate evidence result did not verify {field}")
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
        if evidence.get(field) is not False:
            raise ValueError(f"fresh candidate evidence result violates validation-only boundary: {field}")


def verify_readiness_result(
    candidate_sha: str,
    control_plane_sha: str,
    quality_run: Mapping[str, object],
    fresh: Mapping[str, object],
    readiness_evidence: Mapping[str, object],
) -> None:
    _verify_fresh_result(candidate_sha, control_plane_sha, readiness_evidence)
    expected_identity = {
        "format_version": 1,
        "authority": _READINESS_AUTHORITY,
        "repository": _CANONICAL_REPOSITORY,
        "candidate_sha": candidate_sha,
        "control_plane_sha": control_plane_sha,
        "control_plane_quality_run_id": str(quality_run["id"]),
    }
    if any(readiness_evidence.get(key) != value for key, value in expected_identity.items()):
        raise ValueError("admission-readiness result does not bind exact single-SHA Quality identity")
    if dict(readiness_evidence) != dict(fresh):
        raise ValueError("admission-readiness result does not exactly match independently verified candidate evidence")


def verify_admission(
    candidate_sha: str,
    control_plane_sha: str,
    contract: Mapping[str, object],
    branch: Mapping[str, object],
    quality_run: Mapping[str, object],
    item19_issue: Mapping[str, object],
    item20_issue: Mapping[str, object],
    signing_issue: Mapping[str, object],
    phone_preflight: Mapping[str, object],
    acceptance_artifact: Mapping[str, object],
    acceptance_run: Mapping[str, object],
    acceptance_evidence: Mapping[str, object],
    preflight_artifact: Mapping[str, object],
    preflight_run: Mapping[str, object],
    preflight_evidence: Mapping[str, object],
    readiness_evidence: Mapping[str, object],
) -> dict[str, object]:
    candidate_sha = validate_sha(candidate_sha, "candidate")
    control_plane_sha = validate_sha(control_plane_sha, "control-plane")
    if candidate_sha != control_plane_sha:
        raise ValueError("candidate/control-plane SHA mismatch violates 10/10 single-SHA admission")
    verify_contract(contract)
    verify_control_plane(control_plane_sha, branch, quality_run)
    verify_issue_gates(item19_issue, item20_issue, signing_issue)
    verify_phone_preflight(control_plane_sha, phone_preflight)

    fresh = verify_candidate_chain(
        candidate_sha,
        control_plane_sha,
        contract,
        branch,
        quality_run,
        acceptance_artifact,
        acceptance_run,
        acceptance_evidence,
        preflight_artifact,
        preflight_run,
        preflight_evidence,
    )
    _verify_fresh_result(candidate_sha, control_plane_sha, fresh)
    verify_readiness_result(candidate_sha, control_plane_sha, quality_run, fresh, readiness_evidence)

    return {
        "format_version": 1,
        "authority": "item20_non_live_single_sha_admission_validation",
        "repository": _CANONICAL_REPOSITORY,
        "candidate_sha": candidate_sha,
        "control_plane_sha": control_plane_sha,
        "candidate_control_plane_exact_equality_verified": True,
        "control_plane_quality_run_id": str(quality_run["id"]),
        "item19_historical_tracker_completed": True,
        "item20_tracker_open": True,
        "phone_signing_gate_completed": True,
        "private_phone_read_only_preflight_accepted": True,
        "admission_readiness_result_verified": True,
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
        "raw_phone_identifier_recorded": False,
    }


def _load_object(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"cannot load JSON {path}: {error}") from error
    if not isinstance(value, dict):
        raise ValueError(f"JSON value must be an object: {path}")
    return value


def _write_object(path: Path, value: Mapping[str, object]) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate-sha", required=True)
    parser.add_argument("--control-plane-sha", required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--main-branch", type=Path, required=True)
    parser.add_argument("--quality-run", type=Path, required=True)
    parser.add_argument("--item19-issue", type=Path, required=True)
    parser.add_argument("--item20-issue", type=Path, required=True)
    parser.add_argument("--signing-issue", type=Path, required=True)
    parser.add_argument("--phone-preflight", type=Path, required=True)
    parser.add_argument("--acceptance-artifact", type=Path, required=True)
    parser.add_argument("--acceptance-run", type=Path, required=True)
    parser.add_argument("--acceptance-evidence", type=Path, required=True)
    parser.add_argument("--preflight-artifact", type=Path, required=True)
    parser.add_argument("--preflight-run", type=Path, required=True)
    parser.add_argument("--preflight-evidence", type=Path, required=True)
    parser.add_argument("--readiness-evidence", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    evidence = verify_admission(
        args.candidate_sha,
        args.control_plane_sha,
        _load_object(args.contract),
        _load_object(args.main_branch),
        _load_object(args.quality_run),
        _load_object(args.item19_issue),
        _load_object(args.item20_issue),
        _load_object(args.signing_issue),
        _load_object(args.phone_preflight),
        _load_object(args.acceptance_artifact),
        _load_object(args.acceptance_run),
        _load_object(args.acceptance_evidence),
        _load_object(args.preflight_artifact),
        _load_object(args.preflight_run),
        _load_object(args.preflight_evidence),
        _load_object(args.readiness_evidence),
    )
    _write_object(args.output, evidence)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
