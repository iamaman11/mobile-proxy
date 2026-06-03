use serde::{Deserialize, Serialize};
use uuid::Uuid;

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
    pub last_proxy_error: Option<String>,
    pub serving_failure_reason: Option<String>,
    pub degradation_reason_code: Option<String>,
    pub cellular_route_ready: Option<bool>,
    pub proxy_bind_ready: Option<bool>,
    pub local_serving_ready: Option<bool>,
    pub tun0_present: Option<bool>,
    pub wg_handshake_recent: Option<bool>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RuntimeStatusRecord {
    pub node_id: String,
    pub node_name: String,
    pub current_job: Option<Uuid>,
    pub wireguard_enabled: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ProxyRuntimeRecord {
    pub status: String,
    pub listen_address: String,
    pub pid: Option<u32>,
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
    pub cellular_route_ready: Option<bool>,
    pub proxy_bind_ready: Option<bool>,
    pub local_serving_ready: Option<bool>,
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
    pub degradation_reason_code: Option<String>,
    pub serving_failure_reason: Option<String>,
    pub desired_state: Option<String>,
    pub recovery_intent: Option<String>,
    pub last_event_at: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DeviceList {
    pub devices: Vec<DeviceRecord>,
}
