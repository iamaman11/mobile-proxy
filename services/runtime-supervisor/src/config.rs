use std::fs;
use std::path::PathBuf;

use anyhow::{Context, Result, bail};
use serde::Deserialize;

use crate::cli::Cli;

#[derive(Debug, Deserialize)]
struct RuntimeConfig {
    listen: Option<String>,
    admin_token: String,
    proxy: ProxyConfig,
    wireguard: WireguardConfig,
}

#[derive(Debug, Deserialize)]
struct ProxyConfig {
    binary: String,
    args: Vec<String>,
    working_dir: Option<String>,
}

#[derive(Debug, Deserialize)]
struct WireguardConfig {
    enabled: bool,
    owner: String,
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
    pub poll_secs: u64,
    pub repair_cooldown_secs: u64,
    pub data_bounce_down_secs: u64,
    pub data_bounce_settle_secs: u64,
    pub once: bool,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum TunnelOwner {
    StockWireguardBridge,
    FirstPartyReverseTunnel,
}

impl TunnelOwner {
    pub fn parse(raw: &str) -> Result<Self> {
        match raw {
            "stock_wireguard_bridge" => Ok(Self::StockWireguardBridge),
            "first_party_reverse_tunnel" => Ok(Self::FirstPartyReverseTunnel),
            other => bail!(
                "unsupported tunnel owner {other}; expected stock_wireguard_bridge or first_party_reverse_tunnel"
            ),
        }
    }

    pub fn as_str(self) -> &'static str {
        match self {
            Self::StockWireguardBridge => "stock_wireguard_bridge",
            Self::FirstPartyReverseTunnel => "first_party_reverse_tunnel",
        }
    }

    fn validate_wireguard_flag(self, enabled: bool) -> Result<()> {
        match (self, enabled) {
            (Self::FirstPartyReverseTunnel, false) | (Self::StockWireguardBridge, true) => Ok(()),
            (Self::FirstPartyReverseTunnel, true) => {
                bail!("first_party_reverse_tunnel must not enable WireGuard")
            }
            (Self::StockWireguardBridge, false) => {
                bail!("stock WireGuard rollback owner requires wireguard.enabled=true")
            }
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
    let tunnel_owner = TunnelOwner::parse(&file.wireguard.owner)?;
    tunnel_owner.validate_wireguard_flag(file.wireguard.enabled)?;

    Ok(SupervisorConfig {
        host_binary: runtime_root.join("bin/host-daemon"),
        host_config,
        host_listen,
        admin_token: file.admin_token,
        proxy_binary,
        proxy_config,
        proxy_args: file.proxy.args,
        proxy_working_dir,
        wireguard_enabled: file.wireguard.enabled,
        tunnel_owner,
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
    fn tunnel_owner_is_explicit_and_fail_closed() {
        assert!(TunnelOwner::parse("").is_err());
        assert!(TunnelOwner::parse("unknown").is_err());
        assert!(TunnelOwner::parse("first_party_vpn_service").is_err());
        assert_eq!(
            TunnelOwner::parse("stock_wireguard_bridge").unwrap(),
            TunnelOwner::StockWireguardBridge
        );
        assert_eq!(
            TunnelOwner::parse("first_party_reverse_tunnel").unwrap(),
            TunnelOwner::FirstPartyReverseTunnel
        );
    }

    #[test]
    fn owner_and_wireguard_flag_must_agree() {
        assert!(
            TunnelOwner::FirstPartyReverseTunnel
                .validate_wireguard_flag(false)
                .is_ok()
        );
        assert!(
            TunnelOwner::FirstPartyReverseTunnel
                .validate_wireguard_flag(true)
                .is_err()
        );
        assert!(
            TunnelOwner::StockWireguardBridge
                .validate_wireguard_flag(true)
                .is_ok()
        );
        assert!(
            TunnelOwner::StockWireguardBridge
                .validate_wireguard_flag(false)
                .is_err()
        );
    }
}
