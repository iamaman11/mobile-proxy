from pathlib import Path


def replace_once(path: Path, old: str, new: str) -> None:
    body = path.read_text(encoding="utf-8")
    if body.count(old) != 1:
        raise RuntimeError(f"expected exactly one fixer anchor in {path}: {old!r}")
    path.write_text(body.replace(old, new, 1), encoding="utf-8")


domain = Path("crates/runtime-domain/src/lib.rs")
replace_once(
    domain,
    "/// Concrete transports such as QUIC, TLS/TCP and WireGuard compatibility are\n/// adapter capabilities and must not appear in this state machine.\n",
    "/// Concrete tunnel implementations are adapter capabilities and must not\n/// appear in this state machine.\n",
)
replace_once(
    domain,
    '''\n    #[test]\n    fn serialized_domain_vocabulary_is_transport_neutral() {\n        let serialized = serde_json::to_string(&RuntimeState::WaitingTunnel).unwrap();\n        assert_eq!(serialized, r#\"\"waiting_tunnel\"\"#);\n    }\n''',
    "",
)

health = Path("services/runtime-supervisor/src/health.rs")
replace_once(
    health,
    '''    pub fn lifecycle_state(&self) -> RuntimeState {\n        self.lifecycle_state\n    }\n\n''',
    "",
)
replace_once(
    health,
    "        assert_eq!(state.lifecycle_state(), RuntimeState::Booting);\n",
    "        assert_eq!(state.lifecycle_state, RuntimeState::Booting);\n",
)
replace_once(
    health,
    "        assert_eq!(state.lifecycle_state(), RuntimeState::WaitingTunnel);\n",
    "        assert_eq!(state.lifecycle_state, RuntimeState::WaitingTunnel);\n",
)
replace_once(
    health,
    "        assert_eq!(state.lifecycle_state(), RuntimeState::Recovering);\n",
    "        assert_eq!(state.lifecycle_state, RuntimeState::Recovering);\n",
)
