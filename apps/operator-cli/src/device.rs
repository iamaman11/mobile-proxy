use std::env;
use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command;
use std::time::Duration;

use anyhow::{Context, Result, bail};
use proxy_core::HealthRecord;
use reqwest::Proxy;
use serde::Deserialize;
use tokio::time::sleep;

use crate::cli::{
    InstallDeviceReleaseArgs, PackageDeviceReleaseArgs, RollbackDeviceArgs, VerifyDeviceArgs,
};
use crate::provision::package_device_release;

const FIRST_PARTY_ANDROID_PACKAGE: &str = "com.example.mobileproxy";
const FIRST_PARTY_VPN_SERVICE: &str = "GoBackend$VpnService";
const FIRST_PARTY_TUNNEL_RECEIVER: &str = "TunnelCommandReceiver";

#[derive(Debug, Deserialize)]
struct DeviceManifest {
    #[serde(rename = "deviceId")]
    device_id: String,
    tokens: ManifestTokens,
    relay: ManifestRelay,
}

#[derive(Debug, Deserialize)]
struct ManifestTokens {
    #[serde(rename = "adminTokenEnv")]
    admin_token_env: String,
    #[serde(rename = "relayUserEnv")]
    relay_user_env: String,
    #[serde(rename = "relayPasswordEnv")]
    relay_password_env: String,
}

#[derive(Debug, Deserialize)]
struct ManifestRelay {
    host: String,
    #[serde(rename = "httpPort")]
    http_port: Option<u16>,
}

pub async fn install_device_release(args: &InstallDeviceReleaseArgs) -> Result<()> {
    package_device_release(&PackageDeviceReleaseArgs {
        manifest_path: args.manifest_path.clone(),
        release_id: args.release_id.clone(),
        output_dir: args.output_dir.clone(),
        host_daemon_config_path: args.host_daemon_config_path.clone(),
        sing_box_config_path: args.sing_box_config_path.clone(),
        tunnel_owner: args.tunnel_owner.clone(),
    })?;

    let manifest = load_manifest(&args.manifest_path)?;
    let admin_token = required_env(&manifest.tokens.admin_token_env)?;
    let release_root = repo_root()?.join(&args.output_dir).join(&args.release_id);

    ensure_root_access(args.device_serial.as_deref())?;
    adb(
        args.device_serial.as_deref(),
        &[
            "shell",
            "mkdir",
            "-p",
            &format!("{}/{}", args.temp_root, args.release_id),
        ],
    )?;
    adb(
        args.device_serial.as_deref(),
        &[
            "push",
            release_root.to_str().context("invalid release root path")?,
            &args.temp_root,
        ],
    )?;

    let apply_script = format!(
        "set -eu\nROOT='{device_root}'\nREL='{release_id}'\nTMP='{temp_root}/{release_id}'\nBOOT='/data/adb/service.d/99-mobile-proxy-runtime.sh'\nTARGET=\"$ROOT/releases/$REL\"\nCURRENT=\"$(readlink \"$ROOT/current\" 2>/dev/null || true)\"\nmkdir -p \"$ROOT/releases\" \"$ROOT/logs\" /data/adb/service.d\nif [ \"$CURRENT\" = \"$TARGET\" ]; then\n  if command -v pkill >/dev/null 2>&1; then\n    pkill -f \"$ROOT/.*/bin/runtime-supervisor\" || true\n    pkill -f \"$ROOT/.*/bin/host-daemon\" || true\n    pkill -f \"$ROOT/.*/bin/sing-box\" || true\n  fi\n  for pid in $(pidof runtime-supervisor host-daemon sing-box 2>/dev/null || true); do\n    kill \"$pid\" || true\n  done\n  sleep 1\nfi\nrm -rf \"$TARGET\"\nmkdir -p \"$TARGET\"\ncp -R \"$TMP/\"* \"$TARGET/\"\nchmod +x \"$TARGET/service.sh\" \"$TARGET/bin/runtime-supervisor\" \"$TARGET/bin/host-daemon\" \"$TARGET/bin/sing-box\" \"$TARGET/bin/curl\"\nln -sfn \"$TARGET\" \"$ROOT/current\"\nrm -f /data/adb/service.d/99-mobile-proxy-routefix.sh\ncat > \"$BOOT\" <<'MOBILE_PROXY_BOOT'\n#!/system/bin/sh\nROOT='/data/adb/mobile-proxy-node'\nLOG_DIR='/data/local/tmp/mobile-proxy-logs'\nmkdir -p \"$LOG_DIR\"\nsleep 20\nif [ -x \"$ROOT/current/service.sh\" ]; then\n  sh \"$ROOT/current/service.sh\" >> \"$LOG_DIR/boot-service.log\" 2>&1\nelse\n  echo \"$(date '+%Y-%m-%dT%H:%M:%S%z') missing $ROOT/current/service.sh\" >> \"$LOG_DIR/boot-service.log\"\nfi\nMOBILE_PROXY_BOOT\nchmod 0700 \"$BOOT\"\nsh \"$ROOT/current/service.sh\"\n",
        device_root = args.device_root,
        release_id = args.release_id,
        temp_root = args.temp_root,
    );
    let apply_path = write_temp_file("mobile-proxy-apply.sh", &apply_script)?;
    adb(
        args.device_serial.as_deref(),
        &[
            "push",
            apply_path.to_str().context("invalid apply script path")?,
            &format!("{}/apply.sh", args.temp_root),
        ],
    )?;
    adb(
        args.device_serial.as_deref(),
        &[
            "shell",
            "su",
            "0",
            "sh",
            "-c",
            &format!("sh {}/apply.sh", args.temp_root),
        ],
    )?;

    let health = wait_for_health(
        args.device_serial.as_deref(),
        args.health_port,
        &admin_token,
        75,
        2,
    )
    .await?;
    assert_healthy(&health)?;

    if !args.skip_proxy_smoke {
        proxy_smoke(&manifest).await?;
    }

    println!(
        "Device runtime installed: release={} device={} readiness={}",
        args.release_id, manifest.device_id, health.readiness_state
    );
    Ok(())
}

pub async fn verify_device(args: &VerifyDeviceArgs) -> Result<()> {
    let manifest = load_manifest(&args.manifest_path)?;
    let admin_token = required_env(&manifest.tokens.admin_token_env)?;
    let health = fetch_device_health(
        args.device_serial.as_deref(),
        args.health_port,
        &admin_token,
    )
    .await?;
    if let Some(required) = &args.required_tunnel_owner
        && health.tunnel_owner.as_deref() != Some(required.as_str())
    {
        bail!(
            "device tunnel owner mismatch: expected={} actual={:?}",
            required,
            health.tunnel_owner
        );
    }
    let packages = adb(
        args.device_serial.as_deref(),
        &[
            "shell",
            "pm",
            "list",
            "packages",
            FIRST_PARTY_ANDROID_PACKAGE,
        ],
    )?;
    let app_installed = packages.contains(FIRST_PARTY_ANDROID_PACKAGE);
    assert_healthy(&health)?;
    if !app_installed {
        bail!(
            "device health is healthy, but first-party Android package {} is missing",
            FIRST_PARTY_ANDROID_PACKAGE
        );
    }
    let package_dump = adb(
        args.device_serial.as_deref(),
        &["shell", "dumpsys", "package", FIRST_PARTY_ANDROID_PACKAGE],
    )?;
    if !package_dump.contains(FIRST_PARTY_VPN_SERVICE)
        || !package_dump.contains(FIRST_PARTY_TUNNEL_RECEIVER)
    {
        bail!(
            "first-party Android package {} is installed, but required VPN service/receiver entries are missing",
            FIRST_PARTY_ANDROID_PACKAGE
        );
    }
    if !args.skip_proxy_smoke {
        proxy_smoke(&manifest).await?;
    }
    println!(
        "Device verify passed: node={} ip={:?}",
        health.node_id, health.last_public_ip
    );
    Ok(())
}

pub async fn rollback_device(args: &RollbackDeviceArgs) -> Result<()> {
    let manifest = load_manifest(&args.manifest_path)?;
    let admin_token = required_env(&manifest.tokens.admin_token_env)?;
    ensure_root_access(args.device_serial.as_deref())?;

    let current = adb(
        args.device_serial.as_deref(),
        &[
            "shell",
            "su",
            "0",
            "sh",
            "-c",
            &format!("readlink {}/current", args.device_root),
        ],
    )?;
    let current_release = Path::new(current.trim())
        .file_name()
        .and_then(|name| name.to_str())
        .unwrap_or_default()
        .to_string();
    let releases = adb(
        args.device_serial.as_deref(),
        &[
            "shell",
            "su",
            "0",
            "sh",
            "-c",
            &format!("ls -1t {}/releases", args.device_root),
        ],
    )?;
    let target_release = args.release_id.clone().or_else(|| {
        releases
            .lines()
            .map(str::trim)
            .find(|release| !release.is_empty() && *release != current_release)
            .map(ToOwned::to_owned)
    });
    let target_release = target_release.context("could not select rollback target release")?;

    adb(
        args.device_serial.as_deref(),
        &[
            "shell",
            "su",
            "0",
            "sh",
            "-c",
            &format!(
                "set -eu; ln -sfn {root}/releases/{release} {root}/current; sh {root}/current/service.sh",
                root = args.device_root,
                release = target_release
            ),
        ],
    )?;

    let health = wait_for_health(
        args.device_serial.as_deref(),
        args.health_port,
        &admin_token,
        40,
        2,
    )
    .await?;
    assert_healthy(&health)?;
    println!(
        "Rollback applied: current={} readiness={}",
        target_release, health.readiness_state
    );
    Ok(())
}

async fn fetch_device_health(
    device_serial: Option<&str>,
    health_port: u16,
    admin_token: &str,
) -> Result<HealthRecord> {
    adb(
        device_serial,
        &["forward", &format!("tcp:{health_port}"), "tcp:8088"],
    )?;
    let raw = windows_curl(
        &format!("http://127.0.0.1:{health_port}/v1/health"),
        admin_token,
    )?;
    serde_json::from_str(&raw).context("failed to parse health payload")
}

async fn wait_for_health(
    device_serial: Option<&str>,
    health_port: u16,
    admin_token: &str,
    attempts: u32,
    poll_secs: u64,
) -> Result<HealthRecord> {
    let mut last_error = None;
    for _ in 0..attempts {
        match fetch_device_health(device_serial, health_port, admin_token).await {
            Ok(health) => {
                if health.readiness_state == "healthy"
                    && health.serving
                    && health.proxy_status == "running"
                {
                    return Ok(health);
                }
                last_error = Some(format!(
                    "readiness={} serving={} proxy_status={} reason={:?}",
                    health.readiness_state,
                    health.serving,
                    health.proxy_status,
                    health.degradation_reason_code
                ));
            }
            Err(err) => last_error = Some(err.to_string()),
        }
        sleep(Duration::from_secs(poll_secs.max(1))).await;
    }
    bail!(
        "device health did not become healthy: {}",
        last_error.unwrap_or_else(|| "unknown error".into())
    )
}

fn assert_healthy(health: &HealthRecord) -> Result<()> {
    if health.readiness_state == "healthy" && health.serving && health.proxy_status == "running" {
        return Ok(());
    }
    bail!(
        "health check failed: readiness={} serving={} proxy_status={} reason={:?} last_proxy_error={:?}",
        health.readiness_state,
        health.serving,
        health.proxy_status,
        health.degradation_reason_code,
        health.last_proxy_error
    )
}

async fn proxy_smoke(manifest: &DeviceManifest) -> Result<()> {
    let relay_user = required_env(&manifest.tokens.relay_user_env)?;
    let relay_password = required_env(&manifest.tokens.relay_password_env)?;
    let proxy_url = format!(
        "http://{}:{}@{}:{}",
        relay_user,
        relay_password,
        manifest.relay.host,
        manifest.relay.http_port.unwrap_or(3128)
    );
    let client = reqwest::Client::builder()
        .proxy(Proxy::http(&proxy_url)?)
        .timeout(Duration::from_secs(15))
        .build()
        .context("failed to build proxy smoke client")?;
    client
        .get("http://api.ipify.org")
        .send()
        .await?
        .error_for_status()?;
    Ok(())
}

fn adb(device_serial: Option<&str>, args: &[&str]) -> Result<String> {
    let adb_path = detect_adb()?;
    let mut command = Command::new(adb_path);
    if let Some(serial) = device_serial {
        command.arg("-s").arg(serial);
    }
    command.args(args);
    let output = command.output().context("failed to start adb")?;
    if output.status.success() {
        Ok(String::from_utf8_lossy(&output.stdout).trim().to_string())
    } else {
        bail!(
            "adb {} failed: {}",
            args.join(" "),
            String::from_utf8_lossy(&output.stderr).trim()
        )
    }
}

fn ensure_root_access(device_serial: Option<&str>) -> Result<()> {
    let root_check = adb(device_serial, &["shell", "su", "0", "sh", "-c", "id"])?;
    if root_check.contains("uid=0") {
        Ok(())
    } else {
        bail!("root access is required on device, but 'su 0 sh -c id' did not return uid=0")
    }
}

fn windows_curl(url: &str, admin_token: &str) -> Result<String> {
    let curl_path = detect_windows_curl()?;
    let output = Command::new(curl_path)
        .arg("--silent")
        .arg("--show-error")
        .arg("--fail")
        .arg("-H")
        .arg(format!("Authorization: Bearer {admin_token}"))
        .arg(url)
        .output()
        .context("failed to start curl.exe")?;
    if output.status.success() {
        Ok(String::from_utf8_lossy(&output.stdout).trim().to_string())
    } else {
        bail!(
            "curl.exe {} failed: {}",
            url,
            String::from_utf8_lossy(&output.stderr).trim()
        )
    }
}

fn load_manifest(path: &str) -> Result<DeviceManifest> {
    let manifest_path = resolve_repo_path(path)?;
    serde_json::from_str(
        &fs::read_to_string(&manifest_path)
            .with_context(|| format!("failed to read manifest {}", manifest_path.display()))?,
    )
    .with_context(|| format!("failed to parse manifest {}", manifest_path.display()))
}

fn repo_root() -> Result<PathBuf> {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../..")
        .canonicalize()
        .context("failed to resolve repo root")
}

fn resolve_repo_path(raw: &str) -> Result<PathBuf> {
    let repo_root = repo_root()?;
    let path = Path::new(raw);
    Ok(if path.is_absolute() {
        path.to_path_buf()
    } else {
        repo_root.join(path)
    })
}

fn required_env(name: &str) -> Result<String> {
    env::var(name).with_context(|| format!("missing required environment variable: {name}"))
}

fn detect_adb() -> Result<PathBuf> {
    let candidates = [
        "/mnt/c/Users/Bose/tools/platform-tools/adb.exe",
        "/mnt/c/Users/Bose/AppData/Local/Android/Sdk/platform-tools/adb.exe",
        "/usr/bin/adb",
        "adb",
    ];
    detect_tool(&candidates, "adb")
}

fn detect_windows_curl() -> Result<PathBuf> {
    let candidates = ["/mnt/c/Windows/System32/curl.exe", "curl.exe"];
    detect_tool(&candidates, "curl.exe")
}

fn detect_tool(candidates: &[&str], tool_name: &str) -> Result<PathBuf> {
    for candidate in candidates {
        let path = Path::new(candidate);
        if path.is_absolute() && path.exists() {
            return Ok(path.to_path_buf());
        }
        if !path.is_absolute() {
            return Ok(path.to_path_buf());
        }
    }
    bail!("failed to locate {}", tool_name)
}

fn write_temp_file(name: &str, body: &str) -> Result<PathBuf> {
    let path = env::temp_dir().join(name);
    fs::write(&path, body).with_context(|| format!("failed to write {}", path.display()))?;
    Ok(path)
}
