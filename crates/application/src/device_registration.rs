use std::error::Error;
use std::fmt::{Display, Formatter};
use std::future::Future;
use std::pin::Pin;

use proxy_core::RegisterDeviceRequest;

pub const MAX_REGISTERED_DEVICES: usize = 10_000;

#[derive(Debug, Clone)]
pub struct RegisterDeviceInput {
    pub request: RegisterDeviceRequest,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum RegisterDeviceOutcome {
    Created,
    AlreadyRegistered,
}

impl RegisterDeviceOutcome {
    pub const fn accepted(self) -> bool {
        matches!(self, Self::Created | Self::AlreadyRegistered)
    }

    pub const fn classification(self) -> &'static str {
        match self {
            Self::Created => "created",
            Self::AlreadyRegistered => "already_registered",
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum RegisterDeviceError {
    StateConflict,
    CapacityExceeded,
    Persistence,
}

impl Display for RegisterDeviceError {
    fn fmt(&self, formatter: &mut Formatter<'_>) -> std::fmt::Result {
        formatter.write_str(match self {
            Self::StateConflict => "persisted device registry is internally inconsistent",
            Self::CapacityExceeded => "registered device capacity is exhausted",
            Self::Persistence => "device registration state could not be persisted",
        })
    }
}

impl Error for RegisterDeviceError {}

pub type RegisterDeviceFuture<'a> =
    Pin<Box<dyn Future<Output = Result<RegisterDeviceOutcome, RegisterDeviceError>> + Send + 'a>>;

pub trait RegisterDevicePort {
    fn register_device(&self, input: RegisterDeviceInput) -> RegisterDeviceFuture<'_>;
}

#[cfg(test)]
mod tests {
    use super::RegisterDeviceOutcome;

    #[test]
    fn registration_outcomes_preserve_the_existing_accepted_shape() {
        assert!(RegisterDeviceOutcome::Created.accepted());
        assert!(RegisterDeviceOutcome::AlreadyRegistered.accepted());
    }

    #[test]
    fn registration_classifications_are_bounded() {
        assert_eq!(RegisterDeviceOutcome::Created.classification(), "created");
        assert_eq!(
            RegisterDeviceOutcome::AlreadyRegistered.classification(),
            "already_registered"
        );
    }
}
