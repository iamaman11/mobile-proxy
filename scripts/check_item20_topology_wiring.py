#!/usr/bin/env python3
"""Protect Item 20 reusable boundaries after public orchestration workflow retirement."""

from __future__ import annotations

import json
from pathlib import Path

RETIREMENT = Path("contracts/operations/historical-public-acceptance-retirement-v1.json")
ITEM20 = Path("contracts/operations/item20-acceptance-v1.json")
HANDOFF = Path("contracts/operations/item20-private-handoff-v1.json")
HANDOFF_PRIMITIVE = Path("scripts/item20_private_handoff.py")
GITHUB_V2 = Path("contracts/operations/github-control-plane-v2.json")
TOPOLOGY_V2 = Path("contracts/operations/production-topology-v2.json")

EXPECTED_RETIRED = {
    ".github/workflows/item19-acceptance-lifecycle.yml",
    ".github/workflows/vultr-readonly-preflight.yml",
    ".github/workflows/item20-admission-readiness.yml",
    ".github/workflows/item20-session-orchestration.yml",
}


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
    retirement = _load(root, RETIREMENT, errors)
    item20 = _load(root, ITEM20, errors)
    handoff = _load(root, HANDOFF, errors)
    github_v2 = _load(root, GITHUB_V2, errors)
    topology_v2 = _load(root, TOPOLOGY_V2, errors)

    retired = retirement.get("retired_workflows")
    if retirement.get("status") != "protected_historical_non_executable" or not isinstance(retired, list) or set(retired) != EXPECTED_RETIRED:
        errors.append("historical public acceptance workflow retirement set differs")
    for workflow in EXPECTED_RETIRED:
        if (root / workflow).exists():
            errors.append(f"retired public acceptance workflow is executable again: {workflow}")

    authorization = item20.get("authorization")
    if authorization != {
        "endpoint_handoff_authorized": False,
        "final_production_authority": False,
        "live_execution_authorized": False,
        "phone_mutation_authorized": False,
        "provider_mutation_authorized": False,
    }:
        errors.append("retained Item 20 contract grants live or mutation authority")
    identity = item20.get("identity")
    if not isinstance(identity, dict) or identity.get("exact_equality_required") is not True:
        errors.append("retained Item 20 identity lost exact candidate/control-plane equality")
    historical = item20.get("historical_item19_proof")
    if not isinstance(historical, dict) or historical.get("candidate_sha") != "d151dbdd156279e32a5361d304c90f996bd2d565":
        errors.append("retained Item 20 contract lost immutable Item 19 historical identity")

    implementation = handoff.get("implementation")
    if not isinstance(implementation, dict):
        errors.append("Item 20 sealed handoff implementation contract is missing")
    else:
        for key in (
            "public_handoff_enabled",
            "private_phone_workflow_enabled",
            "private_secret_write_enabled",
            "workflow_dispatch_enabled",
            "live_execution_authorized",
        ):
            if implementation.get(key) is not False:
                errors.append(f"retained Item 20 handoff unexpectedly enables {key}")
    transport = handoff.get("transport")
    if not isinstance(transport, dict) or transport.get("plaintext_endpoint_in_dispatch_inputs") is not False or transport.get("sealed_ciphertext_in_dispatch_inputs") is not True:
        errors.append("retained Item 20 sealed handoff transport boundary differs")

    primitive = _read(root, HANDOFF_PRIMITIVE, errors)
    for token in (
        'find_library("sodium")',
        "crypto_box_seal",
        "crypto_box_seal_open",
        "crypto_scalarmult_base",
        "secrets.token_hex(16)",
        'seal.add_argument("--endpoint-file"',
        'unseal.add_argument("--endpoint-output"',
    ):
        if token not in primitive:
            errors.append(f"retained Item 20 sealed primitive is missing {token!r}")
    lowered = primitive.lower()
    for forbidden in (
        "subprocess.",
        "urllib.request",
        "requests.",
        "http.client",
        "socket.",
        "vultr_api_key",
        "vultr_ssh_private_key",
        "gh workflow run",
        "adb ",
        'add_argument("--endpoint"',
        "print(",
    ):
        if forbidden in lowered:
            errors.append(f"retained Item 20 sealed primitive contains live token {forbidden!r}")

    historical_surfaces = github_v2.get("historical_acceptance_surfaces")
    if not isinstance(historical_surfaces, dict) or historical_surfaces.get(
        "public_item19_item20_workflows"
    ) != "historical_or_development_only_not_product_release_or_runtime_deployment_authority":
        errors.append("GitHub v2 historical public acceptance classification differs")
    controller = github_v2.get("deployment_controller_repository")
    if (
        not isinstance(controller, dict)
        or controller.get("authority") != "deployment_controller"
        or controller.get("visibility") != "public"
    ):
        errors.append("Deployment Controller authority is not preserved")

    evidence = topology_v2.get("evidence")
    release_link = topology_v2.get("release_link")
    if not isinstance(evidence, dict) or evidence.get("historical_public_item19_item20_evidence") != "history_only_not_runtime_authority":
        errors.append("production topology v2 no longer treats public Item19/Item20 evidence as history only")
    if not isinstance(release_link, dict) or release_link.get("product_release_must_exist_before_deployment_admission") is not True:
        errors.append("production topology v2 lost Product Release before deployment ordering")

    return errors


def main() -> int:
    errors = check_repository(Path(__file__).resolve().parents[1])
    for error in errors:
        print(error)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
