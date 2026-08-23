use std::fs;
use std::io::{Read, Write};
use std::path::{Path, PathBuf};
use std::process::Command;

use anyhow::{Context, Result, bail};
use mobile_proxy_foundation::{ContentDigest, DigestDomain};
use serde::Deserialize;

use crate::cli::PrepareRuntimeBinariesArgs;

const ANDROID_TARGET: &str = "armv7-linux-androideabi";
const SING_BOX_ARCHIVE_DOMAIN: DigestDomain =
    DigestDomain::new("mobile-proxy/upstream-sing-box-archive/v1");

#[derive(Debug, Deserialize)]
struct SingBoxArtifactLock {
    schema_version: u32,
    version: String,
    artifacts: std::collections::BTreeMap<String, SingBoxArtifact>,
}

#[derive(Debug, Deserialize)]
struct SingBoxArtifact {
    size: u64,
    content_digest: ContentDigest,
}

pub fn prepare_runtime_binaries(args: &PrepareRuntimeBinariesArgs) -> Result<()> {
    let repo = repo_root()?;
    if !args.skip_android_rust_build {
        build_android_rust(&repo, args)?;
        install_android_rust_binaries(&repo, args)?;
    }
    if !args.skip_sing_box_download {
        install_sing_box(
            &repo,
            &args.sing_box_version,
            &repo.join(&args.sing_box_lock_file),
        )?;
    }
    verify_runtime_binaries(&repo)?;
    println!("runtime binaries prepared");
    Ok(())
}

pub fn verify_runtime_binaries(repo: &Path) -> Result<()> {
    ensure_elf_machine(
        &repo.join("deploy/device-runtime/bin/runtime-supervisor"),
        40,
        "Android ARM runtime-supervisor",
    )?;
    ensure_elf_machine(
        &repo.join("deploy/device-runtime/bin/host-daemon"),
        40,
        "Android ARM host-daemon",
    )?;
    ensure_elf_machine(
        &repo.join("deploy/device-runtime/bin/sing-box"),
        40,
        "Android ARM sing-box",
    )?;
    ensure_elf_machine(
        &repo.join("deploy/vm-runtime/bin/sing-box"),
        62,
        "Linux x86_64 sing-box",
    )?;
    Ok(())
}

fn build_android_rust(repo: &Path, args: &PrepareRuntimeBinariesArgs) -> Result<()> {
    let ndk_bin = Path::new(&args.android_ndk).join("toolchains/llvm/prebuilt/linux-x86_64/bin");
    let clang = ndk_bin.join("armv7a-linux-androideabi23-clang");
    let ar = ndk_bin.join("llvm-ar");
    ensure_file(&clang)?;
    ensure_file(&ar)?;

    run(
        Command::new("rustup")
            .arg("target")
            .arg("add")
            .arg(ANDROID_TARGET),
        repo,
    )?;
    run(
        Command::new("cargo")
            .arg("build")
            .arg("-p")
            .arg("runtime-supervisor")
            .arg("-p")
            .arg("host-daemon")
            .arg("--target")
            .arg(ANDROID_TARGET)
            .env("CC_armv7_linux_androideabi", &clang)
            .env("AR_armv7_linux_androideabi", &ar)
            .env("CARGO_TARGET_ARMV7_LINUX_ANDROIDEABI_LINKER", &clang),
        repo,
    )
}

fn install_android_rust_binaries(repo: &Path, args: &PrepareRuntimeBinariesArgs) -> Result<()> {
    let target_dir = repo.join("target").join(ANDROID_TARGET).join("debug");
    let bin_dir = repo.join("deploy/device-runtime/bin");
    fs::create_dir_all(&bin_dir)?;
    fs::copy(
        target_dir.join("runtime-supervisor"),
        bin_dir.join("runtime-supervisor"),
    )?;
    fs::copy(target_dir.join("host-daemon"), bin_dir.join("host-daemon"))?;
    let strip =
        Path::new(&args.android_ndk).join("toolchains/llvm/prebuilt/linux-x86_64/bin/llvm-strip");
    if strip.is_file() {
        run(
            Command::new(strip)
                .arg(bin_dir.join("runtime-supervisor"))
                .arg(bin_dir.join("host-daemon")),
            repo,
        )?;
    }
    Ok(())
}

fn install_sing_box(repo: &Path, version: &str, lock_path: &Path) -> Result<()> {
    let lock = load_sing_box_lock(lock_path, version)?;
    let cache = repo.join("target/artifacts/sing-box");
    fs::create_dir_all(&cache)?;
    fs::create_dir_all(repo.join("deploy/device-runtime/bin"))?;
    fs::create_dir_all(repo.join("deploy/vm-runtime/bin"))?;

    let android_candidate = download_and_extract_sing_box(
        repo,
        &cache,
        version,
        "android-arm",
        required_artifact(&lock, "android-arm")?,
    )?;
    let vm_candidate = download_and_extract_sing_box(
        repo,
        &cache,
        version,
        "linux-amd64-glibc",
        required_artifact(&lock, "linux-amd64-glibc")?,
    )?;

    ensure_elf_machine(&android_candidate, 40, "candidate Android ARM sing-box")?;
    ensure_elf_machine(&vm_candidate, 62, "candidate Linux x86_64 sing-box")?;
    verify_sing_box_version(&vm_candidate, version, repo)?;
    verify_sing_box_config(&vm_candidate, &cache, repo)?;

    atomic_install(
        &android_candidate,
        &repo.join("deploy/device-runtime/bin/sing-box"),
    )?;
    atomic_install(&vm_candidate, &repo.join("deploy/vm-runtime/bin/sing-box"))?;
    Ok(())
}

fn load_sing_box_lock(path: &Path, requested_version: &str) -> Result<SingBoxArtifactLock> {
    let bytes = fs::read(path)
        .with_context(|| format!("failed to read sing-box artifact lock: {}", path.display()))?;
    let lock: SingBoxArtifactLock = serde_json::from_slice(&bytes)
        .with_context(|| format!("invalid sing-box artifact lock: {}", path.display()))?;
    if lock.schema_version != 1 {
        bail!(
            "unsupported sing-box artifact lock schema: {}",
            lock.schema_version
        );
    }
    if lock.version != requested_version {
        bail!(
            "sing-box version {requested_version} is not pinned by {} (pinned: {})",
            path.display(),
            lock.version
        );
    }
    Ok(lock)
}

fn required_artifact<'a>(
    lock: &'a SingBoxArtifactLock,
    target: &str,
) -> Result<&'a SingBoxArtifact> {
    let artifact = lock
        .artifacts
        .get(target)
        .with_context(|| format!("sing-box artifact lock is missing target {target}"))?;
    Ok(artifact)
}

fn download_and_extract_sing_box(
    repo: &Path,
    cache: &Path,
    version: &str,
    target: &str,
    expected: &SingBoxArtifact,
) -> Result<PathBuf> {
    let archive = cache.join(format!("sing-box-{version}-{target}.tar.gz"));
    let extract_dir = cache.join(format!("sing-box-{version}-{target}"));
    let url = format!(
        "https://github.com/SagerNet/sing-box/releases/download/v{version}/sing-box-{version}-{target}.tar.gz"
    );
    if !archive_matches(&archive, expected)? {
        let archive_name = archive
            .file_name()
            .context("sing-box archive path has no file name")?;
        let download =
            archive.with_file_name(format!("{}.download", archive_name.to_string_lossy()));
        if download.exists() {
            fs::remove_file(&download)?;
        }
        run(
            Command::new("curl")
                .arg("-fL")
                .arg("--retry")
                .arg("3")
                .arg("-o")
                .arg(&download)
                .arg(&url),
            repo,
        )?;
        verify_archive(&download, expected)?;
        fs::rename(&download, &archive)?;
    }
    verify_archive(&archive, expected)?;
    if extract_dir.exists() {
        fs::remove_dir_all(&extract_dir)?;
    }
    fs::create_dir_all(&extract_dir)?;
    run(
        Command::new("tar")
            .arg("-xzf")
            .arg(&archive)
            .arg("-C")
            .arg(&extract_dir),
        repo,
    )?;
    let binary = find_file_named(&extract_dir, "sing-box")
        .with_context(|| format!("sing-box binary not found in {}", archive.display()))?;
    set_executable(&binary)?;
    Ok(binary)
}

fn archive_matches(path: &Path, expected: &SingBoxArtifact) -> Result<bool> {
    if !path.is_file() || fs::metadata(path)?.len() != expected.size {
        return Ok(false);
    }
    Ok(content_digest_file(path)? == expected.content_digest)
}

fn verify_archive(path: &Path, expected: &SingBoxArtifact) -> Result<()> {
    let actual_size = fs::metadata(path)?.len();
    if actual_size != expected.size {
        bail!(
            "sing-box archive size mismatch for {}: expected {}, got {}",
            path.display(),
            expected.size,
            actual_size
        );
    }
    let actual_digest = content_digest_file(path)?;
    if actual_digest != expected.content_digest {
        bail!(
            "sing-box archive content digest mismatch for {}: expected {}, got {}",
            path.display(),
            expected.content_digest,
            actual_digest
        );
    }
    Ok(())
}

fn content_digest_file(path: &Path) -> Result<ContentDigest> {
    let bytes = fs::read(path)?;
    Ok(ContentDigest::derive(
        SING_BOX_ARCHIVE_DOMAIN,
        [bytes.as_slice()],
    ))
}

fn verify_sing_box_version(binary: &Path, expected_version: &str, repo: &Path) -> Result<()> {
    let output = Command::new(binary)
        .arg("version")
        .current_dir(repo)
        .output()?;
    if !output.status.success() {
        bail!("candidate sing-box version command failed");
    }
    let stdout = String::from_utf8(output.stdout).context("sing-box version is not UTF-8")?;
    let expected = format!("sing-box version {expected_version}");
    if !stdout.lines().any(|line| line.trim() == expected) {
        bail!("candidate sing-box version differs: expected {expected_version}");
    }
    Ok(())
}

fn verify_sing_box_config(binary: &Path, cache: &Path, repo: &Path) -> Result<()> {
    let template =
        fs::read_to_string(repo.join("deploy/device-runtime/templates/sing-box.base.json"))?;
    let rendered = template
        .replace("{{SING_BOX_LISTEN_HOST}}", "127.0.0.1")
        .replace("{{RELAY_USER}}", "preflight-user")
        .replace("{{RELAY_PASSWORD}}", "preflight-password")
        .replace("{{PROXY_OUTBOUND}}", r#"{"type":"direct","tag":"direct"}"#)
        .replace("{{SING_BOX_FINAL_OUTBOUND}}", "direct");
    let config = cache.join("sing-box-preflight.json");
    let mut file = fs::File::create(&config)?;
    file.write_all(rendered.as_bytes())?;
    file.sync_all()?;
    run(
        Command::new(binary).arg("check").arg("-c").arg(&config),
        repo,
    )
    .context("candidate sing-box rejected the production config template")
}

fn atomic_install(candidate: &Path, destination: &Path) -> Result<()> {
    let parent = destination
        .parent()
        .context("sing-box destination has no parent")?;
    fs::create_dir_all(parent)?;
    let staged = parent.join("sing-box.candidate");
    let rollback = parent.join("sing-box.rollback");
    fs::copy(candidate, &staged)?;
    set_executable(&staged)?;
    if destination.is_file() {
        fs::copy(destination, &rollback)?;
        set_executable(&rollback)?;
    }
    fs::rename(&staged, destination)?;
    Ok(())
}

fn find_file_named(root: &Path, name: &str) -> Option<PathBuf> {
    for entry in fs::read_dir(root).ok()? {
        let entry = entry.ok()?;
        let path = entry.path();
        if path.is_dir() {
            if let Some(found) = find_file_named(&path, name) {
                return Some(found);
            }
        } else if path.file_name().is_some_and(|file| file == name) {
            return Some(path);
        }
    }
    None
}

pub fn ensure_elf_machine(path: &Path, expected_machine: u16, label: &str) -> Result<()> {
    ensure_file(path)?;
    let mut header = [0_u8; 20];
    let mut file = fs::File::open(path)?;
    file.read_exact(&mut header)?;
    let magic = &header[0..4] == b"\x7FELF";
    let little_endian = header[5] == 1;
    let machine = u16::from_le_bytes([header[18], header[19]]);
    if !magic || !little_endian || machine != expected_machine {
        bail!("{label} has wrong ELF header: {}", path.display());
    }
    Ok(())
}

fn set_executable(_path: &Path) -> Result<()> {
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        let mut permissions = fs::metadata(_path)?.permissions();
        permissions.set_mode(0o755);
        fs::set_permissions(_path, permissions)?;
    }
    Ok(())
}

fn ensure_file(path: &Path) -> Result<()> {
    if path.is_file() {
        Ok(())
    } else {
        bail!("missing required file: {}", path.display())
    }
}

fn run(command: &mut Command, cwd: &Path) -> Result<()> {
    let status = command.current_dir(cwd).status()?;
    if status.success() {
        Ok(())
    } else {
        bail!("command failed with status {status}: {:?}", command)
    }
}

fn repo_root() -> Result<PathBuf> {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../..")
        .canonicalize()
        .context("failed to resolve repo root")
}

#[cfg(test)]
mod tests {
    use super::{load_sing_box_lock, required_artifact};
    use std::path::Path;

    #[test]
    fn committed_sing_box_lock_matches_the_default_release() {
        let repo = Path::new(env!("CARGO_MANIFEST_DIR")).join("../..");
        let lock = load_sing_box_lock(&repo.join("deploy/sing-box-artifacts.lock.json"), "1.13.12")
            .unwrap();

        let android = required_artifact(&lock, "android-arm").unwrap();
        let vm = required_artifact(&lock, "linux-amd64-glibc").unwrap();
        assert_eq!(android.size, 18_350_858);
        assert_eq!(vm.size, 24_594_492);
    }

    #[test]
    fn unpinned_version_is_rejected() {
        let repo = Path::new(env!("CARGO_MANIFEST_DIR")).join("../..");
        let result =
            load_sing_box_lock(&repo.join("deploy/sing-box-artifacts.lock.json"), "99.0.0");
        assert!(result.is_err());
    }
}
