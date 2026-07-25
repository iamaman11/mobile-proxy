#!/usr/bin/env python3
"""Fail closed when first-party source introduces an unapproved digest contract."""

from __future__ import annotations

from pathlib import Path
import re
import tomllib

FIRST_PARTY_ROOTS = ("apps", "crates", "services", "scripts", "deploy")
RUST_PACKAGE_ROOTS = ("apps", "crates", "services")
SOURCE_SUFFIXES = frozenset({".rs", ".py", ".sh", ".kt", ".kts"})
FORBIDDEN_PACKAGES = frozenset({"sha2", "sha256"})
DIRECT_BLAKE3_PACKAGE = "blake3"
DIRECT_BLAKE3_ALLOWED_MANIFEST = Path("crates/foundation/Cargo.toml")
EXCLUDED_SOURCE_FILES = frozenset(
    {
        Path("scripts/check_digest_policy.py"),
        Path("scripts/tests/test_digest_policy.py"),
    }
)
FORBIDDEN_SOURCE_PATTERNS = (
    (re.compile(r"\bsha2::", re.IGNORECASE), "direct Rust SHA-256 primitive"),
    (re.compile(r"\bSha256\s*::"), "direct Rust SHA-256 primitive"),
    (re.compile(r"\bhashlib\s*\.\s*sha256\s*\(", re.IGNORECASE), "direct Python SHA-256 primitive"),
    (
        re.compile(r"\bhashlib\s*\.\s*new\s*\(\s*['\"]sha-?256['\"]", re.IGNORECASE),
        "direct Python SHA-256 primitive",
    ),
    (re.compile(r"\bsha256sum\b", re.IGNORECASE), "direct shell SHA-256 primitive"),
    (
        re.compile(r"\bopenssl\s+dgst\s+-sha256\b", re.IGNORECASE),
        "direct shell SHA-256 primitive",
    ),
    (
        re.compile(r"MessageDigest\s*\.\s*getInstance\s*\(\s*['\"]SHA-256['\"]", re.IGNORECASE),
        "direct JVM SHA-256 primitive",
    ),
    (re.compile(r"\bSHA256SUMS\b"), "legacy release checksum contract"),
    (re.compile(r"\bchecksums\.sha256\b", re.IGNORECASE), "legacy release checksum contract"),
    (re.compile(r"\bconfig_sha256\b"), "untyped internal SHA-256 contract"),
    (re.compile(r"\bimport\s+blake3\b"), "direct untyped Python BLAKE3 primitive"),
    (re.compile(r"\bfrom\s+blake3\s+import\b"), "direct untyped Python BLAKE3 primitive"),
    (re.compile(r"\bb3sum\b"), "direct untyped shell BLAKE3 primitive"),
)
LEGACY_RUNTIME_FINGERPRINT_ENV = "HOST_DAEMON_BINARY_FINGERPRINT"
UNTYPED_RUNTIME_FINGERPRINT = re.compile(
    r"\b(?:config_fingerprint|binary_fingerprint)\s*:\s*(?:Option\s*<\s*)?String\s*>?"
)
REQUIRED_ENFORCEMENT_FRAGMENTS = {
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
    "scripts/verify_physical_deployment.py": (
        '"comparison_contract": "exact-bytes"',
        "remote_bytes == (root / relative).read_bytes()",
        "cmp -s --",
    ),
    "scripts/switch_vm_proxy_transport.py": (
        '"exact_config_match": True',
        "sudo cmp -s --",
    ),
}


def dependency_tables(node: object, path: tuple[str, ...] = ()):
    if not isinstance(node, dict):
        return
    for key, value in node.items():
        next_path = (*path, key)
        if key in {"dependencies", "dev-dependencies", "build-dependencies"} and isinstance(value, dict):
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


def _source_files(root: Path):
    for top_level in FIRST_PARTY_ROOTS:
        base = root / top_level
        if not base.is_dir():
            continue
        for source in sorted(base.rglob("*")):
            if not source.is_file() or source.suffix not in SOURCE_SUFFIXES:
                continue
            relative = source.relative_to(root)
            if relative in EXCLUDED_SOURCE_FILES:
                continue
            yield relative, source


def check_repository(root: Path) -> list[str]:
    errors: list[str] = []
    for top_level in RUST_PACKAGE_ROOTS:
        base = root / top_level
        if not base.is_dir():
            continue
        for manifest in sorted(base.rglob("Cargo.toml")):
            parsed = tomllib.loads(manifest.read_text(encoding="utf-8"))
            relative_manifest = manifest.relative_to(root)
            for table_name, dependencies in dependency_tables(parsed):
                for dependency_name, specification in dependencies.items():
                    package = normalized_package(dependency_package(dependency_name, specification))
                    if package in FORBIDDEN_PACKAGES:
                        errors.append(
                            f"{relative_manifest}: forbidden first-party digest package {package!r} in {table_name}"
                        )
                    if package == DIRECT_BLAKE3_PACKAGE and relative_manifest != DIRECT_BLAKE3_ALLOWED_MANIFEST:
                        errors.append(
                            f"{relative_manifest}: direct BLAKE3 dependency is forbidden outside typed foundation in {table_name}"
                        )

    for relative, source in _source_files(root):
        body = source.read_text(encoding="utf-8", errors="ignore")
        for pattern, description in FORBIDDEN_SOURCE_PATTERNS:
            if pattern.search(body):
                errors.append(f"{relative}: {description} is forbidden ({pattern.pattern!r})")
        if source.suffix == ".rs" and UNTYPED_RUNTIME_FINGERPRINT.search(body):
            errors.append(f"{relative}: runtime fingerprints must use typed contracts")
        if LEGACY_RUNTIME_FINGERPRINT_ENV in body:
            errors.append(f"{relative}: legacy environment-provided binary fingerprint is forbidden")

    config_root = root / "config"
    if config_root.is_dir():
        for path in sorted(config_root.rglob("*")):
            if path.is_file() and LEGACY_RUNTIME_FINGERPRINT_ENV in path.read_text(
                encoding="utf-8", errors="ignore"
            ):
                errors.append(
                    f"{path.relative_to(root)}: legacy environment-provided binary fingerprint is forbidden"
                )

    for relative, fragments in REQUIRED_ENFORCEMENT_FRAGMENTS.items():
        path = root / relative
        if not path.is_file():
            errors.append(f"{relative}: missing digest enforcement file")
            continue
        body = path.read_text(encoding="utf-8")
        for fragment in fragments:
            if fragment not in body:
                errors.append(f"{relative}: missing digest enforcement fragment {fragment!r}")
    return errors
