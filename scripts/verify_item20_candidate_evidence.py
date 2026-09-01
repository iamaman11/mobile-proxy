#!/usr/bin/env python3
"""Pure verifier for fresh single-SHA Item 20 candidate evidence.

No GitHub, provider, or phone I/O is performed here. Callers supply bounded run and
artifact metadata plus downloaded JSON evidence. For the 10/10 baseline the software
candidate and control-plane policy are deliberately the same exact protected main SHA.
"""

from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import re
from typing import Mapping


_CANONICAL_REPOSITORY = "iamaman11/mobile-proxy"
_QUALITY_WORKFLOW = "Quality"
_QUALITY_WORKFLOW_PATH = ".github/workflows/quality.yml"
_ACCEPTANCE_WORKFLOW = "Vultr acceptance authority"
_ACCEPTANCE_WORKFLOW_PATH = ".github/workflows/acceptance-authority.yml"
_PREFLIGHT_WORKFLOW = "Vultr read-only acceptance preflight"
_PREFLIGHT_WORKFLOW_PATH = ".github/workflows/vultr-readonly-preflight.yml"
_VERIFIER_PATH = "scripts/verify_item20_candidate_evidence.py"
_SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
_DIGEST_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")


def validate_sha(value: object, kind: str) -> str:
    if not isinstance(value, str) or _SHA_PATTERN.fullmatch(value) is None:
        raise ValueError(
            f"{kind} SHA must be an exact lowercase 40-character hexadecimal identity"
        )
    return value


def _positive_int(value: object, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ValueError(f"invalid {field}")
    return value


def _positive_decimal(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.isdecimal() or int(value) <= 0:
        raise ValueError(f"invalid {field}")
    return value


def _parse_time(value: object, field: str) -> datetime:
    if not isinstance(value, str) or not value or len(value) > 64:
        raise ValueError(f"invalid {field}")
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as error:
        raise ValueError(f"invalid {field}") from error
    if parsed.utcoffset() is None:
        raise ValueError(f"invalid {field}")
    return parsed


def verify_contract(contract: Mapping[str, object]) -> int:
    expected_top = {
        "contract_version": 1,
        "status": "protected_non_live_admission_core",
        "canonical_repository": _CANONICAL_REPOSITORY,
        "tracker_issue": 135,
        "completed_provider_proof_issue": 124,
        "phone_signing_gate_issue": 115,
    }
    if any(contract.get(key) != value for key, value in expected_top.items()):
        raise ValueError("Item 20 admission contract identity mismatch")

    identity = contract.get("identity")
    expected_identity = {
        "candidate_sha": "exact_current_protected_main_revision_selected_for_10_of_10_window",
        "control_plane_sha": "same_exact_current_protected_main_revision",
        "exact_equality_required": True,
        "final_release_tag_target": "candidate_sha",
        "source_freeze_after_selection": True,
    }
    if not isinstance(identity, dict) or identity != expected_identity:
        raise ValueError("Item 20 single-SHA identity contract differs")

    historical = contract.get("historical_item19_proof")
    if not isinstance(historical, dict) or historical.get("role") != (
        "historical_provider_lifecycle_proof_only_not_item20_final_candidate"
    ):
        raise ValueError("Item 20 historical Item 19 evidence boundary differs")

    future_evidence = contract.get("future_live_candidate_evidence")
    if not isinstance(future_evidence, dict) or future_evidence != {
        "acceptance_authority": "fresh_for_exact_candidate",
        "current_core_verification": "protected_pure_verifier_consumed_by_admission_core",
        "fresh_provider_lifecycle_proof": "required_for_exact_candidate_before_live_item20",
        "same_candidate_required": True,
        "software_release_candidate": "fresh_for_exact_candidate",
        "vultr_readonly_preflight": "fresh_for_exact_candidate",
    }:
        raise ValueError("Item 20 future live candidate evidence requirement differs")

    verifier = contract.get("future_live_candidate_verifier")
    expected_verifier = {
        "candidate_control_plane_exact_equality_required": True,
        "candidate_quality_run_attempt": 1,
        "grants_live_authority": False,
        "performs_external_io": False,
        "selection": "exact_current_protected_main_single_sha_then_fresh_candidate_evidence",
        "status": "protected_pure_verifier_consumed_by_admission_core",
        "verifier": _VERIFIER_PATH,
        "workflow_wiring": "implemented_exact_readiness_artifact_consumption",
    }
    if not isinstance(verifier, dict) or verifier != expected_verifier:
        raise ValueError("Item 20 pure candidate evidence verifier contract differs")

    admission = contract.get("admission")
    if not isinstance(admission, dict):
        raise ValueError("Item 20 admission contract is missing")
    for key in (
        "candidate_must_equal_control_plane_sha",
        "candidate_must_be_exact_current_protected_main",
        "fresh_candidate_evidence_required",
        "fresh_exact_candidate_provider_proof_required_before_live_window",
        "source_freeze_after_candidate_evidence",
    ):
        if admission.get(key) is not True:
            raise ValueError(f"Item 20 admission must require {key}")

    authorization = contract.get("authorization")
    if not isinstance(authorization, dict) or authorization != {
        "endpoint_handoff_authorized": False,
        "final_production_authority": False,
        "live_execution_authorized": False,
        "phone_mutation_authorized": False,
        "provider_mutation_authorized": False,
    }:
        raise ValueError("Item 20 candidate evidence verifier cannot grant live authority")

    return int(expected_verifier["candidate_quality_run_attempt"])


def verify_control_plane(
    control_plane_sha: str,
    branch: Mapping[str, object],
    quality_run: Mapping[str, object],
) -> None:
    validate_sha(control_plane_sha, "control-plane")
    commit = branch.get("commit")
    if (
        branch.get("name") != "main"
        or branch.get("protected") is not True
        or not isinstance(commit, dict)
        or commit.get("sha") != control_plane_sha
    ):
        raise ValueError("control-plane SHA is not the exact current protected main")

    repository = quality_run.get("repository")
    if not isinstance(repository, dict) or repository.get("full_name") != _CANONICAL_REPOSITORY:
        raise ValueError("control-plane Quality run is not canonical")
    expected = {
        "name": _QUALITY_WORKFLOW,
        "path": _QUALITY_WORKFLOW_PATH,
        "event": "push",
        "head_branch": "main",
        "head_sha": control_plane_sha,
        "status": "completed",
        "conclusion": "success",
    }
    if any(quality_run.get(key) != value for key, value in expected.items()):
        raise ValueError("control-plane Quality run does not match exact protected main")
    _positive_int(quality_run.get("id"), "control-plane Quality run id")
    _positive_int(quality_run.get("run_attempt"), "control-plane Quality run attempt")
    _parse_time(quality_run.get("created_at"), "control-plane Quality created_at")


def verify_workflow_run(
    control_plane_sha: str,
    run: Mapping[str, object],
    *,
    expected_name: str,
    expected_path: str,
    label: str,
) -> None:
    validate_sha(control_plane_sha, "control-plane")
    repository = run.get("repository")
    if not isinstance(repository, dict) or repository.get("full_name") != _CANONICAL_REPOSITORY:
        raise ValueError(f"{label} run is not canonical")
    expected = {
        "name": expected_name,
        "path": expected_path,
        "event": "issue_comment",
        "head_branch": "main",
        "head_sha": control_plane_sha,
        "status": "completed",
        "conclusion": "success",
    }
    if any(run.get(key) != value for key, value in expected.items()):
        raise ValueError(f"{label} run does not match exact Item 20 single-SHA control plane")
    _positive_int(run.get("id"), f"{label} run id")
    _positive_int(run.get("run_attempt"), f"{label} run attempt")
    _parse_time(run.get("created_at"), f"{label} created_at")


def verify_artifact_metadata(
    candidate_sha: str,
    control_plane_sha: str,
    artifact: Mapping[str, object],
    run: Mapping[str, object],
    *,
    expected_name_prefix: str,
    label: str,
) -> None:
    validate_sha(candidate_sha, "candidate")
    validate_sha(control_plane_sha, "control-plane")
    if candidate_sha != control_plane_sha:
        raise ValueError("candidate/control-plane SHA mismatch violates 10/10 single-SHA acceptance")
    run_id = _positive_int(run.get("id"), f"{label} run id")
    if artifact.get("name") != f"{expected_name_prefix}-{candidate_sha}":
        raise ValueError(f"{label} artifact name does not bind the exact candidate")
    if artifact.get("expired") is not False:
        raise ValueError(f"{label} artifact is expired or expiry is ambiguous")
    _positive_int(artifact.get("id"), f"{label} artifact id")
    _positive_int(artifact.get("size_in_bytes"), f"{label} artifact size")
    digest = artifact.get("digest")
    if not isinstance(digest, str) or _DIGEST_PATTERN.fullmatch(digest) is None:
        raise ValueError(f"{label} artifact digest is missing or invalid")
    _parse_time(artifact.get("created_at"), f"{label} artifact created_at")

    workflow_run = artifact.get("workflow_run")
    if not isinstance(workflow_run, dict) or any(
        workflow_run.get(key) != value
        for key, value in {
            "id": run_id,
            "head_branch": "main",
            "head_sha": control_plane_sha,
        }.items()
    ):
        raise ValueError(f"{label} artifact is not bound to the exact single-SHA run")


def verify_acceptance_evidence(
    candidate_sha: str,
    candidate_quality_run_id: int,
    candidate_quality_run_attempt: int,
    acceptance_run: Mapping[str, object],
    evidence: Mapping[str, object],
) -> None:
    validate_sha(candidate_sha, "candidate")
    run_id = _positive_int(acceptance_run.get("id"), "acceptance run id")
    run_attempt = _positive_int(acceptance_run.get("run_attempt"), "acceptance run attempt")
    expected = {
        "format_version": 1,
        "authority": "pre_release_acceptance",
        "candidate_sha": candidate_sha,
        "repository": _CANONICAL_REPOSITORY,
        "executor": "github-hosted",
        "acceptance_workflow": _ACCEPTANCE_WORKFLOW,
        "acceptance_workflow_run_id": str(run_id),
        "acceptance_workflow_run_attempt": str(run_attempt),
        "command_issue": 90,
        "candidate_quality_run_id": str(candidate_quality_run_id),
        "candidate_quality_run_attempt": str(candidate_quality_run_attempt),
        "candidate_evidence_artifact": f"software-release-candidate-{candidate_sha}",
        "candidate_evidence_file": "release-candidate-evidence.json",
        "final_production_authority": False,
        "production_environment_authorized": False,
        "final_release_tag_created": False,
        "vultr_api_access_performed": False,
        "vm_mutation_performed": False,
        "phone_mutation_performed": False,
    }
    mismatched = [key for key, value in expected.items() if evidence.get(key) != value]
    if mismatched:
        raise ValueError(
            "fresh acceptance-authority evidence does not match exact Item 20 candidate/run: "
            + ", ".join(sorted(mismatched))
        )
    _positive_decimal(evidence.get("command_comment_id"), "acceptance command_comment_id")


def verify_preflight_evidence(
    candidate_sha: str,
    preflight_run: Mapping[str, object],
    acceptance_run: Mapping[str, object],
    evidence: Mapping[str, object],
) -> None:
    validate_sha(candidate_sha, "candidate")
    run_id = _positive_int(preflight_run.get("id"), "preflight run id")
    run_attempt = _positive_int(preflight_run.get("run_attempt"), "preflight run attempt")
    acceptance_run_id = _positive_int(acceptance_run.get("id"), "acceptance run id")
    acceptance_run_attempt = _positive_int(
        acceptance_run.get("run_attempt"), "acceptance run attempt"
    )
    expected = {
        "format_version": 1,
        "authority": "pre_release_acceptance_read_only",
        "candidate_sha": candidate_sha,
        "repository": _CANONICAL_REPOSITORY,
        "executor": "github-hosted",
        "environment": "acceptance-vultr",
        "workflow": _PREFLIGHT_WORKFLOW,
        "workflow_run_id": str(run_id),
        "workflow_run_attempt": str(run_attempt),
        "command_issue": 90,
        "acceptance_authority_run_id": str(acceptance_run_id),
        "acceptance_authority_run_attempt": str(acceptance_run_attempt),
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
    mismatched = [key for key, value in expected.items() if evidence.get(key) != value]
    if mismatched:
        raise ValueError(
            "fresh read-only preflight evidence does not match exact Item 20 candidate/run chain: "
            + ", ".join(sorted(mismatched))
        )
    _positive_decimal(evidence.get("command_comment_id"), "preflight command_comment_id")


def verify_fresh_order(
    control_plane_quality_run: Mapping[str, object],
    acceptance_run: Mapping[str, object],
    acceptance_artifact: Mapping[str, object],
    preflight_run: Mapping[str, object],
    preflight_artifact: Mapping[str, object],
) -> None:
    ordered = [
        _parse_time(control_plane_quality_run.get("created_at"), "control-plane Quality created_at"),
        _parse_time(acceptance_run.get("created_at"), "acceptance created_at"),
        _parse_time(acceptance_artifact.get("created_at"), "acceptance artifact created_at"),
        _parse_time(preflight_run.get("created_at"), "preflight created_at"),
        _parse_time(preflight_artifact.get("created_at"), "preflight artifact created_at"),
    ]
    if ordered != sorted(ordered):
        raise ValueError("Item 20 candidate authority chain is stale or out of order")


def verify_candidate_chain(
    candidate_sha: str,
    control_plane_sha: str,
    contract: Mapping[str, object],
    branch: Mapping[str, object],
    control_plane_quality_run: Mapping[str, object],
    acceptance_artifact: Mapping[str, object],
    acceptance_run: Mapping[str, object],
    acceptance_evidence: Mapping[str, object],
    preflight_artifact: Mapping[str, object],
    preflight_run: Mapping[str, object],
    preflight_evidence: Mapping[str, object],
) -> dict[str, object]:
    candidate_sha = validate_sha(candidate_sha, "candidate")
    control_plane_sha = validate_sha(control_plane_sha, "control-plane")
    if candidate_sha != control_plane_sha:
        raise ValueError("candidate/control-plane SHA mismatch violates 10/10 single-SHA acceptance")

    candidate_quality_run_attempt = verify_contract(contract)
    verify_control_plane(control_plane_sha, branch, control_plane_quality_run)
    candidate_quality_run_id = _positive_int(
        control_plane_quality_run.get("id"), "candidate/control-plane Quality run id"
    )
    actual_quality_attempt = _positive_int(
        control_plane_quality_run.get("run_attempt"), "candidate/control-plane Quality run attempt"
    )
    if actual_quality_attempt != candidate_quality_run_attempt:
        raise ValueError("candidate/control-plane Quality run attempt differs from protected contract")

    verify_workflow_run(
        control_plane_sha,
        acceptance_run,
        expected_name=_ACCEPTANCE_WORKFLOW,
        expected_path=_ACCEPTANCE_WORKFLOW_PATH,
        label="acceptance",
    )
    verify_artifact_metadata(
        candidate_sha,
        control_plane_sha,
        acceptance_artifact,
        acceptance_run,
        expected_name_prefix="vultr-acceptance-authority",
        label="acceptance",
    )
    verify_acceptance_evidence(
        candidate_sha,
        candidate_quality_run_id,
        candidate_quality_run_attempt,
        acceptance_run,
        acceptance_evidence,
    )

    verify_workflow_run(
        control_plane_sha,
        preflight_run,
        expected_name=_PREFLIGHT_WORKFLOW,
        expected_path=_PREFLIGHT_WORKFLOW_PATH,
        label="preflight",
    )
    verify_artifact_metadata(
        candidate_sha,
        control_plane_sha,
        preflight_artifact,
        preflight_run,
        expected_name_prefix="vultr-readonly-preflight",
        label="preflight",
    )
    verify_preflight_evidence(
        candidate_sha, preflight_run, acceptance_run, preflight_evidence
    )
    verify_fresh_order(
        control_plane_quality_run,
        acceptance_run,
        acceptance_artifact,
        preflight_run,
        preflight_artifact,
    )

    quality_id = candidate_quality_run_id
    acceptance_id = _positive_int(acceptance_run.get("id"), "acceptance run id")
    preflight_id = _positive_int(preflight_run.get("id"), "preflight run id")
    return {
        "format_version": 1,
        "authority": "item20_fresh_single_sha_candidate_evidence_verification",
        "repository": _CANONICAL_REPOSITORY,
        "candidate_sha": candidate_sha,
        "control_plane_sha": control_plane_sha,
        "candidate_control_plane_exact_equality_verified": True,
        "control_plane_quality_run_id": str(quality_id),
        "candidate_quality_run_id": str(quality_id),
        "candidate_quality_run_attempt": str(candidate_quality_run_attempt),
        "acceptance_authority_run_id": str(acceptance_id),
        "acceptance_authority_artifact_id": str(
            _positive_int(acceptance_artifact.get("id"), "acceptance artifact id")
        ),
        "acceptance_authority_artifact_digest": acceptance_artifact["digest"],
        "vultr_readonly_preflight_run_id": str(preflight_id),
        "vultr_readonly_preflight_artifact_id": str(
            _positive_int(preflight_artifact.get("id"), "preflight artifact id")
        ),
        "vultr_readonly_preflight_artifact_digest": preflight_artifact["digest"],
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
    parser.add_argument("--control-plane-quality-run", type=Path, required=True)
    parser.add_argument("--acceptance-artifact", type=Path, required=True)
    parser.add_argument("--acceptance-run", type=Path, required=True)
    parser.add_argument("--acceptance-evidence", type=Path, required=True)
    parser.add_argument("--preflight-artifact", type=Path, required=True)
    parser.add_argument("--preflight-run", type=Path, required=True)
    parser.add_argument("--preflight-evidence", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    evidence = verify_candidate_chain(
        args.candidate_sha,
        args.control_plane_sha,
        _load_object(args.contract),
        _load_object(args.main_branch),
        _load_object(args.control_plane_quality_run),
        _load_object(args.acceptance_artifact),
        _load_object(args.acceptance_run),
        _load_object(args.acceptance_evidence),
        _load_object(args.preflight_artifact),
        _load_object(args.preflight_run),
        _load_object(args.preflight_evidence),
    )
    _write_object(args.output, evidence)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
