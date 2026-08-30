#!/usr/bin/env python3
"""Verify immutable acceptance authority before bounded Vultr read-only preflight."""

from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
from typing import Mapping


_SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
_COMMAND_PATTERN = re.compile(r"^/vultr-readonly-preflight ([0-9a-f]{40})$")
_CANONICAL_REPOSITORY = "iamaman11/mobile-proxy"
_ACCEPTANCE_WORKFLOW = "Vultr acceptance authority"
_ACCEPTANCE_WORKFLOW_PATH = ".github/workflows/acceptance-authority.yml"


def parse_command(body: str) -> str:
    if not body or len(body) > 160:
        raise ValueError("Vultr read-only preflight command is missing or unbounded")
    normalized = body.rstrip("\r\n")
    match = _COMMAND_PATTERN.fullmatch(normalized)
    if match is None:
        raise ValueError("Vultr read-only preflight command must contain one exact lowercase 40-character SHA")
    return match.group(1)


def validate_candidate_sha(candidate_sha: str) -> str:
    if not _SHA_PATTERN.fullmatch(candidate_sha):
        raise ValueError("candidate SHA must be one exact lowercase 40-character Git SHA")
    return candidate_sha


def select_acceptance_run(candidate_sha: str, payload: Mapping[str, object]) -> dict[str, object]:
    validate_candidate_sha(candidate_sha)
    runs = payload.get("workflow_runs")
    if not isinstance(runs, list):
        raise ValueError("Actions response is missing workflow_runs")

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
                "name": _ACCEPTANCE_WORKFLOW,
                "path": _ACCEPTANCE_WORKFLOW_PATH,
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
        raise ValueError("candidate has no successful immutable acceptance-authority run")
    return max(eligible, key=lambda run: (int(run["id"]), int(run["run_attempt"])))


def verify_acceptance_evidence(
    candidate_sha: str,
    acceptance_run: Mapping[str, object],
    evidence: Mapping[str, object],
) -> None:
    validate_candidate_sha(candidate_sha)
    run_id = acceptance_run.get("id")
    run_attempt = acceptance_run.get("run_attempt")
    if not isinstance(run_id, int) or not isinstance(run_attempt, int):
        raise ValueError("selected acceptance run identity is invalid")

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
            "acceptance-authority evidence does not match candidate/run: "
            + ", ".join(sorted(mismatched))
        )
    for name in ("command_comment_id", "candidate_quality_run_id", "candidate_quality_run_attempt"):
        value = evidence.get(name)
        if not isinstance(value, str) or not value.isdecimal() or int(value) <= 0:
            raise ValueError(f"acceptance-authority evidence has invalid {name}")


def _required(env: Mapping[str, str], name: str, maximum: int = 256) -> str:
    value = env.get(name, "")
    if not value or len(value) > maximum or any(ord(character) < 32 for character in value):
        raise ValueError(f"invalid or missing {name}")
    return value


def build_preflight_evidence(candidate_sha: str, env: Mapping[str, str]) -> dict[str, object]:
    validate_candidate_sha(candidate_sha)
    repository = _required(env, "GITHUB_REPOSITORY")
    if repository != _CANONICAL_REPOSITORY:
        raise ValueError("Vultr read-only preflight is not running in the canonical repository")

    workflow = _required(env, "GITHUB_WORKFLOW", 128)
    run_id = _required(env, "GITHUB_RUN_ID", 32)
    run_attempt = _required(env, "GITHUB_RUN_ATTEMPT", 16)
    comment_id = _required(env, "COMMAND_COMMENT_ID", 32)
    acceptance_run_id = _required(env, "ACCEPTANCE_AUTHORITY_RUN_ID", 32)
    acceptance_run_attempt = _required(env, "ACCEPTANCE_AUTHORITY_RUN_ATTEMPT", 16)
    for name, value in {
        "GITHUB_RUN_ID": run_id,
        "GITHUB_RUN_ATTEMPT": run_attempt,
        "COMMAND_COMMENT_ID": comment_id,
        "ACCEPTANCE_AUTHORITY_RUN_ID": acceptance_run_id,
        "ACCEPTANCE_AUTHORITY_RUN_ATTEMPT": acceptance_run_attempt,
    }.items():
        if not value.isdecimal() or int(value) <= 0:
            raise ValueError(f"{name} must be a positive numeric identity")

    return {
        "format_version": 1,
        "authority": "pre_release_acceptance_read_only",
        "candidate_sha": candidate_sha,
        "repository": repository,
        "executor": "github-hosted",
        "environment": "acceptance-vultr",
        "workflow": workflow,
        "workflow_run_id": run_id,
        "workflow_run_attempt": run_attempt,
        "command_issue": 90,
        "command_comment_id": comment_id,
        "acceptance_authority_run_id": acceptance_run_id,
        "acceptance_authority_run_attempt": acceptance_run_attempt,
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


def _load_object(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"cannot load JSON evidence {path}: {error}") from error
    if not isinstance(value, dict):
        raise ValueError(f"JSON evidence must be an object: {path}")
    return value


def _write_object(path: Path, value: Mapping[str, object]) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    parse = subparsers.add_parser("parse-command")
    parse.add_argument("--body-env", required=True)

    select = subparsers.add_parser("select-run")
    select.add_argument("--candidate-sha", required=True)
    select.add_argument("--runs", type=Path, required=True)
    select.add_argument("--output", type=Path, required=True)

    verify = subparsers.add_parser("verify-acceptance")
    verify.add_argument("--candidate-sha", required=True)
    verify.add_argument("--selected-run", type=Path, required=True)
    verify.add_argument("--acceptance-evidence", type=Path, required=True)

    build = subparsers.add_parser("build-evidence")
    build.add_argument("--candidate-sha", required=True)
    build.add_argument("--output", type=Path, required=True)

    args = parser.parse_args()
    if args.command == "parse-command":
        print(parse_command(os.environ.get(args.body_env, "")))
        return 0
    if args.command == "select-run":
        selected = select_acceptance_run(args.candidate_sha, _load_object(args.runs))
        _write_object(args.output, selected)
        print(selected["id"])
        return 0
    if args.command == "verify-acceptance":
        verify_acceptance_evidence(
            args.candidate_sha,
            _load_object(args.selected_run),
            _load_object(args.acceptance_evidence),
        )
        return 0

    _write_object(args.output, build_preflight_evidence(args.candidate_sha, os.environ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
