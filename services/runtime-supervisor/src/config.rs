use std::fs;
use std::path::PathBuf;

use anyhow::{Context, Result, bail};
use serde::Deserialize;

use crate::cli::Cli;

#[derive(Debug, Deserialize)]
struct RuntimeConfig {
    listen: Option<String>,
    admin_token: String,
    #[serde(default)]
    ui_control_token: Option<String>,
    proxy: ProxyConfig,
    #[serde(default)]
    app_egress: Option<FileAppEgressConfig>,
    wireguard: WireguardConfig,
}

#[derive(Debug, Deserialize)]
struct ProxyConfig {
    #[serde(default)]
    binary: Option<String>,
    #[serde(default)]
    args: Vec<String>,
    working_dir: Option<String>,
    username: Option<String>,
    password: Option<String>,
}

#[derive(Debug, Deserialize)]
struct FileAppEgressConfig {
    port: u16,
}

#[derive(Debug)]
pub struct AppEgressConfig {
    pub port: u16,
    pub username: String,
    pub password: String,
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
    pub ui_control_token: Option<String>,
    pub proxy_binary: PathBuf,
    pub proxy_config: PathBuf,
    pub proxy_args: Vec<String>,
    pub proxy_working_dir: PathBuf,
    pub wireguard_enabled: bool,
    pub tunnel_owner: TunnelOwner,
    pub app_tunnel_config: Option<PathBuf>,
    pub app_egress: Option<AppEgressConfig>,
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
    FirstPartyAndroidEgress,
}

impl TunnelOwner {
    pub fn parse(raw: &str) -> Result<Self> {
        match raw {
            "stock_wireguard_bridge" => Ok(Self::StockWireguardBridge),
            "first_party_vpn_service" => Ok(Self::FirstPartyVpnService),
            "first_party_reverse_tunnel" => Ok(Self::FirstPartyReverseTunnel),
            "first_party_android_egress" => Ok(Self::FirstPartyAndroidEgress),
            other => bail!(
                "unsupported tunnel owner {other}; expected stock_wireguard_bridge, first_party_vpn_service, first_party_reverse_tunnel, or first_party_android_egress"
            ),
        }
    }

    pub fn as_str(self) -> &'static str {
        match self {
            Self::StockWireguardBridge => "stock_wireguard_bridge",
            Self::FirstPartyVpnService => "first_party_vpn_service",
            Self::FirstPartyReverseTunnel => "first_party_reverse_tunnel",
            Self::FirstPartyAndroidEgress => "first_party_android_egress",
        }
    }

    fn validate_wireguard_flag(self, enabled: bool) -> Result<()> {
        match (self, enabled) {
            (Self::FirstPartyReverseTunnel, false)
            | (Self::FirstPartyAndroidEgress, false)
            | (Self::StockWireguardBridge, true)
            | (Self::FirstPartyVpnService, true) => Ok(()),
            (Self::FirstPartyReverseTunnel, true) => {
                bail!("first_party_reverse_tunnel must not enable WireGuard")
            }
            (Self::FirstPartyAndroidEgress, true) => {
                bail!("first_party_android_egress must not enable WireGuard")
            }
            (Self::StockWireguardBridge, false) => {
                bail!("stock WireGuard rollback owner requires wireguard.enabled=true")
            }
            (Self::FirstPartyVpnService, false) => {
                bail!("first_party_vpn_service requires wireguard.enabled=true")
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
    let proxy_binary = file
        .proxy
        .binary
        .map(PathBuf::from)
        .unwrap_or_else(|| runtime_root.join("bin/sing-box"));
    let proxy_working_dir = file
        .proxy
        .working_dir
        .map(PathBuf::from)
        .unwrap_or_else(|| runtime_root.clone());
    let mut proxy_args = default_proxy_args(&runtime_root, file.proxy.args);
    let proxy_source_config = proxy_config_path(&runtime_root, &proxy_args);
    let proxy_config = mutable_proxy_config_path(&runtime_root);
    let tunnel_owner = TunnelOwner::parse(&file.wireguard.owner)?;
    tunnel_owner.validate_wireguard_flag(file.wireguard.enabled)?;
    if tunnel_owner == TunnelOwner::FirstPartyVpnService {
        bail!(
            "first_party_vpn_service is disabled after physical validation on July 26, 2026: Android VpnService did not expose a routable 10.66.66.2 listener for the rooted proxy runtime"
        )
    }
    prepare_mutable_proxy_config(&proxy_source_config, &proxy_config)?;
    replace_proxy_config_arg(&mut proxy_args, &proxy_config);
    let app_egress = if tunnel_owner == TunnelOwner::FirstPartyAndroidEgress {
        let app = file
            .app_egress
            .context("first_party_android_egress requires app_egress")?;
        if !(1024..=65535).contains(&app.port) {
            bail!("app_egress.port must be unprivileged")
        }
        let username = file
            .proxy
            .username
            .as_deref()
            .context("app_egress requires proxy.username")?;
        let password = file
            .proxy
            .password
            .as_deref()
            .context("app_egress requires proxy.password")?;
        if username.is_empty() || username.len() > 256 || password.len() < 16 {
            bail!("app_egress proxy credentials are invalid")
        }
        Some(AppEgressConfig {
            port: app.port,
            username: username.to_string(),
            password: password.to_string(),
        })
    } else {
        None
    };
    let app_tunnel_config = if tunnel_owner == TunnelOwner::FirstPartyVpnService {
        let path = runtime_root.join("config/app-wireguard.conf");
        if !path.is_file() {
            bail!("missing first-party VPN tunnel config: {}", path.display())
        }
        Some(path)
    } else {
        None
    };

    Ok(SupervisorConfig {
        host_binary: runtime_root.join("bin/host-daemon"),
        host_config,
        host_listen,
        admin_token: file.admin_token,
        ui_control_token: file.ui_control_token,
        proxy_binary,
        proxy_config,
        proxy_args,
        proxy_working_dir,
        wireguard_enabled: file.wireguard.enabled,
        tunnel_owner,
        app_tunnel_config,
        app_egress,
        poll_secs: cli.poll_secs,
        repair_cooldown_secs: cli.repair_cooldown_secs,
        data_bounce_down_secs: cli.data_bounce_down_secs,
        data_bounce_settle_secs: cli.data_bounce_settle_secs,
        once: cli.once,
    })
}

fn default_proxy_args(runtime_root: &std::path::Path, args: Vec<String>) -> Vec<String> {
    if !args.is_empty() {
        return args;
    }
    vec![
        "run".into(),
        "-c".into(),
        runtime_root
            .join("config/sing-box.json")
            .to_string_lossy()
            .into_owned(),
    ]
}

fn proxy_config_path(runtime_root: &std::path::Path, args: &[String]) -> PathBuf {
    args.windows(2)
        .find(|parts| parts[0] == "-c" || parts[0] == "--config")
        .map(|parts| PathBuf::from(&parts[1]))
        .unwrap_or_else(|| runtime_root.join("config/sing-box.json"))
}

fn mutable_proxy_config_path(runtime_root: &std::path::Path) -> PathBuf {
    if runtime_root
        .file_name()
        .is_some_and(|name| name == "current")
    {
        return runtime_root
            .parent()
            .unwrap_or(runtime_root)
            .join("state/sing-box.json");
    }
    runtime_root.join("state/sing-box.json")
}

fn prepare_mutable_proxy_config(source: &std::path::Path, target: &std::path::Path) -> Result<()> {
    let parent = target
        .parent()
        .context("mutable proxy config has no parent directory")?;
    fs::create_dir_all(parent).with_context(|| format!("failed to create {}", parent.display()))?;
    fs::copy(source, target).with_context(|| {
        format!(
            "failed to initialize mutable proxy config {} from {}",
            target.display(),
            source.display()
        )
    })?;
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        fs::set_permissions(target, fs::Permissions::from_mode(0o600))?;
    }
    Ok(())
}

fn replace_proxy_config_arg(args: &mut [String], config: &std::path::Path) {
    if let Some(index) = args
        .windows(2)
        .position(|parts| parts[0] == "-c" || parts[0] == "--config")
    {
        args[index + 1] = config.to_string_lossy().into_owned();
    }
}

#[cfg(test)]
mod tests {
    use std::fs;

    use super::{TunnelOwner, load_config, mutable_proxy_config_path};
    use crate::cli::Cli;

    #[test]
    fn tunnel_owner_is_explicit_and_fail_closed() {
        assert!(TunnelOwner::parse("").is_err());
        assert!(TunnelOwner::parse("unknown").is_err());
        assert_eq!(
            TunnelOwner::parse("first_party_vpn_service").unwrap(),
            TunnelOwner::FirstPartyVpnService
        );
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
    fn production_current_release_uses_sibling_mutable_state() {
        assert_eq!(
            mutable_proxy_config_path(std::path::Path::new("/data/adb/mobile-proxy-node/current")),
            std::path::Path::new("/data/adb/mobile-proxy-node/state/sing-box.json")
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
            TunnelOwner::FirstPartyVpnService
                .validate_wireguard_flag(true)
                .is_ok()
        );
        assert!(
            TunnelOwner::StockWireguardBridge
                .validate_wireguard_flag(false)
                .is_err()
        );
        assert!(
            TunnelOwner::FirstPartyVpnService
                .validate_wireguard_flag(false)
                .is_err()
        );
    }

    #[test]
    fn supervisor_rejects_disabled_app_owned_owner() {
        let unique = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let root = std::env::temp_dir().join(format!(
            "mobile-proxy-runtime-supervisor-app-owned-{unique}"
        ));
        fs::create_dir_all(root.join("config")).unwrap();
        fs::write(
            root.join("config/host-daemon.json"),
            serde_json::json!({
                "listen": "127.0.0.1:8088",
                "admin_token": "admin-token-0000000000000000000000000001",
                "proxy": {
                    "listen_address": "10.66.66.2:1080",
                    "username": "proxy-user-0000000000000000000000000001",
                    "password": "proxy-pass-0000000000000000000000000001"
                },
                "wireguard": {
                    "enabled": true,
                    "owner": "first_party_vpn_service"
                }
            })
            .to_string(),
        )
        .unwrap();

        let error = load_config(Cli {
            runtime_root: root.to_string_lossy().into_owned(),
            poll_secs: 1,
            repair_cooldown_secs: 15,
            data_bounce_down_secs: 2,
            data_bounce_settle_secs: 8,
            once: false,
        })
        .unwrap_err()
        .to_string();
        assert!(error.contains("first_party_vpn_service is disabled"));

        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn supervisor_defaults_proxy_launcher_from_runtime_root() {
        let unique = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let root =
            std::env::temp_dir().join(format!("mobile-proxy-runtime-supervisor-config-{unique}"));
        fs::create_dir_all(root.join("config")).unwrap();
        fs::write(
            root.join("config/host-daemon.json"),
            serde_json::json!({
                "listen": "127.0.0.1:8088",
                "admin_token": "admin-token-0000000000000000000000000001",
                "proxy": {
                    "listen_address": "127.0.0.1:1080",
                    "username": "proxy-user-0000000000000000000000000001",
                    "password": "proxy-pass-0000000000000000000000000001"
                },
                "wireguard": {
                    "enabled": false,
                    "owner": "first_party_reverse_tunnel"
                }
            })
            .to_string(),
        )
        .unwrap();
        fs::write(root.join("config/sing-box.json"), "{}").unwrap();

        let loaded = load_config(Cli {
            runtime_root: root.to_string_lossy().into_owned(),
            poll_secs: 1,
            repair_cooldown_secs: 15,
            data_bounce_down_secs: 2,
            data_bounce_settle_secs: 8,
            once: false,
        })
        .unwrap();

        assert_eq!(loaded.proxy_binary, root.join("bin/sing-box"));
        assert_eq!(
            loaded.proxy_args,
            vec![
                "run".to_string(),
                "-c".to_string(),
                root.join("state/sing-box.json")
                    .to_string_lossy()
                    .into_owned(),
            ]
        );
        assert_eq!(loaded.proxy_config, root.join("state/sing-box.json"));
        assert_eq!(
            fs::read(root.join("state/sing-box.json")).unwrap(),
            fs::read(root.join("config/sing-box.json")).unwrap()
        );

        let _ = fs::remove_dir_all(root);
    }
}
