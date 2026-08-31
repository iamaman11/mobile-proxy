#!/usr/bin/env python3
"""Pure verifier for fresh Item 20 candidate authority and read-only evidence.

This module deliberately performs no GitHub, provider, or phone I/O.  Callers must
supply bounded GitHub run/artifact metadata plus downloaded JSON evidence.  The
verifier keeps the immutable software candidate distinct from the moving protected
control-plane revision.
"""

from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import re
from typing import Mapping


_CANONICAL_REPOSITORY = "iamaman11/mobile-proxy"
_IMMUTABLE_CANDIDATE = "d151dbdd156279e32a5361d304c90f996bd2d565"
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
        raise ValueError(f"{kind} SHA must be an exact lowercase 40-character hexadecimal identity")
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
    if any(
        contract.get(key) != value
        for key, value in {
            "contract_version": 1,
            "status": "protected_non_live_admission_core",
            "canonical_repository": _CANONICAL_REPOSITORY,
            "tracker_issue": 135,
            "completed_provider_proof_issue": 124,
            "phone_signing_gate_issue": 115,
        }.items()
    ):
        raise ValueError("Item 20 admission contract identity mismatch")

    immutable = contract.get("immutable_candidate")
    if not isinstance(immutable, dict) or immutable.get("candidate_sha") != _IMMUTABLE_CANDIDATE:
        raise ValueError("Item 20 immutable candidate differs from protected Item 19 closeout")
    candidate_quality_run_id = _positive_int(
        immutable.get("item19_quality_run_id"), "immutable candidate Quality run id"
    )

    future = contract.get("future_live_candidate_evidence")
    expected_future = {
        "acceptance_authority": "fresh_for_exact_candidate",
        "vultr_readonly_preflight": "fresh_for_exact_candidate",
        "same_candidate_required": True,
        "candidate_control_plane_separation_required": True,
        "selection": "candidate_specific_artifact_then_exact_control_plane_run",
        "verifier": _VERIFIER_PATH,
        "current_core_verification": "protected_pure_verifier",
        "workflow_wiring": "not_implemented",
    }
    if not isinstance(future, dict) or future != expected_future:
        raise ValueError("Item 20 fresh candidate evidence verification contract differs")

    authorization = contract.get("authorization")
    if not isinstance(authorization, dict) or authorization != {
        "endpoint_handoff_authorized": False,
        "final_production_authority": False,
        "live_execution_authorized": False,
        "phone_mutation_authorized": False,
        "provider_mutation_authorized": False,
    }:
        raise ValueError("Item 20 candidate evidence verifier cannot grant live authority")
    return candidate_quality_run_id


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
        raise ValueError(f"{label} run does not match exact Item 20 control plane")
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
    run_id = _positive_int(run.get("id"), f"{label} run id")
    expected_name = f"{expected_name_prefix}-{candidate_sha}"
    if artifact.get("name") != expected_name:
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
        raise ValueError(f"{label} artifact is not bound to the exact control-plane run")


def verify_acceptance_evidence(
    candidate_sha: str,
    candidate_quality_run_id: int,
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
    _positive_decimal(
        evidence.get("candidate_quality_run_attempt"), "candidate Quality run attempt"
    )


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
    if candidate_sha == control_plane_sha:
        raise ValueError("Item 20 verifier requires candidate/control-plane identities to remain distinct")
    candidate_quality_run_id = verify_contract(contract)
    if candidate_sha != _IMMUTABLE_CANDIDATE:
        raise ValueError("candidate SHA does not match the protected Item 19 closeout")

    verify_control_plane(control_plane_sha, branch, control_plane_quality_run)
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
        candidate_sha, candidate_quality_run_id, acceptance_run, acceptance_evidence
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

    quality_id = _positive_int(control_plane_quality_run.get("id"), "control-plane Quality run id")
    acceptance_id = _positive_int(acceptance_run.get("id"), "acceptance run id")
    preflight_id = _positive_int(preflight_run.get("id"), "preflight run id")
    return {
        "format_version": 1,
        "authority": "item20_fresh_candidate_evidence_verification",
        "repository": _CANONICAL_REPOSITORY,
        "candidate_sha": candidate_sha,
        "control_plane_sha": control_plane_sha,
        "control_plane_quality_run_id": str(quality_id),
        "candidate_quality_run_id": str(candidate_quality_run_id),
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
