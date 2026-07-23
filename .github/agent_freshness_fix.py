from pathlib import Path
import subprocess


MAIN = Path('.github/agent_freshness.py')
FIX = Path('.github/agent_freshness_fix.py')


def main() -> None:
    script = MAIN.read_text()

    old_active = '''        let fresh = session_is_fresh(
            &self.session_liveness.lock().await,
            &selected_node,
            selected_session_id,
            now,
            self.heartbeat_timeout,
        );
        drop(sessions);'''
    new_active = '''        let liveness = self.session_liveness.lock().await;
        let fresh = session_is_fresh(
            &liveness,
            &selected_node,
            selected_session_id,
            now,
            self.heartbeat_timeout,
        );
        drop(liveness);
        drop(sessions);'''
    if script.count(old_active) != 1:
        raise RuntimeError('active-connection liveness marker was not unique')
    script = script.replace(old_active, new_active, 1)

    start = script.index("    accept_stream = '''")
    end = script.index('    state = replace_range(\n        state,\n        "    pub(crate) async fn accept_tcp_proxy_stream("', start)
    accept_block = '''    accept_stream = \'\'\'    pub(crate) async fn accept_tcp_proxy_stream(
        &self,
        node_id: &str,
        session_id: Uuid,
        stream_id: Uuid,
        stream: TcpStream,
    ) -> std::result::Result<(), TcpProxyStreamRejection> {
        let now = Instant::now();
        let (stale_node, stale_session, expire_current) = {
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
                    control.session_id == request.expected_session_id
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
                session_current,
            );
            pending.remove(&stream_id);
            stale
        };
        if expire_current {
            self.expire_session(&stale_node, stale_session).await;
        }
        Err(TcpProxyStreamRejection::SessionInactive)
    }

\'\'\'
'''
    script = script[:start] + accept_block + script[end:]

    old_cleanup = '''    for path in (".github/agent_freshness.py", ".freshness-trigger"):
        Path(path).unlink(missing_ok=True)'''
    new_cleanup = '''    for path in (
        ".github/agent_freshness.py",
        ".github/agent_freshness_fix.py",
        ".freshness-trigger",
        "clippy-error.txt",
    ):
        Path(path).unlink(missing_ok=True)'''
    if script.count(old_cleanup) != 1:
        raise RuntimeError('freshness cleanup marker was not unique')
    script = script.replace(old_cleanup, new_cleanup, 1)

    MAIN.write_text(script)
    subprocess.run(['python3', str(MAIN)], check=True)


if __name__ == '__main__':
    main()
