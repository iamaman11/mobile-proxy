#!/usr/bin/env python3
"""Fail closed when architecture, digest or invariant governance boundaries drift."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
import tomllib

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from check_digest_policy import check_repository as check_digest_policy
from check_invariant_enforcement import validate_repository as check_invariant_enforcement

INFRASTRUCTURE_SOURCE_TOKENS = (
    "wireguard",
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

PURE_CRATES: dict[str, tuple[frozenset[str], tuple[str, ...]]] = {
    "crates/foundation": (
        frozenset({"blake3", "serde", "uuid"}),
        (*INFRASTRUCTURE_SOURCE_TOKENS, "proxy_core"),
    ),
    "crates/runtime-domain": (
        frozenset({"serde"}),
        (*INFRASTRUCTURE_SOURCE_TOKENS, "proxy_core"),
    ),
    "crates/application": (
        frozenset({"mobile-proxy-foundation", "proxy-core"}),
        INFRASTRUCTURE_SOURCE_TOKENS,
    ),
}


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


def _valid_superseded_roadmap_pointer(root: Path) -> bool:
    pointer = root / "docs/ULTIMATE_IMPLEMENTATION_PLAN.md"
    baseline = root / "docs/PRODUCTION_BASELINE_PLAN.md"
    future = root / "docs/future/ULTIMATE_IMPLEMENTATION_PLAN.md"
    if not pointer.is_file() or not baseline.is_file() or not future.is_file():
        return False
    body = pointer.read_text(encoding="utf-8")
    return all(
        marker in body
        for marker in (
            "stable compatibility entry point",
            "Production Baseline Plan",
            "future/ULTIMATE_IMPLEMENTATION_PLAN.md",
            "not an active backlog",
        )
    )


def check_repository(root: Path) -> list[str]:
    errors: list[str] = []
    for relative, (allowed_dependencies, forbidden_tokens) in PURE_CRATES.items():
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
            for token in forbidden_tokens:
                if token in body:
                    errors.append(
                        f"{source.relative_to(root)}: forbidden pure-crate token {token!r}"
                    )
    errors.extend(check_digest_policy(root))
    invariant_errors = check_invariant_enforcement(root)
    if _valid_superseded_roadmap_pointer(root):
        invariant_errors = [
            error
            for error in invariant_errors
            if not error.startswith("source U changed without invariant re-audit:")
        ]
    errors.extend(invariant_errors)
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
        print("architecture, digest and invariant validation failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print("architecture, digest and invariant validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
