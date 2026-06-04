use std::fs;
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::time::{Duration, Instant};

use anyhow::{Context, Result, bail};
use clap::Parser;
use proxy_core::HealthRecord;
use serde::Deserialize;
use tokio::time::sleep;
use tracing::{info, warn};

#[derive(Parser, Debug)]
#[command(name = "runtime-supervisor")]
#[command(about = "Phone-side owner for host-daemon, sing-box, and runtime recovery")]
struct Cli {
    #[arg(long, default_value = "/data/adb/mobile-proxy-node/current")]
    runtime_root: String,
    #[arg(long, default_value_t = 1)]
    poll_secs: u64,
    #[arg(long, default_value_t = 15)]
    repair_cooldown_secs: u64,
    #[arg(long, default_value_t = 2)]
    data_bounce_down_secs: u64,
    #[arg(long, default_value_t = 8)]
    data_bounce_settle_secs: u64,
    #[arg(long, default_value_t = false)]
    once: bool,
}

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
struct SupervisorConfig {
    host_config: PathBuf,
    host_binary: PathBuf,
    host_listen: String,
    admin_token: String,
    proxy_binary: PathBuf,
    proxy_args: Vec<String>,
    proxy_working_dir: PathBuf,
    wireguard_enabled: bool,
    poll_secs: u64,
    repair_cooldown_secs: u64,
    data_bounce_down_secs: u64,
    data_bounce_settle_secs: u64,
    once: bool,
}

struct RuntimeChildren {
    host_daemon: Option<Child>,
    proxy: Option<Child>,
}

#[derive(Debug)]
struct SupervisorState {
    last_route_repair: Option<Instant>,
}

#[tokio::main]
async fn main() -> Result<()> {
    tracing_subscriber::fmt::init();
    let cli = Cli::parse();
    let config = load_config(cli)?;
    let client = reqwest::Client::builder()
        .timeout(Duration::from_secs(5))
        .build()
        .context("failed to build HTTP client")?;
    let mut children = RuntimeChildren {
        host_daemon: None,
        proxy: None,
    };
    let mut state = SupervisorState {
        last_route_repair: None,
    };

    loop {
        ensure_processes(&config, &mut children)?;
        reconcile_wireguard(&config);

        match fetch_health(&client, &config).await {
            Ok(health) => reconcile_health(&config, &mut state, &health)?,
            Err(err) => warn!("host-daemon health unavailable: {err:#}"),
        }

        if config.once {
            break;
        }
        sleep(Duration::from_secs(config.poll_secs.max(1))).await;
    }

    Ok(())
}

fn load_config(cli: Cli) -> Result<SupervisorConfig> {
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

fn ensure_processes(config: &SupervisorConfig, children: &mut RuntimeChildren) -> Result<()> {
    if child_exited(&mut children.proxy)? {
        warn!("proxy process exited; restarting");
        children.proxy = None;
    }
    if child_exited(&mut children.host_daemon)? {
        warn!("host-daemon process exited; restarting");
        children.host_daemon = None;
    }

    if children.proxy.is_none() {
        children.proxy = Some(spawn_proxy(config)?);
    }
    if children.host_daemon.is_none() {
        children.host_daemon = Some(spawn_host_daemon(config)?);
    }
    Ok(())
}

fn child_exited(child: &mut Option<Child>) -> Result<bool> {
    let Some(child) = child else {
        return Ok(false);
    };
    Ok(child.try_wait()?.is_some())
}

fn spawn_host_daemon(config: &SupervisorConfig) -> Result<Child> {
    ensure_executable(&config.host_binary)?;
    let child = Command::new(&config.host_binary)
        .arg("--config")
        .arg(&config.host_config)
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn()
        .with_context(|| format!("failed to spawn {}", config.host_binary.display()))?;
    info!("host-daemon spawned pid={}", child.id());
    Ok(child)
}

fn spawn_proxy(config: &SupervisorConfig) -> Result<Child> {
    ensure_executable(&config.proxy_binary)?;
    let child = Command::new(&config.proxy_binary)
        .args(&config.proxy_args)
        .current_dir(&config.proxy_working_dir)
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn()
        .with_context(|| format!("failed to spawn {}", config.proxy_binary.display()))?;
    info!("proxy spawned pid={}", child.id());
    Ok(child)
}

async fn fetch_health(client: &reqwest::Client, config: &SupervisorConfig) -> Result<HealthRecord> {
    Ok(client
        .get(format!("http://{}/v1/health", config.host_listen))
        .bearer_auth(&config.admin_token)
        .send()
        .await?
        .error_for_status()?
        .json()
        .await?)
}

fn reconcile_health(
    config: &SupervisorConfig,
    state: &mut SupervisorState,
    health: &HealthRecord,
) -> Result<()> {
    if config.wireguard_enabled && health.wg_handshake_recent == Some(false) {
        warn!("WireGuard gateway is unreachable; attempting app/broadcast kick");
        kick_wireguard();
    }

    if health.cellular_route_ready != Some(false) {
        return Ok(());
    }
    if !route_repair_allowed(config, state) {
        return Ok(());
    }

    state.last_route_repair = Some(Instant::now());
    info!(
        "route recovery triggered readiness={} serving={} reason={:?}",
        health.readiness_state, health.serving, health.degradation_reason_code
    );

    if let Err(err) = ensure_cellular_default_route() {
        warn!("direct route repair failed: {err:#}; bouncing mobile data");
        bounce_mobile_data(config)?;
    }

    Ok(())
}

fn route_repair_allowed(config: &SupervisorConfig, state: &SupervisorState) -> bool {
    state.last_route_repair.is_none_or(|last| {
        last.elapsed() >= Duration::from_secs(config.repair_cooldown_secs.max(1))
    })
}

fn reconcile_wireguard(config: &SupervisorConfig) {
    if !config.wireguard_enabled {
        return;
    }
    if tun0_ready() {
        return;
    }

    warn!("wireguard enabled but tun0 is absent; attempting app/broadcast kick");
    kick_wireguard();
}

fn kick_wireguard() {
    let _ = run_shell("settings put secure always_on_vpn_app com.wireguard.android");
    let _ = run_shell("settings put secure always_on_vpn_lockdown 0");
    let _ = run_shell(
        "am broadcast --user 0 --receiver-foreground -a com.wireguard.android.action.SET_TUNNEL_DOWN --es tunnel WiGandroid",
    );
    let _ = run_shell("sleep 1");
    let _ = run_shell("monkey -p com.wireguard.android -c android.intent.category.LAUNCHER 1");
    let _ = run_shell(
        "am broadcast --user 0 --receiver-foreground -a com.wireguard.android.action.SET_TUNNEL_UP --es tunnel WiGandroid",
    );
}

fn ensure_cellular_default_route() -> Result<()> {
    let (dev, via) = cellular_route_hint()?.context("no cellular route hint found")?;
    if main_default_route_for(&dev) {
        return Ok(());
    }

    let mut args = vec!["route", "replace", "default"];
    if let Some(via) = via.as_deref() {
        args.extend(["via", via]);
    }
    args.extend(["dev", dev.as_str(), "table", "main"]);
    run_ip(&args).context("failed to replace main default route")?;
    Ok(())
}

fn cellular_route_hint() -> Result<Option<(String, Option<String>)>> {
    let primary = run_ip(&["-4", "route", "get", "1.1.1.1"]).unwrap_or_default();
    if let Some(hint) = parse_route_line(&primary) {
        return Ok(Some(hint));
    }

    let all_routes = run_ip(&["-4", "route", "show", "table", "all"])?;
    for line in all_routes.lines() {
        if !line.starts_with("default ") {
            continue;
        }
        if let Some(hint) = parse_route_line(line) {
            return Ok(Some(hint));
        }
    }
    Ok(None)
}

fn parse_route_line(line: &str) -> Option<(String, Option<String>)> {
    let mut dev = None;
    let mut via = None;
    let parts: Vec<_> = line.split_whitespace().collect();
    for idx in 0..parts.len().saturating_sub(1) {
        match parts[idx] {
            "dev" => dev = Some(parts[idx + 1].to_string()),
            "via" => via = Some(parts[idx + 1].to_string()),
            _ => {}
        }
    }

    let dev = dev?;
    if !is_cellular_dev(&dev) {
        return None;
    }
    Some((dev, via))
}

fn main_default_route_for(dev: &str) -> bool {
    let output = run_ip(&["route", "show", "default"]).unwrap_or_default();
    output
        .lines()
        .any(|line| line.starts_with("default ") && line.contains(&format!(" dev {dev}")))
}

fn tun0_ready() -> bool {
    run_ip(&["-4", "addr", "show", "tun0"])
        .map(|output| output.contains("inet "))
        .unwrap_or(false)
}

fn bounce_mobile_data(config: &SupervisorConfig) -> Result<()> {
    run_shell("svc data disable").context("failed to disable mobile data")?;
    std::thread::sleep(Duration::from_secs(config.data_bounce_down_secs.max(1)));
    run_shell("svc data enable").context("failed to enable mobile data")?;
    std::thread::sleep(Duration::from_secs(config.data_bounce_settle_secs.max(1)));
    Ok(())
}

fn ensure_executable(path: &Path) -> Result<()> {
    if path.is_file() {
        Ok(())
    } else {
        bail!("missing runtime binary: {}", path.display())
    }
}

fn run_ip(args: &[&str]) -> Result<String> {
    run_command("ip", args)
}

fn run_shell(command: &str) -> Result<String> {
    run_command("sh", &["-c", command])
}

fn run_command(binary: &str, args: &[&str]) -> Result<String> {
    let output = Command::new(binary)
        .args(args)
        .output()
        .with_context(|| format!("failed to start {} {:?}", binary, args))?;
    if output.status.success() {
        Ok(String::from_utf8_lossy(&output.stdout).trim().to_string())
    } else {
        bail!(
            "{} {:?} failed: {}",
            binary,
            args,
            String::from_utf8_lossy(&output.stderr).trim()
        )
    }
}

fn is_cellular_dev(dev: &str) -> bool {
    dev.starts_with("rmnet")
        || dev.starts_with("ccmni")
        || dev.starts_with("pdp")
        || dev.starts_with("wwan")
}

#[cfg(test)]
mod tests {
    use super::{is_cellular_dev, parse_route_line};

    #[test]
    fn extracts_cellular_route_hint() {
        let parsed = parse_route_line("default via 10.159.140.1 dev rmnet4 table 1006")
            .expect("expected cellular route");
        assert_eq!(parsed.0, "rmnet4");
        assert_eq!(parsed.1.as_deref(), Some("10.159.140.1"));
    }

    #[test]
    fn ignores_non_cellular_default_routes() {
        assert!(parse_route_line("default via 192.168.1.1 dev wlan0").is_none());
        assert!(is_cellular_dev("rmnet4"));
        assert!(is_cellular_dev("wwan0"));
        assert!(!is_cellular_dev("wlan0"));
    }
}
