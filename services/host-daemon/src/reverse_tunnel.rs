use reverse_tunnel::{ClientSnapshot, ReverseTunnelClientConfig, run_client};
use tokio::sync::watch;
use tracing::{info, warn};
use uuid::Uuid;

use crate::state::SharedRuntime;

pub async fn spawn_reverse_tunnel(runtime_arc: SharedRuntime, config: ReverseTunnelClientConfig) {
    let (restart_tx, mut restart_rx) = watch::channel(0_u64);
    {
        let mut runtime = runtime_arc.lock().await;
        runtime.reverse_tunnel_restart = Some(restart_tx);
    }

    tokio::spawn(async move {
        loop {
            let (shutdown_tx, shutdown_rx) = watch::channel(false);
            let (status_tx, status_rx) = watch::channel(ClientSnapshot {
                session_id: Uuid::nil(),
                connected: false,
                attempts: 0,
                sent_heartbeats: 0,
                last_error: None,
            });
            let mut client = tokio::spawn(run_client(config.clone(), shutdown_rx, status_tx));
            let status_forwarder = tokio::spawn(forward_status(runtime_arc.clone(), status_rx));

            tokio::select! {
                _ = restart_rx.changed() => {
                    info!("reverse tunnel restart requested");
                    let _ = shutdown_tx.send(true);
                    let _ = client.await;
                    status_forwarder.abort();
                    mark_disconnected(runtime_arc.clone(), "restart requested").await;
                }
                _ = &mut client => {
                    status_forwarder.abort();
                    mark_disconnected(runtime_arc.clone(), "reverse tunnel client exited").await;
                    warn!("reverse tunnel client exited; restarting manager generation");
                }
            }
        }
    });
}

async fn forward_status(
    runtime_arc: SharedRuntime,
    mut status_rx: watch::Receiver<ClientSnapshot>,
) {
    while status_rx.changed().await.is_ok() {
        let snapshot = status_rx.borrow().clone();
        {
            let mut runtime = runtime_arc.lock().await;
            runtime.health.reverse_tunnel_connected = Some(snapshot.connected);
            runtime.health.reverse_tunnel_last_error = snapshot.last_error.clone();
            runtime.reverse_tunnel = Some(snapshot.clone());
        }
        if snapshot.connected {
            info!(
                session_id = %snapshot.session_id,
                attempts = snapshot.attempts,
                sent_heartbeats = snapshot.sent_heartbeats,
                "reverse tunnel connected"
            );
        } else if let Some(error) = snapshot.last_error {
            warn!(
                session_id = %snapshot.session_id,
                attempts = snapshot.attempts,
                error = %error,
                "reverse tunnel disconnected"
            );
        }
    }
}

async fn mark_disconnected(runtime_arc: SharedRuntime, reason: &str) {
    let mut runtime = runtime_arc.lock().await;
    runtime.health.reverse_tunnel_connected = Some(false);
    runtime.health.reverse_tunnel_last_error = Some(reason.into());
    if let Some(snapshot) = runtime.reverse_tunnel.as_mut() {
        snapshot.connected = false;
        snapshot.last_error = Some(reason.into());
    }
}
