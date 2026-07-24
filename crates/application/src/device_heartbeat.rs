use std::error::Error;
use std::fmt::{Display, Formatter};
use std::future::Future;
use std::pin::Pin;

use proxy_core::HeartbeatRequest;

#[derive(Debug, Clone)]
pub struct HeartbeatInput {
    pub request: HeartbeatRequest,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct HeartbeatOutcome {
    legacy_config_fingerprint: bool,
    legacy_binary_fingerprint: bool,
}

impl HeartbeatOutcome {
    pub const fn recorded(
        legacy_config_fingerprint: bool,
        legacy_binary_fingerprint: bool,
    ) -> Self {
        Self {
            legacy_config_fingerprint,
            legacy_binary_fingerprint,
        }
    }

    pub const fn accepted(self) -> bool {
        true
    }

    pub const fn legacy_config_fingerprint(self) -> bool {
        self.legacy_config_fingerprint
    }

    pub const fn legacy_binary_fingerprint(self) -> bool {
        self.legacy_binary_fingerprint
    }

    pub const fn classification(self) -> &'static str {
        if self.legacy_config_fingerprint || self.legacy_binary_fingerprint {
            "accepted_with_legacy_fingerprint"
        } else {
            "accepted"
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum HeartbeatError {
    StateConflict,
    CapacityExceeded,
    Persistence,
}

impl Display for HeartbeatError {
    fn fmt(&self, formatter: &mut Formatter<'_>) -> std::fmt::Result {
        formatter.write_str(match self {
            Self::StateConflict => "persisted device heartbeat state is internally inconsistent",
            Self::CapacityExceeded => "registered device capacity is exhausted",
            Self::Persistence => "device heartbeat state could not be persisted",
        })
    }
}

impl Error for HeartbeatError {}

pub type HeartbeatFuture<'a> =
    Pin<Box<dyn Future<Output = Result<HeartbeatOutcome, HeartbeatError>> + Send + 'a>>;

pub trait HeartbeatPort {
    fn record_heartbeat(&self, input: HeartbeatInput) -> HeartbeatFuture<'_>;
}

#[cfg(test)]
mod tests {
    use super::HeartbeatOutcome;

    #[test]
    fn heartbeat_outcome_preserves_the_existing_accepted_shape() {
        assert!(HeartbeatOutcome::recorded(false, false).accepted());
        assert!(HeartbeatOutcome::recorded(true, true).accepted());
    }

    #[test]
    fn heartbeat_classification_is_bounded() {
        assert_eq!(
            HeartbeatOutcome::recorded(false, false).classification(),
            "accepted"
        );
        assert_eq!(
            HeartbeatOutcome::recorded(true, false).classification(),
            "accepted_with_legacy_fingerprint"
        );
    }
}
