use std::collections::HashMap;
use std::sync::Arc;
use std::time::Duration;

use anyhow::{Context, Result, bail};
use tokio::net::TcpStream;
use tokio::sync::{Mutex, mpsc, oneshot};
use tokio::time::timeout;
use uuid::Uuid;

use crate::model::{ServerFrame, ServerSessionSnapshot};

const TCP_PROXY_STREAM_TIMEOUT: Duration = Duration::from_secs(5);
const MAX_PENDING_TCP_STREAMS: usize = 256;

#[derive(Debug, Clone, Default)]
pub struct ReverseTunnelServerState {
    pub(crate) sessions: Arc<Mutex<HashMap<String, ServerSessionSnapshot>>>,
    pub(crate) connections: Arc<Mutex<HashMap<String, quinn::Connection>>>,
    pub(crate) tcp_controls: Arc<Mutex<HashMap<String, mpsc::Sender<ServerFrame>>>>,
    pub(crate) pending_tcp: Arc<Mutex<HashMap<Uuid, oneshot::Sender<TcpStream>>>>,
}

impl ReverseTunnelServerState {
    pub async fn has_active_session(&self, node_id: Option<&str>) -> bool {
        let sessions = self.sessions.lock().await;
        let active = sessions.values().any(|session| {
            session.connected && node_id.is_none_or(|expected| session.node_id == expected)
        });
        drop(sessions);
        if active {
            return true;
        }
        let controls = self.tcp_controls.lock().await;
        node_id.map_or(!controls.is_empty(), |expected| {
            controls.contains_key(expected)
        })
    }

    pub(crate) async fn open_tcp_proxy(&self, node_id: Option<&str>) -> Result<TcpStream> {
        self.open_tcp_proxy_with_timeout(node_id, TCP_PROXY_STREAM_TIMEOUT)
            .await
    }

    async fn open_tcp_proxy_with_timeout(
        &self,
        node_id: Option<&str>,
        wait: Duration,
    ) -> Result<TcpStream> {
        let controls = self.tcp_controls.lock().await;
        let control = if let Some(node_id) = node_id {
            controls.get(node_id).cloned()
        } else {
            controls.values().next().cloned()
        }
        .context("no authenticated TCP reverse tunnel is active")?;
        drop(controls);

        let stream_id = Uuid::new_v4();
        let (tx, rx) = oneshot::channel();
        {
            let mut pending = self.pending_tcp.lock().await;
            if pending.len() >= MAX_PENDING_TCP_STREAMS {
                bail!("TCP reverse tunnel pending stream capacity reached");
            }
            pending.insert(stream_id, tx);
        }

        if control
            .send(ServerFrame::OpenProxy { stream_id })
            .await
            .is_err()
        {
            self.pending_tcp.lock().await.remove(&stream_id);
            bail!("TCP reverse tunnel control channel closed");
        }

        let result = timeout(wait, rx).await;
        self.pending_tcp.lock().await.remove(&stream_id);
        result
            .context("TCP reverse tunnel proxy stream timed out")?
            .context("TCP reverse tunnel proxy stream was cancelled")
    }

    pub async fn snapshot(&self) -> Vec<ServerSessionSnapshot> {
        let mut sessions: Vec<_> = self.sessions.lock().await.values().cloned().collect();
        sessions.sort_by(|left, right| left.node_id.cmp(&right.node_id));
        sessions
    }

    pub async fn active_connection(&self, node_id: Option<&str>) -> Option<quinn::Connection> {
        let sessions = self.sessions.lock().await;
        let selected_node = if let Some(node_id) = node_id {
            sessions
                .get(node_id)
                .filter(|session| session.connected)
                .map(|session| session.node_id.clone())
        } else {
            sessions
                .values()
                .find(|session| session.connected)
                .map(|session| session.node_id.clone())
        }?;
        drop(sessions);

        let connection = self.connections.lock().await.get(&selected_node).cloned()?;
        if connection.close_reason().is_none() {
            return Some(connection);
        }
        self.connections.lock().await.remove(&selected_node);
        if let Some(session) = self.sessions.lock().await.get_mut(&selected_node) {
            session.connected = false;
        }
        None
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[tokio::test]
    async fn timed_out_tcp_proxy_request_is_removed() {
        let state = ReverseTunnelServerState::default();
        let (control_tx, mut control_rx) = mpsc::channel(1);
        state
            .tcp_controls
            .lock()
            .await
            .insert("test-phone".into(), control_tx);

        let request_state = state.clone();
        let request = tokio::spawn(async move {
            request_state
                .open_tcp_proxy_with_timeout(
                    Some("test-phone"),
                    Duration::from_millis(20),
                )
                .await
        });

        let frame = control_rx.recv().await.expect("open request must be sent");
        assert!(matches!(frame, ServerFrame::OpenProxy { .. }));

        let error = request
            .await
            .expect("request task must finish")
            .expect_err("request must time out without a proxy stream");
        assert!(error.to_string().contains("timed out"));
        assert!(state.pending_tcp.lock().await.is_empty());
    }

    #[tokio::test]
    async fn pending_tcp_proxy_requests_are_bounded() {
        let state = ReverseTunnelServerState::default();
        let (control_tx, _control_rx) = mpsc::channel(1);
        state
            .tcp_controls
            .lock()
            .await
            .insert("test-phone".into(), control_tx);

        let mut pending = state.pending_tcp.lock().await;
        for _ in 0..MAX_PENDING_TCP_STREAMS {
            let (tx, _rx) = oneshot::channel();
            pending.insert(Uuid::new_v4(), tx);
        }
        drop(pending);

        let error = state
            .open_tcp_proxy_with_timeout(Some("test-phone"), Duration::from_millis(1))
            .await
            .expect_err("capacity must reject new pending streams");
        assert!(error.to_string().contains("capacity"));
        assert_eq!(state.pending_tcp.lock().await.len(), MAX_PENDING_TCP_STREAMS);
    }
}
