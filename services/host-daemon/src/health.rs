use std::net::{SocketAddr, TcpStream};
use std::process::Command;
use std::time::Duration;

use proxy_core::RuntimeReadiness;
use serde::Deserialize;
use tokio::time::{MissedTickBehavior, interval};
use tracing::warn;

use crate::config::ProbeConfig;
use crate::state::SharedRuntime;

#[derive(Debug, Deserialize)]
struct IpifyResponse {
    ip: Option<String>,
}

pub async fn run_health_probe(runtime_arc: SharedRuntime, config: ProbeConfig) {
    let client = match reqwest::Client::builder()
        .timeout(Duration::from_secs(5))
        .build()
    {
        Ok(client) => client,
        Err(err) => {
            warn!("health probe disabled: failed to create client: {err}");
            return;
        }
    };
    let mut tick = interval(Duration::from_secs(2));
    tick.set_missed_tick_behavior(MissedTickBehavior::Delay);

    loop {
        tick.tick().await;
        let snapshot = probe_once(&client, &config).await;
        let public_probe_ready = snapshot.public_ip.is_some();
        let mut runtime = runtime_arc.lock().await;
        runtime.health.cellular_route_ready = Some(snapshot.cellular_route_ready);
        runtime.health.proxy_bind_ready = Some(snapshot.proxy_bind_ready);
        runtime.health.local_serving_ready = Some(snapshot.local_serving_ready);
        runtime.health.tun0_present = Some(snapshot.tun0_present);
        runtime.health.wg_handshake_recent = Some(snapshot.wg_gateway_reachable);
        if let Some(ip) = snapshot.public_ip {
            runtime.health.last_public_ip = Some(ip);
        }
        let reverse_tunnel_required =
            config.tunnel_owner.as_deref() == Some("first_party_reverse_tunnel");
        let reverse_tunnel_ready = !reverse_tunnel_required
            || runtime
                .reverse_tunnel
                .as_ref()
                .is_some_and(|snapshot| snapshot.connected);
        runtime.health.reverse_tunnel_connected = runtime
            .reverse_tunnel
            .as_ref()
            .map(|snapshot| snapshot.connected);
        runtime.health.reverse_tunnel_last_error = runtime
            .reverse_tunnel
            .as_ref()
            .and_then(|snapshot| snapshot.last_error.clone());

        let healthy = snapshot.cellular_route_ready
            && snapshot.proxy_bind_ready
            && snapshot.local_serving_ready
            && snapshot.wireguard_path_ready
            && reverse_tunnel_ready
            && public_probe_ready
            && runtime.current_job.is_none();
        runtime.health.readiness_state = if healthy {
            RuntimeReadiness::Healthy.to_string()
        } else if config.wireguard_enabled && !snapshot.wireguard_path_ready {
            RuntimeReadiness::WaitingWireguard.to_string()
        } else if reverse_tunnel_required && !reverse_tunnel_ready {
            RuntimeReadiness::StartingProxy.to_string()
        } else if !snapshot.cellular_route_ready {
            RuntimeReadiness::WaitingCellular.to_string()
        } else {
            RuntimeReadiness::StartingProxy.to_string()
        };
        runtime.health.serving = healthy;
        runtime.health.proxy_status = if healthy {
            "running".into()
        } else {
            "degraded".into()
        };
        runtime.health.degradation_reason_code = if healthy {
            None
        } else if config.wireguard_enabled && !snapshot.wireguard_path_ready {
            Some("wireguard_path_not_ready".into())
        } else if reverse_tunnel_required && !reverse_tunnel_ready {
            Some("reverse_tunnel_not_ready".into())
        } else if !snapshot.cellular_route_ready {
            Some("cellular_route_missing".into())
        } else if !snapshot.proxy_bind_ready {
            Some("proxy_bind_failed".into())
        } else if !public_probe_ready {
            Some("public_probe_failed".into())
        } else {
            Some("local_probe_failed".into())
        };
        runtime.health.serving_failure_reason = runtime
            .health
            .degradation_reason_code
            .as_ref()
            .map(|code| match code.as_str() {
                "cellular_route_missing" => "cellular route is not ready".into(),
                "proxy_bind_failed" => "proxy is not accepting local connections".into(),
                "wireguard_path_not_ready" => "WireGuard path is not ready".into(),
                "reverse_tunnel_not_ready" => "reverse tunnel is not connected".into(),
                "public_probe_failed" => "public IP observer probe failed".into(),
                _ => "local serving probe failed".into(),
            });
    }
}

#[derive(Debug)]
struct ProbeSnapshot {
    cellular_route_ready: bool,
    proxy_bind_ready: bool,
    local_serving_ready: bool,
    tun0_present: bool,
    wg_gateway_reachable: bool,
    wireguard_path_ready: bool,
    public_ip: Option<String>,
}

async fn probe_once(client: &reqwest::Client, config: &ProbeConfig) -> ProbeSnapshot {
    let proxy_bind_ready = tcp_ready(&config.proxy_listen_address);
    let tun0_present = tun0_present();
    let wg_gateway_reachable = tun0_present && wg_gateway_reachable();
    let wireguard_path_ready = !config.wireguard_enabled || (tun0_present && wg_gateway_reachable);
    let public_ip = fetch_public_ip(client, &config.observer_urls).await;
    ProbeSnapshot {
        cellular_route_ready: cellular_route_ready(),
        proxy_bind_ready,
        local_serving_ready: proxy_bind_ready && wireguard_path_ready,
        tun0_present,
        wg_gateway_reachable,
        wireguard_path_ready,
        public_ip,
    }
}

fn cellular_route_ready() -> bool {
    let routes = run_command("ip", &["-4", "route", "show", "table", "all"]).unwrap_or_default();
    routes.lines().any(|line| {
        line.starts_with("default ") && line.contains(" dev ") && is_cellular_route(line)
    })
}

fn is_cellular_route(line: &str) -> bool {
    [" rmnet", " ccmni", " pdp", " wwan"]
        .iter()
        .any(|prefix| line.contains(&format!(" dev{prefix}")))
}

fn tun0_present() -> bool {
    run_command("ip", &["-4", "addr", "show", "tun0"])
        .map(|output| output.contains("inet "))
        .unwrap_or(false)
}

fn wg_gateway_reachable() -> bool {
    Command::new("ping")
        .args(["-c", "1", "-W", "1", "10.66.66.1"])
        .stdout(std::process::Stdio::null())
        .stderr(std::process::Stdio::null())
        .status()
        .map(|status| status.success())
        .unwrap_or(false)
}

fn tcp_ready(raw: &str) -> bool {
    let Ok(addr) = raw.parse::<SocketAddr>() else {
        return false;
    };
    TcpStream::connect_timeout(&addr, Duration::from_secs(1)).is_ok()
}

async fn fetch_public_ip(client: &reqwest::Client, urls: &[String]) -> Option<String> {
    for url in urls {
        let Ok(response) = client.get(url).send().await else {
            continue;
        };
        let Ok(response) = response.error_for_status() else {
            continue;
        };
        let Ok(body) = response.text().await else {
            continue;
        };
        if let Ok(parsed) = serde_json::from_str::<IpifyResponse>(&body)
            && let Some(ip) = parsed.ip
        {
            return Some(ip);
        }
        let trimmed = body.trim();
        if !trimmed.is_empty() && trimmed.len() <= 64 {
            return Some(trimmed.to_string());
        }
    }
    None
}

fn run_command(binary: &str, args: &[&str]) -> Option<String> {
    let output = Command::new(binary).args(args).output().ok()?;
    if output.status.success() {
        Some(String::from_utf8_lossy(&output.stdout).to_string())
    } else {
        None
    }
}

#[cfg(test)]
mod tests {
    use super::is_cellular_route;

    #[test]
    fn cellular_route_detection_accepts_policy_tables() {
        assert!(is_cellular_route(
            "default via 10.159.140.1 dev rmnet4 table 1006 proto static"
        ));
        assert!(!is_cellular_route("default via 192.168.1.1 dev wlan0"));
    }
}
