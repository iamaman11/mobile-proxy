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

#[derive(Debug, Clone, PartialEq, Eq)]
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
    use super::TunnelTransport;

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
}
