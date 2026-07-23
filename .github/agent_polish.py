from pathlib import Path
import subprocess


def main() -> None:
    tunnel_path = Path("crates/reverse-tunnel/src/tunnel.rs")
    tunnel = tunnel_path.read_text()

    run_server_start = tunnel.index("pub async fn run_server(")
    run_server_end = tunnel.index("pub async fn run_quic_server(", run_server_start)
    run_server = '''pub async fn run_server(
    listener: TcpListener,
    config: ReverseTunnelServerConfig,
    state: ReverseTunnelServerState,
    mut shutdown: watch::Receiver<bool>,
) -> Result<()> {
    loop {
        tokio::select! {
            _ = shutdown.changed() => {
                state.shutdown_tcp().await;
                return Ok(());
            }
            accepted = listener.accept() => {
                let (stream, peer) = accepted.context("reverse tunnel accept failed")?;
                debug!(%peer, "accepted TCP reverse tunnel connection");
                let state = state.clone();
                let config = config.clone();
                tokio::spawn(async move {
                    if let Err(err) = handle_server_connection(stream, config, state).await {
                        warn!(error = %err, "TCP reverse tunnel control connection ended");
                    }
                });
            }
        }
    }
}

'''
    tunnel = tunnel[:run_server_start] + run_server + tunnel[run_server_end:]

    handler_start = tunnel.index("async fn handle_server_connection(")
    loop_start = tunnel.index("    let result = loop {", handler_start)
    loop_end = tunnel.index(
        "    state\n        .remove_tcp_control_for_session", loop_start
    )
    control_loop = '''    let result = loop {
        tokio::select! {
            frame = control_rx.recv() => {
                let Some(frame) = frame else { break Ok(()); };
                if let Err(error) = write_server_frame(&mut writer, &frame).await {
                    break Err(error);
                }
            }
            incoming = read_optional_frame(&mut reader) => match incoming {
                Ok(Some(ClientFrame::Heartbeat(heartbeat))) => {
                    mark_heartbeat(&state, &heartbeat).await;
                }
                Ok(Some(ClientFrame::Hello(_) | ClientFrame::ProxyStream { .. })) => {
                    break Err(anyhow::anyhow!(
                        "unexpected repeated hello on reverse tunnel session"
                    ));
                }
                Ok(None) => break Ok(()),
                Err(error) => break Err(error),
            }
        }
    };
'''
    tunnel = tunnel[:loop_start] + control_loop + tunnel[loop_end:]
    tunnel_path.write_text(tunnel)

    state_path = Path("crates/reverse-tunnel/src/state.rs")
    state = state_path.read_text()
    test_name = "async fn explicit_shutdown_clears_pending_requests_and_controls()"
    if test_name not in state:
        marker = '''    #[tokio::test]
    async fn pending_tcp_proxy_requests_are_globally_bounded() {'''
        if state.count(marker) != 1:
            raise RuntimeError("global capacity test marker was not unique")
        shutdown_test = '''    #[tokio::test]
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

'''
        state = state.replace(marker, shutdown_test + marker, 1)
        state_path.write_text(state)

    for temporary in (
        ".github/agent_polish.py",
        ".polish-trigger",
        ".polish-trigger2",
    ):
        Path(temporary).unlink(missing_ok=True)

    subprocess.run(
        ["git", "checkout", "origin/main", "--", ".github/workflows/rust-quality.yml"],
        check=True,
    )


if __name__ == "__main__":
    main()
