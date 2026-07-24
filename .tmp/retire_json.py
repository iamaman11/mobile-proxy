from pathlib import Path
import re

root = Path.cwd()
state_path = root / "services/control-plane/src/state.rs"
s = state_path.read_text()

s = s.replace(
    "use std::fs;\nuse std::io::Write;\nuse std::path::{Path, PathBuf};",
    "use std::path::PathBuf;",
)
s = s.replace("use anyhow::{Context, Result, anyhow};", "use anyhow::Result;")
s = s.replace("use serde::{Deserialize, Serialize};\n", "")
s = s.replace("use crate::cli::StateBackend;\n", "")
s = s.replace("use crate::fingerprint_migration::normalize_persisted_fingerprints;\n", "")
s = s.replace(
    "    state_path: Arc<PathBuf>,\n    state_backend: StateBackend,",
    "    state_path: Arc<PathBuf>,",
)
s = s.replace(
    "#[derive(Default, Clone, Serialize, Deserialize)]\npub struct CommandState {",
    "#[derive(Default, Clone)]\npub struct CommandState {",
)
s = s.replace("    #[serde(default)]\n    pub idempotency_results:", "    pub idempotency_results:")
s = s.replace("    #[serde(default)]\n    pub idempotency_order:", "    pub idempotency_order:")
s = s.replace(
    "#[derive(Default, Clone, Serialize, Deserialize)]\npub(crate) struct StoredState {",
    "#[derive(Default, Clone)]\npub(crate) struct StoredState {",
)

s = re.sub(
    r"\nfn load_json_state\(state_path: &Path\) -> Result<StoredState> \{.*?\n\}\n\nimpl AppState \{",
    "\nimpl AppState {",
    s,
    flags=re.S,
)

old = '''impl AppState {
    #[cfg(test)]
    pub async fn load(state_path: PathBuf) -> Result<Self> {
        Self::load_with_backend(state_path, StateBackend::Json).await
    }

    pub async fn load_with_backend(
        state_path: PathBuf,
        state_backend: StateBackend,
    ) -> Result<Self> {
        let stored = match state_backend {
            StateBackend::Json => load_json_state(&state_path)?,
            StateBackend::Sqlite => state_sqlite_backend::load_existing(&state_path)?,
        };
        Ok(Self {
            devices: Arc::new(Mutex::new(stored.devices)),
            commands: Arc::new(Mutex::new(stored.commands)),
            state_path: Arc::new(state_path),
            state_backend,
        })
    }
'''
new = '''impl AppState {
    pub async fn load(state_path: PathBuf) -> Result<Self> {
        let stored = state_sqlite_backend::load_existing(&state_path)?;
        Ok(Self {
            devices: Arc::new(Mutex::new(stored.devices)),
            commands: Arc::new(Mutex::new(stored.commands)),
            state_path: Arc::new(state_path),
        })
    }
'''
if old not in s:
    raise SystemExit("AppState load block not found")
s = s.replace(old, new)

old = '''        match self.state_backend {
            StateBackend::Json => write_stored_state(self.state_path.as_ref(), &candidate),
            StateBackend::Sqlite => {
                let expected = StoredState {
                    devices: expected_devices.clone(),
                    commands: expected_commands.clone(),
                };
                let changes = state_sqlite_backend::compare_and_swap(
                    self.state_path.as_ref(),
                    &expected,
                    &candidate,
                )?;
                tracing::debug!(
                    devices_upserted = changes.devices_upserted,
                    devices_deleted = changes.devices_deleted,
                    command_results_inserted = changes.command_results_inserted,
                    command_results_deleted = changes.command_results_deleted,
                    idempotency_claims_inserted = changes.idempotency_claims_inserted,
                    idempotency_claims_deleted = changes.idempotency_claims_deleted,
                    pending_commands_inserted = changes.pending_commands_inserted,
                    pending_commands_deleted = changes.pending_commands_deleted,
                    "SQLite control-plane candidate committed"
                );
                Ok(())
            }
        }
'''
new = '''        let expected = StoredState {
            devices: expected_devices.clone(),
            commands: expected_commands.clone(),
        };
        let changes = state_sqlite_backend::compare_and_swap(
            self.state_path.as_ref(),
            &expected,
            &candidate,
        )?;
        tracing::debug!(
            devices_upserted = changes.devices_upserted,
            devices_deleted = changes.devices_deleted,
            command_results_inserted = changes.command_results_inserted,
            command_results_deleted = changes.command_results_deleted,
            idempotency_claims_inserted = changes.idempotency_claims_inserted,
            idempotency_claims_deleted = changes.idempotency_claims_deleted,
            pending_commands_inserted = changes.pending_commands_inserted,
            pending_commands_deleted = changes.pending_commands_deleted,
            "SQLite control-plane candidate committed"
        );
        Ok(())
'''
if old not in s:
    raise SystemExit("persist match block not found")
s = s.replace(old, new)

old = '''        match self.state_backend {
            StateBackend::Json => write_stored_state(self.state_path.as_ref(), &stored),
            StateBackend::Sqlite => {
                state_sqlite_backend::replace_for_test(self.state_path.as_ref(), &stored)
            }
        }
'''
new = '''        state_sqlite_backend::replace_for_test(self.state_path.as_ref(), &stored)
'''
if old not in s:
    raise SystemExit("persist_for_test match not found")
s = s.replace(old, new)

s = re.sub(
    r"\nfn write_stored_state\(path: &Path, stored: &StoredState\) -> Result<\(\)> \{.*?\n\}\n\n#\[cfg\(test\)\]",
    "\n#[cfg(test)]",
    s,
    flags=re.S,
)

for name in [
    "legacy_fingerprint_migration_is_restart_safe",
    "rollback_writer_can_drop_new_fields_without_losing_pending_dedupe",
]:
    pattern = rf"\n    #\[tokio::test\]\n    async fn {name}\(\) \{{.*?(?=\n    #\[tokio::test\])"
    s, count = re.subn(pattern, "", s, flags=re.S)
    if count != 1:
        raise SystemExit(f"failed removing {name}: {count}")

s = s.replace(
    "    use super::{AppState, CommandState, StateBackend};",
    "    use super::{AppState, CommandState, StoredState};",
)
s = s.replace("            state_backend: StateBackend::Json,\n", "")

anchor = "    use super::{AppState, CommandState, StoredState};\n\n"
helper = '''    use super::{AppState, CommandState, StoredState};

    struct TempState {
        path: std::path::PathBuf,
    }

    impl TempState {
        fn initialized(label: &str, stored: &StoredState) -> Self {
            let path = std::env::temp_dir().join(format!(
                "mobile-proxy-control-plane-{label}-{}.sqlite3",
                Uuid::new_v4()
            ));
            crate::state_sqlite_backend::replace_for_test(&path, stored).unwrap();
            Self { path }
        }
    }

    impl Drop for TempState {
        fn drop(&mut self) {
            let _ = fs::remove_file(&self.path);
            for suffix in ["-wal", "-shm"] {
                let mut sidecar = self.path.as_os_str().to_os_string();
                sidecar.push(suffix);
                let _ = fs::remove_file(std::path::PathBuf::from(sidecar));
            }
        }
    }

    async fn load_state(label: &str, stored: StoredState) -> (TempState, AppState) {
        let database = TempState::initialized(label, &stored);
        let state = AppState::load(database.path.clone()).await.unwrap();
        (database, state)
    }

'''
if anchor not in s:
    raise SystemExit("test helper anchor not found")
s = s.replace(anchor, helper, 1)

pattern = re.compile(r'''        let path = std::env::temp_dir\(\)\.join\(format!\(\n            "mobile-proxy-control-plane-([^"{]+)-\{\}\.json",\n            Uuid::new_v4\(\)\n        \)\);\n        let state = AppState::load\(path\.clone\(\)\)\.await\.unwrap\(\);''')

def repl(match):
    label = match.group(1)
    return f'        let (database, state) = load_state("{label}", StoredState::default()).await;'

s, count = pattern.subn(repl, s)
print("replaced common load blocks", count)
s = s.replace(
    "AppState::load(path.clone()).await.unwrap()",
    "AppState::load(database.path.clone()).await.unwrap()",
)
s = s.replace("        let _ = fs::remove_file(path);\n", "")

old = '''        let path = std::env::temp_dir().join(format!(
            "mobile-proxy-control-plane-heartbeat-capacity-{}.json",
            Uuid::new_v4()
        ));
        let state = AppState {
            devices: Arc::new(Mutex::new(devices)),
            commands: Arc::new(Mutex::new(CommandState::default())),
            state_path: Arc::new(path.clone()),
        };
'''
new = '''        let (database, state) = load_state(
            "heartbeat-capacity",
            StoredState {
                devices,
                commands: CommandState::default(),
            },
        )
        .await;
'''
if old not in s:
    raise SystemExit("heartbeat capacity block not found")
s = s.replace(old, new)

s = re.sub(
    r"let \(database, state\) = load_state\((.*?)\)\.await;",
    r"let (_database, state) = load_state(\1).await;",
    s,
    flags=re.S,
)
for test_name in [
    "registration_is_durable_and_preserves_first_registered_metadata",
    "heartbeat_is_durable_and_preserves_public_probe_projection",
    "public_probe_is_durable_and_uses_an_authoritative_timestamp",
    "positive_acknowledgement_is_durable_and_preserves_exact_replay",
]:
    start = s.index(f"async fn {test_name}")
    end = s.find("\n    #[tokio::test]", start)
    if end == -1:
        end = len(s)
    segment = s[start:end].replace("let (_database, state)", "let (database, state)", 1)
    s = s[:start] + segment + s[end:]

s = s.replace("        let _ = fs::remove_file(path);\n", "")
state_path.write_text(s)

(root / "services/control-plane/src/cli.rs").write_text('''use clap::Parser;
use std::path::PathBuf;

const SQLITE_STATE_PATH: &str = "/var/lib/mobile-relaycontrolpoint/control-plane-state.sqlite3";

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
        env = "CONTROL_PLANE_STATE_PATH",
        default_value = SQLITE_STATE_PATH
    )]
    pub state_path: PathBuf,
}

#[cfg(test)]
#[path = "cli_backend_tests.rs"]
mod backend_tests;
''')

(root / "services/control-plane/src/cli_backend_tests.rs").write_text('''use std::path::PathBuf;

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
''')

main = root / "services/control-plane/src/main.rs"
m = main.read_text()
m = m.replace("mod fingerprint_migration;\n", "")
m = m.replace("    let state_path = cli.resolved_state_path();\n", "")
m = m.replace(
    "        AppState::load_with_backend(state_path, cli.state_backend).await?,",
    "        AppState::load(cli.state_path).await?,",
)
main.write_text(m)

p = root / "services/control-plane/src/state_sqlite_backend_tests.rs"
t = p.read_text()
t = t.replace("use crate::cli::StateBackend;\n\n", "")
t = t.replace(
    "AppState::load_with_backend(database.path.clone(), StateBackend::Sqlite)",
    "AppState::load(database.path.clone())",
)
p.write_text(t)

(root / "services/control-plane/src/fingerprint_migration.rs").unlink()
