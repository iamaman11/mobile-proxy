use std::path::PathBuf;

use clap::Parser;

use super::{Cli, StateBackend};

fn base_args() -> [&'static str; 5] {
    [
        "control-plane",
        "--admin-token",
        "admin",
        "--device-token",
        "device",
    ]
}

#[test]
fn state_backend_defaults_to_sqlite_and_its_canonical_path() {
    let cli = Cli::try_parse_from(base_args()).unwrap();
    assert_eq!(cli.state_backend, StateBackend::Sqlite);
    assert_eq!(
        cli.resolved_state_path(),
        PathBuf::from("/var/lib/mobile-relaycontrolpoint/control-plane-state.sqlite3")
    );
}

#[test]
fn json_backend_requires_explicit_rollback_selection() {
    let cli = Cli::try_parse_from([
        "control-plane",
        "--admin-token",
        "admin",
        "--device-token",
        "device",
        "--state-backend",
        "json",
    ])
    .unwrap();
    assert_eq!(cli.state_backend, StateBackend::Json);
    assert_eq!(
        cli.resolved_state_path(),
        PathBuf::from("/var/lib/mobile-relaycontrolpoint/control-plane-state.json")
    );
}

#[test]
fn explicit_state_path_overrides_the_backend_default() {
    let cli = Cli::try_parse_from([
        "control-plane",
        "--admin-token",
        "admin",
        "--device-token",
        "device",
        "--state-path",
        "/srv/control-plane/custom-state.db",
    ])
    .unwrap();
    assert_eq!(cli.state_backend, StateBackend::Sqlite);
    assert_eq!(
        cli.resolved_state_path(),
        PathBuf::from("/srv/control-plane/custom-state.db")
    );
}

#[test]
fn unknown_state_backend_is_rejected() {
    assert!(
        Cli::try_parse_from([
            "control-plane",
            "--admin-token",
            "admin",
            "--device-token",
            "device",
            "--state-backend",
            "unknown",
        ])
        .is_err()
    );
}
