#!/usr/bin/env python3
"""Keep protected Item 20 non-live orchestration wired into canonical control-plane contracts."""

from __future__ import annotations

import json
from pathlib import Path


ITEM20_CONTRACT = Path("contracts/operations/item20-acceptance-v1.json")
GITHUB_CONTRACT = Path("contracts/operations/github-control-plane-v1.json")
TOPOLOGY_CONTRACT = Path("contracts/operations/production-topology-v1.json")
ITEM20_WORKFLOW = Path(".github/workflows/item20-session-orchestration.yml")

EXPECTED_SURFACE = {
    "contract": "contracts/operations/item20-acceptance-v1.json",
    "status": "protected_validation_and_candidate_build_only",
    "workflow": ".github/workflows/item20-session-orchestration.yml",
    "executor": "github-hosted",
    "environment": "none",
    "provider_credentials": "forbidden",
    "provider_mutation": False,
    "phone_execution": False,
    "endpoint_handoff": "not_implemented",
    "live_execution": False,
    "final_production_authority": False,
}

EXPECTED_TOPOLOGY_EXECUTION = (
    "GitHub-hosted exact-current protected-main validation plus exact immutable candidate build only; "
    "no acceptance-vultr environment, provider credentials, provider mutation, phone execution or endpoint handoff"
)
EXPECTED_MIGRATION = (
    "protected_non_live_validation_and_exact_candidate_build_only_no_provider_or_phone_authority"
)
EXPECTED_NEXT_LIFECYCLE = (
    "item_20_must_open_fresh_jit_acceptance_session_with_distinct_item_20_ownership_intent_"
    "and_never_reuse_terminal_item_19_intent"
)


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
    item20 = _load(root, ITEM20_CONTRACT, errors)
    github = _load(root, GITHUB_CONTRACT, errors)
    topology = _load(root, TOPOLOGY_CONTRACT, errors)

    if github.get("item20_acceptance_contract") != str(ITEM20_CONTRACT):
        errors.append("GitHub control plane does not bind the protected Item 20 contract")
    if github.get("item20_non_live_orchestration") != EXPECTED_SURFACE:
        errors.append("GitHub Item 20 non-live orchestration wiring differs from protected value")

    orchestration = item20.get("orchestration")
    if not isinstance(orchestration, dict):
        errors.append("Item 20 contract orchestration block is missing")
    else:
        expected_contract_fields = {
            "status": EXPECTED_SURFACE["status"],
            "workflow": EXPECTED_SURFACE["workflow"],
            "executor": EXPECTED_SURFACE["executor"],
            "provider_environment": "none",
            "provider_credentials": "forbidden",
            "provider_mutation": False,
            "phone_execution": False,
            "endpoint_handoff": "not_implemented",
        }
        for key, value in expected_contract_fields.items():
            if orchestration.get(key) != value:
                errors.append(f"Item 20 contract orchestration field {key!r} differs")

    authorization = item20.get("authorization")
    if not isinstance(authorization, dict) or authorization != {
        "endpoint_handoff_authorized": False,
        "final_production_authority": False,
        "live_execution_authorized": False,
        "phone_mutation_authorized": False,
        "provider_mutation_authorized": False,
    }:
        errors.append("Item 20 protected contract must remain non-live and non-mutating")

    execution = topology.get("execution")
    if not isinstance(execution, dict) or execution.get("item20_non_live") != EXPECTED_TOPOLOGY_EXECUTION:
        errors.append("production topology does not expose the protected Item 20 non-live boundary")

    migration = topology.get("migration_status")
    if not isinstance(migration, dict):
        errors.append("production topology migration status is missing")
    else:
        if migration.get("item_20_non_live_orchestration") != EXPECTED_MIGRATION:
            errors.append("production topology Item 20 non-live checkpoint differs")
        if migration.get("next_acceptance_lifecycle") != EXPECTED_NEXT_LIFECYCLE:
            errors.append("production topology Item 20 live-session gate differs")
        if migration.get("phone_mutation") != "item_20_blocked_by_signing_continuity_gate_issue_115":
            errors.append("production topology no longer preserves the #115 phone-mutation gate")

    workflow_path = root / ITEM20_WORKFLOW
    if not workflow_path.is_file():
        errors.append("protected Item 20 non-live orchestration workflow is missing")
    else:
        workflow = workflow_path.read_text(encoding="utf-8")
        for required in (
            "runs-on: ubuntu-latest",
            "Verify build-only Item 20 orchestration boundary",
            "Build exact immutable candidate server artifact",
            "Provider mutation authorized: false",
            "Phone mutation authorized: false",
            "Endpoint handoff authorized: false",
            "Live execution authorized: false",
        ):
            if required not in workflow:
                errors.append(f"Item 20 non-live workflow is missing boundary token {required!r}")

        lowered = workflow.lower()
        for forbidden in (
            "environment: acceptance-vultr",
            "environment: production-vultr",
            "vultr_api_key",
            "vultr_ssh_private_key",
            "self-hosted",
            "adb ",
            "/v2/instances",
            "curl -x post",
            "curl -x delete",
            "curl -x patch",
        ):
            if forbidden in lowered:
                errors.append(f"Item 20 non-live workflow contains forbidden live token {forbidden!r}")

    return errors


def main() -> int:
    errors = check_repository(Path(__file__).resolve().parents[1])
    for error in errors:
        print(error)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
