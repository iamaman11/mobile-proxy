mod android;
mod cli;
mod config;
mod dns;
mod health;
mod process;
mod runtime_adapter;

use std::time::Duration;

use anyhow::{Context, Result};
use clap::Parser;
use tokio::time::sleep;
use tracing::warn;

use crate::android::{
    provision_android_egress, push_local_ui_control_token, stop_compatibility_vpns, tun0_ready,
};
use crate::cli::Cli;
use crate::config::{TunnelOwner, load_config};
use crate::dns::{reconcile_cellular_dns, reconcile_cellular_proxy_interface};
use crate::health::{
    SupervisorState, fetch_health, reconcile_health, reconcile_startup_cellular_bootstrap,
    reconcile_wireguard,
};
use crate::process::{RuntimeChildren, cleanup_stale_runtime_processes};

#[tokio::main]
async fn main() -> Result<()> {
    tracing_subscriber::fmt::init();
    let config = load_config(Cli::parse())?;
    let client = reqwest::Client::builder()
        .timeout(Duration::from_secs(5))
        .build()
        .context("failed to build HTTP client")?;
    let mut children = RuntimeChildren::new();
    let mut state = SupervisorState::new();

    cleanup_stale_runtime_processes();
    if let Err(error) = push_local_ui_control_token(config.ui_control_token.as_deref()) {
        warn!("failed to provision local UI control: {error:#}");
    }
    if let Some(egress) = config.app_egress.as_ref()
        && let Err(error) =
            provision_android_egress(egress.port, &egress.username, &egress.password)
    {
        warn!("failed to provision Android cellular egress: {error:#}");
    }
    if config.tunnel_owner != TunnelOwner::StockWireguardBridge
        && let Err(error) = stop_compatibility_vpns()
    {
        warn!("failed to stop compatibility VPNs before startup: {error:#}");
    }
    reconcile_startup_cellular_bootstrap(&config, &mut state);

    loop {
        let dns_changed = match reconcile_cellular_dns(&config) {
            Ok(changed) => changed,
            Err(err) => {
                warn!("cellular DNS reconciliation failed: {err:#}");
                false
            }
        };
        let interface_changed = match reconcile_cellular_proxy_interface(&config) {
            Ok(changed) => changed,
            Err(err) => {
                warn!("cellular proxy interface reconciliation failed: {err:#}");
                false
            }
        };
        if dns_changed || interface_changed {
            children.restart_proxy(&config);
        }
        if state.observe_wireguard_tunnel_ready(config.wireguard_enabled, tun0_ready())
            && state.claim_proxy_restart(config.repair_cooldown_secs)
        {
            warn!("tun0 became ready; restarting proxy to refresh listener binds");
            children.restart_proxy(&config);
        }
        children.ensure(&config)?;
        reconcile_wireguard(&config).await;

        match fetch_health(&client, &config).await {
            Ok(health) => {
                if let Err(err) = reconcile_health(&config, &mut state, &health).await {
                    warn!("runtime health reconciliation failed: {err:#}");
                }
                if health.degradation_reason_code.as_deref() == Some("public_probe_failed")
                    && config.tunnel_owner != TunnelOwner::FirstPartyReverseTunnel
                    && state.claim_proxy_restart(config.repair_cooldown_secs)
                {
                    warn!("end-to-end proxy probe failed; restarting local proxy");
                    children.restart_proxy(&config);
                }
                // A reverse-tunnel proxy must keep its authenticated transport
                // session alive while the VM performs its independent public
                // probe. Restarting the local proxy here also kills host-daemon,
                // which tears down QUIC before that probe can succeed and causes
                // a permanent reconnect loop. Process exits and missing local
                // listeners are still repaired by `children.ensure`.
            }
            Err(err) => warn!("host-daemon health unavailable: {err:#}"),
        }

        if config.once {
            break;
        }
        sleep(Duration::from_secs(config.poll_secs.max(1))).await;
    }

    Ok(())
}
