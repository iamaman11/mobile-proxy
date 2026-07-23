#!/usr/bin/env python3
"""Fail closed when pure crates gain infrastructure dependencies or vocabulary."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
import tomllib

PURE_CRATES: dict[str, frozenset[str]] = {
    "crates/foundation": frozenset({"blake3", "serde", "uuid"}),
    "crates/runtime-domain": frozenset({"serde"}),
}

FORBIDDEN_SOURCE_TOKENS = (
    "wireguard",
    "proxy_core",
    "axum",
    "tonic",
    "sqlx",
    "rusqlite",
    "reqwest",
    "tokio",
    "std::fs",
    "std::net",
    "std::process",
    "std::env",
    "systemtime",
    "instant::now",
    "new_v4",
    "getrandom",
    "android",
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


def check_repository(root: Path) -> list[str]:
    errors: list[str] = []
    for relative, allowed_dependencies in PURE_CRATES.items():
        crate = root / relative
        manifest_path = crate / "Cargo.toml"
        if not manifest_path.is_file():
            errors.append(f"{relative}: missing Cargo.toml")
            continue

        manifest = tomllib.loads(manifest_path.read_text(encoding="utf-8"))
        for table_name, dependencies in dependency_tables(manifest):
            for dependency in dependencies:
                normalized = dependency.replace("-", "_")
                allowed = {item.replace("-", "_") for item in allowed_dependencies}
                if normalized not in allowed:
                    errors.append(
                        f"{relative}: forbidden dependency {dependency!r} in {table_name}"
                    )

        source_root = crate / "src"
        if not source_root.is_dir():
            errors.append(f"{relative}: missing src directory")
            continue
        for source in sorted(source_root.rglob("*.rs")):
            body = source.read_text(encoding="utf-8").lower()
            for token in FORBIDDEN_SOURCE_TOKENS:
                if token in body:
                    errors.append(
                        f"{source.relative_to(root)}: forbidden pure-crate token {token!r}"
                    )
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
    )
    args = parser.parse_args()
    errors = check_repository(args.repo_root.resolve())
    if errors:
        print("architecture boundary validation failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print("architecture boundary validation passed for foundation and runtime-domain")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
