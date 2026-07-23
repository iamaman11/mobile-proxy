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
    use super::{TunnelActiveTransport, TunnelFailoverReason, TunnelFreshness, TunnelTransport};

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
