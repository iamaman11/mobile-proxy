#!/usr/bin/env python3
from __future__ import annotations

from collections import Counter
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
SKIP_DIRS = {".git", "target", ".idea", ".vscode", "node_modules"}
TEXT_SUFFIXES = {".rs", ".py", ".sh", ".yml", ".yaml", ".json", ".toml", ".md", ".kt", ".kts", ".java"}
PATTERNS = {
    "sha_api": re.compile(r"(?i)\b(?:sha2|sha256|sha-256|sha256sum|shasum)\b"),
    "digest_symbol": re.compile(r"(?i)\b(?:digest|checksum|fingerprint|hash)\b"),
    "persisted_field": re.compile(r"(?i)\b(?:config_fingerprint|binary_fingerprint|descriptor_fingerprint|endpoint_fingerprint|payload_digest|state_digest|audit_digest|checksum|sha256)\b"),
    "bare_hex64": re.compile(r"(?<![0-9a-fA-F])[0-9a-fA-F]{64}(?![0-9a-fA-F])"),
}


def iter_files():
    for path in sorted(ROOT.rglob("*")):
        if not path.is_file() or any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.name == "Cargo.lock" or path.suffix.lower() in TEXT_SUFFIXES:
            yield path


def classify(path: Path, line: str) -> str:
    rel = path.relative_to(ROOT).as_posix()
    lower = line.lower()
    if "certificate" in lower or "spki" in lower or "tls" in lower or "pin" in lower:
        return "external-standard-or-pinning"
    if rel == "Cargo.lock" or (rel.endswith("Cargo.toml") and ("sha2" in lower or "blake3" in lower)):
        return "dependency-metadata"
    if rel.startswith("docs/") or rel.endswith(".md"):
        return "documentation"
    if rel.startswith(".github/") or "sha256sum" in lower or "shasum" in lower:
        return "build-release-tooling"
    if any(token in lower for token in ("config_fingerprint", "binary_fingerprint", "descriptor_fingerprint", "endpoint_fingerprint", "payload_digest", "state_digest", "audit_digest")):
        return "internal-persisted-contract"
    if any(token in lower for token in ("serialize", "deserialize", "serde", "stored", "persist", "json", "sqlite", "record")):
        return "possible-persisted-contract"
    return "internal-runtime-or-test"


matches: list[tuple[str, int, str, str, list[str]]] = []
for path in iter_files():
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except UnicodeDecodeError:
        continue
    for number, line in enumerate(lines, 1):
        found = [name for name, pattern in PATTERNS.items() if pattern.search(line)]
        if not found:
            continue
        rel = path.relative_to(ROOT).as_posix()
        matches.append((rel, number, classify(path, line), line.strip(), found))

counts = Counter(item[2] for item in matches)
print("=== INTERNAL DIGEST INVENTORY SUMMARY ===")
for key in sorted(counts):
    print(f"{key}: {counts[key]}")
print(f"total matched lines: {len(matches)}")

for category in sorted(counts):
    print(f"\n=== {category.upper()} ===")
    for rel, number, current, line, found in matches:
        if current != category:
            continue
        rendered = line if len(line) <= 240 else line[:237] + "..."
        print(f"{rel}:{number}: [{','.join(found)}] {rendered}")

print("\n=== FIRST-PARTY MIGRATION CANDIDATE FILES ===")
files = sorted({rel for rel, _, category, _, _ in matches if category in {"internal-persisted-contract", "possible-persisted-contract", "internal-runtime-or-test", "build-release-tooling"}})
for rel in files:
    print(rel)
