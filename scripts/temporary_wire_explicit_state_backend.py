from pathlib import Path


def replace_once(body: str, old: str, new: str, label: str) -> str:
    count = body.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected one match, found {count}")
    return body.replace(old, new, 1)


def patch_cli() -> None:
    path = Path("services/control-plane/src/cli.rs")
    body = path.read_text()
    body = replace_once(body, "use clap::Parser;", "use clap::{Parser, ValueEnum};", "clap import")
    enum = '''
#[derive(ValueEnum, Clone, Copy, Debug, Default, PartialEq, Eq)]
#[value(rename_all = "snake_case")]
pub enum StateBackend {
    #[default]
    Json,
    Sqlite,
}

'''
    body = replace_once(body, "#[derive(Parser, Debug)]", enum + "#[derive(Parser, Debug)]", "backend enum")
    field = '''    #[arg(
        long,
        env = "CONTROL_PLANE_STATE_BACKEND",
        value_enum,
        default_value = "json"
    )]
    pub state_backend: StateBackend,
'''
    anchor = '''    #[arg(
        long,
        env = "CONTROL_PLANE_STATE_PATH",
'''
    body = replace_once(body, anchor, field + anchor, "backend CLI field")
    include = '''
#[cfg(test)]
#[path = "cli_backend_tests.rs"]
mod backend_tests;
'''
    if "mod backend_tests;" in body:
        raise SystemExit("CLI backend tests already wired")
    body += include
    path.write_text(body)


def patch_main() -> None:
    path = Path("services/control-plane/src/main.rs")
    body = path.read_text()
    body = replace_once(body, "mod state;", "mod state;\nmod state_sqlite_backend;", "SQLite backend module")
    body = replace_once(
        body,
        "let app = router(AppState::load(cli.state_path).await?, auth);",
        '''let app = router(
        AppState::load_with_backend(cli.state_path, cli.state_backend).await?,
        auth,
    );''',
        "composition root backend selection",
    )
    path.write_text(body)


def load_json_helper() -> str:
    return '''
fn load_json_state(state_path: &Path) -> Result<StoredState> {
    match fs::read_to_string(state_path) {
        Ok(body) => {
            let (normalized, fingerprint_migration) = normalize_persisted_fingerprints(&body)
                .with_context(|| format!("failed to migrate {}", state_path.display()))?;
            let mut stored: StoredState = serde_json::from_value(normalized)
                .with_context(|| format!("failed to parse {}", state_path.display()))?;
            let command_migration = normalize_command_state(&mut stored.commands)
                .map_err(|_| anyhow!("persisted command idempotency state is inconsistent"))?;
            if fingerprint_migration.total() > 0 || command_migration.changed() {
                write_stored_state(state_path, &stored).with_context(|| {
                    format!("failed to persist migrated {}", state_path.display())
                })?;
            }
            if fingerprint_migration.total() > 0 {
                tracing::warn!(
                    legacy_config_fingerprints = fingerprint_migration.legacy_config_values,
                    legacy_binary_fingerprints = fingerprint_migration.legacy_binary_values,
                    "legacy persisted fingerprints removed for typed heartbeat backfill"
                );
            }
            if command_migration.changed() {
                tracing::warn!(
                    recovered_idempotency_results = command_migration.recovered_results,
                    canonicalized_idempotency_keys = command_migration.canonicalized_keys,
                    rebuilt_idempotency_order = command_migration.rebuilt_order,
                    evicted_idempotency_entries = command_migration.evicted_entries,
                    "legacy command idempotency state normalized"
                );
            }
            Ok(stored)
        }
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => Ok(StoredState::default()),
        Err(error) => {
            Err(error).with_context(|| format!("failed to read {}", state_path.display()))
        }
    }
}

'''


def patch_state() -> None:
    path = Path("services/control-plane/src/state.rs")
    body = path.read_text()
    body = replace_once(
        body,
        "use crate::fingerprint_migration::normalize_persisted_fingerprints;",
        "use crate::cli::StateBackend;\nuse crate::fingerprint_migration::normalize_persisted_fingerprints;\nuse crate::state_sqlite_backend;",
        "state backend imports",
    )
    body = replace_once(
        body,
        "    state_path: Arc<PathBuf>,\n}",
        "    state_path: Arc<PathBuf>,\n    state_backend: StateBackend,\n}",
        "AppState backend field",
    )
    body = replace_once(
        body,
        '''struct StoredState {
    devices: HashMap<String, DeviceRecord>,
    commands: CommandState,
}''',
        '''pub(crate) struct StoredState {
    pub(crate) devices: HashMap<String, DeviceRecord>,
    pub(crate) commands: CommandState,
}''',
        "StoredState visibility",
    )

    start = body.index("    pub async fn load(state_path: PathBuf) -> Result<Self> {")
    end = body.index("\n    #[cfg(test)]", start)
    new_load = '''    pub async fn load(state_path: PathBuf) -> Result<Self> {
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

    fn persist_candidate(
        &self,
        expected_devices: &HashMap<String, DeviceRecord>,
        expected_commands: &CommandState,
        candidate_devices: &HashMap<String, DeviceRecord>,
        candidate_commands: &CommandState,
    ) -> Result<()> {
        let candidate = StoredState {
            devices: candidate_devices.clone(),
            commands: candidate_commands.clone(),
        };
        match self.state_backend {
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
    }
'''
    body = body[:start] + new_load + body[end:]

    old = '''    #[cfg(test)]
    async fn persist_for_test(&self) -> Result<()> {
        let devices = self.devices.lock().await;
        let commands = self.commands.lock().await;
        let stored = StoredState {
            devices: devices.clone(),
            commands: commands.clone(),
        };
        write_stored_state(self.state_path.as_ref(), &stored)
    }
'''
    new = '''    #[cfg(test)]
    async fn persist_for_test(&self) -> Result<()> {
        let devices = self.devices.lock().await;
        let commands = self.commands.lock().await;
        let stored = StoredState {
            devices: devices.clone(),
            commands: commands.clone(),
        };
        match self.state_backend {
            StateBackend::Json => write_stored_state(self.state_path.as_ref(), &stored),
            StateBackend::Sqlite => {
                state_sqlite_backend::replace_for_test(self.state_path.as_ref(), &stored)
            }
        }
    }
'''
    body = replace_once(body, old, new, "test persistence")

    mutation_replacements = [
        (
            '''        let stored = StoredState {
            devices: devices.clone(),
            commands: commands_guard.clone(),
        };
        write_stored_state(self.state_path.as_ref(), &stored)
            .map_err(|_| RegisterDeviceError::Persistence)?;
''',
            '''        self.persist_candidate(
            &devices_guard,
            &commands_guard,
            &devices,
            &commands_guard,
        )
        .map_err(|_| RegisterDeviceError::Persistence)?;
''',
            "registration persistence",
        ),
        (
            '''        let stored = StoredState {
            devices: devices.clone(),
            commands: commands_guard.clone(),
        };
        write_stored_state(self.state_path.as_ref(), &stored)
            .map_err(|_| HeartbeatError::Persistence)?;
''',
            '''        self.persist_candidate(
            &devices_guard,
            &commands_guard,
            &devices,
            &commands_guard,
        )
        .map_err(|_| HeartbeatError::Persistence)?;
''',
            "heartbeat persistence",
        ),
        (
            '''        let stored = StoredState {
            devices: devices.clone(),
            commands: commands_guard.clone(),
        };
        write_stored_state(self.state_path.as_ref(), &stored)
            .map_err(|_| PublicProbeError::Persistence)?;
''',
            '''        self.persist_candidate(
            &devices_guard,
            &commands_guard,
            &devices,
            &commands_guard,
        )
        .map_err(|_| PublicProbeError::Persistence)?;
''',
            "public probe persistence",
        ),
        (
            '''        let stored = StoredState {
            devices: devices.clone(),
            commands: commands.clone(),
        };
        write_stored_state(self.state_path.as_ref(), &stored)
            .map_err(|_| AcknowledgeCommandError::Persistence)?;
''',
            '''        self.persist_candidate(
            &devices_guard,
            &commands_guard,
            &devices,
            &commands,
        )
        .map_err(|_| AcknowledgeCommandError::Persistence)?;
''',
            "acknowledgement persistence",
        ),
    ]
    for old, new, label in mutation_replacements:
        body = replace_once(body, old, new, label)

    issue_start = body.index("    async fn issue_command_transaction(")
    issue_end = body.index("\n    async fn poll_command_query(", issue_start)
    issue = body[issue_start:issue_end]
    clone_anchor = '''        let mut devices = devices_guard.clone();
        let mut commands = commands_guard.clone();
'''
    clone_replacement = clone_anchor + '''        let expected_devices = devices.clone();
        let expected_commands = commands.clone();
'''
    issue = replace_once(issue, clone_anchor, clone_replacement, "issue expected snapshot")
    old_persist = "persist_candidate(self.state_path.as_ref(), &devices, &commands)?;"
    if issue.count(old_persist) != 2:
        raise SystemExit(f"issue persistence: expected two matches, found {issue.count(old_persist)}")
    new_persist = '''self.persist_candidate(
                    &expected_devices,
                    &expected_commands,
                    &devices,
                    &commands,
                )
                .map_err(|_| IssueCommandError::Persistence)?;'''
    issue = issue.replace(old_persist, new_persist, 2)
    body = body[:issue_start] + issue + body[issue_end:]

    free_start = body.index("\nfn persist_candidate(\n")
    free_end = body.index("\nfn write_stored_state(", free_start)
    body = body[:free_start] + body[free_end:]

    body = replace_once(body, "impl AppState {", load_json_helper() + "impl AppState {", "JSON loader extraction")

    test_marker = "#[cfg(test)]\nmod tests {"
    test_index = body.index(test_marker)
    head, tail = body[:test_index], body[test_index:]
    tail = replace_once(
        tail,
        "use super::{AppState, CommandState};",
        "use super::{AppState, CommandState, StateBackend};",
        "test backend import",
    )
    count = tail.count("state_path: Arc::new(")
    if count != 16:
        raise SystemExit(f"test AppState literals: expected 16, found {count}")
    lines = tail.splitlines(keepends=True)
    patched: list[str] = []
    inserted = 0
    for line in lines:
        patched.append(line)
        if line.lstrip().startswith("state_path: Arc::new("):
            indent = line[: len(line) - len(line.lstrip())]
            patched.append(f"{indent}state_backend: StateBackend::Json,\n")
            inserted += 1
    if inserted != 16:
        raise SystemExit(f"test backend fields: expected 16, inserted {inserted}")
    body = head + "".join(patched)
    body += '''
#[cfg(test)]
#[path = "state_sqlite_backend_tests.rs"]
mod sqlite_backend_tests;
'''
    path.write_text(body)


def patch_sqlite_tests() -> None:
    path = Path("services/control-plane/src/state_sqlite_backend_tests.rs")
    body = path.read_text()
    old = '''    let error = AppState::load_with_backend(database.path.clone(), StateBackend::Sqlite)
        .await
        .unwrap_err();
'''
    new = '''    let error = match AppState::load_with_backend(database.path.clone(), StateBackend::Sqlite)
        .await
    {
        Ok(_) => panic!("missing SQLite state unexpectedly started"),
        Err(error) => error,
    };
'''
    body = replace_once(body, old, new, "missing SQLite startup assertion")
    path.write_text(body)


patch_cli()
patch_main()
patch_state()
patch_sqlite_tests()
