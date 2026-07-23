#!/usr/bin/env python3
"""Fail closed when first-party code introduces unapproved SHA-256 contracts."""

from __future__ import annotations

from pathlib import Path
import re

FIRST_PARTY_ROOTS = ("apps", "crates", "services")
FORBIDDEN_SOURCE_PATTERNS = (
    re.compile(r"\bSha256\b"),
    re.compile(r"\bsha2::"),
    re.compile(r"checksums\.sha256"),
    re.compile(r"\bSHA256SUMS\b"),
)
SHA2_DEPENDENCY = re.compile(r"^\s*sha2(?:\s*=|\.workspace\s*=)", re.MULTILINE)


def check_repository(root: Path) -> list[str]:
    errors: list[str] = []
    for top_level in FIRST_PARTY_ROOTS:
        base = root / top_level
        if not base.is_dir():
            continue
        for manifest in sorted(base.rglob("Cargo.toml")):
            body = manifest.read_text(encoding="utf-8")
            if SHA2_DEPENDENCY.search(body):
                errors.append(
                    f"{manifest.relative_to(root)}: first-party sha2 dependency is forbidden"
                )
        for source in sorted(base.rglob("*.rs")):
            body = source.read_text(encoding="utf-8")
            for pattern in FORBIDDEN_SOURCE_PATTERNS:
                if pattern.search(body):
                    errors.append(
                        f"{source.relative_to(root)}: unapproved internal SHA-256 usage {pattern.pattern!r}"
                    )
    return errors
