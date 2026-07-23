from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def write(path: str, content: str) -> None:
    target = ROOT / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


def replace_once(path: str, old: str, new: str) -> None:
    target = ROOT / path
    content = target.read_text(encoding="utf-8")
    if content.count(old) != 1:
        raise RuntimeError(f"expected exactly one anchor in {path}: {old!r}")
    target.write_text(content.replace(old, new, 1), encoding="utf-8")


write(
    "crates/runtime-domain/Cargo.toml",
    """[package]
name = "runtime-domain"
version.workspace = true
edition.workspace = true
license.workspace = true

[dependencies]
serde.workspace = true
""",
)

write(
    "crates/runtime-domain/src/lib.rs",
    r'''use serde::{Deserialize, Serialize};

/// Transport-neutral lifecycle state owned by the runtime domain.
///
/// Concrete transports such as QUIC, TLS/TCP and WireGuard compatibility are
/// adapter capabilities and must not appear in this state machine.
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
        (
            RuntimeState::Healthy | RuntimeState::StartingProxy,
            RuntimeEvent::CellularLost,
        ) => (RuntimeState::Recovering, RuntimeAction::RepairCellular),
        (
            RuntimeState::Healthy | RuntimeState::StartingProxy,
            RuntimeEvent::ProxyFailed,
        ) => (RuntimeState::Recovering, RuntimeAction::RestartProxy),
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

    #[test]
    fn serialized_domain_vocabulary_is_transport_neutral() {
        let serialized = serde_json::to_string(&RuntimeState::WaitingTunnel).unwrap();
        assert_eq!(serialized, r#""waiting_tunnel""#);
    }
}
''',
)

write(
    "services/runtime-supervisor/src/runtime_adapter.rs",
    r'''use proxy_core::RuntimeReadiness;
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
''',
)

replace_once(
    "services/runtime-supervisor/src/main.rs",
    "mod process;\n",
    "mod process;\nmod runtime_adapter;\n",
)

replace_once(
    "services/runtime-supervisor/src/health.rs",
    "use proxy_core::HealthRecord;\nuse tracing::{info, warn};\n",
    "use proxy_core::HealthRecord;\nuse runtime_domain::RuntimeState;\nuse tracing::{info, warn};\n",
)
replace_once(
    "services/runtime-supervisor/src/health.rs",
    "use crate::config::{SupervisorConfig, TunnelOwner};\n",
    "use crate::config::{SupervisorConfig, TunnelOwner};\nuse crate::runtime_adapter::{legacy_readiness_from_state, state_from_legacy_readiness};\n",
)
replace_once(
    "services/runtime-supervisor/src/health.rs",
    "pub struct SupervisorState {\n    last_route_repair: Option<Instant>,\n    last_proxy_restart: Option<Instant>,\n}\n",
    "pub struct SupervisorState {\n    lifecycle_state: RuntimeState,\n    last_route_repair: Option<Instant>,\n    last_proxy_restart: Option<Instant>,\n}\n\n#[derive(Debug, Clone, Copy, PartialEq, Eq)]\npub struct ObservedRuntimeTransition {\n    pub from: RuntimeState,\n    pub to: RuntimeState,\n}\n",
)
replace_once(
    "services/runtime-supervisor/src/health.rs",
    "        Self {\n            last_route_repair: None,\n            last_proxy_restart: None,\n        }\n",
    "        Self {\n            lifecycle_state: RuntimeState::Booting,\n            last_route_repair: None,\n            last_proxy_restart: None,\n        }\n",
)
replace_once(
    "services/runtime-supervisor/src/health.rs",
    "    pub fn claim_proxy_restart(&mut self, cooldown_secs: u64) -> bool {\n",
    "    pub fn lifecycle_state(&self) -> RuntimeState {\n        self.lifecycle_state\n    }\n\n    pub fn observe_readiness(&mut self, raw: &str) -> Option<ObservedRuntimeTransition> {\n        let next = state_from_legacy_readiness(raw);\n        if next == self.lifecycle_state {\n            return None;\n        }\n        let transition = ObservedRuntimeTransition {\n            from: self.lifecycle_state,\n            to: next,\n        };\n        self.lifecycle_state = next;\n        Some(transition)\n    }\n\n    pub fn claim_proxy_restart(&mut self, cooldown_secs: u64) -> bool {\n",
)
replace_once(
    "services/runtime-supervisor/src/health.rs",
    "pub async fn reconcile_health(\n    config: &SupervisorConfig,\n    state: &mut SupervisorState,\n    health: &HealthRecord,\n) -> Result<()> {\n",
    "pub async fn reconcile_health(\n    config: &SupervisorConfig,\n    state: &mut SupervisorState,\n    health: &HealthRecord,\n) -> Result<()> {\n    if let Some(transition) = state.observe_readiness(&health.readiness_state) {\n        info!(\n            from = ?transition.from,\n            to = ?transition.to,\n            compatible_readiness = %legacy_readiness_from_state(transition.to),\n            \"runtime lifecycle projection changed\"\n        );\n    }\n",
)

health_tests = r'''

#[cfg(test)]
mod tests {
    use runtime_domain::RuntimeState;

    use super::SupervisorState;

    #[test]
    fn supervisor_tracks_neutral_state_without_duplicate_transitions() {
        let mut state = SupervisorState::new();
        assert_eq!(state.lifecycle_state(), RuntimeState::Booting);

        let waiting = state.observe_readiness("waiting_wireguard").unwrap();
        assert_eq!(waiting.from, RuntimeState::Booting);
        assert_eq!(waiting.to, RuntimeState::WaitingTunnel);
        assert_eq!(state.lifecycle_state(), RuntimeState::WaitingTunnel);
        assert!(state.observe_readiness("waiting_wireguard").is_none());

        let healthy = state.observe_readiness("healthy").unwrap();
        assert_eq!(healthy.from, RuntimeState::WaitingTunnel);
        assert_eq!(healthy.to, RuntimeState::Healthy);
    }

    #[test]
    fn unknown_readiness_fails_closed_to_recovering() {
        let mut state = SupervisorState::new();
        let transition = state.observe_readiness("raw-provider-error").unwrap();
        assert_eq!(transition.to, RuntimeState::Recovering);
        assert_eq!(state.lifecycle_state(), RuntimeState::Recovering);
    }
}
'''
health_path = ROOT / "services/runtime-supervisor/src/health.rs"
health_path.write_text(health_path.read_text(encoding="utf-8") + health_tests, encoding="utf-8")

write(
    "scripts/check_architecture_boundaries.py",
    r'''#!/usr/bin/env python3
"""Fail closed when a domain crate gains infrastructure dependencies or vocabulary."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
import tomllib

DOMAIN_CRATES: dict[str, frozenset[str]] = {
    "crates/runtime-domain": frozenset({"serde"}),
}

FORBIDDEN_SOURCE_TOKENS = (
    "wireguard",
    "proxy_core",
    "axum",
    "tonic",
    "sqlx",
    "rusqlite",
    "reqwest",
    "tokio",
    "std::fs",
    "std::net",
    "std::process",
    "std::env",
    "android",
)


def dependency_tables(node: object, path: tuple[str, ...] = ()):
    if not isinstance(node, dict):
        return
    for key, value in node.items():
        next_path = (*path, key)
        if key in {"dependencies", "dev-dependencies", "build-dependencies"} and isinstance(
            value, dict
        ):
            yield ".".join(next_path), value
        else:
            yield from dependency_tables(value, next_path)


def check_repository(root: Path) -> list[str]:
    errors: list[str] = []
    for relative, allowed_dependencies in DOMAIN_CRATES.items():
        crate = root / relative
        manifest_path = crate / "Cargo.toml"
        if not manifest_path.is_file():
            errors.append(f"{relative}: missing Cargo.toml")
            continue

        manifest = tomllib.loads(manifest_path.read_text(encoding="utf-8"))
        for table_name, dependencies in dependency_tables(manifest):
            for dependency in dependencies:
                normalized = dependency.replace("-", "_")
                allowed = {item.replace("-", "_") for item in allowed_dependencies}
                if normalized not in allowed:
                    errors.append(
                        f"{relative}: forbidden dependency {dependency!r} in {table_name}"
                    )

        source_root = crate / "src"
        if not source_root.is_dir():
            errors.append(f"{relative}: missing src directory")
            continue
        for source in sorted(source_root.rglob("*.rs")):
            body = source.read_text(encoding="utf-8").lower()
            for token in FORBIDDEN_SOURCE_TOKENS:
                if token in body:
                    errors.append(
                        f"{source.relative_to(root)}: forbidden domain token {token!r}"
                    )
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
    )
    args = parser.parse_args()
    errors = check_repository(args.repo_root.resolve())
    if errors:
        print("architecture boundary validation failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print("architecture boundary validation passed for runtime-domain")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
''',
)

write(
    "scripts/tests/test_architecture_boundaries.py",
    r'''import importlib.util
from pathlib import Path
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "check_architecture_boundaries.py"
SPEC = importlib.util.spec_from_file_location("architecture_boundaries", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class ArchitectureBoundaryTests(unittest.TestCase):
    def create_repository(self, manifest: str, source: str) -> Path:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        crate = root / "crates/runtime-domain"
        (crate / "src").mkdir(parents=True)
        (crate / "Cargo.toml").write_text(manifest, encoding="utf-8")
        (crate / "src/lib.rs").write_text(source, encoding="utf-8")
        return root

    def test_accepts_pure_runtime_domain(self):
        root = self.create_repository(
            """[package]\nname = \"runtime-domain\"\nversion = \"0.1.0\"\n\n[dependencies]\nserde = \"1\"\n""",
            "pub enum RuntimeState { WaitingTunnel }\n",
        )
        self.assertEqual(MODULE.check_repository(root), [])

    def test_rejects_infrastructure_dependency(self):
        root = self.create_repository(
            """[package]\nname = \"runtime-domain\"\nversion = \"0.1.0\"\n\n[dependencies]\nserde = \"1\"\ntokio = \"1\"\n""",
            "pub enum RuntimeState { WaitingTunnel }\n",
        )
        errors = MODULE.check_repository(root)
        self.assertTrue(any("forbidden dependency 'tokio'" in error for error in errors))

    def test_rejects_adapter_specific_domain_vocabulary(self):
        root = self.create_repository(
            """[package]\nname = \"runtime-domain\"\nversion = \"0.1.0\"\n\n[dependencies]\nserde = \"1\"\n""",
            'pub const OWNER: &str = "wireguard";\n',
        )
        errors = MODULE.check_repository(root)
        self.assertTrue(any("forbidden domain token 'wireguard'" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
''',
)

write(
    "docs/architecture/runtime-domain-boundary.md",
    """# Transport-neutral runtime domain boundary

## Decision

`crates/runtime-domain` owns only deterministic lifecycle state, events, actions and transitions. It does not know which tunnel adapter is selected.

The domain vocabulary is:

```text
BOOTING
WAITING_TUNNEL
WAITING_CELLULAR
STARTING_PROXY
HEALTHY
RECOVERING
QUARANTINED
```

QUIC, certificate-pinned TLS/TCP and WireGuard compatibility remain adapter capabilities. They must not appear in runtime-domain source or dependencies.

## Compatibility adapter

The existing public readiness value `waiting_wireguard` remains protected. `runtime-supervisor` translates it to `WaitingTunnel` on ingress and translates `WaitingTunnel` back to `waiting_wireguard` when projecting the legacy surface. This isolates historical vocabulary without silently changing operator or control-plane contracts.

Unknown public readiness values fail closed to the neutral `Recovering` state. They are never copied into a domain enum or emitted as an unbounded label.

## Production composition

`runtime-supervisor` observes every authenticated host health record and maintains the neutral lifecycle projection. State changes are logged with bounded enum values and the compatible readiness projection. The projection is observational in this slice: existing recovery commands, readiness decisions, proxy listeners and transport selection are unchanged.

## Enforcement

`scripts/check_architecture_boundaries.py` rejects:

- dependencies other than the explicitly allowed pure dependency set;
- infrastructure frameworks and runtime libraries in domain source;
- filesystem, network, process and environment access;
- Android or WireGuard-specific vocabulary;
- a dependency back to transitional `proxy-core`.

The validator and its regression tests run in the permanent `Rust Quality` workflow and the complete local quality gate.

## Next extraction

The next Phase 1 slice should introduce typed foundation identifiers and deadlines, then move application orchestration behind ports without changing the protected proxy or operator surface.
""",
)

replace_once(
    ".github/workflows/rust-quality.yml",
    "    steps:\n      - name: Check out source\n        uses: actions/checkout@v7\n\n      - name: Install stable Rust toolchain\n",
    "    steps:\n      - name: Check out source\n        uses: actions/checkout@v7\n\n      - name: Enforce architecture boundaries\n        run: |\n          python3 scripts/check_architecture_boundaries.py\n          python3 -m unittest discover -s scripts/tests -p 'test_*.py'\n\n      - name: Install stable Rust toolchain\n",
)

replace_once(
    "scripts/quality-gate.sh",
    "cd \"$repo_root\"\ncargo fmt --all -- --check\n",
    "cd \"$repo_root\"\npython3 scripts/check_architecture_boundaries.py\npython3 -m unittest discover -s scripts/tests -p 'test_*.py'\ncargo fmt --all -- --check\n",
)

replace_once(
    "README.md",
    "- `crates/runtime-domain` - pure runtime state machine baseline\n",
    "- `crates/runtime-domain` - transport-neutral pure runtime lifecycle domain with enforced dependency boundaries\n",
)
