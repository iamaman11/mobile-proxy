#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def write(path: str, body: str) -> None:
    target = ROOT / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(body, encoding="utf-8")


def replace_once(path: str, old: str, new: str) -> None:
    body = read(path)
    if body.count(old) != 1:
        raise RuntimeError(f"{path}: expected one occurrence of {old!r}, found {body.count(old)}")
    write(path, body.replace(old, new, 1))


replace_once("Cargo.toml", 'sha2 = "0.10"\n', "")
replace_once(
    "apps/operator-cli/Cargo.toml",
    'proxy-core = { path = "../../crates/proxy-core" }\n',
    'mobile-proxy-foundation = { path = "../../crates/foundation" }\nproxy-core = { path = "../../crates/proxy-core" }\n',
)
replace_once("apps/operator-cli/Cargo.toml", "sha2.workspace = true\n", "")

replace_once(
    "apps/operator-cli/src/provision.rs",
    "use serde::Deserialize;\nuse sha2::{Digest, Sha256};\n",
    "use mobile_proxy_foundation::{ContentDigest, DigestDomain};\nuse serde::{Deserialize, Serialize};\n",
)
replace_once(
    "apps/operator-cli/src/provision.rs",
    "    write_release_metadata(&repo_root, &release_root, &args.release_id)?;\n    write_checksums(&release_root)?;\n\n    println!(\"{}\", release_root.display());\n",
    "    write_release_metadata(&repo_root, &release_root, &args.release_id)?;\n    write_integrity_manifest(&release_root)?;\n    verify_integrity_manifest(&release_root)?;\n\n    println!(\"{}\", release_root.display());\n",
)
old_checksums = '''fn write_checksums(root: &Path) -> Result<()> {
    let mut files = Vec::new();
    collect_files(root, root, &mut files)?;
    files.sort_by(|a, b| a.0.cmp(&b.0));
    let mut lines = Vec::new();
    for (relative, absolute) in files {
        let mut file = fs::File::open(&absolute)?;
        let mut hasher = Sha256::new();
        let mut buf = [0_u8; 8192];
        loop {
            let read = file.read(&mut buf)?;
            if read == 0 {
                break;
            }
            hasher.update(&buf[..read]);
        }
        let digest = hasher.finalize();
        lines.push(format!("{digest:x} *{relative}"));
    }
    fs::write(root.join("checksums.sha256"), lines.join("\\n"))?;
    Ok(())
}

fn collect_files(root: &Path, dir: &Path, out: &mut Vec<(String, PathBuf)>) -> Result<()> {
    for entry in fs::read_dir(dir)? {
        let entry = entry?;
        let path = entry.path();
        if path.is_dir() {
            collect_files(root, &path, out)?;
        } else if path.is_file() {
            let relative = path
                .strip_prefix(root)
                .context("failed to compute relative path")?
                .to_string_lossy()
                .replace('\\\\', "/");
            out.push((relative, path));
        }
    }
    Ok(())
}
'''
new_integrity = '''const RELEASE_INTEGRITY_MANIFEST: &str = "integrity-manifest.json";
const LEGACY_SHA256_MANIFEST: &str = "checksums.sha256";
const RELEASE_INTEGRITY_DOMAIN: DigestDomain =
    DigestDomain::new("mobile-proxy/release-file/v1");

#[derive(Debug, Serialize, Deserialize, PartialEq, Eq)]
struct ReleaseIntegrityManifest {
    format_version: u32,
    algorithm: String,
    domain: String,
    entries: Vec<ReleaseIntegrityEntry>,
}

#[derive(Debug, Serialize, Deserialize, PartialEq, Eq)]
struct ReleaseIntegrityEntry {
    path: String,
    digest: ContentDigest,
    size_bytes: u64,
}

fn write_integrity_manifest(root: &Path) -> Result<()> {
    let legacy = root.join(LEGACY_SHA256_MANIFEST);
    if legacy.exists() {
        fs::remove_file(&legacy)
            .with_context(|| format!("failed to remove legacy {}", legacy.display()))?;
    }

    let entries = integrity_entries(root)?;
    let manifest = ReleaseIntegrityManifest {
        format_version: 1,
        algorithm: "blake3-256".into(),
        domain: RELEASE_INTEGRITY_DOMAIN.as_str().into(),
        entries,
    };
    fs::write(
        root.join(RELEASE_INTEGRITY_MANIFEST),
        serde_json::to_vec_pretty(&manifest)?,
    )?;
    Ok(())
}

fn verify_integrity_manifest(root: &Path) -> Result<()> {
    let path = root.join(RELEASE_INTEGRITY_MANIFEST);
    let manifest: ReleaseIntegrityManifest = serde_json::from_slice(
        &fs::read(&path).with_context(|| format!("failed to read {}", path.display()))?,
    )
    .with_context(|| format!("failed to parse {}", path.display()))?;
    if manifest.format_version != 1
        || manifest.algorithm != "blake3-256"
        || manifest.domain != RELEASE_INTEGRITY_DOMAIN.as_str()
    {
        bail!("release integrity manifest metadata is unsupported");
    }

    let actual = integrity_entries(root)?;
    if actual != manifest.entries {
        bail!("release integrity manifest does not match packaged files");
    }
    Ok(())
}

fn integrity_entries(root: &Path) -> Result<Vec<ReleaseIntegrityEntry>> {
    let mut files = Vec::new();
    collect_integrity_files(root, root, &mut files)?;
    files.sort_by(|a, b| a.0.cmp(&b.0));
    let mut entries = Vec::with_capacity(files.len());
    for (relative, absolute) in files {
        let bytes = fs::read(&absolute)
            .with_context(|| format!("failed to read release file {}", absolute.display()))?;
        let digest = ContentDigest::derive(RELEASE_INTEGRITY_DOMAIN, [bytes.as_slice()]);
        entries.push(ReleaseIntegrityEntry {
            path: relative,
            digest,
            size_bytes: bytes.len() as u64,
        });
    }
    Ok(entries)
}

fn collect_integrity_files(
    root: &Path,
    dir: &Path,
    out: &mut Vec<(String, PathBuf)>,
) -> Result<()> {
    for entry in fs::read_dir(dir)? {
        let entry = entry?;
        let path = entry.path();
        if path.is_dir() {
            collect_integrity_files(root, &path, out)?;
        } else if path.is_file() {
            let relative = path
                .strip_prefix(root)
                .context("failed to compute relative path")?
                .to_string_lossy()
                .replace('\\\\', "/");
            if relative != RELEASE_INTEGRITY_MANIFEST && relative != LEGACY_SHA256_MANIFEST {
                out.push((relative, path));
            }
        }
    }
    Ok(())
}
'''
replace_once("apps/operator-cli/src/provision.rs", old_checksums, new_integrity)
replace_once(
    "apps/operator-cli/src/provision.rs",
    "    use super::{is_android_arm_elf_header, render_template};\n",
    "    use super::{\n        RELEASE_INTEGRITY_MANIFEST, is_android_arm_elf_header, render_template,\n        verify_integrity_manifest, write_integrity_manifest,\n    };\n    use std::fs;\n    use uuid::Uuid;\n",
)
replace_once(
    "apps/operator-cli/src/provision.rs",
    "    #[test]\n    fn android_arm_elf_header_is_recognized() {\n",
    '''    #[test]
    fn release_integrity_manifest_is_blake3_and_fail_closed() {
        let root = std::env::temp_dir().join(format!(
            "mobile-proxy-release-integrity-{}",
            Uuid::new_v4()
        ));
        fs::create_dir_all(root.join("nested")).unwrap();
        fs::write(root.join("a.txt"), b"alpha").unwrap();
        fs::write(root.join("nested/b.bin"), b"beta").unwrap();

        write_integrity_manifest(&root).unwrap();
        verify_integrity_manifest(&root).unwrap();
        let manifest = fs::read_to_string(root.join(RELEASE_INTEGRITY_MANIFEST)).unwrap();
        assert!(manifest.contains("\\\"algorithm\\\": \\\"blake3-256\\\""));
        assert!(manifest.contains("b3:"));
        assert!(!root.join("checksums.sha256").exists());

        fs::write(root.join("a.txt"), b"tampered").unwrap();
        assert!(verify_integrity_manifest(&root).is_err());
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn android_arm_elf_header_is_recognized() {
''',
)

write(
    "scripts/check_digest_policy.py",
    '''#!/usr/bin/env python3
"""Fail closed when first-party code introduces unapproved SHA-256 contracts."""

from __future__ import annotations

from pathlib import Path
import re

FIRST_PARTY_ROOTS = ("apps", "crates", "services")
FORBIDDEN_SOURCE_PATTERNS = (
    re.compile(r"\\bSha256\\b"),
    re.compile(r"\\bsha2::"),
    re.compile(r"checksums\\.sha256"),
)
SHA2_DEPENDENCY = re.compile(r"^\\s*sha2(?:\\s*=|\\.workspace\\s*=)", re.MULTILINE)


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
''',
)

replace_once(
    "scripts/check_architecture_boundaries.py",
    "import tomllib\n",
    "import tomllib\n\nfrom check_digest_policy import check_repository as check_digest_policy\n",
)
replace_once(
    "scripts/check_architecture_boundaries.py",
    "    return errors\n\n\ndef main() -> int:\n",
    "    errors.extend(check_digest_policy(root))\n    return errors\n\n\ndef main() -> int:\n",
)
replace_once(
    "scripts/check_architecture_boundaries.py",
    '    print("architecture boundary validation passed for foundation and runtime-domain")\n',
    '    print("architecture and digest policy validation passed")\n',
)

write(
    "scripts/tests/test_digest_policy.py",
    '''from pathlib import Path
import tempfile
import unittest

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from check_digest_policy import check_repository


class DigestPolicyTests(unittest.TestCase):
    def test_blake3_first_party_source_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            crate = root / "crates/example"
            (crate / "src").mkdir(parents=True)
            (crate / "Cargo.toml").write_text(
                '[package]\nname = "example"\nversion = "0.1.0"\n',
                encoding="utf-8",
            )
            (crate / "src/lib.rs").write_text(
                'const FORMAT: &str = "b3:";\n', encoding="utf-8"
            )
            self.assertEqual(check_repository(root), [])

    def test_sha2_dependency_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            crate = root / "apps/example"
            (crate / "src").mkdir(parents=True)
            (crate / "Cargo.toml").write_text(
                '[package]\nname = "example"\nversion = "0.1.0"\n\n[dependencies]\nsha2 = "0.10"\n',
                encoding="utf-8",
            )
            (crate / "src/main.rs").write_text("fn main() {}\n", encoding="utf-8")
            errors = check_repository(root)
            self.assertTrue(any("sha2 dependency" in error for error in errors))

    def test_legacy_checksum_contract_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "services/example/src/main.rs"
            source.parent.mkdir(parents=True)
            source.write_text(
                'const LEGACY: &str = "checksums.sha256";\n', encoding="utf-8"
            )
            errors = check_repository(root)
            self.assertTrue(any("SHA-256 usage" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
''',
)

write(
    "docs/architecture/digest-inventory-and-migration.md",
    '''# Digest Inventory and Migration Matrix

Status: normative inventory  
Owner: architecture and security  
Applies to: all first-party code, persisted records, release artifacts and API contracts

## Decision

All first-party internal persisted digests use BLAKE3-256 through the typed foundation `ContentDigest` contract. Legacy internal SHA-256 is transitional only and must not be newly produced. External standards retain the algorithm mandated by that standard.

## Canonical internal representation

- text encoding: `b3:<64 lowercase hexadecimal characters>`;
- structured inputs: versioned domain separation plus unsigned 64-bit big-endian length framing for every field;
- a domain change, field change, normalization change or algorithm change creates a new contract version;
- hashing a legacy digest is not a migration of the original content.

## Current inventory

| Contract or surface | Ownership | Current/previous state | Target | Migration status |
| --- | --- | --- | --- | --- |
| Packaged device release file checksums | First-party internal release contract | `checksums.sha256`, untyped GNU-style lines | `integrity-manifest.json` with typed `b3:` digests, size and domain metadata | Migrated in the first BLAKE3 backfill slice |
| `config_fingerprint` fields | First-party internal runtime state | String field; producer audit required | Typed BLAKE3 config digest | Planned producer-by-producer migration |
| `binary_fingerprint` fields | First-party internal runtime state | String field; producer audit required | Typed BLAKE3 binary digest | Planned producer-by-producer migration |
| Future proxy descriptor and endpoint fingerprints | First-party internal contract | Not yet production-owned | Typed BLAKE3 digest | Required from first implementation |
| Future idempotency, audit and outbox payload digests | First-party internal contract | Not yet production-owned | Typed BLAKE3 digest | Required from first implementation |
| Reverse-tunnel certificate pinning | TLS security boundary | Certificate DER/pinning semantics determined by TLS contract | Preserve TLS-compatible pinning; do not reinterpret as an internal content digest | Permanent exception |
| Cargo registry checksums in `Cargo.lock` | External Rust ecosystem metadata | SHA-256 values generated by Cargo | Preserve exactly | Permanent external exception |
| OCI, SBOM and signature digests | External standards | Algorithm selected by the relevant format/profile | Preserve the standardized algorithm | Permanent external exception |
| Passwords or human passphrases | Authentication secret | Must never use a fast content hash | Argon2id with versioned parameters and salts | Permanent separate primitive |

## Release integrity manifest v1

`integrity-manifest.json` is owned by mobile-proxy and contains:

```json
{
  "format_version": 1,
  "algorithm": "blake3-256",
  "domain": "mobile-proxy/release-file/v1",
  "entries": [
    {
      "path": "bin/runtime-supervisor",
      "digest": "b3:<64 lowercase hex>",
      "size_bytes": 123
    }
  ]
}
```

Entries are path-sorted and cover every packaged file except the manifest itself. Packaging verifies the finished manifest immediately and fails closed on missing, extra, reordered, resized or modified content. A stale `checksums.sha256` is removed rather than carried into a new release.

## Migration rules

1. Inventory the producer, persisted field, index, reader, API and operational tooling.
2. Recompute from canonical source bytes. Never compute BLAKE3 over an old SHA-256 digest as a substitute.
3. New writes use only the target BLAKE3 contract.
4. A temporary legacy reader must be isolated in a migration adapter and explicitly prefixed or schema-versioned.
5. Backfill is restart-safe, observable and reversible until acceptance.
6. Readers reject unknown algorithms, domains and versions.
7. Remove the legacy reader after the compatibility window and acceptance evidence.

## Enforcement

The permanent architecture gate scans first-party Rust source and manifests. It rejects direct `sha2` dependencies, `Sha256` construction and the legacy `checksums.sha256` contract. External standardized SHA-256 must live in an explicit adapter exception introduced through a separate ADR and a narrow allowlist.
''',
)

adr_append = '''

## 14. First-party persisted digest migration

All existing first-party internal persisted digest contracts are migration targets for BLAKE3-256. The earlier compatibility exception applies only while a concrete legacy reader or backfill is required; it is not permission to create new SHA-256 data.

The authoritative inventory and migration state is maintained in [Digest Inventory and Migration Matrix](digest-inventory-and-migration.md). New internal SHA-256 producers are rejected by the permanent architecture gate. External standardized boundaries, Cargo registry checksums, TLS pinning profiles and compliance-specific algorithms remain outside this internal migration.

Migration must recompute from canonical source bytes. `BLAKE3(SHA256(data))` is a digest of the legacy digest and is not equivalent to `BLAKE3(data)`.
'''
adr = read("docs/architecture/ADR-002-cryptographic-hashing-and-kdf-policy.md")
if "## 14. First-party persisted digest migration" not in adr:
    write("docs/architecture/ADR-002-cryptographic-hashing-and-kdf-policy.md", adr.rstrip() + adr_append)

replace_once(
    "IMPLEMENTATION_PLAN.md",
    "- [ADR-002: Cryptographic Hashing and KDF Policy](docs/architecture/ADR-002-cryptographic-hashing-and-kdf-policy.md)\n",
    "- [ADR-002: Cryptographic Hashing and KDF Policy](docs/architecture/ADR-002-cryptographic-hashing-and-kdf-policy.md)\n- [Digest Inventory and Migration Matrix](docs/architecture/digest-inventory-and-migration.md)\n",
)
replace_once(
    "docs/ULTIMATE_IMPLEMENTATION_PLAN.md",
    "Foundation primitives and cryptographic digest decisions are normative in [Foundation Primitives](architecture/foundation-primitives.md) and [ADR-002](architecture/ADR-002-cryptographic-hashing-and-kdf-policy.md).\n",
    "Foundation primitives and cryptographic digest decisions are normative in [Foundation Primitives](architecture/foundation-primitives.md), [ADR-002](architecture/ADR-002-cryptographic-hashing-and-kdf-policy.md) and the [Digest Inventory and Migration Matrix](architecture/digest-inventory-and-migration.md).\n",
)
