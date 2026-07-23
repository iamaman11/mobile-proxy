from pathlib import Path
import subprocess


STATE_PATH = Path("crates/reverse-tunnel/src/state.rs")
TUNNEL_PATH = Path("crates/reverse-tunnel/src/tunnel.rs")


def replace_range(text: str, start_marker: str, end_marker: str, replacement: str) -> str:
    start = text.index(start_marker)
    end = text.index(end_marker, start)
    return text[:start] + replacement + text[end:]


def apply_state() -> None:
    state = STATE_PATH.read_text()

    constant_marker = "const MAX_PENDING_TCP_STREAMS_PER_NODE: usize = 32;\n"
    if state.count(constant_marker) != 1:
        raise RuntimeError("per-node capacity constant marker was not unique")
    state = state.replace(
        constant_marker,
        constant_marker
        + "// Session selection tolerates multiple missed heartbeats while remaining bounded.\n"
        + "// Freshness is checked lazily on every routing/acceptance decision; no sweeper is spawned.\n"
        + "const DEFAULT_SESSION_HEARTBEAT_TIMEOUT: Duration = Duration::from_secs(30);\n\n"
        + "#[derive(Clone, Copy)]\n"
        + "pub(crate) struct SessionLiveness {\n"
        + "    session_id: Uuid,\n"
        + "    last_seen_at: Instant,\n"
        + "}\n",
        1,
    )

    old_state = '''#[derive(Clone, Default)]
pub struct ReverseTunnelServerState {
    pub(crate) sessions: Arc<Mutex<HashMap<String, ServerSessionSnapshot>>>,
    pub(crate) connections: Arc<Mutex<HashMap<String, quinn::Connection>>>,
    pub(crate) tcp_controls: Arc<Mutex<HashMap<String, TcpControlChannel>>>,
    pub(crate) pending_tcp: Arc<StdMutex<PendingTcpMap>>,
}

'''
    new_state = '''#[derive(Clone)]
pub struct ReverseTunnelServerState {
    pub(crate) sessions: Arc<Mutex<HashMap<String, ServerSessionSnapshot>>>,
    pub(crate) connections: Arc<Mutex<HashMap<String, quinn::Connection>>>,
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

'''
    if state.count(old_state) != 1:
        raise RuntimeError("server state shape was not unique")
    state = state.replace(old_state, new_state, 1)

    has_active = '''    pub async fn has_active_session(&self, node_id: Option<&str>) -> bool {
        let now = Instant::now();
        let sessions = self.sessions.lock().await;
        let liveness = self.session_liveness.lock().await;
        let connections = self.connections.lock().await;
        let controls = self.tcp_controls.lock().await;
        let mut stale = Vec::new();
        let mut active = false;

        for session in sessions.values() {
            if !session.connected || node_id.is_some_and(|expected| session.node_id != expected) {
                continue;
            }
            if !session_is_fresh(
                &liveness,
                &session.node_id,
                session.session_id,
                now,
                self.heartbeat_timeout,
            ) {
                stale.push((session.node_id.clone(), session.session_id));
                continue;
            }
            let quic_active = connections
                .get(&session.node_id)
                .is_some_and(|connection| connection.close_reason().is_none());
            let tcp_active = controls.get(&session.node_id).is_some_and(|control| {
                control.session_id == session.session_id && !control.sender.is_closed()
            });
            if quic_active || tcp_active {
                active = true;
                break;
            }
        }
        drop(controls);
        drop(connections);
        drop(liveness);
        drop(sessions);

        for (stale_node, stale_session) in stale {
            self.expire_session(&stale_node, stale_session).await;
        }
        active
    }

'''
    state = replace_range(
        state,
        "    pub async fn has_active_session(",
        "    pub(crate) async fn open_tcp_proxy(",
        has_active,
    )

    select_control = '''    async fn select_tcp_control(
        &self,
        node_id: Option<&str>,
    ) -> Option<(String, Uuid, mpsc::Sender<ServerFrame>)> {
        let now = Instant::now();
        let sessions = self.sessions.lock().await;
        let liveness = self.session_liveness.lock().await;
        let controls = self.tcp_controls.lock().await;
        let mut stale = Vec::new();

        let selected = if let Some(expected_node_id) = node_id {
            sessions
                .get(expected_node_id)
                .filter(|session| session.connected)
                .and_then(|session| {
                    if !session_is_fresh(
                        &liveness,
                        expected_node_id,
                        session.session_id,
                        now,
                        self.heartbeat_timeout,
                    ) {
                        stale.push((expected_node_id.to_owned(), session.session_id));
                        return None;
                    }
                    let control = controls
                        .get(expected_node_id)
                        .filter(|control| control.session_id == session.session_id)?;
                    Some((
                        expected_node_id.to_owned(),
                        session.session_id,
                        control.sender.clone(),
                    ))
                })
        } else {
            sessions.values().find_map(|session| {
                if !session.connected {
                    return None;
                }
                if !session_is_fresh(
                    &liveness,
                    &session.node_id,
                    session.session_id,
                    now,
                    self.heartbeat_timeout,
                ) {
                    stale.push((session.node_id.clone(), session.session_id));
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
        };
        drop(controls);
        drop(liveness);
        drop(sessions);

        for (stale_node, stale_session) in stale {
            self.expire_session(&stale_node, stale_session).await;
        }
        selected
    }

'''
    state = replace_range(
        state,
        "    async fn select_tcp_control(",
        "    pub(crate) async fn accept_tcp_proxy_stream(",
        select_control,
    )

    accept_stream = '''    pub(crate) async fn accept_tcp_proxy_stream(
        &self,
        node_id: &str,
        session_id: Uuid,
        stream_id: Uuid,
        stream: TcpStream,
    ) -> std::result::Result<(), TcpProxyStreamRejection> {
        let now = Instant::now();
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
        let session_fresh = session_current
            && session_is_fresh(
                &liveness,
                &request.expected_node_id,
                request.expected_session_id,
                now,
                self.heartbeat_timeout,
            );
        let control_active = controls
            .get(&request.expected_node_id)
            .is_some_and(|control| {
                control.session_id == request.expected_session_id && !control.sender.is_closed()
            });
        if !session_fresh || !control_active {
            let stale_node = request.expected_node_id.clone();
            let stale_session = request.expected_session_id;
            let expire_current = session_current;
            pending.remove(&stream_id);
            drop(pending);
            drop(controls);
            drop(liveness);
            drop(sessions);
            if expire_current {
                self.expire_session(&stale_node, stale_session).await;
            }
            return Err(TcpProxyStreamRejection::SessionInactive);
        }
        let request = pending
            .remove(&stream_id)
            .expect("validated pending TCP request must remain present");
        drop(pending);
        drop(controls);
        drop(liveness);
        drop(sessions);
        request
            .response_sender
            .send(stream)
            .map_err(|_| TcpProxyStreamRejection::RequesterClosed)
    }

'''
    state = replace_range(
        state,
        "    pub(crate) async fn accept_tcp_proxy_stream(",
        "    pub(crate) async fn register_tcp_control(",
        accept_stream,
    )

    helper_marker = "    pub(crate) async fn shutdown_tcp(&self) {"
    helper_methods = '''    pub(crate) async fn register_session_liveness(&self, node_id: String, session_id: Uuid) {
        self.session_liveness.lock().await.insert(
            node_id,
            SessionLiveness {
                session_id,
                last_seen_at: Instant::now(),
            },
        );
    }

    pub(crate) async fn refresh_session_heartbeat(&self, node_id: &str, session_id: Uuid) -> bool {
        let quic_active = self
            .connections
            .lock()
            .await
            .get(node_id)
            .is_some_and(|connection| connection.close_reason().is_none());
        let tcp_active = self
            .tcp_controls
            .lock()
            .await
            .get(node_id)
            .is_some_and(|control| {
                control.session_id == session_id && !control.sender.is_closed()
            });
        if !quic_active && !tcp_active {
            return false;
        }
        let mut liveness = self.session_liveness.lock().await;
        let Some(entry) = liveness
            .get_mut(node_id)
            .filter(|entry| entry.session_id == session_id)
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

    async fn expire_session(&self, node_id: &str, session_id: Uuid) {
        let should_expire = {
            let mut sessions = self.sessions.lock().await;
            let Some(session) = sessions
                .get_mut(node_id)
                .filter(|session| session.session_id == session_id)
            else {
                return;
            };
            session.connected = false;
            true
        };
        if !should_expire {
            return;
        }
        self.remove_session_liveness(node_id, session_id).await;
        if let Some(connection) = self.connections.lock().await.remove(node_id) {
            connection.close(0_u32.into(), b"heartbeat stale");
        }
        self.remove_tcp_control_for_session(node_id, session_id)
            .await;
        self.cancel_pending_for_session(node_id, session_id);
    }

'''
    if state.count(helper_marker) != 1:
        raise RuntimeError("shutdown helper marker was not unique")
    state = state.replace(helper_marker, helper_methods + helper_marker, 1)

    old_shutdown = '''    pub(crate) async fn shutdown_tcp(&self) {
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

'''
    new_shutdown = '''    pub(crate) async fn shutdown_tcp(&self) {
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

'''
    if state.count(old_shutdown) != 1:
        raise RuntimeError("shutdown implementation was not unique")
    state = state.replace(old_shutdown, new_shutdown, 1)

    active_connection = '''    pub async fn active_connection(&self, node_id: Option<&str>) -> Option<quinn::Connection> {
        let now = Instant::now();
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
        let fresh = session_is_fresh(
            &self.session_liveness.lock().await,
            &selected_node,
            selected_session_id,
            now,
            self.heartbeat_timeout,
        );
        drop(sessions);
        if !fresh {
            self.expire_session(&selected_node, selected_session_id)
                .await;
            return None;
        }

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
        if !tcp_active {
            self.expire_session(&selected_node, selected_session_id)
                .await;
        }
        None
    }

'''
    state = replace_range(
        state,
        "    pub async fn active_connection(",
        "    #[cfg(test)]\n    fn pending_tcp_len",
        active_connection,
    )

    test_helper = '''    #[cfg(test)]
    async fn set_session_last_seen(&self, node_id: &str, session_id: Uuid, last_seen_at: Instant) {
        let mut liveness = self.session_liveness.lock().await;
        let entry = liveness
            .get_mut(node_id)
            .filter(|entry| entry.session_id == session_id)
            .expect("test session liveness must exist");
        entry.last_seen_at = last_seen_at;
    }

'''
    marker = "    #[cfg(test)]\n    fn pending_tcp_len"
    if state.count(marker) != 1:
        raise RuntimeError("pending test helper marker was not unique")
    state = state.replace(marker, test_helper + marker, 1)

    freshness_fn = '''fn session_is_fresh(
    liveness: &HashMap<String, SessionLiveness>,
    node_id: &str,
    session_id: Uuid,
    now: Instant,
    heartbeat_timeout: Duration,
) -> bool {
    liveness.get(node_id).is_some_and(|entry| {
        entry.session_id == session_id
            && now.saturating_duration_since(entry.last_seen_at) <= heartbeat_timeout
    })
}

'''
    marker = "fn lock_pending(pending: &StdMutex<PendingTcpMap>)"
    if state.count(marker) != 1:
        raise RuntimeError("lock_pending marker was not unique")
    state = state.replace(marker, freshness_fn + marker, 1)

    register_marker = '''        state.sessions.lock().await.insert(
            node_id.to_owned(),'''
    register_replacement = '''        state
            .register_session_liveness(node_id.to_owned(), session_id)
            .await;
        state.sessions.lock().await.insert(
            node_id.to_owned(),'''
    if state.count(register_marker) != 1:
        raise RuntimeError("test register_session marker was not unique")
    state = state.replace(register_marker, register_replacement, 1)

    test_marker = '''    #[tokio::test]
    async fn explicit_shutdown_clears_pending_requests_and_controls() {'''
    if state.count(test_marker) != 1:
        raise RuntimeError("shutdown test marker was not unique")
    freshness_tests = '''    #[tokio::test]
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

        assert!(
            state
                .refresh_session_heartbeat("phone-a", session_id)
                .await
        );
        assert!(state.has_active_session(Some("phone-a")).await);

        drop(control);
        state
            .remove_tcp_control_for_session("phone-a", session_id)
            .await;
        assert!(
            !state
                .refresh_session_heartbeat("phone-a", session_id)
                .await
        );
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
        assert!(error.to_string().contains("no authenticated"));
        assert_eq!(state.pending_tcp_len(), 0);
        assert!(state.tcp_controls.lock().await.is_empty());
    }

'''
    state = state.replace(test_marker, freshness_tests + test_marker, 1)

    STATE_PATH.write_text(state)


def apply_tunnel() -> None:
    tunnel = TUNNEL_PATH.read_text()

    connected_marker = '''async fn mark_connected(
    state: &ReverseTunnelServerState,
    hello: &TunnelHello,
    connection: Option<quinn::Connection>,
) {
    let mut sessions = state.sessions.lock().await;'''
    connected_replacement = '''async fn mark_connected(
    state: &ReverseTunnelServerState,
    hello: &TunnelHello,
    connection: Option<quinn::Connection>,
) {
    state
        .register_session_liveness(hello.node_id.clone(), hello.session_id)
        .await;
    let mut sessions = state.sessions.lock().await;'''
    if tunnel.count(connected_marker) != 1:
        raise RuntimeError("mark_connected marker was not unique")
    tunnel = tunnel.replace(connected_marker, connected_replacement, 1)

    heartbeat = '''async fn mark_heartbeat(state: &ReverseTunnelServerState, heartbeat: &TunnelHeartbeat) {
    if !state
        .refresh_session_heartbeat(&heartbeat.node_id, heartbeat.session_id)
        .await
    {
        return;
    }
    let mut sessions = state.sessions.lock().await;
    if let Some(session) = sessions.get_mut(&heartbeat.node_id)
        && session.session_id == heartbeat.session_id
    {
        session.connected = true;
        session.last_heartbeat_sequence = Some(heartbeat.sequence);
    }
}

'''
    tunnel = replace_range(
        tunnel,
        "async fn mark_heartbeat(",
        "async fn mark_disconnected(",
        heartbeat,
    )

    cleanup_marker = '''        state
            .remove_tcp_control_for_session(&hello.node_id, hello.session_id)
            .await;
        state.cancel_pending_for_session(&hello.node_id, hello.session_id);'''
    cleanup_replacement = '''        state
            .remove_tcp_control_for_session(&hello.node_id, hello.session_id)
            .await;
        state
            .remove_session_liveness(&hello.node_id, hello.session_id)
            .await;
        state.cancel_pending_for_session(&hello.node_id, hello.session_id);'''
    if tunnel.count(cleanup_marker) != 1:
        raise RuntimeError("disconnect cleanup marker was not unique")
    tunnel = tunnel.replace(cleanup_marker, cleanup_replacement, 1)

    TUNNEL_PATH.write_text(tunnel)


def cleanup() -> None:
    for path in (".github/agent_freshness.py", ".freshness-trigger"):
        Path(path).unlink(missing_ok=True)
    subprocess.run(
        ["git", "checkout", "origin/main", "--", ".github/workflows/rust-quality.yml"],
        check=True,
    )


def main() -> None:
    apply_state()
    apply_tunnel()
    cleanup()


if __name__ == "__main__":
    main()
