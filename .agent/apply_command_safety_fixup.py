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
    "services/control-plane/src/state.rs",
    "        if pending_command_count(&commands) >= MAX_PENDING_COMMANDS {\n"
    "            return Err(IssueCommandError::CapacityExceeded);\n"
    "        }\n",
    "        if pending_command_count(&commands) >= MAX_PENDING_COMMANDS\n"
    "            || commands\n"
    "                .queues\n"
    "                .get(&input.device_id)\n"
    "                .is_some_and(|queue| queue.len() >= MAX_COMMAND_QUEUE_PER_DEVICE)\n"
    "        {\n"
    "            return Err(IssueCommandError::CapacityExceeded);\n"
    "        }\n",
)
replace_once(
    "services/control-plane/src/state.rs",
    "        queue.push_back(command.clone());\n"
    "        while queue.len() > MAX_COMMAND_QUEUE_PER_DEVICE {\n"
    "            queue.pop_front();\n"
    "        }\n",
    "        queue.push_back(command.clone());\n",
)
replace_once(
    "services/control-plane/src/state.rs",
    "    use std::collections::HashMap;\n",
    "    use std::collections::{HashMap, VecDeque};\n",
)
replace_once(
    "services/control-plane/src/state.rs",
    "    #[tokio::test]\n"
    "    async fn pending_claims_are_not_evicted_when_global_capacity_is_full() {\n",
    r'''    #[tokio::test]
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
        let _ = fs::remove_file(path);
    }

    #[tokio::test]
    async fn pending_claims_are_not_evicted_when_global_capacity_is_full() {
''',
)
replace_once(
    "docs/architecture/command-issuance-application-port.md",
    "The delivery queue remains bounded to 50 commands per device and 1000 pending commands globally. Idempotency results have a deterministic bound of 1000 canonical entries. Pending results are never selected for retention eviction; when all capacity is pending, a new command fails with `command_capacity_exceeded` rather than dropping a live claim.\n",
    "The delivery queue remains bounded to 50 commands per device and 1000 pending commands globally. A full per-device or global queue fails with `command_capacity_exceeded`; no pending command is silently evicted. Idempotency results have a deterministic bound of 1000 canonical entries, and pending results are never selected for retention eviction.\n",
)
print("command safety fixup applied")
