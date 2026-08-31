#!/usr/bin/env python3
"""Fail closed when the protected Item 20 read-only readiness surface drifts."""

from __future__ import annotations

import json
from pathlib import Path


CONTRACT = Path("contracts/operations/item20-admission-readiness-v1.json")
WORKFLOW = Path(".github/workflows/item20-admission-readiness.yml")
SELECTOR = Path("scripts/select_item20_candidate_evidence.py")
TESTS = Path("scripts/tests/test_item20_admission_readiness.py")

_IMMUTABLE_CANDIDATE = "d151dbdd156279e32a5361d304c90f996bd2d565"

_EXPECTED_CONTRACT = {
    "authorization": {
        "endpoint_handoff_authorized": False,
        "final_production_authority": False,
        "live_execution_authorized": False,
        "phone_mutation_authorized": False,
        "provider_mutation_authorized": False,
    },
    "candidate_evidence_workflow": {
        "admission_core_wiring": "not_implemented",
        "artifact_selection": "candidate_specific_artifact_then_exact_control_plane_run",
        "candidate_sha": _IMMUTABLE_CANDIDATE,
        "control_plane_sha": "exact_current_protected_main",
        "output_artifact_name_template": "item20-admission-readiness-<control_plane_sha>",
        "selector": "scripts/select_item20_candidate_evidence.py",
        "status": "protected_read_only_candidate_evidence_wiring",
        "verifier": "scripts/verify_item20_candidate_evidence.py",
        "workflow": ".github/workflows/item20-admission-readiness.yml",
    },
    "canonical_repository": "iamaman11/mobile-proxy",
    "contract_version": 1,
    "execution_boundary": {
        "environment": "none",
        "executor": "github-hosted",
        "permissions": ["actions:read", "contents:read"],
        "phone_execution": False,
        "provider_api_execution": False,
        "provider_credentials": "forbidden",
        "trigger": "workflow_dispatch",
    },
    "forbidden": [
        "acceptance_or_preflight_workflow_dispatch_from_readiness",
        "provider_api_call_from_readiness",
        "provider_credentials_in_readiness",
        "provider_mutation_from_readiness",
        "phone_execution_from_readiness",
        "endpoint_handoff_from_readiness",
        "production_vultr_authority",
        "final_release_or_production_promotion",
        "public_provider_uuid_or_transport_endpoint_recording",
    ],
    "phone_signing_gate_issue": 115,
    "status": "protected_read_only_foundation_not_live_authority",
    "tracker_issue": 135,
}


def _read(root: Path, path: Path, errors: list[str]) -> str:
    try:
        return (root / path).read_text(encoding="utf-8")
    except OSError as error:
        errors.append(f"cannot read {path}: {error}")
        return ""


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


def check_repository(root: Path) -> list[str]:
    errors: list[str] = []
    contract = _load(root, CONTRACT, errors)
    workflow = _read(root, WORKFLOW, errors)
    selector = _read(root, SELECTOR, errors)
    tests = _read(root, TESTS, errors)

    if contract != _EXPECTED_CONTRACT:
        errors.append("Item 20 read-only admission-readiness contract differs from protected value")

    for required in (
        "name: Item 20 read-only admission readiness",
        "workflow_dispatch:",
        "actions: read",
        "contents: read",
        "runs-on: ubuntu-latest",
        "scripts/select_item20_candidate_evidence.py verify-contract",
        "scripts/select_item20_candidate_evidence.py select-artifact",
        "scripts/verify_item20_candidate_evidence.py",
        "vultr-acceptance-authority-$CANDIDATE_SHA",
        "vultr-readonly-preflight-$CANDIDATE_SHA",
        "item20-admission-readiness-${{ github.sha }}",
        "Provider credentials consumed by this workflow: false",
        "Provider API called by this workflow: false",
        "Provider mutation authorized: false",
        "Phone execution invoked: false",
        "Phone mutation authorized: false",
        "Endpoint handoff authorized: false",
        "Live execution authorized: false",
        "Final production authority: false",
    ):
        if required not in workflow:
            errors.append(f"Item 20 readiness workflow is missing protected token {required!r}")

    lowered_workflow = workflow.lower()
    for forbidden in (
        "environment: acceptance-vultr",
        "environment: production-vultr",
        "vultr_api_key",
        "vultr_ssh_private_key",
        "item20_phone_handoff_token",
        "item20_handoff_private_key_b64",
        "sealed_session_envelope",
        "self-hosted",
        "adb ",
        "/v2/instances",
        "gh workflow run",
        "actions/workflows/acceptance-authority.yml/dispatches",
        "actions/workflows/vultr-readonly-preflight.yml/dispatches",
        "curl --request post",
        "curl --request delete",
        "curl --request patch",
    ):
        if forbidden in lowered_workflow:
            errors.append(f"Item 20 readiness workflow contains forbidden live token {forbidden!r}")

    for required in (
        '_IMMUTABLE_CANDIDATE = "d151dbdd156279e32a5361d304c90f996bd2d565"',
        "def verify_readiness_contract(",
        "def select_artifact(",
        '"acceptance": "vultr-acceptance-authority"',
        '"preflight": "vultr-readonly-preflight"',
        'workflow_run.get("head_branch") != "main"',
        'workflow_run.get("head_sha") != control_plane_sha',
        'raise ValueError(f"no unexpired {kind} artifact binds exact candidate and control plane")',
    ):
        if required not in selector:
            errors.append(f"Item 20 readiness selector is missing protected token {required!r}")

    lowered_selector = selector.lower()
    for forbidden in (
        "subprocess.",
        "urllib.request",
        "requests.",
        "http.client",
        "socket.",
        "vultr_api_key",
        "vultr_ssh_private_key",
        "/v2/instances",
        "create_instance(",
        "delete_instance(",
        "adb ",
        "gh workflow run",
    ):
        if forbidden in lowered_selector:
            errors.append(f"Item 20 readiness selector contains forbidden I/O/live token {forbidden!r}")

    for required in (
        "class Item20AdmissionReadinessTests",
        "test_contract_is_exact_validation_only",
        "test_selector_uses_exact_candidate_then_control_plane",
        "test_selector_rejects_old_or_invalid_artifacts",
        "test_workflow_is_read_only_and_consumes_protected_verifier",
    ):
        if required not in tests:
            errors.append(f"Item 20 readiness regression coverage is missing {required!r}")

    return errors


def main() -> int:
    errors = check_repository(Path(__file__).resolve().parents[1])
    for error in errors:
        print(error)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
