#!/usr/bin/env python3
"""Pure selector/verifier for an Item 20 admission-readiness artifact.

This module performs no GitHub, provider, network, or phone I/O. Callers provide
Actions artifact metadata, the selected workflow-run metadata, and the downloaded
bounded JSON evidence. It grants no provider, phone, handoff, live, or production
authority.
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
_READINESS_WORKFLOW = "Item 20 read-only admission readiness"
_READINESS_WORKFLOW_PATH = ".github/workflows/item20-admission-readiness.yml"
_READINESS_AUTHORITY = "item20_fresh_candidate_evidence_verification"
_SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
_DIGEST_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")

_EVIDENCE_KEYS = {
    "format_version",
    "authority",
    "repository",
    "candidate_sha",
    "control_plane_sha",
    "control_plane_quality_run_id",
    "candidate_quality_run_id",
    "candidate_quality_run_attempt",
    "acceptance_authority_run_id",
    "acceptance_authority_artifact_id",
    "acceptance_authority_artifact_digest",
    "vultr_readonly_preflight_run_id",
    "vultr_readonly_preflight_artifact_id",
    "vultr_readonly_preflight_artifact_digest",
    "candidate_control_plane_separation_verified",
    "fresh_acceptance_authority_verified",
    "fresh_vultr_readonly_preflight_verified",
    "provider_probe_read_only_verified",
    "provider_mutation_authorized",
    "phone_mutation_authorized",
    "endpoint_handoff_authorized",
    "live_execution_authorized",
    "final_production_authority",
    "transport_endpoint_recorded",
    "provider_identifier_recorded",
    "secret_derived_identifier_recorded",
}


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


def _artifact_name(control_plane_sha: str) -> str:
    return f"item20-admission-readiness-{control_plane_sha}"


def select_readiness_artifact(
    candidate_sha: str,
    control_plane_sha: str,
    payload: Mapping[str, object],
) -> dict[str, object]:
    candidate_sha = validate_sha(candidate_sha, "candidate")
    control_plane_sha = validate_sha(control_plane_sha, "control-plane")
    if candidate_sha != _IMMUTABLE_CANDIDATE:
        raise ValueError("candidate SHA does not match the protected Item 19 closeout")

    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, list):
        raise ValueError("Actions response is missing artifacts")

    eligible: list[tuple[datetime, dict[str, object]]] = []
    for raw in artifacts:
        if not isinstance(raw, dict):
            continue
        if raw.get("name") != _artifact_name(control_plane_sha) or raw.get("expired") is not False:
            continue
        try:
            _positive_int(raw.get("id"), "readiness artifact id")
            _positive_int(raw.get("size_in_bytes"), "readiness artifact size")
            created = _parse_time(raw.get("created_at"), "readiness artifact created_at")
        except ValueError:
            continue
        digest = raw.get("digest")
        if not isinstance(digest, str) or _DIGEST_PATTERN.fullmatch(digest) is None:
            continue
        workflow_run = raw.get("workflow_run")
        if not isinstance(workflow_run, dict):
            continue
        try:
            _positive_int(workflow_run.get("id"), "readiness workflow-run id")
        except ValueError:
            continue
        if workflow_run.get("head_branch") != "main" or workflow_run.get("head_sha") != control_plane_sha:
            continue
        eligible.append((created, dict(raw)))

    if not eligible:
        raise ValueError("no unexpired readiness artifact binds exact candidate/control plane")

    _, selected = max(eligible, key=lambda item: (item[0], int(item[1]["id"])))
    return selected


def verify_readiness_run(
    control_plane_sha: str,
    artifact: Mapping[str, object],
    run: Mapping[str, object],
) -> None:
    control_plane_sha = validate_sha(control_plane_sha, "control-plane")
    repository = run.get("repository")
    if not isinstance(repository, dict) or repository.get("full_name") != _CANONICAL_REPOSITORY:
        raise ValueError("readiness run is not from the canonical repository")

    expected = {
        "name": _READINESS_WORKFLOW,
        "path": _READINESS_WORKFLOW_PATH,
        "event": "workflow_dispatch",
        "head_branch": "main",
        "head_sha": control_plane_sha,
        "status": "completed",
        "conclusion": "success",
    }
    if any(run.get(key) != value for key, value in expected.items()):
        raise ValueError("readiness run does not match exact protected control plane")

    run_id = _positive_int(run.get("id"), "readiness run id")
    _positive_int(run.get("run_attempt"), "readiness run attempt")
    _parse_time(run.get("created_at"), "readiness run created_at")

    if artifact.get("name") != _artifact_name(control_plane_sha) or artifact.get("expired") is not False:
        raise ValueError("readiness artifact identity differs")
    _positive_int(artifact.get("id"), "readiness artifact id")
    _positive_int(artifact.get("size_in_bytes"), "readiness artifact size")
    digest = artifact.get("digest")
    if not isinstance(digest, str) or _DIGEST_PATTERN.fullmatch(digest) is None:
        raise ValueError("readiness artifact digest is missing or invalid")
    _parse_time(artifact.get("created_at"), "readiness artifact created_at")

    workflow_run = artifact.get("workflow_run")
    if not isinstance(workflow_run, dict) or any(
        workflow_run.get(key) != value
        for key, value in {"id": run_id, "head_branch": "main", "head_sha": control_plane_sha}.items()
    ):
        raise ValueError("readiness artifact is not bound to the exact readiness run")


def verify_readiness_evidence(
    candidate_sha: str,
    control_plane_sha: str,
    control_plane_quality_run_id: int,
    evidence: Mapping[str, object],
) -> None:
    candidate_sha = validate_sha(candidate_sha, "candidate")
    control_plane_sha = validate_sha(control_plane_sha, "control-plane")
    if candidate_sha != _IMMUTABLE_CANDIDATE:
        raise ValueError("candidate SHA does not match the protected Item 19 closeout")
    quality_id = _positive_int(control_plane_quality_run_id, "control-plane Quality run id")

    if set(evidence) != _EVIDENCE_KEYS:
        missing = sorted(_EVIDENCE_KEYS - set(evidence))
        unexpected = sorted(set(evidence) - _EVIDENCE_KEYS)
        raise ValueError(
            "readiness evidence schema differs; missing="
            + ",".join(missing)
            + "; unexpected="
            + ",".join(unexpected)
        )

    expected_identity = {
        "format_version": 1,
        "authority": _READINESS_AUTHORITY,
        "repository": _CANONICAL_REPOSITORY,
        "candidate_sha": candidate_sha,
        "control_plane_sha": control_plane_sha,
        "control_plane_quality_run_id": str(quality_id),
    }
    if any(evidence.get(key) != value for key, value in expected_identity.items()):
        raise ValueError("readiness evidence does not bind exact candidate/control-plane Quality identity")

    for field in (
        "candidate_quality_run_id",
        "candidate_quality_run_attempt",
        "acceptance_authority_run_id",
        "acceptance_authority_artifact_id",
        "vultr_readonly_preflight_run_id",
        "vultr_readonly_preflight_artifact_id",
    ):
        _positive_decimal(evidence.get(field), field)
    for field in (
        "acceptance_authority_artifact_digest",
        "vultr_readonly_preflight_artifact_digest",
    ):
        digest = evidence.get(field)
        if not isinstance(digest, str) or _DIGEST_PATTERN.fullmatch(digest) is None:
            raise ValueError(f"invalid {field}")

    for field in (
        "candidate_control_plane_separation_verified",
        "fresh_acceptance_authority_verified",
        "fresh_vultr_readonly_preflight_verified",
        "provider_probe_read_only_verified",
    ):
        if evidence.get(field) is not True:
            raise ValueError(f"readiness evidence did not verify {field}")

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
            raise ValueError(f"readiness evidence violates validation-only boundary: {field}")


def verify_consumption(
    candidate_sha: str,
    control_plane_sha: str,
    control_plane_quality_run_id: int,
    artifact: Mapping[str, object],
    run: Mapping[str, object],
    evidence: Mapping[str, object],
) -> dict[str, object]:
    verify_readiness_run(control_plane_sha, artifact, run)
    verify_readiness_evidence(candidate_sha, control_plane_sha, control_plane_quality_run_id, evidence)
    return {
        "format_version": 1,
        "authority": "item20_readiness_artifact_validation",
        "repository": _CANONICAL_REPOSITORY,
        "candidate_sha": candidate_sha,
        "control_plane_sha": control_plane_sha,
        "control_plane_quality_run_id": str(control_plane_quality_run_id),
        "readiness_workflow_run_id": str(run["id"]),
        "readiness_artifact_id": str(artifact["id"]),
        "readiness_artifact_digest": artifact["digest"],
        "fresh_acceptance_authority_verified": True,
        "fresh_vultr_readonly_preflight_verified": True,
        "provider_probe_read_only_verified": True,
        "provider_mutation_authorized": False,
        "phone_mutation_authorized": False,
        "endpoint_handoff_authorized": False,
        "live_execution_authorized": False,
        "final_production_authority": False,
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

    select = subparsers.add_parser("select-artifact")
    select.add_argument("--candidate-sha", required=True)
    select.add_argument("--control-plane-sha", required=True)
    select.add_argument("--artifacts", type=Path, required=True)
    select.add_argument("--output", type=Path, required=True)

    verify = subparsers.add_parser("verify")
    verify.add_argument("--candidate-sha", required=True)
    verify.add_argument("--control-plane-sha", required=True)
    verify.add_argument("--control-plane-quality-run-id", type=int, required=True)
    verify.add_argument("--artifact", type=Path, required=True)
    verify.add_argument("--run", type=Path, required=True)
    verify.add_argument("--evidence", type=Path, required=True)
    verify.add_argument("--output", type=Path, required=True)

    args = parser.parse_args()
    if args.command == "select-artifact":
        selected = select_readiness_artifact(
            args.candidate_sha,
            args.control_plane_sha,
            _load_object(args.artifacts),
        )
        _write_object(args.output, selected)
        workflow_run = selected["workflow_run"]
        assert isinstance(workflow_run, dict)
        print(workflow_run["id"])
        return 0

    result = verify_consumption(
        args.candidate_sha,
        args.control_plane_sha,
        args.control_plane_quality_run_id,
        _load_object(args.artifact),
        _load_object(args.run),
        _load_object(args.evidence),
    )
    _write_object(args.output, result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
