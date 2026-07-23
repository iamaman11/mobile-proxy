use mobile_proxy_foundation::{CommandId, DeadlineWindow, IdempotencyKey};
use serde::{Deserialize, Serialize};
use std::fmt::{Display, Formatter};
use uuid::Uuid;

use crate::constants::DEFAULT_AIRPLANE_HOLD_SECS;

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

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct IssueCommandRequest {
    pub desired_state: DesiredState,
    pub recovery_intent: RecoveryIntent,
    pub deadline_secs: DeadlineWindow,
    pub idempotency_key: IdempotencyKey,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct DeviceCommand {
    pub command_id: CommandId,
    pub device_id: String,
    pub desired_state: DesiredState,
    pub recovery_intent: RecoveryIntent,
    pub deadline_secs: DeadlineWindow,
    pub idempotency_key: IdempotencyKey,
    pub issued_at: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct CommandAckRequest {
    pub ok: bool,
    pub message: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RotateRequest {
    pub strategy: String,
    pub require_public_ip_change: bool,
    pub reason: String,
    pub hold_secs: Option<u64>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RotateAccepted {
    pub job_id: Uuid,
    pub accepted: bool,
}

pub fn default_rotate_request() -> RotateRequest {
    RotateRequest {
        strategy: "airplane_bounce".to_string(),
        require_public_ip_change: true,
        reason: "manual-rotate".to_string(),
        hold_secs: Some(DEFAULT_AIRPLANE_HOLD_SECS),
    }
}
