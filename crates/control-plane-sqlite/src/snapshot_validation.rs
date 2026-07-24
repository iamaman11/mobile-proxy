use std::collections::{BTreeMap, BTreeSet, VecDeque};

use mobile_proxy_application::{
    MAX_COMMAND_QUEUE_PER_DEVICE, MAX_IDEMPOTENCY_RESULTS, MAX_PENDING_COMMANDS,
    MAX_REGISTERED_DEVICES, idempotency_scope_key, request_fingerprint,
};
use mobile_proxy_foundation::{CommandId, ContentDigest};
use proxy_core::{DeviceCommand, IssueCommandRequest};

use crate::snapshot::{CommandQueues, DeviceMap, ReplayRecord};
use crate::snapshot_error::SnapshotViolation;
use crate::snapshot_rows::SnapshotRows;

pub(super) fn validate_rows(
    rows: SnapshotRows,
) -> Result<(DeviceMap, CommandQueues, Vec<ReplayRecord>), SnapshotViolation> {
    let (device_rows, result_rows, claim_rows, pending_rows) = rows.into_parts();
    if device_rows.len() > MAX_REGISTERED_DEVICES {
        return Err(SnapshotViolation::DeviceCapacityExceeded);
    }
    if result_rows.len() > MAX_IDEMPOTENCY_RESULTS
        || claim_rows.len() > MAX_IDEMPOTENCY_RESULTS
    {
        return Err(SnapshotViolation::ReplayCapacityExceeded);
    }
    if pending_rows.len() > MAX_PENDING_COMMANDS {
        return Err(SnapshotViolation::PendingCapacityExceeded);
    }

    let mut devices = DeviceMap::new();
    for row in device_rows {
        let (node_id, record) = row.into_parts();
        if node_id.is_empty() || record.node_id != node_id {
            return Err(SnapshotViolation::DeviceKeyMismatch);
        }
        if devices.insert(node_id, record).is_some() {
            return Err(SnapshotViolation::DuplicateDevice);
        }
    }

    let mut results_by_scope = BTreeMap::<String, (ContentDigest, DeviceCommand)>::new();
    let mut result_scope_by_command = BTreeMap::<String, String>::new();
    for row in result_rows {
        let (scope_key, command_id, command) = row.into_parts();
        if command.device_id.is_empty() {
            return Err(SnapshotViolation::EmptyDeviceId);
        }
        if command_id != command.command_id {
            return Err(SnapshotViolation::CommandResultIdentityMismatch);
        }
        let expected_scope = idempotency_scope_key(&command.device_id, &command.idempotency_key);
        if scope_key != expected_scope {
            return Err(SnapshotViolation::ReplayScopeMismatch);
        }

        let scope_text = scope_key.to_string();
        if results_by_scope
            .insert(scope_text.clone(), (scope_key, command.clone()))
            .is_some()
        {
            return Err(SnapshotViolation::DuplicateReplayScope);
        }
        if result_scope_by_command
            .insert(command_id.to_string(), scope_text)
            .is_some()
        {
            return Err(SnapshotViolation::DuplicateCommandId);
        }
    }

    let mut claims_by_scope = BTreeMap::<String, (CommandId, ContentDigest)>::new();
    for row in claim_rows {
        let (scope_key, command_id, request_fingerprint_value) = row.into_parts();
        let scope_text = scope_key.to_string();
        if claims_by_scope.contains_key(&scope_text) {
            return Err(SnapshotViolation::DuplicateClaimScope);
        }
        let Some((_, command)) = results_by_scope.get(&scope_text) else {
            return Err(SnapshotViolation::ClaimResultMissing);
        };
        if command_id != command.command_id {
            return Err(SnapshotViolation::ClaimCommandMismatch);
        }
        let expected_fingerprint = request_fingerprint(&command.device_id, &request_for(command));
        if request_fingerprint_value != expected_fingerprint {
            return Err(SnapshotViolation::ReplayEvidenceMismatch);
        }
        claims_by_scope.insert(scope_text, (command_id, request_fingerprint_value));
    }

    if results_by_scope
        .keys()
        .any(|scope| !claims_by_scope.contains_key(scope))
    {
        return Err(SnapshotViolation::ReplayClaimMissing);
    }

    let mut pending_ids = BTreeSet::new();
    let mut pending_by_device = BTreeMap::<String, BTreeMap<u32, DeviceCommand>>::new();
    for row in pending_rows {
        let (command_id, device_id, queue_position, command) = row.into_parts();
        if device_id.is_empty() || command.device_id.is_empty() {
            return Err(SnapshotViolation::EmptyDeviceId);
        }
        if command_id != command.command_id {
            return Err(SnapshotViolation::PendingIdentityMismatch);
        }
        if device_id != command.device_id {
            return Err(SnapshotViolation::PendingDeviceMismatch);
        }
        if !pending_ids.insert(command_id.to_string()) {
            return Err(SnapshotViolation::DuplicatePendingCommand);
        }

        let Some(scope) = result_scope_by_command.get(&command_id.to_string()) else {
            return Err(SnapshotViolation::PendingReplayMissing);
        };
        let Some((_, replay_command)) = results_by_scope.get(scope) else {
            return Err(SnapshotViolation::PendingReplayMissing);
        };
        if replay_command != &command {
            return Err(SnapshotViolation::PendingReplayMismatch);
        }

        let positions = pending_by_device.entry(device_id).or_default();
        if positions.insert(queue_position, command).is_some() {
            return Err(SnapshotViolation::DuplicateQueuePosition);
        }
        if positions.len() > MAX_COMMAND_QUEUE_PER_DEVICE {
            return Err(SnapshotViolation::DeviceQueueCapacityExceeded);
        }
    }

    let mut queues = CommandQueues::new();
    for (device_id, positions) in pending_by_device {
        let mut queue = VecDeque::with_capacity(positions.len());
        for (expected, (position, command)) in positions.into_iter().enumerate() {
            let expected = u32::try_from(expected)
                .map_err(|_| SnapshotViolation::PendingCapacityExceeded)?;
            if position != expected {
                return Err(SnapshotViolation::NonContiguousQueuePosition);
            }
            queue.push_back(command);
        }
        queues.insert(device_id, queue);
    }

    let replay_records = results_by_scope
        .into_iter()
        .map(|(scope, (scope_key, command))| {
            let (_, fingerprint) = claims_by_scope
                .get(&scope)
                .expect("validated result must have one exact claim");
            ReplayRecord::new(scope_key, *fingerprint, command)
        })
        .collect();

    Ok((devices, queues, replay_records))
}

fn request_for(command: &DeviceCommand) -> IssueCommandRequest {
    IssueCommandRequest {
        desired_state: command.desired_state,
        recovery_intent: command.recovery_intent,
        deadline_secs: command.deadline_secs,
        idempotency_key: command.idempotency_key.clone(),
    }
}
