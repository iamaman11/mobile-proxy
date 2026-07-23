use std::collections::HashMap;
use std::fmt;
use std::sync::{Arc, Mutex as StdMutex, MutexGuard};
use std::time::Duration;

use anyhow::{Context, Result, bail};
use tokio::net::TcpStream;
use tokio::sync::{Mutex, mpsc, oneshot};
use tokio::time::{Instant, timeout_at};
use uuid::Uuid;

use crate::model::{ServerFrame, ServerSessionSnapshot};

const TCP_PROXY_STREAM_TIMEOUT: Duration = Duration::from_secs(5);
const MAX_PENDING_TCP_STREAMS: usize = 256;
// A fixed per-device ceiling prevents one unavailable phone from monopolizing
// the global reserve-tunnel budget while still allowing a bounded burst.
const MAX_PENDING_TCP_STREAMS_PER_NODE: usize = 32;

#[derive(Clone)]
pub(crate) struct TcpControlChannel {
    pub(crate) session_id: Uuid,
    pub(crate) sender: mpsc::Sender<ServerFrame>,
}

pub(crate) struct PendingTcpProxyRequest {
    stream_id: Uuid,
    expected_node_id: String,
    expected_session_id: Uuid,
    created_at: Instant,
    deadline: Instant,
    response_sender: oneshot::Sender<TcpStream>,
}

type PendingTcpMap = HashMap<Uuid, PendingTcpProxyRequest>;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum TcpProxyStreamRejection {
    UnexpectedStreamId,
    NodeMismatch,
    SessionMismatch,
    SessionInactive,
    RequestExpired,
    RequesterClosed,
}

impl fmt::Display for TcpProxyStreamRejection {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(match self {
            Self::UnexpectedStreamId => "unexpected TCP reverse tunnel proxy stream id",
            Self::NodeMismatch => "TCP reverse tunnel proxy stream node mismatch",
            Self::SessionMismatch => "TCP reverse tunnel proxy stream session mismatch",
            Self::SessionInactive => "TCP reverse tunnel proxy stream session is not active",
            Self::RequestExpired => "TCP reverse tunnel proxy stream request expired",
            Self::RequesterClosed => "TCP reverse tunnel proxy requester closed",
        })
    }
}

impl std::error::Error for TcpProxyStreamRejection {}

struct PendingTcpCleanupGuard {
    stream_id: Uuid,
    pending: Arc<StdMutex<PendingTcpMap>>,
}

impl Drop for PendingTcpCleanupGuard {
    fn drop(&mut self) {
        lock_pending(&self.pending).remove(&self.stream_id);
    }
}

#[derive(Clone, Default)]
pub struct ReverseTunnelServerState {
    pub(crate) sessions: Arc<Mutex<HashMap<String, ServerSessionSnapshot>>>,
    pub(crate) connections: Arc<Mutex<HashMap<String, quinn::Connection>>>,
    pub(crate) tcp_controls: Arc<Mutex<HashMap<String, TcpControlChannel>>>,
    pub(crate) pending_tcp: Arc<StdMutex<PendingTcpMap>>,
}

impl ReverseTunnelServerState {
    pub async fn has_active_session(&self, node_id: Option<&str>) -> bool {
        let sessions = self.sessions.lock().await;
        let connections = self.connections.lock().await;
        let controls = self.tcp_controls.lock().await;
        sessions.values().any(|session| {
            if !session.connected || node_id.is_some_and(|expected| session.node_id != expected) {
                return false;
            }
            let quic_active = connections
                .get(&session.node_id)
                .is_some_and(|connection| connection.close_reason().is_none());
            let tcp_active = controls.get(&session.node_id).is_some_and(|control| {
                control.session_id == session.session_id && !control.sender.is_closed()
            });
            quic_active || tcp_active
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
        let (expected_node_id, expected_session_id, control) = self
            .select_tcp_control(node_id)
            .await
            .context("no authenticated TCP reverse tunnel is active")?;

        let stream_id = Uuid::new_v4();
        let (tx, rx) = oneshot::channel();
        let created_at = Instant::now();
        let deadline = created_at + wait;
        {
            let mut pending = lock_pending(&self.pending_tcp);
            if pending.len() >= MAX_PENDING_TCP_STREAMS {
                bail!("TCP reverse tunnel pending stream capacity reached");
            }
            let pending_for_node = pending
                .values()
                .filter(|request| request.expected_node_id == expected_node_id)
                .count();
            if pending_for_node >= MAX_PENDING_TCP_STREAMS_PER_NODE {
                bail!("TCP reverse tunnel per-device pending stream capacity reached");
            }
            pending.insert(
                stream_id,
                PendingTcpProxyRequest {
                    stream_id,
                    expected_node_id: expected_node_id.clone(),
                    expected_session_id,
                    created_at,
                    deadline,
                    response_sender: tx,
                },
            );
        }
        let _cleanup = PendingTcpCleanupGuard {
            stream_id,
            pending: self.pending_tcp.clone(),
        };

        if timeout_at(deadline, control.send(ServerFrame::OpenProxy { stream_id }))
            .await
            .context("TCP reverse tunnel control send timed out")?
            .is_err()
        {
            self.remove_tcp_control_for_session(&expected_node_id, expected_session_id)
                .await;
            self.cancel_pending_for_session(&expected_node_id, expected_session_id);
            bail!("TCP reverse tunnel control channel closed");
        }

        timeout_at(deadline, rx)
            .await
            .context("TCP reverse tunnel proxy stream timed out")?
            .context("TCP reverse tunnel proxy stream was cancelled")
    }

    async fn select_tcp_control(
        &self,
        node_id: Option<&str>,
    ) -> Option<(String, Uuid, mpsc::Sender<ServerFrame>)> {
        let sessions = self.sessions.lock().await;
        let controls = self.tcp_controls.lock().await;
        if let Some(expected_node_id) = node_id {
            let session = sessions
                .get(expected_node_id)
                .filter(|session| session.connected)?;
            let control = controls
                .get(expected_node_id)
                .filter(|control| control.session_id == session.session_id)?;
            return Some((
                expected_node_id.to_owned(),
                session.session_id,
                control.sender.clone(),
            ));
        }

        sessions.values().find_map(|session| {
            if !session.connected {
                return None;
            }
            let control = controls.get(&session.node_id)?;
            (control.session_id == session.session_id && !control.sender.is_closed()).then(|| {
                (
                    session.node_id.clone(),
                    session.session_id,
                    control.sender.clone(),
                )
            })
        })
    }

    pub(crate) async fn accept_tcp_proxy_stream(
        &self,
        node_id: &str,
        session_id: Uuid,
        stream_id: Uuid,
        stream: TcpStream,
    ) -> std::result::Result<(), TcpProxyStreamRejection> {
        let sessions = self.sessions.lock().await;
        let controls = self.tcp_controls.lock().await;
        let mut pending = lock_pending(&self.pending_tcp);
        let Some(request) = pending.get(&stream_id) else {
            return Err(TcpProxyStreamRejection::UnexpectedStreamId);
        };
        if request.stream_id != stream_id {
            return Err(TcpProxyStreamRejection::UnexpectedStreamId);
        }
        if request.expected_node_id != node_id {
            return Err(TcpProxyStreamRejection::NodeMismatch);
        }
        if request.expected_session_id != session_id {
            return Err(TcpProxyStreamRejection::SessionMismatch);
        }
        if request.is_expired(Instant::now()) {
            pending.remove(&stream_id);
            return Err(TcpProxyStreamRejection::RequestExpired);
        }
        let session_active = sessions
            .get(&request.expected_node_id)
            .is_some_and(|session| {
                session.connected && session.session_id == request.expected_session_id
            });
        let control_active = controls
            .get(&request.expected_node_id)
            .is_some_and(|control| {
                control.session_id == request.expected_session_id && !control.sender.is_closed()
            });
        if !session_active || !control_active {
            pending.remove(&stream_id);
            return Err(TcpProxyStreamRejection::SessionInactive);
        }
        let request = pending
            .remove(&stream_id)
            .expect("validated pending TCP request must remain present");
        drop(pending);
        drop(controls);
        drop(sessions);
        request
            .response_sender
            .send(stream)
            .map_err(|_| TcpProxyStreamRejection::RequesterClosed)
    }

    pub(crate) async fn register_tcp_control(
        &self,
        node_id: String,
        session_id: Uuid,
        sender: mpsc::Sender<ServerFrame>,
    ) {
        self.tcp_controls
            .lock()
            .await
            .insert(node_id, TcpControlChannel { session_id, sender });
    }

    pub(crate) async fn remove_tcp_control_for_session(&self, node_id: &str, session_id: Uuid) {
        let mut controls = self.tcp_controls.lock().await;
        if controls
            .get(node_id)
            .is_some_and(|control| control.session_id == session_id)
        {
            controls.remove(node_id);
        }
    }

    pub(crate) fn cancel_pending_for_session(&self, node_id: &str, session_id: Uuid) {
        lock_pending(&self.pending_tcp).retain(|_, request| {
            request.expected_node_id != node_id || request.expected_session_id != session_id
        });
    }

    pub(crate) async fn shutdown_tcp(&self) {
        let mut sessions = self.sessions.lock().await;
        let controls: Vec<_> = self
            .tcp_controls
            .lock()
            .await
            .drain()
            .map(|(node_id, control)| (node_id, control.session_id))
            .collect();
        lock_pending(&self.pending_tcp).clear();
        for (node_id, session_id) in controls {
            if let Some(session) = sessions.get_mut(&node_id)
                && session.session_id == session_id
            {
                session.connected = false;
            }
        }
    }

    pub async fn snapshot(&self) -> Vec<ServerSessionSnapshot> {
        let mut sessions: Vec<_> = self.sessions.lock().await.values().cloned().collect();
        sessions.sort_by(|left, right| left.node_id.cmp(&right.node_id));
        sessions
    }

    pub async fn active_connection(&self, node_id: Option<&str>) -> Option<quinn::Connection> {
        let sessions = self.sessions.lock().await;
        let (selected_node, selected_session_id) = if let Some(node_id) = node_id {
            sessions
                .get(node_id)
                .filter(|session| session.connected)
                .map(|session| (session.node_id.clone(), session.session_id))
        } else {
            sessions
                .values()
                .find(|session| session.connected)
                .map(|session| (session.node_id.clone(), session.session_id))
        }?;
        drop(sessions);

        let connection = self.connections.lock().await.get(&selected_node).cloned()?;
        if connection.close_reason().is_none() {
            return Some(connection);
        }
        self.connections.lock().await.remove(&selected_node);
        let tcp_active = self
            .tcp_controls
            .lock()
            .await
            .get(&selected_node)
            .is_some_and(|control| {
                control.session_id == selected_session_id && !control.sender.is_closed()
            });
        if !tcp_active
            && let Some(session) = self.sessions.lock().await.get_mut(&selected_node)
            && session.session_id == selected_session_id
        {
            session.connected = false;
        }
        None
    }

    #[cfg(test)]
    fn pending_tcp_len(&self) -> usize {
        lock_pending(&self.pending_tcp).len()
    }
}

impl PendingTcpProxyRequest {
    fn is_expired(&self, now: Instant) -> bool {
        debug_assert!(self.deadline >= self.created_at);
        now >= self.deadline
    }
}

fn lock_pending(pending: &StdMutex<PendingTcpMap>) -> MutexGuard<'_, PendingTcpMap> {
    pending
        .lock()
        .unwrap_or_else(|poisoned| poisoned.into_inner())
}

#[cfg(test)]
mod tests {
    use super::*;
    use tokio::net::TcpListener;
    use tokio::task::yield_now;

    #[tokio::test]
    async fn correct_node_and_session_complete_pending_request() {
        let state = ReverseTunnelServerState::default();
        let session_id = Uuid::new_v4();
        let mut control = register_session(&state, "phone-a", session_id).await;
        let request = spawn_request(&state, "phone-a").await;
        let stream_id = open_stream_id(&mut control).await;
        let (incoming, peer) = tcp_pair().await;

        state
            .accept_tcp_proxy_stream("phone-a", session_id, stream_id, incoming)
            .await
            .expect("matching stream must be accepted");
        let delivered = request
            .await
            .expect("request task must finish")
            .expect("request must receive proxy stream");

        assert_eq!(state.pending_tcp_len(), 0);
        drop(delivered);
        drop(peer);
    }

    #[tokio::test]
    async fn wrong_node_is_rejected_without_consuming_pending_request() {
        let state = ReverseTunnelServerState::default();
        let session_a = Uuid::new_v4();
        let session_b = Uuid::new_v4();
        let mut control_a = register_session(&state, "phone-a", session_a).await;
        let _control_b = register_session(&state, "phone-b", session_b).await;
        let request = spawn_request(&state, "phone-a").await;
        let stream_id = open_stream_id(&mut control_a).await;
        let (wrong, wrong_peer) = tcp_pair().await;

        assert_eq!(
            state
                .accept_tcp_proxy_stream("phone-b", session_b, stream_id, wrong)
                .await,
            Err(TcpProxyStreamRejection::NodeMismatch)
        );
        assert_eq!(state.pending_tcp_len(), 1);
        drop(wrong_peer);

        let (correct, correct_peer) = tcp_pair().await;
        state
            .accept_tcp_proxy_stream("phone-a", session_a, stream_id, correct)
            .await
            .unwrap();
        drop(request.await.unwrap().unwrap());
        drop(correct_peer);
        assert_eq!(state.pending_tcp_len(), 0);
    }

    #[tokio::test]
    async fn wrong_session_is_rejected_without_consuming_pending_request() {
        let state = ReverseTunnelServerState::default();
        let session_id = Uuid::new_v4();
        let mut control = register_session(&state, "phone-a", session_id).await;
        let request = spawn_request(&state, "phone-a").await;
        let stream_id = open_stream_id(&mut control).await;
        let (wrong, wrong_peer) = tcp_pair().await;

        assert_eq!(
            state
                .accept_tcp_proxy_stream("phone-a", Uuid::new_v4(), stream_id, wrong,)
                .await,
            Err(TcpProxyStreamRejection::SessionMismatch)
        );
        assert_eq!(state.pending_tcp_len(), 1);
        drop(wrong_peer);

        let (correct, correct_peer) = tcp_pair().await;
        state
            .accept_tcp_proxy_stream("phone-a", session_id, stream_id, correct)
            .await
            .unwrap();
        drop(request.await.unwrap().unwrap());
        drop(correct_peer);
    }

    #[tokio::test]
    async fn stale_session_is_rejected_and_removed() {
        let state = ReverseTunnelServerState::default();
        let old_session = Uuid::new_v4();
        let new_session = Uuid::new_v4();
        let mut control = register_session(&state, "phone-a", old_session).await;
        let request = spawn_request(&state, "phone-a").await;
        let stream_id = open_stream_id(&mut control).await;
        let _new_control = register_session(&state, "phone-a", new_session).await;
        let (late, late_peer) = tcp_pair().await;

        assert_eq!(
            state
                .accept_tcp_proxy_stream("phone-a", old_session, stream_id, late)
                .await,
            Err(TcpProxyStreamRejection::SessionInactive)
        );
        assert_eq!(state.pending_tcp_len(), 0);
        assert!(request.await.unwrap().is_err());
        drop(late_peer);
    }

    #[tokio::test]
    async fn timed_out_tcp_proxy_request_is_removed() {
        let state = ReverseTunnelServerState::default();
        let session_id = Uuid::new_v4();
        let mut control = register_session(&state, "test-phone", session_id).await;

        let request_state = state.clone();
        let request = tokio::spawn(async move {
            request_state
                .open_tcp_proxy_with_timeout(Some("test-phone"), Duration::from_millis(20))
                .await
        });
        let _ = open_stream_id(&mut control).await;

        let error = request
            .await
            .expect("request task must finish")
            .expect_err("request must time out without a proxy stream");
        assert!(error.to_string().contains("timed out"));
        assert_eq!(state.pending_tcp_len(), 0);
    }

    #[tokio::test]
    async fn cancelled_tcp_proxy_request_is_removed() {
        let state = ReverseTunnelServerState::default();
        let session_id = Uuid::new_v4();
        let mut control = register_session(&state, "test-phone", session_id).await;
        let request = spawn_request(&state, "test-phone").await;
        let _ = open_stream_id(&mut control).await;
        assert_eq!(state.pending_tcp_len(), 1);

        request.abort();
        let _ = request.await;
        yield_now().await;
        assert_eq!(state.pending_tcp_len(), 0);
    }

    #[tokio::test]
    async fn closed_control_channel_removes_pending_request() {
        let state = ReverseTunnelServerState::default();
        let session_id = Uuid::new_v4();
        let control = register_session(&state, "test-phone", session_id).await;
        drop(control);

        let error = state
            .open_tcp_proxy_with_timeout(Some("test-phone"), Duration::from_millis(100))
            .await
            .expect_err("closed control channel must fail");
        assert!(error.to_string().contains("control channel closed"));
        assert_eq!(state.pending_tcp_len(), 0);
    }

    #[tokio::test]
    async fn explicit_shutdown_clears_pending_requests_and_controls() {
        let state = ReverseTunnelServerState::default();
        let session_id = Uuid::new_v4();
        let mut control = register_session(&state, "test-phone", session_id).await;
        let request = spawn_request(&state, "test-phone").await;
        let _ = open_stream_id(&mut control).await;
        assert_eq!(state.pending_tcp_len(), 1);

        state.shutdown_tcp().await;

        let error = timeout_at(Instant::now() + Duration::from_secs(1), request)
            .await
            .expect("shutdown must finish the pending requester")
            .expect("request task must finish")
            .expect_err("shutdown must cancel the request");
        assert!(error.to_string().contains("cancelled"));
        assert_eq!(state.pending_tcp_len(), 0);
        assert!(state.tcp_controls.lock().await.is_empty());
        assert!(
            state
                .sessions
                .lock()
                .await
                .get("test-phone")
                .is_some_and(|session| !session.connected)
        );
        assert!(control.recv().await.is_none());
    }

    #[tokio::test]
    async fn pending_tcp_proxy_requests_are_globally_bounded() {
        let state = ReverseTunnelServerState::default();
        let session_id = Uuid::new_v4();
        let _control = register_session(&state, "test-phone", session_id).await;
        for index in 0..MAX_PENDING_TCP_STREAMS {
            insert_pending(&state, &format!("phone-{index}"), Uuid::new_v4());
        }

        let error = state
            .open_tcp_proxy_with_timeout(Some("test-phone"), Duration::from_millis(1))
            .await
            .expect_err("global capacity must reject new pending streams");
        assert!(error.to_string().contains("capacity"));
        assert_eq!(state.pending_tcp_len(), MAX_PENDING_TCP_STREAMS);
    }

    #[tokio::test]
    async fn pending_tcp_proxy_requests_are_bounded_per_device() {
        let state = ReverseTunnelServerState::default();
        let session_id = Uuid::new_v4();
        let _control = register_session(&state, "phone-a", session_id).await;
        for _ in 0..MAX_PENDING_TCP_STREAMS_PER_NODE {
            insert_pending(&state, "phone-a", session_id);
        }

        let error = state
            .open_tcp_proxy_with_timeout(Some("phone-a"), Duration::from_millis(1))
            .await
            .expect_err("per-device capacity must reject new pending streams");
        assert!(error.to_string().contains("per-device"));
        assert_eq!(state.pending_tcp_len(), MAX_PENDING_TCP_STREAMS_PER_NODE);
    }

    #[tokio::test]
    async fn one_device_capacity_does_not_block_another_device() {
        let state = ReverseTunnelServerState::default();
        let session_a = Uuid::new_v4();
        let session_b = Uuid::new_v4();
        let _control_a = register_session(&state, "phone-a", session_a).await;
        let mut control_b = register_session(&state, "phone-b", session_b).await;
        for _ in 0..MAX_PENDING_TCP_STREAMS_PER_NODE {
            insert_pending(&state, "phone-a", session_a);
        }

        let request = spawn_request(&state, "phone-b").await;
        let stream_id = open_stream_id(&mut control_b).await;
        let (incoming, peer) = tcp_pair().await;
        state
            .accept_tcp_proxy_stream("phone-b", session_b, stream_id, incoming)
            .await
            .unwrap();
        drop(request.await.unwrap().unwrap());
        drop(peer);
        assert_eq!(state.pending_tcp_len(), MAX_PENDING_TCP_STREAMS_PER_NODE);
    }

    #[tokio::test]
    async fn duplicate_stream_is_not_accepted_twice() {
        let state = ReverseTunnelServerState::default();
        let session_id = Uuid::new_v4();
        let mut control = register_session(&state, "phone-a", session_id).await;
        let request = spawn_request(&state, "phone-a").await;
        let stream_id = open_stream_id(&mut control).await;
        let (first, first_peer) = tcp_pair().await;
        state
            .accept_tcp_proxy_stream("phone-a", session_id, stream_id, first)
            .await
            .unwrap();
        drop(request.await.unwrap().unwrap());
        drop(first_peer);

        let (duplicate, duplicate_peer) = tcp_pair().await;
        assert_eq!(
            state
                .accept_tcp_proxy_stream("phone-a", session_id, stream_id, duplicate,)
                .await,
            Err(TcpProxyStreamRejection::UnexpectedStreamId)
        );
        drop(duplicate_peer);
    }

    async fn register_session(
        state: &ReverseTunnelServerState,
        node_id: &str,
        session_id: Uuid,
    ) -> mpsc::Receiver<ServerFrame> {
        state.sessions.lock().await.insert(
            node_id.to_owned(),
            ServerSessionSnapshot {
                node_id: node_id.to_owned(),
                session_id,
                connected: true,
                accepted_connections: 1,
                last_heartbeat_sequence: None,
            },
        );
        let (sender, receiver) = mpsc::channel(4);
        state
            .register_tcp_control(node_id.to_owned(), session_id, sender)
            .await;
        receiver
    }

    async fn spawn_request(
        state: &ReverseTunnelServerState,
        node_id: &str,
    ) -> tokio::task::JoinHandle<Result<TcpStream>> {
        let request_state = state.clone();
        let node_id = node_id.to_owned();
        tokio::spawn(async move {
            request_state
                .open_tcp_proxy_with_timeout(Some(&node_id), Duration::from_secs(1))
                .await
        })
    }

    async fn open_stream_id(control: &mut mpsc::Receiver<ServerFrame>) -> Uuid {
        let frame = control.recv().await.expect("open request must be sent");
        let ServerFrame::OpenProxy { stream_id } = frame;
        stream_id
    }

    async fn tcp_pair() -> (TcpStream, TcpStream) {
        let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
        let address = listener.local_addr().unwrap();
        let (connected, accepted) = tokio::join!(TcpStream::connect(address), listener.accept());
        (connected.unwrap(), accepted.unwrap().0)
    }

    fn insert_pending(state: &ReverseTunnelServerState, node_id: &str, session_id: Uuid) {
        let stream_id = Uuid::new_v4();
        let (response_sender, _response_receiver) = oneshot::channel();
        let created_at = Instant::now();
        lock_pending(&state.pending_tcp).insert(
            stream_id,
            PendingTcpProxyRequest {
                stream_id,
                expected_node_id: node_id.to_owned(),
                expected_session_id: session_id,
                created_at,
                deadline: created_at + Duration::from_secs(60),
                response_sender,
            },
        );
    }
}
