use std::collections::{BTreeMap, VecDeque};

use mobile_proxy_application::{idempotency_scope_key, request_fingerprint};
use mobile_proxy_foundation::ContentDigest;
use proxy_core::{DeviceCommand, DeviceRecord, IssueCommandRequest};
use serde::{Deserialize, Serialize};

use crate::snapshot_error::{SnapshotError, SnapshotViolation};
use crate::snapshot_rows::{
    CommandResultRow, DeviceRow, IdempotencyClaimRow, PendingCommandRow, SnapshotRows,
};
use crate::snapshot_validation::validate_rows;

pub const SNAPSHOT_FORMAT_VERSION: u32 = 1;

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

    pub const fn new(
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
        let device_rows = devices
            .into_iter()
            .map(|(node_id, record)| DeviceRow::new(node_id, record))
            .collect();
        let mut command_results = Vec::with_capacity(replay_records.len());
        let mut idempotency_claims = Vec::with_capacity(replay_records.len());
        for replay in replay_records {
            command_results.push(CommandResultRow::new(
                replay.scope_key,
                replay.command.command_id,
                replay.command.clone(),
            ));
            idempotency_claims.push(IdempotencyClaimRow::new(
                replay.scope_key,
                replay.command.command_id,
                replay.request_fingerprint,
            ));
        }

        let mut pending_commands = Vec::new();
        for (device_id, queue) in queues {
            for (position, command) in queue.into_iter().enumerate() {
                let queue_position = u32::try_from(position)
                    .map_err(|_| SnapshotViolation::PendingCapacityExceeded)?;
                pending_commands.push(PendingCommandRow::new(
                    command.command_id,
                    device_id.clone(),
                    queue_position,
                    command,
                ));
            }
        }

        Self::from_rows(SnapshotRows::new(
            device_rows,
            command_results,
            idempotency_claims,
            pending_commands,
        ))
    }

    pub fn from_rows(rows: SnapshotRows) -> Result<Self, SnapshotViolation> {
        let (devices, queues, replay_records) = validate_rows(rows)?;
        Ok(Self {
            devices,
            queues,
            replay_records,
        })
    }

    pub fn from_json(body: &[u8]) -> Result<Self, SnapshotError> {
        let document: SnapshotDocument = serde_json::from_slice(body)?;
        if document.schema_version != SNAPSHOT_FORMAT_VERSION {
            return Err(SnapshotViolation::UnsupportedSchemaVersion {
                found: document.schema_version,
                supported: SNAPSHOT_FORMAT_VERSION,
            }
            .into());
        }
        Self::from_rows(document.into_rows()).map_err(Into::into)
    }

    pub fn to_canonical_json(&self) -> Result<Vec<u8>, SnapshotError> {
        Ok(serde_json::to_vec(&SnapshotDocument::from_rows(
            self.rows(),
        ))?)
    }

    pub fn rows(&self) -> SnapshotRows {
        let devices = self
            .devices
            .iter()
            .map(|(node_id, record)| DeviceRow::new(node_id.clone(), record.clone()))
            .collect();
        let command_results = self
            .replay_records
            .iter()
            .map(|replay| {
                CommandResultRow::new(
                    replay.scope_key,
                    replay.command.command_id,
                    replay.command.clone(),
                )
            })
            .collect();
        let idempotency_claims = self
            .replay_records
            .iter()
            .map(|replay| {
                IdempotencyClaimRow::new(
                    replay.scope_key,
                    replay.command.command_id,
                    replay.request_fingerprint,
                )
            })
            .collect();
        let mut pending_commands = Vec::new();
        for (device_id, queue) in &self.queues {
            for (position, command) in queue.iter().enumerate() {
                let queue_position =
                    u32::try_from(position).expect("validated queue position must fit in u32");
                pending_commands.push(PendingCommandRow::new(
                    command.command_id,
                    device_id.clone(),
                    queue_position,
                    command.clone(),
                ));
            }
        }
        SnapshotRows::new(
            devices,
            command_results,
            idempotency_claims,
            pending_commands,
        )
    }

    pub fn validate(&self) -> Result<(), SnapshotViolation> {
        Self::from_rows(self.rows()).map(|_| ())
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
}

impl Default for ControlPlaneSnapshot {
    fn default() -> Self {
        Self::empty()
    }
}

#[derive(Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct SnapshotDocument {
    schema_version: u32,
    devices: Vec<DeviceRow>,
    command_results: Vec<CommandResultRow>,
    idempotency_claims: Vec<IdempotencyClaimRow>,
    pending_commands: Vec<PendingCommandRow>,
}

impl SnapshotDocument {
    fn from_rows(rows: SnapshotRows) -> Self {
        let (devices, command_results, idempotency_claims, pending_commands) = rows.into_parts();
        Self {
            schema_version: SNAPSHOT_FORMAT_VERSION,
            devices,
            command_results,
            idempotency_claims,
            pending_commands,
        }
    }

    fn into_rows(self) -> SnapshotRows {
        SnapshotRows::new(
            self.devices,
            self.command_results,
            self.idempotency_claims,
            self.pending_commands,
        )
    }
}

fn request_for(command: &DeviceCommand) -> IssueCommandRequest {
    IssueCommandRequest {
        desired_state: command.desired_state,
        recovery_intent: command.recovery_intent,
        deadline_secs: command.deadline_secs,
        idempotency_key: command.idempotency_key.clone(),
    }
}
