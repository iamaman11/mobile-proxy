#!/usr/bin/env python3
"""Validate provider-neutral VM ownership safety without granting PRODUCT execution authority."""

from __future__ import annotations

import json
from pathlib import Path

CONTRACT_PATH = Path("contracts/governance/vm-ownership-v1.json")
RETIREMENT_PATH = Path("contracts/operations/historical-public-acceptance-retirement-v1.json")
PROJECT_V2_PATH = Path("contracts/operations/project-authority-v2.json")
TOPOLOGY_V2_PATH = Path("contracts/operations/production-topology-v2.json")
DOCUMENT_PATH = Path("docs/architecture/vm-ownership-boundary.md")
ITEM19_STATE_DOC = Path("docs/architecture/acceptance-vm-binding-store.md")
PROVIDER_POLICY_PATH = Path("crates/proxy-core/src/provider_lifecycle.rs")
VULTR_ADAPTER_PATH = Path("apps/operator-cli/src/vultr_lifecycle.rs")
VULTR_CLIENT_PATH = Path("apps/operator-cli/src/vultr_client.rs")
DURABLE_STATE_PATH = Path("apps/operator-cli/src/github_vm_binding_store.rs")

REQUIRED_STATES = {
    "empty", "create_prepared", "create_dispatched", "bound",
    "delete_prepared", "delete_dispatched", "terminal",
}
REQUIRED_FAILURES = {
    "missing_binding", "invalid_binding", "lifecycle_operation_in_progress_presented_as_empty",
    "create_already_dispatched", "terminal_intent_reuse", "provider_instance_not_found",
    "provider_identity_mismatch", "missing_ownership_metadata", "ownership_metadata_mismatch",
    "conflicting_ownership_metadata", "ambiguous_resource_set", "duplicate_ownership_claim",
    "neighbouring_or_unbound_resource", "stale_generation", "binding_compare_and_swap_conflict",
    "forked_durable_lifecycle_history", "incomplete_provider_pagination",
}
REQUIRED_FORBIDDEN = {
    "arbitrary_instance_uuid_from_operator_input", "first_matching_instance_selection",
    "label_name_or_ip_as_authority", "fuzzy_or_prefix_ownership_matching",
    "mutation_without_expected_generation", "operation_after_identity_ownership_or_generation_verification_failure",
    "unverified_binding_replacement", "blind_create_retry_after_dispatch_fence",
    "binding_clear_before_provider_confirmed_delete", "terminal_intent_reset_to_generation_one",
    "provider_mutation_without_current_deployment_controller_admission",
    "public_product_repository_runtime_provider_mutation_authority",
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
    retirement = _load(root, RETIREMENT_PATH, errors)
    project_v2 = _load(root, PROJECT_V2_PATH, errors)
    topology_v2 = _load(root, TOPOLOGY_V2_PATH, errors)
    if not contract:
        return errors

    if contract.get("contract_version") != 1 or contract.get("status") != "protected_provider_neutral_safety":
        errors.append("VM ownership contract must remain protected provider-neutral safety version 1")
    if contract.get("owner") != "operator-cli":
        errors.append("VM ownership contract owner must remain operator-cli")

    expected_authority = {
        "project_authority": str(PROJECT_V2_PATH),
        "production_topology": str(TOPOLOGY_V2_PATH),
        "runtime_deployment_controller": "iamaman11/mobile-proxy-production",
        "execution_authority": False,
        "historical_item18_item19_chronology": "context_only_not_current_runtime_authority",
    }
    if contract.get("current_authority") != expected_authority:
        errors.append("VM ownership safety contract current authority binding differs from v2 Deployment Controller boundary")

    required_implementation = {
        "provider_neutral_policy": str(PROVIDER_POLICY_PATH),
        "vultr_adapter": str(VULTR_ADAPTER_PATH),
        "vultr_http_client": str(VULTR_CLIENT_PATH),
        "durable_lifecycle_state_model": str(DURABLE_STATE_PATH),
        "execution_authority": False,
    }
    if contract.get("implementation") != required_implementation:
        errors.append("VM ownership implementation boundary differs from provider-neutral safety contract")

    controller = project_v2.get("deployment_controller_authority")
    product = project_v2.get("public_product_authority")
    if (
        not isinstance(controller, dict)
        or controller.get("repository") != "iamaman11/mobile-proxy-production"
        or controller.get("visibility") != "public"
        or controller.get("authority") != "deployment_controller"
    ):
        errors.append("project v2 no longer binds the Deployment Controller as runtime authority")
    if not isinstance(product, dict) or "phone_or_vm_target_mutation" not in product.get("forbidden", []):
        errors.append("project v2 no longer forbids PRODUCT VM target mutation")

    targets = topology_v2.get("targets")
    vm_target = targets.get("vm-production") if isinstance(targets, dict) else None
    if (
        not isinstance(vm_target, dict)
        or vm_target.get("destructive_dispatch") != "forbidden_until_proven"
        or vm_target.get("reuses_same_controller_kernel") is not True
    ):
        errors.append("production topology v2 VM target no longer reuses the fail-closed Deployment Controller kernel")

    historical_docs = retirement.get("historical_execution_docs")
    mixed_docs = retirement.get("mixed_context_docs")
    if not isinstance(historical_docs, list) or str(ITEM19_STATE_DOC) not in historical_docs:
        errors.append("Item19 VM binding-store execution design is not classified as historical-only")
    if not isinstance(mixed_docs, dict) or mixed_docs.get(str(DOCUMENT_PATH)) != (
        "provider_neutral_ownership_safety_is_current_but_item18_item19_execution_chronology_is_historical_only"
    ):
        errors.append("VM ownership document does not separate current safety from historical Item18/Item19 chronology")

    binding = contract.get("binding")
    if not isinstance(binding, dict):
        errors.append("VM ownership binding must be an object")
    else:
        expected = {
            "state_store": "durable owner-controlled state outside version control",
            "identity": "provider-assigned immutable instance UUID/ID",
            "ownership_intent": "exact immutable lifecycle scope plus exact intent ID",
            "serialized_writer": "runtime must provide exactly one serialized lifecycle writer; concrete lock and transaction ownership is defined by the current deployment controller",
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
        "project": "mobile-proxy", "managed-by": "mobile-proxy"
    }:
        errors.append("VM ownership static metadata differs from exact mobile-proxy identity")
    elif ownership.get("binding_fields") != ["scope", "intent", "generation"] or ownership.get("matching") != "exact_only":
        errors.append("VM ownership metadata must be exact scope/intent/generation only")

    enumeration = contract.get("provider_enumeration")
    if enumeration != {
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
            "requires_never_started_empty_state", "requires_zero_ownership_compatible_resources",
            "requires_durable_prepare_before_dispatch", "requires_durable_dispatch_fence_before_provider_post",
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
                "requires_persisted_binding", "requires_exact_provider_identity",
                "requires_exact_ownership_metadata", "requires_expected_generation",
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
            "replacement_dispatch_fencing_cannot_be_bypassed",
        )
    ):
        errors.append("VM replace must advance exactly one verified generation with CAS and preserved dispatch fencing")

    failures = contract.get("fail_closed")
    if not isinstance(failures, list) or set(failures) != REQUIRED_FAILURES:
        errors.append("VM ownership fail_closed set differs from protected provider-neutral failures")
    forbidden = contract.get("forbidden")
    if not isinstance(forbidden, list) or set(forbidden) != REQUIRED_FORBIDDEN:
        errors.append("VM ownership forbidden set differs from protected provider-neutral behaviours")

    if contract.get("activation_condition") != (
        "Any runtime provider adapter must satisfy this provider-neutral safety contract before destructive lifecycle dispatch is admitted by the current deployment controller."
    ):
        errors.append("VM ownership activation condition is not controller-v2 neutral")
    if contract.get("historical_execution_context") != {
        "item18_item19_public_acceptance_chronology": "historical_only_not_current_runtime_authority",
        "old_public_acceptance_workflow_serialization": "retired_not_current_writer_authority",
    }:
        errors.append("VM ownership historical execution chronology is not explicitly non-authoritative")

    _require_tokens(PROVIDER_POLICY_PATH, root, (
        "ProviderResourceId", "OwnershipIntent", "Generation", "VmBindingStore",
        "compare_and_swap", "VerifiedMutationTarget", "DuplicateOwnershipClaim",
        "NeighboringOrUnboundResource", "StaleGeneration",
    ), errors)
    _require_tokens(VULTR_ADAPTER_PATH, root, (
        "Uuid::parse_str", "mobile-proxy:scope=", "mobile-proxy:intent=",
        "mobile-proxy:generation=", "VerifiedMutationTarget", "PlannedCreate",
    ), errors)
    _require_tokens(DURABLE_STATE_PATH, root, (
        "CreatePrepared", "CreateDispatched", "DeletePrepared", "DeleteDispatched",
        "Terminal", "CreateAlreadyDispatched", "TerminalIntentReuse", "OperationInProgress",
        "predecessor_deployment_id",
    ), errors)
    _require_tokens(VULTR_CLIENT_PATH, root, (
        "INSTANCE_PAGE_SIZE: u32 = 500", "MAX_INSTANCE_PAGES", "cursor", "ResponseTooLarge",
        "AcceptanceScopeRequired", "VerifiedMutationTarget", "PlannedCreate",
    ), errors)
    _require_tokens(ITEM19_STATE_DOC, root, (
        "CreateDispatched", "blind second POST", "Terminal", "Complete provider enumeration",
    ), errors)
    _require_tokens(DOCUMENT_PATH, root, (
        "provider-assigned immutable VM UUID/ID", "scope", "intent", "generation",
        "compare-and-swap", "fail closed",
    ), errors)

    client = (root / VULTR_CLIENT_PATH).read_text(encoding="utf-8") if (root / VULTR_CLIENT_PATH).is_file() else ""
    for forbidden_token in (
        "production-vultr", "LifecycleScope::Production =>", "first().unwrap", "instances[0]",
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
