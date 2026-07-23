#!/usr/bin/env python3
from pathlib import Path

ROOT = Path.cwd()


def replace_once(relative: str, old: str, new: str) -> None:
    path = ROOT / relative
    body = path.read_text(encoding="utf-8")
    count = body.count(old)
    if count != 1:
        raise SystemExit(f"{relative}: expected one anchor, found {count}")
    path.write_text(body.replace(old, new), encoding="utf-8")


replace_once(
    "crates/application/src/command_issue.rs",
    "pub const MAX_IDEMPOTENCY_RESULTS: usize = 1_000;\n",
    "pub const MAX_IDEMPOTENCY_RESULTS: usize = 1_000;\n"
    "pub const MAX_PENDING_COMMANDS: usize = 1_000;\n",
)
replace_once(
    "crates/application/src/command_issue.rs",
    "    StateConflict,\n    Persistence,\n",
    "    StateConflict,\n    CapacityExceeded,\n    Persistence,\n",
)
replace_once(
    "crates/application/src/command_issue.rs",
    "            Self::StateConflict => \"persisted command state is internally inconsistent\",\n"
    "            Self::Persistence => \"command state could not be persisted\",\n",
    "            Self::StateConflict => \"persisted command state is internally inconsistent\",\n"
    "            Self::CapacityExceeded => \"pending command capacity is exhausted\",\n"
    "            Self::Persistence => \"command state could not be persisted\",\n",
)
replace_once(
    "crates/application/src/lib.rs",
    "    IssueCommandPort, MAX_COMMAND_QUEUE_PER_DEVICE, MAX_IDEMPOTENCY_RESULTS, classify_existing,\n"
    "    idempotency_scope_key, request_fingerprint,\n",
    "    IssueCommandPort, MAX_COMMAND_QUEUE_PER_DEVICE, MAX_IDEMPOTENCY_RESULTS,\n"
    "    MAX_PENDING_COMMANDS, classify_existing, idempotency_scope_key, request_fingerprint,\n",
)
replace_once(
    "services/control-plane/src/state.rs",
    "    IssueCommandPort, MAX_COMMAND_QUEUE_PER_DEVICE, MAX_IDEMPOTENCY_RESULTS, classify_existing,\n"
    "    idempotency_scope_key,\n",
    "    IssueCommandPort, MAX_COMMAND_QUEUE_PER_DEVICE, MAX_IDEMPOTENCY_RESULTS,\n"
    "    MAX_PENDING_COMMANDS, classify_existing, idempotency_scope_key,\n",
)
replace_once(
    "services/control-plane/src/state.rs",
    "        if commands.idempotency.contains_key(&scope)\n"
    "            || commands.idempotency.contains_key(&legacy_scope)\n"
    "        {\n"
    "            return Err(IssueCommandError::IdempotencyConflict);\n"
    "        }\n\n"
    "        let command = DeviceCommand {\n",
    "        if commands.idempotency.contains_key(&scope)\n"
    "            || commands.idempotency.contains_key(&legacy_scope)\n"
    "        {\n"
    "            return Err(IssueCommandError::IdempotencyConflict);\n"
    "        }\n"
    "        if pending_command_count(&commands) >= MAX_PENDING_COMMANDS {\n"
    "            return Err(IssueCommandError::CapacityExceeded);\n"
    "        }\n\n"
    "        let command = DeviceCommand {\n",
)
replace_once(
    "services/control-plane/src/state.rs",
    "        commands\n"
    "            .idempotency\n"
    "            .insert(scope.clone(), command.command_id);\n"
    "        commands\n"
    "            .idempotency_results\n"
    "            .insert(scope.clone(), command.clone());\n"
    "        commands.idempotency_order.push_back(scope);\n"
    "        trim_idempotency_state(&mut commands);\n",
    "        commands\n"
    "            .idempotency\n"
    "            .insert(legacy_scope, command.command_id);\n"
    "        commands\n"
    "            .idempotency_results\n"
    "            .insert(scope.clone(), command.clone());\n"
    "        commands.idempotency_order.push_back(scope);\n"
    "        trim_idempotency_state(&mut commands)\n"
    "            .map_err(|_| IssueCommandError::StateConflict)?;\n",
)
state_path = ROOT / "services/control-plane/src/state.rs"
state_body = state_path.read_text(encoding="utf-8")
start = state_body.index("fn normalize_command_state(")
end = state_body.index("\nfn persist_candidate(", start)
replacement = r'''fn legacy_scope_for_command(command: &DeviceCommand) -> String {
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
        let canonical = idempotency_scope_key(&command.device_id, &command.idempotency_key)
            .to_string();
        if stored_key != canonical {
            commands.idempotency_results.remove(&stored_key);
            if let Some(existing) = commands.idempotency_results.get(&canonical)
                && existing != &command
            {
                return Err(());
            }
            commands
                .idempotency_results
                .insert(canonical, command);
            migration.canonicalized_keys += 1;
        }
    }

    let queued_commands: Vec<DeviceCommand> = commands
        .queues
        .values()
        .flat_map(|queue| queue.iter().cloned())
        .collect();
    for command in queued_commands {
        let canonical = idempotency_scope_key(&command.device_id, &command.idempotency_key)
            .to_string();
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
            commands
                .idempotency
                .insert(legacy, command.command_id);
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
                .insert(legacy, command.command_id);
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
'''
state_path.write_text(state_body[:start] + replacement + state_body[end:], encoding="utf-8")

replace_once(
    "services/control-plane/src/routes.rs",
    "        Err(IssueCommandError::Persistence) => {\n",
    "        Err(IssueCommandError::CapacityExceeded) => {\n"
    "            tracing::warn!(\n"
    "                request_id = %context.request_id(),\n"
    "                correlation_id = %context.correlation_id(),\n"
    "                device_id = %id,\n"
    "                error_code = \"command_capacity_exceeded\",\n"
    "                \"device command rejected\"\n"
    "            );\n"
    "            Err((\n"
    "                StatusCode::SERVICE_UNAVAILABLE,\n"
    "                Json(serde_json::json!({ \"error\": \"command_capacity_exceeded\" })),\n"
    "            ))\n"
    "        }\n"
    "        Err(IssueCommandError::Persistence) => {\n",
)
replace_once(
    "services/control-plane/src/state.rs",
    "    use mobile_proxy_application::{\n"
    "        IssueCommandError, IssueCommandInput, IssueCommandOutcome, IssueCommandPort,\n"
    "    };\n"
    "    use mobile_proxy_foundation::{DeadlineWindow, IdempotencyKey};\n"
    "    use proxy_core::{DesiredState, IssueCommandRequest, RecoveryIntent};\n",
    "    use mobile_proxy_application::{\n"
    "        IssueCommandError, IssueCommandInput, IssueCommandOutcome, IssueCommandPort,\n"
    "        MAX_PENDING_COMMANDS, idempotency_scope_key,\n"
    "    };\n"
    "    use mobile_proxy_foundation::{CommandId, DeadlineWindow, IdempotencyKey};\n"
    "    use proxy_core::{\n"
    "        DesiredState, DeviceCommand, IssueCommandRequest, RecoveryIntent,\n"
    "    };\n",
)
replace_once(
    "services/control-plane/src/state.rs",
    "    #[tokio::test]\n"
    "    async fn failed_persistence_does_not_publish_in_memory_command() {\n",
    r'''    #[tokio::test]
    async fn rollback_writer_can_drop_new_fields_without_losing_pending_dedupe() {
        let path = std::env::temp_dir().join(format!(
            "mobile-proxy-control-plane-command-rollback-{}.json",
            Uuid::new_v4()
        ));
        let state = AppState::load(path.clone()).await.unwrap();
        let first = state
            .issue_command(command_input(DesiredState::HealthyServing))
            .await
            .unwrap();
        let (_, original) = first.into_parts();
        {
            let mut commands = state.commands.lock().await;
            assert!(commands.idempotency.contains_key("device-1:command-123"));
            commands.idempotency_results.clear();
            commands.idempotency_order.clear();
        }
        state.persist().await.unwrap();
        drop(state);

        let restarted = AppState::load(path.clone()).await.unwrap();
        let duplicate = restarted
            .issue_command(command_input(DesiredState::HealthyServing))
            .await
            .unwrap();
        assert_eq!(duplicate, IssueCommandOutcome::ExactDuplicate(original));
        let _ = fs::remove_file(path);
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
            commands
                .idempotency_results
                .insert(scope.clone(), command);
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
        let _ = fs::remove_file(path);
    }

    #[tokio::test]
    async fn failed_persistence_does_not_publish_in_memory_command() {
''',
)
replace_once(
    "docs/architecture/command-issuance-application-port.md",
    "The canonical claim key is a full typed BLAKE3 digest using domain:\n",
    "The canonical durable-result key is a full typed BLAKE3 digest using domain:\n",
)
replace_once(
    "docs/architecture/command-issuance-application-port.md",
    "The delivery queue remains bounded to 50 commands per device. Idempotency results have a separate deterministic bound of 1000 claims, so removal from the queue does not remove the original replay result.\n\n"
    "The JSON schema adds optional `idempotency_results` and `idempotency_order` fields under `commands`. Serde defaults keep old state readable; previous binaries ignore the added fields, preserving software rollback. Existing concatenated claims are a legacy migration input only. Recoverable claims are rewritten to the typed scope; an unrecoverable retained claim rejects reuse rather than creating a duplicate command.\n",
    "The delivery queue remains bounded to 50 commands per device and 1000 pending commands globally. Idempotency results have a deterministic bound of 1000 canonical entries. Pending results are never selected for retention eviction; when all capacity is pending, a new command fails with `command_capacity_exceeded` rather than dropping a live claim.\n\n"
    "The JSON schema adds optional `idempotency_results` and `idempotency_order` fields under `commands`. Serde defaults keep old state readable. The legacy concatenated claim remains as a compatibility alias while canonical result identity uses the typed digest. This lets a previous binary still deduplicate a pending command. If a rollback writer drops the added fields, the new binary reconstructs exact replay evidence from the queue and legacy claim; an unrecoverable retained claim rejects reuse fail closed. Legacy aliases plus canonical history remain bounded to at most 2000 claim records.\n",
)
print("command safety follow-up applied")
