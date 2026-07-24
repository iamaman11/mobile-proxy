use clap::Parser;

use super::{Cli, StateBackend};

#[test]
fn state_backend_defaults_to_json() {
    let cli = Cli::try_parse_from([
        "control-plane",
        "--admin-token",
        "admin",
        "--device-token",
        "device",
    ])
    .unwrap();
    assert_eq!(cli.state_backend, StateBackend::Json);
}

#[test]
fn sqlite_state_backend_requires_explicit_selection() {
    let cli = Cli::try_parse_from([
        "control-plane",
        "--admin-token",
        "admin",
        "--device-token",
        "device",
        "--state-backend",
        "sqlite",
    ])
    .unwrap();
    assert_eq!(cli.state_backend, StateBackend::Sqlite);
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
