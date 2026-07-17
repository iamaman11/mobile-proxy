use std::fs;
use std::path::PathBuf;

use anyhow::{Context, Result};
use serde::Deserialize;

use crate::cli::Cli;

#[derive(Debug, Deserialize)]
struct RuntimeConfig {
    listen: Option<String>,
    admin_token: String,
    proxy: ProxyConfig,
    wireguard: Option<WireguardConfig>,
}

#[derive(Debug, Deserialize)]
struct ProxyConfig {
    binary: String,
    args: Vec<String>,
    working_dir: Option<String>,
}

#[derive(Debug, Deserialize)]
struct WireguardConfig {
    enabled: Option<bool>,
    owner: Option<String>,
}

#[derive(Debug)]
pub struct SupervisorConfig {
    pub host_config: PathBuf,
    pub host_binary: PathBuf,
    pub host_listen: String,
    pub admin_token: String,
    pub proxy_binary: PathBuf,
    pub proxy_config: PathBuf,
    pub proxy_args: Vec<String>,
    pub proxy_working_dir: PathBuf,
    pub wireguard_enabled: bool,
    pub tunnel_owner: TunnelOwner,
    pub app_tunnel_config: PathBuf,
    pub poll_secs: u64,
    pub repair_cooldown_secs: u64,
    pub data_bounce_down_secs: u64,
    pub data_bounce_settle_secs: u64,
    pub once: bool,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum TunnelOwner {
    StockWireguardBridge,
    FirstPartyVpnService,
    FirstPartyReverseTunnel,
}

impl TunnelOwner {
    pub fn parse(raw: Option<String>) -> Self {
        match raw.as_deref() {
            Some("first_party_vpn_service") => Self::FirstPartyVpnService,
            Some("first_party_reverse_tunnel") => Self::FirstPartyReverseTunnel,
            _ => Self::StockWireguardBridge,
        }
    }

    pub fn as_str(self) -> &'static str {
        match self {
            Self::StockWireguardBridge => "stock_wireguard_bridge",
            Self::FirstPartyVpnService => "first_party_vpn_service",
            Self::FirstPartyReverseTunnel => "first_party_reverse_tunnel",
        }
    }
}

pub fn load_config(cli: Cli) -> Result<SupervisorConfig> {
    let runtime_root = PathBuf::from(cli.runtime_root);
    let host_config = runtime_root.join("config/host-daemon.json");
    let config_body = fs::read_to_string(&host_config)
        .with_context(|| format!("failed to read {}", host_config.display()))?;
    let file: RuntimeConfig = serde_json::from_str(&config_body)
        .with_context(|| format!("failed to parse {}", host_config.display()))?;
    let host_listen = file.listen.unwrap_or_else(|| "127.0.0.1:8088".into());
    let proxy_binary = PathBuf::from(file.proxy.binary);
    let proxy_working_dir = file
        .proxy
        .working_dir
        .map(PathBuf::from)
        .unwrap_or_else(|| runtime_root.clone());
    let proxy_config = proxy_config_path(&runtime_root, &file.proxy.args);

    Ok(SupervisorConfig {
        host_binary: runtime_root.join("bin/host-daemon"),
        host_config,
        host_listen,
        admin_token: file.admin_token,
        proxy_binary,
        proxy_config,
        proxy_args: file.proxy.args,
        proxy_working_dir,
        wireguard_enabled: file
            .wireguard
            .as_ref()
            .and_then(|w| w.enabled)
            .unwrap_or(false),
        tunnel_owner: TunnelOwner::parse(file.wireguard.and_then(|w| w.owner)),
        app_tunnel_config: runtime_root.join("config/app-wireguard.conf"),
        poll_secs: cli.poll_secs,
        repair_cooldown_secs: cli.repair_cooldown_secs,
        data_bounce_down_secs: cli.data_bounce_down_secs,
        data_bounce_settle_secs: cli.data_bounce_settle_secs,
        once: cli.once,
    })
}

fn proxy_config_path(runtime_root: &std::path::Path, args: &[String]) -> PathBuf {
    args.windows(2)
        .find(|parts| parts[0] == "-c" || parts[0] == "--config")
        .map(|parts| PathBuf::from(&parts[1]))
        .unwrap_or_else(|| runtime_root.join("config/sing-box.json"))
}

#[cfg(test)]
mod tests {
    use super::TunnelOwner;

    #[test]
    fn tunnel_owner_defaults_to_explicit_stock_bridge() {
        assert_eq!(TunnelOwner::parse(None), TunnelOwner::StockWireguardBridge);
        assert_eq!(
            TunnelOwner::parse(Some("stock_wireguard_bridge".into())),
            TunnelOwner::StockWireguardBridge
        );
    }

    #[test]
    fn tunnel_owner_accepts_first_party_mode() {
        assert_eq!(
            TunnelOwner::parse(Some("first_party_vpn_service".into())),
            TunnelOwner::FirstPartyVpnService
        );
        assert_eq!(
            TunnelOwner::FirstPartyVpnService.as_str(),
            "first_party_vpn_service"
        );
    }

    #[test]
    fn tunnel_owner_accepts_reverse_tunnel_mode() {
        assert_eq!(
            TunnelOwner::parse(Some("first_party_reverse_tunnel".into())),
            TunnelOwner::FirstPartyReverseTunnel
        );
        assert_eq!(
            TunnelOwner::FirstPartyReverseTunnel.as_str(),
            "first_party_reverse_tunnel"
        );
    }
}
