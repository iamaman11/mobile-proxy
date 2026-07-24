use std::error::Error;
use std::fmt::{Display, Formatter};

#[derive(Debug)]
pub enum SnapshotError {
    Json(serde_json::Error),
    Violation(SnapshotViolation),
}

impl Display for SnapshotError {
    fn fmt(&self, formatter: &mut Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Json(_) => formatter.write_str("control-plane snapshot JSON is invalid"),
            Self::Violation(error) => Display::fmt(error, formatter),
        }
    }
}

impl Error for SnapshotError {
    fn source(&self) -> Option<&(dyn Error + 'static)> {
        match self {
            Self::Json(error) => Some(error),
            Self::Violation(error) => Some(error),
        }
    }
}

impl From<serde_json::Error> for SnapshotError {
    fn from(error: serde_json::Error) -> Self {
        Self::Json(error)
    }
}

impl From<SnapshotViolation> for SnapshotError {
    fn from(error: SnapshotViolation) -> Self {
        Self::Violation(error)
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum SnapshotViolation {
    UnsupportedSchemaVersion { found: u32, supported: u32 },
    DeviceCapacityExceeded,
    ReplayCapacityExceeded,
    PendingCapacityExceeded,
    DeviceQueueCapacityExceeded,
    DeviceKeyMismatch,
    DuplicateDevice,
    EmptyDeviceId,
    CommandResultIdentityMismatch,
    ReplayScopeMismatch,
    DuplicateReplayScope,
    DuplicateCommandId,
    DuplicateClaimScope,
    ClaimResultMissing,
    ClaimCommandMismatch,
    ReplayEvidenceMismatch,
    ReplayClaimMissing,
    PendingIdentityMismatch,
    PendingDeviceMismatch,
    DuplicatePendingCommand,
    DuplicateQueuePosition,
    NonContiguousQueuePosition,
    PendingReplayMissing,
    PendingReplayMismatch,
}

impl Display for SnapshotViolation {
    fn fmt(&self, formatter: &mut Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::UnsupportedSchemaVersion { found, supported } => write!(
                formatter,
                "unsupported snapshot schema version {found}; supported version is {supported}"
            ),
            Self::DeviceCapacityExceeded => formatter.write_str("device capacity is exceeded"),
            Self::ReplayCapacityExceeded => formatter.write_str("replay capacity is exceeded"),
            Self::PendingCapacityExceeded => {
                formatter.write_str("pending command capacity is exceeded")
            }
            Self::DeviceQueueCapacityExceeded => {
                formatter.write_str("per-device command capacity is exceeded")
            }
            Self::DeviceKeyMismatch => {
                formatter.write_str("device row key does not match the canonical record")
            }
            Self::DuplicateDevice => formatter.write_str("device row is duplicated"),
            Self::EmptyDeviceId => formatter.write_str("device identity is empty"),
            Self::CommandResultIdentityMismatch => {
                formatter.write_str("command-result row identity does not match its result")
            }
            Self::ReplayScopeMismatch => {
                formatter.write_str("replay scope does not match the original command")
            }
            Self::DuplicateReplayScope => formatter.write_str("replay scope is duplicated"),
            Self::DuplicateCommandId => formatter.write_str("command identity is duplicated"),
            Self::DuplicateClaimScope => {
                formatter.write_str("idempotency claim scope is duplicated")
            }
            Self::ClaimResultMissing => {
                formatter.write_str("idempotency claim has no durable command result")
            }
            Self::ClaimCommandMismatch => {
                formatter.write_str("idempotency claim references another command")
            }
            Self::ReplayEvidenceMismatch => {
                formatter.write_str("request fingerprint does not match the original command")
            }
            Self::ReplayClaimMissing => {
                formatter.write_str("durable command result has no idempotency claim")
            }
            Self::PendingIdentityMismatch => {
                formatter.write_str("pending row identity does not match its command")
            }
            Self::PendingDeviceMismatch => {
                formatter.write_str("pending command is bound to another device")
            }
            Self::DuplicatePendingCommand => {
                formatter.write_str("pending command is duplicated")
            }
            Self::DuplicateQueuePosition => {
                formatter.write_str("pending queue position is duplicated")
            }
            Self::NonContiguousQueuePosition => {
                formatter.write_str("pending queue positions are not contiguous from zero")
            }
            Self::PendingReplayMissing => {
                formatter.write_str("pending command has no durable replay result")
            }
            Self::PendingReplayMismatch => {
                formatter.write_str("pending command differs from its durable replay result")
            }
        }
    }
}

impl Error for SnapshotViolation {}
