use std::path::PathBuf;

use clap::Parser;

use super::Cli;

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
fn sqlite_state_path_is_the_only_runtime_default() {
    let cli = Cli::try_parse_from(base_args()).unwrap();
    assert_eq!(
        cli.state_path,
        PathBuf::from("/var/lib/mobile-relaycontrolpoint/control-plane-state.sqlite3")
    );
}

#[test]
fn explicit_state_path_overrides_the_sqlite_default() {
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
    assert_eq!(
        cli.state_path,
        PathBuf::from("/srv/control-plane/custom-state.db")
    );
}

#[test]
fn retired_state_backend_option_is_rejected() {
    for value in ["json", "sqlite"] {
        assert!(
            Cli::try_parse_from([
                "control-plane",
                "--admin-token",
                "admin",
                "--device-token",
                "device",
                "--state-backend",
                value,
            ])
            .is_err()
        );
    }
}
