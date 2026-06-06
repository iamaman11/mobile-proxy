use reverse_tunnel::{ClientSnapshot, ReverseTunnelClientConfig, run_client};
use tokio::sync::watch;
use tracing::{info, warn};
use uuid::Uuid;

pub fn spawn_reverse_tunnel(config: ReverseTunnelClientConfig) {
    let (shutdown_tx, shutdown_rx) = watch::channel(false);
    let (status_tx, mut status_rx) = watch::channel(ClientSnapshot {
        session_id: Uuid::nil(),
        connected: false,
        attempts: 0,
        sent_heartbeats: 0,
        last_error: None,
    });
    tokio::spawn(async move {
        run_client(config, shutdown_rx, status_tx).await;
    });
    tokio::spawn(async move {
        let _shutdown_guard = shutdown_tx;
        while status_rx.changed().await.is_ok() {
            let snapshot = status_rx.borrow().clone();
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
    });
}
