use std::net::SocketAddr;
use std::time::Duration;

use anyhow::{Context, Result};
use base64::Engine;
use serde::{Deserialize, Serialize};
use uuid::Uuid;

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct TunnelHello {
    pub node_id: String,
    pub session_id: Uuid,
    pub protocol_version: u16,
    pub auth_token: String,
}
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct TunnelHeartbeat {
    pub node_id: String,
    pub session_id: Uuid,
    pub sequence: u64,
}
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(tag = "type")]
pub enum ClientFrame {
    Hello(TunnelHello),
    Heartbeat(TunnelHeartbeat),
    ProxyStream {
        node_id: String,
        session_id: Uuid,
        stream_id: Uuid,
        auth_token: String,
    },
}
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(tag = "type")]
pub enum ServerFrame {
    OpenProxy { stream_id: Uuid },
}

#[derive(Debug, Clone)]
pub struct ReverseTunnelClientConfig {
    pub node_id: String,
    pub server_addr: SocketAddr,
    pub tcp_fallback_addr: Option<SocketAddr>,
    pub local_proxy_addr: SocketAddr,
    pub auth_token: String,
    pub transport: TunnelTransport,
    pub connect_timeout: Duration,
    pub heartbeat_interval: Duration,
    pub reconnect_floor: Duration,
    pub reconnect_ceiling: Duration,
}
#[derive(Debug, Clone)]
pub struct ReverseTunnelServerConfig {
    pub auth_token: String,
    pub transport: TunnelTransport,
}
#[derive(Debug, Clone)]
pub enum TunnelTransport {
    Tcp,
    Quic {
        server_name: String,
        server_cert_der: Vec<u8>,
        server_key_der: Option<Vec<u8>>,
    },
    Hybrid {
        server_name: String,
        server_cert_der: Vec<u8>,
        server_key_der: Option<Vec<u8>>,
    },
}
impl TunnelTransport {
    pub fn is_quic_first(&self) -> bool {
        matches!(self, Self::Quic { .. } | Self::Hybrid { .. })
    }
}
#[derive(Debug, Clone, Copy)]
pub enum ProxyProtocol {
    Mixed,
    Socks5,
    Http,
}

pub fn decode_der_base64(raw: &str) -> Result<Vec<u8>> {
    base64::engine::general_purpose::STANDARD
        .decode(raw.trim())
        .context("failed to decode base64 DER")
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum TunnelActiveTransport {
    Tcp,
    Quic,
    TlsTcp,
}

impl TunnelActiveTransport {
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
            _ => None,
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize, Default)]
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

    pub fn same_persisted_state(&self, other: &Self) -> bool {
        self.connection_counts == other.connection_counts
            && self.transition_counts == other.transition_counts
            && self.failover_counts == other.failover_counts
            && self.disconnect_counts == other.disconnect_counts
            && self.reconnect_attempts == other.reconnect_attempts
            && self.reconnect_successes == other.reconnect_successes
            && self.ever_connected == other.ever_connected
            && self.last_successful_transport == other.last_successful_transport
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
    pub session_id: Uuid,
    pub connected: bool,
    pub attempts: u64,
    pub sent_heartbeats: u64,
    pub last_error: Option<String>,
    pub active_transport: Option<TunnelActiveTransport>,
    pub freshness: TunnelFreshness,
    pub last_failover_reason: Option<TunnelFailoverReason>,
    pub event_counters: TunnelEventCounters,
}
impl ClientSnapshot {
    #[cfg(test)]
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
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ServerSessionSnapshot {
    pub node_id: String,
    pub session_id: Uuid,
    pub connected: bool,
    pub accepted_connections: u64,
    pub last_heartbeat_sequence: Option<u64>,
}

#[cfg(test)]
mod tests {
    use super::{
        TunnelActiveTransport, TunnelDisconnectReason, TunnelEventCounters, TunnelFailoverReason,
        TunnelFreshness, TunnelTransport, TunnelTransportTransition,
    };

    #[test]
    fn hybrid_transport_is_explicitly_quic_first() {
        let transport = TunnelTransport::Hybrid {
            server_name: "relay.example".to_string(),
            server_cert_der: vec![1],
            server_key_der: None,
        };

        assert!(transport.is_quic_first());
        assert!(!TunnelTransport::Tcp.is_quic_first());
    }

    #[test]
    fn tunnel_event_counters_are_bounded_monotonic_and_idempotent_per_attempt() {
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
}
