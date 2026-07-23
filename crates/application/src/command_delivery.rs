use std::error::Error;
use std::fmt::{Display, Formatter};
use std::future::Future;
use std::pin::Pin;

use mobile_proxy_foundation::CommandId;
use proxy_core::{CommandAckRequest, DeviceCommand};

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct PollCommandInput {
    pub device_id: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum PollCommandOutcome {
    Pending(DeviceCommand),
    Empty,
}

impl PollCommandOutcome {
    pub fn into_option(self) -> Option<DeviceCommand> {
        match self {
            Self::Pending(command) => Some(command),
            Self::Empty => None,
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum PollCommandError {
    StateConflict,
}

impl Display for PollCommandError {
    fn fmt(&self, formatter: &mut Formatter<'_>) -> std::fmt::Result {
        formatter.write_str(match self {
            Self::StateConflict => "persisted command state is internally inconsistent",
        })
    }
}

impl Error for PollCommandError {}

pub type PollCommandFuture<'a> =
    Pin<Box<dyn Future<Output = Result<PollCommandOutcome, PollCommandError>> + Send + 'a>>;

pub trait PollCommandPort {
    fn poll_command(&self, input: PollCommandInput) -> PollCommandFuture<'_>;
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct AcknowledgeCommandInput {
    pub device_id: String,
    pub command_id: CommandId,
    pub request: CommandAckRequest,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum AcknowledgeCommandOutcome {
    Completed,
    RetryRequested,
    NotFound,
}

impl AcknowledgeCommandOutcome {
    pub const fn accepted(self) -> bool {
        !matches!(self, Self::NotFound)
    }

    pub const fn classification(self) -> &'static str {
        match self {
            Self::Completed => "completed",
            Self::RetryRequested => "retry_requested",
            Self::NotFound => "not_found",
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum AcknowledgeCommandError {
    StateConflict,
    Persistence,
}

impl Display for AcknowledgeCommandError {
    fn fmt(&self, formatter: &mut Formatter<'_>) -> std::fmt::Result {
        formatter.write_str(match self {
            Self::StateConflict => "persisted command state is internally inconsistent",
            Self::Persistence => "command state could not be persisted",
        })
    }
}

impl Error for AcknowledgeCommandError {}

pub type AcknowledgeCommandFuture<'a> = Pin<
    Box<
        dyn Future<Output = Result<AcknowledgeCommandOutcome, AcknowledgeCommandError>> + Send + 'a,
    >,
>;

pub trait AcknowledgeCommandPort {
    fn acknowledge_command(&self, input: AcknowledgeCommandInput) -> AcknowledgeCommandFuture<'_>;
}

#[cfg(test)]
mod tests {
    use super::AcknowledgeCommandOutcome;

    #[test]
    fn acknowledgement_outcomes_preserve_existing_http_acceptance_shape() {
        assert!(AcknowledgeCommandOutcome::Completed.accepted());
        assert!(AcknowledgeCommandOutcome::RetryRequested.accepted());
        assert!(!AcknowledgeCommandOutcome::NotFound.accepted());
    }
}
