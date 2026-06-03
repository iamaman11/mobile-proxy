use std::fs;
use std::io::Read;
use std::path::{Path, PathBuf};
use std::process::Command;

use anyhow::{Context, Result, bail};

use crate::cli::PrepareRuntimeBinariesArgs;

const ANDROID_TARGET: &str = "armv7-linux-androideabi";

pub fn prepare_runtime_binaries(args: &PrepareRuntimeBinariesArgs) -> Result<()> {
    let repo = repo_root()?;
    if !args.skip_android_rust_build {
        build_android_rust(&repo, args)?;
        install_android_rust_binaries(&repo, args)?;
    }
    if !args.skip_sing_box_download {
        install_sing_box(&repo, &args.sing_box_version)?;
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

fn install_sing_box(repo: &Path, version: &str) -> Result<()> {
    let cache = repo.join("target/artifacts/sing-box");
    fs::create_dir_all(&cache)?;
    fs::create_dir_all(repo.join("deploy/device-runtime/bin"))?;
    fs::create_dir_all(repo.join("deploy/vm-runtime/bin"))?;

    download_and_extract_sing_box(
        repo,
        &cache,
        version,
        "android-arm",
        &repo.join("deploy/device-runtime/bin/sing-box"),
    )?;
    download_and_extract_sing_box(
        repo,
        &cache,
        version,
        "linux-amd64-glibc",
        &repo.join("deploy/vm-runtime/bin/sing-box"),
    )?;
    Ok(())
}

fn download_and_extract_sing_box(
    repo: &Path,
    cache: &Path,
    version: &str,
    target: &str,
    destination: &Path,
) -> Result<()> {
    let archive = cache.join(format!("sing-box-{version}-{target}.tar.gz"));
    let extract_dir = cache.join(format!("sing-box-{version}-{target}"));
    let url = format!(
        "https://github.com/SagerNet/sing-box/releases/download/v{version}/sing-box-{version}-{target}.tar.gz"
    );
    if !archive.is_file() {
        run(
            Command::new("curl")
                .arg("-fL")
                .arg("--retry")
                .arg("3")
                .arg("-o")
                .arg(&archive)
                .arg(&url),
            repo,
        )?;
    }
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
    fs::copy(binary, destination)?;
    set_executable(destination)?;
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

fn set_executable(path: &Path) -> Result<()> {
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        let mut permissions = fs::metadata(path)?.permissions();
        permissions.set_mode(0o755);
        fs::set_permissions(path, permissions)?;
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
