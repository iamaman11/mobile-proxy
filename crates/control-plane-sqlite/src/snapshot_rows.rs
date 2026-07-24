use mobile_proxy_application::{idempotency_scope_key, request_fingerprint};
use mobile_proxy_foundation::{CommandId, ContentDigest};
use proxy_core::{DeviceCommand, DeviceRecord, IssueCommandRequest};
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct DeviceRow {
    node_id: String,
    record: DeviceRecord,
}

impl DeviceRow {
    pub fn from_record(record: DeviceRecord) -> Self {
        Self {
            node_id: record.node_id.clone(),
            record,
        }
    }

    pub fn new(node_id: impl Into<String>, record: DeviceRecord) -> Self {
        Self {
            node_id: node_id.into(),
            record,
        }
    }

    pub fn node_id(&self) -> &str {
        &self.node_id
    }

    pub fn record(&self) -> &DeviceRecord {
        &self.record
    }

    pub fn into_parts(self) -> (String, DeviceRecord) {
        (self.node_id, self.record)
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct CommandResultRow {
    scope_key: ContentDigest,
    command_id: CommandId,
    result: DeviceCommand,
}

impl CommandResultRow {
    pub fn from_command(command: DeviceCommand) -> Self {
        Self {
            scope_key: idempotency_scope_key(&command.device_id, &command.idempotency_key),
            command_id: command.command_id,
            result: command,
        }
    }

    pub const fn new(
        scope_key: ContentDigest,
        command_id: CommandId,
        result: DeviceCommand,
    ) -> Self {
        Self {
            scope_key,
            command_id,
            result,
        }
    }

    pub const fn scope_key(&self) -> ContentDigest {
        self.scope_key
    }

    pub const fn command_id(&self) -> CommandId {
        self.command_id
    }

    pub fn result(&self) -> &DeviceCommand {
        &self.result
    }

    pub fn into_parts(self) -> (ContentDigest, CommandId, DeviceCommand) {
        (self.scope_key, self.command_id, self.result)
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct IdempotencyClaimRow {
    scope_key: ContentDigest,
    command_id: CommandId,
    request_fingerprint: ContentDigest,
}

impl IdempotencyClaimRow {
    pub fn from_command(command: &DeviceCommand) -> Self {
        Self {
            scope_key: idempotency_scope_key(&command.device_id, &command.idempotency_key),
            command_id: command.command_id,
            request_fingerprint: request_fingerprint(&command.device_id, &request_for(command)),
        }
    }

    pub const fn new(
        scope_key: ContentDigest,
        command_id: CommandId,
        request_fingerprint: ContentDigest,
    ) -> Self {
        Self {
            scope_key,
            command_id,
            request_fingerprint,
        }
    }

    pub const fn scope_key(&self) -> ContentDigest {
        self.scope_key
    }

    pub const fn command_id(&self) -> CommandId {
        self.command_id
    }

    pub const fn request_fingerprint(&self) -> ContentDigest {
        self.request_fingerprint
    }

    pub const fn into_parts(self) -> (ContentDigest, CommandId, ContentDigest) {
        (self.scope_key, self.command_id, self.request_fingerprint)
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct PendingCommandRow {
    command_id: CommandId,
    device_id: String,
    queue_position: u32,
    command: DeviceCommand,
}

impl PendingCommandRow {
    pub fn from_command(queue_position: u32, command: DeviceCommand) -> Self {
        Self {
            command_id: command.command_id,
            device_id: command.device_id.clone(),
            queue_position,
            command,
        }
    }

    pub fn new(
        command_id: CommandId,
        device_id: impl Into<String>,
        queue_position: u32,
        command: DeviceCommand,
    ) -> Self {
        Self {
            command_id,
            device_id: device_id.into(),
            queue_position,
            command,
        }
    }

    pub const fn command_id(&self) -> CommandId {
        self.command_id
    }

    pub fn device_id(&self) -> &str {
        &self.device_id
    }

    pub const fn queue_position(&self) -> u32 {
        self.queue_position
    }

    pub fn command(&self) -> &DeviceCommand {
        &self.command
    }

    pub fn into_parts(self) -> (CommandId, String, u32, DeviceCommand) {
        (
            self.command_id,
            self.device_id,
            self.queue_position,
            self.command,
        )
    }
}

#[derive(Debug, Clone)]
pub struct SnapshotRows {
    devices: Vec<DeviceRow>,
    command_results: Vec<CommandResultRow>,
    idempotency_claims: Vec<IdempotencyClaimRow>,
    pending_commands: Vec<PendingCommandRow>,
}

impl SnapshotRows {
    pub fn new(
        devices: Vec<DeviceRow>,
        command_results: Vec<CommandResultRow>,
        idempotency_claims: Vec<IdempotencyClaimRow>,
        pending_commands: Vec<PendingCommandRow>,
    ) -> Self {
        Self {
            devices,
            command_results,
            idempotency_claims,
            pending_commands,
        }
    }

    pub fn devices(&self) -> &[DeviceRow] {
        &self.devices
    }

    pub fn command_results(&self) -> &[CommandResultRow] {
        &self.command_results
    }

    pub fn idempotency_claims(&self) -> &[IdempotencyClaimRow] {
        &self.idempotency_claims
    }

    pub fn pending_commands(&self) -> &[PendingCommandRow] {
        &self.pending_commands
    }

    pub fn into_parts(
        self,
    ) -> (
        Vec<DeviceRow>,
        Vec<CommandResultRow>,
        Vec<IdempotencyClaimRow>,
        Vec<PendingCommandRow>,
    ) {
        (
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
