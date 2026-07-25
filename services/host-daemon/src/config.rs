use std::{
    env, fs,
    net::SocketAddr,
    path::{Path, PathBuf},
    time::Duration,
};

use anyhow::{Context, Result, bail};
use proxy_core::{
    BinaryFingerprintInput, ConfigFingerprint, ConfigFingerprintInput, HealthRecord,
    RuntimeReadiness,
};
use reverse_tunnel::{ReverseTunnelClientConfig, TunnelTransport, decode_der_base64};
use serde::Deserialize;

use crate::cli::Cli;
use crate::control_plane::ControlPlaneSyncConfig;
use crate::fingerprints::{config_source_fingerprint, current_binary_fingerprint};
use crate::state::{RotationCommands, RuntimeState};

const PRIMARY_OWNER: &str = "first_party_reverse_tunnel";
const ROLLBACK_OWNER: &str = "stock_wireguard_bridge";
const APP_OWNED_OWNER: &str = "first_party_vpn_service";
const MAX_SECRET_LENGTH: usize = 4096;
const MAX_URLS: usize = 8;

#[derive(Debug, Deserialize, Clone)]
pub struct FileConfig {
    node_id: Option<String>,
    node_name: Option<String>,
    listen: Option<String>,
    admin_token: Option<String>,
    observer_urls: Option<Vec<String>>,
    operator_profiles: Option<FileOperatorProfiles>,
    proxy: Option<FileProxyConfig>,
    wireguard: Option<FileWireguardConfig>,
    reverse_tunnel: Option<FileReverseTunnelConfig>,
    control_plane: Option<FileControlPlaneConfig>,
    rotation: Option<FileRotationConfig>,
}

#[derive(Debug, Deserialize, Clone)]
struct FileOperatorProfiles {
    default_profile: Option<String>,
}

#[derive(Debug, Deserialize, Clone)]
struct FileProxyConfig {
    listen_address: Option<String>,
    username: Option<String>,
    password: Option<String>,
    #[allow(dead_code)]
    binary: Option<String>,
    #[allow(dead_code)]
    args: Option<Vec<String>>,
    #[allow(dead_code)]
    working_dir: Option<String>,
    #[allow(dead_code)]
    env: Option<serde_json::Value>,
}

#[derive(Debug, Deserialize, Clone)]
struct FileWireguardConfig {
    enabled: Option<bool>,
    owner: Option<String>,
    #[allow(dead_code)]
    up_command: Option<String>,
    #[allow(dead_code)]
    down_command: Option<String>,
}

#[derive(Debug, Deserialize, Clone)]
struct FileReverseTunnelConfig {
    enabled: Option<bool>,
    transport: Option<String>,
    server_addr: Option<String>,
    tcp_fallback_addr: Option<String>,
    local_proxy_addr: Option<String>,
    server_name: Option<String>,
    server_cert_der_b64: Option<String>,
    auth_token: Option<String>,
    connect_timeout_ms: Option<u64>,
    heartbeat_interval_ms: Option<u64>,
    reconnect_floor_ms: Option<u64>,
    reconnect_ceiling_ms: Option<u64>,
    counter_state_path: Option<String>,
}

#[derive(Debug, Deserialize, Clone)]
struct FileControlPlaneConfig {
    base_url: Option<String>,
    device_token: Option<String>,
    server_name: Option<String>,
    server_addr: Option<SocketAddr>,
    server_cert_der_b64: Option<String>,
    heartbeat_interval_secs: Option<u64>,
    poll_interval_secs: Option<u64>,
}

#[derive(Debug, Deserialize, Clone)]
struct FileRotationConfig {
    data_reconnect: Option<FileRotationStrategyConfig>,
    airplane_bounce: Option<FileRotationStrategyConfig>,
    network_mode_bounce: Option<FileRotationStrategyConfig>,
    ril_bounce: Option<FileRotationStrategyConfig>,
    #[allow(dead_code)]
    drain_delay_secs: Option<u64>,
}

#[derive(Debug, Deserialize, Clone)]
struct FileRotationStrategyConfig {
    command: Option<String>,
    #[allow(dead_code)]
    enabled: Option<bool>,
}

pub struct LoadedConfig {
    pub listen: String,
    pub admin_token: String,
    pub control_plane_sync: Option<ControlPlaneSyncConfig>,
    pub reverse_tunnel: Option<ReverseTunnelClientConfig>,
    pub reverse_tunnel_counter_state_path: Option<PathBuf>,
    pub runtime_state: RuntimeState,
    pub probe: ProbeConfig,
}

#[derive(Debug, Clone)]
pub struct ProbeConfig {
    pub observer_urls: Vec<String>,
    pub proxy_listen_address: String,
    pub proxy_username: String,
    pub proxy_password: String,
    pub wireguard_enabled: bool,
    pub tunnel_owner: Option<String>,
}

pub fn load_runtime_config(cli: &Cli) -> Result<LoadedConfig> {
    let (file_config, config_fingerprint) = load_file_config(cli.config.as_deref())?;
    let file_config = file_config.context("host-daemon requires an explicit configuration file")?;

    let listen = cli
        .listen
        .clone()
        .or_else(|| file_config.listen.clone())
        .unwrap_or_else(|| "127.0.0.1:8088".into());
    let listen_addr: SocketAddr = listen
        .parse()
        .context("host-daemon listen address is invalid")?;
    if !listen_addr.ip().is_loopback() {
        bail!("host-daemon API must bind to a loopback address")
    }

    let admin_token = cli
        .admin_token
        .clone()
        .or_else(|| file_config.admin_token.clone())
        .context("admin_token is required")?;
    validate_secret("admin_token", &admin_token)?;

    let node_id = file_config
        .node_id
        .clone()
        .or_else(|| env::var("HOST_DAEMON_NODE_ID").ok())
        .unwrap_or_else(|| proxy_core::DEVICE_ID.to_string());
    validate_identifier("node_id", &node_id, 64)?;
    let node_name = file_config
        .node_name
        .clone()
        .or_else(|| env::var("HOST_DAEMON_NODE_NAME").ok())
        .unwrap_or_else(|| proxy_core::NODE_NAME.to_string());
    validate_identifier("node_name", &node_name, 128)?;

    let active_profile = file_config
        .operator_profiles
        .as_ref()
        .and_then(|profiles| profiles.default_profile.clone())
        .unwrap_or_else(|| "default".into());
    validate_identifier("operator profile", &active_profile, 64)?;

    let wireguard = file_config
        .wireguard
        .as_ref()
        .context("wireguard owner configuration is required")?;
    let wireguard_enabled = wireguard.enabled.context("wireguard.enabled is required")?;
    let tunnel_owner = wireguard
        .owner
        .clone()
        .context("wireguard.owner is required")?;
    validate_owner_flags(&tunnel_owner, wireguard_enabled)?;

    let proxy = file_config
        .proxy
        .as_ref()
        .context("proxy configuration is required")?;
    let proxy_listen_address = proxy
        .listen_address
        .clone()
        .context("proxy.listen_address is required")?;
    let proxy_addr: SocketAddr = proxy_listen_address
        .parse()
        .context("proxy.listen_address is invalid")?;
    if tunnel_owner == PRIMARY_OWNER && !proxy_addr.ip().is_loopback() {
        bail!("native reverse-tunnel proxy must bind to loopback")
    }
    let proxy_username = proxy
        .username
        .clone()
        .context("proxy.username is required")?;
    let proxy_password = proxy
        .password
        .clone()
        .context("proxy.password is required")?;
    validate_secret("proxy.username", &proxy_username)?;
    validate_secret("proxy.password", &proxy_password)?;

    let observer_urls = file_config
        .observer_urls
        .clone()
        .unwrap_or_else(|| vec!["https://api.ipify.org?format=json".into()]);
    validate_observer_urls(&observer_urls)?;

    let rotation_commands = RotationCommands {
        data_reconnect: rotation_command(&file_config, |rotation| {
            rotation.data_reconnect.as_ref()
        })?,
        airplane_bounce: rotation_command(&file_config, |rotation| {
            rotation.airplane_bounce.as_ref()
        })?,
        network_mode_bounce: rotation_command(&file_config, |rotation| {
            rotation.network_mode_bounce.as_ref()
        })?,
        ril_bounce: rotation_command(&file_config, |rotation| rotation.ril_bounce.as_ref())?,
    };

    let control_plane_sync = control_plane_config(&file_config)?;
    let reverse_tunnel = reverse_tunnel_config(&file_config, &node_id, &tunnel_owner)?;
    let reverse_tunnel_counter_state_path = reverse_tunnel.as_ref().map(|_| {
        file_config
            .reverse_tunnel
            .as_ref()
            .and_then(|config| config.counter_state_path.clone())
            .or_else(|| env::var("HOST_DAEMON_REVERSE_TUNNEL_COUNTER_STATE_PATH").ok())
            .map(PathBuf::from)
            .unwrap_or_else(|| PathBuf::from("state/reverse-tunnel-counters-v1.json"))
    });
    if let Some(path) = reverse_tunnel_counter_state_path.as_ref() {
        validate_state_path(path)?;
    }

    let health = HealthRecord {
        node_id,
        node_name,
        config_fingerprint: config_fingerprint.map(ConfigFingerprintInput::current),
        binary_fingerprint: BinaryFingerprintInput::current(current_binary_fingerprint()?),
        readiness_state: RuntimeReadiness::Booting.to_string(),
        serving: false,
        proxy_status: "starting".into(),
        last_public_ip: None,
        active_operator_profile: Some(active_profile),
        active_operator_plmn: None,
        last_proxy_error: None,
        serving_failure_reason: None,
        degradation_reason_code: None,
        cellular_route_ready: None,
        proxy_bind_ready: None,
        local_serving_ready: None,
        tun0_present: None,
        wg_handshake_recent: None,
        reverse_tunnel_connected: None,
        reverse_tunnel_last_error: None,
        reverse_tunnel_active_transport: None,
        reverse_tunnel_freshness: None,
        reverse_tunnel_failover_reason: None,
        tunnel_owner: Some(tunnel_owner.clone()),
    };

    Ok(LoadedConfig {
        listen,
        admin_token,
        control_plane_sync,
        reverse_tunnel,
        reverse_tunnel_counter_state_path,
        runtime_state: RuntimeState::new(
            health,
            wireguard_enabled,
            Some(tunnel_owner.clone()),
            proxy_listen_address.clone(),
            rotation_commands,
            observer_urls.clone(),
        ),
        probe: ProbeConfig {
            observer_urls,
            proxy_listen_address,
            proxy_username,
            proxy_password,
            wireguard_enabled,
            tunnel_owner: Some(tunnel_owner),
        },
    })
}

fn control_plane_config(file_config: &FileConfig) -> Result<Option<ControlPlaneSyncConfig>> {
    let Some(config) = file_config.control_plane.as_ref() else {
        return Ok(None);
    };
    let base_url = config
        .base_url
        .clone()
        .or_else(|| env::var("HOST_DAEMON_CONTROL_PLANE_URL").ok())
        .context("control_plane.base_url is required")?;
    let parsed = reqwest::Url::parse(&base_url).context("control_plane.base_url is invalid")?;
    if parsed.scheme() != "https" || parsed.host_str().is_none() {
        bail!("control_plane.base_url must be an absolute HTTPS URL")
    }
    let device_token = config
        .device_token
        .clone()
        .or_else(|| env::var("HOST_DAEMON_DEVICE_TOKEN").ok())
        .context("control_plane.device_token is required")?;
    validate_secret("control_plane.device_token", &device_token)?;
    let server_name = config
        .server_name
        .clone()
        .context("control_plane.server_name is required")?;
    validate_identifier("control_plane.server_name", &server_name, 253)?;
    let server_addr = config
        .server_addr
        .context("control_plane.server_addr is required")?;
    let server_cert_der = decode_der_base64(
        config
            .server_cert_der_b64
            .as_deref()
            .context("control_plane.server_cert_der_b64 is required")?,
    )?;
    let heartbeat_interval_secs = bounded_interval(
        "control_plane.heartbeat_interval_secs",
        config.heartbeat_interval_secs.unwrap_or(2),
        1,
        300,
    )?;
    let poll_interval_secs = bounded_interval(
        "control_plane.poll_interval_secs",
        config.poll_interval_secs.unwrap_or(5),
        1,
        300,
    )?;
    Ok(Some(ControlPlaneSyncConfig {
        base_url,
        device_token,
        server_name: Some(server_name),
        server_addr: Some(server_addr),
        server_cert_der: Some(server_cert_der),
        heartbeat_interval_secs,
        poll_interval_secs,
    }))
}

fn reverse_tunnel_config(
    file_config: &FileConfig,
    node_id: &str,
    tunnel_owner: &str,
) -> Result<Option<ReverseTunnelClientConfig>> {
    let config = file_config.reverse_tunnel.as_ref();
    if matches!(tunnel_owner, ROLLBACK_OWNER | APP_OWNED_OWNER) {
        if config.is_some_and(|value| value.enabled.unwrap_or(false)) {
            bail!("WireGuard tunnel owners must not enable the reverse tunnel")
        }
        return Ok(None);
    }
    let config = config.context("native owner requires reverse_tunnel configuration")?;
    if config.enabled != Some(true) {
        bail!("native owner requires reverse_tunnel.enabled=true")
    }
    if config.transport.as_deref().unwrap_or("hybrid") != "hybrid" {
        bail!("production reverse tunnel transport must be hybrid; plaintext tcp is forbidden")
    }
    let server_addr: SocketAddr = config
        .server_addr
        .as_deref()
        .context("reverse_tunnel.server_addr is required")?
        .parse()
        .context("reverse_tunnel.server_addr is invalid")?;
    let tcp_fallback_addr: SocketAddr = config
        .tcp_fallback_addr
        .as_deref()
        .context("reverse_tunnel.tcp_fallback_addr is required")?
        .parse()
        .context("reverse_tunnel.tcp_fallback_addr is invalid")?;
    let local_proxy_addr: SocketAddr = config
        .local_proxy_addr
        .as_deref()
        .context("reverse_tunnel.local_proxy_addr is required")?
        .parse()
        .context("reverse_tunnel.local_proxy_addr is invalid")?;
    if !local_proxy_addr.ip().is_loopback() {
        bail!("reverse_tunnel.local_proxy_addr must be loopback")
    }
    let auth_token = config
        .auth_token
        .clone()
        .context("reverse_tunnel.auth_token is required")?;
    validate_secret("reverse_tunnel.auth_token", &auth_token)?;
    let server_name = config
        .server_name
        .clone()
        .context("reverse_tunnel.server_name is required")?;
    validate_identifier("reverse_tunnel.server_name", &server_name, 253)?;
    let server_cert_der = decode_der_base64(
        config
            .server_cert_der_b64
            .as_deref()
            .context("reverse_tunnel.server_cert_der_b64 is required")?,
    )?;

    let connect_timeout_ms = bounded_interval(
        "reverse_tunnel.connect_timeout_ms",
        config.connect_timeout_ms.unwrap_or(2_000),
        100,
        60_000,
    )?;
    let heartbeat_interval_ms = bounded_interval(
        "reverse_tunnel.heartbeat_interval_ms",
        config.heartbeat_interval_ms.unwrap_or(2_000),
        100,
        60_000,
    )?;
    let reconnect_floor_ms = bounded_interval(
        "reverse_tunnel.reconnect_floor_ms",
        config.reconnect_floor_ms.unwrap_or(1_000),
        100,
        60_000,
    )?;
    let reconnect_ceiling_ms = bounded_interval(
        "reverse_tunnel.reconnect_ceiling_ms",
        config.reconnect_ceiling_ms.unwrap_or(30_000),
        reconnect_floor_ms,
        300_000,
    )?;

    Ok(Some(ReverseTunnelClientConfig {
        node_id: node_id.to_string(),
        server_addr,
        tcp_fallback_addr: Some(tcp_fallback_addr),
        local_proxy_addr,
        auth_token,
        transport: TunnelTransport::Hybrid {
            server_name,
            server_cert_der,
            server_key_der: None,
        },
        connect_timeout: Duration::from_millis(connect_timeout_ms),
        heartbeat_interval: Duration::from_millis(heartbeat_interval_ms),
        reconnect_floor: Duration::from_millis(reconnect_floor_ms),
        reconnect_ceiling: Duration::from_millis(reconnect_ceiling_ms),
    }))
}

fn rotation_command(
    file_config: &FileConfig,
    selector: impl Fn(&FileRotationConfig) -> Option<&FileRotationStrategyConfig>,
) -> Result<Option<String>> {
    let command = file_config
        .rotation
        .as_ref()
        .and_then(selector)
        .and_then(|strategy| strategy.command.clone());
    if let Some(value) = command.as_deref() {
        validate_bounded_text("rotation command", value, 2_048)?;
    }
    Ok(command)
}

fn load_file_config(path: Option<&str>) -> Result<(Option<FileConfig>, Option<ConfigFingerprint>)> {
    let Some(path) = path else {
        return Ok((None, None));
    };
    let body = fs::read(path)?;
    if body.is_empty() || body.len() > 1_048_576 {
        bail!("host-daemon configuration size is invalid")
    }
    let fingerprint = config_source_fingerprint(&body)?;
    let config = serde_json::from_slice::<FileConfig>(&body)?;
    Ok((Some(config), Some(fingerprint)))
}

fn validate_owner_flags(owner: &str, wireguard_enabled: bool) -> Result<()> {
    match (owner, wireguard_enabled) {
        (PRIMARY_OWNER, false) | (ROLLBACK_OWNER, true) | (APP_OWNED_OWNER, true) => Ok(()),
        (PRIMARY_OWNER, true) => bail!("native reverse-tunnel owner must disable WireGuard"),
        (ROLLBACK_OWNER, false) => bail!("stock rollback owner must enable WireGuard"),
        (APP_OWNED_OWNER, false) => bail!("first-party VPN owner must enable WireGuard"),
        _ => bail!("unsupported tunnel owner"),
    }
}

fn validate_observer_urls(urls: &[String]) -> Result<()> {
    if urls.is_empty() || urls.len() > MAX_URLS {
        bail!("observer URL inventory is invalid")
    }
    for raw in urls {
        let url = reqwest::Url::parse(raw).context("observer URL is invalid")?;
        if url.scheme() != "https"
            || url.host_str().is_none()
            || url.username() != ""
            || url.password().is_some()
        {
            bail!("observer URLs must be credential-free absolute HTTPS URLs")
        }
    }
    Ok(())
}

fn validate_secret(field: &str, value: &str) -> Result<()> {
    if value.len() < 16 || value.len() > MAX_SECRET_LENGTH || value.chars().any(char::is_control) {
        bail!("{field} is invalid")
    }
    Ok(())
}

fn validate_identifier(field: &str, value: &str, maximum: usize) -> Result<()> {
    if value.is_empty()
        || value.len() > maximum
        || !value.chars().all(|character| {
            character.is_ascii_alphanumeric() || matches!(character, '-' | '_' | '.' | ':')
        })
    {
        bail!("{field} is invalid")
    }
    Ok(())
}

fn validate_bounded_text(field: &str, value: &str, maximum: usize) -> Result<()> {
    if value.is_empty() || value.len() > maximum || value.chars().any(char::is_control) {
        bail!("{field} is invalid")
    }
    Ok(())
}

fn bounded_interval(field: &str, value: u64, minimum: u64, maximum: u64) -> Result<u64> {
    if !(minimum..=maximum).contains(&value) {
        bail!("{field} is outside the supported range")
    }
    Ok(value)
}

fn validate_state_path(path: &Path) -> Result<()> {
    if path.as_os_str().is_empty()
        || path.components().any(|component| {
            matches!(
                component,
                std::path::Component::ParentDir | std::path::Component::Prefix(_)
            )
        })
    {
        bail!("reverse-tunnel counter state path is invalid")
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use std::fs;

    use uuid::Uuid;

    use super::load_runtime_config;
    use crate::cli::Cli;

    fn valid_config() -> String {
        serde_json::json!({
            "admin_token": "admin-token-0000000000000000000000000001",
            "node_id": "device-1",
            "node_name": "phone-1",
            "observer_urls": ["https://api.ipify.org?format=json"],
            "operator_profiles": {"default_profile": "default"},
            "proxy": {
                "listen_address": "127.0.0.1:1080",
                "username": "proxy-user-0000000000000000000000000001",
                "password": "proxy-pass-0000000000000000000000000001"
            },
            "wireguard": {"enabled": false, "owner": "first_party_reverse_tunnel"},
            "reverse_tunnel": {
                "enabled": true,
                "transport": "hybrid",
                "server_addr": "127.0.0.1:18090",
                "tcp_fallback_addr": "127.0.0.1:443",
                "local_proxy_addr": "127.0.0.1:1080",
                "server_name": "mobile-proxy-relay",
                "server_cert_der_b64": "MAA=",
                "auth_token": "reverse-token-00000000000000000000000001",
                "connect_timeout_ms": 2000,
                "heartbeat_interval_ms": 2000,
                "reconnect_floor_ms": 1000,
                "reconnect_ceiling_ms": 30000
            }
        })
        .to_string()
    }

    #[test]
    fn runtime_config_produces_typed_source_and_binary_fingerprints() {
        let root = std::env::temp_dir().join(format!(
            "mobile-proxy-host-config-fingerprint-{}",
            Uuid::new_v4()
        ));
        fs::create_dir_all(&root).unwrap();
        let path = root.join("host-daemon.json");
        fs::write(&path, valid_config()).unwrap();
        let loaded = load_runtime_config(&Cli {
            listen: None,
            admin_token: None,
            config: Some(path.to_string_lossy().into_owned()),
        })
        .unwrap();
        assert!(loaded.runtime_state.health.config_fingerprint.is_some());
        assert_eq!(
            loaded.runtime_state.health.tunnel_owner.as_deref(),
            Some("first_party_reverse_tunnel")
        );
        assert!(loaded.reverse_tunnel.is_some());
        assert!(
            loaded
                .runtime_state
                .health
                .binary_fingerprint
                .current_value()
                .unwrap()
                .to_string()
                .starts_with("b3:")
        );
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn plaintext_unknown_and_owner_mismatch_fail_closed() {
        let root = std::env::temp_dir().join(format!(
            "mobile-proxy-host-config-fail-closed-{}",
            Uuid::new_v4()
        ));
        fs::create_dir_all(&root).unwrap();
        let path = root.join("host-daemon.json");
        let cli = |path: &std::path::Path| Cli {
            listen: None,
            admin_token: None,
            config: Some(path.to_string_lossy().into_owned()),
        };

        let mut value: serde_json::Value = serde_json::from_str(&valid_config()).unwrap();
        value["reverse_tunnel"]["transport"] = "tcp".into();
        fs::write(&path, value.to_string()).unwrap();
        assert!(load_runtime_config(&cli(&path)).is_err());

        let mut value: serde_json::Value = serde_json::from_str(&valid_config()).unwrap();
        value["wireguard"]["owner"] = "unknown".into();
        fs::write(&path, value.to_string()).unwrap();
        assert!(load_runtime_config(&cli(&path)).is_err());

        let mut value: serde_json::Value = serde_json::from_str(&valid_config()).unwrap();
        value["wireguard"]["enabled"] = true.into();
        fs::write(&path, value.to_string()).unwrap();
        assert!(load_runtime_config(&cli(&path)).is_err());

        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn shared_runtime_template_fields_are_tolerated() {
        let root = std::env::temp_dir().join(format!(
            "mobile-proxy-host-config-shared-{}",
            Uuid::new_v4()
        ));
        fs::create_dir_all(&root).unwrap();
        let path = root.join("host-daemon.json");
        let mut value: serde_json::Value = serde_json::from_str(&valid_config()).unwrap();
        value["proxy"]["binary"] = "/data/adb/mobile-proxy-node/current/bin/sing-box".into();
        value["proxy"]["args"] = serde_json::json!([
            "run",
            "-c",
            "/data/adb/mobile-proxy-node/current/config/sing-box.json"
        ]);
        value["proxy"]["working_dir"] = "/data/adb/mobile-proxy-node/current".into();
        value["proxy"]["env"] = serde_json::json!({});
        value["wireguard"]["up_command"] = "true".into();
        value["wireguard"]["down_command"] = "true".into();
        value["rotation"]["drain_delay_secs"] = 2.into();
        value["rotation"]["data_reconnect"]["enabled"] = true.into();
        value["network"] = serde_json::json!({
            "cellular_only": true
        });
        value["reliability"] = serde_json::json!({
            "max_restart_attempts": 5
        });
        value["operator_detection"] = serde_json::json!({
            "command": "getprop gsm.operator.numeric"
        });
        value["operator_profiles"]["profiles"] = serde_json::json!({
            "default": {
                "preferred_rotation_strategy": "data_reconnect"
            }
        });
        fs::write(&path, value.to_string()).unwrap();

        assert!(
            load_runtime_config(&Cli {
                listen: None,
                admin_token: None,
                config: Some(path.to_string_lossy().into_owned()),
            })
            .is_ok()
        );

        let _ = fs::remove_dir_all(root);
    }
}
