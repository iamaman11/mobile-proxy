#!/usr/bin/env python3
"""Fail closed if the retired public Item 20 readiness workflow returns."""

from __future__ import annotations

import json
from pathlib import Path

CONTRACT = Path("contracts/operations/item20-admission-readiness-v1.json")
RETIREMENT = Path("contracts/operations/historical-public-acceptance-retirement-v1.json")
WORKFLOW = Path(".github/workflows/item20-admission-readiness.yml")
SELECTOR = Path("scripts/select_item20_candidate_evidence.py")
TESTS = Path("scripts/tests/test_item20_admission_readiness.py")


def _load(root: Path, path: Path, errors: list[str]) -> dict[str, object]:
    try:
        value = json.loads((root / path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        errors.append(f"cannot load {path}: {error}")
        return {}
    if not isinstance(value, dict):
        errors.append(f"{path} root must be an object")
        return {}
    return value


def _read(root: Path, path: Path, errors: list[str]) -> str:
    try:
        return (root / path).read_text(encoding="utf-8")
    except OSError as error:
        errors.append(f"cannot read {path}: {error}")
        return ""


def check_repository(root: Path) -> list[str]:
    errors: list[str] = []
    contract = _load(root, CONTRACT, errors)
    retirement = _load(root, RETIREMENT, errors)
    selector = _read(root, SELECTOR, errors)
    tests = _read(root, TESTS, errors)

    if (root / WORKFLOW).exists():
        errors.append("retired Item 20 admission-readiness workflow is executable again")

    retired = retirement.get("retired_workflows")
    if retirement.get("status") != "protected_historical_non_executable" or not isinstance(retired, list) or str(WORKFLOW) not in retired:
        errors.append("retirement contract does not bind Item 20 admission-readiness as historical/non-executable")

    if contract.get("contract_version") != 1 or contract.get("canonical_repository") != "iamaman11/mobile-proxy":
        errors.append("historical Item 20 readiness contract identity differs")
    workflow_snapshot = contract.get("candidate_evidence_workflow")
    if not isinstance(workflow_snapshot, dict) or workflow_snapshot.get("workflow") != str(WORKFLOW):
        errors.append("historical Item 20 readiness snapshot lost workflow provenance")
    if not isinstance(workflow_snapshot, dict) or workflow_snapshot.get("candidate_control_plane_exact_equality_required") is not True:
        errors.append("historical Item 20 readiness snapshot lost same-SHA invariant")
    authorization = contract.get("authorization")
    if authorization != {
        "endpoint_handoff_authorized": False,
        "final_production_authority": False,
        "live_execution_authorized": False,
        "phone_mutation_authorized": False,
        "provider_mutation_authorized": False,
    }:
        errors.append("historical Item 20 readiness contract grants authority")

    for required in (
        "def verify_readiness_contract(",
        "def select_artifact(",
        "candidate_sha != control_plane_sha",
        '"acceptance": "vultr-acceptance-authority"',
        '"preflight": "vultr-readonly-preflight"',
        'workflow_run.get("head_branch") != "main"',
        'workflow_run.get("head_sha") != candidate_sha',
    ):
        if required not in selector:
            errors.append(f"retained Item 20 pure selector is missing {required!r}")
    lowered = selector.lower()
    for forbidden in (
        "subprocess.",
        "urllib.request",
        "requests.",
        "http.client",
        "socket.",
        "vultr_api_key",
        "vultr_ssh_private_key",
        "create_instance(",
        "delete_instance(",
        "adb ",
        "gh workflow run",
    ):
        if forbidden in lowered:
            errors.append(f"retained Item 20 selector gained external/live token {forbidden!r}")

    for required in (
        "class Item20AdmissionReadinessTests",
        "test_contract_snapshot_remains_validation_only",
        "test_selector_uses_same_sha_candidate_and_run",
        "test_selector_rejects_candidate_control_plane_mismatch",
        "test_retired_workflow_is_absent",
    ):
        if required not in tests:
            errors.append(f"Item 20 readiness retirement coverage is missing {required!r}")

    return errors


def main() -> int:
    errors = check_repository(Path(__file__).resolve().parents[1])
    for error in errors:
        print(error)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
