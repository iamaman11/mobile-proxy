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
}

#[derive(Debug)]
pub struct SupervisorConfig {
    pub host_config: PathBuf,
    pub host_binary: PathBuf,
    pub host_listen: String,
    pub admin_token: String,
    pub proxy_binary: PathBuf,
    pub proxy_args: Vec<String>,
    pub proxy_working_dir: PathBuf,
    pub wireguard_enabled: bool,
    pub poll_secs: u64,
    pub repair_cooldown_secs: u64,
    pub data_bounce_down_secs: u64,
    pub data_bounce_settle_secs: u64,
    pub once: bool,
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

    Ok(SupervisorConfig {
        host_binary: runtime_root.join("bin/host-daemon"),
        host_config,
        host_listen,
        admin_token: file.admin_token,
        proxy_binary,
        proxy_args: file.proxy.args,
        proxy_working_dir,
        wireguard_enabled: file.wireguard.and_then(|w| w.enabled).unwrap_or(false),
        poll_secs: cli.poll_secs,
        repair_cooldown_secs: cli.repair_cooldown_secs,
        data_bounce_down_secs: cli.data_bounce_down_secs,
        data_bounce_settle_secs: cli.data_bounce_settle_secs,
        once: cli.once,
    })
}
