use std::error::Error;
use std::fmt::{Display, Formatter};
use std::str::FromStr;

use mobile_proxy_foundation::{CommandId, ContentDigest, FoundationError};
use proxy_core::{DeviceCommand, DeviceRecord};
use rusqlite::{Transaction, TransactionBehavior, params};
use serde::Serialize;
use serde::de::DeserializeOwned;

use crate::{
    CommandResultRow, ControlPlaneSnapshot, DeviceRow, IdempotencyClaimRow, PendingCommandRow,
    SnapshotRows, SnapshotViolation, SqliteStore, StoreError,
};

#[derive(Debug)]
pub enum SnapshotStoreError {
    Store(StoreError),
    Json {
        relation: &'static str,
        source: serde_json::Error,
    },
    Foundation {
        relation: &'static str,
        field: &'static str,
        source: FoundationError,
    },
    QueuePositionOutOfRange(i64),
    Violation(SnapshotViolation),
}

impl Display for SnapshotStoreError {
    fn fmt(&self, formatter: &mut Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Store(error) => Display::fmt(error, formatter),
            Self::Json { relation, .. } => {
                write!(formatter, "{relation} contains invalid typed JSON")
            }
            Self::Foundation {
                relation, field, ..
            } => write!(
                formatter,
                "{relation}.{field} contains an invalid typed value"
            ),
            Self::QueuePositionOutOfRange(_) => {
                formatter.write_str("pending_commands.queue_position is outside the u32 range")
            }
            Self::Violation(error) => Display::fmt(error, formatter),
        }
    }
}

impl Error for SnapshotStoreError {
    fn source(&self) -> Option<&(dyn Error + 'static)> {
        match self {
            Self::Store(error) => Some(error),
            Self::Json { source, .. } => Some(source),
            Self::Foundation { source, .. } => Some(source),
            Self::QueuePositionOutOfRange(_) => None,
            Self::Violation(error) => Some(error),
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
        Self::Store(StoreError::Database(error))
    }
}

impl From<SnapshotViolation> for SnapshotStoreError {
    fn from(error: SnapshotViolation) -> Self {
        Self::Violation(error)
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
        replace_rows(&transaction, rows)?;
        transaction.commit()?;
        Ok(())
    }

    pub fn load_snapshot(&mut self) -> Result<ControlPlaneSnapshot, SnapshotStoreError> {
        let transaction = self
            .connection
            .transaction_with_behavior(TransactionBehavior::Deferred)?;
        let rows = load_rows(&transaction)?;
        let snapshot = ControlPlaneSnapshot::from_rows(rows)?;
        transaction.commit()?;
        Ok(snapshot)
    }
}

fn replace_rows(
    transaction: &Transaction<'_>,
    rows: SnapshotRows,
) -> Result<(), SnapshotStoreError> {
    transaction.execute("DELETE FROM pending_commands", [])?;
    transaction.execute("DELETE FROM idempotency_claims", [])?;
    transaction.execute("DELETE FROM command_results", [])?;
    transaction.execute("DELETE FROM devices", [])?;

    let (devices, command_results, idempotency_claims, pending_commands) = rows.into_parts();
    for row in devices {
        let (node_id, record) = row.into_parts();
        transaction.execute(
            "INSERT INTO devices (node_id, record_json) VALUES (?1, ?2)",
            params![node_id, encode_json("devices", &record)?],
        )?;
    }
    for row in command_results {
        let (scope_key, command_id, result) = row.into_parts();
        transaction.execute(
            "INSERT INTO command_results (scope_key, command_id, result_json) VALUES (?1, ?2, ?3)",
            params![
                scope_key.to_string(),
                command_id.to_string(),
                encode_json("command_results", &result)?
            ],
        )?;
    }
    for row in idempotency_claims {
        let (scope_key, command_id, request_fingerprint) = row.into_parts();
        transaction.execute(
            "INSERT INTO idempotency_claims (scope_key, command_id, request_fingerprint) \
             VALUES (?1, ?2, ?3)",
            params![
                scope_key.to_string(),
                command_id.to_string(),
                request_fingerprint.to_string()
            ],
        )?;
    }
    for row in pending_commands {
        let (command_id, device_id, queue_position, command) = row.into_parts();
        transaction.execute(
            "INSERT INTO pending_commands \
             (command_id, device_id, queue_position, command_json) VALUES (?1, ?2, ?3, ?4)",
            params![
                command_id.to_string(),
                device_id,
                i64::from(queue_position),
                encode_json("pending_commands", &command)?
            ],
        )?;
    }
    Ok(())
}

fn load_rows(transaction: &Transaction<'_>) -> Result<SnapshotRows, SnapshotStoreError> {
    Ok(SnapshotRows::new(
        load_devices(transaction)?,
        load_command_results(transaction)?,
        load_idempotency_claims(transaction)?,
        load_pending_commands(transaction)?,
    ))
}

fn load_devices(transaction: &Transaction<'_>) -> Result<Vec<DeviceRow>, SnapshotStoreError> {
    let mut statement =
        transaction.prepare("SELECT node_id, record_json FROM devices ORDER BY node_id")?;
    let raw = statement
        .query_map([], |row| {
            Ok((row.get::<_, String>(0)?, row.get::<_, String>(1)?))
        })?
        .collect::<rusqlite::Result<Vec<_>>>()?;
    raw.into_iter()
        .map(|(node_id, record_json)| {
            Ok(DeviceRow::new(
                node_id,
                decode_json::<DeviceRecord>("devices", &record_json)?,
            ))
        })
        .collect()
}

fn load_command_results(
    transaction: &Transaction<'_>,
) -> Result<Vec<CommandResultRow>, SnapshotStoreError> {
    let mut statement = transaction.prepare(
        "SELECT scope_key, command_id, result_json FROM command_results ORDER BY scope_key",
    )?;
    let raw = statement
        .query_map([], |row| {
            Ok((
                row.get::<_, String>(0)?,
                row.get::<_, String>(1)?,
                row.get::<_, String>(2)?,
            ))
        })?
        .collect::<rusqlite::Result<Vec<_>>>()?;
    raw.into_iter()
        .map(|(scope_key, command_id, result_json)| {
            Ok(CommandResultRow::new(
                parse_digest("command_results", "scope_key", &scope_key)?,
                parse_command_id("command_results", "command_id", &command_id)?,
                decode_json::<DeviceCommand>("command_results", &result_json)?,
            ))
        })
        .collect()
}

fn load_idempotency_claims(
    transaction: &Transaction<'_>,
) -> Result<Vec<IdempotencyClaimRow>, SnapshotStoreError> {
    let mut statement = transaction.prepare(
        "SELECT scope_key, command_id, request_fingerprint \
         FROM idempotency_claims ORDER BY scope_key",
    )?;
    let raw = statement
        .query_map([], |row| {
            Ok((
                row.get::<_, String>(0)?,
                row.get::<_, String>(1)?,
                row.get::<_, String>(2)?,
            ))
        })?
        .collect::<rusqlite::Result<Vec<_>>>()?;
    raw.into_iter()
        .map(|(scope_key, command_id, request_fingerprint)| {
            Ok(IdempotencyClaimRow::new(
                parse_digest("idempotency_claims", "scope_key", &scope_key)?,
                parse_command_id("idempotency_claims", "command_id", &command_id)?,
                parse_digest(
                    "idempotency_claims",
                    "request_fingerprint",
                    &request_fingerprint,
                )?,
            ))
        })
        .collect()
}

fn load_pending_commands(
    transaction: &Transaction<'_>,
) -> Result<Vec<PendingCommandRow>, SnapshotStoreError> {
    let mut statement = transaction.prepare(
        "SELECT command_id, device_id, queue_position, command_json \
         FROM pending_commands ORDER BY device_id, queue_position",
    )?;
    let raw = statement
        .query_map([], |row| {
            Ok((
                row.get::<_, String>(0)?,
                row.get::<_, String>(1)?,
                row.get::<_, i64>(2)?,
                row.get::<_, String>(3)?,
            ))
        })?
        .collect::<rusqlite::Result<Vec<_>>>()?;
    raw.into_iter()
        .map(|(command_id, device_id, queue_position, command_json)| {
            Ok(PendingCommandRow::new(
                parse_command_id("pending_commands", "command_id", &command_id)?,
                device_id,
                u32::try_from(queue_position)
                    .map_err(|_| SnapshotStoreError::QueuePositionOutOfRange(queue_position))?,
                decode_json::<DeviceCommand>("pending_commands", &command_json)?,
            ))
        })
        .collect()
}

fn encode_json<T: Serialize>(
    relation: &'static str,
    value: &T,
) -> Result<String, SnapshotStoreError> {
    serde_json::to_string(value).map_err(|source| SnapshotStoreError::Json { relation, source })
}

fn decode_json<T: DeserializeOwned>(
    relation: &'static str,
    raw: &str,
) -> Result<T, SnapshotStoreError> {
    serde_json::from_str(raw).map_err(|source| SnapshotStoreError::Json { relation, source })
}

fn parse_digest(
    relation: &'static str,
    field: &'static str,
    raw: &str,
) -> Result<ContentDigest, SnapshotStoreError> {
    ContentDigest::from_str(raw).map_err(|source| SnapshotStoreError::Foundation {
        relation,
        field,
        source,
    })
}

fn parse_command_id(
    relation: &'static str,
    field: &'static str,
    raw: &str,
) -> Result<CommandId, SnapshotStoreError> {
    CommandId::from_str(raw).map_err(|source| SnapshotStoreError::Foundation {
        relation,
        field,
        source,
    })
}
