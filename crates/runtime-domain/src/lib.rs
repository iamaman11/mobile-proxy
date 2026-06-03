use proxy_core::RuntimeReadiness;
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum RuntimeState {
    Booting,
    WaitingWireguard,
    WaitingCellular,
    StartingProxy,
    Healthy,
    Recovering,
    Quarantined,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub enum RuntimeEvent {
    BootCompleted,
    WireguardReady,
    CellularReady,
    ProxyReady,
    RouteMissing,
    ProxyFailed,
    RotationRequested,
    RecoveryTimedOut,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub enum RuntimeAction {
    WaitForWireguard,
    WaitForCellular,
    StartProxy,
    MarkHealthy,
    RepairRoute,
    RestartProxy,
    StartRotation,
    Quarantine,
    Noop,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct Transition {
    pub state: RuntimeState,
    pub actions: Vec<RuntimeAction>,
}

pub fn reduce(state: RuntimeState, event: RuntimeEvent) -> Transition {
    match (state, event) {
        (RuntimeState::Booting, RuntimeEvent::BootCompleted) => Transition {
            state: RuntimeState::WaitingWireguard,
            actions: vec![RuntimeAction::WaitForWireguard],
        },
        (RuntimeState::WaitingWireguard, RuntimeEvent::WireguardReady) => Transition {
            state: RuntimeState::WaitingCellular,
            actions: vec![RuntimeAction::WaitForCellular],
        },
        (RuntimeState::WaitingCellular, RuntimeEvent::CellularReady) => Transition {
            state: RuntimeState::StartingProxy,
            actions: vec![RuntimeAction::StartProxy],
        },
        (RuntimeState::StartingProxy, RuntimeEvent::ProxyReady) => Transition {
            state: RuntimeState::Healthy,
            actions: vec![RuntimeAction::MarkHealthy],
        },
        (RuntimeState::Healthy, RuntimeEvent::RouteMissing) => Transition {
            state: RuntimeState::Recovering,
            actions: vec![RuntimeAction::RepairRoute],
        },
        (RuntimeState::Healthy, RuntimeEvent::ProxyFailed) => Transition {
            state: RuntimeState::Recovering,
            actions: vec![RuntimeAction::RestartProxy],
        },
        (_, RuntimeEvent::RotationRequested) => Transition {
            state: RuntimeState::Recovering,
            actions: vec![RuntimeAction::StartRotation],
        },
        (RuntimeState::Recovering, RuntimeEvent::RecoveryTimedOut) => Transition {
            state: RuntimeState::Quarantined,
            actions: vec![RuntimeAction::Quarantine],
        },
        (RuntimeState::Recovering, RuntimeEvent::CellularReady) => Transition {
            state: RuntimeState::StartingProxy,
            actions: vec![RuntimeAction::StartProxy],
        },
        _ => Transition {
            state,
            actions: vec![RuntimeAction::Noop],
        },
    }
}

impl From<RuntimeState> for RuntimeReadiness {
    fn from(value: RuntimeState) -> Self {
        match value {
            RuntimeState::Booting => RuntimeReadiness::Booting,
            RuntimeState::WaitingWireguard => RuntimeReadiness::WaitingWireguard,
            RuntimeState::WaitingCellular => RuntimeReadiness::WaitingCellular,
            RuntimeState::StartingProxy => RuntimeReadiness::StartingProxy,
            RuntimeState::Healthy => RuntimeReadiness::Healthy,
            RuntimeState::Recovering => RuntimeReadiness::WaitingCellular,
            RuntimeState::Quarantined => RuntimeReadiness::Quarantined,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::{RuntimeAction, RuntimeEvent, RuntimeState, reduce};

    #[test]
    fn boot_progresses_toward_wireguard() {
        let transition = reduce(RuntimeState::Booting, RuntimeEvent::BootCompleted);
        assert_eq!(transition.state, RuntimeState::WaitingWireguard);
        assert_eq!(transition.actions, vec![RuntimeAction::WaitForWireguard]);
    }

    #[test]
    fn route_loss_enters_recovering() {
        let transition = reduce(RuntimeState::Healthy, RuntimeEvent::RouteMissing);
        assert_eq!(transition.state, RuntimeState::Recovering);
        assert_eq!(transition.actions, vec![RuntimeAction::RepairRoute]);
    }

    #[test]
    fn repeated_timeout_quarantines_runtime() {
        let transition = reduce(RuntimeState::Recovering, RuntimeEvent::RecoveryTimedOut);
        assert_eq!(transition.state, RuntimeState::Quarantined);
        assert_eq!(transition.actions, vec![RuntimeAction::Quarantine]);
    }
}
