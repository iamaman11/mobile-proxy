#!/usr/bin/env python3
"""Verify one immutable pre-release acceptance candidate and write bounded evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from pathlib import Path
from typing import Mapping


_SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
_COMMAND_PATTERN = re.compile(r"^/accept-candidate ([0-9a-f]{40})$")
_CANONICAL_REPOSITORY = "iamaman11/mobile-proxy"
_QUALITY_WORKFLOW = "Quality"
_QUALITY_WORKFLOW_PATH = ".github/workflows/quality.yml"


def parse_command(body: str) -> str:
    if not body or len(body) > 128:
        raise ValueError("acceptance command is missing or unbounded")
    normalized = body.rstrip("\r\n")
    match = _COMMAND_PATTERN.fullmatch(normalized)
    if match is None:
        raise ValueError("acceptance command must contain one exact lowercase 40-character SHA")
    return match.group(1)


def validate_candidate_sha(candidate_sha: str) -> str:
    if not _SHA_PATTERN.fullmatch(candidate_sha):
        raise ValueError("candidate SHA must be one exact lowercase 40-character Git SHA")
    return candidate_sha


def select_quality_run(candidate_sha: str, payload: Mapping[str, object]) -> dict[str, object]:
    validate_candidate_sha(candidate_sha)
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

    distinct_run_ids = {int(run["id"]) for run in eligible}
    if len(distinct_run_ids) != 1:
        raise ValueError("candidate must have exactly one eligible canonical Quality push run")
    return eligible[0]


def verify_candidate_evidence(
    candidate_sha: str,
    quality_run: Mapping[str, object],
    evidence: Mapping[str, object],
) -> None:
    validate_candidate_sha(candidate_sha)
    run_id = quality_run.get("id")
    run_attempt = quality_run.get("run_attempt")
    if not isinstance(run_id, int) or not isinstance(run_attempt, int):
        raise ValueError("selected Quality run identity is invalid")

    expected_url = f"https://github.com/{_CANONICAL_REPOSITORY}/actions/runs/{run_id}"
    expected = {
        "format_version": 2,
        "candidate_sha": candidate_sha,
        "repository": _CANONICAL_REPOSITORY,
        "workflow": _QUALITY_WORKFLOW,
        "workflow_run_id": str(run_id),
        "workflow_run_attempt": str(run_attempt),
        "workflow_event": "push",
        "workflow_url": expected_url,
        "git_worktree_clean": True,
        "software_10_of_10_ready": True,
        "physical_phone_acceptance_required": True,
        "baseline_complete": False,
    }
    mismatched = [key for key, value in expected.items() if evidence.get(key) != value]
    if mismatched:
        raise ValueError(
            "release-candidate evidence does not match candidate/Quality run: "
            + ", ".join(sorted(mismatched))
        )
    checks = evidence.get("accepted_checks")
    if not isinstance(checks, list) or not checks or not all(isinstance(item, str) for item in checks):
        raise ValueError("release-candidate evidence accepted_checks is missing or invalid")


def _required(env: Mapping[str, str], name: str, maximum: int = 256) -> str:
    value = env.get(name, "")
    if not value or len(value) > maximum or any(ord(character) < 32 for character in value):
        raise ValueError(f"invalid or missing {name}")
    return value


def build_acceptance_evidence(
    candidate_sha: str,
    quality_run: Mapping[str, object],
    candidate_evidence_sha256: str,
    env: Mapping[str, str],
) -> dict[str, object]:
    validate_candidate_sha(candidate_sha)
    if not re.fullmatch(r"[0-9a-f]{64}", candidate_evidence_sha256):
        raise ValueError("candidate evidence digest must be lowercase SHA-256")

    repository = _required(env, "GITHUB_REPOSITORY")
    if repository != _CANONICAL_REPOSITORY:
        raise ValueError("acceptance workflow is not running in the canonical repository")
    workflow = _required(env, "GITHUB_WORKFLOW", 128)
    run_id = _required(env, "GITHUB_RUN_ID", 32)
    run_attempt = _required(env, "GITHUB_RUN_ATTEMPT", 16)
    comment_id = _required(env, "COMMAND_COMMENT_ID", 32)
    if not run_id.isdecimal() or not run_attempt.isdecimal() or not comment_id.isdecimal():
        raise ValueError("acceptance workflow identity must be numeric")

    quality_run_id = quality_run.get("id")
    quality_run_attempt = quality_run.get("run_attempt")
    if not isinstance(quality_run_id, int) or not isinstance(quality_run_attempt, int):
        raise ValueError("selected Quality run identity is invalid")

    return {
        "format_version": 1,
        "authority": "pre_release_acceptance",
        "candidate_sha": candidate_sha,
        "repository": repository,
        "executor": "github-hosted",
        "acceptance_workflow": workflow,
        "acceptance_workflow_run_id": run_id,
        "acceptance_workflow_run_attempt": run_attempt,
        "command_issue": 90,
        "command_comment_id": comment_id,
        "candidate_quality_run_id": str(quality_run_id),
        "candidate_quality_run_attempt": str(quality_run_attempt),
        "candidate_evidence_sha256": candidate_evidence_sha256,
        "final_production_authority": False,
        "production_environment_authorized": False,
        "final_release_tag_created": False,
        "vultr_api_access_performed": False,
        "vm_mutation_performed": False,
        "phone_mutation_performed": False,
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


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    parse = subparsers.add_parser("parse-command")
    parse.add_argument("--body-env", required=True)

    select = subparsers.add_parser("select-run")
    select.add_argument("--candidate-sha", required=True)
    select.add_argument("--runs", type=Path, required=True)
    select.add_argument("--output", type=Path, required=True)

    verify = subparsers.add_parser("verify")
    verify.add_argument("--candidate-sha", required=True)
    verify.add_argument("--selected-run", type=Path, required=True)
    verify.add_argument("--candidate-evidence", type=Path, required=True)
    verify.add_argument("--output", type=Path, required=True)

    args = parser.parse_args()
    if args.command == "parse-command":
        print(parse_command(os.environ.get(args.body_env, "")))
        return 0

    if args.command == "select-run":
        selected = select_quality_run(args.candidate_sha, _load_object(args.runs))
        _write_object(args.output, selected)
        print(selected["id"])
        return 0

    quality_run = _load_object(args.selected_run)
    candidate_evidence = _load_object(args.candidate_evidence)
    verify_candidate_evidence(args.candidate_sha, quality_run, candidate_evidence)
    acceptance = build_acceptance_evidence(
        args.candidate_sha,
        quality_run,
        _sha256(args.candidate_evidence),
        os.environ,
    )
    _write_object(args.output, acceptance)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
