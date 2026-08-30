#!/usr/bin/env python3
"""Verify the exact Item 19 Slice B acceptance admission chain."""

from __future__ import annotations

import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import re
import sys
from typing import Mapping

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from verify_acceptance_candidate import (
    select_quality_run,
    validate_candidate_sha,
    verify_candidate_evidence,
)
from verify_vultr_readonly_preflight import (
    select_acceptance_run,
    verify_acceptance_evidence,
)

_COMMAND_PATTERN = re.compile(r"^/item19-acceptance-ready ([0-9a-f]{40})$")
_CANONICAL_REPOSITORY = "iamaman11/mobile-proxy"
_PREFLIGHT_WORKFLOW = "Vultr read-only acceptance preflight"
_PREFLIGHT_WORKFLOW_PATH = ".github/workflows/vultr-readonly-preflight.yml"
_ITEM19_ISSUE = 124
_SIGNING_GATE_ISSUE = 115


def parse_command(body: str) -> str:
    if not body or len(body) > 192:
        raise ValueError("item-19 readiness command is missing or unbounded")
    normalized = body.rstrip("\r\n")
    match = _COMMAND_PATTERN.fullmatch(normalized)
    if match is None:
        raise ValueError(
            "item-19 readiness command must contain one exact lowercase 40-character SHA"
        )
    return match.group(1)


def select_preflight_run(
    candidate_sha: str, payload: Mapping[str, object]
) -> dict[str, object]:
    validate_candidate_sha(candidate_sha)
    runs = payload.get("workflow_runs")
    if not isinstance(runs, list):
        raise ValueError("Actions response is missing workflow_runs")

    eligible: list[dict[str, object]] = []
    for raw in runs:
        if not isinstance(raw, dict):
            continue
        repository = raw.get("repository")
        if (
            not isinstance(repository, dict)
            or repository.get("full_name") != _CANONICAL_REPOSITORY
        ):
            continue
        if any(
            raw.get(key) != value
            for key, value in {
                "name": _PREFLIGHT_WORKFLOW,
                "path": _PREFLIGHT_WORKFLOW_PATH,
                "event": "issue_comment",
                "head_branch": "main",
                "head_sha": candidate_sha,
                "status": "completed",
                "conclusion": "success",
            }.items()
        ):
            continue
        run_id = raw.get("id")
        run_attempt = raw.get("run_attempt")
        if not isinstance(run_id, int) or run_id <= 0:
            continue
        if not isinstance(run_attempt, int) or run_attempt <= 0:
            continue
        eligible.append(raw)

    if not eligible:
        raise ValueError("candidate has no successful immutable read-only preflight run")
    return max(eligible, key=lambda run: (int(run["id"]), int(run["run_attempt"])))


def verify_main_branch(candidate_sha: str, branch: Mapping[str, object]) -> None:
    validate_candidate_sha(candidate_sha)
    commit = branch.get("commit")
    if (
        branch.get("name") != "main"
        or branch.get("protected") is not True
        or not isinstance(commit, dict)
        or commit.get("sha") != candidate_sha
    ):
        raise ValueError("candidate is not the exact current protected main SHA")


def verify_signing_gate(issue: Mapping[str, object]) -> None:
    if issue.get("number") != _SIGNING_GATE_ISSUE or issue.get("state") != "closed":
        raise ValueError("signing continuity gate #115 is not closed")


def verify_preflight_evidence(
    candidate_sha: str,
    preflight_run: Mapping[str, object],
    acceptance_run: Mapping[str, object],
    evidence: Mapping[str, object],
) -> None:
    validate_candidate_sha(candidate_sha)
    run_id = preflight_run.get("id")
    run_attempt = preflight_run.get("run_attempt")
    acceptance_run_id = acceptance_run.get("id")
    acceptance_run_attempt = acceptance_run.get("run_attempt")
    if not all(
        isinstance(value, int) and value > 0
        for value in (run_id, run_attempt, acceptance_run_id, acceptance_run_attempt)
    ):
        raise ValueError("selected workflow run identity is invalid")

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
            "read-only preflight evidence does not match candidate/run: "
            + ", ".join(sorted(mismatched))
        )
    comment_id = evidence.get("command_comment_id")
    if (
        not isinstance(comment_id, str)
        or not comment_id.isdecimal()
        or int(comment_id) <= 0
    ):
        raise ValueError("read-only preflight evidence has invalid command_comment_id")


def _parse_time(value: object, field: str) -> datetime:
    if not isinstance(value, str) or len(value) > 64:
        raise ValueError(f"invalid {field}")
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        return datetime.fromisoformat(normalized)
    except ValueError as error:
        raise ValueError(f"invalid {field}") from error


def verify_fresh_chain(
    quality_run: Mapping[str, object],
    acceptance_run: Mapping[str, object],
    acceptance_evidence: Mapping[str, object],
    preflight_run: Mapping[str, object],
    trigger_created_at: str,
) -> None:
    quality_id = quality_run.get("id")
    acceptance_id = acceptance_run.get("id")
    if not isinstance(quality_id, int) or quality_id <= 0:
        raise ValueError("Quality run identity is invalid")
    if not isinstance(acceptance_id, int) or acceptance_id <= 0:
        raise ValueError("acceptance run identity is invalid")
    if acceptance_evidence.get("candidate_quality_run_id") != str(quality_id):
        raise ValueError("acceptance authority is not chained to the selected Quality run")

    ordered = [
        _parse_time(quality_run.get("created_at"), "Quality created_at"),
        _parse_time(acceptance_run.get("created_at"), "acceptance created_at"),
        _parse_time(preflight_run.get("created_at"), "preflight created_at"),
        _parse_time(trigger_created_at, "readiness comment created_at"),
    ]
    if ordered != sorted(ordered):
        raise ValueError("item-19 authority chain is stale or out of order")


def build_admission_evidence(
    candidate_sha: str,
    quality_run: Mapping[str, object],
    acceptance_run: Mapping[str, object],
    preflight_run: Mapping[str, object],
    env: Mapping[str, str],
) -> dict[str, object]:
    validate_candidate_sha(candidate_sha)
    repository = env.get("GITHUB_REPOSITORY", "")
    run_id = env.get("GITHUB_RUN_ID", "")
    run_attempt = env.get("GITHUB_RUN_ATTEMPT", "")
    comment_id = env.get("COMMAND_COMMENT_ID", "")
    if repository != _CANONICAL_REPOSITORY:
        raise ValueError("workflow is not running in the canonical repository")
    for name, value in {
        "GITHUB_RUN_ID": run_id,
        "GITHUB_RUN_ATTEMPT": run_attempt,
        "COMMAND_COMMENT_ID": comment_id,
    }.items():
        if not value.isdecimal() or int(value) <= 0:
            raise ValueError(f"{name} must be a positive numeric identity")

    identities: dict[str, str] = {}
    for name, run in {
        "quality": quality_run,
        "acceptance": acceptance_run,
        "preflight": preflight_run,
    }.items():
        value = run.get("id")
        attempt = run.get("run_attempt")
        if not isinstance(value, int) or value <= 0:
            raise ValueError(f"{name} run identity is invalid")
        if not isinstance(attempt, int) or attempt <= 0:
            raise ValueError(f"{name} run attempt is invalid")
        identities[f"{name}_run_id"] = str(value)
        identities[f"{name}_run_attempt"] = str(attempt)

    return {
        "format_version": 1,
        "authority": "item19_pre_release_acceptance_lifecycle",
        "candidate_sha": candidate_sha,
        "repository": repository,
        "workflow_run_id": run_id,
        "workflow_run_attempt": run_attempt,
        "command_issue": _ITEM19_ISSUE,
        "command_comment_id": comment_id,
        **identities,
        "physical_acceptance_window_ready": True,
        "signing_continuity_gate_issue": _SIGNING_GATE_ISSUE,
        "signing_continuity_gate_closed": True,
        "scope": "acceptance",
        "environment": "acceptance-vultr",
        "final_production_authority": False,
        "production_environment_authorized": False,
        "phone_mutation_authorized": False,
        "provider_mutation_performed_at_admission": False,
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

    parse = subparsers.add_parser("parse-command")
    parse.add_argument("--body-env", required=True)

    quality = subparsers.add_parser("select-quality-run")
    quality.add_argument("--candidate-sha", required=True)
    quality.add_argument("--runs", type=Path, required=True)
    quality.add_argument("--output", type=Path, required=True)

    acceptance = subparsers.add_parser("select-acceptance-run")
    acceptance.add_argument("--candidate-sha", required=True)
    acceptance.add_argument("--runs", type=Path, required=True)
    acceptance.add_argument("--output", type=Path, required=True)

    preflight = subparsers.add_parser("select-preflight-run")
    preflight.add_argument("--candidate-sha", required=True)
    preflight.add_argument("--runs", type=Path, required=True)
    preflight.add_argument("--output", type=Path, required=True)

    verify = subparsers.add_parser("verify-gates")
    verify.add_argument("--candidate-sha", required=True)
    verify.add_argument("--main-branch", type=Path, required=True)
    verify.add_argument("--quality-run", type=Path, required=True)
    verify.add_argument("--candidate-evidence", type=Path, required=True)
    verify.add_argument("--acceptance-run", type=Path, required=True)
    verify.add_argument("--acceptance-evidence", type=Path, required=True)
    verify.add_argument("--preflight-run", type=Path, required=True)
    verify.add_argument("--preflight-evidence", type=Path, required=True)
    verify.add_argument("--signing-issue", type=Path, required=True)
    verify.add_argument("--output", type=Path, required=True)

    args = parser.parse_args()
    if args.command == "parse-command":
        print(parse_command(os.environ.get(args.body_env, "")))
        return 0

    if args.command == "select-quality-run":
        selected = select_quality_run(args.candidate_sha, _load_object(args.runs))
        _write_object(args.output, selected)
        print(selected["id"])
        return 0

    if args.command == "select-acceptance-run":
        selected = select_acceptance_run(args.candidate_sha, _load_object(args.runs))
        _write_object(args.output, selected)
        print(selected["id"])
        return 0

    if args.command == "select-preflight-run":
        selected = select_preflight_run(args.candidate_sha, _load_object(args.runs))
        _write_object(args.output, selected)
        print(selected["id"])
        return 0

    main_branch = _load_object(args.main_branch)
    quality_run = _load_object(args.quality_run)
    candidate_evidence = _load_object(args.candidate_evidence)
    acceptance_run = _load_object(args.acceptance_run)
    acceptance_evidence = _load_object(args.acceptance_evidence)
    preflight_run = _load_object(args.preflight_run)
    preflight_evidence = _load_object(args.preflight_evidence)
    signing_issue = _load_object(args.signing_issue)

    verify_main_branch(args.candidate_sha, main_branch)
    verify_candidate_evidence(args.candidate_sha, quality_run, candidate_evidence)
    verify_acceptance_evidence(args.candidate_sha, acceptance_run, acceptance_evidence)
    verify_preflight_evidence(
        args.candidate_sha, preflight_run, acceptance_run, preflight_evidence
    )
    verify_signing_gate(signing_issue)
    verify_fresh_chain(
        quality_run,
        acceptance_run,
        acceptance_evidence,
        preflight_run,
        os.environ.get("COMMAND_CREATED_AT", ""),
    )
    evidence = build_admission_evidence(
        args.candidate_sha,
        quality_run,
        acceptance_run,
        preflight_run,
        os.environ,
    )
    _write_object(args.output, evidence)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
