use std::path::PathBuf;
use std::sync::Arc;

use anyhow::Result;
use reverse_tunnel::{
    ClientSnapshot, ReverseTunnelClientConfig, TunnelFreshness, run_client_with_counters,
};
use tokio::sync::{Mutex, watch};
use tracing::{info, warn};
use uuid::Uuid;

use crate::state::SharedRuntime;
use crate::tunnel_counters::TunnelCounterStore;

type SharedCounterStore = Arc<Mutex<TunnelCounterStore>>;

pub async fn spawn_reverse_tunnel(
    runtime_arc: SharedRuntime,
    config: ReverseTunnelClientConfig,
    counter_state_path: PathBuf,
) -> Result<()> {
    let counter_store = TunnelCounterStore::load(counter_state_path)?;
    let initial_counters = counter_store.counters().clone();
    {
        let mut runtime = runtime_arc.lock().await;
        runtime.reverse_tunnel_counters = initial_counters;
        runtime.reverse_tunnel_counter_persistence_healthy = true;
    }
    let counter_store = Arc::new(Mutex::new(counter_store));
    let (restart_tx, mut restart_rx) = watch::channel(0_u64);
    {
        let mut runtime = runtime_arc.lock().await;
        runtime.reverse_tunnel_restart = Some(restart_tx);
    }

    tokio::spawn(async move {
        loop {
            let counters = counter_store.lock().await.counters().clone();
            let (shutdown_tx, shutdown_rx) = watch::channel(false);
            let (status_tx, status_rx) = watch::channel(ClientSnapshot {
                session_id: Uuid::nil(),
                connected: false,
                attempts: 0,
                sent_heartbeats: 0,
                last_error: None,
                active_transport: None,
                freshness: TunnelFreshness::Unknown,
                last_failover_reason: None,
                event_counters: counters.clone(),
            });
            let final_status = status_rx.clone();
            let mut client = tokio::spawn(run_client_with_counters(
                config.clone(),
                shutdown_rx,
                status_tx,
                counters,
            ));
            let status_forwarder = tokio::spawn(forward_status(
                runtime_arc.clone(),
                counter_store.clone(),
                status_rx,
            ));

            let disconnect_reason = tokio::select! {
                _ = restart_rx.changed() => {
                    info!("reverse tunnel restart requested");
                    let _ = shutdown_tx.send(true);
                    let _ = client.await;
                    "restart requested"
                }
                _ = &mut client => {
                    warn!("reverse tunnel client exited; restarting manager generation");
                    "reverse tunnel client exited"
                }
            };

            let snapshot = final_status.borrow().clone();
            project_snapshot(runtime_arc.clone(), counter_store.clone(), snapshot).await;
            status_forwarder.abort();
            mark_disconnected(runtime_arc.clone(), disconnect_reason).await;
        }
    });
    Ok(())
}

async fn forward_status(
    runtime_arc: SharedRuntime,
    counter_store: SharedCounterStore,
    mut status_rx: watch::Receiver<ClientSnapshot>,
) {
    while status_rx.changed().await.is_ok() {
        let snapshot = status_rx.borrow().clone();
        project_snapshot(runtime_arc.clone(), counter_store.clone(), snapshot).await;
    }
}

async fn project_snapshot(
    runtime_arc: SharedRuntime,
    counter_store: SharedCounterStore,
    snapshot: ClientSnapshot,
) {
    let persistence_healthy = match counter_store
        .lock()
        .await
        .persist_if_changed(&snapshot.event_counters)
    {
        Ok(_) => true,
        Err(error) => {
            warn!(error = %error, "failed to persist reverse tunnel counters");
            false
        }
    };
    {
        let mut runtime = runtime_arc.lock().await;
        runtime.health.reverse_tunnel_connected = Some(snapshot.connected);
        runtime.health.reverse_tunnel_last_error = snapshot.last_error.clone();
        runtime.health.reverse_tunnel_active_transport = snapshot
            .active_transport
            .map(|transport| transport.as_str().to_string());
        runtime.health.reverse_tunnel_freshness = Some(snapshot.freshness.as_str().to_string());
        runtime.health.reverse_tunnel_failover_reason = snapshot
            .last_failover_reason
            .map(|reason| reason.as_str().to_string());
        runtime.reverse_tunnel_counters = snapshot.event_counters.clone();
        runtime.reverse_tunnel_counter_persistence_healthy = persistence_healthy;
        runtime.reverse_tunnel = Some(snapshot.clone());
    }
    if snapshot.connected {
        info!(
            session_id = %snapshot.session_id,
            attempts = snapshot.attempts,
            sent_heartbeats = snapshot.sent_heartbeats,
            active_transport = snapshot.active_transport.map(|value| value.as_str()).unwrap_or("none"),
            freshness = snapshot.freshness.as_str(),
            failover_reason = snapshot.last_failover_reason.map(|value| value.as_str()).unwrap_or("none"),
            "reverse tunnel connected"
        );
    } else if let Some(error) = snapshot.last_error {
        warn!(
            session_id = %snapshot.session_id,
            attempts = snapshot.attempts,
            freshness = snapshot.freshness.as_str(),
            failover_reason = snapshot.last_failover_reason.map(|value| value.as_str()).unwrap_or("none"),
            error = %error,
            "reverse tunnel disconnected"
        );
    }
}

async fn mark_disconnected(runtime_arc: SharedRuntime, reason: &str) {
    let mut runtime = runtime_arc.lock().await;
    let failover_reason = runtime
        .reverse_tunnel
        .as_ref()
        .and_then(|snapshot| snapshot.last_failover_reason)
        .map(|value| value.as_str().to_string());
    runtime.health.reverse_tunnel_connected = Some(false);
    runtime.health.reverse_tunnel_last_error = Some(reason.into());
    runtime.health.reverse_tunnel_active_transport = None;
    runtime.health.reverse_tunnel_freshness = Some("stale".into());
    runtime.health.reverse_tunnel_failover_reason = failover_reason;
    if let Some(snapshot) = runtime.reverse_tunnel.as_mut() {
        snapshot.connected = false;
        snapshot.active_transport = None;
        snapshot.freshness = TunnelFreshness::Stale;
        snapshot.last_error = Some(reason.into());
    }
}
