use std::process::Command;
use std::time::Duration;
use std::{fs, path::Path};

use anyhow::{Context, Result, bail};
use base64::Engine;
use tokio::time::sleep;

pub fn kick_first_party_vpn_service(config_path: &Path) -> Result<()> {
    let config = fs::read_to_string(config_path)
        .with_context(|| format!("failed to read {}", config_path.display()))?;
    let encoded = base64::engine::general_purpose::STANDARD.encode(config.as_bytes());
    run_command(
        "am",
        &[
            "broadcast",
            "--user",
            "0",
            "--receiver-foreground",
            "-a",
            "com.example.mobileproxy.action.SET_TUNNEL_CONFIG",
            "-n",
            "com.example.mobileproxy/.TunnelCommandReceiver",
            "--es",
            "config_b64",
            &encoded,
        ],
    )?;
    run_command(
        "am",
        &[
            "broadcast",
            "--user",
            "0",
            "--receiver-foreground",
            "-a",
            "com.example.mobileproxy.action.START_TUNNEL",
            "-n",
            "com.example.mobileproxy/.TunnelCommandReceiver",
        ],
    )?;
    Ok(())
}

pub async fn kick_stock_wireguard_bridge() {
    let _ = run_command(
        "am",
        &[
            "broadcast",
            "--user",
            "0",
            "--receiver-foreground",
            "-a",
            "com.example.mobileproxy.action.START_TUNNEL",
            "-n",
            "com.example.mobileproxy/.TunnelCommandReceiver",
        ],
    );
    sleep(Duration::from_secs(1)).await;
    if tun0_ready() {
        return;
    }

    let _ = run_shell("settings put secure always_on_vpn_app com.wireguard.android");
    let _ = run_shell("settings put secure always_on_vpn_lockdown 0");
    let _ = run_shell(
        "am broadcast --user 0 --receiver-foreground -a com.wireguard.android.action.SET_TUNNEL_DOWN --es tunnel WiGandroid",
    );
    sleep(Duration::from_secs(1)).await;
    let _ = run_shell("monkey -p com.wireguard.android -c android.intent.category.LAUNCHER 1");
    let _ = run_shell(
        "am broadcast --user 0 --receiver-foreground -a com.wireguard.android.action.SET_TUNNEL_UP --es tunnel WiGandroid",
    );
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
        if let Err(err) = run_shell(command) {
            failures.push(format!("{command}: {err:#}"));
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
