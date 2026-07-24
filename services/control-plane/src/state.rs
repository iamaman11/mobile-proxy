use std::collections::{HashMap, VecDeque};
use std::path::PathBuf;
use std::sync::Arc;

use anyhow::Result;
use mobile_proxy_application::{
    AcknowledgeCommandError, AcknowledgeCommandFuture, AcknowledgeCommandInput,
    AcknowledgeCommandOutcome, AcknowledgeCommandPort, HeartbeatError, HeartbeatFuture,
    HeartbeatInput, HeartbeatOutcome, HeartbeatPort, IssueCommandError, IssueCommandFuture,
    IssueCommandInput, IssueCommandOutcome, IssueCommandPort, MAX_COMMAND_QUEUE_PER_DEVICE,
    MAX_IDEMPOTENCY_RESULTS, MAX_PENDING_COMMANDS, MAX_REGISTERED_DEVICES, PollCommandError,
    PollCommandFuture, PollCommandInput, PollCommandOutcome, PollCommandPort, PublicProbeError,
    PublicProbeFuture, PublicProbeInput, PublicProbeOutcome, PublicProbePort, RegisterDeviceError,
    RegisterDeviceFuture, RegisterDeviceInput, RegisterDeviceOutcome, RegisterDevicePort,
    classify_existing, idempotency_scope_key,
};
use mobile_proxy_foundation::CommandId;
use proxy_core::{DeviceCommand, DeviceRecord};
use tokio::sync::Mutex;
use uuid::Uuid;

use crate::projection::{
    apply_public_probe, build_heartbeat_device, build_registered_device, now_unix_secs,
};
use crate::state_sqlite_backend;

#[derive(Clone)]
pub struct AppState {
    pub devices: Arc<Mutex<HashMap<String, DeviceRecord>>>,
    pub commands: Arc<Mutex<CommandState>>,
    state_path: Arc<PathBuf>,
}

#[derive(Default, Clone)]
pub struct CommandState {
    pub queues: HashMap<String, VecDeque<DeviceCommand>>,
    pub idempotency: HashMap<String, CommandId>,
    pub idempotency_results: HashMap<String, DeviceCommand>,
    pub idempotency_order: VecDeque<String>,
}

#[derive(Default, Clone)]
pub(crate) struct StoredState {
    pub(crate) devices: HashMap<String, DeviceRecord>,
    pub(crate) commands: CommandState,
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
        let stored = state_sqlite_backend::load_existing(&state_path)?;
        Ok(Self {
            devices: Arc::new(Mutex::new(stored.devices)),
            commands: Arc::new(Mutex::new(stored.commands)),
            state_path: Arc::new(state_path),
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

    #[cfg(test)]
    async fn persist_for_test(&self) -> Result<()> {
        let devices = self.devices.lock().await;
        let commands = self.commands.lock().await;
        let stored = StoredState {
            devices: devices.clone(),
            commands: commands.clone(),
        };
        state_sqlite_backend::replace_for_test(self.state_path.as_ref(), &stored)
    }

    async fn register_device_transaction(
        &self,
        input: RegisterDeviceInput,
    ) -> Result<RegisterDeviceOutcome, RegisterDeviceError> {
        let mut devices_guard = self.devices.lock().await;
        let commands_guard = self.commands.lock().await;
        let mut devices = devices_guard.clone();
        let request = input.request;
        let node_id = request.node_id.clone();

        let outcome = if let Some(existing) = devices.get(&node_id) {
            if existing.node_id != node_id {
                return Err(RegisterDeviceError::StateConflict);
            }
            RegisterDeviceOutcome::AlreadyRegistered
        } else {
            if devices.len() >= MAX_REGISTERED_DEVICES {
                return Err(RegisterDeviceError::CapacityExceeded);
            }
            let device = build_registered_device(request);
            let stored_node_id = device.node_id.clone();
            if devices.insert(stored_node_id, device).is_some() {
                return Err(RegisterDeviceError::StateConflict);
            }
            RegisterDeviceOutcome::Created
        };

        self.persist_candidate(&devices_guard, &commands_guard, &devices, &commands_guard)
            .map_err(|_| RegisterDeviceError::Persistence)?;
        *devices_guard = devices;
        Ok(outcome)
    }

    async fn heartbeat_transaction(
        &self,
        input: HeartbeatInput,
    ) -> Result<HeartbeatOutcome, HeartbeatError> {
        let mut devices_guard = self.devices.lock().await;
        let commands_guard = self.commands.lock().await;
        let mut devices = devices_guard.clone();
        let request = input.request;
        let node_id = request.node_id.clone();
        let legacy_config_fingerprint = request
            .config_fingerprint
            .as_ref()
            .is_some_and(proxy_core::ConfigFingerprintInput::is_legacy);
        let legacy_binary_fingerprint = request
            .binary_fingerprint
            .as_ref()
            .is_some_and(proxy_core::BinaryFingerprintInput::is_legacy);

        if let Some(existing) = devices.get(&node_id) {
            if existing.node_id != node_id {
                return Err(HeartbeatError::StateConflict);
            }
        } else if devices.len() >= MAX_REGISTERED_DEVICES {
            return Err(HeartbeatError::CapacityExceeded);
        }

        let (publicly_serving, public_probe_error, public_probe_at) = devices
            .get(&node_id)
            .map(|device| {
                (
                    device.publicly_serving,
                    device.public_probe_error.clone(),
                    device.public_probe_at.clone(),
                )
            })
            .unwrap_or((false, None, None));
        let device = build_heartbeat_device(
            request,
            publicly_serving,
            public_probe_error,
            public_probe_at,
        );
        if device.node_id != node_id {
            return Err(HeartbeatError::StateConflict);
        }
        devices.insert(node_id, device);

        self.persist_candidate(&devices_guard, &commands_guard, &devices, &commands_guard)
            .map_err(|_| HeartbeatError::Persistence)?;
        *devices_guard = devices;
        Ok(HeartbeatOutcome::recorded(
            legacy_config_fingerprint,
            legacy_binary_fingerprint,
        ))
    }

    async fn public_probe_transaction(
        &self,
        input: PublicProbeInput,
    ) -> Result<PublicProbeOutcome, PublicProbeError> {
        let mut devices_guard = self.devices.lock().await;
        let Some(existing) = devices_guard.get(&input.device_id) else {
            return Ok(PublicProbeOutcome::DeviceNotFound);
        };
        if existing.node_id != input.device_id {
            return Err(PublicProbeError::StateConflict);
        }

        let commands_guard = self.commands.lock().await;
        let mut devices = devices_guard.clone();
        let device = devices
            .get_mut(&input.device_id)
            .ok_or(PublicProbeError::StateConflict)?;
        apply_public_probe(device, input.report);
        if device.node_id != input.device_id {
            return Err(PublicProbeError::StateConflict);
        }

        self.persist_candidate(&devices_guard, &commands_guard, &devices, &commands_guard)
            .map_err(|_| PublicProbeError::Persistence)?;
        *devices_guard = devices;
        Ok(PublicProbeOutcome::Updated)
    }

    async fn issue_command_transaction(
        &self,
        input: IssueCommandInput,
    ) -> Result<IssueCommandOutcome, IssueCommandError> {
        let mut devices_guard = self.devices.lock().await;
        let mut commands_guard = self.commands.lock().await;
        let mut devices = devices_guard.clone();
        let mut commands = commands_guard.clone();
        let expected_devices = devices.clone();
        let expected_commands = commands.clone();

        let migration =
            normalize_command_state(&mut commands).map_err(|_| IssueCommandError::StateConflict)?;
        let scope =
            idempotency_scope_key(&input.device_id, &input.request.idempotency_key).to_string();
        let legacy_scope = legacy_idempotency_scope_key(&input);

        if let Some(existing) = commands.idempotency_results.get(&scope) {
            let original = classify_existing(existing, &input.device_id, &input.request)?;
            if migration.changed() {
                self.persist_candidate(&expected_devices, &expected_commands, &devices, &commands)
                    .map_err(|_| IssueCommandError::Persistence)?;
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
        if pending_command_count(&commands) >= MAX_PENDING_COMMANDS
            || commands
                .queues
                .get(&input.device_id)
                .is_some_and(|queue| queue.len() >= MAX_COMMAND_QUEUE_PER_DEVICE)
        {
            return Err(IssueCommandError::CapacityExceeded);
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

        commands
            .idempotency
            .insert(legacy_scope, command.command_id);
        commands
            .idempotency_results
            .insert(scope.clone(), command.clone());
        commands.idempotency_order.push_back(scope);
        trim_idempotency_state(&mut commands).map_err(|_| IssueCommandError::StateConflict)?;

        if let Some(device) = devices.get_mut(&input.device_id) {
            device.desired_state = Some(command.desired_state.to_string());
            device.recovery_intent = Some(command.recovery_intent.to_string());
            device.last_event_at = Some(command.issued_at.clone());
        }

        self.persist_candidate(&expected_devices, &expected_commands, &devices, &commands)
            .map_err(|_| IssueCommandError::Persistence)?;
        *devices_guard = devices;
        *commands_guard = commands;
        Ok(IssueCommandOutcome::Created(command))
    }

    async fn poll_command_query(
        &self,
        input: PollCommandInput,
    ) -> Result<PollCommandOutcome, PollCommandError> {
        let commands = self.commands.lock().await;
        let Some(command) = commands
            .queues
            .get(&input.device_id)
            .and_then(|queue| queue.front())
        else {
            return Ok(PollCommandOutcome::Empty);
        };
        if command.device_id != input.device_id {
            return Err(PollCommandError::StateConflict);
        }
        Ok(PollCommandOutcome::Pending(command.clone()))
    }

    async fn acknowledge_command_transaction(
        &self,
        input: AcknowledgeCommandInput,
    ) -> Result<AcknowledgeCommandOutcome, AcknowledgeCommandError> {
        if !input.request.ok {
            return Ok(AcknowledgeCommandOutcome::RetryRequested);
        }

        let mut devices_guard = self.devices.lock().await;
        let mut commands_guard = self.commands.lock().await;
        let mut devices = devices_guard.clone();
        let mut commands = commands_guard.clone();

        let (command, queue_empty) = {
            let Some(queue) = commands.queues.get_mut(&input.device_id) else {
                return Ok(AcknowledgeCommandOutcome::NotFound);
            };
            let Some(index) = queue
                .iter()
                .position(|command| command.command_id == input.command_id)
            else {
                return Ok(AcknowledgeCommandOutcome::NotFound);
            };
            if queue[index].device_id != input.device_id {
                return Err(AcknowledgeCommandError::StateConflict);
            }
            let command = queue
                .remove(index)
                .ok_or(AcknowledgeCommandError::StateConflict)?;
            (command, queue.is_empty())
        };
        if queue_empty {
            commands.queues.remove(&input.device_id);
        }

        if let Some(device) = devices.get_mut(&input.device_id) {
            device.recovery_intent = Some(proxy_core::RecoveryIntent::None.to_string());
            device.last_event_at = Some(now_unix_secs());
        }

        self.persist_candidate(&devices_guard, &commands_guard, &devices, &commands)
            .map_err(|_| AcknowledgeCommandError::Persistence)?;
        *devices_guard = devices;
        *commands_guard = commands;

        debug_assert_eq!(command.command_id, input.command_id);
        Ok(AcknowledgeCommandOutcome::Completed)
    }
}

impl RegisterDevicePort for AppState {
    fn register_device(&self, input: RegisterDeviceInput) -> RegisterDeviceFuture<'_> {
        Box::pin(async move { self.register_device_transaction(input).await })
    }
}

impl HeartbeatPort for AppState {
    fn record_heartbeat(&self, input: HeartbeatInput) -> HeartbeatFuture<'_> {
        Box::pin(async move { self.heartbeat_transaction(input).await })
    }
}

impl PublicProbePort for AppState {
    fn record_public_probe(&self, input: PublicProbeInput) -> PublicProbeFuture<'_> {
        Box::pin(async move { self.public_probe_transaction(input).await })
    }
}

impl IssueCommandPort for AppState {
    fn issue_command(&self, input: IssueCommandInput) -> IssueCommandFuture<'_> {
        Box::pin(async move { self.issue_command_transaction(input).await })
    }
}

impl PollCommandPort for AppState {
    fn poll_command(&self, input: PollCommandInput) -> PollCommandFuture<'_> {
        Box::pin(async move { self.poll_command_query(input).await })
    }
}

impl AcknowledgeCommandPort for AppState {
    fn acknowledge_command(&self, input: AcknowledgeCommandInput) -> AcknowledgeCommandFuture<'_> {
        Box::pin(async move { self.acknowledge_command_transaction(input).await })
    }
}

fn legacy_idempotency_scope_key(input: &IssueCommandInput) -> String {
    format!("{}:{}", input.device_id, input.request.idempotency_key)
}

fn legacy_scope_for_command(command: &DeviceCommand) -> String {
    format!("{}:{}", command.device_id, command.idempotency_key)
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
            commands.idempotency_results.insert(canonical, command);
            migration.canonicalized_keys += 1;
        }
    }

    let queued_commands: Vec<DeviceCommand> = commands
        .queues
        .values()
        .flat_map(|queue| queue.iter().cloned())
        .collect();
    for command in queued_commands {
        let canonical =
            idempotency_scope_key(&command.device_id, &command.idempotency_key).to_string();
        let legacy = legacy_scope_for_command(&command);
        if let Some(existing) = commands.idempotency_results.get(&canonical) {
            if existing != &command {
                return Err(());
            }
        } else {
            commands
                .idempotency_results
                .insert(canonical, command.clone());
            migration.recovered_results += 1;
        }
        if let Some(existing_id) = commands.idempotency.get(&legacy) {
            if *existing_id != command.command_id {
                return Err(());
            }
        } else {
            commands.idempotency.insert(legacy, command.command_id);
            migration.recovered_results += 1;
        }
    }

    let canonical_results: Vec<(String, DeviceCommand)> = commands
        .idempotency_results
        .iter()
        .map(|(key, command)| (key.clone(), command.clone()))
        .collect();
    for (canonical, command) in canonical_results {
        let legacy = legacy_scope_for_command(&command);
        if let Some(existing_id) = commands.idempotency.get(&legacy) {
            if *existing_id != command.command_id {
                return Err(());
            }
        } else {
            commands
                .idempotency
                .insert(legacy.clone(), command.command_id);
            migration.recovered_results += 1;
        }
        if canonical != legacy
            && let Some(existing_id) = commands.idempotency.get(&canonical).copied()
        {
            if existing_id != command.command_id {
                return Err(());
            }
            commands.idempotency.remove(&canonical);
            migration.canonicalized_keys += 1;
        }
    }

    let original_order = std::mem::take(&mut commands.idempotency_order);
    let mut normalized_order = VecDeque::new();
    for key in &original_order {
        if commands.idempotency_results.contains_key(key) && !normalized_order.contains(key) {
            normalized_order.push_back(key.clone());
        }
    }
    let mut missing: Vec<String> = commands
        .idempotency_results
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
    migration.evicted_entries = trim_idempotency_state(commands)?;

    if commands.idempotency.len() > MAX_IDEMPOTENCY_RESULTS * 2 {
        return Err(());
    }
    Ok(migration)
}

fn pending_command_count(commands: &CommandState) -> usize {
    commands.queues.values().map(VecDeque::len).sum()
}

fn command_is_pending(commands: &CommandState, command_id: CommandId) -> bool {
    commands
        .queues
        .values()
        .any(|queue| queue.iter().any(|command| command.command_id == command_id))
}

fn trim_idempotency_state(commands: &mut CommandState) -> Result<u64, ()> {
    let mut evicted = 0;
    while commands.idempotency_order.len() > MAX_IDEMPOTENCY_RESULTS {
        let position = commands
            .idempotency_order
            .iter()
            .position(|key| {
                commands
                    .idempotency_results
                    .get(key)
                    .is_none_or(|command| !command_is_pending(commands, command.command_id))
            })
            .ok_or(())?;
        let key = commands.idempotency_order.remove(position).ok_or(())?;
        if let Some(command) = commands.idempotency_results.remove(&key) {
            let legacy = legacy_scope_for_command(&command);
            if commands.idempotency.get(&legacy) == Some(&command.command_id) {
                commands.idempotency.remove(&legacy);
            }
            if commands.idempotency.get(&key) == Some(&command.command_id) {
                commands.idempotency.remove(&key);
            }
        } else {
            commands.idempotency.remove(&key);
        }
        evicted += 1;
    }
    Ok(evicted)
}

#[cfg(test)]
mod tests {
    use std::collections::{HashMap, VecDeque};
    use std::fs;
    use std::sync::Arc;

    use mobile_proxy_application::{
        AcknowledgeCommandError, AcknowledgeCommandInput, AcknowledgeCommandOutcome,
        AcknowledgeCommandPort, HeartbeatError, HeartbeatInput, HeartbeatPort, IssueCommandError,
        IssueCommandInput, IssueCommandOutcome, IssueCommandPort, MAX_COMMAND_QUEUE_PER_DEVICE,
        MAX_PENDING_COMMANDS, MAX_REGISTERED_DEVICES, PollCommandError, PollCommandInput,
        PollCommandOutcome, PollCommandPort, PublicProbeError, PublicProbeInput,
        PublicProbeOutcome, PublicProbePort, RegisterDeviceError, RegisterDeviceInput,
        RegisterDeviceOutcome, RegisterDevicePort, idempotency_scope_key,
    };
    use mobile_proxy_foundation::{CommandId, DeadlineWindow, IdempotencyKey};
    use proxy_core::{
        CommandAckRequest, DesiredState, DeviceCommand, HeartbeatRequest, IssueCommandRequest,
        PublicProbeReport, RecoveryIntent, RegisterDeviceRequest,
    };
    use serde_json::json;
    use tokio::sync::Mutex;
    use uuid::Uuid;

    use crate::projection::build_registered_device;

    use super::{AppState, CommandState, StoredState};

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

    fn acknowledgement(command_id: CommandId, ok: bool) -> AcknowledgeCommandInput {
        AcknowledgeCommandInput {
            device_id: "device-1".into(),
            command_id,
            request: CommandAckRequest { ok, message: None },
        }
    }

    fn registration(node_id: &str, node_name: &str) -> RegisterDeviceInput {
        RegisterDeviceInput {
            request: RegisterDeviceRequest {
                node_id: node_id.into(),
                node_name: node_name.into(),
                proxy_status: "starting".into(),
                tunnel_owner: Some("stock_wireguard_bridge".into()),
            },
        }
    }

    fn heartbeat(node_id: &str, node_name: &str) -> HeartbeatInput {
        HeartbeatInput {
            request: serde_json::from_value::<HeartbeatRequest>(json!({
                "node_id": node_id,
                "node_name": node_name,
                "readiness_state": "healthy",
                "serving": true,
                "proxy_status": "running"
            }))
            .unwrap(),
        }
    }

    fn public_probe(device_id: &str, publicly_serving: bool) -> PublicProbeInput {
        PublicProbeInput {
            device_id: device_id.into(),
            report: PublicProbeReport {
                publicly_serving,
                public_probe_error: (!publicly_serving).then(|| "backend probe failed".into()),
                public_probe_at: "untrusted-client-time".into(),
            },
        }
    }

    #[tokio::test]
    async fn exact_duplicate_survives_queue_removal() {
        let (_database, state) = load_state("command-idempotency", StoredState::default()).await;
        let first = state
            .issue_command(command_input(DesiredState::HealthyServing))
            .await
            .unwrap();
        let (_, original) = first.into_parts();
        state.commands.lock().await.queues.clear();
        state.persist_for_test().await.unwrap();

        let duplicate = state
            .issue_command(command_input(DesiredState::HealthyServing))
            .await
            .unwrap();
        assert_eq!(duplicate, IssueCommandOutcome::ExactDuplicate(original));
    }

    #[tokio::test]
    async fn reused_key_with_changed_parameters_fails_closed() {
        let (_database, state) = load_state("command-conflict", StoredState::default()).await;
        state
            .issue_command(command_input(DesiredState::HealthyServing))
            .await
            .unwrap();
        let conflict = state
            .issue_command(command_input(DesiredState::DegradedSafe))
            .await;
        assert_eq!(conflict, Err(IssueCommandError::IdempotencyConflict));
    }

    #[tokio::test]
    async fn full_device_queue_rejects_without_dropping_a_pending_command() {
        let path = std::env::temp_dir().join(format!(
            "mobile-proxy-control-plane-device-command-capacity-{}.json",
            Uuid::new_v4()
        ));
        let mut commands = CommandState::default();
        for index in 0..MAX_COMMAND_QUEUE_PER_DEVICE {
            let idempotency_key = IdempotencyKey::parse(format!("device-command-{index}")).unwrap();
            let command = DeviceCommand {
                command_id: CommandId::from_uuid(Uuid::from_u128(index as u128 + 1)),
                device_id: "device-1".into(),
                desired_state: DesiredState::HealthyServing,
                recovery_intent: RecoveryIntent::None,
                deadline_secs: DeadlineWindow::new(30).unwrap(),
                idempotency_key: idempotency_key.clone(),
                issued_at: "1".into(),
            };
            let scope = idempotency_scope_key("device-1", &idempotency_key).to_string();
            commands
                .queues
                .entry("device-1".into())
                .or_default()
                .push_back(command.clone());
            commands
                .idempotency
                .insert(format!("device-1:{idempotency_key}"), command.command_id);
            commands.idempotency_results.insert(scope.clone(), command);
            commands.idempotency_order.push_back(scope);
        }
        let state = AppState {
            devices: Arc::new(Mutex::new(HashMap::new())),
            commands: Arc::new(Mutex::new(commands)),
            state_path: Arc::new(path.clone()),
        };

        let result = state
            .issue_command(IssueCommandInput {
                device_id: "device-1".into(),
                request: IssueCommandRequest {
                    desired_state: DesiredState::DegradedSafe,
                    recovery_intent: RecoveryIntent::None,
                    deadline_secs: DeadlineWindow::new(30).unwrap(),
                    idempotency_key: IdempotencyKey::parse("overflow-device-command").unwrap(),
                },
            })
            .await;
        assert_eq!(result, Err(IssueCommandError::CapacityExceeded));
        assert_eq!(
            state
                .commands
                .lock()
                .await
                .queues
                .get("device-1")
                .unwrap()
                .len(),
            MAX_COMMAND_QUEUE_PER_DEVICE
        );
    }

    #[tokio::test]
    async fn pending_claims_are_not_evicted_when_global_capacity_is_full() {
        let path = std::env::temp_dir().join(format!(
            "mobile-proxy-control-plane-command-capacity-{}.json",
            Uuid::new_v4()
        ));
        let mut commands = CommandState::default();
        for index in 0..MAX_PENDING_COMMANDS {
            let device_id = format!("device-{}", index / 50);
            let idempotency_key = IdempotencyKey::parse(format!("command-{index}")).unwrap();
            let command = DeviceCommand {
                command_id: CommandId::from_uuid(Uuid::from_u128(index as u128 + 1)),
                device_id: device_id.clone(),
                desired_state: DesiredState::HealthyServing,
                recovery_intent: RecoveryIntent::None,
                deadline_secs: DeadlineWindow::new(30).unwrap(),
                idempotency_key: idempotency_key.clone(),
                issued_at: "1".into(),
            };
            let scope = idempotency_scope_key(&device_id, &idempotency_key).to_string();
            commands
                .queues
                .entry(device_id.clone())
                .or_default()
                .push_back(command.clone());
            commands
                .idempotency
                .insert(format!("{device_id}:{idempotency_key}"), command.command_id);
            commands.idempotency_results.insert(scope.clone(), command);
            commands.idempotency_order.push_back(scope);
        }
        let state = AppState {
            devices: Arc::new(Mutex::new(HashMap::new())),
            commands: Arc::new(Mutex::new(commands)),
            state_path: Arc::new(path.clone()),
        };

        let result = state
            .issue_command(IssueCommandInput {
                device_id: "overflow-device".into(),
                request: IssueCommandRequest {
                    desired_state: DesiredState::HealthyServing,
                    recovery_intent: RecoveryIntent::None,
                    deadline_secs: DeadlineWindow::new(30).unwrap(),
                    idempotency_key: IdempotencyKey::parse("overflow-command").unwrap(),
                },
            })
            .await;
        assert_eq!(result, Err(IssueCommandError::CapacityExceeded));
        let commands = state.commands.lock().await;
        assert_eq!(commands.idempotency_results.len(), MAX_PENDING_COMMANDS);
        assert_eq!(
            commands.queues.values().map(VecDeque::len).sum::<usize>(),
            MAX_PENDING_COMMANDS
        );
        drop(commands);
    }

    #[tokio::test]
    async fn registration_is_durable_and_preserves_first_registered_metadata() {
        let (database, state) = load_state("device-registration", StoredState::default()).await;
        assert_eq!(
            state
                .register_device(registration("device-1", "first-name"))
                .await
                .unwrap(),
            RegisterDeviceOutcome::Created
        );
        assert_eq!(
            state
                .register_device(RegisterDeviceInput {
                    request: RegisterDeviceRequest {
                        node_id: "device-1".into(),
                        node_name: "changed-name".into(),
                        proxy_status: "running".into(),
                        tunnel_owner: Some("first_party_reverse_tunnel".into()),
                    },
                })
                .await
                .unwrap(),
            RegisterDeviceOutcome::AlreadyRegistered
        );
        let registered = state.devices.lock().await.get("device-1").unwrap().clone();
        assert_eq!(registered.node_name, "first-name");
        assert_eq!(registered.proxy_status, "starting");
        assert_eq!(
            registered.tunnel_owner.as_deref(),
            Some("stock_wireguard_bridge")
        );
        drop(state);

        let restarted = AppState::load(database.path.clone()).await.unwrap();
        let registered = restarted
            .devices
            .lock()
            .await
            .get("device-1")
            .unwrap()
            .clone();
        assert_eq!(registered.node_name, "first-name");
        assert_eq!(registered.proxy_status, "starting");
    }

    #[tokio::test]
    async fn failed_registration_persistence_does_not_publish_a_new_device() {
        let blocking_parent = std::env::temp_dir().join(format!(
            "mobile-proxy-control-plane-registration-persistence-{}",
            Uuid::new_v4()
        ));
        fs::write(&blocking_parent, b"not a directory").unwrap();
        let state = AppState {
            devices: Arc::new(Mutex::new(HashMap::new())),
            commands: Arc::new(Mutex::new(CommandState::default())),
            state_path: Arc::new(blocking_parent.join("state.json")),
        };

        assert_eq!(
            state
                .register_device(registration("device-1", "node"))
                .await,
            Err(RegisterDeviceError::Persistence)
        );
        assert!(state.devices.lock().await.is_empty());
        let _ = fs::remove_file(blocking_parent);
    }

    #[tokio::test]
    async fn duplicate_registration_reports_persistence_failure() {
        let blocking_parent = std::env::temp_dir().join(format!(
            "mobile-proxy-control-plane-registration-replay-persistence-{}",
            Uuid::new_v4()
        ));
        fs::write(&blocking_parent, b"not a directory").unwrap();
        let device = build_registered_device(registration("device-1", "node").request);
        let mut devices = HashMap::new();
        devices.insert("device-1".into(), device);
        let state = AppState {
            devices: Arc::new(Mutex::new(devices)),
            commands: Arc::new(Mutex::new(CommandState::default())),
            state_path: Arc::new(blocking_parent.join("state.json")),
        };

        assert_eq!(
            state
                .register_device(registration("device-1", "node"))
                .await,
            Err(RegisterDeviceError::Persistence)
        );
        assert_eq!(state.devices.lock().await.len(), 1);
        let _ = fs::remove_file(blocking_parent);
    }

    #[tokio::test]
    async fn registered_device_capacity_is_bounded() {
        let template = build_registered_device(registration("template", "template").request);
        let mut devices = HashMap::new();
        for index in 0..MAX_REGISTERED_DEVICES {
            let node_id = format!("device-{index}");
            let mut device = template.clone();
            device.node_id = node_id.clone();
            device.node_name = node_id.clone();
            devices.insert(node_id, device);
        }
        let state = AppState {
            devices: Arc::new(Mutex::new(devices)),
            commands: Arc::new(Mutex::new(CommandState::default())),
            state_path: Arc::new(std::path::PathBuf::from("unused")),
        };

        assert_eq!(
            state
                .register_device(registration("overflow-device", "overflow"))
                .await,
            Err(RegisterDeviceError::CapacityExceeded)
        );
        assert_eq!(state.devices.lock().await.len(), MAX_REGISTERED_DEVICES);
    }

    #[tokio::test]
    async fn registration_fails_closed_on_a_mismatched_stored_device() {
        let mismatched = build_registered_device(registration("device-2", "node").request);
        let mut devices = HashMap::new();
        devices.insert("device-1".into(), mismatched);
        let state = AppState {
            devices: Arc::new(Mutex::new(devices)),
            commands: Arc::new(Mutex::new(CommandState::default())),
            state_path: Arc::new(std::path::PathBuf::from("unused")),
        };

        assert_eq!(
            state
                .register_device(registration("device-1", "node"))
                .await,
            Err(RegisterDeviceError::StateConflict)
        );
    }

    #[tokio::test]
    async fn heartbeat_is_durable_and_preserves_public_probe_projection() {
        let (database, state) = load_state("heartbeat", StoredState::default()).await;
        state
            .register_device(registration("device-1", "registered-name"))
            .await
            .unwrap();
        {
            let mut devices = state.devices.lock().await;
            let device = devices.get_mut("device-1").unwrap();
            device.publicly_serving = true;
            device.public_probe_error = Some("bounded_probe_error".into());
            device.public_probe_at = Some("123".into());
        }
        state.persist_for_test().await.unwrap();

        let outcome = state
            .record_heartbeat(heartbeat("device-1", "heartbeat-name"))
            .await
            .unwrap();
        assert!(outcome.accepted());
        let device = state.devices.lock().await.get("device-1").unwrap().clone();
        assert_eq!(device.node_name, "heartbeat-name");
        assert!(device.publicly_serving);
        assert_eq!(
            device.public_probe_error.as_deref(),
            Some("bounded_probe_error")
        );
        assert_eq!(device.public_probe_at.as_deref(), Some("123"));
        drop(state);

        let restarted = AppState::load(database.path.clone()).await.unwrap();
        let device = restarted
            .devices
            .lock()
            .await
            .get("device-1")
            .unwrap()
            .clone();
        assert_eq!(device.node_name, "heartbeat-name");
        assert!(device.publicly_serving);
        assert_eq!(device.public_probe_at.as_deref(), Some("123"));
    }

    #[tokio::test]
    async fn failed_heartbeat_persistence_does_not_publish_a_new_projection() {
        let blocking_parent = std::env::temp_dir().join(format!(
            "mobile-proxy-control-plane-heartbeat-persistence-{}",
            Uuid::new_v4()
        ));
        fs::write(&blocking_parent, b"not a directory").unwrap();
        let existing = build_registered_device(registration("device-1", "registered-name").request);
        let mut devices = HashMap::new();
        devices.insert("device-1".into(), existing);
        let state = AppState {
            devices: Arc::new(Mutex::new(devices)),
            commands: Arc::new(Mutex::new(CommandState::default())),
            state_path: Arc::new(blocking_parent.join("state.json")),
        };

        assert_eq!(
            state
                .record_heartbeat(heartbeat("device-1", "heartbeat-name"))
                .await,
            Err(HeartbeatError::Persistence)
        );
        assert_eq!(
            state
                .devices
                .lock()
                .await
                .get("device-1")
                .unwrap()
                .node_name,
            "registered-name"
        );
        let _ = fs::remove_file(blocking_parent);
    }

    #[tokio::test]
    async fn heartbeat_capacity_rejects_new_devices_but_allows_existing_updates() {
        let template = build_registered_device(registration("template", "template").request);
        let mut devices = HashMap::new();
        for index in 0..MAX_REGISTERED_DEVICES {
            let node_id = format!("device-{index}");
            let mut device = template.clone();
            device.node_id = node_id.clone();
            device.node_name = node_id.clone();
            devices.insert(node_id, device);
        }
        let (_database, state) = load_state(
            "heartbeat-capacity",
            StoredState {
                devices,
                commands: CommandState::default(),
            },
        )
        .await;

        assert_eq!(
            state
                .record_heartbeat(heartbeat("overflow-device", "overflow"))
                .await,
            Err(HeartbeatError::CapacityExceeded)
        );
        assert!(
            state
                .record_heartbeat(heartbeat("device-0", "updated"))
                .await
                .is_ok()
        );
        assert_eq!(state.devices.lock().await.len(), MAX_REGISTERED_DEVICES);
        assert_eq!(
            state
                .devices
                .lock()
                .await
                .get("device-0")
                .unwrap()
                .node_name,
            "updated"
        );
    }

    #[tokio::test]
    async fn heartbeat_fails_closed_on_a_mismatched_stored_device() {
        let mismatched = build_registered_device(registration("device-2", "node").request);
        let mut devices = HashMap::new();
        devices.insert("device-1".into(), mismatched);
        let state = AppState {
            devices: Arc::new(Mutex::new(devices)),
            commands: Arc::new(Mutex::new(CommandState::default())),
            state_path: Arc::new(std::path::PathBuf::from("unused")),
        };

        assert_eq!(
            state
                .record_heartbeat(heartbeat("device-1", "heartbeat-name"))
                .await,
            Err(HeartbeatError::StateConflict)
        );
    }

    #[tokio::test]
    async fn public_probe_is_durable_and_uses_an_authoritative_timestamp() {
        let (database, state) = load_state("public-probe", StoredState::default()).await;
        state
            .record_heartbeat(heartbeat("device-1", "heartbeat-name"))
            .await
            .unwrap();

        assert_eq!(
            state
                .record_public_probe(public_probe("device-1", true))
                .await
                .unwrap(),
            PublicProbeOutcome::Updated
        );
        let device = state.devices.lock().await.get("device-1").unwrap().clone();
        assert!(device.publicly_serving);
        assert_eq!(device.public_probe_error, None);
        assert!(device.public_probe_at.is_some());
        assert_ne!(
            device.public_probe_at.as_deref(),
            Some("untrusted-client-time")
        );
        assert_eq!(device.availability, "ready");
        drop(state);

        let restarted = AppState::load(database.path.clone()).await.unwrap();
        let device = restarted
            .devices
            .lock()
            .await
            .get("device-1")
            .unwrap()
            .clone();
        assert!(device.publicly_serving);
        assert_eq!(device.availability, "ready");
        assert_ne!(
            device.public_probe_at.as_deref(),
            Some("untrusted-client-time")
        );
    }

    #[tokio::test]
    async fn missing_public_probe_device_preserves_the_existing_accepted_no_op() {
        let state = AppState {
            devices: Arc::new(Mutex::new(HashMap::new())),
            commands: Arc::new(Mutex::new(CommandState::default())),
            state_path: Arc::new(std::path::PathBuf::from("unused")),
        };

        assert_eq!(
            state
                .record_public_probe(public_probe("missing-device", true))
                .await
                .unwrap(),
            PublicProbeOutcome::DeviceNotFound
        );
        assert!(state.devices.lock().await.is_empty());
    }

    #[tokio::test]
    async fn failed_public_probe_persistence_does_not_publish_a_new_projection() {
        let blocking_parent = std::env::temp_dir().join(format!(
            "mobile-proxy-control-plane-public-probe-persistence-{}",
            Uuid::new_v4()
        ));
        fs::write(&blocking_parent, b"not a directory").unwrap();
        let existing = build_registered_device(registration("device-1", "registered-name").request);
        let mut devices = HashMap::new();
        devices.insert("device-1".into(), existing);
        let state = AppState {
            devices: Arc::new(Mutex::new(devices)),
            commands: Arc::new(Mutex::new(CommandState::default())),
            state_path: Arc::new(blocking_parent.join("state.json")),
        };

        assert_eq!(
            state
                .record_public_probe(public_probe("device-1", true))
                .await,
            Err(PublicProbeError::Persistence)
        );
        let device = state.devices.lock().await.get("device-1").unwrap().clone();
        assert!(!device.publicly_serving);
        assert_eq!(device.public_probe_at, None);
        let _ = fs::remove_file(blocking_parent);
    }

    #[tokio::test]
    async fn public_probe_fails_closed_on_a_mismatched_stored_device() {
        let mismatched = build_registered_device(registration("device-2", "node").request);
        let mut devices = HashMap::new();
        devices.insert("device-1".into(), mismatched);
        let state = AppState {
            devices: Arc::new(Mutex::new(devices)),
            commands: Arc::new(Mutex::new(CommandState::default())),
            state_path: Arc::new(std::path::PathBuf::from("unused")),
        };

        assert_eq!(
            state
                .record_public_probe(public_probe("device-1", true))
                .await,
            Err(PublicProbeError::StateConflict)
        );
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

    #[tokio::test]
    async fn polling_and_negative_acknowledgement_keep_the_command_pending() {
        let (_database, state) = load_state("command-retry", StoredState::default()).await;
        let (_, original) = state
            .issue_command(command_input(DesiredState::HealthyServing))
            .await
            .unwrap()
            .into_parts();

        let polled = state
            .poll_command(PollCommandInput {
                device_id: "device-1".into(),
            })
            .await
            .unwrap();
        assert_eq!(polled, PollCommandOutcome::Pending(original.clone()));

        let outcome = state
            .acknowledge_command(acknowledgement(original.command_id, false))
            .await
            .unwrap();
        assert_eq!(outcome, AcknowledgeCommandOutcome::RetryRequested);
        assert_eq!(
            state
                .poll_command(PollCommandInput {
                    device_id: "device-1".into(),
                })
                .await
                .unwrap(),
            PollCommandOutcome::Pending(original)
        );
    }

    #[tokio::test]
    async fn positive_acknowledgement_is_durable_and_preserves_exact_replay() {
        let (database, state) = load_state("command-ack", StoredState::default()).await;
        let (_, original) = state
            .issue_command(command_input(DesiredState::HealthyServing))
            .await
            .unwrap()
            .into_parts();
        assert_eq!(
            state
                .acknowledge_command(acknowledgement(original.command_id, true))
                .await
                .unwrap(),
            AcknowledgeCommandOutcome::Completed
        );
        assert_eq!(
            state
                .poll_command(PollCommandInput {
                    device_id: "device-1".into(),
                })
                .await
                .unwrap(),
            PollCommandOutcome::Empty
        );
        drop(state);

        let restarted = AppState::load(database.path.clone()).await.unwrap();
        assert_eq!(
            restarted
                .poll_command(PollCommandInput {
                    device_id: "device-1".into(),
                })
                .await
                .unwrap(),
            PollCommandOutcome::Empty
        );
        assert_eq!(
            restarted
                .issue_command(command_input(DesiredState::HealthyServing))
                .await
                .unwrap(),
            IssueCommandOutcome::ExactDuplicate(original)
        );
    }

    #[tokio::test]
    async fn unknown_positive_acknowledgement_does_not_remove_a_command() {
        let (_database, state) = load_state("command-unknown-ack", StoredState::default()).await;
        let (_, original) = state
            .issue_command(command_input(DesiredState::HealthyServing))
            .await
            .unwrap()
            .into_parts();
        let unknown = CommandId::from_uuid(Uuid::new_v4());
        assert_eq!(
            state
                .acknowledge_command(acknowledgement(unknown, true))
                .await
                .unwrap(),
            AcknowledgeCommandOutcome::NotFound
        );
        assert_eq!(
            state
                .poll_command(PollCommandInput {
                    device_id: "device-1".into(),
                })
                .await
                .unwrap(),
            PollCommandOutcome::Pending(original)
        );
    }

    #[tokio::test]
    async fn failed_acknowledgement_persistence_does_not_publish_queue_removal() {
        let blocking_parent = std::env::temp_dir().join(format!(
            "mobile-proxy-control-plane-command-ack-persistence-{}",
            Uuid::new_v4()
        ));
        fs::write(&blocking_parent, b"not a directory").unwrap();
        let command = DeviceCommand {
            command_id: CommandId::from_uuid(Uuid::new_v4()),
            device_id: "device-1".into(),
            desired_state: DesiredState::HealthyServing,
            recovery_intent: RecoveryIntent::None,
            deadline_secs: DeadlineWindow::new(30).unwrap(),
            idempotency_key: IdempotencyKey::parse("ack-persistence").unwrap(),
            issued_at: "1".into(),
        };
        let mut commands = CommandState::default();
        commands
            .queues
            .entry("device-1".into())
            .or_default()
            .push_back(command.clone());
        let state = AppState {
            devices: Arc::new(Mutex::new(HashMap::new())),
            commands: Arc::new(Mutex::new(commands)),
            state_path: Arc::new(blocking_parent.join("state.json")),
        };

        assert_eq!(
            state
                .acknowledge_command(acknowledgement(command.command_id, true))
                .await,
            Err(AcknowledgeCommandError::Persistence)
        );
        assert_eq!(
            state
                .poll_command(PollCommandInput {
                    device_id: "device-1".into(),
                })
                .await
                .unwrap(),
            PollCommandOutcome::Pending(command)
        );
        let _ = fs::remove_file(blocking_parent);
    }

    #[tokio::test]
    async fn polling_fails_closed_on_a_mismatched_stored_device() {
        let command = DeviceCommand {
            command_id: CommandId::from_uuid(Uuid::new_v4()),
            device_id: "device-2".into(),
            desired_state: DesiredState::HealthyServing,
            recovery_intent: RecoveryIntent::None,
            deadline_secs: DeadlineWindow::new(30).unwrap(),
            idempotency_key: IdempotencyKey::parse("mismatched-device").unwrap(),
            issued_at: "1".into(),
        };
        let mut commands = CommandState::default();
        commands
            .queues
            .entry("device-1".into())
            .or_default()
            .push_back(command);
        let state = AppState {
            devices: Arc::new(Mutex::new(HashMap::new())),
            commands: Arc::new(Mutex::new(commands)),
            state_path: Arc::new(std::path::PathBuf::from("unused")),
        };

        assert_eq!(
            state
                .poll_command(PollCommandInput {
                    device_id: "device-1".into(),
                })
                .await,
            Err(PollCommandError::StateConflict)
        );
    }
}

#[cfg(test)]
#[path = "state_sqlite_backend_tests.rs"]
mod sqlite_backend_tests;
