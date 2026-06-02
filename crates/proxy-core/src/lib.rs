use serde::{Deserialize, Serialize};
use std::fmt::{Display, Formatter};
use uuid::Uuid;

pub const RELAY_IP: &str = "34.118.26.142";
pub const MIXED_PORT: u16 = 1080;
pub const SOCKS5_PORT: u16 = 1081;
pub const HTTP_PORT: u16 = 3128;
pub const LOCAL_API: &str = "http://127.0.0.1:18088";
pub const DEVICE_ID: &str = "b4a6b2f4-5f6f-4fd1-baa4-b7d241b49a06";
pub const NODE_NAME: &str = "galaxy-a02-gcp-relay";

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum RuntimeReadiness {
    Booting,
    WaitingWireguard,
    WaitingCellular,
    StartingProxy,
    Healthy,
    Quarantined,
    Unknown,
}

impl RuntimeReadiness {
    pub fn parse(raw: &str) -> Self {
        match raw {
            "booting" => Self::Booting,
            "waiting_wireguard" => Self::WaitingWireguard,
            "waiting_cellular" => Self::WaitingCellular,
            "starting_proxy" => Self::StartingProxy,
            "healthy" => Self::Healthy,
            "quarantined" => Self::Quarantined,
            _ => Self::Unknown,
        }
    }
}

impl Display for RuntimeReadiness {
    fn fmt(&self, f: &mut Formatter<'_>) -> std::fmt::Result {
        let value = match self {
            Self::Booting => "booting",
            Self::WaitingWireguard => "waiting_wireguard",
            Self::WaitingCellular => "waiting_cellular",
            Self::StartingProxy => "starting_proxy",
            Self::Healthy => "healthy",
            Self::Quarantined => "quarantined",
            Self::Unknown => "unknown",
        };
        write!(f, "{value}")
    }
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum Availability {
    Ready,
    Degraded,
}

impl Display for Availability {
    fn fmt(&self, f: &mut Formatter<'_>) -> std::fmt::Result {
        let value = match self {
            Self::Ready => "ready",
            Self::Degraded => "degraded",
        };
        write!(f, "{value}")
    }
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum DegradationReasonCode {
    Booting,
    WireguardPathNotReady,
    CellularRouteMissing,
    ProxyStarting,
    ProxyBindFailed,
    LocalProbeFailed,
    RotationInProgress,
    Quarantined,
    UnknownState,
}

impl Display for DegradationReasonCode {
    fn fmt(&self, f: &mut Formatter<'_>) -> std::fmt::Result {
        let value = match self {
            Self::Booting => "booting",
            Self::WireguardPathNotReady => "wireguard_path_not_ready",
            Self::CellularRouteMissing => "cellular_route_missing",
            Self::ProxyStarting => "proxy_starting",
            Self::ProxyBindFailed => "proxy_bind_failed",
            Self::LocalProbeFailed => "local_probe_failed",
            Self::RotationInProgress => "rotation_in_progress",
            Self::Quarantined => "quarantined",
            Self::UnknownState => "unknown_state",
        };
        write!(f, "{value}")
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RuntimeProjectionInput {
    pub readiness_state: String,
    pub serving: bool,
    pub publicly_serving: bool,
    pub current_job: Option<Uuid>,
    pub cellular_route_ready: Option<bool>,
    pub proxy_bind_ready: Option<bool>,
    pub local_serving_ready: Option<bool>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RuntimeProjection {
    pub readiness_state: String,
    pub serving: bool,
    pub availability: String,
    pub degradation_reason_code: Option<String>,
    pub serving_failure_reason: Option<String>,
}

pub fn project_runtime(input: RuntimeProjectionInput) -> RuntimeProjection {
    let readiness = RuntimeReadiness::parse(&input.readiness_state);
    let serving = normalize_serving(readiness, &input);
    let reason = derive_degradation_reason(readiness, serving, &input);
    let availability =
        if readiness == RuntimeReadiness::Healthy && serving && input.publicly_serving {
            Availability::Ready
        } else {
            Availability::Degraded
        };

    RuntimeProjection {
        readiness_state: readiness.to_string(),
        serving,
        availability: availability.to_string(),
        degradation_reason_code: reason.map(|r| r.to_string()),
        serving_failure_reason: reason.map(degradation_reason_message),
    }
}

fn normalize_serving(readiness: RuntimeReadiness, input: &RuntimeProjectionInput) -> bool {
    if readiness != RuntimeReadiness::Healthy {
        return false;
    }
    if input.current_job.is_some() {
        return false;
    }
    if input.cellular_route_ready == Some(false) {
        return false;
    }
    if input.proxy_bind_ready == Some(false) {
        return false;
    }
    if input.local_serving_ready == Some(false) {
        return false;
    }
    input.serving
}

fn derive_degradation_reason(
    readiness: RuntimeReadiness,
    serving: bool,
    input: &RuntimeProjectionInput,
) -> Option<DegradationReasonCode> {
    if input.current_job.is_some() {
        return Some(DegradationReasonCode::RotationInProgress);
    }
    if !serving {
        if input.cellular_route_ready == Some(false) {
            return Some(DegradationReasonCode::CellularRouteMissing);
        }
        if input.proxy_bind_ready == Some(false) {
            return Some(DegradationReasonCode::ProxyBindFailed);
        }
        if input.local_serving_ready == Some(false) {
            return Some(DegradationReasonCode::LocalProbeFailed);
        }
    }

    match readiness {
        RuntimeReadiness::Booting => Some(DegradationReasonCode::Booting),
        RuntimeReadiness::WaitingWireguard => Some(DegradationReasonCode::WireguardPathNotReady),
        RuntimeReadiness::WaitingCellular => Some(DegradationReasonCode::CellularRouteMissing),
        RuntimeReadiness::StartingProxy => Some(DegradationReasonCode::ProxyStarting),
        RuntimeReadiness::Quarantined => Some(DegradationReasonCode::Quarantined),
        RuntimeReadiness::Unknown => Some(DegradationReasonCode::UnknownState),
        RuntimeReadiness::Healthy => {
            if serving {
                None
            } else {
                Some(DegradationReasonCode::LocalProbeFailed)
            }
        }
    }
}

fn degradation_reason_message(code: DegradationReasonCode) -> String {
    match code {
        DegradationReasonCode::Booting => "runtime is booting".into(),
        DegradationReasonCode::WireguardPathNotReady => "wireguard path is not ready".into(),
        DegradationReasonCode::CellularRouteMissing => "cellular default route is not ready".into(),
        DegradationReasonCode::ProxyStarting => "proxy is starting".into(),
        DegradationReasonCode::ProxyBindFailed => {
            "proxy is not bound to the expected listen address".into()
        }
        DegradationReasonCode::LocalProbeFailed => "local proxy probe failed".into(),
        DegradationReasonCode::RotationInProgress => "rotation job is in progress".into(),
        DegradationReasonCode::Quarantined => "runtime is quarantined".into(),
        DegradationReasonCode::UnknownState => "runtime reported unknown state".into(),
    }
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum DesiredState {
    HealthyServing,
    DegradedSafe,
}

impl Display for DesiredState {
    fn fmt(&self, f: &mut Formatter<'_>) -> std::fmt::Result {
        let value = match self {
            Self::HealthyServing => "healthy_serving",
            Self::DegradedSafe => "degraded_safe",
        };
        write!(f, "{value}")
    }
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum RecoveryIntent {
    None,
    RouteRepair,
    RestartRuntime,
    RotateRecovery,
}

impl Display for RecoveryIntent {
    fn fmt(&self, f: &mut Formatter<'_>) -> std::fmt::Result {
        let value = match self {
            Self::None => "none",
            Self::RouteRepair => "route_repair",
            Self::RestartRuntime => "restart_runtime",
            Self::RotateRecovery => "rotate_recovery",
        };
        write!(f, "{value}")
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct IssueCommandRequest {
    pub desired_state: DesiredState,
    pub recovery_intent: RecoveryIntent,
    pub deadline_secs: u32,
    pub idempotency_key: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DeviceCommand {
    pub command_id: Uuid,
    pub device_id: String,
    pub desired_state: DesiredState,
    pub recovery_intent: RecoveryIntent,
    pub deadline_secs: u32,
    pub idempotency_key: String,
    pub issued_at: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CommandAckRequest {
    pub ok: bool,
    pub message: Option<String>,
}

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

#[cfg(test)]
mod tests {
    use super::{
        Availability, RuntimeProjectionInput, RuntimeReadiness, project_runtime, proxy_endpoints,
    };

    #[test]
    fn projection_requires_public_probe_for_ready() {
        let projected = project_runtime(RuntimeProjectionInput {
            readiness_state: RuntimeReadiness::Healthy.to_string(),
            serving: true,
            publicly_serving: false,
            current_job: None,
            cellular_route_ready: Some(true),
            proxy_bind_ready: Some(true),
            local_serving_ready: Some(true),
        });
        assert_eq!(projected.availability, Availability::Degraded.to_string());
    }

    #[test]
    fn projection_rejects_serving_without_cellular_route() {
        let projected = project_runtime(RuntimeProjectionInput {
            readiness_state: RuntimeReadiness::Healthy.to_string(),
            serving: true,
            publicly_serving: true,
            current_job: None,
            cellular_route_ready: Some(false),
            proxy_bind_ready: Some(true),
            local_serving_ready: Some(true),
        });
        assert!(!projected.serving);
        assert_eq!(
            projected.degradation_reason_code.as_deref(),
            Some("cellular_route_missing")
        );
    }

    #[test]
    fn projection_rejects_serving_while_rotation_job_exists() {
        let projected = project_runtime(RuntimeProjectionInput {
            readiness_state: RuntimeReadiness::Healthy.to_string(),
            serving: true,
            publicly_serving: true,
            current_job: Some(uuid::Uuid::new_v4()),
            cellular_route_ready: Some(true),
            proxy_bind_ready: Some(true),
            local_serving_ready: Some(true),
        });
        assert!(!projected.serving);
        assert_eq!(
            projected.degradation_reason_code.as_deref(),
            Some("rotation_in_progress")
        );
    }

    #[test]
    fn proxy_endpoints_have_expected_public_ports() {
        let endpoints = proxy_endpoints();
        assert_eq!(endpoints[0].port, 1080);
        assert_eq!(endpoints[1].port, 1081);
        assert_eq!(endpoints[2].port, 3128);
    }
}
