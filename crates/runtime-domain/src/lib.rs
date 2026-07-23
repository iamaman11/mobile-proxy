use serde::{Deserialize, Serialize};

/// Transport-neutral lifecycle state owned by the runtime domain.
///
/// Concrete tunnel implementations are adapter capabilities and must not
/// appear in this state machine.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum RuntimeState {
    Booting,
    WaitingTunnel,
    WaitingCellular,
    StartingProxy,
    Healthy,
    Recovering,
    Quarantined,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum RuntimeEvent {
    BootCompleted,
    TunnelReady,
    TunnelLost,
    CellularReady,
    CellularLost,
    ProxyReady,
    ProxyFailed,
    RotationRequested,
    RecoveryTimedOut,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum RuntimeAction {
    WaitForTunnel,
    WaitForCellular,
    StartProxy,
    MarkHealthy,
    RecoverTunnel,
    RepairCellular,
    RestartProxy,
    StartRotation,
    Quarantine,
    Noop,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub struct Transition {
    pub previous_state: RuntimeState,
    pub state: RuntimeState,
    pub action: RuntimeAction,
}

impl Transition {
    pub fn changed(self) -> bool {
        self.previous_state != self.state
    }
}

pub fn reduce(state: RuntimeState, event: RuntimeEvent) -> Transition {
    let (next_state, action) = match (state, event) {
        (RuntimeState::Booting, RuntimeEvent::BootCompleted) => {
            (RuntimeState::WaitingTunnel, RuntimeAction::WaitForTunnel)
        }
        (RuntimeState::WaitingTunnel, RuntimeEvent::TunnelReady) => (
            RuntimeState::WaitingCellular,
            RuntimeAction::WaitForCellular,
        ),
        (RuntimeState::WaitingCellular, RuntimeEvent::CellularReady) => {
            (RuntimeState::StartingProxy, RuntimeAction::StartProxy)
        }
        (RuntimeState::StartingProxy, RuntimeEvent::ProxyReady) => {
            (RuntimeState::Healthy, RuntimeAction::MarkHealthy)
        }
        (
            RuntimeState::Healthy | RuntimeState::StartingProxy | RuntimeState::WaitingCellular,
            RuntimeEvent::TunnelLost,
        ) => (RuntimeState::Recovering, RuntimeAction::RecoverTunnel),
        (RuntimeState::Healthy | RuntimeState::StartingProxy, RuntimeEvent::CellularLost) => {
            (RuntimeState::Recovering, RuntimeAction::RepairCellular)
        }
        (RuntimeState::Healthy | RuntimeState::StartingProxy, RuntimeEvent::ProxyFailed) => {
            (RuntimeState::Recovering, RuntimeAction::RestartProxy)
        }
        (RuntimeState::Healthy, RuntimeEvent::RotationRequested) => {
            (RuntimeState::Recovering, RuntimeAction::StartRotation)
        }
        (RuntimeState::Recovering, RuntimeEvent::TunnelReady) => (
            RuntimeState::WaitingCellular,
            RuntimeAction::WaitForCellular,
        ),
        (RuntimeState::Recovering, RuntimeEvent::CellularReady) => {
            (RuntimeState::StartingProxy, RuntimeAction::StartProxy)
        }
        (RuntimeState::Recovering, RuntimeEvent::RecoveryTimedOut) => {
            (RuntimeState::Quarantined, RuntimeAction::Quarantine)
        }
        _ => (state, RuntimeAction::Noop),
    };

    Transition {
        previous_state: state,
        state: next_state,
        action,
    }
}

#[cfg(test)]
mod tests {
    use super::{RuntimeAction, RuntimeEvent, RuntimeState, reduce};

    #[test]
    fn boot_progresses_to_transport_neutral_tunnel_wait() {
        let transition = reduce(RuntimeState::Booting, RuntimeEvent::BootCompleted);
        assert_eq!(transition.previous_state, RuntimeState::Booting);
        assert_eq!(transition.state, RuntimeState::WaitingTunnel);
        assert_eq!(transition.action, RuntimeAction::WaitForTunnel);
        assert!(transition.changed());
    }

    #[test]
    fn readiness_progression_requires_tunnel_cellular_and_proxy() {
        let tunnel = reduce(RuntimeState::WaitingTunnel, RuntimeEvent::TunnelReady);
        assert_eq!(tunnel.state, RuntimeState::WaitingCellular);
        assert_eq!(tunnel.action, RuntimeAction::WaitForCellular);

        let cellular = reduce(tunnel.state, RuntimeEvent::CellularReady);
        assert_eq!(cellular.state, RuntimeState::StartingProxy);
        assert_eq!(cellular.action, RuntimeAction::StartProxy);

        let proxy = reduce(cellular.state, RuntimeEvent::ProxyReady);
        assert_eq!(proxy.state, RuntimeState::Healthy);
        assert_eq!(proxy.action, RuntimeAction::MarkHealthy);
    }

    #[test]
    fn transport_loss_recovers_without_naming_an_adapter() {
        let transition = reduce(RuntimeState::Healthy, RuntimeEvent::TunnelLost);
        assert_eq!(transition.state, RuntimeState::Recovering);
        assert_eq!(transition.action, RuntimeAction::RecoverTunnel);
    }

    #[test]
    fn cellular_and_proxy_failures_have_distinct_actions() {
        let cellular = reduce(RuntimeState::Healthy, RuntimeEvent::CellularLost);
        assert_eq!(cellular.state, RuntimeState::Recovering);
        assert_eq!(cellular.action, RuntimeAction::RepairCellular);

        let proxy = reduce(RuntimeState::Healthy, RuntimeEvent::ProxyFailed);
        assert_eq!(proxy.state, RuntimeState::Recovering);
        assert_eq!(proxy.action, RuntimeAction::RestartProxy);
    }

    #[test]
    fn rotation_is_fail_closed_until_runtime_is_healthy() {
        for state in [
            RuntimeState::Booting,
            RuntimeState::WaitingTunnel,
            RuntimeState::WaitingCellular,
            RuntimeState::StartingProxy,
            RuntimeState::Recovering,
            RuntimeState::Quarantined,
        ] {
            let transition = reduce(state, RuntimeEvent::RotationRequested);
            assert_eq!(transition.state, state);
            assert_eq!(transition.action, RuntimeAction::Noop);
            assert!(!transition.changed());
        }

        let healthy = reduce(RuntimeState::Healthy, RuntimeEvent::RotationRequested);
        assert_eq!(healthy.state, RuntimeState::Recovering);
        assert_eq!(healthy.action, RuntimeAction::StartRotation);
    }

    #[test]
    fn recovery_timeout_quarantines_runtime() {
        let transition = reduce(RuntimeState::Recovering, RuntimeEvent::RecoveryTimedOut);
        assert_eq!(transition.state, RuntimeState::Quarantined);
        assert_eq!(transition.action, RuntimeAction::Quarantine);
    }

    #[test]
    fn irrelevant_events_are_auditable_noops() {
        let transition = reduce(RuntimeState::Quarantined, RuntimeEvent::ProxyReady);
        assert_eq!(transition.previous_state, RuntimeState::Quarantined);
        assert_eq!(transition.state, RuntimeState::Quarantined);
        assert_eq!(transition.action, RuntimeAction::Noop);
        assert!(!transition.changed());
    }
}
