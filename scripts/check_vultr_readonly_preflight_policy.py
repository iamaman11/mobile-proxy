#!/usr/bin/env python3
"""Enforce the bounded Vultr read-only acceptance preflight contract."""

from __future__ import annotations

import json
from pathlib import Path


CONTRACT = Path("contracts/operations/vultr-readonly-preflight-v1.json")
WORKFLOW = Path(".github/workflows/vultr-readonly-preflight.yml")
GITHUB_CONTRACT = Path("contracts/operations/github-control-plane-v1.json")


def check_repository(root: Path) -> list[str]:
    errors: list[str] = []
    try:
        contract = json.loads((root / CONTRACT).read_text(encoding="utf-8"))
        github = json.loads((root / GITHUB_CONTRACT).read_text(encoding="utf-8"))
        workflow = (root / WORKFLOW).read_text(encoding="utf-8")
    except (OSError, json.JSONDecodeError) as error:
        return [f"cannot load Vultr read-only preflight policy: {error}"]

    if contract.get("authority") != "pre_release_acceptance_read_only":
        errors.append("Vultr read-only preflight authority is not pre-release read-only")
    execution = contract.get("execution")
    if not isinstance(execution, dict) or execution.get("environment") != "acceptance-vultr":
        errors.append("Vultr read-only preflight must use acceptance-vultr")
    probe = contract.get("provider_probe")
    if not isinstance(probe, dict) or probe != {
        "provider": "vultr",
        "method": "GET",
        "url": "https://api.vultr.com/v2/account",
        "response_body": "discarded",
        "response_metadata": "not_recorded",
        "allowed_api_calls": 1,
        "vm_lifecycle": "forbidden",
        "provider_mutation": "forbidden",
    }:
        errors.append("Vultr provider preflight scope is not exact read-only /v2/account")
    separation = contract.get("authority_separation")
    if not isinstance(separation, dict) or any(
        separation.get(key) != value
        for key, value in {
            "acceptance_environment_name": "acceptance-vultr",
            "production_environment_name": "production-vultr",
            "environments_must_differ": True,
            "final_release_tag": "forbidden",
            "final_production_authority": False,
        }.items()
    ):
        errors.append("Vultr acceptance and final production authority are not separated")

    if github.get("vultr_readonly_preflight_contract") != str(CONTRACT):
        errors.append("GitHub control-plane contract does not bind Vultr read-only preflight")
    environment = github.get("acceptance_vultr_environment")
    if not isinstance(environment, dict) or any(
        environment.get(key) != value
        for key, value in {
            "name": "acceptance-vultr",
            "authority": "pre_release_acceptance_read_only",
            "entry_workflow": str(WORKFLOW),
            "allowed_provider_api": "GET /v2/account only",
            "response_body_recording": "forbidden",
            "vm_lifecycle": "forbidden",
            "provider_mutation": "forbidden",
            "final_production_authority": False,
            "executor": "github-hosted",
        }.items()
    ):
        errors.append("GitHub acceptance-vultr boundary differs from the read-only contract")
    if isinstance(environment, dict) and environment.get("required_secret_names") != [
        "VULTR_API_KEY",
        "VULTR_SSH_PRIVATE_KEY",
    ]:
        errors.append("acceptance-vultr secret names differ from the contract")

    required_workflow = (
        "github.event.issue.number == 90",
        "github.event.comment.user.login == github.repository_owner",
        "startsWith(github.event.comment.body, '/vultr-readonly-preflight ')",
        "runs-on: ubuntu-latest",
        "environment: acceptance-vultr",
        "vultr-acceptance-authority-",
        "verify_vultr_readonly_preflight.py",
        "--request GET",
        "--output /dev/null",
        "https://api.vultr.com/v2/account",
    )
    if any(token not in workflow for token in required_workflow):
        errors.append("Vultr read-only workflow is missing a required immutable/read-only control")
    forbidden_workflow = (
        "environment: production-vultr",
        "runs-on: self-hosted",
        "/v2/instances",
        "/v2/snapshots",
        "--request POST",
        "--request PUT",
        "--request PATCH",
        "--request DELETE",
        "adb ",
        "gcloud",
    )
    if any(token in workflow for token in forbidden_workflow):
        errors.append("Vultr read-only workflow contains production, mutation, or phone authority")
    if workflow.count("https://api.vultr.com/v2/account") != 1:
        errors.append("Vultr read-only workflow must contain exactly one provider account endpoint")

    return errors


def main() -> int:
    errors = check_repository(Path(__file__).resolve().parents[1])
    for error in errors:
        print(error)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
