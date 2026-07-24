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

for signature, label in (
    (
        "    pub(crate) async fn open_tcp_proxy(&self, node_id: Option<&str>) -> Result<TcpStream> {\n",
        "test-only open TCP proxy wrapper",
    ),
    (
        "    async fn open_tcp_proxy_with_timeout(\n",
        "test-only timeout wrapper",
    ),
    (
        "    async fn select_tcp_control(\n",
        "test-only session-only TCP selector",
    ),
    (
        "    pub(crate) async fn register_tcp_control(\n",
        "test-only TCP control registration wrapper",
    ),
    (
        "    pub(crate) async fn remove_tcp_control_for_session(&self, node_id: &str, session_id: Uuid) {\n",
        "test-only TCP control removal wrapper",
    ),
    (
        "    pub(crate) async fn register_session_liveness(&self, node_id: String, session_id: Uuid) {\n",
        "test-only liveness registration wrapper",
    ),
    (
        "    pub(crate) async fn refresh_session_heartbeat(&self, node_id: &str, session_id: Uuid) -> bool {\n",
        "test-only session-only heartbeat wrapper",
    ),
):
    replace_once(state_path, signature, "    #[cfg(test)]\n" + signature, label)

replace_once(
    state_path,
    """    pub(crate) fn cancel_pending_for_session(&self, node_id: &str, session_id: Uuid) {
        lock_pending(&self.pending_tcp).retain(|_, request| {
            request.expected_node_id != node_id || request.expected_session_id != session_id
        });
    }

""",
    "",
    "obsolete session-only pending cancellation wrapper",
)
