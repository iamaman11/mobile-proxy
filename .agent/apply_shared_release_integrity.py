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
        raise RuntimeError(
            f"{path}: expected one occurrence of {old!r}, found {body.count(old)}"
        )
    write(path, body.replace(old, new, 1))


write(
    "apps/operator-cli/src/release_integrity.rs",
    r'''use std::fs;
use std::path::{Path, PathBuf};

use anyhow::{Context, Result, bail};
use mobile_proxy_foundation::{ContentDigest, DigestDomain};
use serde::{Deserialize, Serialize};

pub(crate) const RELEASE_INTEGRITY_MANIFEST: &str = "integrity-manifest.json";
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

pub(crate) fn write_integrity_manifest(root: &Path) -> Result<()> {
    let manifest = ReleaseIntegrityManifest {
        format_version: 1,
        algorithm: "blake3-256".into(),
        domain: RELEASE_INTEGRITY_DOMAIN.as_str().into(),
        entries: integrity_entries(root)?,
    };
    fs::write(
        root.join(RELEASE_INTEGRITY_MANIFEST),
        serde_json::to_vec_pretty(&manifest)?,
    )?;
    Ok(())
}

pub(crate) fn verify_integrity_manifest(root: &Path) -> Result<()> {
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
    files.sort_by(|left, right| left.0.cmp(&right.0));

    files
        .into_iter()
        .map(|(relative, absolute)| {
            let bytes = fs::read(&absolute)
                .with_context(|| format!("failed to read release file {}", absolute.display()))?;
            Ok(ReleaseIntegrityEntry {
                path: relative,
                digest: ContentDigest::derive(RELEASE_INTEGRITY_DOMAIN, [bytes.as_slice()]),
                size_bytes: u64::try_from(bytes.len())
                    .context("release file size exceeds the supported range")?,
            })
        })
        .collect()
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
                .context("failed to compute release-relative path")?
                .to_string_lossy()
                .replace('\\', "/");
            if relative != RELEASE_INTEGRITY_MANIFEST {
                out.push((relative, path));
            }
        }
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use std::fs;

    use serde_json::Value;
    use uuid::Uuid;

    use super::{
        RELEASE_INTEGRITY_MANIFEST, verify_integrity_manifest, write_integrity_manifest,
    };

    #[test]
    fn manifest_is_typed_sorted_and_fail_closed() {
        let root = std::env::temp_dir().join(format!(
            "mobile-proxy-release-integrity-{}",
            Uuid::new_v4()
        ));
        fs::create_dir_all(root.join("nested")).unwrap();
        fs::write(root.join("z.bin"), b"zeta").unwrap();
        fs::write(root.join("nested/a.txt"), b"alpha").unwrap();

        write_integrity_manifest(&root).unwrap();
        verify_integrity_manifest(&root).unwrap();

        let manifest: Value = serde_json::from_slice(
            &fs::read(root.join(RELEASE_INTEGRITY_MANIFEST)).unwrap(),
        )
        .unwrap();
        assert_eq!(manifest["format_version"], 1);
        assert_eq!(manifest["algorithm"], "blake3-256");
        assert_eq!(manifest["domain"], "mobile-proxy/release-file/v1");
        assert_eq!(manifest["entries"][0]["path"], "nested/a.txt");
        assert_eq!(manifest["entries"][1]["path"], "z.bin");
        for entry in manifest["entries"].as_array().unwrap() {
            let digest = entry["digest"].as_str().unwrap();
            assert!(digest.starts_with("b3:"));
            assert_eq!(digest.len(), 67);
        }

        fs::write(root.join("nested/a.txt"), b"tampered").unwrap();
        assert!(verify_integrity_manifest(&root).is_err());
        fs::write(root.join("nested/a.txt"), b"alpha").unwrap();
        fs::write(root.join("extra.txt"), b"unexpected").unwrap();
        assert!(verify_integrity_manifest(&root).is_err());

        fs::remove_dir_all(root).unwrap();
    }
}
''',
)

replace_once(
    "apps/operator-cli/src/main.rs",
    "mod provision;\n",
    "mod provision;\nmod release_integrity;\n",
)

provision_path = "apps/operator-cli/src/provision.rs"
provision = read(provision_path)
provision = provision.replace(
    "use mobile_proxy_foundation::{ContentDigest, DigestDomain};\nuse serde::{Deserialize, Serialize};\n",
    "use serde::Deserialize;\n",
)
anchor = "use crate::cli::PackageDeviceReleaseArgs;\n"
if provision.count(anchor) != 1:
    raise RuntimeError("device release import anchor was not found exactly once")
provision = provision.replace(
    anchor,
    anchor
    + "use crate::release_integrity::{\n"
    + "    RELEASE_INTEGRITY_MANIFEST, verify_integrity_manifest, write_integrity_manifest,\n"
    + "};\n",
    1,
)
start = provision.find("const RELEASE_INTEGRITY_MANIFEST: &str")
end = provision.find("#[cfg(test)]", start)
if start == -1 or end == -1:
    raise RuntimeError("embedded device release integrity implementation was not found")
provision = provision[:start] + provision[end:]
provision = provision.replace(
    "    use super::{\n"
    "        RELEASE_INTEGRITY_MANIFEST, is_android_arm_elf_header, render_template,\n"
    "        verify_integrity_manifest, write_integrity_manifest,\n"
    "    };\n"
    "    use std::fs;\n"
    "    use uuid::Uuid;\n",
    "    use super::{is_android_arm_elf_header, render_template};\n",
)
release_test_start = provision.find(
    "    #[test]\n    fn release_integrity_manifest_is_blake3_and_fail_closed()"
)
if release_test_start != -1:
    next_test = provision.find("    #[test]\n    fn android_arm_elf_header_is_recognized()", release_test_start)
    if next_test == -1:
        raise RuntimeError("device release integrity test boundary was not found")
    provision = provision[:release_test_start] + provision[next_test:]
if "checksums.sha256" in provision or "Sha256" in provision or "sha2::" in provision:
    raise RuntimeError("legacy digest marker remains in device release producer")
write(provision_path, provision)

vm_path = "apps/operator-cli/src/vm.rs"
vm = read(vm_path)
vm = vm.replace(
    "use serde::Deserialize;\nuse sha2::{Digest, Sha256};\n",
    "use serde::Deserialize;\n",
)
vm_anchor = "use crate::cli::{DeleteVmArgs, ProvisionVmArgs};\n"
if vm.count(vm_anchor) != 1:
    raise RuntimeError("VM release import anchor was not found exactly once")
vm = vm.replace(
    vm_anchor,
    vm_anchor
    + "use crate::release_integrity::{verify_integrity_manifest, write_integrity_manifest};\n",
    1,
)
if vm.count("    write_checksums(&release_root)?;\n") != 1:
    raise RuntimeError("VM checksum writer call was not found exactly once")
vm = vm.replace(
    "    write_checksums(&release_root)?;\n",
    "    write_integrity_manifest(&release_root)?;\n"
    "    verify_integrity_manifest(&release_root)?;\n",
    1,
)
vm_start = vm.find("fn write_checksums(root: &Path) -> Result<()> {")
vm_end = vm.find("fn gcloud_status", vm_start)
if vm_start == -1 or vm_end == -1:
    raise RuntimeError("VM checksum implementation was not found")
vm = vm[:vm_start] + vm[vm_end:]
if "SHA256SUMS" in vm or "Sha256" in vm or "sha2::" in vm:
    raise RuntimeError("legacy digest marker remains in VM release producer")
write(vm_path, vm)

policy_path = "scripts/check_digest_policy.py"
policy = read(policy_path)
policy = policy.replace(
    '    re.compile(r"checksums\\.sha256"),\n',
    '    re.compile(r"checksums\\.sha256"),\n    re.compile(r"\\bSHA256SUMS\\b"),\n',
)
write(policy_path, policy)

test_path = "scripts/tests/test_digest_policy.py"
tests = read(test_path)
needle = '''    def test_legacy_checksum_contract_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "services/example/src/main.rs"
            source.parent.mkdir(parents=True)
            source.write_text(
                'const LEGACY: &str = "checksums.sha256";\n', encoding="utf-8"
            )
            errors = check_repository(root)
            self.assertTrue(any("SHA-256 usage" in error for error in errors))
'''
replacement = needle + '''
    def test_legacy_vm_checksum_contract_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "apps/example/src/main.rs"
            source.parent.mkdir(parents=True)
            source.write_text(
                'const LEGACY: &str = "SHA256SUMS";\n', encoding="utf-8"
            )
            errors = check_repository(root)
            self.assertTrue(any("SHA-256 usage" in error for error in errors))
'''
if tests.count(needle) != 1:
    raise RuntimeError("digest policy regression-test anchor was not found exactly once")
write(test_path, tests.replace(needle, replacement, 1))

inventory_path = "docs/architecture/digest-inventory-and-migration.md"
inventory = read(inventory_path)
inventory = inventory.replace(
    "| Packaged device release file checksums | First-party internal release contract | `checksums.sha256`, untyped GNU-style lines | `integrity-manifest.json` with typed `b3:` digests, size and domain metadata | Migrated in the first BLAKE3 backfill slice |",
    "| Packaged device and VM release file checksums | First-party internal release contracts | Legacy untyped checksum files produced by both packagers | Shared `integrity-manifest.json` with typed `b3:` digests, size and domain metadata | Migrated in the first BLAKE3 backfill slice |",
)
inventory = inventory.replace(
    "Entries are path-sorted and cover every packaged file except the manifest itself. Packaging verifies the finished manifest immediately and fails closed on missing, extra, reordered, resized or modified content. A stale `checksums.sha256` is removed rather than carried into a new release.",
    "Entries are path-sorted and cover every packaged file except the manifest itself. Both device and VM packaging verify the finished manifest immediately and fail closed on missing, extra, reordered, resized or modified content. Release roots are recreated before packaging, so no legacy checksum file can be carried into a new release.",
)
inventory += "\n\nThe manifest proves deterministic package consistency; it is not a digital signature or trust root. Release authenticity remains a separate signing/provenance responsibility.\n"
write(inventory_path, inventory)
