use serde::{Deserialize, Serialize};
use uuid::Uuid;

pub const RELAY_IP: &str = "34.118.26.142";
pub const MIXED_PORT: u16 = 1080;
pub const SOCKS5_PORT: u16 = 1081;
pub const HTTP_PORT: u16 = 3128;
pub const LOCAL_API: &str = "http://127.0.0.1:18088";
pub const DEVICE_ID: &str = "b4a6b2f4-5f6f-4fd1-baa4-b7d241b49a06";
pub const NODE_NAME: &str = "galaxy-a02-gcp-relay";

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ProxyEndpoint {
    pub scheme: &'static str,
    pub host: &'static str,
    pub port: u16,
    pub username: Option<&'static str>,
    pub password: Option<&'static str>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RotateRequest {
    pub strategy: String,
    pub require_public_ip_change: bool,
    pub reason: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RotateAccepted {
    pub job_id: Uuid,
    pub accepted: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct JobRecord {
    pub id: Uuid,
    pub kind: String,
    pub status: String,
    pub old_public_ip: Option<String>,
    pub new_public_ip: Option<String>,
    pub changed: Option<bool>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct HealthRecord {
    pub node_id: String,
    pub node_name: String,
    pub binary_fingerprint: String,
    pub readiness_state: String,
    pub serving: bool,
    pub proxy_status: String,
    pub last_public_ip: Option<String>,
    pub active_operator_profile: Option<String>,
    pub active_operator_plmn: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RegisterDeviceRequest {
    pub node_id: String,
    pub node_name: String,
    pub proxy_status: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct HeartbeatRequest {
    pub node_id: String,
    pub node_name: String,
    pub readiness_state: String,
    pub serving: bool,
    pub proxy_status: String,
    pub proxy_pid: Option<u32>,
    pub last_public_ip: Option<String>,
    pub current_job: Option<Uuid>,
    pub last_proxy_error: Option<String>,
    pub version: Option<String>,
    pub config_fingerprint: Option<String>,
    pub binary_fingerprint: Option<String>,
    pub active_operator_profile: Option<String>,
    pub active_operator_plmn: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PublicProbeReport {
    pub publicly_serving: bool,
    pub public_probe_error: Option<String>,
    pub public_probe_at: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DeviceRecord {
    pub node_id: String,
    pub node_name: String,
    pub readiness_state: String,
    pub serving: bool,
    pub proxy_status: String,
    pub proxy_pid: Option<u32>,
    pub last_public_ip: Option<String>,
    pub current_job: Option<Uuid>,
    pub last_proxy_error: Option<String>,
    pub version: Option<String>,
    pub config_fingerprint: Option<String>,
    pub binary_fingerprint: Option<String>,
    pub active_operator_profile: Option<String>,
    pub active_operator_plmn: Option<String>,
    pub publicly_serving: bool,
    pub public_probe_error: Option<String>,
    pub public_probe_at: Option<String>,
    pub availability: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DeviceList {
    pub devices: Vec<DeviceRecord>,
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

pub fn default_rotate_request() -> RotateRequest {
    RotateRequest {
        strategy: "airplane_bounce".to_string(),
        require_public_ip_change: true,
        reason: "manual-rotate".to_string(),
    }
}
