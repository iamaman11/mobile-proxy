use std::ffi::OsStr;
use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command;

use anyhow::{Context, Result, bail};

use crate::cli::InstallAndroidAppArgs;

const IGNORED_DIRS: &[&str] = &["build", ".gradle", ".kotlin"];

pub fn install_android_app(args: &InstallAndroidAppArgs) -> Result<()> {
    let user = std::env::var("USER")
        .or_else(|_| std::env::var("USERNAME"))
        .unwrap_or_else(|_| "Bose".to_string());

    let windows_build_dir = args.windows_build_dir.replace("Bose", &user);
    let windows_build_dir_cmd = args.windows_build_dir_cmd.replace("Bose", &user);
    let apk_windows_path = args.apk_windows_path.replace("Bose", &user);

    let project_dir = repo_root()?.join(&args.project_dir);
    let build_dir = PathBuf::from(&windows_build_dir);
    copy_project(&project_dir, &build_dir)?;
    write_local_properties(&build_dir)?;
    run_windows_gradle(&build_dir, &windows_build_dir_cmd)?;
    verify_apk_exists(&build_dir)?;

    if !args.skip_install {
        adb_install(args.device_serial.as_deref(), &apk_windows_path)?;
    }

    println!(
        "Android app prepared{}: {}",
        if args.skip_install {
            ""
        } else {
            " and installed"
        },
        apk_windows_path
    );
    Ok(())
}

fn write_local_properties(build_dir: &Path) -> Result<()> {
    let user = std::env::var("USER")
        .or_else(|_| std::env::var("USERNAME"))
        .unwrap_or_else(|_| "Bose".to_string());
    
    let sdk_dir = std::env::var("ANDROID_SDK_ROOT")
        .or_else(|_| std::env::var("ANDROID_HOME"))
        .unwrap_or_else(|_| format!("C:/Users/{}/AppData/Local/Android/Sdk", user));

    let local_properties = build_dir.join("local.properties");
    fs::write(&local_properties, format!("sdk.dir={sdk_dir}\n")).with_context(|| {
        format!(
            "failed to write Android local properties to {}",
            local_properties.display()
        )
    })
}

fn copy_project(src: &Path, dst: &Path) -> Result<()> {
    if dst.exists() {
        fs::remove_dir_all(dst).with_context(|| format!("failed to remove {}", dst.display()))?;
    }
    fs::create_dir_all(dst).with_context(|| format!("failed to create {}", dst.display()))?;
    copy_dir_contents(src, dst)
}

fn copy_dir_contents(src: &Path, dst: &Path) -> Result<()> {
    for entry in fs::read_dir(src).with_context(|| format!("failed to read {}", src.display()))? {
        let entry = entry?;
        let path = entry.path();
        let name = entry.file_name();
        let target = dst.join(&name);
        if path.is_dir() {
            if is_ignored_dir(&name) {
                continue;
            }
            fs::create_dir_all(&target)
                .with_context(|| format!("failed to create {}", target.display()))?;
            copy_dir_contents(&path, &target)?;
        } else {
            fs::copy(&path, &target).with_context(|| {
                format!("failed to copy {} to {}", path.display(), target.display())
            })?;
        }
    }
    Ok(())
}

fn is_ignored_dir(name: &OsStr) -> bool {
    name.to_str().is_some_and(|raw| IGNORED_DIRS.contains(&raw))
}

fn run_windows_gradle(build_dir: &Path, windows_build_dir_cmd: &str) -> Result<()> {
    let cmd = format!("cd /d {windows_build_dir_cmd} && gradlew.bat clean :app:assembleDebug");
    let status = Command::new("/mnt/c/Windows/System32/cmd.exe")
        .args(["/C", &cmd])
        .current_dir(build_dir)
        .status()
        .context("failed to start Windows Gradle build")?;
    if status.success() {
        Ok(())
    } else {
        bail!("Windows Gradle build failed with status {status}")
    }
}

fn verify_apk_exists(build_dir: &Path) -> Result<()> {
    let apk = build_dir.join("app/build/outputs/apk/debug/app-debug.apk");
    if apk.is_file() {
        Ok(())
    } else {
        bail!("Android APK was not produced at {}", apk.display())
    }
}

fn adb_install(device_serial: Option<&str>, apk_windows_path: &str) -> Result<()> {
    let adb_path = detect_adb()?;
    let mut command = Command::new(adb_path);
    if let Some(serial) = device_serial {
        command.arg("-s").arg(serial);
    }
    let output = command
        .args(["install", "-r", apk_windows_path])
        .output()
        .context("failed to start adb install")?;
    if output.status.success() {
        Ok(())
    } else {
        bail!(
            "adb install failed: {}{}",
            String::from_utf8_lossy(&output.stdout),
            String::from_utf8_lossy(&output.stderr)
        )
    }
}

fn detect_adb() -> Result<PathBuf> {
    let user = std::env::var("USER")
        .or_else(|_| std::env::var("USERNAME"))
        .unwrap_or_else(|_| "Bose".to_string());

    let path_custom_tools = PathBuf::from(format!("/mnt/c/Users/{}/tools/platform-tools/adb.exe", user));
    let path_sdk = PathBuf::from(format!("/mnt/c/Users/{}/AppData/Local/Android/Sdk/platform-tools/adb.exe", user));

    if path_custom_tools.is_file() {
        return Ok(path_custom_tools);
    }
    if path_sdk.is_file() {
        return Ok(path_sdk);
    }

    let bose_custom_tools = PathBuf::from("/mnt/c/Users/Bose/tools/platform-tools/adb.exe");
    let bose_sdk = PathBuf::from("/mnt/c/Users/Bose/AppData/Local/Android/Sdk/platform-tools/adb.exe");

    if bose_custom_tools.is_file() {
        return Ok(bose_custom_tools);
    }
    if bose_sdk.is_file() {
        return Ok(bose_sdk);
    }

    if Command::new("adb").arg("--version").output().is_ok() {
        return Ok(PathBuf::from("adb"));
    }

    bail!("adb.exe not found")
}

fn repo_root() -> Result<PathBuf> {
    Ok(PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .and_then(Path::parent)
        .context("failed to resolve repo root")?
        .to_path_buf())
}

#[cfg(test)]
mod tests {
    use std::ffi::OsStr;

    use super::{is_ignored_dir, write_local_properties};

    #[test]
    fn android_copy_skips_build_outputs() {
        assert!(is_ignored_dir(OsStr::new("build")));
        assert!(is_ignored_dir(OsStr::new(".gradle")));
        assert!(!is_ignored_dir(OsStr::new("src")));
    }

    #[test]
    fn android_build_dir_gets_local_properties() {
        let build_dir = std::env::temp_dir().join(format!(
            "mobile-proxy-android-local-properties-{}",
            uuid::Uuid::new_v4()
        ));
        std::fs::create_dir_all(&build_dir).expect("create temp build dir");

        write_local_properties(&build_dir).expect("write local.properties");

        let content = std::fs::read_to_string(build_dir.join("local.properties"))
            .expect("read local.properties");
        assert!(content.starts_with("sdk.dir="));

        std::fs::remove_dir_all(build_dir).expect("cleanup temp build dir");
    }
}
