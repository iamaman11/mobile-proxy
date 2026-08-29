#!/usr/bin/env python3
"""Validate registered authoritative mutable-state ownership fail closed."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re

CONTRACT_PATH = Path("contracts/governance/state-ownership-v1.json")
EXPECTED_POLICIES = {
    "duplicate_resource_owner": "reject",
    "unknown_owner_module": "reject",
    "writer_outside_owner": "reject",
    "durable_state_without_persistence_owner": "reject",
}
ALLOWED_STORAGE = {"ephemeral", "sqlite", "durable_file"}
IDENTIFIER = re.compile(r"^[a-z][a-z0-9_]{0,95}$")
GROUP_ID = re.compile(r"^[a-z][a-z0-9-]{0,95}$")


def _load_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def _within(path: str, root: str) -> bool:
    path_obj = Path(path)
    root_obj = Path(root)
    try:
        path_obj.relative_to(root_obj)
        return True
    except ValueError:
        return False


def validate_repository(root: Path, contract_path: Path | None = None) -> list[str]:
    root = root.resolve()
    errors: list[str] = []
    contract_file = contract_path or root / CONTRACT_PATH
    if not contract_file.is_file():
        return [f"missing state-ownership contract: {contract_file}"]
    try:
        contract = _load_json(contract_file)
    except (OSError, json.JSONDecodeError) as exc:
        return [f"cannot parse state-ownership contract: {exc}"]
    if not isinstance(contract, dict):
        return ["state-ownership contract root must be an object"]

    if contract.get("schema_version") != 1:
        errors.append("state-ownership schema_version must be 1")
    if contract.get("status") != "normative":
        errors.append("state-ownership contract status must be normative")
    if contract.get("scope") != "current_authoritative_and_operational_mutable_state":
        errors.append("state-ownership scope must remain explicit and bounded")
    if contract.get("policies") != EXPECTED_POLICIES:
        errors.append("state-ownership policies must remain fail-closed")

    architecture_standard = contract.get("architecture_standard")
    if (
        not isinstance(architecture_standard, str)
        or not architecture_standard
        or not (root / architecture_standard).is_file()
    ):
        errors.append("state-ownership contract must reference the architecture standard")

    module_contract_path = contract.get("module_boundaries")
    if not isinstance(module_contract_path, str) or not module_contract_path:
        errors.append("state-ownership contract must reference module boundaries")
        return errors
    module_contract_file = root / module_contract_path
    if not module_contract_file.is_file():
        errors.append(f"module-boundary contract does not exist: {module_contract_path}")
        return errors
    try:
        module_contract = _load_json(module_contract_file)
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"cannot parse module-boundary contract: {exc}")
        return errors
    raw_modules = module_contract.get("modules") if isinstance(module_contract, dict) else None
    if not isinstance(raw_modules, list):
        errors.append("module-boundary contract modules must be an array")
        return errors
    known_modules = {
        module.get("path")
        for module in raw_modules
        if isinstance(module, dict) and isinstance(module.get("path"), str)
    }

    groups = contract.get("state_groups")
    if not isinstance(groups, list) or not groups:
        errors.append("state-ownership contract requires a non-empty state_groups array")
        return errors

    seen_group_ids: set[str] = set()
    resource_owners: dict[str, str] = {}
    for index, group in enumerate(groups):
        if not isinstance(group, dict):
            errors.append(f"state group {index} must be an object")
            continue
        group_id = group.get("id")
        if not isinstance(group_id, str) or GROUP_ID.fullmatch(group_id) is None:
            errors.append(f"state group {index} has invalid id")
            continue
        if group_id in seen_group_ids:
            errors.append(f"duplicate state group id: {group_id}")
        seen_group_ids.add(group_id)

        authority = group.get("authority_module")
        if not isinstance(authority, str) or authority not in known_modules:
            errors.append(f"{group_id}: unknown authority module {authority!r}")
            authority = ""
        storage = group.get("storage")
        if storage not in ALLOWED_STORAGE:
            errors.append(f"{group_id}: unsupported storage {storage!r}")

        persistence_owner = group.get("persistence_owner_module")
        if storage == "ephemeral":
            if persistence_owner is not None:
                errors.append(f"{group_id}: ephemeral state must not name a persistence owner")
        else:
            if not isinstance(persistence_owner, str) or persistence_owner not in known_modules:
                errors.append(
                    f"{group_id}: durable state requires a known persistence owner module"
                )

        policy_modules = group.get("policy_modules")
        if not isinstance(policy_modules, list) or any(
            not isinstance(item, str) for item in policy_modules
        ):
            errors.append(f"{group_id}: policy_modules must be a string array")
            policy_modules = []
        for policy_module in policy_modules:
            if policy_module not in known_modules:
                errors.append(f"{group_id}: unknown policy module {policy_module!r}")

        resources = group.get("resources")
        if not isinstance(resources, list) or not resources or any(
            not isinstance(item, str) for item in resources
        ):
            errors.append(f"{group_id}: resources must be a non-empty string array")
            resources = []
        if len(set(resources)) != len(resources):
            errors.append(f"{group_id}: resources contains duplicates")
        for resource in resources:
            if IDENTIFIER.fullmatch(resource) is None:
                errors.append(f"{group_id}: invalid resource identifier {resource!r}")
                continue
            previous = resource_owners.get(resource)
            if previous is not None:
                errors.append(
                    f"resource {resource!r} has multiple owners: {previous}, {group_id}"
                )
            resource_owners[resource] = group_id

        writer_paths = group.get("writer_paths")
        if not isinstance(writer_paths, list) or not writer_paths or any(
            not isinstance(item, str) for item in writer_paths
        ):
            errors.append(f"{group_id}: writer_paths must be a non-empty string array")
            writer_paths = []
        for relative in writer_paths:
            if not (root / relative).exists():
                errors.append(f"{group_id}: writer path does not exist: {relative}")
            if authority and not _within(relative, authority):
                errors.append(
                    f"{group_id}: writer path escapes authority module {authority}: {relative}"
                )

        persistence_paths = group.get("persistence_writer_paths")
        if not isinstance(persistence_paths, list) or any(
            not isinstance(item, str) for item in persistence_paths
        ):
            errors.append(f"{group_id}: persistence_writer_paths must be a string array")
            persistence_paths = []
        if storage != "ephemeral" and not persistence_paths:
            errors.append(f"{group_id}: durable state requires persistence writer paths")
        if storage == "ephemeral" and persistence_paths:
            errors.append(f"{group_id}: ephemeral state must not have persistence writer paths")
        for relative in persistence_paths:
            if not (root / relative).exists():
                errors.append(f"{group_id}: persistence writer path does not exist: {relative}")
            if isinstance(persistence_owner, str) and not _within(relative, persistence_owner):
                errors.append(
                    f"{group_id}: persistence writer path escapes persistence owner "
                    f"{persistence_owner}: {relative}"
                )

        migration_paths = group.get("migration_writer_paths")
        if not isinstance(migration_paths, list) or any(
            not isinstance(item, str) for item in migration_paths
        ):
            errors.append(f"{group_id}: migration_writer_paths must be a string array")
            migration_paths = []
        for relative in migration_paths:
            if not (root / relative).exists():
                errors.append(f"{group_id}: migration writer path does not exist: {relative}")
            allowed_roots = {authority}
            if isinstance(persistence_owner, str):
                allowed_roots.add(persistence_owner)
            if not any(root_name and _within(relative, root_name) for root_name in allowed_roots):
                errors.append(
                    f"{group_id}: migration writer path escapes declared owner modules: {relative}"
                )

        evidence_paths = group.get("evidence_paths")
        if not isinstance(evidence_paths, list) or not evidence_paths or any(
            not isinstance(item, str) for item in evidence_paths
        ):
            errors.append(f"{group_id}: evidence_paths must be a non-empty string array")
            evidence_paths = []
        for relative in evidence_paths:
            if not (root / relative).exists():
                errors.append(f"{group_id}: evidence path does not exist: {relative}")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
    )
    args = parser.parse_args()
    errors = validate_repository(args.repo_root)
    if errors:
        print("state-ownership validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print("state-ownership validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
