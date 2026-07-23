use std::error::Error;
use std::fmt::{Display, Formatter};
use std::future::Future;
use std::pin::Pin;

use mobile_proxy_foundation::{ContentDigest, DigestDomain, IdempotencyKey};
use proxy_core::{DeviceCommand, IssueCommandRequest};

const COMMAND_REQUEST_DOMAIN: DigestDomain =
    DigestDomain::new("mobile-proxy/control-plane-command-request/v1");
const IDEMPOTENCY_SCOPE_DOMAIN: DigestDomain =
    DigestDomain::new("mobile-proxy/control-plane-command-idempotency-scope/v1");

pub const MAX_COMMAND_QUEUE_PER_DEVICE: usize = 50;
pub const MAX_IDEMPOTENCY_RESULTS: usize = 1_000;
pub const MAX_PENDING_COMMANDS: usize = 1_000;

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct IssueCommandInput {
    pub device_id: String,
    pub request: IssueCommandRequest,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum IssueCommandOutcome {
    Created(DeviceCommand),
    ExactDuplicate(DeviceCommand),
}

impl IssueCommandOutcome {
    pub fn into_parts(self) -> (&'static str, DeviceCommand) {
        match self {
            Self::Created(command) => ("created", command),
            Self::ExactDuplicate(command) => ("exact_duplicate", command),
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum IssueCommandError {
    IdempotencyConflict,
    StateConflict,
    CapacityExceeded,
    Persistence,
}

impl Display for IssueCommandError {
    fn fmt(&self, formatter: &mut Formatter<'_>) -> std::fmt::Result {
        formatter.write_str(match self {
            Self::IdempotencyConflict => "idempotency key conflicts with the original command",
            Self::StateConflict => "persisted command state is internally inconsistent",
            Self::CapacityExceeded => "pending command capacity is exhausted",
            Self::Persistence => "command state could not be persisted",
        })
    }
}

impl Error for IssueCommandError {}

pub type IssueCommandFuture<'a> =
    Pin<Box<dyn Future<Output = Result<IssueCommandOutcome, IssueCommandError>> + Send + 'a>>;

pub trait IssueCommandPort {
    fn issue_command(&self, input: IssueCommandInput) -> IssueCommandFuture<'_>;
}

pub fn request_fingerprint(device_id: &str, request: &IssueCommandRequest) -> ContentDigest {
    let desired_state = request.desired_state.to_string();
    let recovery_intent = request.recovery_intent.to_string();
    let deadline = request.deadline_secs.as_secs().to_be_bytes();
    ContentDigest::derive(
        COMMAND_REQUEST_DOMAIN,
        [
            device_id.as_bytes(),
            desired_state.as_bytes(),
            recovery_intent.as_bytes(),
            deadline.as_slice(),
        ],
    )
}

pub fn idempotency_scope_key(device_id: &str, key: &IdempotencyKey) -> ContentDigest {
    ContentDigest::derive(
        IDEMPOTENCY_SCOPE_DOMAIN,
        [device_id.as_bytes(), key.as_str().as_bytes()],
    )
}

pub fn classify_existing(
    existing: &DeviceCommand,
    device_id: &str,
    request: &IssueCommandRequest,
) -> Result<DeviceCommand, IssueCommandError> {
    let original = IssueCommandRequest {
        desired_state: existing.desired_state,
        recovery_intent: existing.recovery_intent,
        deadline_secs: existing.deadline_secs,
        idempotency_key: existing.idempotency_key.clone(),
    };
    if existing.idempotency_key == request.idempotency_key
        && request_fingerprint(&existing.device_id, &original)
            == request_fingerprint(device_id, request)
    {
        Ok(existing.clone())
    } else {
        Err(IssueCommandError::IdempotencyConflict)
    }
}

#[cfg(test)]
mod tests {
    use mobile_proxy_foundation::{DeadlineWindow, IdempotencyKey};
    use proxy_core::{DesiredState, DeviceCommand, IssueCommandRequest, RecoveryIntent};

    use super::{IssueCommandError, classify_existing, idempotency_scope_key, request_fingerprint};

    fn request(desired_state: DesiredState, key: &str) -> IssueCommandRequest {
        IssueCommandRequest {
            desired_state,
            recovery_intent: RecoveryIntent::None,
            deadline_secs: DeadlineWindow::new(30).unwrap(),
            idempotency_key: IdempotencyKey::parse(key).unwrap(),
        }
    }

    fn existing() -> DeviceCommand {
        let request = request(DesiredState::HealthyServing, "command-123");
        DeviceCommand {
            command_id: "00000000-0000-0000-0000-000000000001".parse().unwrap(),
            device_id: "device-1".into(),
            desired_state: request.desired_state,
            recovery_intent: request.recovery_intent,
            deadline_secs: request.deadline_secs,
            idempotency_key: request.idempotency_key,
            issued_at: "1".into(),
        }
    }

    #[test]
    fn exact_duplicate_returns_original_result() {
        let existing = existing();
        let duplicate = request(DesiredState::HealthyServing, "command-123");
        assert_eq!(
            classify_existing(&existing, "device-1", &duplicate).unwrap(),
            existing
        );
    }

    #[test]
    fn changed_parameters_fail_with_idempotency_conflict() {
        let result = classify_existing(
            &existing(),
            "device-1",
            &request(DesiredState::DegradedSafe, "command-123"),
        );
        assert_eq!(result, Err(IssueCommandError::IdempotencyConflict));
    }

    #[test]
    fn scoped_key_and_request_fingerprint_use_unambiguous_framing() {
        let left_key = IdempotencyKey::parse("c").unwrap();
        let right_key = IdempotencyKey::parse("b:c").unwrap();
        assert_ne!(
            idempotency_scope_key("a:b", &left_key),
            idempotency_scope_key("a", &right_key)
        );

        let left = request(DesiredState::HealthyServing, "left");
        let mut right = left.clone();
        right.deadline_secs = DeadlineWindow::new(31).unwrap();
        assert_ne!(
            request_fingerprint("device-1", &left),
            request_fingerprint("device-1", &right)
        );
    }
}
