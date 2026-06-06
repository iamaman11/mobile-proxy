use std::time::{Duration, Instant};

use anyhow::{Context, Result};
use proxy_core::HealthRecord;
use tracing::{info, warn};

use crate::android::{
    bounce_mobile_data, ensure_cellular_default_route, kick_first_party_vpn_service,
    kick_stock_wireguard_bridge, tun0_ready,
};
use crate::config::{SupervisorConfig, TunnelOwner};

#[derive(Debug)]
pub struct SupervisorState {
    last_route_repair: Option<Instant>,
}

impl SupervisorState {
    pub fn new() -> Self {
        Self {
            last_route_repair: None,
        }
    }
}

pub async fn fetch_health(
    client: &reqwest::Client,
    config: &SupervisorConfig,
) -> Result<HealthRecord> {
    Ok(client
        .get(format!("http://{}/v1/health", config.host_listen))
        .bearer_auth(&config.admin_token)
        .send()
        .await?
        .error_for_status()?
        .json()
        .await?)
}

pub fn reconcile_wireguard(config: &SupervisorConfig) {
    if !config.wireguard_enabled {
        return;
    }
    if tun0_ready() {
        return;
    }

    warn!(
        tunnel_owner = config.tunnel_owner.as_str(),
        "wireguard enabled but tun0 is absent; attempting tunnel kick"
    );
    kick_tunnel(config);
}

pub fn reconcile_health(
    config: &SupervisorConfig,
    state: &mut SupervisorState,
    health: &HealthRecord,
) -> Result<()> {
    if config.wireguard_enabled && health.wg_handshake_recent == Some(false) {
        warn!(
            tunnel_owner = config.tunnel_owner.as_str(),
            "WireGuard gateway is unreachable; attempting tunnel kick"
        );
        kick_tunnel(config);
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
        bounce_mobile_data(config.data_bounce_down_secs, config.data_bounce_settle_secs)
            .context("mobile data bounce failed")?;
    }

    Ok(())
}

fn kick_tunnel(config: &SupervisorConfig) {
    match config.tunnel_owner {
        TunnelOwner::FirstPartyVpnService => {
            if let Err(err) = kick_first_party_vpn_service(&config.app_tunnel_config) {
                warn!("first-party VPN kick failed: {err:#}");
            }
        }
        TunnelOwner::FirstPartyReverseTunnel => {}
        TunnelOwner::StockWireguardBridge => kick_stock_wireguard_bridge(),
    }
}

fn route_repair_allowed(config: &SupervisorConfig, state: &SupervisorState) -> bool {
    state.last_route_repair.is_none_or(|last| {
        last.elapsed() >= Duration::from_secs(config.repair_cooldown_secs.max(1))
    })
}
