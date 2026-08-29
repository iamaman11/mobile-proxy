#!/usr/bin/env python3
"""Validate the fail-closed VM ownership contract for shared cloud accounts."""

from __future__ import annotations

import json
from pathlib import Path


CONTRACT_PATH = Path("contracts/governance/vm-ownership-v1.json")
DOCUMENT_PATH = Path("docs/architecture/vm-ownership-boundary.md")
REQUIRED_TAGS = {"project": "mobile-proxy", "managed-by": "mobile-proxy"}
REQUIRED_OPERATIONS = {"create", "manage", "snapshot", "delete", "recreate"}
REQUIRED_FAILURES = {
    "missing_binding",
    "invalid_binding",
    "provider_instance_not_found",
    "uuid_mismatch",
    "required_tag_missing",
    "required_tag_mismatch",
    "binding_compare_and_swap_conflict",
}
FORBIDDEN_BEHAVIOURS = {
    "arbitrary_instance_uuid_from_operator_input",
    "first_matching_instance_selection",
    "label_or_name_as_authority",
    "operation_after_identity_or_tag_verification_failure",
    "unverified_binding_replacement",
}


def check_repository(root: Path) -> list[str]:
    errors: list[str] = []
    contract_path = root / CONTRACT_PATH
    document_path = root / DOCUMENT_PATH
    if not contract_path.is_file():
        return [f"missing VM ownership contract: {CONTRACT_PATH}"]
    if not document_path.is_file():
        return [f"missing VM ownership architecture document: {DOCUMENT_PATH}"]
    try:
        contract = json.loads(contract_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        return [f"cannot parse VM ownership contract: {error}"]
    if not isinstance(contract, dict):
        return ["VM ownership contract root must be an object"]
    if contract.get("contract_version") != 1:
        errors.append("VM ownership contract_version must be 1")
    if contract.get("status") != "protected":
        errors.append("VM ownership contract status must be protected")
    if contract.get("owner") != "operator-cli":
        errors.append("VM ownership contract owner must be operator-cli")
    if contract.get("required_tags") != REQUIRED_TAGS:
        errors.append("VM ownership required_tags must be the exact mobile-proxy ownership tags")
    binding = contract.get("binding")
    if not isinstance(binding, dict):
        errors.append("VM ownership binding must be an object")
    elif binding.get("identity") != "provider-assigned immutable instance UUID":
        errors.append("VM ownership binding must use a provider-assigned immutable instance UUID")

    operations = contract.get("operations")
    if not isinstance(operations, dict) or set(operations) != REQUIRED_OPERATIONS:
        errors.append("VM ownership operations must contain exactly create, manage, snapshot, delete and recreate")
        operations = {}
    for operation in ("manage", "snapshot", "delete"):
        rule = operations.get(operation)
        if not isinstance(rule, dict) or not all(
            rule.get(field) is True
            for field in ("requires_persisted_binding", "requires_exact_uuid", "requires_exact_required_tags")
        ):
            errors.append(f"VM ownership {operation} must require binding, exact UUID and exact tags")
    create = operations.get("create")
    if not isinstance(create, dict) or not all(
        create.get(field) is True
        for field in (
            "provider_request_must_set_required_tags",
            "provider_response_must_match_required_tags",
            "persist_binding_before_success",
        )
    ):
        errors.append("VM ownership create must tag, verify and persist before success")
    delete = operations.get("delete")
    if not isinstance(delete, dict) or delete.get("clear_binding_only_after_provider_confirms_delete") is not True:
        errors.append("VM ownership delete must retain binding until provider deletion succeeds")
    recreate = operations.get("recreate")
    if not isinstance(recreate, dict) or not all(
        recreate.get(field) is True
        for field in (
            "provider_request_must_set_required_tags",
            "provider_response_must_match_required_tags",
            "atomically_replace_uuid_and_generation_after_verification",
        )
    ):
        errors.append("VM ownership recreate must verify tags and atomically replace the binding")

    failures = contract.get("fail_closed")
    if not isinstance(failures, list) or set(failures) != REQUIRED_FAILURES:
        errors.append("VM ownership fail_closed set differs from the required fail-closed failures")
    forbidden = contract.get("forbidden")
    if not isinstance(forbidden, list) or set(forbidden) != FORBIDDEN_BEHAVIOURS:
        errors.append("VM ownership forbidden set differs from the required forbidden behaviours")
    if not isinstance(contract.get("activation_condition"), str) or not contract["activation_condition"]:
        errors.append("VM ownership contract requires a non-empty activation_condition")

    document = document_path.read_text(encoding="utf-8")
    for required in (
        "provider-assigned immutable VM UUID",
        "project=mobile-proxy",
        "managed-by=mobile-proxy",
        "fail closed",
        "atomically replace UUID and generation",
    ):
        if required not in document:
            errors.append(f"VM ownership architecture document is missing {required!r}")
    return errors
