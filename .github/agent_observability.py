from pathlib import Path
import subprocess


def replace_once(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text()
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{path}: expected exactly one match, found {count}")
    file.write_text(text.replace(old, new, 1))


def replace_first(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text()
    count = text.count(old)
    if count < 1:
        raise RuntimeError(f"{path}: expected at least one match")
    file.write_text(text.replace(old, new, 1))


replace_once(
    "crates/reverse-tunnel/src/model.rs",
    '''#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ClientSnapshot {
    pub session_id: Uuid,
    pub connected: bool,
    pub attempts: u64,
    pub sent_heartbeats: u64,
    pub last_error: Option<String>,
}
impl ClientSnapshot {
    pub(crate) fn new(session_id: Uuid) -> Self {
        Self {
            session_id,
            connected: false,
            attempts: 0,
            sent_heartbeats: 0,
            last_error: None,
        }
    }
}
''',
    '''#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum TunnelActiveTransport {
    Tcp,
    Quic,
    TlsTcp,
}

impl TunnelActiveTransport {
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::Tcp => "tcp",
            Self::Quic => "quic",
            Self::TlsTcp => "tls_tcp",
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum TunnelFreshness {
    Unknown,
    Fresh,
    Stale,
}

impl TunnelFreshness {
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::Unknown => "unknown",
            Self::Fresh => "fresh",
            Self::Stale => "stale",
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum TunnelFailoverReason {
    ConnectTimeout,
    ConnectFailed,
    AuthenticationFailed,
    SessionClosed,
    SessionError,
}

impl TunnelFailoverReason {
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::ConnectTimeout => "connect_timeout",
            Self::ConnectFailed => "connect_failed",
            Self::AuthenticationFailed => "authentication_failed",
            Self::SessionClosed => "session_closed",
            Self::SessionError => "session_error",
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ClientSnapshot {
    pub session_id: Uuid,
    pub connected: bool,
    pub attempts: u64,
    pub sent_heartbeats: u64,
    pub last_error: Option<String>,
    pub active_transport: Option<TunnelActiveTransport>,
    pub freshness: TunnelFreshness,
    pub last_failover_reason: Option<TunnelFailoverReason>,
}
impl ClientSnapshot {
    pub(crate) fn new(session_id: Uuid) -> Self {
        Self {
            session_id,
            connected: false,
            attempts: 0,
            sent_heartbeats: 0,
            last_error: None,
            active_transport: None,
            freshness: TunnelFreshness::Unknown,
            last_failover_reason: None,
        }
    }
}
'''
)
replace_once(
    "crates/reverse-tunnel/src/model.rs",
    "    use super::TunnelTransport;\n",
    '''    use super::{
        TunnelActiveTransport, TunnelFailoverReason, TunnelFreshness, TunnelTransport,
    };
'''
)
replace_once(
    "crates/reverse-tunnel/src/model.rs",
    '''    fn hybrid_transport_is_explicitly_quic_first() {
        let transport = TunnelTransport::Hybrid {
            server_name: "relay.example".to_string(),
            server_cert_der: vec![1],
            server_key_der: None,
        };

        assert!(transport.is_quic_first());
        assert!(!TunnelTransport::Tcp.is_quic_first());
    }
''',
    '''    fn hybrid_transport_is_explicitly_quic_first() {
        let transport = TunnelTransport::Hybrid {
            server_name: "relay.example".to_string(),
            server_cert_der: vec![1],
            server_key_der: None,
        };

        assert!(transport.is_quic_first());
        assert!(!TunnelTransport::Tcp.is_quic_first());
    }

    #[test]
    fn tunnel_observability_values_are_bounded_and_serializable() {
        assert_eq!(
            serde_json::to_string(&TunnelActiveTransport::TlsTcp).unwrap(),
            r#""tls_tcp""#
        );
        assert_eq!(
            serde_json::to_string(&TunnelFreshness::Fresh).unwrap(),
            r#""fresh""#
        );
        assert_eq!(
            serde_json::to_string(&TunnelFailoverReason::ConnectTimeout).unwrap(),
            r#""connect_timeout""#
        );
        assert_eq!(TunnelActiveTransport::Quic.as_str(), "quic");
        assert_eq!(TunnelFreshness::Stale.as_str(), "stale");
        assert_eq!(
            TunnelFailoverReason::AuthenticationFailed.as_str(),
            "authentication_failed"
        );
    }
'''
)
replace_once(
    "crates/reverse-tunnel/src/tunnel.rs",
    '''        if *shutdown.borrow() {
            let _ = status.send(snapshot);
            return;
        }

        snapshot.connected = false;
        snapshot.attempts += 1;
        let _ = status.send(snapshot.clone());

        match connect_and_pump(&config, session_id, &mut shutdown, &mut snapshot, &status).await {
            Ok(()) => {
                snapshot.connected = false;
                snapshot.last_error = None;
                backoff = config.reconnect_floor;
            }
            Err(err) => {
                let had_connected_session = snapshot.connected;
                snapshot.connected = false;
                snapshot.last_error = Some(format!("{err:#}"));
                let _ = status.send(snapshot.clone());
''',
    '''        if *shutdown.borrow() {
            snapshot.connected = false;
            snapshot.active_transport = None;
            snapshot.freshness = TunnelFreshness::Stale;
            let _ = status.send(snapshot);
            return;
        }

        snapshot.connected = false;
        snapshot.active_transport = None;
        snapshot.freshness = TunnelFreshness::Unknown;
        snapshot.attempts += 1;
        let _ = status.send(snapshot.clone());

        match connect_and_pump(&config, session_id, &mut shutdown, &mut snapshot, &status).await {
            Ok(()) => {
                snapshot.connected = false;
                snapshot.active_transport = None;
                snapshot.freshness = TunnelFreshness::Stale;
                snapshot.last_error = None;
                let _ = status.send(snapshot.clone());
                backoff = config.reconnect_floor;
            }
            Err(err) => {
                let had_connected_session = snapshot.connected;
                snapshot.connected = false;
                snapshot.active_transport = None;
                snapshot.freshness = TunnelFreshness::Stale;
                snapshot.last_error = Some(format!("{err:#}"));
                let _ = status.send(snapshot.clone());
'''
)
replace_once(
    "crates/reverse-tunnel/src/tunnel.rs",
    '''            Err(error) => {
                warn!(
                    node_id = %config.node_id,
                    from_transport = "quic",
                    to_transport = "tls_tcp",
                    reason = quic_failover_reason(&error),
                    "reverse tunnel transport failover"
                );
            }
''',
    '''            Err(error) => {
                let reason = record_quic_failover(snapshot, &error, status);
                warn!(
                    node_id = %config.node_id,
                    from_transport = "quic",
                    to_transport = "tls_tcp",
                    reason = reason.as_str(),
                    "reverse tunnel transport failover"
                );
            }
'''
)
replace_once(
    "crates/reverse-tunnel/src/tunnel.rs",
    '''    write_frame(&mut writer, &hello).await?;

    snapshot.connected = true;
    snapshot.last_error = None;
    let _ = status.send(snapshot.clone());
    let mut sequence = snapshot.sent_heartbeats;
''',
    '''    write_frame(&mut writer, &hello).await?;

    mark_snapshot_connected(snapshot, TunnelActiveTransport::Tcp, false);
    let _ = status.send(snapshot.clone());
    let mut sequence = snapshot.sent_heartbeats;
'''
)
replace_once(
    "crates/reverse-tunnel/src/tunnel.rs",
    '''fn quic_failover_reason(error: &anyhow::Error) -> &'static str {
    let message = error.to_string();
    if message.contains("timed out") {
        "connect_timeout"
    } else if message.contains("connect failed") {
        "connect_failed"
    } else if message.contains("authentication") {
        "authentication_failed"
    } else if message.contains("closed") {
        "session_closed"
    } else {
        "session_error"
    }
}
''',
    '''fn mark_snapshot_connected(
    snapshot: &mut ClientSnapshot,
    transport: TunnelActiveTransport,
    preserve_failover_reason: bool,
) {
    snapshot.connected = true;
    snapshot.active_transport = Some(transport);
    snapshot.freshness = TunnelFreshness::Fresh;
    snapshot.last_error = None;
    if !preserve_failover_reason {
        snapshot.last_failover_reason = None;
    }
}

fn record_quic_failover(
    snapshot: &mut ClientSnapshot,
    error: &anyhow::Error,
    status: &watch::Sender<ClientSnapshot>,
) -> TunnelFailoverReason {
    let reason = quic_failover_reason(error);
    snapshot.connected = false;
    snapshot.active_transport = None;
    snapshot.freshness = TunnelFreshness::Unknown;
    snapshot.last_failover_reason = Some(reason);
    let _ = status.send(snapshot.clone());
    reason
}

fn quic_failover_reason(error: &anyhow::Error) -> TunnelFailoverReason {
    let message = error.to_string();
    if message.contains("timed out") {
        TunnelFailoverReason::ConnectTimeout
    } else if message.contains("connect failed") {
        TunnelFailoverReason::ConnectFailed
    } else if message.contains("authentication") {
        TunnelFailoverReason::AuthenticationFailed
    } else if message.contains("closed") {
        TunnelFailoverReason::SessionClosed
    } else {
        TunnelFailoverReason::SessionError
    }
}
'''
)
replace_once(
    "crates/reverse-tunnel/src/tunnel.rs",
    '''    .await?;
    snapshot.connected = true;
    snapshot.last_error = None;
    let _ = status.send(snapshot.clone());
    let mut sequence = snapshot.sent_heartbeats;
    loop {
''',
    '''    .await?;
    mark_snapshot_connected(snapshot, TunnelActiveTransport::TlsTcp, true);
    let _ = status.send(snapshot.clone());
    let mut sequence = snapshot.sent_heartbeats;
    loop {
'''
)
replace_once(
    "crates/reverse-tunnel/src/tunnel.rs",
    '''    write_frame(&mut send, &hello).await?;

    snapshot.connected = true;
    snapshot.last_error = None;
    let _ = status.send(snapshot.clone());
    let mut sequence = snapshot.sent_heartbeats;
''',
    '''    write_frame(&mut send, &hello).await?;

    mark_snapshot_connected(snapshot, TunnelActiveTransport::Quic, false);
    let _ = status.send(snapshot.clone());
    let mut sequence = snapshot.sent_heartbeats;
'''
)
replace_once(
    "crates/reverse-tunnel/src/tunnel.rs",
    '''    #[tokio::test]
    async fn client_reconnects_after_server_drops_connection() {
''',
    '''    #[test]
    fn failover_observability_is_bounded_and_preserved_by_tls_fallback() {
        let mut snapshot = ClientSnapshot::new(Uuid::new_v4());
        mark_snapshot_connected(&mut snapshot, TunnelActiveTransport::Quic, false);
        let (status_tx, status_rx) = watch::channel(snapshot.clone());

        let reason = record_quic_failover(
            &mut snapshot,
            &anyhow::anyhow!("QUIC connect timed out"),
            &status_tx,
        );
        assert_eq!(reason, TunnelFailoverReason::ConnectTimeout);
        assert_eq!(
            status_rx.borrow().last_failover_reason,
            Some(TunnelFailoverReason::ConnectTimeout)
        );
        assert_eq!(status_rx.borrow().freshness, TunnelFreshness::Unknown);

        mark_snapshot_connected(&mut snapshot, TunnelActiveTransport::TlsTcp, true);
        assert_eq!(
            snapshot.last_failover_reason,
            Some(TunnelFailoverReason::ConnectTimeout)
        );
        assert_eq!(
            snapshot.active_transport,
            Some(TunnelActiveTransport::TlsTcp)
        );
        assert_eq!(snapshot.freshness, TunnelFreshness::Fresh);

        mark_snapshot_connected(&mut snapshot, TunnelActiveTransport::Quic, false);
        assert_eq!(snapshot.last_failover_reason, None);
    }

    #[test]
    fn failover_reason_never_exposes_raw_error_text() {
        assert_eq!(
            quic_failover_reason(&anyhow::anyhow!("credential=secret internal detail")),
            TunnelFailoverReason::SessionError
        );
        assert_eq!(
            quic_failover_reason(&anyhow::anyhow!("authentication rejected")),
            TunnelFailoverReason::AuthenticationFailed
        );
    }

    #[tokio::test]
    async fn client_reconnects_after_server_drops_connection() {
'''
)
replace_once(
    "crates/reverse-tunnel/src/tunnel.rs",
    '''        wait_for_heartbeat_with_status(&state, status_rx.clone()).await;
        let sessions = state.snapshot().await;
''',
    '''        wait_for_heartbeat_with_status(&state, status_rx.clone()).await;
        let client_snapshot = status_rx.borrow().clone();
        assert_eq!(
            client_snapshot.active_transport,
            Some(TunnelActiveTransport::Tcp)
        );
        assert_eq!(client_snapshot.freshness, TunnelFreshness::Fresh);
        assert_eq!(client_snapshot.last_failover_reason, None);
        let sessions = state.snapshot().await;
'''
)
replace_once(
    "crates/reverse-tunnel/src/tunnel.rs",
    '''        wait_for_heartbeat(&state).await;
        let sessions = state.snapshot().await;
        assert_eq!(sessions.len(), 1);
''',
    '''        wait_for_heartbeat(&state).await;
        let client_snapshot = status_rx.borrow().clone();
        assert_eq!(
            client_snapshot.active_transport,
            Some(TunnelActiveTransport::Quic)
        );
        assert_eq!(client_snapshot.freshness, TunnelFreshness::Fresh);
        assert_eq!(client_snapshot.last_failover_reason, None);
        let sessions = state.snapshot().await;
        assert_eq!(sessions.len(), 1);
'''
)
records = "crates/proxy-core/src/records.rs"
replace_first(
    records,
    '''    pub reverse_tunnel_connected: Option<bool>,
    pub reverse_tunnel_last_error: Option<String>,
    pub tunnel_owner: Option<String>,
}
''',
    '''    pub reverse_tunnel_connected: Option<bool>,
    pub reverse_tunnel_last_error: Option<String>,
    #[serde(default)]
    pub reverse_tunnel_active_transport: Option<String>,
    #[serde(default)]
    pub reverse_tunnel_freshness: Option<String>,
    #[serde(default)]
    pub reverse_tunnel_failover_reason: Option<String>,
    pub tunnel_owner: Option<String>,
}
'''
)
replace_first(
    records,
    '''    pub reverse_tunnel_connected: Option<bool>,
    pub reverse_tunnel_last_error: Option<String>,
    pub tunnel_owner: Option<String>,
}
''',
    '''    pub reverse_tunnel_connected: Option<bool>,
    pub reverse_tunnel_last_error: Option<String>,
    #[serde(default)]
    pub reverse_tunnel_active_transport: Option<String>,
    #[serde(default)]
    pub reverse_tunnel_freshness: Option<String>,
    #[serde(default)]
    pub reverse_tunnel_failover_reason: Option<String>,
    pub tunnel_owner: Option<String>,
}
'''
)
replace_once(
    records,
    '''    pub reverse_tunnel_connected: Option<bool>,
    pub reverse_tunnel_last_error: Option<String>,
    pub tunnel_owner: Option<String>,
    pub last_heartbeat_at: Option<String>,
''',
    '''    pub reverse_tunnel_connected: Option<bool>,
    pub reverse_tunnel_last_error: Option<String>,
    #[serde(default)]
    pub reverse_tunnel_active_transport: Option<String>,
    #[serde(default)]
    pub reverse_tunnel_freshness: Option<String>,
    #[serde(default)]
    pub reverse_tunnel_failover_reason: Option<String>,
    pub tunnel_owner: Option<String>,
    pub last_heartbeat_at: Option<String>,
'''
)
replace_once(
    "services/host-daemon/src/config.rs",
    '''        reverse_tunnel_connected: None,
        reverse_tunnel_last_error: None,
        tunnel_owner: tunnel_owner.clone(),
''',
    '''        reverse_tunnel_connected: None,
        reverse_tunnel_last_error: None,
        reverse_tunnel_active_transport: None,
        reverse_tunnel_freshness: None,
        reverse_tunnel_failover_reason: None,
        tunnel_owner: tunnel_owner.clone(),
'''
)
replace_once(
    "services/host-daemon/src/reverse_tunnel.rs",
    '''            let (status_tx, status_rx) = watch::channel(ClientSnapshot {
                session_id: Uuid::nil(),
                connected: false,
                attempts: 0,
                sent_heartbeats: 0,
                last_error: None,
            });
''',
    '''            let (status_tx, status_rx) = watch::channel(ClientSnapshot {
                session_id: Uuid::nil(),
                connected: false,
                attempts: 0,
                sent_heartbeats: 0,
                last_error: None,
                active_transport: None,
                freshness: reverse_tunnel::TunnelFreshness::Unknown,
                last_failover_reason: None,
            });
'''
)
replace_once(
    "services/host-daemon/src/reverse_tunnel.rs",
    '''            runtime.health.reverse_tunnel_connected = Some(snapshot.connected);
            runtime.health.reverse_tunnel_last_error = snapshot.last_error.clone();
            runtime.reverse_tunnel = Some(snapshot.clone());
''',
    '''            runtime.health.reverse_tunnel_connected = Some(snapshot.connected);
            runtime.health.reverse_tunnel_last_error = snapshot.last_error.clone();
            runtime.health.reverse_tunnel_active_transport = snapshot
                .active_transport
                .map(|transport| transport.as_str().to_string());
            runtime.health.reverse_tunnel_freshness =
                Some(snapshot.freshness.as_str().to_string());
            runtime.health.reverse_tunnel_failover_reason = snapshot
                .last_failover_reason
                .map(|reason| reason.as_str().to_string());
            runtime.reverse_tunnel = Some(snapshot.clone());
'''
)
replace_once(
    "services/host-daemon/src/reverse_tunnel.rs",
    '''                sent_heartbeats = snapshot.sent_heartbeats,
                "reverse tunnel connected"
''',
    '''                sent_heartbeats = snapshot.sent_heartbeats,
                active_transport = snapshot.active_transport.map(|value| value.as_str()).unwrap_or("none"),
                freshness = snapshot.freshness.as_str(),
                failover_reason = snapshot.last_failover_reason.map(|value| value.as_str()).unwrap_or("none"),
                "reverse tunnel connected"
'''
)
replace_once(
    "services/host-daemon/src/reverse_tunnel.rs",
    '''                attempts = snapshot.attempts,
                error = %error,
                "reverse tunnel disconnected"
''',
    '''                attempts = snapshot.attempts,
                freshness = snapshot.freshness.as_str(),
                failover_reason = snapshot.last_failover_reason.map(|value| value.as_str()).unwrap_or("none"),
                error = %error,
                "reverse tunnel disconnected"
'''
)
replace_once(
    "services/host-daemon/src/reverse_tunnel.rs",
    '''    runtime.health.reverse_tunnel_connected = Some(false);
    runtime.health.reverse_tunnel_last_error = Some(reason.into());
    if let Some(snapshot) = runtime.reverse_tunnel.as_mut() {
        snapshot.connected = false;
        snapshot.last_error = Some(reason.into());
    }
''',
    '''    let failover_reason = runtime
        .reverse_tunnel
        .as_ref()
        .and_then(|snapshot| snapshot.last_failover_reason)
        .map(|value| value.as_str().to_string());
    runtime.health.reverse_tunnel_connected = Some(false);
    runtime.health.reverse_tunnel_last_error = Some(reason.into());
    runtime.health.reverse_tunnel_active_transport = None;
    runtime.health.reverse_tunnel_freshness = Some("stale".into());
    runtime.health.reverse_tunnel_failover_reason = failover_reason;
    if let Some(snapshot) = runtime.reverse_tunnel.as_mut() {
        snapshot.connected = false;
        snapshot.active_transport = None;
        snapshot.freshness = reverse_tunnel::TunnelFreshness::Stale;
        snapshot.last_error = Some(reason.into());
    }
'''
)
replace_once(
    "services/host-daemon/src/health.rs",
    "use proxy_core::RuntimeReadiness;\n",
    '''use proxy_core::RuntimeReadiness;
use reverse_tunnel::TunnelFreshness;
'''
)
replace_once(
    "services/host-daemon/src/health.rs",
    ".is_some_and(|snapshot| snapshot.connected);",
    '''.is_some_and(|snapshot| {
                    snapshot.connected && snapshot.freshness == TunnelFreshness::Fresh
                });'''
)
replace_once(
    "services/host-daemon/src/health.rs",
    '''        runtime.health.reverse_tunnel_last_error = runtime
            .reverse_tunnel
            .as_ref()
            .and_then(|snapshot| snapshot.last_error.clone());

        let healthy =
''',
    '''        runtime.health.reverse_tunnel_last_error = runtime
            .reverse_tunnel
            .as_ref()
            .and_then(|snapshot| snapshot.last_error.clone());
        runtime.health.reverse_tunnel_active_transport = runtime
            .reverse_tunnel
            .as_ref()
            .and_then(|snapshot| snapshot.active_transport)
            .map(|transport| transport.as_str().to_string());
        runtime.health.reverse_tunnel_freshness = runtime
            .reverse_tunnel
            .as_ref()
            .map(|snapshot| snapshot.freshness.as_str().to_string());
        runtime.health.reverse_tunnel_failover_reason = runtime
            .reverse_tunnel
            .as_ref()
            .and_then(|snapshot| snapshot.last_failover_reason)
            .map(|reason| reason.as_str().to_string());

        let healthy =
'''
)
replace_once(
    "services/host-daemon/src/control_plane.rs",
    '''        reverse_tunnel_connected: runtime.health.reverse_tunnel_connected,
        reverse_tunnel_last_error: runtime.health.reverse_tunnel_last_error.clone(),
        tunnel_owner: runtime.tunnel_owner.clone(),
''',
    '''        reverse_tunnel_connected: runtime.health.reverse_tunnel_connected,
        reverse_tunnel_last_error: runtime.health.reverse_tunnel_last_error.clone(),
        reverse_tunnel_active_transport: runtime
            .health
            .reverse_tunnel_active_transport
            .clone(),
        reverse_tunnel_freshness: runtime.health.reverse_tunnel_freshness.clone(),
        reverse_tunnel_failover_reason: runtime
            .health
            .reverse_tunnel_failover_reason
            .clone(),
        tunnel_owner: runtime.tunnel_owner.clone(),
'''
)
replace_once(
    "services/control-plane/src/projection.rs",
    '''        reverse_tunnel_connected: None,
        reverse_tunnel_last_error: None,
        tunnel_owner: req.tunnel_owner,
''',
    '''        reverse_tunnel_connected: None,
        reverse_tunnel_last_error: None,
        reverse_tunnel_active_transport: None,
        reverse_tunnel_freshness: None,
        reverse_tunnel_failover_reason: None,
        tunnel_owner: req.tunnel_owner,
'''
)
replace_once(
    "services/control-plane/src/projection.rs",
    '''        reverse_tunnel_connected: req.reverse_tunnel_connected,
        reverse_tunnel_last_error: req.reverse_tunnel_last_error,
        tunnel_owner: req.tunnel_owner,
''',
    '''        reverse_tunnel_connected: req.reverse_tunnel_connected,
        reverse_tunnel_last_error: req.reverse_tunnel_last_error,
        reverse_tunnel_active_transport: req.reverse_tunnel_active_transport,
        reverse_tunnel_freshness: req.reverse_tunnel_freshness,
        reverse_tunnel_failover_reason: req.reverse_tunnel_failover_reason,
        tunnel_owner: req.tunnel_owner,
'''
)
replace_once(
    "services/control-plane/src/routes.rs",
    '''    device.reverse_tunnel_connected = Some(false);
    device.reverse_tunnel_last_error = Some("device heartbeat is stale".into());
    device.availability = "degraded".into();
''',
    '''    device.reverse_tunnel_connected = Some(false);
    device.reverse_tunnel_last_error = Some("device heartbeat is stale".into());
    device.reverse_tunnel_active_transport = None;
    device.reverse_tunnel_freshness = Some("stale".into());
    device.availability = "degraded".into();
'''
)
replace_once(
    "services/control-plane/src/routes.rs",
    '''            reverse_tunnel_connected: None,
            reverse_tunnel_last_error: None,
            tunnel_owner: Some("stock_wireguard_bridge".into()),
''',
    '''            reverse_tunnel_connected: None,
            reverse_tunnel_last_error: None,
            reverse_tunnel_active_transport: Some("quic".into()),
            reverse_tunnel_freshness: Some("fresh".into()),
            reverse_tunnel_failover_reason: Some("connect_timeout".into()),
            tunnel_owner: Some("stock_wireguard_bridge".into()),
'''
)
replace_once(
    "services/control-plane/src/routes.rs",
    '''        assert_eq!(projected.reverse_tunnel_connected, Some(false));
        assert_eq!(
            projected.degradation_reason_code.as_deref(),
''',
    '''        assert_eq!(projected.reverse_tunnel_connected, Some(false));
        assert_eq!(projected.reverse_tunnel_active_transport, None);
        assert_eq!(
            projected.reverse_tunnel_freshness.as_deref(),
            Some("stale")
        );
        assert_eq!(
            projected.reverse_tunnel_failover_reason.as_deref(),
            Some("connect_timeout")
        );
        assert_eq!(
            projected.degradation_reason_code.as_deref(),
'''
)
workflow = subprocess.check_output(
    ["git", "show", "origin/main:.github/workflows/rust-quality.yml"],
    text=True,
)
Path(".github/workflows/rust-quality.yml").write_text(workflow)
Path(".github/agent_observability.py").unlink()
