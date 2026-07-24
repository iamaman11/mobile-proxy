#!/usr/bin/env python3
"""Fail closed when first-party code introduces unapproved digest contracts."""

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
LEGACY_RUNTIME_FINGERPRINT_ENV = "HOST_DAEMON_BINARY_FINGERPRINT"
UNTYPED_RUNTIME_FINGERPRINT = re.compile(
    r"\b(?:config_fingerprint|binary_fingerprint)\s*:\s*(?:Option\s*<\s*)?String\s*>?"
)
REQUIRED_FINGERPRINT_ENFORCEMENT_FRAGMENTS = {
    "crates/proxy-core/src/fingerprints.rs": (
        'DigestDomain::new("mobile-proxy/host-daemon-nonsecret-config/v1")',
        'DigestDomain::new("mobile-proxy/host-daemon-binary/v1")',
        "ConfigFingerprintInput",
        "BinaryFingerprintInput",
    ),
    "crates/proxy-core/src/records.rs": (
        "pub config_fingerprint: Option<ConfigFingerprint>",
        "pub binary_fingerprint: Option<BinaryFingerprint>",
    ),
    "services/host-daemon/src/fingerprints.rs": (
        "config_source_fingerprint",
        "current_binary_fingerprint",
        'Path::new("/proc/self/exe")',
    ),
    "crates/control-plane-sqlite/src/legacy_json_import.rs": (
        "LegacyJsonMigrationStats",
        "ConfigFingerprintInput",
        "BinaryFingerprintInput",
        "fingerprint_stats",
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
            if UNTYPED_RUNTIME_FINGERPRINT.search(body):
                errors.append(
                    f"{source.relative_to(root)}: runtime fingerprints must use typed contracts"
                )
            if LEGACY_RUNTIME_FINGERPRINT_ENV in body:
                errors.append(
                    f"{source.relative_to(root)}: legacy environment-provided binary fingerprint is forbidden"
                )

    config_root = root / "config"
    if config_root.is_dir():
        for path in sorted(config_root.rglob("*")):
            if path.is_file() and LEGACY_RUNTIME_FINGERPRINT_ENV in path.read_text(
                encoding="utf-8", errors="ignore"
            ):
                errors.append(
                    f"{path.relative_to(root)}: legacy environment-provided binary fingerprint is forbidden"
                )

    for relative, fragments in REQUIRED_FINGERPRINT_ENFORCEMENT_FRAGMENTS.items():
        path = root / relative
        if not path.is_file():
            errors.append(f"{relative}: missing fingerprint enforcement file")
            continue
        body = path.read_text(encoding="utf-8")
        for fragment in fragments:
            if fragment not in body:
                errors.append(
                    f"{relative}: missing fingerprint enforcement fragment {fragment!r}"
                )
    return errors
