use serde::{Deserialize, Serialize};
use std::fmt::{Display, Formatter};
use uuid::Uuid;

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
