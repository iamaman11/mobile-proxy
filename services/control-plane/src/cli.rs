use clap::{Parser, ValueEnum};
use std::path::PathBuf;

const JSON_STATE_PATH: &str =
    "/var/lib/mobile-relaycontrolpoint/control-plane-state.json";
const SQLITE_STATE_PATH: &str =
    "/var/lib/mobile-relaycontrolpoint/control-plane-state.sqlite3";

#[derive(ValueEnum, Clone, Copy, Debug, Default, PartialEq, Eq)]
#[value(rename_all = "snake_case")]
pub enum StateBackend {
    Json,
    #[default]
    Sqlite,
}

impl StateBackend {
    fn default_state_path(self) -> PathBuf {
        match self {
            Self::Json => PathBuf::from(JSON_STATE_PATH),
            Self::Sqlite => PathBuf::from(SQLITE_STATE_PATH),
        }
    }
}

#[derive(Parser, Debug)]
#[command(name = "control-plane")]
#[command(about = "Reconstructed registry and public probe service")]
pub struct Cli {
    #[arg(long, env = "CONTROL_PLANE_LISTEN", default_value = "127.0.0.1:8080")]
    pub listen: String,
    #[arg(long, env = "CONTROL_PLANE_ADMIN_TOKEN", hide_env_values = true)]
    pub admin_token: String,
    #[arg(long, env = "CONTROL_PLANE_DEVICE_TOKEN", hide_env_values = true)]
    pub device_token: String,
    #[arg(
        long,
        env = "CONTROL_PLANE_STATE_BACKEND",
        value_enum,
        default_value = "sqlite"
    )]
    pub state_backend: StateBackend,
    #[arg(long, env = "CONTROL_PLANE_STATE_PATH")]
    pub state_path: Option<PathBuf>,
}

impl Cli {
    pub fn resolved_state_path(&self) -> PathBuf {
        self.state_path
            .clone()
            .unwrap_or_else(|| self.state_backend.default_state_path())
    }
}

#[cfg(test)]
#[path = "cli_backend_tests.rs"]
mod backend_tests;
