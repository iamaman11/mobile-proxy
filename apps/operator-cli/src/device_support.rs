use std::env;
use std::fs;
use std::io::Write;
#[cfg(unix)]
use std::os::unix::fs::PermissionsExt;
use std::path::{Component, Path, PathBuf};
use std::process::{Command, Output, Stdio};
use std::time::Duration;

use anyhow::{Context, Result, bail};
use proxy_core::HealthRecord;
use reqwest::Proxy;
use serde::Deserialize;
use serde_json::Value;
use tokio::time::sleep;

pub(crate) const PRIMARY_TUNNEL_OWNER: &str = "first_party_reverse_tunnel";
pub(crate) const STOCK_WIREGUARD_OWNER: &str = "stock_wireguard_bridge";
pub(crate) const APP_OWNED_TUNNEL_OWNER: &str = "first_party_vpn_service";
const STOCK_WIREGUARD_PACKAGE: &str = "com.wireguard.android";
const APP_OWNED_TUNNEL_PACKAGE: &str = "com.example.mobileproxy";
const APP_OWNED_TUNNEL_DISABLED_REASON: &str = "first_party_vpn_service is disabled after physical validation on July 26, 2026: Android VpnService did not expose a routable 10.66.66.2 listener for the rooted proxy runtime";

#[derive(Debug, Deserialize)]
pub(crate) struct DeviceManifest {
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

impl DeviceManifest {
    pub(crate) fn device_id(&self) -> &str {
        &self.device_id
    }
}

pub(crate) fn load_manifest(path: &str) -> Result<DeviceManifest> {
    let manifest_path = resolve_repo_path(path)?;
    serde_json::from_str(
        &fs::read_to_string(&manifest_path)
            .with_context(|| format!("failed to read manifest {}", manifest_path.display()))?,
    )
    .with_context(|| format!("failed to parse manifest {}", manifest_path.display()))
}

pub(crate) fn admin_token(manifest: &DeviceManifest) -> Result<String> {
    required_env(&manifest.tokens.admin_token_env)
}

pub(crate) fn release_root(output_dir: &str, release_id: &str) -> Result<PathBuf> {
    Ok(repo_root()?.join(output_dir).join(release_id))
}

pub(crate) fn validate_tunnel_owner(value: &str) -> Result<()> {
    match value {
        PRIMARY_TUNNEL_OWNER | STOCK_WIREGUARD_OWNER => Ok(()),
        APP_OWNED_TUNNEL_OWNER => bail!("{APP_OWNED_TUNNEL_DISABLED_REASON}"),
        other => bail!(
            "unsupported tunnel owner {other}; expected {PRIMARY_TUNNEL_OWNER} or {STOCK_WIREGUARD_OWNER}"
        ),
    }
}

pub(crate) fn validate_release_id(value: &str) -> Result<()> {
    let first = value.chars().next();
    let last = value.chars().last();
    if value.is_empty()
        || value.len() > 64
        || !first.is_some_and(|character| character.is_ascii_alphanumeric())
        || !last.is_some_and(|character| character.is_ascii_alphanumeric())
        || !value.chars().all(|character| {
            character.is_ascii_alphanumeric() || matches!(character, '-' | '_' | '.')
        })
    {
        bail!("release_id is invalid")
    }
    Ok(())
}

pub(crate) fn validate_device_path(value: &str, field: &str) -> Result<()> {
    let path = Path::new(value);
    let mut components = path.components();
    if value.len() > 256
        || !matches!(components.next(), Some(Component::RootDir))
        || components.clone().next().is_none()
        || components.any(|component| !matches!(component, Component::Normal(_)))
        || value.chars().any(|character| {
            !(character.is_ascii_alphanumeric() || matches!(character, '/' | '-' | '_' | '.'))
        })
    {
        bail!("{field} is invalid")
    }
    Ok(())
}

pub(crate) fn shell_quote_validated(value: &str) -> String {
    debug_assert!(!value.contains('\''));
    format!("'{value}'")
}

pub(crate) fn ensure_root_access(device_serial: Option<&str>) -> Result<()> {
    let root_check = adb(device_serial, &["shell", "su", "0", "sh", "-c", "id"])?;
    if root_check.contains("uid=0") {
        Ok(())
    } else {
        bail!("root access is required on device")
    }
}

pub(crate) fn adb(device_serial: Option<&str>, args: &[&str]) -> Result<String> {
    let output = adb_output(device_serial, args)?;
    Ok(String::from_utf8_lossy(&output.stdout).trim().to_string())
}

fn adb_bytes(device_serial: Option<&str>, args: &[&str]) -> Result<Vec<u8>> {
    Ok(adb_output(device_serial, args)?.stdout)
}

fn adb_output(device_serial: Option<&str>, args: &[&str]) -> Result<Output> {
    let adb_path = detect_adb()?;
    let mut command = Command::new(&adb_path);
    if let Some(serial) = device_serial {
        command.arg("-s").arg(serial);
    }
    command.args(args);
    let output = command
        .output()
        .with_context(|| format!("failed to start adb at {}", adb_path.display()))?;
    if output.status.success() {
        Ok(output)
    } else {
        bail!(
            "adb command failed: {}",
            String::from_utf8_lossy(&output.stderr).trim()
        )
    }
}

pub(crate) fn write_temp_script(stem: &str, body: &str) -> Result<PathBuf> {
    let path = env::temp_dir().join(format!("{stem}-{}.sh", std::process::id()));
    fs::write(&path, body).with_context(|| format!("failed to write {}", path.display()))?;
    #[cfg(unix)]
    fs::set_permissions(&path, fs::Permissions::from_mode(0o600))?;
    Ok(path)
}

pub(crate) fn verify_installed_release_files(
    root: &Path,
    device_serial: Option<&str>,
    device_root: &str,
) -> Result<()> {
    let manifest_path = root.join("integrity-manifest.json");
    let manifest: Value = serde_json::from_slice(
        &fs::read(&manifest_path)
            .with_context(|| format!("failed to read {}", manifest_path.display()))?,
    )?;
    if manifest["format_version"] != 1
        || manifest["algorithm"] != "blake3-256"
        || manifest["domain"] != "mobile-proxy/release-file/v1"
    {
        bail!("release integrity manifest metadata is unsupported")
    }
    let entries = manifest["entries"]
        .as_array()
        .context("release integrity manifest entries are missing")?;
    if entries.is_empty() || entries.len() > 128 {
        bail!("release integrity manifest inventory is invalid")
    }
    for entry in entries {
        let relative = entry["path"]
            .as_str()
            .context("release integrity path is invalid")?;
        validate_relative_release_path(relative)?;
        let local = fs::read(root.join(relative))
            .with_context(|| format!("failed to read packaged release file {relative}"))?;
        let remote = format!("{}/current/{}", device_root.trim_end_matches('/'), relative);
        let deployed = adb_bytes(device_serial, &["exec-out", "su", "0", "cat", &remote])?;
        if local != deployed {
            bail!("deployed device release file differs: {relative}")
        }
    }
    Ok(())
}

fn validate_relative_release_path(value: &str) -> Result<()> {
    let path = Path::new(value);
    if value.is_empty()
        || path.is_absolute()
        || path
            .components()
            .any(|component| !matches!(component, Component::Normal(_)))
    {
        bail!("invalid release-relative path")
    }
    Ok(())
}

pub(crate) async fn wait_for_health(
    device_serial: Option<&str>,
    health_port: u16,
    token: &str,
    attempts: u32,
    poll_secs: u64,
) -> Result<HealthRecord> {
    let mut last_error = None;
    for _ in 0..attempts {
        match fetch_device_health(device_serial, health_port, token).await {
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
            Err(error) => last_error = Some(format!("{error:#}")),
        }
        sleep(Duration::from_secs(poll_secs.max(1))).await;
    }
    bail!(
        "device health did not become healthy: {}",
        last_error.unwrap_or_else(|| "unknown error".into())
    )
}

async fn fetch_device_health(
    device_serial: Option<&str>,
    health_port: u16,
    token: &str,
) -> Result<HealthRecord> {
    adb(
        device_serial,
        &["forward", &format!("tcp:{health_port}"), "tcp:8088"],
    )?;
    if detect_adb()?
        .extension()
        .is_some_and(|extension| extension == "exe")
    {
        return fetch_windows_forwarded_health(health_port, token);
    }
    let client = reqwest::Client::builder()
        .timeout(Duration::from_secs(15))
        .build()
        .context("failed to build local health client")?;
    client
        .get(format!("http://127.0.0.1:{health_port}/v1/health"))
        .bearer_auth(token)
        .send()
        .await
        .context("failed to query forwarded device health")?
        .error_for_status()
        .context("forwarded device health returned an error")?
        .json::<HealthRecord>()
        .await
        .context("failed to parse health payload")
}

fn fetch_windows_forwarded_health(health_port: u16, token: &str) -> Result<HealthRecord> {
    let powershell =
        if Path::new("/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe").is_file() {
            PathBuf::from("/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe")
        } else {
            PathBuf::from("powershell.exe")
        };
    let script = format!(
        r#"$token=[Console]::In.ReadToEnd(); $headers=@{{Authorization=("Bearer " + $token)}}; try {{ $response=Invoke-WebRequest -UseBasicParsing -Headers $headers -TimeoutSec 15 -Uri "http://127.0.0.1:{health_port}/v1/health"; [Console]::Out.Write($response.Content) }} catch {{ [Console]::Error.Write($_.Exception.Message); exit 1 }}"#
    );
    let mut child = Command::new(&powershell)
        .args(["-NoProfile", "-NonInteractive", "-Command", &script])
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .with_context(|| {
            format!(
                "failed to start Windows PowerShell at {}",
                powershell.display()
            )
        })?;
    child
        .stdin
        .as_mut()
        .context("failed to open Windows health client stdin")?
        .write_all(token.as_bytes())
        .context("failed to send health token to Windows client")?;
    let output = child
        .wait_with_output()
        .context("failed to wait for Windows health client")?;
    if output.status.success() {
        serde_json::from_slice(&output.stdout)
            .context("failed to parse Windows-forwarded health payload")
    } else {
        bail!(
            "Windows-forwarded device health request failed: {}",
            String::from_utf8_lossy(&output.stderr).trim()
        )
    }
}

pub(crate) fn assert_healthy(health: &HealthRecord) -> Result<()> {
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

pub(crate) fn assert_tunnel_owner(health: &HealthRecord, required: &str) -> Result<()> {
    if health.tunnel_owner.as_deref() == Some(required) {
        Ok(())
    } else {
        bail!(
            "device tunnel owner mismatch: expected={} actual={:?}",
            required,
            health.tunnel_owner
        )
    }
}

pub(crate) fn assert_active_vpn_owner(
    device_serial: Option<&str>,
    required_tunnel_owner: &str,
) -> Result<()> {
    let connectivity_dump = adb(device_serial, &["shell", "dumpsys", "connectivity"])?;
    let active_vpn_owner_uid = parse_active_vpn_owner_uid(&connectivity_dump);
    match required_tunnel_owner {
        PRIMARY_TUNNEL_OWNER => {
            if let Some(actual_owner_uid) = active_vpn_owner_uid {
                bail!(
                    "native reverse tunnel requires no active Android VPN, but owner uid {} is active",
                    actual_owner_uid
                )
            }
        }
        STOCK_WIREGUARD_OWNER => {
            let expected_uid = package_uid(device_serial, STOCK_WIREGUARD_PACKAGE)?;
            let actual_uid =
                active_vpn_owner_uid.context("active Android VPN owner uid was not found")?;
            if actual_uid != expected_uid {
                bail!(
                    "active Android VPN owner mismatch: expected_package={} expected_uid={} actual_owner_uid={}",
                    STOCK_WIREGUARD_PACKAGE,
                    expected_uid,
                    actual_uid
                )
            }
        }
        APP_OWNED_TUNNEL_OWNER => {
            let expected_uid = package_uid(device_serial, APP_OWNED_TUNNEL_PACKAGE)?;
            let actual_uid =
                active_vpn_owner_uid.context("active Android VPN owner uid was not found")?;
            if actual_uid != expected_uid {
                bail!(
                    "active Android VPN owner mismatch: expected_package={} expected_uid={} actual_owner_uid={}",
                    APP_OWNED_TUNNEL_PACKAGE,
                    expected_uid,
                    actual_uid
                )
            }
        }
        other => bail!("unsupported required tunnel owner {other}"),
    }
    Ok(())
}

fn package_uid(device_serial: Option<&str>, package_name: &str) -> Result<u32> {
    let output = adb(
        device_serial,
        &[
            "shell",
            "cmd",
            "package",
            "list",
            "packages",
            "-U",
            package_name,
        ],
    )?;
    parse_package_uid(&output, package_name)
        .with_context(|| format!("package uid for {} was not found", package_name))
}

fn parse_package_uid(output: &str, package_name: &str) -> Option<u32> {
    output.lines().find_map(|line| {
        if !line.contains(&format!("package:{package_name}")) {
            return None;
        }
        line.split_whitespace()
            .find_map(|part| part.strip_prefix("uid:")?.parse().ok())
    })
}

fn parse_active_vpn_owner_uid(connectivity_dump: &str) -> Option<u32> {
    connectivity_dump.lines().find_map(|line| {
        if !line.contains("Transports:") || !line.contains("VPN") || !line.contains("OwnerUid:") {
            return None;
        }
        line.split("OwnerUid:")
            .nth(1)?
            .split(|character: char| !character.is_ascii_digit())
            .find(|part| !part.is_empty())?
            .parse()
            .ok()
    })
}

pub(crate) async fn proxy_smoke(manifest: &DeviceManifest) -> Result<()> {
    let relay_user = required_env(&manifest.tokens.relay_user_env)?;
    let relay_password = required_env(&manifest.tokens.relay_password_env)?;
    let proxy = Proxy::http(format!(
        "http://{}:{}",
        manifest.relay.host,
        manifest.relay.http_port.unwrap_or(3128)
    ))?
    .basic_auth(&relay_user, &relay_password);
    let client = reqwest::Client::builder()
        .proxy(proxy)
        .timeout(Duration::from_secs(15))
        .build()
        .context("failed to build proxy smoke client")?;
    let mut last_error = None;
    for _ in 0..5 {
        match client.get("http://api.ipify.org").send().await {
            Ok(response) => match response.error_for_status() {
                Ok(response) => match response.text().await {
                    Ok(body) if is_ipv4(body.trim()) => return Ok(()),
                    Ok(body) => {
                        let bounded: String = body.chars().take(64).collect();
                        last_error = Some(format!("invalid bounded proxy IP body: {bounded:?}"));
                    }
                    Err(error) => last_error = Some(error.to_string()),
                },
                Err(error) => last_error = Some(error.to_string()),
            },
            Err(error) => last_error = Some(error.to_string()),
        }
        sleep(Duration::from_secs(2)).await;
    }
    bail!(
        "proxy smoke failed after retries: {}",
        last_error.unwrap_or_else(|| "unknown error".into())
    )
}

fn is_ipv4(value: &str) -> bool {
    let mut parts = value.split('.');
    let Some(first) = parts.next() else {
        return false;
    };
    if parse_ipv4_octet(first).is_none() {
        return false;
    }
    let mut count = 1;
    for part in parts {
        count += 1;
        if parse_ipv4_octet(part).is_none() {
            return false;
        }
    }
    count == 4
}

fn parse_ipv4_octet(value: &str) -> Option<u8> {
    if value.is_empty() || (value.len() > 1 && value.starts_with('0')) {
        return None;
    }
    value.parse().ok()
}

fn required_env(name: &str) -> Result<String> {
    let value =
        env::var(name).with_context(|| format!("missing required environment variable: {name}"))?;
    if value.is_empty() || value.len() > 4096 || value.chars().any(char::is_control) {
        bail!("required environment variable {name} is invalid")
    }
    Ok(value)
}

fn repo_root() -> Result<PathBuf> {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../..")
        .canonicalize()
        .context("failed to resolve repo root")
}

fn resolve_repo_path(raw: &str) -> Result<PathBuf> {
    let root = repo_root()?;
    let path = Path::new(raw);
    Ok(if path.is_absolute() {
        path.to_path_buf()
    } else {
        root.join(path)
    })
}

fn detect_adb() -> Result<PathBuf> {
    if let Some(configured) = env::var_os("MOBILE_PROXY_ADB") {
        let configured = PathBuf::from(configured);
        if configured.is_absolute() && !configured.is_file() {
            bail!(
                "MOBILE_PROXY_ADB points to a missing executable: {}",
                configured.display()
            );
        }
        return Ok(configured);
    }

    let user = env::var("USER")
        .or_else(|_| env::var("USERNAME"))
        .unwrap_or_else(|_| "Bose".to_string());
    #[cfg(windows)]
    let candidates = [
        format!("C:\\Users\\{user}\\tools\\platform-tools\\adb.exe"),
        format!("C:\\Users\\{user}\\AppData\\Local\\Android\\Sdk\\platform-tools\\adb.exe"),
        "adb".into(),
    ];
    #[cfg(not(windows))]
    let candidates = if env::var_os("ADB_SERVER_SOCKET").is_some() {
        // In WSL, prefer the Linux client when it is explicitly configured to
        // talk to the Windows ADB server. This avoids relying on WSL interop to
        // spawn adb.exe and keeps all operator commands on one server.
        vec![
            "/usr/bin/adb".into(),
            "adb".into(),
            format!("/mnt/c/Users/{user}/tools/platform-tools/adb.exe"),
            format!("/mnt/c/Users/{user}/AppData/Local/Android/Sdk/platform-tools/adb.exe"),
        ]
    } else {
        vec![
            format!("/mnt/c/Users/{user}/tools/platform-tools/adb.exe"),
            format!("/mnt/c/Users/{user}/AppData/Local/Android/Sdk/platform-tools/adb.exe"),
            "/usr/bin/adb".into(),
            "adb".into(),
        ]
    };
    detect_tool(&candidates, "adb")
}

fn detect_tool(candidates: &[String], tool_name: &str) -> Result<PathBuf> {
    for candidate in candidates {
        let path = Path::new(candidate);
        if path.is_absolute() && path.exists() {
            return Ok(path.to_path_buf());
        }
        if !path.is_absolute() {
            return Ok(path.to_path_buf());
        }
    }
    bail!("failed to locate {tool_name}")
}

#[cfg(test)]
mod tests {
    use super::{
        APP_OWNED_TUNNEL_OWNER, PRIMARY_TUNNEL_OWNER, is_ipv4, parse_active_vpn_owner_uid,
        parse_package_uid, shell_quote_validated, validate_device_path, validate_release_id,
        validate_tunnel_owner,
    };

    #[test]
    fn parsers_and_inputs_fail_closed() {
        let output = "package:com.wireguard.android uid:10209\n";
        assert_eq!(
            parse_package_uid(output, "com.wireguard.android"),
            Some(10209)
        );
        assert_eq!(parse_package_uid(output, "com.example.mobileproxy"), None);
        let dump = "NetworkAgentInfo Transports: CELLULAR|VPN OwnerUid: 10212";
        assert_eq!(parse_active_vpn_owner_uid(dump), Some(10212));
        assert_eq!(
            parse_active_vpn_owner_uid("Transports: CELLULAR OwnerUid: 1000"),
            None
        );
        assert!(validate_tunnel_owner(PRIMARY_TUNNEL_OWNER).is_ok());
        assert!(validate_tunnel_owner(APP_OWNED_TUNNEL_OWNER).is_err());
        assert!(validate_release_id("candidate-1.0").is_ok());
        assert!(validate_release_id("../candidate").is_err());
        assert!(validate_device_path("/data/adb/mobile-proxy-node", "root").is_ok());
        assert!(validate_device_path("/data/../secret", "root").is_err());
        assert_eq!(shell_quote_validated("candidate-1"), "'candidate-1'");
    }

    #[test]
    fn validates_proxy_smoke_ipv4_body() {
        assert!(is_ipv4("178.168.185.116"));
        assert!(!is_ipv4(""));
        assert!(!is_ipv4("178.168.185"));
        assert!(!is_ipv4("178.168.185.999"));
        assert!(!is_ipv4("178.168.185.01"));
        assert!(!is_ipv4("not-an-ip"));
    }
}
