#!/usr/bin/env python3
"""Validate the protected non-live Production Baseline Item 20 single-SHA orchestration surface."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Mapping

from verify_item20_admission import validate_sha, verify_contract, verify_control_plane

_CANONICAL_REPOSITORY = "iamaman11/mobile-proxy"
_QUALITY_WORKFLOW = "Quality"
_QUALITY_WORKFLOW_PATH = ".github/workflows/quality.yml"
_ORCHESTRATION = {
    "status": "protected_validation_and_candidate_build_only",
    "workflow": ".github/workflows/item20-session-orchestration.yml",
    "verifier": "scripts/verify_item20_orchestration.py",
    "trigger": "workflow_dispatch",
    "executor": "github-hosted",
    "control_plane_source": "exact_current_protected_main",
    "candidate_source": "same_exact_current_protected_main_as_control_plane",
    "server_artifact_name_template": "item20-server-candidate-<candidate_sha>",
    "provider_environment": "none",
    "provider_credentials": "forbidden",
    "provider_mutation": False,
    "phone_execution": False,
    "endpoint_handoff": "not_implemented",
}


def select_quality_run(
    control_plane_sha: str, payload: Mapping[str, object]
) -> dict[str, object]:
    control_plane_sha = validate_sha(control_plane_sha, "control-plane")
    runs = payload.get("workflow_runs")
    if not isinstance(runs, list):
        raise ValueError("Quality workflow response is missing workflow_runs")

    eligible: list[dict[str, object]] = []
    for raw in runs:
        if not isinstance(raw, dict):
            continue
        repository = raw.get("repository")
        if not isinstance(repository, dict) or repository.get("full_name") != _CANONICAL_REPOSITORY:
            continue
        if any(
            raw.get(key) != value
            for key, value in {
                "name": _QUALITY_WORKFLOW,
                "path": _QUALITY_WORKFLOW_PATH,
                "event": "push",
                "head_branch": "main",
                "head_sha": control_plane_sha,
                "status": "completed",
                "conclusion": "success",
            }.items()
        ):
            continue
        run_id = raw.get("id")
        attempt = raw.get("run_attempt")
        if not isinstance(run_id, int) or run_id <= 0:
            continue
        if not isinstance(attempt, int) or attempt <= 0:
            continue
        eligible.append(raw)

    distinct_ids = {int(run["id"]) for run in eligible}
    if len(distinct_ids) != 1:
        raise ValueError("control plane must have exactly one eligible canonical Quality push run")
    return eligible[0]


def _verify_issue(
    issue: Mapping[str, object], number: int, state: str, state_reason: str | None, label: str
) -> None:
    if issue.get("number") != number or issue.get("state") != state:
        raise ValueError(f"{label} issue state does not satisfy non-live Item 20 orchestration")
    if state_reason is not None and issue.get("state_reason") != state_reason:
        raise ValueError(f"{label} issue state_reason does not satisfy non-live Item 20 orchestration")


def phone_signing_gate_completed(issue: Mapping[str, object]) -> bool:
    if issue.get("number") != 115:
        raise ValueError("phone signing-continuity gate identity is invalid")
    if issue.get("state") == "open":
        return False
    if issue.get("state") == "closed" and issue.get("state_reason") == "completed":
        return True
    raise ValueError("phone signing-continuity gate is neither OPEN nor closed completed")


def verify_orchestration(
    candidate_sha: str,
    control_plane_sha: str,
    contract: Mapping[str, object],
    branch: Mapping[str, object],
    quality_run: Mapping[str, object],
    item19_issue: Mapping[str, object],
    item20_issue: Mapping[str, object],
    signing_issue: Mapping[str, object],
) -> dict[str, object]:
    candidate_sha = validate_sha(candidate_sha, "candidate")
    control_plane_sha = validate_sha(control_plane_sha, "control-plane")
    if candidate_sha != control_plane_sha:
        raise ValueError("candidate/control-plane SHA mismatch violates 10/10 single-SHA orchestration")
    verify_contract(contract)

    if contract.get("orchestration") != _ORCHESTRATION:
        raise ValueError("Item 20 non-live single-SHA orchestration contract differs")

    identity = contract.get("identity")
    if not isinstance(identity, dict) or identity.get("exact_equality_required") is not True:
        raise ValueError("Item 20 contract does not enforce candidate/control-plane equality")

    verify_control_plane(control_plane_sha, branch, quality_run)
    _verify_issue(item19_issue, 124, "closed", "completed", "Item 19 historical proof")
    _verify_issue(item20_issue, 135, "open", None, "Item 20")
    signing_completed = phone_signing_gate_completed(signing_issue)

    return {
        "format_version": 1,
        "authority": "item20_non_live_single_sha_orchestration",
        "repository": _CANONICAL_REPOSITORY,
        "candidate_sha": candidate_sha,
        "control_plane_sha": control_plane_sha,
        "candidate_control_plane_exact_equality_verified": True,
        "control_plane_quality_run_id": str(quality_run["id"]),
        "item19_historical_tracker_completed": True,
        "item20_tracker_open": True,
        "phone_signing_gate_completed": signing_completed,
        "fresh_acceptance_authority_verified": False,
        "fresh_vultr_readonly_preflight_verified": False,
        "fresh_exact_candidate_provider_proof_required_before_live_window": True,
        "source_freeze_required_after_evidence": True,
        "non_live_candidate_artifact_build_authorized": True,
        "provider_credential_access_performed": False,
        "provider_mutation_authorized": False,
        "phone_mutation_authorized": False,
        "endpoint_handoff_authorized": False,
        "live_execution_authorized": False,
        "final_production_authority": False,
        "provider_identifier_recorded": False,
        "transport_endpoint_recorded": False,
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
    subparsers = parser.add_subparsers(dest="command", required=True)

    select = subparsers.add_parser("select-quality-run")
    select.add_argument("--control-plane-sha", required=True)
    select.add_argument("--runs", type=Path, required=True)
    select.add_argument("--output", type=Path, required=True)

    verify = subparsers.add_parser("verify")
    verify.add_argument("--candidate-sha", required=True)
    verify.add_argument("--control-plane-sha", required=True)
    verify.add_argument("--contract", type=Path, required=True)
    verify.add_argument("--main-branch", type=Path, required=True)
    verify.add_argument("--quality-run", type=Path, required=True)
    verify.add_argument("--item19-issue", type=Path, required=True)
    verify.add_argument("--item20-issue", type=Path, required=True)
    verify.add_argument("--signing-issue", type=Path, required=True)
    verify.add_argument("--output", type=Path, required=True)

    args = parser.parse_args()
    if args.command == "select-quality-run":
        selected = select_quality_run(args.control_plane_sha, _load_object(args.runs))
        _write_object(args.output, selected)
        print(selected["id"])
        return 0

    evidence = verify_orchestration(
        args.candidate_sha,
        args.control_plane_sha,
        _load_object(args.contract),
        _load_object(args.main_branch),
        _load_object(args.quality_run),
        _load_object(args.item19_issue),
        _load_object(args.item20_issue),
        _load_object(args.signing_issue),
    )
    _write_object(args.output, evidence)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
