use std::collections::{HashMap, VecDeque};
use std::fs;
use std::io::Write;
use std::path::{Path, PathBuf};
use std::sync::Arc;

use anyhow::{Context, Result, anyhow};
use mobile_proxy_application::{
    IssueCommandError, IssueCommandFuture, IssueCommandInput, IssueCommandOutcome,
    IssueCommandPort, MAX_COMMAND_QUEUE_PER_DEVICE, MAX_IDEMPOTENCY_RESULTS, classify_existing,
    idempotency_scope_key,
};
use mobile_proxy_foundation::CommandId;
use proxy_core::{DeviceCommand, DeviceRecord};
use serde::{Deserialize, Serialize};
use tokio::sync::Mutex;
use uuid::Uuid;

use crate::fingerprint_migration::normalize_persisted_fingerprints;
use crate::projection::now_unix_secs;

#[derive(Clone)]
pub struct AppState {
    pub devices: Arc<Mutex<HashMap<String, DeviceRecord>>>,
    pub commands: Arc<Mutex<CommandState>>,
    state_path: Arc<PathBuf>,
}

#[derive(Default, Clone, Serialize, Deserialize)]
pub struct CommandState {
    pub queues: HashMap<String, VecDeque<DeviceCommand>>,
    pub idempotency: HashMap<String, CommandId>,
    #[serde(default)]
    pub idempotency_results: HashMap<String, DeviceCommand>,
    #[serde(default)]
    pub idempotency_order: VecDeque<String>,
}

#[derive(Default, Clone, Serialize, Deserialize)]
struct StoredState {
    devices: HashMap<String, DeviceRecord>,
    commands: CommandState,
}

#[derive(Default)]
struct CommandStateMigration {
    recovered_results: u64,
    canonicalized_keys: u64,
    rebuilt_order: u64,
    evicted_entries: u64,
}

impl CommandStateMigration {
    fn changed(&self) -> bool {
        self.recovered_results > 0
            || self.canonicalized_keys > 0
            || self.rebuilt_order > 0
            || self.evicted_entries > 0
    }
}

impl AppState {
    pub async fn load(state_path: PathBuf) -> Result<Self> {
        let stored = match fs::read_to_string(&state_path) {
            Ok(body) => {
                let (normalized, fingerprint_migration) =
                    normalize_persisted_fingerprints(&body)
                        .with_context(|| format!("failed to migrate {}", state_path.display()))?;
                let mut stored: StoredState = serde_json::from_value(normalized)
                    .with_context(|| format!("failed to parse {}", state_path.display()))?;
                let command_migration = normalize_command_state(&mut stored.commands)
                    .map_err(|_| anyhow!("persisted command idempotency state is inconsistent"))?;
                if fingerprint_migration.total() > 0 || command_migration.changed() {
                    write_stored_state(&state_path, &stored).with_context(|| {
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
                stored
            }
            Err(err) if err.kind() == std::io::ErrorKind::NotFound => StoredState::default(),
            Err(err) => {
                return Err(err)
                    .with_context(|| format!("failed to read {}", state_path.display()));
            }
        };
        Ok(Self {
            devices: Arc::new(Mutex::new(stored.devices)),
            commands: Arc::new(Mutex::new(stored.commands)),
            state_path: Arc::new(state_path),
        })
    }

    pub async fn persist(&self) -> Result<()> {
        let devices = self.devices.lock().await;
        let commands = self.commands.lock().await;
        let stored = StoredState {
            devices: devices.clone(),
            commands: commands.clone(),
        };
        write_stored_state(self.state_path.as_ref(), &stored)
    }

    async fn issue_command_transaction(
        &self,
        input: IssueCommandInput,
    ) -> Result<IssueCommandOutcome, IssueCommandError> {
        let mut devices_guard = self.devices.lock().await;
        let mut commands_guard = self.commands.lock().await;
        let mut devices = devices_guard.clone();
        let mut commands = commands_guard.clone();

        let migration =
            normalize_command_state(&mut commands).map_err(|_| IssueCommandError::StateConflict)?;
        let scope =
            idempotency_scope_key(&input.device_id, &input.request.idempotency_key).to_string();
        let legacy_scope = legacy_idempotency_scope_key(&input);

        if let Some(existing) = commands.idempotency_results.get(&scope) {
            let original = classify_existing(existing, &input.device_id, &input.request)?;
            if migration.changed() {
                persist_candidate(self.state_path.as_ref(), &devices, &commands)?;
                *devices_guard = devices;
                *commands_guard = commands;
            }
            return Ok(IssueCommandOutcome::ExactDuplicate(original));
        }

        if commands.idempotency.contains_key(&scope)
            || commands.idempotency.contains_key(&legacy_scope)
        {
            return Err(IssueCommandError::IdempotencyConflict);
        }

        let command = DeviceCommand {
            command_id: CommandId::from_uuid(Uuid::new_v4()),
            device_id: input.device_id.clone(),
            desired_state: input.request.desired_state,
            recovery_intent: input.request.recovery_intent,
            deadline_secs: input.request.deadline_secs,
            idempotency_key: input.request.idempotency_key,
            issued_at: now_unix_secs(),
        };
        let queue = commands.queues.entry(input.device_id.clone()).or_default();
        queue.push_back(command.clone());
        while queue.len() > MAX_COMMAND_QUEUE_PER_DEVICE {
            queue.pop_front();
        }

        commands
            .idempotency
            .insert(scope.clone(), command.command_id);
        commands
            .idempotency_results
            .insert(scope.clone(), command.clone());
        commands.idempotency_order.push_back(scope);
        trim_idempotency_state(&mut commands);

        if let Some(device) = devices.get_mut(&input.device_id) {
            device.desired_state = Some(command.desired_state.to_string());
            device.recovery_intent = Some(command.recovery_intent.to_string());
            device.last_event_at = Some(command.issued_at.clone());
        }

        persist_candidate(self.state_path.as_ref(), &devices, &commands)?;
        *devices_guard = devices;
        *commands_guard = commands;
        Ok(IssueCommandOutcome::Created(command))
    }
}

impl IssueCommandPort for AppState {
    fn issue_command(&self, input: IssueCommandInput) -> IssueCommandFuture<'_> {
        Box::pin(async move { self.issue_command_transaction(input).await })
    }
}

fn legacy_idempotency_scope_key(input: &IssueCommandInput) -> String {
    format!("{}:{}", input.device_id, input.request.idempotency_key)
}

fn normalize_command_state(commands: &mut CommandState) -> Result<CommandStateMigration, ()> {
    let mut migration = CommandStateMigration::default();

    let result_entries: Vec<(String, DeviceCommand)> = commands
        .idempotency_results
        .iter()
        .map(|(key, command)| (key.clone(), command.clone()))
        .collect();
    for (stored_key, command) in result_entries {
        let canonical =
            idempotency_scope_key(&command.device_id, &command.idempotency_key).to_string();
        if stored_key != canonical {
            commands.idempotency_results.remove(&stored_key);
            if let Some(existing) = commands.idempotency_results.get(&canonical)
                && existing != &command
            {
                return Err(());
            }
            commands
                .idempotency_results
                .insert(canonical.clone(), command.clone());
            if let Some(command_id) = commands.idempotency.remove(&stored_key) {
                if command_id != command.command_id {
                    return Err(());
                }
                commands.idempotency.insert(canonical, command_id);
            }
            migration.canonicalized_keys += 1;
        }
    }

    let claim_entries: Vec<(String, CommandId)> = commands
        .idempotency
        .iter()
        .map(|(key, command_id)| (key.clone(), *command_id))
        .collect();
    for (stored_key, command_id) in claim_entries {
        if let Some(existing) = commands.idempotency_results.get(&stored_key) {
            if existing.command_id != command_id {
                return Err(());
            }
            continue;
        }
        let Some(command) = find_queued_command(commands, command_id).cloned() else {
            continue;
        };
        let canonical =
            idempotency_scope_key(&command.device_id, &command.idempotency_key).to_string();
        if let Some(existing_id) = commands.idempotency.get(&canonical)
            && *existing_id != command_id
        {
            return Err(());
        }
        if let Some(existing) = commands.idempotency_results.get(&canonical)
            && existing != &command
        {
            return Err(());
        }
        if stored_key != canonical {
            commands.idempotency.remove(&stored_key);
            commands.idempotency.insert(canonical.clone(), command_id);
            migration.canonicalized_keys += 1;
        }
        commands.idempotency_results.insert(canonical, command);
        migration.recovered_results += 1;
    }

    let canonical_results: Vec<(String, CommandId)> = commands
        .idempotency_results
        .iter()
        .map(|(key, command)| (key.clone(), command.command_id))
        .collect();
    for (key, command_id) in canonical_results {
        if let Some(existing_id) = commands.idempotency.get(&key) {
            if *existing_id != command_id {
                return Err(());
            }
        } else {
            commands.idempotency.insert(key, command_id);
            migration.recovered_results += 1;
        }
    }

    let original_order = std::mem::take(&mut commands.idempotency_order);
    let mut normalized_order = VecDeque::new();
    for key in &original_order {
        if commands.idempotency.contains_key(key) && !normalized_order.contains(key) {
            normalized_order.push_back(key.clone());
        }
    }
    let mut missing: Vec<String> = commands
        .idempotency
        .keys()
        .filter(|key| !normalized_order.contains(key))
        .cloned()
        .collect();
    missing.sort();
    normalized_order.extend(missing);
    if normalized_order != original_order {
        migration.rebuilt_order = 1;
    }
    commands.idempotency_order = normalized_order;
    migration.evicted_entries = trim_idempotency_state(commands);
    Ok(migration)
}

fn find_queued_command(commands: &CommandState, command_id: CommandId) -> Option<&DeviceCommand> {
    commands
        .queues
        .values()
        .flat_map(|queue| queue.iter())
        .find(|command| command.command_id == command_id)
}

fn trim_idempotency_state(commands: &mut CommandState) -> u64 {
    let mut evicted = 0;
    while commands.idempotency_order.len() > MAX_IDEMPOTENCY_RESULTS {
        let Some(key) = commands.idempotency_order.pop_front() else {
            break;
        };
        commands.idempotency.remove(&key);
        commands.idempotency_results.remove(&key);
        evicted += 1;
    }
    evicted
}

fn persist_candidate(
    path: &Path,
    devices: &HashMap<String, DeviceRecord>,
    commands: &CommandState,
) -> Result<(), IssueCommandError> {
    let stored = StoredState {
        devices: devices.clone(),
        commands: commands.clone(),
    };
    write_stored_state(path, &stored).map_err(|_| IssueCommandError::Persistence)
}

fn write_stored_state(path: &Path, stored: &StoredState) -> Result<()> {
    let body = serde_json::to_vec_pretty(stored)?;
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent)?;
    }
    let tmp = path.with_extension("json.tmp");
    let mut file = fs::File::create(&tmp)?;
    file.write_all(&body)?;
    file.sync_all()?;
    drop(file);
    fs::rename(&tmp, path)?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use std::collections::HashMap;
    use std::fs;
    use std::sync::Arc;

    use mobile_proxy_application::{
        IssueCommandError, IssueCommandInput, IssueCommandOutcome, IssueCommandPort,
    };
    use mobile_proxy_foundation::{DeadlineWindow, IdempotencyKey};
    use proxy_core::{DesiredState, IssueCommandRequest, RecoveryIntent};
    use serde_json::json;
    use tokio::sync::Mutex;
    use uuid::Uuid;

    use super::{AppState, CommandState};

    fn command_input(desired_state: DesiredState) -> IssueCommandInput {
        IssueCommandInput {
            device_id: "device-1".into(),
            request: IssueCommandRequest {
                desired_state,
                recovery_intent: RecoveryIntent::None,
                deadline_secs: DeadlineWindow::new(30).unwrap(),
                idempotency_key: IdempotencyKey::parse("command-123").unwrap(),
            },
        }
    }

    #[tokio::test]
    async fn legacy_fingerprint_migration_is_restart_safe() {
        let path = std::env::temp_dir().join(format!(
            "mobile-proxy-control-plane-fingerprint-migration-{}.json",
            Uuid::new_v4()
        ));
        fs::write(
            &path,
            serde_json::to_vec_pretty(&json!({
                "devices": {
                    "node": {
                        "node_id": "node",
                        "node_name": "node",
                        "readiness_state": "booting",
                        "serving": false,
                        "proxy_status": "starting",
                        "proxy_pid": null,
                        "last_public_ip": null,
                        "current_job": null,
                        "last_proxy_error": null,
                        "version": null,
                        "config_fingerprint": "legacy-config",
                        "binary_fingerprint": "legacy-binary",
                        "active_operator_profile": null,
                        "active_operator_plmn": null,
                        "publicly_serving": false,
                        "public_probe_error": null,
                        "public_probe_at": null,
                        "cellular_route_ready": null,
                        "proxy_bind_ready": null,
                        "local_serving_ready": null,
                        "tun0_present": null,
                        "wg_handshake_recent": null,
                        "reverse_tunnel_connected": null,
                        "reverse_tunnel_last_error": null,
                        "reverse_tunnel_active_transport": null,
                        "reverse_tunnel_freshness": null,
                        "reverse_tunnel_failover_reason": null,
                        "tunnel_owner": null,
                        "last_heartbeat_at": null,
                        "availability": "degraded",
                        "degradation_reason_code": null,
                        "serving_failure_reason": null,
                        "desired_state": null,
                        "recovery_intent": null,
                        "last_event_at": null
                    }
                },
                "commands": {"queues": {}, "idempotency": {}}
            }))
            .unwrap(),
        )
        .unwrap();

        let first = AppState::load(path.clone()).await.unwrap();
        let device = first.devices.lock().await.get("node").unwrap().clone();
        assert!(device.config_fingerprint.is_none());
        assert!(device.binary_fingerprint.is_none());
        drop(first);

        let second = AppState::load(path.clone()).await.unwrap();
        let device = second.devices.lock().await.get("node").unwrap().clone();
        assert!(device.config_fingerprint.is_none());
        assert!(device.binary_fingerprint.is_none());
        let _ = fs::remove_file(path);
    }

    #[tokio::test]
    async fn exact_duplicate_survives_queue_removal() {
        let path = std::env::temp_dir().join(format!(
            "mobile-proxy-control-plane-command-idempotency-{}.json",
            Uuid::new_v4()
        ));
        let state = AppState::load(path.clone()).await.unwrap();
        let first = state
            .issue_command(command_input(DesiredState::HealthyServing))
            .await
            .unwrap();
        let (_, original) = first.into_parts();
        state.commands.lock().await.queues.clear();
        state.persist().await.unwrap();

        let duplicate = state
            .issue_command(command_input(DesiredState::HealthyServing))
            .await
            .unwrap();
        assert_eq!(duplicate, IssueCommandOutcome::ExactDuplicate(original));
        let _ = fs::remove_file(path);
    }

    #[tokio::test]
    async fn reused_key_with_changed_parameters_fails_closed() {
        let path = std::env::temp_dir().join(format!(
            "mobile-proxy-control-plane-command-conflict-{}.json",
            Uuid::new_v4()
        ));
        let state = AppState::load(path.clone()).await.unwrap();
        state
            .issue_command(command_input(DesiredState::HealthyServing))
            .await
            .unwrap();
        let conflict = state
            .issue_command(command_input(DesiredState::DegradedSafe))
            .await;
        assert_eq!(conflict, Err(IssueCommandError::IdempotencyConflict));
        let _ = fs::remove_file(path);
    }

    #[tokio::test]
    async fn failed_persistence_does_not_publish_in_memory_command() {
        let blocking_parent = std::env::temp_dir().join(format!(
            "mobile-proxy-control-plane-command-persistence-{}",
            Uuid::new_v4()
        ));
        fs::write(&blocking_parent, b"not a directory").unwrap();
        let state = AppState {
            devices: Arc::new(Mutex::new(HashMap::new())),
            commands: Arc::new(Mutex::new(CommandState::default())),
            state_path: Arc::new(blocking_parent.join("state.json")),
        };

        let result = state
            .issue_command(command_input(DesiredState::HealthyServing))
            .await;
        assert_eq!(result, Err(IssueCommandError::Persistence));
        assert!(state.commands.lock().await.queues.is_empty());
        let _ = fs::remove_file(blocking_parent);
    }
}
