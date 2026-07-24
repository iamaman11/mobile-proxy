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
// Session selection tolerates multiple missed heartbeats while remaining bounded.
// Freshness is checked lazily on every routing/acceptance decision; no sweeper is spawned.
const DEFAULT_SESSION_HEARTBEAT_TIMEOUT: Duration = Duration::from_secs(30);

#[derive(Clone, Copy)]
pub(crate) struct SessionLiveness {
    session_id: Uuid,
    authority_id: Uuid,
    last_seen_at: Instant,
}

#[derive(Clone)]
pub(crate) struct TcpControlChannel {
    pub(crate) session_id: Uuid,
    pub(crate) authority_id: Uuid,
    pub(crate) sender: mpsc::Sender<ServerFrame>,
}

#[derive(Clone)]
pub(crate) struct SessionBound<T> {
    session_id: Uuid,
    authority_id: Uuid,
    value: T,
}

pub(crate) enum SessionAuthority {
    Quic(quinn::Connection),
    Tcp(mpsc::Sender<ServerFrame>),
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct ActiveSessionTarget {
    pub(crate) node_id: String,
    pub(crate) session_id: Uuid,
    pub(crate) authority_id: Uuid,
}

pub(crate) struct PendingTcpProxyRequest {
    stream_id: Uuid,
    expected_node_id: String,
    expected_session_id: Uuid,
    expected_authority_id: Uuid,
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

#[derive(Clone)]
pub struct ReverseTunnelServerState {
    pub(crate) sessions: Arc<Mutex<HashMap<String, ServerSessionSnapshot>>>,
    pub(crate) connections: Arc<Mutex<HashMap<String, SessionBound<quinn::Connection>>>>,
    pub(crate) tcp_controls: Arc<Mutex<HashMap<String, TcpControlChannel>>>,
    pub(crate) pending_tcp: Arc<StdMutex<PendingTcpMap>>,
    session_liveness: Arc<Mutex<HashMap<String, SessionLiveness>>>,
    heartbeat_timeout: Duration,
}

impl Default for ReverseTunnelServerState {
    fn default() -> Self {
        Self {
            sessions: Arc::default(),
            connections: Arc::default(),
            tcp_controls: Arc::default(),
            pending_tcp: Arc::default(),
            session_liveness: Arc::default(),
            heartbeat_timeout: DEFAULT_SESSION_HEARTBEAT_TIMEOUT,
        }
    }
}

impl ReverseTunnelServerState {
    pub async fn has_active_session(&self, node_id: Option<&str>) -> bool {
        self.select_active_target(node_id).await.is_some()
    }

    pub(crate) async fn select_active_target(
        &self,
        node_id: Option<&str>,
    ) -> Option<ActiveSessionTarget> {
        let now = Instant::now();
        let sessions = self.sessions.lock().await;
        let liveness = self.session_liveness.lock().await;
        let connections = self.connections.lock().await;
        let controls = self.tcp_controls.lock().await;
        let mut inactive = Vec::new();
        let mut closed_connections = Vec::new();
        let mut candidates = Vec::with_capacity(2);

        for session in sessions.values() {
            if !session.connected || node_id.is_some_and(|expected| session.node_id != expected) {
                continue;
            }
            let Some(live) = liveness.get(&session.node_id).filter(|live| {
                live.session_id == session.session_id
                    && now.saturating_duration_since(live.last_seen_at) <= self.heartbeat_timeout
            }) else {
                if let Some(live) = liveness.get(&session.node_id) {
                    inactive.push((session.node_id.clone(), live.session_id, live.authority_id));
                }
                continue;
            };
            let quic = connections.get(&session.node_id).filter(|connection| {
                connection.session_id == session.session_id
                    && connection.authority_id == live.authority_id
            });
            let quic_active =
                quic.is_some_and(|connection| connection.value.close_reason().is_none());
            if quic.is_some_and(|connection| connection.value.close_reason().is_some()) {
                closed_connections.push((
                    session.node_id.clone(),
                    session.session_id,
                    live.authority_id,
                ));
            }
            let tcp_active = controls.get(&session.node_id).is_some_and(|control| {
                control.session_id == session.session_id
                    && control.authority_id == live.authority_id
                    && !control.sender.is_closed()
            });
            if quic_active || tcp_active {
                candidates.push(ActiveSessionTarget {
                    node_id: session.node_id.clone(),
                    session_id: session.session_id,
                    authority_id: live.authority_id,
                });
            } else {
                inactive.push((
                    session.node_id.clone(),
                    session.session_id,
                    live.authority_id,
                ));
            }
        }

        let selected = if node_id.is_some() {
            candidates.into_iter().next()
        } else {
            let mut candidates = candidates.into_iter();
            let first = candidates.next();
            if first.is_some() && candidates.next().is_none() {
                first
            } else {
                None
            }
        };
        drop(controls);
        drop(connections);
        drop(liveness);
        drop(sessions);

        for (closed_node, closed_session, closed_authority) in closed_connections {
            self.remove_quic_connection_for_authority(
                &closed_node,
                closed_session,
                closed_authority,
                b"QUIC connection closed",
            )
            .await;
        }
        for (inactive_node, inactive_session, inactive_authority) in inactive {
            self.expire_session(&inactive_node, inactive_session, inactive_authority)
                .await;
        }
        selected
    }

    #[cfg(test)]
    pub(crate) async fn open_tcp_proxy(&self, node_id: Option<&str>) -> Result<TcpStream> {
        let target = self
            .select_active_target(node_id)
            .await
            .context("no unambiguous authenticated reverse tunnel is active")?;
        self.open_tcp_proxy_for_target(&target).await
    }

    pub(crate) async fn open_tcp_proxy_for_target(
        &self,
        target: &ActiveSessionTarget,
    ) -> Result<TcpStream> {
        self.open_tcp_proxy_for_target_with_timeout(target, TCP_PROXY_STREAM_TIMEOUT)
            .await
    }

    #[cfg(test)]
    async fn open_tcp_proxy_with_timeout(
        &self,
        node_id: Option<&str>,
        wait: Duration,
    ) -> Result<TcpStream> {
        let target = self
            .select_active_target(node_id)
            .await
            .context("no unambiguous authenticated reverse tunnel is active")?;
        self.open_tcp_proxy_for_target_with_timeout(&target, wait)
            .await
    }

    async fn open_tcp_proxy_for_target_with_timeout(
        &self,
        target: &ActiveSessionTarget,
        wait: Duration,
    ) -> Result<TcpStream> {
        let control = self
            .select_tcp_control_for_target(target)
            .await
            .context("no authenticated TCP reverse tunnel is active for selected session")?;

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
                .filter(|request| request.expected_node_id == target.node_id)
                .count();
            if pending_for_node >= MAX_PENDING_TCP_STREAMS_PER_NODE {
                bail!("TCP reverse tunnel per-device pending stream capacity reached");
            }
            pending.insert(
                stream_id,
                PendingTcpProxyRequest {
                    stream_id,
                    expected_node_id: target.node_id.clone(),
                    expected_session_id: target.session_id,
                    expected_authority_id: target.authority_id,
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
            self.remove_tcp_control_for_authority(
                &target.node_id,
                target.session_id,
                target.authority_id,
            )
            .await;
            self.cancel_pending_for_authority(
                &target.node_id,
                target.session_id,
                target.authority_id,
            );
            bail!("TCP reverse tunnel control channel closed");
        }

        timeout_at(deadline, rx)
            .await
            .context("TCP reverse tunnel proxy stream timed out")?
            .context("TCP reverse tunnel proxy stream was cancelled")
    }

    #[cfg(test)]
    async fn select_tcp_control(
        &self,
        node_id: Option<&str>,
    ) -> Option<(String, Uuid, mpsc::Sender<ServerFrame>)> {
        let target = self.select_active_target(node_id).await?;
        let sender = self.select_tcp_control_for_target(&target).await?;
        Some((target.node_id, target.session_id, sender))
    }

    async fn select_tcp_control_for_target(
        &self,
        target: &ActiveSessionTarget,
    ) -> Option<mpsc::Sender<ServerFrame>> {
        let now = Instant::now();
        let sessions = self.sessions.lock().await;
        let liveness = self.session_liveness.lock().await;
        let controls = self.tcp_controls.lock().await;
        let current = sessions
            .get(&target.node_id)
            .is_some_and(|session| session.connected && session.session_id == target.session_id);
        let fresh = current
            && session_is_fresh(
                &liveness,
                &target.node_id,
                target.session_id,
                target.authority_id,
                now,
                self.heartbeat_timeout,
            );
        let selected = fresh
            .then(|| controls.get(&target.node_id))
            .flatten()
            .filter(|control| {
                control.session_id == target.session_id
                    && control.authority_id == target.authority_id
                    && !control.sender.is_closed()
            })
            .map(|control| control.sender.clone());
        drop(controls);
        drop(liveness);
        drop(sessions);

        if current && !fresh {
            self.expire_session(&target.node_id, target.session_id, target.authority_id)
                .await;
        }
        selected
    }

    pub(crate) async fn accept_tcp_proxy_stream(
        &self,
        node_id: &str,
        session_id: Uuid,
        stream_id: Uuid,
        stream: TcpStream,
    ) -> std::result::Result<(), TcpProxyStreamRejection> {
        let now = Instant::now();
        let (stale_node, stale_session, stale_authority, expire_current) = {
            let sessions = self.sessions.lock().await;
            let liveness = self.session_liveness.lock().await;
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
            if request.is_expired(now) {
                pending.remove(&stream_id);
                return Err(TcpProxyStreamRejection::RequestExpired);
            }
            let session_current = sessions
                .get(&request.expected_node_id)
                .is_some_and(|session| {
                    session.connected && session.session_id == request.expected_session_id
                });
            let authority_current = session_current
                && liveness
                    .get(&request.expected_node_id)
                    .is_some_and(|entry| {
                        entry.session_id == request.expected_session_id
                            && entry.authority_id == request.expected_authority_id
                    });
            let session_fresh = authority_current
                && session_is_fresh(
                    &liveness,
                    &request.expected_node_id,
                    request.expected_session_id,
                    request.expected_authority_id,
                    now,
                    self.heartbeat_timeout,
                );
            let control_active = controls
                .get(&request.expected_node_id)
                .is_some_and(|control| {
                    control.session_id == request.expected_session_id
                        && control.authority_id == request.expected_authority_id
                        && !control.sender.is_closed()
                });
            if session_fresh && control_active {
                let request = pending
                    .remove(&stream_id)
                    .expect("validated pending TCP request must remain present");
                return request
                    .response_sender
                    .send(stream)
                    .map_err(|_| TcpProxyStreamRejection::RequesterClosed);
            }
            let stale = (
                request.expected_node_id.clone(),
                request.expected_session_id,
                request.expected_authority_id,
                authority_current,
            );
            pending.remove(&stream_id);
            stale
        };
        if expire_current {
            self.expire_session(&stale_node, stale_session, stale_authority)
                .await;
        }
        Err(TcpProxyStreamRejection::SessionInactive)
    }

    pub(crate) async fn replace_session_authority(
        &self,
        node_id: String,
        session_id: Uuid,
        authority: SessionAuthority,
    ) -> Uuid {
        let authority_id = Uuid::new_v4();
        let displaced_connection = {
            let mut sessions = self.sessions.lock().await;
            let mut liveness = self.session_liveness.lock().await;
            let mut connections = self.connections.lock().await;
            let mut controls = self.tcp_controls.lock().await;
            let mut pending = lock_pending(&self.pending_tcp);

            let previous_session = sessions.get(&node_id).map(|session| session.session_id);
            let previous_authority = liveness.get(&node_id).map(|entry| entry.authority_id);
            let accepted_connections = sessions
                .get(&node_id)
                .map(|existing| existing.accepted_connections.saturating_add(1))
                .unwrap_or(1);

            if let Some(previous_session) = previous_session {
                pending.retain(|_, request| {
                    if request.expected_node_id != node_id
                        || request.expected_session_id != previous_session
                    {
                        return true;
                    }
                    previous_authority
                        .is_some_and(|previous| request.expected_authority_id != previous)
                });
            }

            let displaced_connection = connections.remove(&node_id);
            controls.remove(&node_id);
            liveness.remove(&node_id);
            sessions.insert(
                node_id.clone(),
                ServerSessionSnapshot {
                    node_id: node_id.clone(),
                    session_id,
                    connected: true,
                    accepted_connections,
                    last_heartbeat_sequence: None,
                },
            );
            liveness.insert(
                node_id.clone(),
                SessionLiveness {
                    session_id,
                    authority_id,
                    last_seen_at: Instant::now(),
                },
            );
            match authority {
                SessionAuthority::Quic(connection) => {
                    connections.insert(
                        node_id,
                        SessionBound {
                            session_id,
                            authority_id,
                            value: connection,
                        },
                    );
                }
                SessionAuthority::Tcp(sender) => {
                    controls.insert(
                        node_id,
                        TcpControlChannel {
                            session_id,
                            authority_id,
                            sender,
                        },
                    );
                }
            }
            displaced_connection
        };

        if let Some(connection) = displaced_connection {
            connection
                .value
                .close(0_u32.into(), b"session authority replaced");
        }
        authority_id
    }

    pub(crate) async fn disconnect_session_authority(
        &self,
        node_id: &str,
        session_id: Uuid,
        authority_id: Uuid,
        reason: &[u8],
    ) -> bool {
        let removed_connection = {
            let mut sessions = self.sessions.lock().await;
            let mut liveness = self.session_liveness.lock().await;
            let mut connections = self.connections.lock().await;
            let mut controls = self.tcp_controls.lock().await;
            let mut pending = lock_pending(&self.pending_tcp);

            let current_session = sessions
                .get(node_id)
                .is_some_and(|session| session.connected && session.session_id == session_id);
            let current_authority = liveness.get(node_id).is_some_and(|entry| {
                entry.session_id == session_id && entry.authority_id == authority_id
            });
            if !current_session || !current_authority {
                return false;
            }

            if let Some(session) = sessions.get_mut(node_id) {
                session.connected = false;
            }
            liveness.remove(node_id);
            let removed_connection =
                remove_session_bound(&mut connections, node_id, session_id, authority_id);
            if controls.get(node_id).is_some_and(|control| {
                control.session_id == session_id && control.authority_id == authority_id
            }) {
                controls.remove(node_id);
            }
            pending.retain(|_, request| {
                request.expected_node_id != node_id
                    || request.expected_session_id != session_id
                    || request.expected_authority_id != authority_id
            });
            removed_connection
        };

        if let Some(connection) = removed_connection {
            connection.value.close(0_u32.into(), reason);
        }
        true
    }

    #[cfg(test)]
    pub(crate) async fn register_tcp_control(
        &self,
        node_id: String,
        session_id: Uuid,
        sender: mpsc::Sender<ServerFrame>,
    ) {
        self.tcp_controls.lock().await.insert(
            node_id,
            TcpControlChannel {
                session_id,
                authority_id: session_id,
                sender,
            },
        );
    }

    #[cfg(test)]
    pub(crate) async fn remove_tcp_control_for_session(&self, node_id: &str, session_id: Uuid) {
        let mut controls = self.tcp_controls.lock().await;
        if controls
            .get(node_id)
            .is_some_and(|control| control.session_id == session_id)
        {
            controls.remove(node_id);
        }
    }

    pub(crate) async fn remove_tcp_control_for_authority(
        &self,
        node_id: &str,
        session_id: Uuid,
        authority_id: Uuid,
    ) {
        let mut controls = self.tcp_controls.lock().await;
        if controls.get(node_id).is_some_and(|control| {
            control.session_id == session_id && control.authority_id == authority_id
        }) {
            controls.remove(node_id);
        }
    }

    pub(crate) fn cancel_pending_for_authority(
        &self,
        node_id: &str,
        session_id: Uuid,
        authority_id: Uuid,
    ) {
        lock_pending(&self.pending_tcp).retain(|_, request| {
            request.expected_node_id != node_id
                || request.expected_session_id != session_id
                || request.expected_authority_id != authority_id
        });
    }

    #[cfg(test)]
    pub(crate) async fn register_session_liveness(&self, node_id: String, session_id: Uuid) {
        self.session_liveness.lock().await.insert(
            node_id,
            SessionLiveness {
                session_id,
                authority_id: session_id,
                last_seen_at: Instant::now(),
            },
        );
    }

    #[cfg(test)]
    pub(crate) async fn refresh_session_heartbeat(&self, node_id: &str, session_id: Uuid) -> bool {
        self.refresh_session_heartbeat_for_authority(node_id, session_id, session_id)
            .await
    }

    pub(crate) async fn refresh_session_heartbeat_for_authority(
        &self,
        node_id: &str,
        session_id: Uuid,
        authority_id: Uuid,
    ) -> bool {
        let sessions = self.sessions.lock().await;
        if !sessions
            .get(node_id)
            .is_some_and(|session| session.connected && session.session_id == session_id)
        {
            return false;
        }
        let mut liveness = self.session_liveness.lock().await;
        let connections = self.connections.lock().await;
        let controls = self.tcp_controls.lock().await;
        let quic_active = connections.get(node_id).is_some_and(|connection| {
            connection.session_id == session_id
                && connection.authority_id == authority_id
                && connection.value.close_reason().is_none()
        });
        let tcp_active = controls.get(node_id).is_some_and(|control| {
            control.session_id == session_id
                && control.authority_id == authority_id
                && !control.sender.is_closed()
        });
        if !quic_active && !tcp_active {
            return false;
        }
        let Some(entry) = liveness
            .get_mut(node_id)
            .filter(|entry| entry.session_id == session_id && entry.authority_id == authority_id)
        else {
            return false;
        };
        entry.last_seen_at = Instant::now();
        true
    }

    pub(crate) async fn remove_session_liveness(&self, node_id: &str, session_id: Uuid) {
        let mut liveness = self.session_liveness.lock().await;
        if liveness
            .get(node_id)
            .is_some_and(|entry| entry.session_id == session_id)
        {
            liveness.remove(node_id);
        }
    }

    async fn remove_quic_connection_for_authority(
        &self,
        node_id: &str,
        session_id: Uuid,
        authority_id: Uuid,
        reason: &[u8],
    ) {
        let connection = remove_session_bound(
            &mut *self.connections.lock().await,
            node_id,
            session_id,
            authority_id,
        );
        if let Some(connection) = connection {
            connection.value.close(0_u32.into(), reason);
        }
    }

    async fn expire_session(&self, node_id: &str, session_id: Uuid, authority_id: Uuid) {
        self.disconnect_session_authority(node_id, session_id, authority_id, b"heartbeat stale")
            .await;
    }

    pub(crate) async fn shutdown_tcp(&self) {
        let controls: Vec<_> = self
            .tcp_controls
            .lock()
            .await
            .drain()
            .map(|(node_id, control)| (node_id, control.session_id))
            .collect();
        lock_pending(&self.pending_tcp).clear();
        for (node_id, session_id) in controls {
            if let Some(session) = self.sessions.lock().await.get_mut(&node_id)
                && session.session_id == session_id
            {
                session.connected = false;
            }
            self.remove_session_liveness(&node_id, session_id).await;
        }
    }

    pub async fn snapshot(&self) -> Vec<ServerSessionSnapshot> {
        let mut sessions: Vec<_> = self.sessions.lock().await.values().cloned().collect();
        sessions.sort_by(|left, right| left.node_id.cmp(&right.node_id));
        sessions
    }

    pub async fn active_connection(&self, node_id: Option<&str>) -> Option<quinn::Connection> {
        let target = self.select_active_target(node_id).await?;
        self.active_connection_for_target(&target).await
    }

    pub(crate) async fn active_connection_for_target(
        &self,
        target: &ActiveSessionTarget,
    ) -> Option<quinn::Connection> {
        let now = Instant::now();
        let sessions = self.sessions.lock().await;
        let liveness = self.session_liveness.lock().await;
        let connections = self.connections.lock().await;
        let controls = self.tcp_controls.lock().await;
        let current = sessions
            .get(&target.node_id)
            .is_some_and(|session| session.connected && session.session_id == target.session_id);
        let fresh = current
            && session_is_fresh(
                &liveness,
                &target.node_id,
                target.session_id,
                target.authority_id,
                now,
                self.heartbeat_timeout,
            );
        let connection = fresh
            .then(|| connections.get(&target.node_id))
            .flatten()
            .filter(|connection| {
                connection.session_id == target.session_id
                    && connection.authority_id == target.authority_id
                    && connection.value.close_reason().is_none()
            })
            .map(|connection| connection.value.clone());
        let closed = connections.get(&target.node_id).is_some_and(|connection| {
            connection.session_id == target.session_id
                && connection.authority_id == target.authority_id
                && connection.value.close_reason().is_some()
        });
        let tcp_active = controls.get(&target.node_id).is_some_and(|control| {
            control.session_id == target.session_id
                && control.authority_id == target.authority_id
                && !control.sender.is_closed()
        });
        drop(controls);
        drop(connections);
        drop(liveness);
        drop(sessions);

        if closed {
            self.remove_quic_connection_for_authority(
                &target.node_id,
                target.session_id,
                target.authority_id,
                b"QUIC connection closed",
            )
            .await;
        }
        if current && (!fresh || (connection.is_none() && !tcp_active)) {
            self.expire_session(&target.node_id, target.session_id, target.authority_id)
                .await;
        }
        connection
    }

    #[cfg(test)]
    async fn set_session_last_seen(&self, node_id: &str, session_id: Uuid, last_seen_at: Instant) {
        let mut liveness = self.session_liveness.lock().await;
        let entry = liveness
            .get_mut(node_id)
            .filter(|entry| entry.session_id == session_id)
            .expect("test session liveness must exist");
        entry.last_seen_at = last_seen_at;
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

fn session_is_fresh(
    liveness: &HashMap<String, SessionLiveness>,
    node_id: &str,
    session_id: Uuid,
    authority_id: Uuid,
    now: Instant,
    heartbeat_timeout: Duration,
) -> bool {
    liveness.get(node_id).is_some_and(|entry| {
        entry.session_id == session_id
            && entry.authority_id == authority_id
            && now.saturating_duration_since(entry.last_seen_at) <= heartbeat_timeout
    })
}

fn remove_session_bound<T>(
    entries: &mut HashMap<String, SessionBound<T>>,
    node_id: &str,
    session_id: Uuid,
    authority_id: Uuid,
) -> Option<SessionBound<T>> {
    if entries
        .get(node_id)
        .is_some_and(|entry| entry.session_id == session_id && entry.authority_id == authority_id)
    {
        entries.remove(node_id)
    } else {
        None
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
        assert!(
            error
                .to_string()
                .contains("no unambiguous authenticated reverse tunnel is active")
        );
        assert_eq!(state.pending_tcp_len(), 0);
    }

    #[tokio::test]
    async fn stale_heartbeat_session_is_rejected_and_cleaned_up() {
        let state = ReverseTunnelServerState::default();
        let session_id = Uuid::new_v4();
        let mut control = register_session(&state, "phone-a", session_id).await;
        state
            .set_session_last_seen(
                "phone-a",
                session_id,
                Instant::now() - state.heartbeat_timeout - Duration::from_millis(1),
            )
            .await;

        assert!(!state.has_active_session(Some("phone-a")).await);
        assert!(state.tcp_controls.lock().await.is_empty());
        assert!(
            state
                .sessions
                .lock()
                .await
                .get("phone-a")
                .is_some_and(|session| !session.connected)
        );
        assert!(control.recv().await.is_none());
    }

    #[tokio::test]
    async fn fresh_session_remains_selectable() {
        let state = ReverseTunnelServerState::default();
        let session_id = Uuid::new_v4();
        let _control = register_session(&state, "phone-a", session_id).await;

        assert!(state.has_active_session(Some("phone-a")).await);
        assert!(state.select_tcp_control(Some("phone-a")).await.is_some());
    }

    #[tokio::test]
    async fn heartbeat_refresh_requires_matching_live_transport() {
        let state = ReverseTunnelServerState::default();
        let session_id = Uuid::new_v4();
        let control = register_session(&state, "phone-a", session_id).await;
        state
            .set_session_last_seen(
                "phone-a",
                session_id,
                Instant::now() - state.heartbeat_timeout - Duration::from_millis(1),
            )
            .await;

        assert!(state.refresh_session_heartbeat("phone-a", session_id).await);
        assert!(state.has_active_session(Some("phone-a")).await);

        drop(control);
        state
            .remove_tcp_control_for_session("phone-a", session_id)
            .await;
        assert!(!state.refresh_session_heartbeat("phone-a", session_id).await);
    }

    #[tokio::test]
    async fn pending_request_is_rejected_when_heartbeat_becomes_stale() {
        let state = ReverseTunnelServerState::default();
        let session_id = Uuid::new_v4();
        let mut control = register_session(&state, "phone-a", session_id).await;
        let request = spawn_request(&state, "phone-a").await;
        let stream_id = open_stream_id(&mut control).await;
        state
            .set_session_last_seen(
                "phone-a",
                session_id,
                Instant::now() - state.heartbeat_timeout - Duration::from_millis(1),
            )
            .await;
        let (incoming, peer) = tcp_pair().await;

        assert_eq!(
            state
                .accept_tcp_proxy_stream("phone-a", session_id, stream_id, incoming)
                .await,
            Err(TcpProxyStreamRejection::SessionInactive)
        );
        assert_eq!(state.pending_tcp_len(), 0);
        assert!(request.await.expect("request task must finish").is_err());
        assert!(state.tcp_controls.lock().await.is_empty());
        assert!(control.recv().await.is_none());
        drop(peer);
    }

    #[tokio::test]
    async fn stale_session_cannot_create_pending_request() {
        let state = ReverseTunnelServerState::default();
        let session_id = Uuid::new_v4();
        let _control = register_session(&state, "phone-a", session_id).await;
        state
            .set_session_last_seen(
                "phone-a",
                session_id,
                Instant::now() - state.heartbeat_timeout - Duration::from_millis(1),
            )
            .await;

        let error = state
            .open_tcp_proxy_with_timeout(Some("phone-a"), Duration::from_millis(10))
            .await
            .expect_err("stale session must not receive a pending request");
        assert!(
            error
                .to_string()
                .contains("no unambiguous authenticated reverse tunnel is active")
        );
        assert_eq!(state.pending_tcp_len(), 0);
        assert!(state.tcp_controls.lock().await.is_empty());
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

    #[test]
    fn session_bound_removal_requires_exact_session_and_authority() {
        let session_id = Uuid::new_v4();
        let authority_id = Uuid::new_v4();
        let mut entries = HashMap::from([(
            "phone-a".to_owned(),
            SessionBound {
                session_id,
                authority_id,
                value: "current",
            },
        )]);

        assert!(
            remove_session_bound(&mut entries, "phone-a", Uuid::new_v4(), authority_id,).is_none()
        );
        assert!(
            remove_session_bound(&mut entries, "phone-a", session_id, Uuid::new_v4(),).is_none()
        );
        assert_eq!(
            entries.get("phone-a").map(|entry| entry.value),
            Some("current")
        );
        assert_eq!(
            remove_session_bound(&mut entries, "phone-a", session_id, authority_id)
                .map(|entry| entry.value),
            Some("current")
        );
        assert!(entries.is_empty());
    }

    #[tokio::test]
    async fn missing_target_selects_exactly_one_active_session() {
        let state = ReverseTunnelServerState::default();
        let session_id = Uuid::new_v4();
        let mut control = register_session(&state, "phone-a", session_id).await;
        let request_state = state.clone();
        let request = tokio::spawn(async move {
            request_state
                .open_tcp_proxy_with_timeout(None, Duration::from_secs(1))
                .await
        });
        let stream_id = open_stream_id(&mut control).await;
        let (incoming, peer) = tcp_pair().await;
        state
            .accept_tcp_proxy_stream("phone-a", session_id, stream_id, incoming)
            .await
            .unwrap();
        drop(request.await.unwrap().unwrap());
        drop(peer);
    }

    #[tokio::test]
    async fn missing_target_fails_closed_when_multiple_sessions_are_active() {
        let state = ReverseTunnelServerState::default();
        let mut control_a = register_session(&state, "phone-a", Uuid::new_v4()).await;
        let mut control_b = register_session(&state, "phone-b", Uuid::new_v4()).await;

        let error = state
            .open_tcp_proxy_with_timeout(None, Duration::from_millis(20))
            .await
            .expect_err("ambiguous target must fail closed");
        assert!(error.to_string().contains("unambiguous"));
        assert_eq!(state.pending_tcp_len(), 0);
        assert!(
            tokio::time::timeout(Duration::from_millis(20), control_a.recv())
                .await
                .is_err()
        );
        assert!(
            tokio::time::timeout(Duration::from_millis(20), control_b.recv())
                .await
                .is_err()
        );
    }

    #[tokio::test]
    async fn explicit_target_never_falls_back_to_another_node() {
        let state = ReverseTunnelServerState::default();
        let session_a = Uuid::new_v4();
        let session_b = Uuid::new_v4();
        let mut control_a = register_session(&state, "phone-a", session_a).await;
        let mut control_b = register_session(&state, "phone-b", session_b).await;
        let request = spawn_request(&state, "phone-b").await;
        let stream_id = open_stream_id(&mut control_b).await;
        assert!(
            tokio::time::timeout(Duration::from_millis(20), control_a.recv())
                .await
                .is_err()
        );
        let (incoming, peer) = tcp_pair().await;
        state
            .accept_tcp_proxy_stream("phone-b", session_b, stream_id, incoming)
            .await
            .unwrap();
        drop(request.await.unwrap().unwrap());
        drop(peer);
    }

    #[tokio::test]
    async fn old_authority_cannot_refresh_or_disconnect_replacement() {
        let state = ReverseTunnelServerState::default();
        let session_id = Uuid::new_v4();
        let (old_sender, _old_receiver) = mpsc::channel(4);
        let old_authority = state
            .replace_session_authority(
                "phone-a".to_owned(),
                session_id,
                SessionAuthority::Tcp(old_sender),
            )
            .await;
        let (new_sender, _new_receiver) = mpsc::channel(4);
        let new_authority = state
            .replace_session_authority(
                "phone-a".to_owned(),
                session_id,
                SessionAuthority::Tcp(new_sender),
            )
            .await;

        assert_ne!(old_authority, new_authority);
        assert!(
            !state
                .refresh_session_heartbeat_for_authority("phone-a", session_id, old_authority,)
                .await
        );
        assert!(
            state
                .refresh_session_heartbeat_for_authority("phone-a", session_id, new_authority,)
                .await
        );
        assert!(
            !state
                .disconnect_session_authority(
                    "phone-a",
                    session_id,
                    old_authority,
                    b"late disconnect",
                )
                .await
        );
        assert_eq!(
            state
                .select_active_target(Some("phone-a"))
                .await
                .map(|target| target.authority_id),
            Some(new_authority)
        );
    }

    async fn register_session(
        state: &ReverseTunnelServerState,
        node_id: &str,
        session_id: Uuid,
    ) -> mpsc::Receiver<ServerFrame> {
        state
            .register_session_liveness(node_id.to_owned(), session_id)
            .await;
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
                expected_authority_id: session_id,
                created_at,
                deadline: created_at + Duration::from_secs(60),
                response_sender,
            },
        );
    }
}
