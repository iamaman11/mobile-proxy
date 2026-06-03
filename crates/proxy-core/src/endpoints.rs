use serde::{Deserialize, Serialize};

use crate::constants::{HTTP_PORT, MIXED_PORT, RELAY_IP, SOCKS5_PORT};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ProxyEndpoint {
    pub scheme: &'static str,
    pub host: &'static str,
    pub port: u16,
    pub username: Option<&'static str>,
    pub password: Option<&'static str>,
}

pub fn proxy_endpoints() -> [ProxyEndpoint; 3] {
    [
        ProxyEndpoint {
            scheme: "mixed",
            host: RELAY_IP,
            port: MIXED_PORT,
            username: None,
            password: None,
        },
        ProxyEndpoint {
            scheme: "socks5",
            host: RELAY_IP,
            port: SOCKS5_PORT,
            username: None,
            password: None,
        },
        ProxyEndpoint {
            scheme: "http",
            host: RELAY_IP,
            port: HTTP_PORT,
            username: None,
            password: None,
        },
    ]
}
