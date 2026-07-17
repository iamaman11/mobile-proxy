use std::time::{Duration, Instant};

use anyhow::{Context, Result};
use proxy_core::HealthRecord;
use tracing::{info, warn};

use crate::android::{
    bootstrap_cellular_data, bounce_mobile_data, ensure_cellular_default_route,
    kick_first_party_vpn_service, kick_stock_wireguard_bridge, tun0_ready,
};
use crate::config::{SupervisorConfig, TunnelOwner};

#[derive(Debug)]
pub struct SupervisorState {
    last_route_repair: Option<Instant>,
    last_proxy_restart: Option<Instant>,
}

impl SupervisorState {
    pub fn new() -> Self {
        Self {
            last_route_repair: None,
            last_proxy_restart: None,
        }
    }

    pub fn claim_proxy_restart(&mut self, cooldown_secs: u64) -> bool {
        if self
            .last_proxy_restart
            .is_some_and(|last| last.elapsed() < Duration::from_secs(cooldown_secs.max(1)))
        {
            return false;
        }
        self.last_proxy_restart = Some(Instant::now());
        true
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

pub async fn reconcile_wireguard(config: &SupervisorConfig) {
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
    kick_tunnel(config).await;
}

pub async fn reconcile_health(
    config: &SupervisorConfig,
    state: &mut SupervisorState,
    health: &HealthRecord,
) -> Result<()> {
    if config.wireguard_enabled && health.wg_handshake_recent == Some(false) {
        warn!(
            tunnel_owner = config.tunnel_owner.as_str(),
            "WireGuard gateway is unreachable; attempting tunnel kick"
        );
        kick_tunnel(config).await;
    }

    if health.cellular_route_ready != Some(false) {
        reconcile_reverse_tunnel_cellular_bootstrap(config, state, health);
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
            .await
            .context("mobile data bounce failed")?;
    }

    Ok(())
}

pub fn reconcile_startup_cellular_bootstrap(
    config: &SupervisorConfig,
    state: &mut SupervisorState,
) {
    if config.tunnel_owner != TunnelOwner::FirstPartyReverseTunnel {
        return;
    }
    if !route_repair_allowed(config, state) {
        return;
    }

    state.last_route_repair = Some(Instant::now());
    if let Err(err) = bootstrap_cellular_data() {
        warn!("startup cellular bootstrap failed: {err:#}");
    }
}

fn reconcile_reverse_tunnel_cellular_bootstrap(
    config: &SupervisorConfig,
    state: &mut SupervisorState,
    health: &HealthRecord,
) {
    if config.tunnel_owner != TunnelOwner::FirstPartyReverseTunnel || health.serving {
        return;
    }

    let Some(reason) = health.degradation_reason_code.as_deref() else {
        return;
    };
    if !matches!(reason, "public_probe_failed" | "reverse_tunnel_not_ready") {
        return;
    }
    if !route_repair_allowed(config, state) {
        return;
    }

    state.last_route_repair = Some(Instant::now());
    info!(
        "cellular bootstrap triggered readiness={} reason={reason}",
        health.readiness_state
    );
    if let Err(err) = bootstrap_cellular_data() {
        warn!("cellular bootstrap failed: {err:#}");
    }
}

async fn kick_tunnel(config: &SupervisorConfig) {
    match config.tunnel_owner {
        TunnelOwner::FirstPartyVpnService => {
            if let Err(err) = kick_first_party_vpn_service(&config.app_tunnel_config) {
                warn!("first-party VPN kick failed: {err:#}");
            }
        }
        TunnelOwner::FirstPartyReverseTunnel => {}
        TunnelOwner::StockWireguardBridge => kick_stock_wireguard_bridge().await,
    }
}

fn route_repair_allowed(config: &SupervisorConfig, state: &SupervisorState) -> bool {
    state.last_route_repair.is_none_or(|last| {
        last.elapsed() >= Duration::from_secs(config.repair_cooldown_secs.max(1))
    })
}
