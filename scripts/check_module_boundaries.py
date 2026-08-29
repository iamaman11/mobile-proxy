#!/usr/bin/env python3
"""Fail closed when the Rust workspace drifts from declared module boundaries."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import tomllib

CONTRACT_PATH = Path("contracts/governance/module-boundaries-v1.json")
EXPECTED_POLICIES = {
    "unknown_workspace_member": "reject",
    "undeclared_internal_dependency": "reject",
    "stale_allowed_dependency": "reject",
    "dependency_cycle": "reject",
}


def _load_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def _dependency_tables(manifest: object):
    if not isinstance(manifest, dict):
        return
    for key, value in manifest.items():
        if key in {"dependencies", "dev-dependencies", "build-dependencies"} and isinstance(
            value, dict
        ):
            yield value
        elif isinstance(value, dict):
            yield from _dependency_tables(value)


def _dependency_package_name(alias: str, spec: object) -> str:
    if isinstance(spec, dict) and isinstance(spec.get("package"), str):
        return spec["package"]
    return alias


def _find_cycle(graph: dict[str, set[str]]) -> list[str] | None:
    visited: set[str] = set()
    active: set[str] = set()
    stack: list[str] = []

    def visit(node: str) -> list[str] | None:
        if node in active:
            start = stack.index(node)
            return [*stack[start:], node]
        if node in visited:
            return None
        active.add(node)
        stack.append(node)
        for dependency in sorted(graph.get(node, set())):
            cycle = visit(dependency)
            if cycle is not None:
                return cycle
        stack.pop()
        active.remove(node)
        visited.add(node)
        return None

    for node in sorted(graph):
        cycle = visit(node)
        if cycle is not None:
            return cycle
    return None


def validate_repository(root: Path) -> list[str]:
    root = root.resolve()
    errors: list[str] = []
    contract_file = root / CONTRACT_PATH
    if not contract_file.is_file():
        return [f"missing module-boundary contract: {CONTRACT_PATH}"]

    try:
        contract = _load_json(contract_file)
    except (OSError, json.JSONDecodeError) as exc:
        return [f"cannot parse module-boundary contract: {exc}"]
    if not isinstance(contract, dict):
        return ["module-boundary contract root must be an object"]

    if contract.get("schema_version") != 1:
        errors.append("module-boundary schema_version must be 1")
    if contract.get("status") != "normative":
        errors.append("module-boundary contract status must be normative")
    standard = contract.get("architecture_standard")
    if not isinstance(standard, str) or not standard or not (root / standard).is_file():
        errors.append("module-boundary contract must reference the architecture standard")
    if contract.get("policies") != EXPECTED_POLICIES:
        errors.append("module-boundary policies must remain fail-closed")

    workspace_manifest = contract.get("workspace_manifest")
    if not isinstance(workspace_manifest, str) or not workspace_manifest:
        errors.append("workspace_manifest must be a non-empty path")
        return errors
    workspace_file = root / workspace_manifest
    if not workspace_file.is_file():
        errors.append(f"workspace manifest does not exist: {workspace_manifest}")
        return errors
    try:
        workspace = tomllib.loads(workspace_file.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        errors.append(f"cannot parse workspace manifest: {exc}")
        return errors
    raw_members = workspace.get("workspace", {}).get("members") if isinstance(workspace, dict) else None
    if not isinstance(raw_members, list) or any(not isinstance(item, str) for item in raw_members):
        errors.append("workspace.members must be a string array")
        return errors
    workspace_members = set(raw_members)

    raw_modules = contract.get("modules")
    if not isinstance(raw_modules, list) or not raw_modules:
        errors.append("module-boundary contract requires a non-empty modules array")
        return errors

    modules_by_path: dict[str, dict[str, object]] = {}
    modules_by_package: dict[str, dict[str, object]] = {}
    for index, module in enumerate(raw_modules):
        if not isinstance(module, dict):
            errors.append(f"module {index} must be an object")
            continue
        path = module.get("path")
        package = module.get("package")
        role = module.get("role")
        allowed = module.get("allowed_internal_dependencies")
        if not isinstance(path, str) or not path:
            errors.append(f"module {index} has no path")
            continue
        if not isinstance(package, str) or not package:
            errors.append(f"{path}: package must be non-empty")
            continue
        if not isinstance(role, str) or not role:
            errors.append(f"{path}: role must be non-empty")
        if not isinstance(allowed, list) or any(not isinstance(item, str) for item in allowed):
            errors.append(f"{path}: allowed_internal_dependencies must be a string array")
            allowed = []
        if len(set(allowed)) != len(allowed):
            errors.append(f"{path}: allowed_internal_dependencies contains duplicates")
        if path in modules_by_path:
            errors.append(f"duplicate module path: {path}")
        if package in modules_by_package:
            errors.append(f"duplicate module package: {package}")
        modules_by_path[path] = module
        modules_by_package[package] = module

    declared_paths = set(modules_by_path)
    if declared_paths != workspace_members:
        errors.append(
            "Rust workspace classification differs: "
            f"missing={sorted(workspace_members - declared_paths)} "
            f"extra={sorted(declared_paths - workspace_members)}"
        )

    graph: dict[str, set[str]] = {}
    internal_packages = set(modules_by_package)
    for path, module in modules_by_path.items():
        package = module.get("package")
        if not isinstance(package, str):
            continue
        manifest_file = root / path / "Cargo.toml"
        if not manifest_file.is_file():
            errors.append(f"{path}: missing Cargo.toml")
            graph[package] = set()
            continue
        try:
            manifest = tomllib.loads(manifest_file.read_text(encoding="utf-8"))
        except (OSError, tomllib.TOMLDecodeError) as exc:
            errors.append(f"{path}: cannot parse Cargo.toml: {exc}")
            graph[package] = set()
            continue
        actual_package = manifest.get("package", {}).get("name") if isinstance(manifest, dict) else None
        if actual_package != package:
            errors.append(
                f"{path}: package mismatch, contract={package!r} Cargo.toml={actual_package!r}"
            )

        actual_internal: set[str] = set()
        for dependencies in _dependency_tables(manifest):
            for alias, spec in dependencies.items():
                dependency_package = _dependency_package_name(alias, spec)
                if dependency_package in internal_packages:
                    actual_internal.add(dependency_package)

        raw_allowed = module.get("allowed_internal_dependencies")
        allowed = set(raw_allowed) if isinstance(raw_allowed, list) else set()
        unknown_allowed = allowed - internal_packages
        if unknown_allowed:
            errors.append(f"{path}: allowed dependencies are not declared modules: {sorted(unknown_allowed)}")
        forbidden = actual_internal - allowed
        stale = allowed - actual_internal
        if forbidden:
            errors.append(f"{path}: undeclared internal dependencies: {sorted(forbidden)}")
        if stale:
            errors.append(f"{path}: stale allowed internal dependencies: {sorted(stale)}")
        if package in actual_internal:
            errors.append(f"{path}: self dependency is forbidden")
        graph[package] = actual_internal

    cycle = _find_cycle(graph)
    if cycle is not None:
        errors.append(f"internal dependency cycle: {' -> '.join(cycle)}")
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
        print("module-boundary validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print("module-boundary validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
