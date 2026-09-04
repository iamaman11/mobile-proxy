#!/usr/bin/env python3
"""Protect historical Vultr preflight evidence after workflow retirement."""

from __future__ import annotations

import json
from pathlib import Path

CONTRACT = Path("contracts/operations/vultr-readonly-preflight-v1.json")
RETIREMENT = Path("contracts/operations/historical-public-acceptance-retirement-v1.json")
WORKFLOW = Path(".github/workflows/vultr-readonly-preflight.yml")
GITHUB_V2 = Path("contracts/operations/github-control-plane-v2.json")


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
    retirement = _load(root, RETIREMENT, errors)
    github_v2 = _load(root, GITHUB_V2, errors)

    if (root / WORKFLOW).exists():
        errors.append("retired Vultr read-only public workflow is executable again")
    retired = retirement.get("retired_workflows")
    if retirement.get("status") != "protected_historical_non_executable" or not isinstance(retired, list) or str(WORKFLOW) not in retired:
        errors.append("retirement contract does not bind Vultr read-only workflow")

    if contract.get("contract_version") != 1 or contract.get("canonical_repository") != "iamaman11/mobile-proxy":
        errors.append("historical Vultr read-only contract identity differs")
    if contract.get("authority") != "pre_release_acceptance_read_only":
        errors.append("historical Vultr preflight authority label differs")
    probe = contract.get("provider_probe")
    if probe != {
        "provider": "vultr",
        "method": "GET",
        "url": "https://api.vultr.com/v2/account",
        "response_body": "discarded",
        "response_metadata": "not_recorded",
        "allowed_api_calls": 1,
        "vm_lifecycle": "forbidden",
        "provider_mutation": "forbidden",
    }:
        errors.append("historical Vultr read-only probe evidence contract differs")
    separation = contract.get("authority_separation")
    if not isinstance(separation, dict) or separation.get("final_production_authority") is not False or separation.get("final_release_tag") != "forbidden":
        errors.append("historical Vultr preflight snapshot gained production authority")

    historical_surfaces = github_v2.get("historical_acceptance_surfaces")
    if not isinstance(historical_surfaces, dict) or historical_surfaces.get(
        "acceptance_vultr_environment"
    ) != "historical_acceptance_boundary_not_normal_production_deployment_authority":
        errors.append("GitHub v2 no longer classifies acceptance-vultr as historical")

    return errors


def main() -> int:
    errors = check_repository(Path(__file__).resolve().parents[1])
    for error in errors:
        print(error)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
