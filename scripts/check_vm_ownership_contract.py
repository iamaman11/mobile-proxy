#!/usr/bin/env python3
"""Validate the fail-closed shared-provider VM lifecycle contract."""

from __future__ import annotations

import json
from pathlib import Path


CONTRACT_PATH = Path("contracts/governance/vm-ownership-v1.json")
DOCUMENT_PATH = Path("docs/architecture/vm-ownership-boundary.md")
ITEM19_STATE_DOC = Path("docs/architecture/acceptance-vm-binding-store.md")
PROVIDER_POLICY_PATH = Path("crates/proxy-core/src/provider_lifecycle.rs")
VULTR_ADAPTER_PATH = Path("apps/operator-cli/src/vultr_lifecycle.rs")
VULTR_CLIENT_PATH = Path("apps/operator-cli/src/vultr_client.rs")
DURABLE_STATE_PATH = Path("apps/operator-cli/src/github_vm_binding_store.rs")
TOPOLOGY_PATH = Path("contracts/operations/production-topology-v1.json")
GITHUB_CONTROL_PLANE_PATH = Path("contracts/operations/github-control-plane-v1.json")

REQUIRED_STATES = {
    "empty",
    "create_prepared",
    "create_dispatched",
    "bound",
    "delete_prepared",
    "delete_dispatched",
    "terminal",
}
REQUIRED_FAILURES = {
    "missing_binding",
    "invalid_binding",
    "lifecycle_operation_in_progress_presented_as_empty",
    "create_already_dispatched",
    "terminal_intent_reuse",
    "provider_instance_not_found",
    "provider_identity_mismatch",
    "missing_ownership_metadata",
    "ownership_metadata_mismatch",
    "conflicting_ownership_metadata",
    "ambiguous_resource_set",
    "duplicate_ownership_claim",
    "neighbouring_or_unbound_resource",
    "stale_generation",
    "binding_compare_and_swap_conflict",
    "forked_durable_lifecycle_history",
    "incomplete_provider_pagination",
}
REQUIRED_FORBIDDEN = {
    "arbitrary_instance_uuid_from_operator_input",
    "first_matching_instance_selection",
    "label_name_or_ip_as_authority",
    "fuzzy_or_prefix_ownership_matching",
    "mutation_without_expected_generation",
    "operation_after_identity_ownership_or_generation_verification_failure",
    "unverified_binding_replacement",
    "blind_create_retry_after_dispatch_fence",
    "binding_clear_before_provider_confirmed_delete",
    "terminal_intent_reset_to_generation_one",
    "item_18_live_provider_mutation",
    "item_18_final_production_authority",
    "item_19_production_authority",
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


def _require_tokens(path: Path, root: Path, tokens: tuple[str, ...], errors: list[str]) -> None:
    if not (root / path).is_file():
        errors.append(f"missing required VM lifecycle source/document: {path}")
        return
    body = (root / path).read_text(encoding="utf-8")
    for token in tokens:
        if token not in body:
            errors.append(f"{path} is missing protected token {token!r}")


def check_repository(root: Path) -> list[str]:
    errors: list[str] = []
    contract = _load(root, CONTRACT_PATH, errors)
    topology = _load(root, TOPOLOGY_PATH, errors)
    github = _load(root, GITHUB_CONTROL_PLANE_PATH, errors)
    if not contract:
        return errors

    if contract.get("contract_version") != 1 or contract.get("status") != "protected":
        errors.append("VM ownership contract must remain protected version 1")
    if contract.get("owner") != "operator-cli":
        errors.append("VM ownership contract owner must remain operator-cli")

    implementation = contract.get("implementation")
    required_implementation = {
        "provider_neutral_policy": str(PROVIDER_POLICY_PATH),
        "vultr_adapter": str(VULTR_ADAPTER_PATH),
        "vultr_http_client": str(VULTR_CLIENT_PATH),
        "durable_acceptance_state": str(DURABLE_STATE_PATH),
        "live_execution": "forbidden_until_item_19_bounded_workflow_and_exact_current_gates",
        "first_live_vm_creation_item": 19,
    }
    if implementation != required_implementation:
        errors.append("VM ownership implementation boundary differs from protected item-19 Slice A state")

    binding = contract.get("binding")
    if not isinstance(binding, dict):
        errors.append("VM ownership binding must be an object")
    else:
        expected = {
            "state_store": "durable owner-controlled state outside version control",
            "identity": "provider-assigned immutable instance UUID/ID",
            "ownership_intent": "exact immutable lifecycle scope plus exact intent ID",
            "serialized_writer": "one repository-wide acceptance lifecycle workflow concurrency group with cancel-in-progress false",
            "fork_policy": "non-linear durable history fails closed",
            "terminal_reuse": "forbidden",
        }
        for key, value in expected.items():
            if binding.get(key) != value:
                errors.append(f"VM ownership binding {key!r} differs from protected value")
        if "generation" not in binding or "compare_and_swap" not in binding:
            errors.append("VM ownership binding must define generation and compare-and-swap fencing")

    states = contract.get("lifecycle_states")
    if not isinstance(states, list) or set(states) != REQUIRED_STATES:
        errors.append("VM ownership lifecycle states must distinguish empty/create/delete/bound/terminal phases")

    ownership = contract.get("required_ownership_metadata")
    if not isinstance(ownership, dict) or ownership.get("static") != {
        "project": "mobile-proxy",
        "managed-by": "mobile-proxy",
    }:
        errors.append("VM ownership static metadata differs from exact mobile-proxy identity")
    elif ownership.get("binding_fields") != ["scope", "intent", "generation"] or ownership.get("matching") != "exact_only":
        errors.append("VM ownership metadata must be exact scope/intent/generation only")

    enumeration = contract.get("provider_enumeration")
    if not isinstance(enumeration, dict) or enumeration != {
        "complete_listing_required_before_lifecycle_decision": True,
        "pagination": "bounded_cursor_pagination_until_no_next_cursor",
        "first_page_only": "forbidden",
        "duplicate_or_ambiguous_claims": "fail_closed",
    }:
        errors.append("provider enumeration must be complete, bounded and fail closed")

    operations = contract.get("operations")
    required_ops = {"create", "manage", "stop", "reconfigure", "snapshot", "delete", "replace"}
    if not isinstance(operations, dict) or set(operations) != required_ops:
        errors.append("VM ownership operations differ from the protected typed lifecycle set")
        operations = {}

    create = operations.get("create")
    if not isinstance(create, dict):
        errors.append("VM ownership create contract is missing")
    else:
        required_true = (
            "requires_never_started_empty_state",
            "requires_zero_ownership_compatible_resources",
            "requires_durable_prepare_before_dispatch",
            "requires_durable_dispatch_fence_before_provider_post",
            "provider_request_must_set_exact_ownership_metadata",
            "provider_response_or_relisted_resource_must_match_exact_ownership_metadata",
            "persist_binding_with_compare_and_swap_before_success",
        )
        if any(create.get(field) is not True for field in required_true):
            errors.append("VM create must be unique, durably fenced, exactly owned and CAS-persisted")
        if create.get("blind_redispatch_after_dispatched_state") != "forbidden":
            errors.append("VM create must forbid blind redispatch after durable dispatch fencing")
        if create.get("ambiguous_provider_post_outcome") != "relist_and_recover_or_fail_closed_never_blindly_post_again":
            errors.append("ambiguous provider create outcome must recover or fail closed")

    for operation in ("manage", "stop", "reconfigure", "snapshot", "delete", "replace"):
        rule = operations.get(operation)
        if not isinstance(rule, dict) or any(
            rule.get(field) is not True
            for field in (
                "requires_persisted_binding",
                "requires_exact_provider_identity",
                "requires_exact_ownership_metadata",
                "requires_expected_generation",
            )
        ):
            errors.append(f"VM {operation} must require exact binding/provider/ownership/generation")

    delete = operations.get("delete")
    if not isinstance(delete, dict) or any(
        delete.get(field) is not True
        for field in (
            "requires_durable_prepare_before_dispatch",
            "requires_durable_dispatch_fence_before_provider_delete",
            "clear_binding_only_after_provider_confirms_delete",
            "clear_binding_requires_compare_and_swap",
            "clear_transitions_intent_to_terminal",
        )
    ):
        errors.append("VM delete must be durably fenced and clear only after provider-confirmed deletion")

    replace = operations.get("replace")
    if not isinstance(replace, dict) or any(
        replace.get(field) is not True
        for field in (
            "replacement_generation_must_be_exactly_current_plus_one",
            "replacement_must_be_verified_before_binding_swap",
            "atomically_replace_provider_identity_and_generation_with_compare_and_swap",
        )
    ):
        errors.append("VM replace must advance exactly one verified generation with CAS")

    failures = contract.get("fail_closed")
    if not isinstance(failures, list) or set(failures) != REQUIRED_FAILURES:
        errors.append("VM ownership fail_closed set differs from protected item-19 failures")
    forbidden = contract.get("forbidden")
    if not isinstance(forbidden, list) or set(forbidden) != REQUIRED_FORBIDDEN:
        errors.append("VM ownership forbidden set differs from protected item-19 behaviours")

    if contract.get("item_18_execution") != {
        "allowed": "contract_policy_adapter_and_non_mutating_tests_only",
        "live_provider_mutation": False,
        "real_vm_creation": False,
        "production_vultr_authority": False,
        "phone_mutation": False,
    }:
        errors.append("item 18 execution boundary must remain non-mutating")
    if contract.get("item_19_slice_a") != {
        "allowed": "durable_state_typed_http_client_contracts_docs_and_non_mutating_tests",
        "live_provider_mutation": False,
        "real_vm_creation": False,
        "production_vultr_authority": False,
        "phone_mutation": False,
    }:
        errors.append("item 19 Slice A must remain non-mutating and non-production")

    if topology:
        migration = topology.get("migration_status")
        if not isinstance(migration, dict):
            errors.append("production topology migration_status must be an object")
        else:
            if migration.get("vultr_adapter") != "implemented_typed_provider_neutral_ownership_and_generation_policy":
                errors.append("production topology must keep item 18 typed Vultr adapter protected")
            if migration.get("vultr_durable_acceptance_state") != "item_19_slice_a_active_crash_safe_dispatch_fencing_no_live_entrypoint":
                errors.append("production topology must bind the item-19 durable state boundary")
            if migration.get("vultr_typed_http_client") != "item_19_slice_a_active_acceptance_only_bounded_full_instance_enumeration":
                errors.append("production topology must bind the item-19 typed client boundary")
            if migration.get("vultr_live_lifecycle") != "item_19_active_but_live_invocation_forbidden_until_bounded_workflow_exact_authority_preflight_and_provider_proof_window_gates":
                errors.append("production topology live lifecycle must remain forbidden until all item-19 live gates")

    if github:
        adapter = github.get("vultr_lifecycle_adapter")
        if not isinstance(adapter, dict):
            errors.append("GitHub control plane must define item-19 lifecycle adapter state")
        else:
            required = {
                "status": "item_19_slice_a_typed_client_and_durable_state_active_no_live_entrypoint",
                "provider_identity": "typed_provider_assigned_immutable_uuid_id",
                "ownership_matching": "exact_project_manager_scope_intent_generation",
                "generation_cas": "required",
                "create_dispatch_fence": "durable_before_provider_post_and_never_blindly_redispatched",
                "delete_dispatch_fence": "durable_before_provider_delete",
                "terminal_intent_reuse": "forbidden",
                "full_provider_enumeration": "bounded_cursor_pagination_required_before_lifecycle_decisions",
                "live_execution": "forbidden_until_item_19_bounded_workflow_and_exact_current_gates",
                "first_live_vm_creation_item": 19,
                "production_vultr_authority": False,
            }
            for key, value in required.items():
                if adapter.get(key) != value:
                    errors.append(f"GitHub lifecycle adapter {key!r} differs from protected item-19 state")

    _require_tokens(
        PROVIDER_POLICY_PATH,
        root,
        (
            "ProviderResourceId",
            "OwnershipIntent",
            "Generation",
            "VmBindingStore",
            "compare_and_swap",
            "VerifiedMutationTarget",
            "DuplicateOwnershipClaim",
            "NeighboringOrUnboundResource",
            "StaleGeneration",
        ),
        errors,
    )
    _require_tokens(
        VULTR_ADAPTER_PATH,
        root,
        (
            "Uuid::parse_str",
            "mobile-proxy:scope=",
            "mobile-proxy:intent=",
            "mobile-proxy:generation=",
            "VerifiedMutationTarget",
            "PlannedCreate",
        ),
        errors,
    )
    _require_tokens(
        DURABLE_STATE_PATH,
        root,
        (
            "CreatePrepared",
            "CreateDispatched",
            "DeletePrepared",
            "DeleteDispatched",
            "Terminal",
            "CreateAlreadyDispatched",
            "TerminalIntentReuse",
            "OperationInProgress",
            "predecessor_deployment_id",
        ),
        errors,
    )
    _require_tokens(
        VULTR_CLIENT_PATH,
        root,
        (
            "INSTANCE_PAGE_SIZE: u32 = 500",
            "MAX_INSTANCE_PAGES",
            "cursor",
            "ResponseTooLarge",
            "AcceptanceScopeRequired",
            "VerifiedMutationTarget",
            "PlannedCreate",
        ),
        errors,
    )
    _require_tokens(
        ITEM19_STATE_DOC,
        root,
        (
            "CreateDispatched",
            "blind second POST",
            "Terminal",
            "Complete provider enumeration",
            "production-vultr",
        ),
        errors,
    )
    _require_tokens(
        DOCUMENT_PATH,
        root,
        (
            "provider-assigned immutable VM UUID/ID",
            "scope",
            "intent",
            "generation",
            "compare-and-swap",
            "fail closed",
            "item 19",
        ),
        errors,
    )

    client = (root / VULTR_CLIENT_PATH).read_text(encoding="utf-8") if (root / VULTR_CLIENT_PATH).is_file() else ""
    for forbidden_token in (
        "production-vultr",
        "LifecycleScope::Production =>",
        "first().unwrap",
        "instances[0]",
    ):
        if forbidden_token in client:
            errors.append(f"typed Vultr client contains forbidden authority shortcut {forbidden_token!r}")

    return errors


def main() -> int:
    errors = check_repository(Path(__file__).resolve().parents[1])
    for error in errors:
        print(error)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
