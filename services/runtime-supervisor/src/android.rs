use std::fs;
use std::path::Path;
use std::process::Command;
use std::time::Duration;

use anyhow::{Context, Result, bail};
use tokio::time::sleep;

const STOCK_WIREGUARD_PACKAGE: &str = "com.wireguard.android";
const STOCK_WIREGUARD_TUNNEL: &str = "WiGandroid";
const APP_OWNED_PACKAGE: &str = "com.example.mobileproxy";

pub async fn kick_stock_wireguard_bridge() {
    let _ = run_shell("settings put secure always_on_vpn_app com.wireguard.android");
    let _ = run_shell("settings put secure always_on_vpn_lockdown 0");
    let _ = stop_stock_wireguard_tunnel();
    sleep(Duration::from_secs(1)).await;
    let _ = run_shell("monkey -p com.wireguard.android -c android.intent.category.LAUNCHER 1");
    let _ = start_stock_wireguard_tunnel();
}

pub async fn kick_first_party_vpn_service(config_path: &Path) -> Result<()> {
    stop_stock_wireguard_tunnel().ok();
    stop_first_party_vpn_service().ok();
    push_first_party_tunnel_config(config_path)?;
    sleep(Duration::from_secs(1)).await;
    let Some(uid) = package_uid(APP_OWNED_PACKAGE)? else {
        bail!("first-party VPN package is not installed")
    };
    run_as_uid(
        uid,
        "am broadcast --user 0 -n com.example.mobileproxy/.TunnelCommandReceiver -a com.example.mobileproxy.action.START_TUNNEL",
    )?;
    Ok(())
}

pub fn push_local_ui_control_token(token: Option<&str>) -> Result<()> {
    let Some(token) = token else {
        return Ok(());
    };
    if token.is_empty()
        || token.len() > 256
        || !token
            .chars()
            .all(|value| value.is_ascii_alphanumeric() || value == '-')
    {
        bail!("local UI control token is invalid")
    }
    let Some(uid) = package_uid(APP_OWNED_PACKAGE)? else {
        return Ok(());
    };
    run_as_uid(
        uid,
        &format!(
            "am broadcast --user 0 -n com.example.mobileproxy/.TunnelCommandReceiver -a com.example.mobileproxy.action.SET_LOCAL_CONTROL_TOKEN --es control_token {}",
            shell_single_quote(token)
        ),
    )?;
    Ok(())
}

pub fn stop_compatibility_vpns() -> Result<()> {
    let mut failures = Vec::new();
    if let Err(error) = stop_stock_wireguard_tunnel() {
        failures.push(format!("compatibility VPN cleanup failed: {error:#}"));
    }
    if let Err(error) = stop_first_party_vpn_service() {
        failures.push(format!("compatibility VPN cleanup failed: {error:#}"));
    }
    for command in [
        "settings delete secure always_on_vpn_app",
        "settings put secure always_on_vpn_lockdown 0",
    ] {
        if let Err(error) = run_shell(command) {
            failures.push(format!("compatibility VPN cleanup failed: {error:#}"));
        }
    }
    if failures.is_empty() {
        Ok(())
    } else {
        bail!("failed to stop compatibility VPNs: {}", failures.join("; "))
    }
}

pub fn ensure_cellular_default_route() -> Result<()> {
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

pub fn bootstrap_cellular_data() -> Result<()> {
    let mut failures = Vec::new();
    for command in [
        "svc wifi disable",
        "settings put global mobile_data 1",
        "svc data enable",
    ] {
        if let Err(error) = run_shell(command) {
            failures.push(format!("cellular bootstrap command failed: {error:#}"));
        }
    }

    if failures.is_empty() {
        Ok(())
    } else {
        bail!("cellular bootstrap failed: {}", failures.join("; "))
    }
}

pub fn tun0_ready() -> bool {
    run_ip(&["-4", "addr", "show", "tun0"])
        .map(|output| output.contains("inet "))
        .unwrap_or(false)
}

pub async fn bounce_mobile_data(down_secs: u64, settle_secs: u64) -> Result<()> {
    run_shell("svc data disable").context("failed to disable mobile data")?;
    sleep(Duration::from_secs(down_secs.max(1))).await;
    run_shell("svc data enable").context("failed to enable mobile data")?;
    sleep(Duration::from_secs(settle_secs.max(1))).await;
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
    for index in 0..parts.len().saturating_sub(1) {
        match parts[index] {
            "dev" => dev = Some(parts[index + 1].to_string()),
            "via" => via = Some(parts[index + 1].to_string()),
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

fn run_ip(args: &[&str]) -> Result<String> {
    run_command("ip", args)
}

fn run_as_uid(uid: u32, command: &str) -> Result<String> {
    run_command("su", &[&uid.to_string(), "sh", "-c", command])
}

fn run_shell(command: &str) -> Result<String> {
    run_command("sh", &["-c", command])
}

fn run_command(binary: &str, args: &[&str]) -> Result<String> {
    let output = Command::new(binary)
        .args(args)
        .output()
        .with_context(|| format!("failed to start {binary}"))?;
    if output.status.success() {
        Ok(String::from_utf8_lossy(&output.stdout).trim().to_string())
    } else {
        bail!(
            "{binary} command failed: {}",
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

fn stop_stock_wireguard_tunnel() -> Result<()> {
    let Some(uid) = package_uid(STOCK_WIREGUARD_PACKAGE)? else {
        return Ok(());
    };
    let command = format!(
        "am broadcast --user 0 -n com.wireguard.android/.model.TunnelManager\\$IntentReceiver -a com.wireguard.android.action.SET_TUNNEL_DOWN -e tunnel {STOCK_WIREGUARD_TUNNEL}"
    );
    run_as_uid(uid, &command)?;
    Ok(())
}

fn start_stock_wireguard_tunnel() -> Result<()> {
    let Some(uid) = package_uid(STOCK_WIREGUARD_PACKAGE)? else {
        bail!("stock WireGuard package is not installed")
    };
    let command = format!(
        "am broadcast --user 0 -n com.wireguard.android/.model.TunnelManager\\$IntentReceiver -a com.wireguard.android.action.SET_TUNNEL_UP -e tunnel {STOCK_WIREGUARD_TUNNEL}"
    );
    run_as_uid(uid, &command)?;
    Ok(())
}

fn stop_first_party_vpn_service() -> Result<()> {
    let Some(uid) = package_uid(APP_OWNED_PACKAGE)? else {
        return Ok(());
    };
    run_as_uid(
        uid,
        "am broadcast --user 0 -n com.example.mobileproxy/.TunnelCommandReceiver -a com.example.mobileproxy.action.STOP_TUNNEL",
    )?;
    Ok(())
}

fn push_first_party_tunnel_config(config_path: &Path) -> Result<()> {
    let config = fs::read_to_string(config_path)
        .with_context(|| format!("failed to read {}", config_path.display()))?;
    if config.is_empty() || config.len() > 16 * 1024 {
        bail!("first-party tunnel config size is invalid")
    }
    let Some(uid) = package_uid(APP_OWNED_PACKAGE)? else {
        bail!("first-party VPN package is not installed")
    };
    run_as_uid(
        uid,
        &format!(
            "am broadcast --user 0 -n com.example.mobileproxy/.TunnelCommandReceiver -a com.example.mobileproxy.action.SET_TUNNEL_CONFIG --es config {}",
            shell_single_quote(&config)
        ),
    )?;
    Ok(())
}

fn package_uid(package_name: &str) -> Result<Option<u32>> {
    let output = run_command("cmd", &["package", "list", "packages", "-U", package_name])?;
    Ok(parse_package_uid(&output, package_name))
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

fn shell_single_quote(value: &str) -> String {
    format!("'{}'", value.replace('\'', r"'\''"))
}

#[cfg(test)]
mod tests {
    use super::{is_cellular_dev, parse_package_uid, parse_route_line, shell_single_quote};

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

    #[test]
    fn package_uid_parser_is_generic() {
        let output = "package:com.example.mobileproxy uid:10209\n";
        assert_eq!(
            parse_package_uid(output, "com.example.mobileproxy"),
            Some(10209)
        );
        assert_eq!(parse_package_uid(output, "com.wireguard.android"), None);
    }

    #[test]
    fn shell_quote_handles_single_quotes() {
        assert_eq!(shell_single_quote("a'b"), "'a'\\''b'");
    }
}
