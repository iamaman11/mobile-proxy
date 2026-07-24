from pathlib import Path


def replace_once(path: Path, old: str, new: str, label: str) -> None:
    content = path.read_text(encoding="utf-8")
    count = content.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected exactly one match, found {count}")
    path.write_text(content.replace(old, new, 1), encoding="utf-8")


state_path = Path("crates/reverse-tunnel/src/state.rs")
tunnel_path = Path("crates/reverse-tunnel/src/tunnel.rs")

replace_once(
    state_path,
    """        let connection = remove_session_bound(
            &mut self.connections.lock().await,
""",
    """        let connection = remove_session_bound(
            &mut *self.connections.lock().await,
""",
    "session-bound QUIC removal guard dereference",
)

replace_once(
    tunnel_path,
    """        mark_connected(&state, &old, None).await;
        mark_connected(&state, &new, None).await;
        mark_disconnected(&state, &old).await;
""",
    """        let (old_control_tx, _old_control_rx) = mpsc::channel(1);
        let old_authority =
            mark_connected(&state, &old, SessionAuthority::Tcp(old_control_tx)).await;
        let (new_control_tx, _new_control_rx) = mpsc::channel(1);
        let _new_authority =
            mark_connected(&state, &new, SessionAuthority::Tcp(new_control_tx)).await;
        mark_disconnected(&state, &old, old_authority).await;
""",
    "stale disconnect test authority call sites",
)

replace_once(
    tunnel_path,
    """        mark_connected(&state, &old, None).await;
        let (control_tx, mut control_rx) = mpsc::channel(1);
        state
            .register_tcp_control(old.node_id.clone(), old.session_id, control_tx)
            .await;
""",
    """        let (control_tx, mut control_rx) = mpsc::channel(1);
        let _old_authority =
            mark_connected(&state, &old, SessionAuthority::Tcp(control_tx)).await;
""",
    "pending cancellation test old authority call site",
)

replace_once(
    tunnel_path,
    """        mark_connected(&state, &new, None).await;

        let error = timeout(Duration::from_secs(1), request)
""",
    """        let (new_control_tx, _new_control_rx) = mpsc::channel(1);
        let _new_authority =
            mark_connected(&state, &new, SessionAuthority::Tcp(new_control_tx)).await;

        let error = timeout(Duration::from_secs(1), request)
""",
    "pending cancellation test new authority call site",
)
