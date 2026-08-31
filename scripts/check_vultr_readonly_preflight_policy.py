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

    acceptance = contract.get("acceptance_evidence")
    expected_selection = {
        "strategy": "candidate_specific_artifact_then_exact_control_plane_run",
        "required_artifact_expired": False,
        "required_artifact_digest": "sha256",
        "required_artifact_run_branch": "main",
        "required_artifact_run_head_sha": "control_plane_sha",
        "candidate_sha_equals_control_plane_sha": False,
    }
    if not isinstance(acceptance, dict) or acceptance.get("selection") != expected_selection:
        errors.append("Vultr read-only preflight does not protect candidate/artifact/control-plane selection")

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
    if not isinstance(environment, dict):
        errors.append("GitHub acceptance-vultr credential boundary is missing")
    else:
        expected_boundary = {
            "name": "acceptance-vultr",
            "authority": "pre_release_acceptance_credential_boundary_not_final_production_authority",
            "required_precondition": "verified_vultr_acceptance_authority_artifact_for_exact_candidate_sha",
            "executor": "github-hosted",
            "final_production_authority": False,
        }
        if any(environment.get(key) != value for key, value in expected_boundary.items()):
            errors.append("GitHub acceptance-vultr credential boundary differs from the protected contract")
        if environment.get("required_secret_names") != [
            "VULTR_API_KEY",
            "VULTR_SSH_PRIVATE_KEY",
        ]:
            errors.append("acceptance-vultr secret names differ from the contract")

        capabilities = environment.get("workflow_capabilities")
        readonly = capabilities.get("readonly_preflight") if isinstance(capabilities, dict) else None
        if readonly != {
            "workflow": str(WORKFLOW),
            "allowed_provider_api": ["GET /v2/account"],
            "response_body_recording": "forbidden",
            "vm_lifecycle": False,
            "provider_mutation": False,
        }:
            errors.append("GitHub acceptance-vultr read-only capability differs from the read-only contract")

        for legacy_flat_capability in (
            "entry_workflow",
            "allowed_provider_api",
            "response_body_recording",
            "vm_lifecycle",
            "provider_mutation",
        ):
            if legacy_flat_capability in environment:
                errors.append(
                    "GitHub acceptance-vultr must define provider capability per workflow, not as a flat environment authority"
                )
                break

    required_workflow = (
        "github.event.issue.number == 90",
        "github.event.comment.user.login == github.repository_owner",
        "startsWith(github.event.comment.body, '/vultr-readonly-preflight ')",
        "runs-on: ubuntu-latest",
        "environment: acceptance-vultr",
        "actions/artifacts?name=vultr-acceptance-authority-$CANDIDATE_SHA&per_page=100",
        "actions/runs/$run_id",
        "actions/artifacts/$ACCEPTANCE_ARTIFACT_ID/zip",
        "select-artifact",
        "--control-plane-sha \"$CONTROL_PLANE_SHA\"",
        "--selected-artifact selected-acceptance-artifact.json",
        "verify_vultr_readonly_preflight.py",
        "--request GET",
        "--output /dev/null",
        "https://api.vultr.com/v2/account",
    )
    if any(token not in workflow for token in required_workflow):
        errors.append("Vultr read-only workflow is missing a required immutable/read-only control")
    forbidden_workflow = (
        "head_sha=$CANDIDATE_SHA",
        "select-run",
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
        errors.append("Vultr read-only workflow contains stale selection, production, mutation, or phone authority")
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
