#!/usr/bin/env python3
"""Fail closed when first-party code introduces unapproved SHA-256 contracts."""

from __future__ import annotations

from pathlib import Path
import re
import tomllib

FIRST_PARTY_ROOTS = ("apps", "crates", "services")
FORBIDDEN_PACKAGES = frozenset({"sha2", "sha256"})
FORBIDDEN_SOURCE_PATTERNS = (
    re.compile(r"\bsha2::", re.IGNORECASE),
    re.compile(r"\bsha[-_]?256\b", re.IGNORECASE),
    re.compile(r"\bSHA256SUMS\b"),
)


def dependency_tables(node: object, path: tuple[str, ...] = ()):
    if not isinstance(node, dict):
        return
    for key, value in node.items():
        next_path = (*path, key)
        if key in {"dependencies", "dev-dependencies", "build-dependencies"} and isinstance(
            value, dict
        ):
            yield ".".join(next_path), value
        else:
            yield from dependency_tables(value, next_path)


def dependency_package(name: str, specification: object) -> str:
    if isinstance(specification, dict):
        package = specification.get("package")
        if isinstance(package, str):
            return package
    return name


def normalized_package(name: str) -> str:
    return name.strip().lower().replace("_", "-")


def check_repository(root: Path) -> list[str]:
    errors: list[str] = []
    for top_level in FIRST_PARTY_ROOTS:
        base = root / top_level
        if not base.is_dir():
            continue
        for manifest in sorted(base.rglob("Cargo.toml")):
            parsed = tomllib.loads(manifest.read_text(encoding="utf-8"))
            for table_name, dependencies in dependency_tables(parsed):
                for dependency_name, specification in dependencies.items():
                    package = normalized_package(
                        dependency_package(dependency_name, specification)
                    )
                    if package in FORBIDDEN_PACKAGES:
                        errors.append(
                            f"{manifest.relative_to(root)}: forbidden first-party digest package "
                            f"{package!r} in {table_name}"
                        )
        for source in sorted(base.rglob("*.rs")):
            body = source.read_text(encoding="utf-8")
            for pattern in FORBIDDEN_SOURCE_PATTERNS:
                if pattern.search(body):
                    errors.append(
                        f"{source.relative_to(root)}: unapproved internal SHA-256 usage "
                        f"{pattern.pattern!r}"
                    )
    return errors
