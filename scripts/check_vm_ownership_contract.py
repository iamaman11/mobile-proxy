#!/usr/bin/env python3
"""Validate the fail-closed VM ownership contract for shared cloud accounts."""

from __future__ import annotations

import json
from pathlib import Path


CONTRACT_PATH = Path("contracts/governance/vm-ownership-v1.json")
DOCUMENT_PATH = Path("docs/architecture/vm-ownership-boundary.md")
PROVIDER_POLICY_PATH = Path("crates/proxy-core/src/provider_lifecycle.rs")
VULTR_ADAPTER_PATH = Path("apps/operator-cli/src/vultr_lifecycle.rs")
TOPOLOGY_PATH = Path("contracts/operations/production-topology-v1.json")
GITHUB_CONTROL_PLANE_PATH = Path("contracts/operations/github-control-plane-v1.json")
REQUIRED_STATIC_METADATA = {"project": "mobile-proxy", "managed-by": "mobile-proxy"}
REQUIRED_BINDING_FIELDS = ["scope", "intent", "generation"]
REQUIRED_OPERATIONS = {
    "create",
    "manage",
    "stop",
    "reconfigure",
    "snapshot",
    "delete",
    "replace",
}
REQUIRED_FAILURES = {
    "missing_binding",
    "invalid_binding",
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
}
FORBIDDEN_BEHAVIOURS = {
    "arbitrary_instance_uuid_from_operator_input",
    "first_matching_instance_selection",
    "label_name_or_ip_as_authority",
    "fuzzy_or_prefix_ownership_matching",
    "mutation_without_expected_generation",
    "operation_after_identity_ownership_or_generation_verification_failure",
    "unverified_binding_replacement",
    "item_18_live_provider_mutation",
    "item_18_final_production_authority",
}
EXPECTED_ADAPTER_STATUS = {
    "status": "implemented_non_mutating_item_18",
    "provider_neutral_policy": str(PROVIDER_POLICY_PATH),
    "provider_adapter": str(VULTR_ADAPTER_PATH),
    "ownership_contract": str(CONTRACT_PATH),
    "provider_identity": "typed_provider_assigned_immutable_uuid_id",
    "ownership_matching": "exact_project_manager_scope_intent_generation",
    "generation_cas": "required",
    "idempotent_reconcile": "required",
    "live_execution": "forbidden_until_item_19",
    "first_live_vm_creation_item": 19,
    "production_vultr_authority": False,
}


def _load_json(root: Path, path: Path, label: str) -> tuple[dict | None, str | None]:
    try:
        value = json.loads((root / path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return None, f"cannot load {label}: {error}"
    if not isinstance(value, dict):
        return None, f"{label} root must be an object"
    return value, None


def check_repository(root: Path) -> list[str]:
    errors: list[str] = []
    contract_path = root / CONTRACT_PATH
    document_path = root / DOCUMENT_PATH
    provider_policy_path = root / PROVIDER_POLICY_PATH
    vultr_adapter_path = root / VULTR_ADAPTER_PATH
    if not contract_path.is_file():
        return [f"missing VM ownership contract: {CONTRACT_PATH}"]
    if not document_path.is_file():
        return [f"missing VM ownership architecture document: {DOCUMENT_PATH}"]
    if not provider_policy_path.is_file():
        errors.append(f"missing provider-neutral lifecycle policy: {PROVIDER_POLICY_PATH}")
    if not vultr_adapter_path.is_file():
        errors.append(f"missing typed Vultr adapter: {VULTR_ADAPTER_PATH}")

    contract, load_error = _load_json(root, CONTRACT_PATH, "VM ownership contract")
    if load_error:
        return [load_error]
    assert contract is not None

    topology, topology_error = _load_json(root, TOPOLOGY_PATH, "production topology contract")
    if topology_error:
        errors.append(topology_error)
    github, github_error = _load_json(root, GITHUB_CONTROL_PLANE_PATH, "GitHub control-plane contract")
    if github_error:
        errors.append(github_error)

    if contract.get("contract_version") != 1:
        errors.append("VM ownership contract_version must be 1")
    if contract.get("status") != "protected":
        errors.append("VM ownership contract status must be protected")
    if contract.get("owner") != "operator-cli":
        errors.append("VM ownership contract owner must be operator-cli")

    implementation = contract.get("implementation")
    expected_implementation = {
        "provider_neutral_policy": str(PROVIDER_POLICY_PATH),
        "vultr_adapter": str(VULTR_ADAPTER_PATH),
        "live_execution": "forbidden_in_item_18",
        "first_live_vm_creation_item": 19,
    }
    if implementation != expected_implementation:
        errors.append("VM ownership implementation boundary differs from item-18 policy")

    binding = contract.get("binding")
    if not isinstance(binding, dict):
        errors.append("VM ownership binding must be an object")
    else:
        if binding.get("identity") != "provider-assigned immutable instance UUID/ID":
            errors.append("VM ownership binding must use provider-assigned immutable identity")
        if binding.get("ownership_intent") != "exact immutable lifecycle scope plus exact intent ID":
            errors.append("VM ownership binding must include exact immutable ownership intent")
        if "generation" not in binding or "compare_and_swap" not in binding:
            errors.append("VM ownership binding must define generation and compare-and-swap fencing")

    ownership = contract.get("required_ownership_metadata")
    if not isinstance(ownership, dict):
        errors.append("VM ownership metadata contract must be an object")
    else:
        if ownership.get("static") != REQUIRED_STATIC_METADATA:
            errors.append("VM ownership static metadata differs from exact mobile-proxy identity")
        if ownership.get("binding_fields") != REQUIRED_BINDING_FIELDS:
            errors.append("VM ownership binding metadata must be exact scope, intent and generation")
        if ownership.get("matching") != "exact_only":
            errors.append("VM ownership metadata matching must be exact-only")

    operations = contract.get("operations")
    if not isinstance(operations, dict) or set(operations) != REQUIRED_OPERATIONS:
        errors.append("VM ownership operations must contain the exact typed lifecycle operation set")
        operations = {}

    create = operations.get("create")
    if not isinstance(create, dict) or not all(
        create.get(field) is True
        for field in (
            "requires_no_existing_binding",
            "requires_zero_ownership_compatible_resources",
            "provider_request_must_set_exact_ownership_metadata",
            "provider_response_must_match_exact_ownership_metadata",
            "persist_binding_with_compare_and_swap_before_success",
        )
    ):
        errors.append("VM ownership create must be unbound, unique, exactly owned and CAS-persisted")

    for operation in ("manage", "stop", "reconfigure", "snapshot", "delete", "replace"):
        rule = operations.get(operation)
        if not isinstance(rule, dict) or not all(
            rule.get(field) is True
            for field in (
                "requires_persisted_binding",
                "requires_exact_provider_identity",
                "requires_exact_ownership_metadata",
                "requires_expected_generation",
            )
        ):
            errors.append(
                f"VM ownership {operation} must require binding, exact provider identity, exact ownership and generation"
            )

    delete = operations.get("delete")
    if not isinstance(delete, dict) or not all(
        delete.get(field) is True
        for field in (
            "clear_binding_only_after_provider_confirms_delete",
            "clear_binding_requires_compare_and_swap",
        )
    ):
        errors.append("VM ownership delete must retain and CAS-clear the binding after provider confirmation")

    replace = operations.get("replace")
    if not isinstance(replace, dict) or not all(
        replace.get(field) is True
        for field in (
            "replacement_generation_must_be_exactly_current_plus_one",
            "replacement_must_be_verified_before_binding_swap",
            "atomically_replace_provider_identity_and_generation_with_compare_and_swap",
        )
    ):
        errors.append("VM ownership replace must advance exactly one generation and CAS the verified identity")

    failures = contract.get("fail_closed")
    if not isinstance(failures, list) or set(failures) != REQUIRED_FAILURES:
        errors.append("VM ownership fail_closed set differs from the required item-18 failures")
    forbidden = contract.get("forbidden")
    if not isinstance(forbidden, list) or set(forbidden) != FORBIDDEN_BEHAVIOURS:
        errors.append("VM ownership forbidden set differs from the required item-18 behaviours")

    item_18 = contract.get("item_18_execution")
    if item_18 != {
        "allowed": "contract_policy_adapter_and_non_mutating_tests_only",
        "live_provider_mutation": False,
        "real_vm_creation": False,
        "production_vultr_authority": False,
        "phone_mutation": False,
    }:
        errors.append("item 18 execution boundary must remain non-mutating and non-production")

    if not isinstance(contract.get("activation_condition"), str) or not contract["activation_condition"]:
        errors.append("VM ownership contract requires a non-empty activation_condition")

    if topology is not None:
        migration = topology.get("migration_status")
        if not isinstance(migration, dict):
            errors.append("production topology migration_status must be an object")
        else:
            if migration.get("vultr_adapter") != (
                "implemented_typed_provider_neutral_ownership_and_generation_cas_non_mutating_item18"
            ):
                errors.append("production topology must keep item 18 Vultr adapter in implemented state")
            if migration.get("vultr_live_lifecycle") != "forbidden_until_item_19":
                errors.append("production topology must keep live Vultr lifecycle forbidden until item 19")

    if github is not None:
        if github.get("vm_ownership_contract") != str(CONTRACT_PATH):
            errors.append("GitHub control plane must bind the VM ownership contract")
        if github.get("vultr_lifecycle_adapter") != EXPECTED_ADAPTER_STATUS:
            errors.append("GitHub control plane item-18 Vultr lifecycle adapter status differs from protected state")
        acceptance = github.get("acceptance_vultr_environment")
        if not isinstance(acceptance, dict) or any(
            acceptance.get(key) != value
            for key, value in {
                "name": "acceptance-vultr",
                "authority": "pre_release_acceptance_read_only",
                "allowed_provider_api": "GET /v2/account only",
                "vm_lifecycle": "forbidden",
                "provider_mutation": "forbidden",
                "final_production_authority": False,
                "executor": "github-hosted",
            }.items()
        ):
            errors.append("item 18 must preserve the item-17 acceptance-vultr read-only boundary")

    document = document_path.read_text(encoding="utf-8")
    for required in (
        "provider-assigned immutable VM UUID/ID",
        "scope",
        "intent",
        "generation",
        "compare-and-swap",
        "fail closed",
        "item 19",
    ):
        if required not in document:
            errors.append(f"VM ownership architecture document is missing {required!r}")

    if provider_policy_path.is_file():
        policy = provider_policy_path.read_text(encoding="utf-8")
        for required in (
            "ProviderResourceId",
            "OwnershipIntent",
            "Generation",
            "VmBindingStore",
            "compare_and_swap",
            "VerifiedMutationTarget",
            "DuplicateOwnershipClaim",
            "NeighboringOrUnboundResource",
            "StaleGeneration",
        ):
            if required not in policy:
                errors.append(f"provider-neutral lifecycle policy is missing {required!r}")

    if vultr_adapter_path.is_file():
        adapter = vultr_adapter_path.read_text(encoding="utf-8")
        for required in (
            "Uuid::parse_str",
            "mobile-proxy:scope=",
            "mobile-proxy:intent=",
            "mobile-proxy:generation=",
            "VerifiedMutationTarget",
            "PlannedCreate",
            "ITEM18_LIVE_PROVIDER_MUTATION_ALLOWED: bool = false",
            "ITEM18_FINAL_PRODUCTION_AUTHORITY_ALLOWED: bool = false",
        ):
            if required not in adapter:
                errors.append(f"typed Vultr adapter is missing {required!r}")
        forbidden_adapter_tokens = (
            "std::env::var(\"VULTR_API_KEY\")",
            "environment: production-vultr",
            "Command::Vultr",
        )
        for token in forbidden_adapter_tokens:
            if token in adapter:
                errors.append(f"item-18 Vultr adapter exposes forbidden live authority token {token!r}")
    return errors


def main() -> int:
    errors = check_repository(Path(__file__).resolve().parents[1])
    for error in errors:
        print(error)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
