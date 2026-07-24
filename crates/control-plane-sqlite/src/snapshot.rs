use std::collections::{BTreeMap, VecDeque};
use std::error::Error;
use std::fmt::{Display, Formatter};
use std::str::FromStr;

use mobile_proxy_application::{idempotency_scope_key, request_fingerprint};
use mobile_proxy_foundation::{CommandId, ContentDigest};
use proxy_core::{DeviceCommand, DeviceRecord, IssueCommandRequest};
use rusqlite::{Connection, TransactionBehavior, params};
use serde::{Deserialize, Serialize, de::DeserializeOwned};

use crate::snapshot_error::{SnapshotError, SnapshotViolation};
use crate::snapshot_rows::{
    CommandResultRow, DeviceRow, IdempotencyClaimRow, PendingCommandRow, SnapshotRows,
};
use crate::snapshot_validation::validate_rows;
use crate::{SqliteStore, StoreError};

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

#[derive(Debug)]
pub enum SnapshotStoreError {
    Store(StoreError),
    Json {
        field: &'static str,
        source: serde_json::Error,
    },
    InvalidField {
        field: &'static str,
    },
    InvalidSnapshot(SnapshotViolation),
}

impl Display for SnapshotStoreError {
    fn fmt(&self, formatter: &mut Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Store(_) => formatter.write_str("SQLite snapshot store operation failed"),
            Self::Json { field, .. } => write!(formatter, "invalid typed JSON in {field}"),
            Self::InvalidField { field } => write!(formatter, "invalid typed SQLite field: {field}"),
            Self::InvalidSnapshot(error) => write!(formatter, "invalid control-plane snapshot: {error}"),
        }
    }
}

impl Error for SnapshotStoreError {
    fn source(&self) -> Option<&(dyn Error + 'static)> {
        match self {
            Self::Store(error) => Some(error),
            Self::Json { source, .. } => Some(source),
            Self::InvalidField { .. } => None,
            Self::InvalidSnapshot(error) => Some(error),
        }
    }
}

impl From<StoreError> for SnapshotStoreError {
    fn from(error: StoreError) -> Self {
        Self::Store(error)
    }
}

impl From<rusqlite::Error> for SnapshotStoreError {
    fn from(error: rusqlite::Error) -> Self {
        Self::Store(StoreError::from(error))
    }
}

impl From<SnapshotViolation> for SnapshotStoreError {
    fn from(error: SnapshotViolation) -> Self {
        Self::InvalidSnapshot(error)
    }
}

impl SqliteStore {
    pub fn replace_snapshot(
        &mut self,
        snapshot: &ControlPlaneSnapshot,
    ) -> Result<(), SnapshotStoreError> {
        snapshot.validate()?;
        let rows = snapshot.rows();
        let transaction = self
            .connection
            .transaction_with_behavior(TransactionBehavior::Immediate)?;
        replace_snapshot_rows(&transaction, &rows)?;
        transaction.commit()?;
        Ok(())
    }

    pub fn load_snapshot(&self) -> Result<ControlPlaneSnapshot, SnapshotStoreError> {
        let rows = load_snapshot_rows(&self.connection)?;
        ControlPlaneSnapshot::from_rows(rows).map_err(Into::into)
    }
}

fn replace_snapshot_rows(
    connection: &Connection,
    rows: &SnapshotRows,
) -> Result<(), SnapshotStoreError> {
    connection.execute_batch(
        "DELETE FROM pending_commands;\n\
         DELETE FROM idempotency_claims;\n\
         DELETE FROM command_results;\n\
         DELETE FROM devices;",
    )?;

    for row in rows.devices() {
        let record_json = encode_json("devices.record_json", row.record())?;
        connection.execute(
            "INSERT INTO devices (node_id, record_json) VALUES (?1, ?2)",
            params![row.node_id(), record_json],
        )?;
    }

    for row in rows.command_results() {
        let result_json = encode_json("command_results.result_json", row.result())?;
        connection.execute(
            "INSERT INTO command_results (scope_key, command_id, result_json) \
             VALUES (?1, ?2, ?3)",
            params![
                row.scope_key().to_string(),
                row.command_id().to_string(),
                result_json
            ],
        )?;
    }

    for row in rows.idempotency_claims() {
        connection.execute(
            "INSERT INTO idempotency_claims \
             (scope_key, command_id, request_fingerprint) VALUES (?1, ?2, ?3)",
            params![
                row.scope_key().to_string(),
                row.command_id().to_string(),
                row.request_fingerprint().to_string()
            ],
        )?;
    }

    for row in rows.pending_commands() {
        let command_json = encode_json("pending_commands.command_json", row.command())?;
        connection.execute(
            "INSERT INTO pending_commands \
             (command_id, device_id, queue_position, command_json) VALUES (?1, ?2, ?3, ?4)",
            params![
                row.command_id().to_string(),
                row.device_id(),
                i64::from(row.queue_position()),
                command_json
            ],
        )?;
    }

    Ok(())
}

fn load_snapshot_rows(connection: &Connection) -> Result<SnapshotRows, SnapshotStoreError> {
    Ok(SnapshotRows::new(
        load_device_rows(connection)?,
        load_command_result_rows(connection)?,
        load_idempotency_claim_rows(connection)?,
        load_pending_command_rows(connection)?,
    ))
}

fn load_device_rows(connection: &Connection) -> Result<Vec<DeviceRow>, SnapshotStoreError> {
    let mut statement = connection.prepare(
        "SELECT node_id, record_json FROM devices ORDER BY node_id",
    )?;
    let raw_rows = statement
        .query_map([], |row| Ok((row.get::<_, String>(0)?, row.get::<_, String>(1)?)))?
        .collect::<rusqlite::Result<Vec<_>>>()?;

    raw_rows
        .into_iter()
        .map(|(node_id, record_json)| {
            Ok(DeviceRow::new(
                node_id,
                decode_json("devices.record_json", &record_json)?,
            ))
        })
        .collect()
}

fn load_command_result_rows(
    connection: &Connection,
) -> Result<Vec<CommandResultRow>, SnapshotStoreError> {
    let mut statement = connection.prepare(
        "SELECT scope_key, command_id, result_json \
         FROM command_results ORDER BY scope_key",
    )?;
    let raw_rows = statement
        .query_map([], |row| {
            Ok((
                row.get::<_, String>(0)?,
                row.get::<_, String>(1)?,
                row.get::<_, String>(2)?,
            ))
        })?
        .collect::<rusqlite::Result<Vec<_>>>()?;

    raw_rows
        .into_iter()
        .map(|(scope_key, command_id, result_json)| {
            Ok(CommandResultRow::new(
                parse_digest("command_results.scope_key", &scope_key)?,
                parse_command_id("command_results.command_id", &command_id)?,
                decode_json("command_results.result_json", &result_json)?,
            ))
        })
        .collect()
}

fn load_idempotency_claim_rows(
    connection: &Connection,
) -> Result<Vec<IdempotencyClaimRow>, SnapshotStoreError> {
    let mut statement = connection.prepare(
        "SELECT scope_key, command_id, request_fingerprint \
         FROM idempotency_claims ORDER BY scope_key",
    )?;
    let raw_rows = statement
        .query_map([], |row| {
            Ok((
                row.get::<_, String>(0)?,
                row.get::<_, String>(1)?,
                row.get::<_, String>(2)?,
            ))
        })?
        .collect::<rusqlite::Result<Vec<_>>>()?;

    raw_rows
        .into_iter()
        .map(|(scope_key, command_id, request_fingerprint)| {
            Ok(IdempotencyClaimRow::new(
                parse_digest("idempotency_claims.scope_key", &scope_key)?,
                parse_command_id("idempotency_claims.command_id", &command_id)?,
                parse_digest(
                    "idempotency_claims.request_fingerprint",
                    &request_fingerprint,
                )?,
            ))
        })
        .collect()
}

fn load_pending_command_rows(
    connection: &Connection,
) -> Result<Vec<PendingCommandRow>, SnapshotStoreError> {
    let mut statement = connection.prepare(
        "SELECT command_id, device_id, queue_position, command_json \
         FROM pending_commands ORDER BY device_id, queue_position",
    )?;
    let raw_rows = statement
        .query_map([], |row| {
            Ok((
                row.get::<_, String>(0)?,
                row.get::<_, String>(1)?,
                row.get::<_, i64>(2)?,
                row.get::<_, String>(3)?,
            ))
        })?
        .collect::<rusqlite::Result<Vec<_>>>()?;

    raw_rows
        .into_iter()
        .map(|(command_id, device_id, queue_position, command_json)| {
            Ok(PendingCommandRow::new(
                parse_command_id("pending_commands.command_id", &command_id)?,
                device_id,
                u32::try_from(queue_position).map_err(|_| SnapshotStoreError::InvalidField {
                    field: "pending_commands.queue_position",
                })?,
                decode_json("pending_commands.command_json", &command_json)?,
            ))
        })
        .collect()
}

fn encode_json<T: Serialize + ?Sized>(
    field: &'static str,
    value: &T,
) -> Result<String, SnapshotStoreError> {
    serde_json::to_string(value).map_err(|source| SnapshotStoreError::Json { field, source })
}

fn decode_json<T: DeserializeOwned>(
    field: &'static str,
    value: &str,
) -> Result<T, SnapshotStoreError> {
    serde_json::from_str(value).map_err(|source| SnapshotStoreError::Json { field, source })
}

fn parse_digest(
    field: &'static str,
    value: &str,
) -> Result<ContentDigest, SnapshotStoreError> {
    ContentDigest::from_str(value).map_err(|_| SnapshotStoreError::InvalidField { field })
}

fn parse_command_id(
    field: &'static str,
    value: &str,
) -> Result<CommandId, SnapshotStoreError> {
    CommandId::from_str(value).map_err(|_| SnapshotStoreError::InvalidField { field })
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

#[cfg(test)]
#[path = "snapshot_store_tests.rs"]
mod store_tests;
