use proxy_core::RuntimeReadiness;
use runtime_domain::RuntimeState;

/// Converts the backward-compatible public readiness vocabulary into the
/// transport-neutral runtime-domain state.
pub fn state_from_legacy_readiness(raw: &str) -> RuntimeState {
    match RuntimeReadiness::parse(raw) {
        RuntimeReadiness::Booting => RuntimeState::Booting,
        RuntimeReadiness::WaitingWireguard => RuntimeState::WaitingTunnel,
        RuntimeReadiness::WaitingCellular => RuntimeState::WaitingCellular,
        RuntimeReadiness::StartingProxy => RuntimeState::StartingProxy,
        RuntimeReadiness::Healthy => RuntimeState::Healthy,
        RuntimeReadiness::Quarantined => RuntimeState::Quarantined,
        RuntimeReadiness::Unknown => RuntimeState::Recovering,
    }
}

/// Projects the neutral domain state back onto the protected legacy readiness
/// surface. `waiting_wireguard` remains unchanged until an explicit compatibility
/// migration is accepted.
pub fn legacy_readiness_from_state(state: RuntimeState) -> RuntimeReadiness {
    match state {
        RuntimeState::Booting => RuntimeReadiness::Booting,
        RuntimeState::WaitingTunnel => RuntimeReadiness::WaitingWireguard,
        RuntimeState::WaitingCellular => RuntimeReadiness::WaitingCellular,
        RuntimeState::StartingProxy => RuntimeReadiness::StartingProxy,
        RuntimeState::Healthy => RuntimeReadiness::Healthy,
        RuntimeState::Recovering => RuntimeReadiness::WaitingCellular,
        RuntimeState::Quarantined => RuntimeReadiness::Quarantined,
    }
}

#[cfg(test)]
mod tests {
    use proxy_core::RuntimeReadiness;
    use runtime_domain::RuntimeState;

    use super::{legacy_readiness_from_state, state_from_legacy_readiness};

    #[test]
    fn protected_waiting_wireguard_value_maps_to_neutral_domain_state() {
        assert_eq!(
            state_from_legacy_readiness("waiting_wireguard"),
            RuntimeState::WaitingTunnel
        );
    }

    #[test]
    fn neutral_tunnel_wait_preserves_legacy_public_value() {
        assert_eq!(
            legacy_readiness_from_state(RuntimeState::WaitingTunnel),
            RuntimeReadiness::WaitingWireguard
        );
        assert_eq!(
            legacy_readiness_from_state(RuntimeState::WaitingTunnel).to_string(),
            "waiting_wireguard"
        );
    }

    #[test]
    fn unknown_external_state_fails_closed_to_recovering() {
        assert_eq!(
            state_from_legacy_readiness("credential=secret"),
            RuntimeState::Recovering
        );
        assert_eq!(
            legacy_readiness_from_state(RuntimeState::Recovering),
            RuntimeReadiness::WaitingCellular
        );
    }
}
