use std::collections::{BTreeMap, BTreeSet, VecDeque};
use std::error::Error;
use std::fmt::{Display, Formatter};

use mobile_proxy_application::{
    MAX_COMMAND_QUEUE_PER_DEVICE, MAX_IDEMPOTENCY_RESULTS, MAX_PENDING_COMMANDS,
    MAX_REGISTERED_DEVICES, idempotency_scope_key, request_fingerprint,
};
use mobile_proxy_foundation::{CommandId, ContentDigest};
use proxy_core::{DeviceCommand, DeviceRecord, IssueCommandRequest};

pub type DeviceMap = BTreeMap<String, DeviceRecord>;
pub type CommandQueues = BTreeMap<String, VecDeque<DeviceCommand>>;

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ReplayRecord {
    scope_key: ContentDigest,
    request_fingerprint: ContentDigest,
    command: DeviceCommand,
}

impl ReplayRecord {
    pub fn from_command(command: DeviceCommand) -> Self {
        let request = request_for(&command);
        Self {
            scope_key: idempotency_scope_key(&command.device_id, &command.idempotency_key),
            request_fingerprint: request_fingerprint(&command.device_id, &request),
            command,
        }
    }

    pub fn new(
        scope_key: ContentDigest,
        request_fingerprint: ContentDigest,
        command: DeviceCommand,
    ) -> Self {
        Self {
            scope_key,
            request_fingerprint,
            command,
        }
    }

    pub const fn scope_key(&self) -> ContentDigest {
        self.scope_key
    }

    pub const fn request_fingerprint(&self) -> ContentDigest {
        self.request_fingerprint
    }

    pub fn command(&self) -> &DeviceCommand {
        &self.command
    }

    pub fn into_command(self) -> DeviceCommand {
        self.command
    }
}

#[derive(Debug, Clone)]
pub struct ControlPlaneSnapshot {
    devices: DeviceMap,
    queues: CommandQueues,
    replay_records: Vec<ReplayRecord>,
}

impl ControlPlaneSnapshot {
    pub fn empty() -> Self {
        Self {
            devices: DeviceMap::new(),
            queues: CommandQueues::new(),
            replay_records: Vec::new(),
        }
    }

    pub fn from_parts(
        devices: DeviceMap,
        queues: CommandQueues,
        replay_records: Vec<ReplayRecord>,
    ) -> Result<Self, SnapshotViolation> {
        let snapshot = Self {
            devices,
            queues,
            replay_records,
        };
        snapshot.validate()?;
        Ok(snapshot)
    }

    pub fn devices(&self) -> &DeviceMap {
        &self.devices
    }

    pub fn queues(&self) -> &CommandQueues {
        &self.queues
    }

    pub fn replay_records(&self) -> &[ReplayRecord] {
        &self.replay_records
    }

    pub fn into_parts(self) -> (DeviceMap, CommandQueues, Vec<ReplayRecord>) {
        (self.devices, self.queues, self.replay_records)
    }

    pub fn validate(&self) -> Result<(), SnapshotViolation> {
        if self.devices.len() > MAX_REGISTERED_DEVICES {
            return Err(SnapshotViolation::DeviceCapacityExceeded);
        }
        if self.replay_records.len() > MAX_IDEMPOTENCY_RESULTS {
            return Err(SnapshotViolation::ReplayCapacityExceeded);
        }

        for (node_id, device) in &self.devices {
            if node_id.is_empty() || device.node_id != *node_id {
                return Err(SnapshotViolation::DeviceKeyMismatch);
            }
        }

        let mut replay_by_command = BTreeMap::<CommandId, &DeviceCommand>::new();
        let mut replay_scopes = BTreeSet::new();
        for record in &self.replay_records {
            let command = record.command();
            if command.device_id.is_empty() {
                return Err(SnapshotViolation::EmptyDeviceId);
            }
            let request = request_for(command);
            let expected_scope =
                idempotency_scope_key(&command.device_id, &command.idempotency_key);
            let expected_fingerprint = request_fingerprint(&command.device_id, &request);
            if record.scope_key() != expected_scope
                || record.request_fingerprint() != expected_fingerprint
            {
                return Err(SnapshotViolation::ReplayEvidenceMismatch);
            }
            if !replay_scopes.insert(record.scope_key()) {
                return Err(SnapshotViolation::DuplicateReplayScope);
            }
            if replay_by_command
                .insert(command.command_id, command)
                .is_some()
            {
                return Err(SnapshotViolation::DuplicateCommandId);
            }
        }

        let mut pending_count = 0usize;
        let mut pending_ids = BTreeSet::new();
        for (device_id, queue) in &self.queues {
            if device_id.is_empty() {
                return Err(SnapshotViolation::EmptyDeviceId);
            }
            if queue.len() > MAX_COMMAND_QUEUE_PER_DEVICE {
                return Err(SnapshotViolation::DeviceQueueCapacityExceeded);
            }
            pending_count = pending_count
                .checked_add(queue.len())
                .ok_or(SnapshotViolation::PendingCapacityExceeded)?;
            if pending_count > MAX_PENDING_COMMANDS {
                return Err(SnapshotViolation::PendingCapacityExceeded);
            }

            for command in queue {
                if command.device_id != *device_id {
                    return Err(SnapshotViolation::PendingDeviceMismatch);
                }
                if !pending_ids.insert(command.command_id) {
                    return Err(SnapshotViolation::DuplicatePendingCommand);
                }
                match replay_by_command.get(&command.command_id) {
                    Some(replay) if *replay == command => {}
                    Some(_) => return Err(SnapshotViolation::PendingReplayMismatch),
                    None => return Err(SnapshotViolation::PendingReplayMissing),
                }
            }
        }

        Ok(())
    }
}

impl Default for ControlPlaneSnapshot {
    fn default() -> Self {
        Self::empty()
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum SnapshotViolation {
    DeviceCapacityExceeded,
    ReplayCapacityExceeded,
    PendingCapacityExceeded,
    DeviceQueueCapacityExceeded,
    DeviceKeyMismatch,
    EmptyDeviceId,
    ReplayEvidenceMismatch,
    DuplicateReplayScope,
    DuplicateCommandId,
    PendingDeviceMismatch,
    DuplicatePendingCommand,
    PendingReplayMissing,
    PendingReplayMismatch,
}

impl Display for SnapshotViolation {
    fn fmt(&self, formatter: &mut Formatter<'_>) -> std::fmt::Result {
        formatter.write_str(match self {
            Self::DeviceCapacityExceeded => "device capacity is exceeded",
            Self::ReplayCapacityExceeded => "replay capacity is exceeded",
            Self::PendingCapacityExceeded => "pending command capacity is exceeded",
            Self::DeviceQueueCapacityExceeded => "per-device command capacity is exceeded",
            Self::DeviceKeyMismatch => "device map key does not match the canonical record",
            Self::EmptyDeviceId => "device identity is empty",
            Self::ReplayEvidenceMismatch => "replay evidence does not match the command",
            Self::DuplicateReplayScope => "replay scope is duplicated",
            Self::DuplicateCommandId => "command identity is duplicated",
            Self::PendingDeviceMismatch => "pending command is bound to another device",
            Self::DuplicatePendingCommand => "pending command is duplicated",
            Self::PendingReplayMissing => "pending command has no durable replay result",
            Self::PendingReplayMismatch => "pending command differs from its replay result",
        })
    }
}

impl Error for SnapshotViolation {}

fn request_for(command: &DeviceCommand) -> IssueCommandRequest {
    IssueCommandRequest {
        desired_state: command.desired_state,
        recovery_intent: command.recovery_intent,
        deadline_secs: command.deadline_secs,
        idempotency_key: command.idempotency_key.clone(),
    }
}
