#!/usr/bin/env python3
"""Pure artifact selector for Item 20 read-only admission readiness.

The selector performs no GitHub, provider, network, or phone I/O. A caller supplies
an Actions artifact-list JSON response. Selection is candidate-specific first and
then requires the artifact's workflow-run binding to match the exact protected
control-plane SHA. The full protected verifier independently validates the selected
run and downloaded evidence afterwards.
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
_CONTRACT_STATUS = "protected_read_only_foundation_not_live_authority"
_SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
_DIGEST_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
_KIND_PREFIX = {
    "acceptance": "vultr-acceptance-authority",
    "preflight": "vultr-readonly-preflight",
}


def validate_sha(value: object, kind: str) -> str:
    if not isinstance(value, str) or _SHA_PATTERN.fullmatch(value) is None:
        raise ValueError(f"{kind} SHA must be an exact lowercase 40-character hexadecimal identity")
    return value


def _positive_int(value: object, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
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


def verify_readiness_contract(contract: Mapping[str, object]) -> None:
    expected = {
        "contract_version": 1,
        "status": _CONTRACT_STATUS,
        "canonical_repository": _CANONICAL_REPOSITORY,
        "tracker_issue": 135,
        "phone_signing_gate_issue": 115,
    }
    if any(contract.get(key) != value for key, value in expected.items()):
        raise ValueError("Item 20 admission-readiness contract identity differs")

    workflow = contract.get("candidate_evidence_workflow")
    if not isinstance(workflow, dict) or workflow != {
        "status": "protected_read_only_candidate_evidence_wiring",
        "workflow": ".github/workflows/item20-admission-readiness.yml",
        "selector": "scripts/select_item20_candidate_evidence.py",
        "verifier": "scripts/verify_item20_candidate_evidence.py",
        "candidate_sha": _IMMUTABLE_CANDIDATE,
        "control_plane_sha": "exact_current_protected_main",
        "artifact_selection": "candidate_specific_artifact_then_exact_control_plane_run",
        "output_artifact_name_template": "item20-admission-readiness-<control_plane_sha>",
        "admission_core_wiring": "not_implemented",
    }:
        raise ValueError("Item 20 candidate-evidence readiness wiring differs")

    boundary = contract.get("execution_boundary")
    if not isinstance(boundary, dict) or boundary != {
        "trigger": "workflow_dispatch",
        "executor": "github-hosted",
        "environment": "none",
        "permissions": ["actions:read", "contents:read"],
        "provider_credentials": "forbidden",
        "provider_api_execution": False,
        "phone_execution": False,
    }:
        raise ValueError("Item 20 admission-readiness execution boundary differs")

    authorization = contract.get("authorization")
    if not isinstance(authorization, dict) or authorization != {
        "provider_mutation_authorized": False,
        "phone_mutation_authorized": False,
        "endpoint_handoff_authorized": False,
        "live_execution_authorized": False,
        "final_production_authority": False,
    }:
        raise ValueError("Item 20 admission-readiness contract grants live authority")

    forbidden = contract.get("forbidden")
    if forbidden != [
        "acceptance_or_preflight_workflow_dispatch_from_readiness",
        "provider_api_call_from_readiness",
        "provider_credentials_in_readiness",
        "provider_mutation_from_readiness",
        "phone_execution_from_readiness",
        "endpoint_handoff_from_readiness",
        "production_vultr_authority",
        "final_release_or_production_promotion",
        "public_provider_uuid_or_transport_endpoint_recording",
    ]:
        raise ValueError("Item 20 admission-readiness forbidden boundary differs")


def select_artifact(
    kind: str,
    candidate_sha: str,
    control_plane_sha: str,
    payload: Mapping[str, object],
) -> dict[str, object]:
    candidate_sha = validate_sha(candidate_sha, "candidate")
    control_plane_sha = validate_sha(control_plane_sha, "control-plane")
    if candidate_sha != _IMMUTABLE_CANDIDATE:
        raise ValueError("candidate SHA does not match the protected Item 19 closeout")
    prefix = _KIND_PREFIX.get(kind)
    if prefix is None:
        raise ValueError("unsupported Item 20 evidence artifact kind")

    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, list):
        raise ValueError("Actions response is missing artifacts")

    eligible: list[tuple[datetime, dict[str, object]]] = []
    for raw in artifacts:
        if not isinstance(raw, dict):
            continue
        if raw.get("name") != f"{prefix}-{candidate_sha}" or raw.get("expired") is not False:
            continue
        try:
            _positive_int(raw.get("id"), f"{kind} artifact id")
            _positive_int(raw.get("size_in_bytes"), f"{kind} artifact size")
            created = _parse_time(raw.get("created_at"), f"{kind} artifact created_at")
        except ValueError:
            continue
        digest = raw.get("digest")
        if not isinstance(digest, str) or _DIGEST_PATTERN.fullmatch(digest) is None:
            continue
        workflow_run = raw.get("workflow_run")
        if not isinstance(workflow_run, dict):
            continue
        try:
            _positive_int(workflow_run.get("id"), f"{kind} workflow-run id")
        except ValueError:
            continue
        if workflow_run.get("head_branch") != "main" or workflow_run.get("head_sha") != control_plane_sha:
            continue
        eligible.append((created, dict(raw)))

    if not eligible:
        raise ValueError(f"no unexpired {kind} artifact binds exact candidate and control plane")

    _, selected = max(
        eligible,
        key=lambda item: (item[0], int(item[1]["id"])),
    )
    return selected


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

    contract = subparsers.add_parser("verify-contract")
    contract.add_argument("--contract", type=Path, required=True)

    select = subparsers.add_parser("select-artifact")
    select.add_argument("--kind", choices=sorted(_KIND_PREFIX), required=True)
    select.add_argument("--candidate-sha", required=True)
    select.add_argument("--control-plane-sha", required=True)
    select.add_argument("--artifacts", type=Path, required=True)
    select.add_argument("--output", type=Path, required=True)

    args = parser.parse_args()
    if args.command == "verify-contract":
        verify_readiness_contract(_load_object(args.contract))
        return 0

    selected = select_artifact(
        args.kind,
        args.candidate_sha,
        args.control_plane_sha,
        _load_object(args.artifacts),
    )
    _write_object(args.output, selected)
    workflow_run = selected["workflow_run"]
    assert isinstance(workflow_run, dict)
    print(workflow_run["id"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
