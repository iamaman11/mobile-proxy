use std::error::Error;
use std::fmt::{Display, Formatter};
use std::future::Future;
use std::pin::Pin;

use proxy_core::PublicProbeReport;

#[derive(Debug, Clone)]
pub struct PublicProbeInput {
    pub device_id: String,
    pub report: PublicProbeReport,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum PublicProbeOutcome {
    Updated,
    DeviceNotFound,
}

impl PublicProbeOutcome {
    pub const fn accepted(self) -> bool {
        matches!(self, Self::Updated | Self::DeviceNotFound)
    }

    pub const fn classification(self) -> &'static str {
        match self {
            Self::Updated => "updated",
            Self::DeviceNotFound => "device_not_found",
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum PublicProbeError {
    StateConflict,
    Persistence,
}

impl Display for PublicProbeError {
    fn fmt(&self, formatter: &mut Formatter<'_>) -> std::fmt::Result {
        formatter.write_str(match self {
            Self::StateConflict => "persisted public-probe device state is internally inconsistent",
            Self::Persistence => "public-probe state could not be persisted",
        })
    }
}

impl Error for PublicProbeError {}

pub type PublicProbeFuture<'a> =
    Pin<Box<dyn Future<Output = Result<PublicProbeOutcome, PublicProbeError>> + Send + 'a>>;

pub trait PublicProbePort {
    fn record_public_probe(&self, input: PublicProbeInput) -> PublicProbeFuture<'_>;
}

#[cfg(test)]
mod tests {
    use super::PublicProbeOutcome;

    #[test]
    fn public_probe_outcomes_preserve_the_existing_accepted_shape() {
        assert!(PublicProbeOutcome::Updated.accepted());
        assert!(PublicProbeOutcome::DeviceNotFound.accepted());
    }

    #[test]
    fn public_probe_classifications_are_bounded() {
        assert_eq!(PublicProbeOutcome::Updated.classification(), "updated");
        assert_eq!(
            PublicProbeOutcome::DeviceNotFound.classification(),
            "device_not_found"
        );
    }
}
