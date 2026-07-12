use std::{env, fs, net::SocketAddr, time::Duration};

use anyhow::{Result, bail};
use proxy_core::{HealthRecord, RuntimeReadiness};
use reverse_tunnel::{ReverseTunnelClientConfig, TunnelTransport, decode_der_base64};
use serde::Deserialize;

use crate::cli::Cli;
use crate::control_plane::ControlPlaneSyncConfig;
use crate::state::{RotationCommands, RuntimeState};

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
}

#[derive(Debug, Deserialize, Clone)]
struct FileWireguardConfig {
    enabled: Option<bool>,
    owner: Option<String>,
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
}

#[derive(Debug, Deserialize, Clone)]
struct FileRotationStrategyConfig {
    command: Option<String>,
}

pub struct LoadedConfig {
    pub listen: String,
    pub admin_token: String,
    pub control_plane_sync: Option<ControlPlaneSyncConfig>,
    pub reverse_tunnel: Option<ReverseTunnelClientConfig>,
    pub runtime_state: RuntimeState,
    pub probe: ProbeConfig,
}

#[derive(Debug, Clone)]
pub struct ProbeConfig {
    pub observer_urls: Vec<String>,
    pub proxy_listen_address: String,
    pub wireguard_enabled: bool,
    pub tunnel_owner: Option<String>,
}

pub fn load_runtime_config(cli: &Cli) -> Result<LoadedConfig> {
    let file_config = load_file_config(cli.config.as_deref())?;
    let listen = cli
        .listen
        .clone()
        .or_else(|| file_config.as_ref().and_then(|c| c.listen.clone()))
        .unwrap_or_else(|| "127.0.0.1:8088".into());
    let admin_token = cli
        .admin_token
        .clone()
        .or_else(|| file_config.as_ref().and_then(|c| c.admin_token.clone()))
        .ok_or_else(|| {
            anyhow::anyhow!("admin_token is required (set it via command line or config file)")
        })?;
    let node_id = file_config
        .as_ref()
        .and_then(|c| c.node_id.clone())
        .or_else(|| env::var("HOST_DAEMON_NODE_ID").ok())
        .unwrap_or_else(|| proxy_core::DEVICE_ID.to_string());
    let node_name = file_config
        .as_ref()
        .and_then(|c| c.node_name.clone())
        .or_else(|| env::var("HOST_DAEMON_NODE_NAME").ok())
        .unwrap_or_else(|| proxy_core::NODE_NAME.to_string());
    let active_profile = file_config
        .as_ref()
        .and_then(|c| c.operator_profiles.as_ref())
        .and_then(|p| p.default_profile.clone())
        .unwrap_or_else(|| "mts_by".into());
    let wireguard_enabled = file_config
        .as_ref()
        .and_then(|c| c.wireguard.as_ref())
        .and_then(|w| w.enabled)
        .unwrap_or(false);
    let tunnel_owner = file_config
        .as_ref()
        .and_then(|c| c.wireguard.as_ref())
        .and_then(|w| w.owner.clone());
    let proxy_listen_address = file_config
        .as_ref()
        .and_then(|c| c.proxy.as_ref())
        .and_then(|p| p.listen_address.clone())
        .unwrap_or_else(|| "10.66.66.2:1080".into());
    let observer_urls = file_config
        .as_ref()
        .and_then(|c| c.observer_urls.clone())
        .unwrap_or_else(|| vec!["https://api.ipify.org?format=json".into()]);
    let rotation_commands = RotationCommands {
        data_reconnect: rotation_command(file_config.as_ref(), |r| r.data_reconnect.as_ref()),
        airplane_bounce: rotation_command(file_config.as_ref(), |r| r.airplane_bounce.as_ref()),
        network_mode_bounce: rotation_command(file_config.as_ref(), |r| {
            r.network_mode_bounce.as_ref()
        }),
        ril_bounce: rotation_command(file_config.as_ref(), |r| r.ril_bounce.as_ref()),
    };
    let control_plane_base_url = file_config
        .as_ref()
        .and_then(|c| c.control_plane.as_ref())
        .and_then(|cp| cp.base_url.clone())
        .or_else(|| env::var("HOST_DAEMON_CONTROL_PLANE_URL").ok());
    let control_plane_sync = control_plane_base_url
        .map(|base_url| -> Result<_> {
            let device_token = file_config
                .as_ref()
                .and_then(|c| c.control_plane.as_ref())
                .and_then(|cp| cp.device_token.clone())
                .or_else(|| env::var("HOST_DAEMON_DEVICE_TOKEN").ok())
                .filter(|token| !token.is_empty())
                .ok_or_else(|| anyhow::anyhow!("control_plane.device_token is required"))?;
            Ok(ControlPlaneSyncConfig {
                base_url,
                device_token,
                server_name: file_config
                    .as_ref()
                    .and_then(|c| c.control_plane.as_ref())
                    .and_then(|cp| cp.server_name.clone()),
                server_addr: file_config
                    .as_ref()
                    .and_then(|c| c.control_plane.as_ref())
                    .and_then(|cp| cp.server_addr),
                server_cert_der: file_config
                    .as_ref()
                    .and_then(|c| c.control_plane.as_ref())
                    .and_then(|cp| cp.server_cert_der_b64.as_deref())
                    .map(decode_der_base64)
                    .transpose()?,
                heartbeat_interval_secs: file_config
                    .as_ref()
                    .and_then(|c| c.control_plane.as_ref())
                    .and_then(|cp| cp.heartbeat_interval_secs)
                    .or_else(|| {
                        env::var("HOST_DAEMON_HEARTBEAT_INTERVAL_SECS")
                            .ok()
                            .and_then(|value| value.parse::<u64>().ok())
                    })
                    .unwrap_or(2),
                poll_interval_secs: file_config
                    .as_ref()
                    .and_then(|c| c.control_plane.as_ref())
                    .and_then(|cp| cp.poll_interval_secs)
                    .or_else(|| {
                        env::var("HOST_DAEMON_COMMAND_POLL_INTERVAL_SECS")
                            .ok()
                            .and_then(|value| value.parse::<u64>().ok())
                    })
                    .unwrap_or(5),
            })
        })
        .transpose()?;
    let reverse_tunnel = reverse_tunnel_config(file_config.as_ref(), &node_id)?;

    let health = HealthRecord {
        node_id,
        node_name,
        binary_fingerprint: env::var("HOST_DAEMON_BINARY_FINGERPRINT")
            .unwrap_or_else(|_| "reconstructed".into()),
        readiness_state: RuntimeReadiness::Booting.to_string(),
        serving: false,
        proxy_status: "starting".into(),
        last_public_ip: None,
        active_operator_profile: Some(active_profile),
        active_operator_plmn: Some("25702".into()),
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
        tunnel_owner: tunnel_owner.clone(),
    };

    Ok(LoadedConfig {
        listen,
        admin_token,
        control_plane_sync,
        reverse_tunnel,
        runtime_state: RuntimeState::new(
            health,
            wireguard_enabled,
            tunnel_owner.clone(),
            proxy_listen_address.clone(),
            rotation_commands,
            observer_urls.clone(),
        ),
        probe: ProbeConfig {
            observer_urls,
            proxy_listen_address,
            wireguard_enabled,
            tunnel_owner,
        },
    })
}

fn reverse_tunnel_config(
    file_config: Option<&FileConfig>,
    node_id: &str,
) -> Result<Option<ReverseTunnelClientConfig>> {
    let Some(config) = file_config.and_then(|c| c.reverse_tunnel.as_ref()) else {
        return Ok(None);
    };
    if !config.enabled.unwrap_or(false) {
        return Ok(None);
    }
    let server_addr: SocketAddr = config
        .server_addr
        .as_deref()
        .unwrap_or("127.0.0.1:18090")
        .parse()?;
    let Some(auth_token) = config.auth_token.clone().filter(|token| !token.is_empty()) else {
        bail!("reverse_tunnel.auth_token is required when reverse_tunnel.enabled=true");
    };
    let local_proxy_addr: SocketAddr = config
        .local_proxy_addr
        .as_deref()
        .unwrap_or("127.0.0.1:1080")
        .parse()?;
    let build_secure_transport = |hybrid: bool| -> Result<TunnelTransport> {
        let server_name = config
            .server_name
            .clone()
            .unwrap_or_else(|| "mobile-proxy-relay".into());
        let server_cert_der =
            decode_der_base64(config.server_cert_der_b64.as_deref().ok_or_else(|| {
                anyhow::anyhow!("reverse_tunnel.server_cert_der_b64 is required")
            })?)?;
        Ok(if hybrid {
            TunnelTransport::Hybrid {
                server_name,
                server_cert_der,
                server_key_der: None,
            }
        } else {
            TunnelTransport::Quic {
                server_name,
                server_cert_der,
                server_key_der: None,
            }
        })
    };
    let transport = match config.transport.as_deref().unwrap_or("hybrid") {
        "tcp" => TunnelTransport::Tcp,
        "quic" => build_secure_transport(false)?,
        "hybrid" => build_secure_transport(true)?,
        other => bail!("unsupported reverse_tunnel.transport: {other}"),
    };
    Ok(Some(ReverseTunnelClientConfig {
        node_id: node_id.to_string(),
        server_addr,
        tcp_fallback_addr: config
            .tcp_fallback_addr
            .as_deref()
            .map(str::parse)
            .transpose()?,
        local_proxy_addr,
        auth_token,
        transport,
        connect_timeout: Duration::from_millis(config.connect_timeout_ms.unwrap_or(2_000)),
        heartbeat_interval: Duration::from_millis(config.heartbeat_interval_ms.unwrap_or(2_000)),
        reconnect_floor: Duration::from_millis(config.reconnect_floor_ms.unwrap_or(1_000)),
        reconnect_ceiling: Duration::from_millis(config.reconnect_ceiling_ms.unwrap_or(30_000)),
    }))
}

fn rotation_command(
    file_config: Option<&FileConfig>,
    selector: impl Fn(&FileRotationConfig) -> Option<&FileRotationStrategyConfig>,
) -> Option<String> {
    file_config
        .and_then(|c| c.rotation.as_ref())
        .and_then(selector)
        .and_then(|s| s.command.clone())
}

fn load_file_config(path: Option<&str>) -> Result<Option<FileConfig>> {
    if let Some(path) = path {
        let body = fs::read_to_string(path)?;
        let config = serde_json::from_str::<FileConfig>(&body)?;
        Ok(Some(config))
    } else {
        Ok(None)
    }
}
