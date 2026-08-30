#!/usr/bin/env python3
"""Prevent Production Baseline item-19 architecture and documentation drift."""

from __future__ import annotations

import json
from pathlib import Path


PLAN = Path("docs/PRODUCTION_BASELINE_PLAN.md")
PHYSICAL_RUNBOOK = Path("docs/physical-phone-acceptance-runbook.md")
PRE_DEVICE = Path("docs/PRE_DEVICE_PREPARATION_CHECKLIST.md")
PHONE_RUNTIME = Path("docs/operations/phone-gitops-runtime.md")
HISTORICAL_AUDIT = Path("docs/pre-device-readiness-audit.md")
GITHUB_CONTRACT = Path("contracts/operations/github-control-plane-v1.json")
VM_CONTRACT = Path("contracts/governance/vm-ownership-v1.json")
STATE_SOURCE = Path("apps/operator-cli/src/github_vm_binding_store.rs")
CLIENT_SOURCE = Path("apps/operator-cli/src/vultr_client.rs")
READONLY_WORKFLOW = Path(".github/workflows/vultr-readonly-preflight.yml")


def _read(root: Path, path: Path, errors: list[str]) -> str:
    try:
        return (root / path).read_text(encoding="utf-8")
    except OSError as error:
        errors.append(f"cannot read {path}: {error}")
        return ""


def _load(root: Path, path: Path, errors: list[str]) -> dict[str, object]:
    text = _read(root, path, errors)
    if not text:
        return {}
    try:
        value = json.loads(text)
    except json.JSONDecodeError as error:
        errors.append(f"cannot parse {path}: {error}")
        return {}
    if not isinstance(value, dict):
        errors.append(f"{path} root must be an object")
        return {}
    return value


def check_repository(root: Path) -> list[str]:
    errors: list[str] = []
    plan = _read(root, PLAN, errors)
    physical = _read(root, PHYSICAL_RUNBOOK, errors)
    pre_device = _read(root, PRE_DEVICE, errors)
    phone = _read(root, PHONE_RUNTIME, errors)
    historical = _read(root, HISTORICAL_AUDIT, errors)
    state = _read(root, STATE_SOURCE, errors)
    client = _read(root, CLIENT_SOURCE, errors)
    readonly = _read(root, READONLY_WORKFLOW, errors)
    github = _load(root, GITHUB_CONTRACT, errors)
    vm_contract = _load(root, VM_CONTRACT, errors)

    for stale in (
        "first unfinished item for the current continuation is item 16",
        "The first unfinished Production Baseline item is **16**",
        "## Current implementation focus — item 16",
    ):
        if stale in plan:
            errors.append(f"canonical baseline plan regressed to stale item-16 status: {stale!r}")
    for required in (
        "items 15, 16, 17 and 18 are `COMPLETE`",
        "Item 19 is `ACTIVE`",
        "Item 20 becomes the next delivery item only after the live item-19 Definition of Done is complete",
    ):
        if required not in plan:
            errors.append(f"canonical baseline plan is missing current item-19 status token {required!r}")

    legacy_runtime_tokens = (
        "--project <gcp-project>",
        "--zone <gcp-zone>",
        "GCP project is correct",
        "cargo run --release -p operator-cli -- provision-vm",
        "gcloud compute",
    )
    for path, body in ((PHYSICAL_RUNBOOK, physical), (PRE_DEVICE, pre_device)):
        for token in legacy_runtime_tokens:
            if token in body:
                errors.append(f"current normative document {path} contains retired GCP/workstation command token {token!r}")

    if "STATUS: HISTORICAL / NON-NORMATIVE AUDIT" not in historical:
        errors.append("legacy pre-device readiness audit must remain explicitly historical/non-normative")

    for required in (
        "This is a workflow-level mutation gate, not only an APK-install gate.",
        "Before enabling **any mutable phone workflow**",
        "private runner must never receive\n   Vultr credentials",
    ):
        if required not in phone:
            errors.append(f"phone GitOps runtime is missing fail-closed item-19/20 boundary {required!r}")

    for required in (
        "CreatePrepared",
        "CreateDispatched",
        "DeletePrepared",
        "DeleteDispatched",
        "Terminal",
        "CreateAlreadyDispatched",
        "OperationInProgress",
        "TerminalIntentReuse",
    ):
        if required not in state:
            errors.append(f"durable item-19 lifecycle state is missing {required!r}")
    if "Ok(None)" not in state:
        errors.append("binding projection no longer exposes an explicit never-started None state")
    if "AcceptanceVmLifecycleState::CreateDispatched" not in state or "Err(BindingStoreError::OperationInProgress)" not in state:
        errors.append("in-progress create must not project as an unbound/never-created intent")

    for required in (
        "INSTANCE_PAGE_SIZE: u32 = 500",
        "MAX_INSTANCE_PAGES",
        '"cursor"',
        "ResponseTooLarge",
        "AcceptanceScopeRequired",
    ):
        if required not in client:
            errors.append(f"typed Vultr client is missing bounded lifecycle control {required!r}")
    for forbidden in ("instances[0]", ".first().unwrap", "production-vultr"):
        if forbidden in client:
            errors.append(f"typed Vultr client contains forbidden selection/production token {forbidden!r}")

    if "https://api.vultr.com/v2/account" not in readonly:
        errors.append("read-only Vultr preflight must retain GET /v2/account")
    for forbidden in ("/v2/instances", "curl -X POST", "curl -X DELETE", "curl -X PATCH", "environment: production-vultr"):
        if forbidden in readonly:
            errors.append(f"read-only Vultr preflight gained forbidden lifecycle token {forbidden!r}")

    acceptance_env = github.get("acceptance_vultr_environment") if github else None
    if not isinstance(acceptance_env, dict):
        errors.append("GitHub contract must define acceptance-vultr credential boundary")
    else:
        capabilities = acceptance_env.get("workflow_capabilities")
        if not isinstance(capabilities, dict):
            errors.append("acceptance-vultr must define per-workflow capability contracts")
        else:
            readonly_capability = capabilities.get("readonly_preflight")
            if not isinstance(readonly_capability, dict) or readonly_capability.get("allowed_provider_api") != ["GET /v2/account"]:
                errors.append("read-only acceptance capability must remain GET /v2/account only")
            lifecycle = capabilities.get("item_19_acceptance_lifecycle")
            if not isinstance(lifecycle, dict) or lifecycle.get("production_scope") != "forbidden":
                errors.append("item-19 lifecycle must forbid production scope")

    phone_contract = github.get("phone_control_repository") if github else None
    if not isinstance(phone_contract, dict):
        errors.append("GitHub contract must define the private phone execution boundary")
    else:
        denied = phone_contract.get("runner_must_not_receive")
        if not isinstance(denied, list) or not {"VULTR_API_KEY", "VULTR_SSH_PRIVATE_KEY"}.issubset(denied):
            errors.append("private phone runner must be permanently denied Vultr credentials")

    states = vm_contract.get("lifecycle_states") if vm_contract else None
    if not isinstance(states, list) or "terminal" not in states or "create_dispatched" not in states:
        errors.append("VM ownership contract must distinguish dispatched create from terminal lifecycle state")
    forbidden = vm_contract.get("forbidden") if vm_contract else None
    if not isinstance(forbidden, list) or "terminal_intent_reset_to_generation_one" not in forbidden:
        errors.append("VM ownership contract must forbid terminal reset to generation one")
    if not isinstance(forbidden, list) or "label_name_or_ip_as_authority" not in forbidden:
        errors.append("VM ownership contract must forbid name/IP mutation authority")

    return errors


def main() -> int:
    errors = check_repository(Path(__file__).resolve().parents[1])
    for error in errors:
        print(error)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
