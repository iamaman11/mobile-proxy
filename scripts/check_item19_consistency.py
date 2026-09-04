#!/usr/bin/env python3
"""Protect historical Item 19 evidence after public workflow retirement."""

from __future__ import annotations

import json
from pathlib import Path

RETIREMENT = Path("contracts/operations/historical-public-acceptance-retirement-v1.json")
V2_GITHUB = Path("contracts/operations/github-control-plane-v2.json")
ITEM19_CLOSEOUT = Path("docs/operations/item19-provider-proof-closeout.md")
ITEM19_ENTRYPOINT = Path("apps/operator-cli/src/bin/item19-acceptance-lifecycle.rs")
BINDING_STORE = Path("apps/operator-cli/src/github_vm_binding_store.rs")

HISTORICAL_ITEM19_SHA = "d151dbdd156279e32a5361d304c90f996bd2d565"
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
    github_v2 = _load(root, V2_GITHUB, errors)

    if retirement.get("status") != "protected_historical_non_executable":
        errors.append("historical public acceptance retirement contract is not fail-closed")
    if retirement.get("canonical_repository") != "iamaman11/mobile-proxy":
        errors.append("historical retirement contract canonical repository differs")
    retired = retirement.get("retired_workflows")
    if not isinstance(retired, list) or set(retired) != EXPECTED_RETIRED:
        errors.append("historical retirement workflow set differs")

    execution = retirement.get("execution")
    expected_execution = {
        "workflow_files_must_be_absent": True,
        "issue_comment_execution": False,
        "workflow_dispatch_execution": False,
        "provider_api_execution": False,
        "provider_mutation": False,
        "phone_execution": False,
        "private_controller_mutation": False,
        "product_release_authority_changed": False,
    }
    if execution != expected_execution:
        errors.append("historical retirement execution boundary differs")

    for workflow in EXPECTED_RETIRED:
        if (root / workflow).exists():
            errors.append(f"retired historical workflow is executable again: {workflow}")
    upstream = retirement.get("retired_upstream_workflow")
    if upstream != ".github/workflows/acceptance-authority.yml":
        errors.append("retired upstream acceptance workflow identity differs")
    elif (root / upstream).exists():
        errors.append("retired acceptance-authority workflow is executable again")

    historical = retirement.get("immutable_historical_item19_evidence")
    expected_historical = {
        "candidate_sha": HISTORICAL_ITEM19_SHA,
        "quality_run_id": 33341602485,
        "acceptance_authority_run_id": 33341737260,
        "vultr_readonly_preflight_run_id": 33341760002,
        "item19_lifecycle_run_id": 33342000338,
        "closeout_record": "docs/operations/item19-provider-proof-closeout.md",
    }
    if historical != expected_historical:
        errors.append("immutable historical Item 19 evidence identity differs")

    closeout = _read(root, ITEM19_CLOSEOUT, errors)
    for token in (
        HISTORICAL_ITEM19_SHA,
        "33341602485",
        "33341737260",
        "33341760002",
        "33342000338",
        "provider deletion confirmed",
        "durable terminal state confirmed",
    ):
        if token not in closeout:
            errors.append(f"Item 19 closeout lost immutable historical token {token!r}")

    historical_surfaces = github_v2.get("historical_acceptance_surfaces")
    if not isinstance(historical_surfaces, dict) or historical_surfaces.get(
        "public_item19_item20_workflows"
    ) != "historical_or_development_only_not_product_release_or_runtime_deployment_authority":
        errors.append("GitHub v2 no longer classifies public Item19/Item20 workflows as historical")

    entrypoint = _read(root, ITEM19_ENTRYPOINT, errors)
    if 'format!("candidate:{candidate_sha}")' not in entrypoint:
        errors.append("retained Item 19 lifecycle lost historical ownership-intent semantics")

    binding = _read(root, BINDING_STORE, errors)
    for token in (
        "pub enum AcceptanceVmIntentNamespace",
        "Item19,",
        "Item20,",
        "BindingStoreError::TerminalIntentReuse",
    ):
        if token not in binding:
            errors.append(f"retained durable acceptance state lost {token!r}")

    return errors


def main() -> int:
    errors = check_repository(Path(__file__).resolve().parents[1])
    for error in errors:
        print(error)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
