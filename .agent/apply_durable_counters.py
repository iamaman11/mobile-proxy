from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    target = Path(path)
    body = target.read_text()
    count = body.count(old)
    if count != 1:
        raise RuntimeError(f"expected one match in {path}, found {count}: {old[:120]!r}")
    target.write_text(body.replace(old, new, 1))


def write(path: str, content: str) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content)


# reverse-tunnel bounded event model
model = "crates/reverse-tunnel/src/model.rs"
replace_once(
    model,
    '''impl TunnelActiveTransport {
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::Tcp => "tcp",
            Self::Quic => "quic",
            Self::TlsTcp => "tls_tcp",
        }
    }
}
''',
    '''impl TunnelActiveTransport {
    pub const ALL: [Self; 3] = [Self::Tcp, Self::Quic, Self::TlsTcp];

    pub const fn as_str(self) -> &'static str {
        match self {
            Self::Tcp => "tcp",
            Self::Quic => "quic",
            Self::TlsTcp => "tls_tcp",
        }
    }

    const fn index(self) -> usize {
        match self {
            Self::Tcp => 0,
            Self::Quic => 1,
            Self::TlsTcp => 2,
        }
    }
}
''',
)
replace_once(
    model,
    '''impl TunnelFailoverReason {
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
''',
    '''impl TunnelFailoverReason {
    pub const ALL: [Self; 5] = [
        Self::ConnectTimeout,
        Self::ConnectFailed,
        Self::AuthenticationFailed,
        Self::SessionClosed,
        Self::SessionError,
    ];

    pub const fn as_str(self) -> &'static str {
        match self {
            Self::ConnectTimeout => "connect_timeout",
            Self::ConnectFailed => "connect_failed",
            Self::AuthenticationFailed => "authentication_failed",
            Self::SessionClosed => "session_closed",
            Self::SessionError => "session_error",
        }
    }

    const fn index(self) -> usize {
        match self {
            Self::ConnectTimeout => 0,
            Self::ConnectFailed => 1,
            Self::AuthenticationFailed => 2,
            Self::SessionClosed => 3,
            Self::SessionError => 4,
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum TunnelDisconnectReason {
    Shutdown,
    SessionClosed,
    SessionError,
}

impl TunnelDisconnectReason {
    pub const ALL: [Self; 3] = [Self::Shutdown, Self::SessionClosed, Self::SessionError];

    pub const fn as_str(self) -> &'static str {
        match self {
            Self::Shutdown => "shutdown",
            Self::SessionClosed => "session_closed",
            Self::SessionError => "session_error",
        }
    }

    const fn index(self) -> usize {
        match self {
            Self::Shutdown => 0,
            Self::SessionClosed => 1,
            Self::SessionError => 2,
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum TunnelTransportTransition {
    NoneToTcp,
    NoneToQuic,
    NoneToTlsTcp,
    TcpToQuic,
    TcpToTlsTcp,
    QuicToTcp,
    QuicToTlsTcp,
    TlsTcpToTcp,
    TlsTcpToQuic,
}

impl TunnelTransportTransition {
    pub const ALL: [Self; 9] = [
        Self::NoneToTcp,
        Self::NoneToQuic,
        Self::NoneToTlsTcp,
        Self::TcpToQuic,
        Self::TcpToTlsTcp,
        Self::QuicToTcp,
        Self::QuicToTlsTcp,
        Self::TlsTcpToTcp,
        Self::TlsTcpToQuic,
    ];

    pub const fn from_str(self) -> &'static str {
        match self {
            Self::NoneToTcp | Self::NoneToQuic | Self::NoneToTlsTcp => "none",
            Self::TcpToQuic | Self::TcpToTlsTcp => "tcp",
            Self::QuicToTcp | Self::QuicToTlsTcp => "quic",
            Self::TlsTcpToTcp | Self::TlsTcpToQuic => "tls_tcp",
        }
    }

    pub const fn to_str(self) -> &'static str {
        match self {
            Self::NoneToTcp | Self::QuicToTcp | Self::TlsTcpToTcp => "tcp",
            Self::NoneToQuic | Self::TcpToQuic | Self::TlsTcpToQuic => "quic",
            Self::NoneToTlsTcp | Self::TcpToTlsTcp | Self::QuicToTlsTcp => "tls_tcp",
        }
    }

    const fn index(self) -> usize {
        match self {
            Self::NoneToTcp => 0,
            Self::NoneToQuic => 1,
            Self::NoneToTlsTcp => 2,
            Self::TcpToQuic => 3,
            Self::TcpToTlsTcp => 4,
            Self::QuicToTcp => 5,
            Self::QuicToTlsTcp => 6,
            Self::TlsTcpToTcp => 7,
            Self::TlsTcpToQuic => 8,
        }
    }

    const fn from_pair(
        from: Option<TunnelActiveTransport>,
        to: TunnelActiveTransport,
    ) -> Option<Self> {
        match (from, to) {
            (None, TunnelActiveTransport::Tcp) => Some(Self::NoneToTcp),
            (None, TunnelActiveTransport::Quic) => Some(Self::NoneToQuic),
            (None, TunnelActiveTransport::TlsTcp) => Some(Self::NoneToTlsTcp),
            (Some(TunnelActiveTransport::Tcp), TunnelActiveTransport::Quic) => {
                Some(Self::TcpToQuic)
            }
            (Some(TunnelActiveTransport::Tcp), TunnelActiveTransport::TlsTcp) => {
                Some(Self::TcpToTlsTcp)
            }
            (Some(TunnelActiveTransport::Quic), TunnelActiveTransport::Tcp) => {
                Some(Self::QuicToTcp)
            }
            (Some(TunnelActiveTransport::Quic), TunnelActiveTransport::TlsTcp) => {
                Some(Self::QuicToTlsTcp)
            }
            (Some(TunnelActiveTransport::TlsTcp), TunnelActiveTransport::Tcp) => {
                Some(Self::TlsTcpToTcp)
            }
            (Some(TunnelActiveTransport::TlsTcp), TunnelActiveTransport::Quic) => {
                Some(Self::TlsTcpToQuic)
            }
            (Some(current), next) if current as u8 == next as u8 => None,
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct TunnelEventCounters {
    connection_counts: [u64; 3],
    transition_counts: [u64; 9],
    failover_counts: [u64; 5],
    disconnect_counts: [u64; 3],
    reconnect_attempts: u64,
    reconnect_successes: u64,
    ever_connected: bool,
    last_successful_transport: Option<TunnelActiveTransport>,
    #[serde(skip)]
    current_attempt_is_reconnect: bool,
    #[serde(skip)]
    connection_recorded_in_attempt: bool,
    #[serde(skip)]
    failover_recorded_in_attempt: bool,
    #[serde(skip)]
    disconnect_recorded_in_attempt: bool,
}

impl Default for TunnelEventCounters {
    fn default() -> Self {
        Self {
            connection_counts: [0; 3],
            transition_counts: [0; 9],
            failover_counts: [0; 5],
            disconnect_counts: [0; 3],
            reconnect_attempts: 0,
            reconnect_successes: 0,
            ever_connected: false,
            last_successful_transport: None,
            current_attempt_is_reconnect: false,
            connection_recorded_in_attempt: false,
            failover_recorded_in_attempt: false,
            disconnect_recorded_in_attempt: false,
        }
    }
}

impl TunnelEventCounters {
    pub fn begin_attempt(&mut self) {
        self.current_attempt_is_reconnect = self.ever_connected;
        self.connection_recorded_in_attempt = false;
        self.failover_recorded_in_attempt = false;
        self.disconnect_recorded_in_attempt = false;
        if self.current_attempt_is_reconnect {
            increment(&mut self.reconnect_attempts);
        }
    }

    pub fn record_connection(&mut self, transport: TunnelActiveTransport) {
        if self.connection_recorded_in_attempt {
            return;
        }
        increment(&mut self.connection_counts[transport.index()]);
        if let Some(transition) =
            TunnelTransportTransition::from_pair(self.last_successful_transport, transport)
        {
            increment(&mut self.transition_counts[transition.index()]);
        }
        if self.current_attempt_is_reconnect {
            increment(&mut self.reconnect_successes);
        }
        self.ever_connected = true;
        self.last_successful_transport = Some(transport);
        self.connection_recorded_in_attempt = true;
    }

    pub fn record_failover(&mut self, reason: TunnelFailoverReason) {
        if self.failover_recorded_in_attempt {
            return;
        }
        increment(&mut self.failover_counts[reason.index()]);
        self.failover_recorded_in_attempt = true;
    }

    pub fn record_disconnect(&mut self, reason: TunnelDisconnectReason) {
        if !self.connection_recorded_in_attempt || self.disconnect_recorded_in_attempt {
            return;
        }
        increment(&mut self.disconnect_counts[reason.index()]);
        self.disconnect_recorded_in_attempt = true;
    }

    pub const fn connection_count(&self, transport: TunnelActiveTransport) -> u64 {
        self.connection_counts[transport.index()]
    }

    pub const fn transition_count(&self, transition: TunnelTransportTransition) -> u64 {
        self.transition_counts[transition.index()]
    }

    pub const fn failover_count(&self, reason: TunnelFailoverReason) -> u64 {
        self.failover_counts[reason.index()]
    }

    pub const fn disconnect_count(&self, reason: TunnelDisconnectReason) -> u64 {
        self.disconnect_counts[reason.index()]
    }

    pub const fn reconnect_attempts(&self) -> u64 {
        self.reconnect_attempts
    }

    pub const fn reconnect_successes(&self) -> u64 {
        self.reconnect_successes
    }
}

fn increment(value: &mut u64) {
    *value = value.saturating_add(1);
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ClientSnapshot {
''',
)
replace_once(
    model,
    '''    pub freshness: TunnelFreshness,
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
''',
    '''    pub freshness: TunnelFreshness,
    pub last_failover_reason: Option<TunnelFailoverReason>,
    pub event_counters: TunnelEventCounters,
}
impl ClientSnapshot {
    pub(crate) fn new(session_id: Uuid) -> Self {
        Self::with_event_counters(session_id, TunnelEventCounters::default())
    }

    pub(crate) fn with_event_counters(
        session_id: Uuid,
        event_counters: TunnelEventCounters,
    ) -> Self {
        Self {
            session_id,
            connected: false,
            attempts: 0,
            sent_heartbeats: 0,
            last_error: None,
            active_transport: None,
            freshness: TunnelFreshness::Unknown,
            last_failover_reason: None,
            event_counters,
        }
    }
}
''',
)
replace_once(
    model,
    '''    use super::{TunnelActiveTransport, TunnelFailoverReason, TunnelFreshness, TunnelTransport};
''',
    '''    use super::{
        TunnelActiveTransport, TunnelDisconnectReason, TunnelEventCounters, TunnelFailoverReason,
        TunnelFreshness, TunnelTransport, TunnelTransportTransition,
    };
''',
)
replace_once(
    model,
    '''    fn tunnel_observability_values_are_bounded_and_serializable() {
''',
    '''    fn tunnel_event_counters_are_bounded_monotonic_and_idempotent_per_attempt() {
        let mut counters = TunnelEventCounters::default();
        counters.begin_attempt();
        counters.record_connection(TunnelActiveTransport::Tcp);
        counters.record_connection(TunnelActiveTransport::Tcp);
        assert_eq!(counters.connection_count(TunnelActiveTransport::Tcp), 1);
        assert_eq!(
            counters.transition_count(TunnelTransportTransition::NoneToTcp),
            1
        );

        counters.record_disconnect(TunnelDisconnectReason::SessionClosed);
        counters.record_disconnect(TunnelDisconnectReason::SessionClosed);
        assert_eq!(
            counters.disconnect_count(TunnelDisconnectReason::SessionClosed),
            1
        );

        counters.begin_attempt();
        counters.record_failover(TunnelFailoverReason::ConnectTimeout);
        counters.record_failover(TunnelFailoverReason::ConnectTimeout);
        counters.record_connection(TunnelActiveTransport::TlsTcp);
        assert_eq!(counters.reconnect_attempts(), 1);
        assert_eq!(counters.reconnect_successes(), 1);
        assert_eq!(
            counters.failover_count(TunnelFailoverReason::ConnectTimeout),
            1
        );
        assert_eq!(
            counters.transition_count(TunnelTransportTransition::TcpToTlsTcp),
            1
        );
    }

    #[test]
    fn tunnel_observability_values_are_bounded_and_serializable() {
''',
)

# reverse-tunnel authoritative lifecycle increments
path = "crates/reverse-tunnel/src/tunnel.rs"
replace_once(
    path,
    '''pub async fn run_client(
    config: ReverseTunnelClientConfig,
    mut shutdown: watch::Receiver<bool>,
    status: watch::Sender<ClientSnapshot>,
) {
    let session_id = Uuid::new_v4();
    let mut snapshot = ClientSnapshot::new(session_id);
    let mut backoff = config.reconnect_floor;

    loop {
        if *shutdown.borrow() {
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
                if had_connected_session {
                    backoff = config.reconnect_floor;
                }
                if sleep_or_shutdown(backoff, &mut shutdown).await {
                    return;
                }
                backoff = next_backoff(backoff, config.reconnect_ceiling);
            }
        }
    }
}
''',
    '''pub async fn run_client(
    config: ReverseTunnelClientConfig,
    shutdown: watch::Receiver<bool>,
    status: watch::Sender<ClientSnapshot>,
) {
    run_client_with_counters(
        config,
        shutdown,
        status,
        TunnelEventCounters::default(),
    )
    .await;
}

pub async fn run_client_with_counters(
    config: ReverseTunnelClientConfig,
    mut shutdown: watch::Receiver<bool>,
    status: watch::Sender<ClientSnapshot>,
    initial_event_counters: TunnelEventCounters,
) {
    let session_id = Uuid::new_v4();
    let mut snapshot = ClientSnapshot::with_event_counters(session_id, initial_event_counters);
    let mut backoff = config.reconnect_floor;

    loop {
        if *shutdown.borrow() {
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
        snapshot.event_counters.begin_attempt();
        let _ = status.send(snapshot.clone());

        match connect_and_pump(&config, session_id, &mut shutdown, &mut snapshot, &status).await {
            Ok(()) => {
                if snapshot.connected {
                    snapshot
                        .event_counters
                        .record_disconnect(TunnelDisconnectReason::Shutdown);
                }
                snapshot.connected = false;
                snapshot.active_transport = None;
                snapshot.freshness = TunnelFreshness::Stale;
                snapshot.last_error = None;
                let _ = status.send(snapshot.clone());
                backoff = config.reconnect_floor;
            }
            Err(err) => {
                let had_connected_session = snapshot.connected;
                if had_connected_session {
                    snapshot
                        .event_counters
                        .record_disconnect(disconnect_reason(&err));
                }
                snapshot.connected = false;
                snapshot.active_transport = None;
                snapshot.freshness = TunnelFreshness::Stale;
                snapshot.last_error = Some(format!("{err:#}"));
                let _ = status.send(snapshot.clone());
                if had_connected_session {
                    backoff = config.reconnect_floor;
                }
                if sleep_or_shutdown(backoff, &mut shutdown).await {
                    return;
                }
                backoff = next_backoff(backoff, config.reconnect_ceiling);
            }
        }
    }
}
''',
)
replace_once(
    path,
    '''    snapshot.connected = true;
    snapshot.active_transport = Some(transport);
''',
    '''    snapshot.event_counters.record_connection(transport);
    snapshot.connected = true;
    snapshot.active_transport = Some(transport);
''',
)
replace_once(
    path,
    '''    snapshot.last_failover_reason = Some(reason);
    let _ = status.send(snapshot.clone());
''',
    '''    snapshot.last_failover_reason = Some(reason);
    snapshot.event_counters.record_failover(reason);
    let _ = status.send(snapshot.clone());
''',
)
replace_once(
    path,
    '''fn quic_failover_reason(error: &anyhow::Error) -> TunnelFailoverReason {
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
''',
    '''fn quic_failover_reason(error: &anyhow::Error) -> TunnelFailoverReason {
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

fn disconnect_reason(error: &anyhow::Error) -> TunnelDisconnectReason {
    if error.to_string().contains("closed") {
        TunnelDisconnectReason::SessionClosed
    } else {
        TunnelDisconnectReason::SessionError
    }
}
''',
)
replace_once(
    path,
    '''        assert_eq!(reason, TunnelFailoverReason::ConnectTimeout);
''',
    '''        assert_eq!(reason, TunnelFailoverReason::ConnectTimeout);
        assert_eq!(
            snapshot
                .event_counters
                .failover_count(TunnelFailoverReason::ConnectTimeout),
            1
        );
''',
)
replace_once(
    path,
    '''        assert_eq!(client_snapshot.last_failover_reason, None);
        let sessions = state.snapshot().await;
''',
    '''        assert_eq!(client_snapshot.last_failover_reason, None);
        assert_eq!(
            client_snapshot
                .event_counters
                .connection_count(TunnelActiveTransport::Tcp),
            1
        );
        assert_eq!(
            client_snapshot
                .event_counters
                .transition_count(TunnelTransportTransition::NoneToTcp),
            1
        );
        let sessions = state.snapshot().await;
''',
)
# The second occurrence is the QUIC lifecycle test.
replace_once(
    path,
    '''        assert_eq!(client_snapshot.last_failover_reason, None);
        let sessions = state.snapshot().await;
''',
    '''        assert_eq!(client_snapshot.last_failover_reason, None);
        assert_eq!(
            client_snapshot
                .event_counters
                .connection_count(TunnelActiveTransport::Quic),
            1
        );
        assert_eq!(
            client_snapshot
                .event_counters
                .transition_count(TunnelTransportTransition::NoneToQuic),
            1
        );
        let sessions = state.snapshot().await;
''',
)
replace_once(
    path,
    '''        let frames = received.lock().await;
        assert_eq!(frames.len(), 2);
''',
    '''        let final_snapshot = status_rx.borrow().clone();
        assert_eq!(
            final_snapshot
                .event_counters
                .connection_count(TunnelActiveTransport::Tcp),
            2
        );
        assert_eq!(final_snapshot.event_counters.reconnect_attempts(), 1);
        assert_eq!(final_snapshot.event_counters.reconnect_successes(), 1);

        let frames = received.lock().await;
        assert_eq!(frames.len(), 2);
''',
)

replace_once(
    "crates/reverse-tunnel/src/lib.rs",
    '''pub use tunnel::{run_client, run_quic_server, run_quic_tcp_forward_listener, run_server};
''',
    '''pub use tunnel::{
    run_client, run_client_with_counters, run_quic_server, run_quic_tcp_forward_listener,
    run_server,
};
''',
)

# Hybrid process proof carries exact event assertions.
hybrid = "crates/reverse-tunnel/tests/hybrid_tls_fallback.rs"
replace_once(
    hybrid,
    '''    TunnelTransport, run_client, run_quic_tcp_forward_listener, run_server,
''',
    '''    TunnelTransport, TunnelTransportTransition, run_client, run_quic_tcp_forward_listener,
    run_server,
''',
)
replace_once(
    hybrid,
    '''        freshness: TunnelFreshness::Unknown,
        last_failover_reason: None,
    };
''',
    '''        freshness: TunnelFreshness::Unknown,
        last_failover_reason: None,
        event_counters: reverse_tunnel::TunnelEventCounters::default(),
    };
''',
)
replace_once(
    hybrid,
    '''    assert_eq!(
        snapshot.last_failover_reason,
        Some(TunnelFailoverReason::ConnectTimeout)
    );
    assert!(state.active_connection(Some("test-phone")).await.is_none());
''',
    '''    assert_eq!(
        snapshot.last_failover_reason,
        Some(TunnelFailoverReason::ConnectTimeout)
    );
    assert_eq!(
        snapshot
            .event_counters
            .connection_count(TunnelActiveTransport::TlsTcp),
        1
    );
    assert_eq!(
        snapshot
            .event_counters
            .connection_count(TunnelActiveTransport::Quic),
        0
    );
    assert_eq!(
        snapshot
            .event_counters
            .failover_count(TunnelFailoverReason::ConnectTimeout),
        1
    );
    assert_eq!(
        snapshot
            .event_counters
            .transition_count(TunnelTransportTransition::NoneToTlsTcp),
        1
    );
    assert!(state.active_connection(Some("test-phone")).await.is_none());
''',
)

# Durable bounded host-daemon persistence adapter.
write(
    "services/host-daemon/src/tunnel_counters.rs",
    '''use std::fs::{self, File, OpenOptions};
use std::io::{ErrorKind, Write};
use std::path::{Path, PathBuf};

use anyhow::{Context, Result, bail};
use reverse_tunnel::TunnelEventCounters;
use serde::{Deserialize, Serialize};

const COUNTER_SCHEMA_VERSION: u16 = 1;
const MAX_COUNTER_FILE_BYTES: u64 = 16 * 1024;

#[derive(Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct PersistedTunnelCounters {
    schema_version: u16,
    counters: TunnelEventCounters,
}

#[derive(Debug)]
pub struct TunnelCounterStore {
    path: PathBuf,
    current: TunnelEventCounters,
}

impl TunnelCounterStore {
    pub fn load(path: PathBuf) -> Result<Self> {
        let metadata = match fs::metadata(&path) {
            Ok(metadata) => metadata,
            Err(error) if error.kind() == ErrorKind::NotFound => {
                return Ok(Self {
                    path,
                    current: TunnelEventCounters::default(),
                });
            }
            Err(error) => return Err(error).context("failed to inspect tunnel counter state"),
        };
        if metadata.len() > MAX_COUNTER_FILE_BYTES {
            bail!("tunnel counter state exceeds bounded file size");
        }
        let body = fs::read(&path).context("failed to read tunnel counter state")?;
        let persisted: PersistedTunnelCounters =
            serde_json::from_slice(&body).context("failed to decode tunnel counter state")?;
        if persisted.schema_version != COUNTER_SCHEMA_VERSION {
            bail!("unsupported tunnel counter state schema version");
        }
        Ok(Self {
            path,
            current: persisted.counters,
        })
    }

    pub fn counters(&self) -> &TunnelEventCounters {
        &self.current
    }

    pub fn persist_if_changed(&mut self, counters: &TunnelEventCounters) -> Result<bool> {
        if self.current == *counters {
            return Ok(false);
        }
        write_atomic(&self.path, counters)?;
        self.current = counters.clone();
        Ok(true)
    }
}

fn write_atomic(path: &Path, counters: &TunnelEventCounters) -> Result<()> {
    let persisted = PersistedTunnelCounters {
        schema_version: COUNTER_SCHEMA_VERSION,
        counters: counters.clone(),
    };
    let body = serde_json::to_vec(&persisted).context("failed to encode tunnel counter state")?;
    if body.len() as u64 > MAX_COUNTER_FILE_BYTES {
        bail!("encoded tunnel counter state exceeds bounded file size");
    }
    if let Some(parent) = path.parent().filter(|parent| !parent.as_os_str().is_empty()) {
        fs::create_dir_all(parent).context("failed to create tunnel counter state directory")?;
    }
    let file_name = path
        .file_name()
        .and_then(|name| name.to_str())
        .context("tunnel counter state path has no UTF-8 file name")?;
    let temporary = path.with_file_name(format!(".{file_name}.tmp-{}", std::process::id()));
    let mut file = OpenOptions::new()
        .create(true)
        .truncate(true)
        .write(true)
        .open(&temporary)
        .context("failed to create temporary tunnel counter state")?;
    file.write_all(&body)
        .context("failed to write temporary tunnel counter state")?;
    file.sync_all()
        .context("failed to sync temporary tunnel counter state")?;
    fs::rename(&temporary, path).context("failed to atomically replace tunnel counter state")?;
    #[cfg(unix)]
    if let Some(parent) = path.parent().filter(|parent| !parent.as_os_str().is_empty()) {
        File::open(parent)
            .and_then(|directory| directory.sync_all())
            .context("failed to sync tunnel counter state directory")?;
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use reverse_tunnel::{
        TunnelActiveTransport, TunnelFailoverReason, TunnelTransportTransition,
    };
    use uuid::Uuid;

    #[test]
    fn state_round_trips_atomically_and_duplicate_snapshot_does_not_rewrite() {
        let directory = std::env::temp_dir().join(format!(
            "mobile-proxy-tunnel-counter-test-{}",
            Uuid::new_v4()
        ));
        let path = directory.join("counters.json");
        let mut store = TunnelCounterStore::load(path.clone()).unwrap();
        let mut counters = TunnelEventCounters::default();
        counters.begin_attempt();
        counters.record_failover(TunnelFailoverReason::ConnectTimeout);
        counters.record_connection(TunnelActiveTransport::TlsTcp);

        assert!(store.persist_if_changed(&counters).unwrap());
        assert!(!store.persist_if_changed(&counters).unwrap());
        let reloaded = TunnelCounterStore::load(path).unwrap();
        assert_eq!(reloaded.counters(), &counters);
        assert_eq!(
            reloaded
                .counters()
                .transition_count(TunnelTransportTransition::NoneToTlsTcp),
            1
        );
        fs::remove_dir_all(directory).unwrap();
    }

    #[test]
    fn invalid_schema_fails_closed() {
        let directory = std::env::temp_dir().join(format!(
            "mobile-proxy-tunnel-counter-schema-test-{}",
            Uuid::new_v4()
        ));
        fs::create_dir_all(&directory).unwrap();
        let path = directory.join("counters.json");
        let body = serde_json::json!({
            "schema_version": 999,
            "counters": TunnelEventCounters::default(),
        });
        fs::write(&path, serde_json::to_vec(&body).unwrap()).unwrap();
        let error = TunnelCounterStore::load(path).unwrap_err();
        assert!(error.to_string().contains("unsupported"));
        fs::remove_dir_all(directory).unwrap();
    }
}
''',
)

# Runtime owns one bounded registry, never a map keyed by supplied strings.
replace_once(
    "services/host-daemon/src/state.rs",
    '''use reverse_tunnel::ClientSnapshot;
''',
    '''use reverse_tunnel::{ClientSnapshot, TunnelEventCounters};
''',
)
replace_once(
    "services/host-daemon/src/state.rs",
    '''    pub reverse_tunnel: Option<ClientSnapshot>,
    pub reverse_tunnel_restart: Option<watch::Sender<u64>>,
''',
    '''    pub reverse_tunnel: Option<ClientSnapshot>,
    pub reverse_tunnel_counters: TunnelEventCounters,
    pub reverse_tunnel_restart: Option<watch::Sender<u64>>,
''',
)
replace_once(
    "services/host-daemon/src/state.rs",
    '''            reverse_tunnel: None,
            reverse_tunnel_restart: None,
''',
    '''            reverse_tunnel: None,
            reverse_tunnel_counters: TunnelEventCounters::default(),
            reverse_tunnel_restart: None,
''',
)

write(
    "services/host-daemon/src/reverse_tunnel.rs",
    '''use std::path::PathBuf;
use std::sync::Arc;

use anyhow::Result;
use reverse_tunnel::{
    ClientSnapshot, ReverseTunnelClientConfig, TunnelEventCounters, TunnelFreshness,
    run_client_with_counters,
};
use tokio::sync::{Mutex, watch};
use tracing::{info, warn};
use uuid::Uuid;

use crate::state::SharedRuntime;
use crate::tunnel_counters::TunnelCounterStore;

type SharedCounterStore = Arc<Mutex<TunnelCounterStore>>;

pub async fn spawn_reverse_tunnel(
    runtime_arc: SharedRuntime,
    config: ReverseTunnelClientConfig,
    counter_state_path: PathBuf,
) -> Result<()> {
    let counter_store = TunnelCounterStore::load(counter_state_path)?;
    let initial_counters = counter_store.counters().clone();
    {
        let mut runtime = runtime_arc.lock().await;
        runtime.reverse_tunnel_counters = initial_counters;
    }
    let counter_store = Arc::new(Mutex::new(counter_store));
    let (restart_tx, mut restart_rx) = watch::channel(0_u64);
    {
        let mut runtime = runtime_arc.lock().await;
        runtime.reverse_tunnel_restart = Some(restart_tx);
    }

    tokio::spawn(async move {
        loop {
            let counters = counter_store.lock().await.counters().clone();
            let (shutdown_tx, shutdown_rx) = watch::channel(false);
            let (status_tx, status_rx) = watch::channel(ClientSnapshot {
                session_id: Uuid::nil(),
                connected: false,
                attempts: 0,
                sent_heartbeats: 0,
                last_error: None,
                active_transport: None,
                freshness: TunnelFreshness::Unknown,
                last_failover_reason: None,
                event_counters: counters.clone(),
            });
            let final_status = status_rx.clone();
            let mut client = tokio::spawn(run_client_with_counters(
                config.clone(),
                shutdown_rx,
                status_tx,
                counters,
            ));
            let status_forwarder = tokio::spawn(forward_status(
                runtime_arc.clone(),
                counter_store.clone(),
                status_rx,
            ));

            let disconnect_reason = tokio::select! {
                _ = restart_rx.changed() => {
                    info!("reverse tunnel restart requested");
                    let _ = shutdown_tx.send(true);
                    let _ = client.await;
                    "restart requested"
                }
                _ = &mut client => {
                    warn!("reverse tunnel client exited; restarting manager generation");
                    "reverse tunnel client exited"
                }
            };

            let snapshot = final_status.borrow().clone();
            project_snapshot(runtime_arc.clone(), counter_store.clone(), snapshot).await;
            status_forwarder.abort();
            mark_disconnected(runtime_arc.clone(), disconnect_reason).await;
        }
    });
    Ok(())
}

async fn forward_status(
    runtime_arc: SharedRuntime,
    counter_store: SharedCounterStore,
    mut status_rx: watch::Receiver<ClientSnapshot>,
) {
    while status_rx.changed().await.is_ok() {
        let snapshot = status_rx.borrow().clone();
        project_snapshot(runtime_arc.clone(), counter_store.clone(), snapshot).await;
    }
}

async fn project_snapshot(
    runtime_arc: SharedRuntime,
    counter_store: SharedCounterStore,
    snapshot: ClientSnapshot,
) {
    if let Err(error) = counter_store
        .lock()
        .await
        .persist_if_changed(&snapshot.event_counters)
    {
        warn!(error = %error, "failed to persist reverse tunnel counters");
    }
    {
        let mut runtime = runtime_arc.lock().await;
        runtime.health.reverse_tunnel_connected = Some(snapshot.connected);
        runtime.health.reverse_tunnel_last_error = snapshot.last_error.clone();
        runtime.health.reverse_tunnel_active_transport = snapshot
            .active_transport
            .map(|transport| transport.as_str().to_string());
        runtime.health.reverse_tunnel_freshness = Some(snapshot.freshness.as_str().to_string());
        runtime.health.reverse_tunnel_failover_reason = snapshot
            .last_failover_reason
            .map(|reason| reason.as_str().to_string());
        runtime.reverse_tunnel_counters = snapshot.event_counters.clone();
        runtime.reverse_tunnel = Some(snapshot.clone());
    }
    if snapshot.connected {
        info!(
            session_id = %snapshot.session_id,
            attempts = snapshot.attempts,
            sent_heartbeats = snapshot.sent_heartbeats,
            active_transport = snapshot.active_transport.map(|value| value.as_str()).unwrap_or("none"),
            freshness = snapshot.freshness.as_str(),
            failover_reason = snapshot.last_failover_reason.map(|value| value.as_str()).unwrap_or("none"),
            "reverse tunnel connected"
        );
    } else if let Some(error) = snapshot.last_error {
        warn!(
            session_id = %snapshot.session_id,
            attempts = snapshot.attempts,
            freshness = snapshot.freshness.as_str(),
            failover_reason = snapshot.last_failover_reason.map(|value| value.as_str()).unwrap_or("none"),
            error = %error,
            "reverse tunnel disconnected"
        );
    }
}

async fn mark_disconnected(runtime_arc: SharedRuntime, reason: &str) {
    let mut runtime = runtime_arc.lock().await;
    let failover_reason = runtime
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
        snapshot.freshness = TunnelFreshness::Stale;
        snapshot.last_error = Some(reason.into());
    }
}
''',
)

# Versioned state path is explicit and independent of credentials.
config = "services/host-daemon/src/config.rs"
replace_once(
    config,
    '''use std::{env, fs, net::SocketAddr, time::Duration};
''',
    '''use std::{env, fs, net::SocketAddr, path::PathBuf, time::Duration};
''',
)
replace_once(
    config,
    '''    reconnect_ceiling_ms: Option<u64>,
}
''',
    '''    reconnect_ceiling_ms: Option<u64>,
    counter_state_path: Option<String>,
}
''',
)
replace_once(
    config,
    '''    pub reverse_tunnel: Option<ReverseTunnelClientConfig>,
    pub runtime_state: RuntimeState,
''',
    '''    pub reverse_tunnel: Option<ReverseTunnelClientConfig>,
    pub reverse_tunnel_counter_state_path: Option<PathBuf>,
    pub runtime_state: RuntimeState,
''',
)
replace_once(
    config,
    '''    let reverse_tunnel = reverse_tunnel_config(file_config.as_ref(), &node_id)?;

    let health = HealthRecord {
''',
    '''    let reverse_tunnel = reverse_tunnel_config(file_config.as_ref(), &node_id)?;
    let reverse_tunnel_counter_state_path = reverse_tunnel.as_ref().map(|_| {
        file_config
            .as_ref()
            .and_then(|config| config.reverse_tunnel.as_ref())
            .and_then(|config| config.counter_state_path.clone())
            .or_else(|| env::var("HOST_DAEMON_REVERSE_TUNNEL_COUNTER_STATE_PATH").ok())
            .map(PathBuf::from)
            .unwrap_or_else(|| PathBuf::from("state/reverse-tunnel-counters-v1.json"))
    });

    let health = HealthRecord {
''',
)
replace_once(
    config,
    '''        reverse_tunnel,
        runtime_state: RuntimeState::new(
''',
    '''        reverse_tunnel,
        reverse_tunnel_counter_state_path,
        runtime_state: RuntimeState::new(
''',
)

main = "services/host-daemon/src/main.rs"
replace_once(main, "mod state;\n", "mod state;\nmod tunnel_counters;\n")
replace_once(
    main,
    '''    if let Some(reverse_tunnel) = loaded.reverse_tunnel {
        spawn_reverse_tunnel(state.runtime.clone(), reverse_tunnel).await;
    }
''',
    '''    if let Some(reverse_tunnel) = loaded.reverse_tunnel {
        let counter_state_path = loaded
            .reverse_tunnel_counter_state_path
            .expect("enabled reverse tunnel must have a counter state path");
        spawn_reverse_tunnel(state.runtime.clone(), reverse_tunnel, counter_state_path).await?;
    }
''',
)

# Authenticated Prometheus surface keeps gauges and adds exact bounded families.
write(
    "services/host-daemon/src/api.rs",
    '''use std::fmt::Write as _;

use axum::{
    Json, Router,
    extract::{Path, State},
    http::{HeaderMap, header::CONTENT_TYPE},
    response::IntoResponse,
    routing::{get, post},
};
use proxy_core::{HealthRecord, JobRecord, ProxyRuntimeRecord, RotateRequest, RuntimeStatusRecord};
use reverse_tunnel::{
    TunnelActiveTransport, TunnelDisconnectReason, TunnelEventCounters, TunnelFailoverReason,
    TunnelTransportTransition,
};
use uuid::Uuid;

use crate::auth::{ApiError, authorize};
use crate::rotation::start_rotation;
use crate::state::AppState;

pub fn router(state: AppState) -> Router {
    Router::new()
        .route("/v1/health", get(get_health))
        .route("/v1/metrics", get(get_metrics))
        .route("/v1/status", get(get_status))
        .route("/v1/proxy", get(get_proxy))
        .route("/v1/ip/rotate", post(rotate_ip))
        .route("/v1/jobs/{id}", get(get_job))
        .with_state(state)
}

async fn get_health(
    State(state): State<AppState>,
    headers: HeaderMap,
) -> Result<Json<HealthRecord>, ApiError> {
    authorize(&headers, &state.admin_token)?;
    let runtime = state.runtime.lock().await;
    Ok(Json(runtime.health.clone()))
}

async fn get_metrics(
    State(state): State<AppState>,
    headers: HeaderMap,
) -> Result<impl IntoResponse, ApiError> {
    authorize(&headers, &state.admin_token)?;
    let runtime = state.runtime.lock().await;
    let body = render_reverse_tunnel_metrics(
        runtime.health.reverse_tunnel_connected,
        runtime.health.reverse_tunnel_active_transport.as_deref(),
        runtime.health.reverse_tunnel_freshness.as_deref(),
        runtime.health.reverse_tunnel_failover_reason.as_deref(),
        &runtime.reverse_tunnel_counters,
    );
    Ok((
        [(CONTENT_TYPE, "text/plain; version=0.0.4; charset=utf-8")],
        body,
    ))
}

fn render_reverse_tunnel_metrics(
    connected: Option<bool>,
    active_transport: Option<&str>,
    freshness: Option<&str>,
    failover_reason: Option<&str>,
    counters: &TunnelEventCounters,
) -> String {
    const FRESHNESS: &[&str] = &["unknown", "fresh", "stale"];

    let mut output = String::new();
    writeln!(output, "# TYPE mobile_proxy_reverse_tunnel_connected gauge").unwrap();
    writeln!(
        output,
        "mobile_proxy_reverse_tunnel_connected {}",
        u8::from(connected == Some(true))
    )
    .unwrap();
    writeln!(
        output,
        "# TYPE mobile_proxy_reverse_tunnel_active_transport gauge"
    )
    .unwrap();
    for transport in TunnelActiveTransport::ALL {
        let label = transport.as_str();
        writeln!(
            output,
            r#"mobile_proxy_reverse_tunnel_active_transport{{transport="{label}"}} {}"#,
            u8::from(active_transport == Some(label))
        )
        .unwrap();
    }
    writeln!(output, "# TYPE mobile_proxy_reverse_tunnel_freshness gauge").unwrap();
    for state in FRESHNESS {
        writeln!(
            output,
            r#"mobile_proxy_reverse_tunnel_freshness{{state="{state}"}} {}"#,
            u8::from(freshness == Some(*state))
        )
        .unwrap();
    }
    writeln!(
        output,
        "# TYPE mobile_proxy_reverse_tunnel_last_failover_reason gauge"
    )
    .unwrap();
    for reason in TunnelFailoverReason::ALL {
        let label = reason.as_str();
        writeln!(
            output,
            r#"mobile_proxy_reverse_tunnel_last_failover_reason{{reason="{label}"}} {}"#,
            u8::from(failover_reason == Some(label))
        )
        .unwrap();
    }

    writeln!(
        output,
        "# TYPE mobile_proxy_reverse_tunnel_connections_total counter"
    )
    .unwrap();
    for transport in TunnelActiveTransport::ALL {
        writeln!(
            output,
            r#"mobile_proxy_reverse_tunnel_connections_total{{transport="{}"}} {}"#,
            transport.as_str(),
            counters.connection_count(transport)
        )
        .unwrap();
    }
    writeln!(
        output,
        "# TYPE mobile_proxy_reverse_tunnel_transport_transitions_total counter"
    )
    .unwrap();
    for transition in TunnelTransportTransition::ALL {
        writeln!(
            output,
            r#"mobile_proxy_reverse_tunnel_transport_transitions_total{{from="{}",to="{}"}} {}"#,
            transition.from_str(),
            transition.to_str(),
            counters.transition_count(transition)
        )
        .unwrap();
    }
    writeln!(
        output,
        "# TYPE mobile_proxy_reverse_tunnel_failovers_total counter"
    )
    .unwrap();
    for reason in TunnelFailoverReason::ALL {
        writeln!(
            output,
            r#"mobile_proxy_reverse_tunnel_failovers_total{{reason="{}"}} {}"#,
            reason.as_str(),
            counters.failover_count(reason)
        )
        .unwrap();
    }
    writeln!(
        output,
        "# TYPE mobile_proxy_reverse_tunnel_disconnects_total counter"
    )
    .unwrap();
    for reason in TunnelDisconnectReason::ALL {
        writeln!(
            output,
            r#"mobile_proxy_reverse_tunnel_disconnects_total{{reason="{}"}} {}"#,
            reason.as_str(),
            counters.disconnect_count(reason)
        )
        .unwrap();
    }
    writeln!(
        output,
        "# TYPE mobile_proxy_reverse_tunnel_reconnect_attempts_total counter"
    )
    .unwrap();
    writeln!(
        output,
        "mobile_proxy_reverse_tunnel_reconnect_attempts_total {}",
        counters.reconnect_attempts()
    )
    .unwrap();
    writeln!(
        output,
        "# TYPE mobile_proxy_reverse_tunnel_reconnect_successes_total counter"
    )
    .unwrap();
    writeln!(
        output,
        "mobile_proxy_reverse_tunnel_reconnect_successes_total {}",
        counters.reconnect_successes()
    )
    .unwrap();
    output
}

async fn get_status(
    State(state): State<AppState>,
    headers: HeaderMap,
) -> Result<Json<RuntimeStatusRecord>, ApiError> {
    authorize(&headers, &state.admin_token)?;
    let runtime = state.runtime.lock().await;
    Ok(Json(RuntimeStatusRecord {
        node_id: runtime.health.node_id.clone(),
        node_name: runtime.health.node_name.clone(),
        current_job: runtime.current_job,
        wireguard_enabled: runtime.wireguard_enabled,
        tunnel_owner: runtime.tunnel_owner.clone(),
    }))
}

async fn get_proxy(
    State(state): State<AppState>,
    headers: HeaderMap,
) -> Result<Json<ProxyRuntimeRecord>, ApiError> {
    authorize(&headers, &state.admin_token)?;
    let runtime = state.runtime.lock().await;
    Ok(Json(ProxyRuntimeRecord {
        status: runtime.health.proxy_status.clone(),
        listen_address: runtime.proxy_listen_address.clone(),
        pid: runtime.proxy_pid,
    }))
}

async fn rotate_ip(
    State(state): State<AppState>,
    headers: HeaderMap,
    Json(request): Json<RotateRequest>,
) -> Result<Json<proxy_core::RotateAccepted>, ApiError> {
    authorize(&headers, &state.admin_token)?;
    let accepted = start_rotation(&state, request).await?;
    Ok(Json(accepted))
}

async fn get_job(
    State(state): State<AppState>,
    headers: HeaderMap,
    Path(id): Path<Uuid>,
) -> Result<Json<JobRecord>, ApiError> {
    authorize(&headers, &state.admin_token)?;
    let runtime = state.runtime.lock().await;
    let job = runtime
        .jobs
        .get(&id)
        .cloned()
        .ok_or_else(|| ApiError(axum::http::StatusCode::NOT_FOUND, "job not found".into()))?;
    Ok(Json(job))
}

#[cfg(test)]
mod tests {
    use std::sync::Arc;

    use axum::extract::State;
    use axum::http::{HeaderMap, HeaderValue, StatusCode};
    use proxy_core::HealthRecord;
    use reverse_tunnel::{
        TunnelActiveTransport, TunnelDisconnectReason, TunnelEventCounters, TunnelFailoverReason,
        TunnelTransportTransition,
    };
    use tokio::sync::Mutex;

    use super::{get_metrics, render_reverse_tunnel_metrics};
    use crate::state::{AppState, RotationCommands, RuntimeState};

    #[test]
    fn tunnel_metrics_have_fixed_cardinality_and_no_raw_labels() {
        let mut counters = TunnelEventCounters::default();
        counters.begin_attempt();
        counters.record_failover(TunnelFailoverReason::ConnectTimeout);
        counters.record_connection(TunnelActiveTransport::TlsTcp);
        counters.record_disconnect(TunnelDisconnectReason::SessionClosed);
        let metrics = render_reverse_tunnel_metrics(
            Some(true),
            Some("tls_tcp"),
            Some("fresh"),
            Some("connect_timeout"),
            &counters,
        );
        assert!(
            metrics
                .contains(r#"mobile_proxy_reverse_tunnel_active_transport{transport="tls_tcp"} 1"#)
        );
        assert!(metrics.contains(r#"mobile_proxy_reverse_tunnel_freshness{state="fresh"} 1"#));
        assert!(metrics.contains(
            r#"mobile_proxy_reverse_tunnel_last_failover_reason{reason="connect_timeout"} 1"#
        ));
        assert!(metrics.contains(
            r#"mobile_proxy_reverse_tunnel_connections_total{transport="tls_tcp"} 1"#
        ));
        assert!(metrics.contains(
            r#"mobile_proxy_reverse_tunnel_transport_transitions_total{from="none",to="tls_tcp"} 1"#
        ));
        assert!(metrics.contains(
            r#"mobile_proxy_reverse_tunnel_failovers_total{reason="connect_timeout"} 1"#
        ));
        assert_eq!(
            metrics
                .lines()
                .filter(|line| line.starts_with("mobile_proxy_reverse_tunnel_connections_total{"))
                .count(),
            3
        );
        assert_eq!(
            metrics
                .lines()
                .filter(|line| line.starts_with(
                    "mobile_proxy_reverse_tunnel_transport_transitions_total{"
                ))
                .count(),
            9
        );
        assert_eq!(
            metrics
                .lines()
                .filter(|line| line.starts_with("mobile_proxy_reverse_tunnel_failovers_total{"))
                .count(),
            5
        );
        assert_eq!(
            metrics
                .lines()
                .filter(|line| line.starts_with("mobile_proxy_reverse_tunnel_disconnects_total{"))
                .count(),
            3
        );

        let untrusted = render_reverse_tunnel_metrics(
            Some(true),
            Some("credential=secret"),
            Some("arbitrary"),
            Some("raw-provider-error"),
            &counters,
        );
        assert!(!untrusted.contains("credential=secret"));
        assert!(!untrusted.contains("arbitrary"));
        assert!(!untrusted.contains("raw-provider-error"));
        assert!(!untrusted.lines().any(|line| {
            line.ends_with(" 1")
                && (line.starts_with("mobile_proxy_reverse_tunnel_active_transport{")
                    || line.starts_with("mobile_proxy_reverse_tunnel_freshness{")
                    || line.starts_with("mobile_proxy_reverse_tunnel_last_failover_reason{"))
        }));
    }

    #[test]
    fn stale_current_state_does_not_decrease_counters() {
        let mut counters = TunnelEventCounters::default();
        counters.begin_attempt();
        counters.record_connection(TunnelActiveTransport::Quic);
        let metrics = render_reverse_tunnel_metrics(
            Some(false),
            None,
            Some("stale"),
            None,
            &counters,
        );
        assert!(metrics.contains("mobile_proxy_reverse_tunnel_connected 0"));
        assert!(metrics.contains(
            r#"mobile_proxy_reverse_tunnel_active_transport{transport="quic"} 0"#
        ));
        assert!(metrics.contains(
            r#"mobile_proxy_reverse_tunnel_connections_total{transport="quic"} 1"#
        ));
        assert_eq!(
            counters.transition_count(TunnelTransportTransition::NoneToQuic),
            1
        );
    }

    #[tokio::test]
    async fn metrics_endpoint_requires_admin_authentication() {
        let state = AppState {
            admin_token: "admin-secret".into(),
            runtime: Arc::new(Mutex::new(RuntimeState::new(
                test_health(),
                false,
                None,
                "127.0.0.1:1080".into(),
                RotationCommands::default(),
                Vec::new(),
            ))),
        };
        match get_metrics(State(state.clone()), HeaderMap::new()).await {
            Err(error) => assert_eq!(error.0, StatusCode::UNAUTHORIZED),
            Ok(_) => panic!("metrics endpoint must reject missing authentication"),
        }

        let mut headers = HeaderMap::new();
        headers.insert(
            "authorization",
            HeaderValue::from_static("Bearer admin-secret"),
        );
        assert!(get_metrics(State(state), headers).await.is_ok());
    }

    fn test_health() -> HealthRecord {
        HealthRecord {
            node_id: "test-node".into(),
            node_name: "test-node".into(),
            binary_fingerprint: "test".into(),
            readiness_state: "booting".into(),
            serving: false,
            proxy_status: "starting".into(),
            last_public_ip: None,
            active_operator_profile: None,
            active_operator_plmn: None,
            last_proxy_error: None,
            serving_failure_reason: None,
            degradation_reason_code: None,
            cellular_route_ready: None,
            proxy_bind_ready: None,
            local_serving_ready: None,
            tun0_present: None,
            wg_handshake_recent: None,
            reverse_tunnel_connected: None,
            reverse_tunnel_last_error: None,
            reverse_tunnel_active_transport: None,
            reverse_tunnel_freshness: None,
            reverse_tunnel_failover_reason: None,
            tunnel_owner: None,
        }
    }
}
''',
)

write(
    "docs/operations/reverse-tunnel-event-counters.md",
    '''# Reverse tunnel event counters

## Scope

The host daemon exposes process-restart-persistent reverse-tunnel event counters through the existing authenticated `GET /v1/metrics` endpoint. The operator CLI continues to return the complete Prometheus exposition through `operator-cli metrics` without changing `operator-cli status` output.

## Authoritative boundary

The reverse-tunnel client lifecycle is the only event authority. It increments a fixed `TunnelEventCounters` value exactly where an attempt begins, a transport becomes connected, QUIC falls back, or a connected session terminates. The host daemon never reconstructs event frequency from current-state gauges and never increments a second copy. It only persists and projects the cumulative snapshot.

Each attempt has bounded duplicate guards, so repeated calls or repeated delivery of an identical snapshot cannot increment the same connection, failover or disconnect event twice. Counters use saturating `u64` increments and therefore never decrease or wrap.

## Transition model

Transitions describe changes between successful active transports, not attempted transports. The fixed inventory contains:

- `none` to `tcp`, `quic` or `tls_tcp`;
- `tcp` to `quic` or `tls_tcp`;
- `quic` to `tcp` or `tls_tcp`;
- `tls_tcp` to `tcp` or `quic`.

A first-start QUIC timeout followed by successful TLS/TCP fallback records `none -> tls_tcp` plus one `connect_timeout` failover. If a previously successful QUIC session later reconnects through TLS/TCP, it records `quic -> tls_tcp`. Reconnecting on the same transport is a connection and reconnect success, but not a transport transition.

## Persistence

The host daemon stores one schema-versioned JSON document at `reverse_tunnel.counter_state_path`, `HOST_DAEMON_REVERSE_TUNNEL_COUNTER_STATE_PATH`, or the default `state/reverse-tunnel-counters-v1.json`.

The file contains only fixed arrays, bounded enums, monotonic counters and the last successful transport. It contains no node ID, session ID, IP, hostname, token, credential, payload or free-form error. The encoded size is limited to 16 KiB. Writes use a same-directory temporary file, file sync and atomic rename. Unknown fields, invalid JSON, oversized files and unsupported schema versions fail closed during startup rather than silently resetting counters.

## Cardinality

The exposition has a compile-time upper bound:

- 3 connection series;
- 9 transition series;
- 5 QUIC failover series;
- 3 disconnect series;
- 2 label-free reconnect counters.

Current-state gauges remain unchanged. No supplied health string is interpolated into a metric label, and diagnostic failover history does not change readiness.
''',
)
