#!/usr/bin/env python3
"""Prevent historical Item-19 evidence and Item-20 handoff architecture from drifting."""

from __future__ import annotations

import json
from pathlib import Path


PLAN = Path("docs/PRODUCTION_BASELINE_PLAN.md")
PHYSICAL_RUNBOOK = Path("docs/physical-phone-acceptance-runbook.md")
PRE_DEVICE = Path("docs/PRE_DEVICE_PREPARATION_CHECKLIST.md")
PHONE_RUNTIME = Path("docs/operations/phone-gitops-runtime.md")
ITEM19_CLOSEOUT = Path("docs/operations/item19-provider-proof-closeout.md")
HISTORICAL_AUDIT = Path("docs/pre-device-readiness-audit.md")
GITHUB_CONTRACT = Path("contracts/operations/github-control-plane-v1.json")
TOPOLOGY_CONTRACT = Path("contracts/operations/production-topology-v1.json")
VM_CONTRACT = Path("contracts/governance/vm-ownership-v1.json")
STATE_SOURCE = Path("apps/operator-cli/src/github_vm_binding_store.rs")
CLIENT_SOURCE = Path("apps/operator-cli/src/vultr_client.rs")
READONLY_WORKFLOW = Path(".github/workflows/vultr-readonly-preflight.yml")

HISTORICAL_ITEM19_SHA = "d151dbdd156279e32a5361d304c90f996bd2d565"
EXPECTED_ITEM19_LIFECYCLE = (
    "historical_item_19_complete_provider_only_live_run_33342000338_exact_candidate_deployed_verified_deleted_"
    "and_durable_terminal_confirmed_not_active_item20_candidate_authority"
)
EXPECTED_ITEM20_NEXT = (
    "item_20_must_select_exact_current_protected_main_as_candidate_and_control_plane_then_open_fresh_jit_"
    "acceptance_session_with_distinct_item_20_ownership_intent_and_never_reuse_terminal_item_19_intent"
)


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
    closeout = _read(root, ITEM19_CLOSEOUT, errors)
    historical = _read(root, HISTORICAL_AUDIT, errors)
    state = _read(root, STATE_SOURCE, errors)
    client = _read(root, CLIENT_SOURCE, errors)
    readonly = _read(root, READONLY_WORKFLOW, errors)
    github = _load(root, GITHUB_CONTRACT, errors)
    topology = _load(root, TOPOLOGY_CONTRACT, errors)
    vm_contract = _load(root, VM_CONTRACT, errors)

    for stale in (
        "first unfinished item for the current continuation is item 16",
        "The first unfinished Production Baseline item is **16**",
        "## Current implementation focus — item 16",
        "Item 19 is `ACTIVE` and is the first unfinished item",
        "**Item 19 is `ACTIVE` and is the first unfinished item.**",
    ):
        if stale in plan:
            errors.append(f"canonical baseline plan regressed to stale delivery status: {stale!r}")
    for required in (
        "Historical Item 19 candidate",
        "Item 19 historical provider proof is COMPLETE.",
        "Item 20 is the first unfinished delivery item",
        "Item 20 remains blocked by the signing-continuity gate",
        "distinct ownership intent rather than reuse Item 19's terminal proof intent",
    ):
        if required not in plan:
            errors.append(f"canonical baseline plan is missing reconciled post-item-19 token {required!r}")

    for required in (
        "Status: **COMPLETE",
        "33341602485",
        "33341737260",
        "33341760002",
        "33342000338",
        "provider deletion confirmed",
        "durable terminal state confirmed",
        "Item 20 ownership intent",
        "signing-continuity gate #115",
        HISTORICAL_ITEM19_SHA,
    ):
        if required not in closeout:
            errors.append(f"item-19 provider-proof closeout is missing evidence token {required!r}")

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
        "The private runner has no Vultr credentials",
        "Before enabling any mutable phone workflow:",
        "Item 19 provider proof is COMPLETE.",
        "that SHA is not active Item 20 release authority.",
        "private Item 20 phone execution must not call Vultr APIs.",
    ):
        if required not in phone:
            errors.append(f"phone GitOps runtime is missing fail-closed historical Item19/Item20 boundary {required!r}")

    for required in (
        "distinct Item 20 ownership intent",
        "terminal Item 19 proof intent is never reused",
    ):
        if required not in physical:
            errors.append(f"physical acceptance runbook is missing non-cyclic JIT handoff token {required!r}")

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
    if "AcceptanceVmLifecycleState::Empty => Ok(None)" not in state:
        errors.append("only never-started Empty state may project as an unbound None binding")
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
            elif lifecycle.get("phone_signing_gate") != "issue_115_applies_to_item_20_phone_mutation_not_item_19_provider_proof":
                errors.append("item-19 provider proof must not consume the item-20 phone signing gate")
            elif lifecycle.get("item_20_server_session") != "fresh_jit_acceptance_session_with_distinct_item_20_ownership_intent_never_reuse_terminal_item_19_intent":
                errors.append("item-20 must open a fresh JIT server session without terminal intent reuse")

    phone_contract = github.get("phone_control_repository") if github else None
    if not isinstance(phone_contract, dict):
        errors.append("GitHub contract must define the private phone execution boundary")
    else:
        denied = phone_contract.get("runner_must_not_receive")
        if not isinstance(denied, list) or not {"VULTR_API_KEY", "VULTR_SSH_PRIVATE_KEY"}.issubset(denied):
            errors.append("private phone runner must be permanently denied Vultr credentials")

    migration = topology.get("migration_status") if topology else None
    if not isinstance(migration, dict):
        errors.append("production topology must define migration_status")
    else:
        if migration.get("vultr_live_lifecycle") != EXPECTED_ITEM19_LIFECYCLE:
            errors.append("production topology must preserve Item19 lifecycle as historical-only evidence")
        if migration.get("next_acceptance_lifecycle") != EXPECTED_ITEM20_NEXT:
            errors.append("production topology must require exact-current same-SHA Item20 selection plus a fresh distinct intent")
        if migration.get("phone_mutation") != "item_20_blocked_by_signing_continuity_gate_issue_115":
            errors.append("production topology must retain #115 as the item-20 phone-mutation gate")
        live_preflight = str(migration.get("vultr_live_preflight", ""))
        if HISTORICAL_ITEM19_SHA not in live_preflight or "not_active_item20_candidate_authority" not in live_preflight:
            errors.append("production topology must preserve Item19 read-only proof as historical-only evidence")

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
