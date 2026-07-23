from pathlib import Path
import subprocess


STATE = Path('crates/reverse-tunnel/src/state.rs')


def main() -> None:
    state = STATE.read_text()

    start = state.index('    async fn expire_session(&self, node_id: &str, session_id: Uuid) {')
    end = state.index('    pub(crate) async fn shutdown_tcp(&self) {', start)
    expire = '''    async fn expire_session(&self, node_id: &str, session_id: Uuid) {
        {
            let mut sessions = self.sessions.lock().await;
            let Some(session) = sessions
                .get_mut(node_id)
                .filter(|session| session.session_id == session_id)
            else {
                return;
            };
            session.connected = false;
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
    state = state[:start] + expire + state[end:]

    start = state.index('    pub async fn active_connection(&self, node_id: Option<&str>)')
    end = state.index('    #[cfg(test)]\n    async fn set_session_last_seen', start)
    active_connection = '''    pub async fn active_connection(&self, node_id: Option<&str>) -> Option<quinn::Connection> {
        let now = Instant::now();
        let sessions = self.sessions.lock().await;
        let liveness = self.session_liveness.lock().await;
        let connections = self.connections.lock().await;
        let controls = self.tcp_controls.lock().await;
        let mut stale = Vec::new();
        let mut closed_connections = Vec::new();

        let selected = sessions.values().find_map(|session| {
            if !session.connected || node_id.is_some_and(|expected| session.node_id != expected) {
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
            let tcp_active = controls.get(&session.node_id).is_some_and(|control| {
                control.session_id == session.session_id && !control.sender.is_closed()
            });
            let Some(connection) = connections.get(&session.node_id) else {
                if !tcp_active {
                    stale.push((session.node_id.clone(), session.session_id));
                }
                return None;
            };
            if connection.close_reason().is_none() {
                return Some(connection.clone());
            }
            closed_connections.push(session.node_id.clone());
            if !tcp_active {
                stale.push((session.node_id.clone(), session.session_id));
            }
            None
        });
        drop(controls);
        drop(connections);
        drop(liveness);
        drop(sessions);

        if !closed_connections.is_empty() {
            let mut connections = self.connections.lock().await;
            for closed_node in closed_connections {
                if connections
                    .get(&closed_node)
                    .is_some_and(|connection| connection.close_reason().is_some())
                {
                    connections.remove(&closed_node);
                }
            }
        }
        for (stale_node, stale_session) in stale {
            self.expire_session(&stale_node, stale_session).await;
        }
        selected
    }

'''
    state = state[:start] + active_connection + state[end:]

    marker = '''    #[tokio::test]
    async fn stale_session_cannot_create_pending_request() {'''
    if state.count(marker) != 1:
        raise RuntimeError('stale request marker was not unique')
    test = '''    #[tokio::test]
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

'''
    state = state.replace(marker, test + marker, 1)
    STATE.write_text(state)

    for path in (
        '.github/agent_freshness_polish.py',
        '.freshness-polish-trigger',
    ):
        Path(path).unlink(missing_ok=True)
    subprocess.run(
        ['git', 'checkout', 'origin/main', '--', '.github/workflows/rust-quality.yml'],
        check=True,
    )


if __name__ == '__main__':
    main()
