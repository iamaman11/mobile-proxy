use std::fs;
use std::path::{Path, PathBuf};

use anyhow::{Context, Result, bail};
use mobile_proxy_foundation::{ContentDigest, DigestDomain};
use serde::{Deserialize, Serialize};

pub(crate) const RELEASE_INTEGRITY_MANIFEST: &str = "integrity-manifest.json";
const RELEASE_INTEGRITY_DOMAIN: DigestDomain = DigestDomain::new("mobile-proxy/release-file/v1");

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

    use super::{RELEASE_INTEGRITY_MANIFEST, verify_integrity_manifest, write_integrity_manifest};

    #[test]
    fn manifest_is_typed_sorted_and_fail_closed() {
        let root =
            std::env::temp_dir().join(format!("mobile-proxy-release-integrity-{}", Uuid::new_v4()));
        fs::create_dir_all(root.join("nested")).unwrap();
        fs::write(root.join("z.bin"), b"zeta").unwrap();
        fs::write(root.join("nested/a.txt"), b"alpha").unwrap();

        write_integrity_manifest(&root).unwrap();
        verify_integrity_manifest(&root).unwrap();

        let manifest: Value =
            serde_json::from_slice(&fs::read(root.join(RELEASE_INTEGRITY_MANIFEST)).unwrap())
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
