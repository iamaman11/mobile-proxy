use std::time::{Duration, Instant};

use anyhow::{Context, Result};
use proxy_core::HealthRecord;
use runtime_domain::RuntimeState;
use tracing::{info, warn};

use crate::android::{
    bootstrap_cellular_data, bounce_mobile_data, ensure_cellular_default_route,
    kick_first_party_vpn_service, kick_stock_wireguard_bridge, tun0_ready,
};
use crate::config::{SupervisorConfig, TunnelOwner};
use crate::runtime_adapter::{legacy_readiness_from_state, state_from_legacy_readiness};

#[derive(Debug)]
pub struct SupervisorState {
    lifecycle_state: RuntimeState,
    last_route_repair: Option<Instant>,
    last_proxy_restart: Option<Instant>,
    last_tun0_ready: Option<bool>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct ObservedRuntimeTransition {
    pub from: RuntimeState,
    pub to: RuntimeState,
}

impl SupervisorState {
    pub fn new() -> Self {
        Self {
            lifecycle_state: RuntimeState::Booting,
            last_route_repair: None,
            last_proxy_restart: None,
            last_tun0_ready: None,
        }
    }

    pub fn observe_readiness(&mut self, raw: &str) -> Option<ObservedRuntimeTransition> {
        let next = state_from_legacy_readiness(raw);
        if next == self.lifecycle_state {
            return None;
        }
        let transition = ObservedRuntimeTransition {
            from: self.lifecycle_state,
            to: next,
        };
        self.lifecycle_state = next;
        Some(transition)
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

    pub fn observe_wireguard_tunnel_ready(
        &mut self,
        wireguard_enabled: bool,
        tun0_ready: bool,
    ) -> bool {
        if !wireguard_enabled {
            self.last_tun0_ready = None;
            return false;
        }

        let previous = self.last_tun0_ready.replace(tun0_ready);
        matches!(previous, Some(false)) && tun0_ready
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
    if !config.wireguard_enabled || tun0_ready() {
        return;
    }

    warn!(
        tunnel_owner = config.tunnel_owner.as_str(),
        "WireGuard tunnel owner is enabled but tun0 is absent; attempting tunnel kick"
    );
    match config.tunnel_owner {
        TunnelOwner::StockWireguardBridge => kick_stock_wireguard_bridge().await,
        TunnelOwner::FirstPartyVpnService => {
            if let Some(path) = config.app_tunnel_config.as_ref()
                && let Err(error) = kick_first_party_vpn_service(path).await
            {
                warn!("first-party VPN tunnel kick failed: {error:#}");
            }
        }
        TunnelOwner::FirstPartyReverseTunnel | TunnelOwner::FirstPartyAndroidEgress => {}
    }
}

pub async fn reconcile_health(
    config: &SupervisorConfig,
    state: &mut SupervisorState,
    health: &HealthRecord,
) -> Result<()> {
    if let Some(transition) = state.observe_readiness(&health.readiness_state) {
        info!(
            from = ?transition.from,
            to = ?transition.to,
            compatible_readiness = %legacy_readiness_from_state(transition.to),
            "runtime lifecycle projection changed"
        );
    }
    if health.wg_handshake_recent == Some(false) {
        match config.tunnel_owner {
            TunnelOwner::StockWireguardBridge => {
                warn!("stock WireGuard gateway is unreachable; attempting tunnel kick");
                kick_stock_wireguard_bridge().await;
            }
            TunnelOwner::FirstPartyVpnService => {
                warn!("first-party VPN gateway is unreachable; attempting tunnel kick");
                if let Some(path) = config.app_tunnel_config.as_ref()
                    && let Err(error) = kick_first_party_vpn_service(path).await
                {
                    warn!("first-party VPN tunnel kick failed: {error:#}");
                }
            }
            TunnelOwner::FirstPartyReverseTunnel | TunnelOwner::FirstPartyAndroidEgress => {}
        }
    }

    if health.cellular_route_ready != Some(false) {
        // Android keeps cellular defaults in per-network policy tables. A
        // root-owned direct proxy socket does not inherit an app UID's
        // netd mark, so it needs a matching main-table default as well. The
        // health projection can correctly observe a cellular policy route
        // while that main route is absent; repair it idempotently before
        // declaring the route sufficient for the native reverse-tunnel
        // runtime.
        if let Err(error) = ensure_cellular_default_route() {
            warn!("cellular main-route reconciliation failed: {error:#}");
        }
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
    // A failed VM-side public probe is not evidence that the phone's cellular
    // route is broken. Re-running `svc data enable` for it drops an otherwise
    // healthy QUIC session, so the public probe can never catch up. Cellular
    // bootstrap is reserved for a tunnel that is actually unavailable.
    if reason != "reverse_tunnel_not_ready" {
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

fn route_repair_allowed(config: &SupervisorConfig, state: &SupervisorState) -> bool {
    state.last_route_repair.is_none_or(|last| {
        last.elapsed() >= Duration::from_secs(config.repair_cooldown_secs.max(1))
    })
}

#[cfg(test)]
mod tests {
    use runtime_domain::RuntimeState;

    use super::SupervisorState;

    #[test]
    fn supervisor_tracks_neutral_state_without_duplicate_transitions() {
        let mut state = SupervisorState::new();
        assert_eq!(state.lifecycle_state, RuntimeState::Booting);

        let waiting = state.observe_readiness("waiting_wireguard").unwrap();
        assert_eq!(waiting.from, RuntimeState::Booting);
        assert_eq!(waiting.to, RuntimeState::WaitingTunnel);
        assert_eq!(state.lifecycle_state, RuntimeState::WaitingTunnel);
        assert!(state.observe_readiness("waiting_wireguard").is_none());

        let healthy = state.observe_readiness("healthy").unwrap();
        assert_eq!(healthy.from, RuntimeState::WaitingTunnel);
        assert_eq!(healthy.to, RuntimeState::Healthy);
    }

    #[test]
    fn unknown_readiness_fails_closed_to_recovering() {
        let mut state = SupervisorState::new();
        let transition = state.observe_readiness("raw-provider-error").unwrap();
        assert_eq!(transition.to, RuntimeState::Recovering);
        assert_eq!(state.lifecycle_state, RuntimeState::Recovering);
    }

    #[test]
    fn tunnel_ready_transition_only_fires_after_observed_absence() {
        let mut state = SupervisorState::new();

        assert!(!state.observe_wireguard_tunnel_ready(true, false));
        assert!(state.observe_wireguard_tunnel_ready(true, true));
        assert!(!state.observe_wireguard_tunnel_ready(true, true));
        assert!(!state.observe_wireguard_tunnel_ready(true, false));
        assert!(state.observe_wireguard_tunnel_ready(true, true));
    }

    #[test]
    fn first_observation_of_ready_tunnel_does_not_force_restart() {
        let mut state = SupervisorState::new();

        assert!(!state.observe_wireguard_tunnel_ready(true, true));
        assert!(!state.observe_wireguard_tunnel_ready(false, false));
        assert!(!state.observe_wireguard_tunnel_ready(true, true));
    }
}
