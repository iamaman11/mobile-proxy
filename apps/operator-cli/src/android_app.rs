use std::ffi::OsStr;
use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command;
use std::thread;
use std::time::{Duration, Instant};

use anyhow::{Context, Result, bail};

use crate::cli::InstallAndroidAppArgs;

const IGNORED_DIRS: &[&str] = &["build", ".gradle", ".kotlin"];
const ANDROID_GRADLE_QUALITY_TASKS: &str =
    "--no-daemon clean testDebugUnitTest lintDebug assembleDebug";
const WINDOWS_GRADLE_LOG_NAME: &str = "run-mobile-proxy-gradle.log";
const WINDOWS_GRADLE_LAUNCHER_NAME: &str = "run-mobile-proxy-gradle.ps1";
const WINDOWS_GRADLE_COMPLETION_WAIT: Duration = Duration::from_secs(180);

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
    let sdk_dir = sdk_dir_for_local_properties(&sdk_dir);

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

fn sdk_dir_for_local_properties(raw: &str) -> String {
    windows_path_from_wsl_mount(Path::new(raw))
        .unwrap_or_else(|| raw.to_string())
        .replace('\\', "/")
        .replace(':', "\\:")
}

fn run_windows_gradle(build_dir: &Path, windows_build_dir_cmd: &str) -> Result<()> {
    let launcher_path = write_windows_gradle_launcher(build_dir, windows_build_dir_cmd)?;
    let launcher_windows_path = windows_path_from_wsl_mount(&launcher_path).with_context(|| {
        format!(
            "failed to convert Windows Gradle launcher path {}",
            launcher_path.display()
        )
    })?;

    let output = Command::new("/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe")
        .args(["-NoProfile", "-ExecutionPolicy", "Bypass", "-File"])
        .arg(&launcher_windows_path)
        .output()
        .context("failed to start Windows Gradle build")?;

    let cleanup_result = fs::remove_file(&launcher_path);
    if output.status.success() {
        cleanup_result.with_context(|| {
            format!(
                "Windows Gradle build succeeded but failed to remove launcher {}",
                launcher_path.display()
            )
        })?;
        Ok(())
    } else {
        let _ = cleanup_result;
        let log_excerpt = read_windows_gradle_log(build_dir)
            .unwrap_or_else(|_| "launcher log unavailable".to_string());
        bail!(
            "Windows Gradle build failed with status {}; launcher={}; stdout={}; stderr={}; launcher_log={}",
            output.status,
            launcher_path.display(),
            String::from_utf8_lossy(&output.stdout),
            String::from_utf8_lossy(&output.stderr),
            log_excerpt
        )
    }
}

fn verify_apk_exists(build_dir: &Path) -> Result<()> {
    let apk = build_dir.join("app/build/outputs/apk/debug/app-debug.apk");
    let deadline = Instant::now() + WINDOWS_GRADLE_COMPLETION_WAIT;
    loop {
        if apk.is_file() {
            return Ok(());
        }
        if let Ok(log_excerpt) = read_windows_gradle_log(build_dir)
            && log_excerpt.contains("BUILD FAILED")
        {
            bail!(
                "Android Gradle build failed before producing {}; launcher_log={}",
                apk.display(),
                log_excerpt
            );
        }
        if Instant::now() >= deadline {
            let log_excerpt = read_windows_gradle_log(build_dir)
                .unwrap_or_else(|_| "launcher log unavailable".to_string());
            bail!(
                "Android APK was not produced at {} within {:?}; launcher_log={}",
                apk.display(),
                WINDOWS_GRADLE_COMPLETION_WAIT,
                log_excerpt
            );
        }
        thread::sleep(Duration::from_millis(250));
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
    if let Some(configured) = std::env::var_os("MOBILE_PROXY_ADB") {
        let configured = PathBuf::from(configured);
        if configured.is_absolute() && !configured.is_file() {
            bail!(
                "MOBILE_PROXY_ADB points to a missing executable: {}",
                configured.display()
            );
        }
        return Ok(configured);
    }

    let user = std::env::var("USER")
        .or_else(|_| std::env::var("USERNAME"))
        .unwrap_or_else(|_| "Bose".to_string());

    #[cfg(windows)]
    let (path_custom_tools, path_sdk) = (
        PathBuf::from(format!(
            "C:\\Users\\{}\\tools\\platform-tools\\adb.exe",
            user
        )),
        PathBuf::from(format!(
            "C:\\Users\\{}\\AppData\\Local\\Android\\Sdk\\platform-tools\\adb.exe",
            user
        )),
    );

    #[cfg(not(windows))]
    let (path_custom_tools, path_sdk) = (
        PathBuf::from(format!(
            "/mnt/c/Users/{}/tools/platform-tools/adb.exe",
            user
        )),
        PathBuf::from(format!(
            "/mnt/c/Users/{}/AppData/Local/Android/Sdk/platform-tools/adb.exe",
            user
        )),
    );

    #[cfg(not(windows))]
    if std::env::var_os("ADB_SERVER_SOCKET").is_some() && Path::new("/usr/bin/adb").is_file() {
        return Ok(PathBuf::from("/usr/bin/adb"));
    }

    if path_custom_tools.is_file() {
        return Ok(path_custom_tools);
    }
    if path_sdk.is_file() {
        return Ok(path_sdk);
    }

    #[cfg(windows)]
    let (bose_custom_tools, bose_sdk) = (
        PathBuf::from("C:\\Users\\Bose\\tools\\platform-tools\\adb.exe"),
        PathBuf::from("C:\\Users\\Bose\\AppData\\Local\\Android\\Sdk\\platform-tools\\adb.exe"),
    );

    #[cfg(not(windows))]
    let (bose_custom_tools, bose_sdk) = (
        PathBuf::from("/mnt/c/Users/Bose/tools/platform-tools/adb.exe"),
        PathBuf::from("/mnt/c/Users/Bose/AppData/Local/Android/Sdk/platform-tools/adb.exe"),
    );

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

fn detect_windows_java_home() -> Result<Option<String>> {
    let user = std::env::var("USER")
        .or_else(|_| std::env::var("USERNAME"))
        .unwrap_or_else(|_| "Bose".to_string());
    for base in [
        format!("/mnt/c/Users/{user}/mobile-proxy-windows-jdk21"),
        "/mnt/c/Users/Bose/mobile-proxy-windows-jdk21".to_string(),
    ] {
        if let Some(found) = find_windows_java_home(Path::new(&base))? {
            return Ok(Some(found));
        }
    }
    Ok(None)
}

fn find_windows_java_home(base: &Path) -> Result<Option<String>> {
    if !base.is_dir() {
        return Ok(None);
    }
    for entry in fs::read_dir(base).with_context(|| format!("failed to read {}", base.display()))? {
        let entry = entry?;
        let path = entry.path();
        if !path.is_dir() || !path.join("bin/java.exe").is_file() {
            continue;
        }
        if let Some(windows) = windows_path_from_wsl_mount(&path) {
            return Ok(Some(windows));
        }
    }
    Ok(None)
}

fn windows_path_from_wsl_mount(path: &Path) -> Option<String> {
    let windows = path.to_str()?.replace('/', "\\");
    if windows.len() >= 7 && windows.starts_with(r"\mnt\c\") {
        return Some(format!("C:{}", &windows[6..]));
    }
    None
}

fn windows_cmd_quoted(raw: &str) -> String {
    format!("\"{}\"", raw.replace('"', ""))
}

fn windows_powershell_single_quoted(raw: &str) -> String {
    format!("'{}'", raw.replace('\'', "''"))
}

fn repo_root() -> Result<PathBuf> {
    Ok(PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .and_then(Path::parent)
        .context("failed to resolve repo root")?
        .to_path_buf())
}

fn write_windows_gradle_launcher(build_dir: &Path, windows_build_dir_cmd: &str) -> Result<PathBuf> {
    let launcher_path = build_dir.join(WINDOWS_GRADLE_LAUNCHER_NAME);
    let log_windows_path = windows_path_from_wsl_mount(&build_dir.join(WINDOWS_GRADLE_LOG_NAME))
        .with_context(|| {
            format!(
                "failed to convert Windows Gradle log path {}",
                build_dir.join(WINDOWS_GRADLE_LOG_NAME).display()
            )
        })?;
    let launcher_content =
        windows_gradle_launcher_content(windows_build_dir_cmd, &log_windows_path)?;
    fs::write(&launcher_path, launcher_content).with_context(|| {
        format!(
            "failed to write Windows Gradle launcher to {}",
            launcher_path.display()
        )
    })?;
    Ok(launcher_path)
}

fn read_windows_gradle_log(build_dir: &Path) -> Result<String> {
    let log = fs::read_to_string(build_dir.join(WINDOWS_GRADLE_LOG_NAME)).with_context(|| {
        format!(
            "failed to read Windows Gradle log from {}",
            build_dir.join(WINDOWS_GRADLE_LOG_NAME).display()
        )
    })?;
    Ok(log.replace('\r', " ").replace('\n', " | "))
}

fn windows_gradle_launcher_content(
    windows_build_dir_cmd: &str,
    log_windows_path: &str,
) -> Result<String> {
    let mut lines = vec![
        "$ErrorActionPreference = 'Stop'".to_string(),
        "$ProgressPreference = 'SilentlyContinue'".to_string(),
    ];
    lines.extend(windows_gradle_env_lines());
    if let Some(java_home) = detect_windows_java_home()? {
        lines.push(format!(
            "$env:JAVA_HOME = {}",
            windows_powershell_single_quoted(&java_home)
        ));
        lines.push(r#"$env:PATH = "$env:JAVA_HOME\bin;$env:PATH""#.to_string());
    }
    lines.push(format!(
        "Set-Location -LiteralPath {}",
        windows_powershell_single_quoted(windows_build_dir_cmd)
    ));
    lines.push(format!(
        "Set-Content -LiteralPath {} -Value 'launcher_started'",
        windows_powershell_single_quoted(log_windows_path)
    ));
    let gradle_cmd = format!(
        "call gradlew.bat {ANDROID_GRADLE_QUALITY_TASKS} >> {} 2>&1",
        windows_cmd_quoted(log_windows_path)
    );
    lines.push(format!(
        "& 'C:\\Windows\\System32\\cmd.exe' /d /c {}",
        windows_powershell_single_quoted(&gradle_cmd)
    ));
    lines.push("$exitCode = $LASTEXITCODE".to_string());
    lines.push(format!(
        "Add-Content -LiteralPath {} -Value \"gradle_exit_code=$exitCode\"",
        windows_powershell_single_quoted(log_windows_path)
    ));
    lines.push("exit $exitCode".to_string());
    Ok(lines.join("\r\n") + "\r\n")
}

fn windows_gradle_env_lines() -> Vec<String> {
    vec![
        "$env:http_proxy = ''".to_string(),
        "$env:https_proxy = ''".to_string(),
        "$env:HTTP_PROXY = ''".to_string(),
        "$env:HTTPS_PROXY = ''".to_string(),
        "$env:all_proxy = ''".to_string(),
        "$env:ALL_PROXY = ''".to_string(),
        "$env:no_proxy = ''".to_string(),
        "$env:NO_PROXY = ''".to_string(),
        "$env:JAVA_TOOL_OPTIONS = '-Djdk.tls.client.protocols=TLSv1.2,TLSv1.3 -Dhttps.protocols=TLSv1.2,TLSv1.3'".to_string(),
    ]
}

#[cfg(test)]
mod tests {
    use std::ffi::OsStr;
    use std::path::Path;

    use super::{
        ANDROID_GRADLE_QUALITY_TASKS, WINDOWS_GRADLE_LAUNCHER_NAME, WINDOWS_GRADLE_LOG_NAME,
        is_ignored_dir, sdk_dir_for_local_properties, windows_cmd_quoted, windows_gradle_env_lines,
        windows_gradle_launcher_content, windows_path_from_wsl_mount,
        windows_powershell_single_quoted, write_local_properties,
    };

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
        assert!(content.ends_with('\n'));

        std::fs::remove_dir_all(build_dir).expect("cleanup temp build dir");
    }

    #[test]
    fn local_properties_sdk_dir_normalizes_wsl_and_escapes_windows_drive_paths() {
        assert_eq!(
            sdk_dir_for_local_properties("/mnt/c/Users/Bose/AppData/Local/Android/Sdk"),
            r"C\:/Users/Bose/AppData/Local/Android/Sdk"
        );
        assert_eq!(
            sdk_dir_for_local_properties(r"C:\Users\Bose\AppData\Local\Android\Sdk"),
            r"C\:/Users/Bose/AppData/Local/Android/Sdk"
        );
    }

    #[test]
    fn windows_gradle_env_lines_clear_proxy_variables_and_pin_tls_protocols() {
        let lines = windows_gradle_env_lines();
        for key in [
            "http_proxy",
            "https_proxy",
            "HTTP_PROXY",
            "HTTPS_PROXY",
            "all_proxy",
            "ALL_PROXY",
            "no_proxy",
            "NO_PROXY",
        ] {
            assert!(lines.iter().any(|line| line == &format!("$env:{key} = ''")));
        }
        assert!(lines.iter().any(|line| {
            line == "$env:JAVA_TOOL_OPTIONS = '-Djdk.tls.client.protocols=TLSv1.2,TLSv1.3 -Dhttps.protocols=TLSv1.2,TLSv1.3'"
        }));
    }

    #[test]
    fn windows_gradle_env_lines_are_explicit_and_ordered() {
        let lines = windows_gradle_env_lines();
        assert_eq!(
            lines.first().expect("first env line"),
            "$env:http_proxy = ''"
        );
        assert_eq!(
            lines.last().expect("last env line"),
            "$env:JAVA_TOOL_OPTIONS = '-Djdk.tls.client.protocols=TLSv1.2,TLSv1.3 -Dhttps.protocols=TLSv1.2,TLSv1.3'"
        );
        assert_eq!(lines.len(), 9);
    }

    #[test]
    fn windows_gradle_launcher_uses_powershell_script_and_cmd_bridge() {
        let launcher = windows_gradle_launcher_content(
            r"C:\Users\Bose\mobile-proxy-android-build",
            r"C:\Users\Bose\mobile-proxy-android-build\run-mobile-proxy-gradle.log",
        )
        .expect("build launcher content");
        assert!(launcher.starts_with("$ErrorActionPreference = 'Stop'\r\n"));
        assert!(launcher.contains("$ProgressPreference = 'SilentlyContinue'\r\n"));
        assert!(launcher.contains(
            "Set-Location -LiteralPath 'C:\\Users\\Bose\\mobile-proxy-android-build'\r\n"
        ));
        assert!(launcher.contains(&format!(
            "Set-Content -LiteralPath 'C:\\Users\\Bose\\mobile-proxy-android-build\\{WINDOWS_GRADLE_LOG_NAME}' -Value 'launcher_started'\r\n"
        )));
        assert!(launcher.contains(&format!(
            "& 'C:\\Windows\\System32\\cmd.exe' /d /c 'call gradlew.bat {ANDROID_GRADLE_QUALITY_TASKS} >> \"C:\\Users\\Bose\\mobile-proxy-android-build\\{WINDOWS_GRADLE_LOG_NAME}\" 2>&1'\r\n"
        )));
        assert!(launcher.contains(&format!(
            "Add-Content -LiteralPath 'C:\\Users\\Bose\\mobile-proxy-android-build\\{WINDOWS_GRADLE_LOG_NAME}' -Value \"gradle_exit_code=$exitCode\"\r\n"
        )));
        assert!(launcher.contains("$exitCode = $LASTEXITCODE\r\n"));
        assert!(launcher.contains("exit $exitCode\r\n"));
        assert!(launcher.contains("$env:http_proxy = ''\r\n"));
    }

    #[test]
    fn windows_gradle_launcher_quotes_build_dir_with_spaces() {
        let launcher = windows_gradle_launcher_content(
            r"C:\Users\Bose\Mobile Proxy Build",
            r"C:\Users\Bose\Mobile Proxy Build\run-mobile-proxy-gradle.log",
        )
        .expect("build launcher content");
        assert!(
            launcher
                .contains("Set-Location -LiteralPath 'C:\\Users\\Bose\\Mobile Proxy Build'\r\n")
        );
        assert!(launcher.contains(
            "Set-Content -LiteralPath 'C:\\Users\\Bose\\Mobile Proxy Build\\run-mobile-proxy-gradle.log' -Value 'launcher_started'\r\n"
        ));
    }

    #[test]
    fn windows_cmd_quoted_wraps_and_strips_inner_quotes() {
        assert_eq!(
            windows_cmd_quoted(r#"C:\Users\Bose\Mobile Proxy Build"#),
            r#""C:\Users\Bose\Mobile Proxy Build""#
        );
        assert_eq!(
            windows_cmd_quoted(r#""C:\Temp\Quoted""#),
            r#""C:\Temp\Quoted""#
        );
    }

    #[test]
    fn windows_powershell_single_quoted_wraps_and_escapes_paths() {
        assert_eq!(
            windows_powershell_single_quoted(r#"C:\Users\Bose\Mobile Proxy Build\run.cmd"#),
            r#"'C:\Users\Bose\Mobile Proxy Build\run.cmd'"#
        );
        assert_eq!(
            windows_powershell_single_quoted(r#"C:\Users\Bose\Bob's Build\run.cmd"#),
            r#"'C:\Users\Bose\Bob''s Build\run.cmd'"#
        );
    }

    #[test]
    fn converts_mnt_c_path_to_windows_java_home() {
        let detected = windows_path_from_wsl_mount(Path::new(
            "/mnt/c/Users/Bose/mobile-proxy-windows-jdk21/jdk-21.0.11+10",
        ))
        .expect("convert WSL mount path");
        assert_eq!(
            detected,
            r"C:\Users\Bose\mobile-proxy-windows-jdk21\jdk-21.0.11+10"
        );
    }

    #[test]
    fn windows_gradle_launcher_name_is_powershell_script() {
        assert_eq!(WINDOWS_GRADLE_LAUNCHER_NAME, "run-mobile-proxy-gradle.ps1");
    }
}
