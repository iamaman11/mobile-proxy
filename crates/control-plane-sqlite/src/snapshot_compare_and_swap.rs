use std::collections::BTreeMap;
use std::error::Error;
use std::fmt::{Display, Formatter};

use rusqlite::{Transaction, TransactionBehavior, params};
use serde::Serialize;

use crate::{
    ControlPlaneSnapshot, SnapshotStoreError, SnapshotViolation, SqliteStore, StoreError,
};

#[derive(Debug, Clone, Copy, Default, PartialEq, Eq)]
pub struct SnapshotRowChanges {
    pub devices_upserted: usize,
    pub devices_deleted: usize,
    pub command_results_inserted: usize,
    pub command_results_deleted: usize,
    pub idempotency_claims_inserted: usize,
    pub idempotency_claims_deleted: usize,
    pub pending_commands_inserted: usize,
    pub pending_commands_deleted: usize,
}

#[derive(Debug)]
pub enum SnapshotCompareAndSwapError {
    Store(SnapshotStoreError),
    StaleExpectedState,
    PostWriteParityMismatch,
}

impl Display for SnapshotCompareAndSwapError {
    fn fmt(&self, formatter: &mut Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Store(error) => Display::fmt(error, formatter),
            Self::StaleExpectedState => formatter
                .write_str("SQLite state does not match the expected control-plane snapshot"),
            Self::PostWriteParityMismatch => formatter
                .write_str("SQLite row mutation did not produce the candidate snapshot"),
        }
    }
}

impl Error for SnapshotCompareAndSwapError {
    fn source(&self) -> Option<&(dyn Error + 'static)> {
        match self {
            Self::Store(error) => Some(error),
            Self::StaleExpectedState | Self::PostWriteParityMismatch => None,
        }
    }
}

impl From<SnapshotStoreError> for SnapshotCompareAndSwapError {
    fn from(error: SnapshotStoreError) -> Self {
        Self::Store(error)
    }
}

impl From<SnapshotViolation> for SnapshotCompareAndSwapError {
    fn from(error: SnapshotViolation) -> Self {
        Self::Store(SnapshotStoreError::Violation(error))
    }
}

impl From<rusqlite::Error> for SnapshotCompareAndSwapError {
    fn from(error: rusqlite::Error) -> Self {
        Self::Store(SnapshotStoreError::Store(StoreError::Database(error)))
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct RelationalState {
    devices: BTreeMap<String, String>,
    command_results: BTreeMap<String, (String, String)>,
    idempotency_claims: BTreeMap<String, (String, String)>,
    pending_commands: BTreeMap<String, (String, i64, String)>,
}

impl SqliteStore {
    pub fn compare_and_swap_snapshot(
        &mut self,
        expected: &ControlPlaneSnapshot,
        candidate: &ControlPlaneSnapshot,
    ) -> Result<SnapshotRowChanges, SnapshotCompareAndSwapError> {
        expected.validate()?;
        candidate.validate()?;
        let expected_rows = materialize(expected)?;
        let candidate_rows = materialize(candidate)?;

        let transaction = self
            .connection
            .transaction_with_behavior(TransactionBehavior::Immediate)?;
        let current_rows = load_relational_state(&transaction)?;
        if current_rows != expected_rows {
            return Err(SnapshotCompareAndSwapError::StaleExpectedState);
        }

        let changes = apply_row_changes(&transaction, &current_rows, &candidate_rows)?;
        if load_relational_state(&transaction)? != candidate_rows {
            return Err(SnapshotCompareAndSwapError::PostWriteParityMismatch);
        }
        transaction.commit()?;
        Ok(changes)
    }
}

fn materialize(
    snapshot: &ControlPlaneSnapshot,
) -> Result<RelationalState, SnapshotCompareAndSwapError> {
    let (device_rows, result_rows, claim_rows, pending_rows) = snapshot.rows().into_parts();
    let mut devices = BTreeMap::new();
    let mut command_results = BTreeMap::new();
    let mut idempotency_claims = BTreeMap::new();
    let mut pending_commands = BTreeMap::new();

    for row in device_rows {
        let (node_id, record) = row.into_parts();
        devices.insert(node_id, encode_json("devices", &record)?);
    }
    for row in result_rows {
        let (scope_key, command_id, command) = row.into_parts();
        command_results.insert(
            scope_key.to_string(),
            (
                command_id.to_string(),
                encode_json("command_results", &command)?,
            ),
        );
    }
    for row in claim_rows {
        let (scope_key, command_id, request_fingerprint) = row.into_parts();
        idempotency_claims.insert(
            scope_key.to_string(),
            (command_id.to_string(), request_fingerprint.to_string()),
        );
    }
    for row in pending_rows {
        let (command_id, device_id, queue_position, command) = row.into_parts();
        pending_commands.insert(
            command_id.to_string(),
            (
                device_id,
                i64::from(queue_position),
                encode_json("pending_commands", &command)?,
            ),
        );
    }

    Ok(RelationalState {
        devices,
        command_results,
        idempotency_claims,
        pending_commands,
    })
}

fn load_relational_state(
    transaction: &Transaction<'_>,
) -> Result<RelationalState, SnapshotCompareAndSwapError> {
    Ok(RelationalState {
        devices: query_pairs(
            transaction,
            "SELECT node_id, record_json FROM devices ORDER BY node_id",
        )?,
        command_results: query_triples(
            transaction,
            "SELECT scope_key, command_id, result_json FROM command_results ORDER BY scope_key",
        )?,
        idempotency_claims: query_triples(
            transaction,
            "SELECT scope_key, command_id, request_fingerprint \
             FROM idempotency_claims ORDER BY scope_key",
        )?,
        pending_commands: query_pending(transaction)?,
    })
}

fn query_pairs(
    transaction: &Transaction<'_>,
    sql: &str,
) -> Result<BTreeMap<String, String>, SnapshotCompareAndSwapError> {
    let mut statement = transaction.prepare(sql)?;
    let rows = statement
        .query_map([], |row| {
            Ok((row.get::<_, String>(0)?, row.get::<_, String>(1)?))
        })?
        .collect::<rusqlite::Result<Vec<_>>>()?;
    Ok(rows.into_iter().collect())
}

fn query_triples(
    transaction: &Transaction<'_>,
    sql: &str,
) -> Result<BTreeMap<String, (String, String)>, SnapshotCompareAndSwapError> {
    let mut statement = transaction.prepare(sql)?;
    let rows = statement
        .query_map([], |row| {
            Ok((
                row.get::<_, String>(0)?,
                (row.get::<_, String>(1)?, row.get::<_, String>(2)?),
            ))
        })?
        .collect::<rusqlite::Result<Vec<_>>>()?;
    Ok(rows.into_iter().collect())
}

fn query_pending(
    transaction: &Transaction<'_>,
) -> Result<BTreeMap<String, (String, i64, String)>, SnapshotCompareAndSwapError> {
    let mut statement = transaction.prepare(
        "SELECT command_id, device_id, queue_position, command_json \
         FROM pending_commands ORDER BY command_id",
    )?;
    let rows = statement
        .query_map([], |row| {
            Ok((
                row.get::<_, String>(0)?,
                (
                    row.get::<_, String>(1)?,
                    row.get::<_, i64>(2)?,
                    row.get::<_, String>(3)?,
                ),
            ))
        })?
        .collect::<rusqlite::Result<Vec<_>>>()?;
    Ok(rows.into_iter().collect())
}

fn apply_row_changes(
    transaction: &Transaction<'_>,
    current: &RelationalState,
    candidate: &RelationalState,
) -> Result<SnapshotRowChanges, SnapshotCompareAndSwapError> {
    let mut changes = SnapshotRowChanges::default();

    for (command_id, value) in &current.pending_commands {
        if candidate.pending_commands.get(command_id) != Some(value) {
            transaction.execute(
                "DELETE FROM pending_commands WHERE command_id = ?1",
                params![command_id],
            )?;
            changes.pending_commands_deleted += 1;
        }
    }
    for (scope_key, value) in &current.idempotency_claims {
        if candidate.idempotency_claims.get(scope_key) != Some(value) {
            transaction.execute(
                "DELETE FROM idempotency_claims WHERE scope_key = ?1",
                params![scope_key],
            )?;
            changes.idempotency_claims_deleted += 1;
        }
    }
    for (scope_key, value) in &current.command_results {
        if candidate.command_results.get(scope_key) != Some(value) {
            transaction.execute(
                "DELETE FROM command_results WHERE scope_key = ?1",
                params![scope_key],
            )?;
            changes.command_results_deleted += 1;
        }
    }
    for node_id in current.devices.keys() {
        if !candidate.devices.contains_key(node_id) {
            transaction.execute("DELETE FROM devices WHERE node_id = ?1", params![node_id])?;
            changes.devices_deleted += 1;
        }
    }

    for (node_id, record_json) in &candidate.devices {
        if current.devices.get(node_id) != Some(record_json) {
            transaction.execute(
                "INSERT INTO devices (node_id, record_json) VALUES (?1, ?2) \
                 ON CONFLICT(node_id) DO UPDATE SET record_json = excluded.record_json",
                params![node_id, record_json],
            )?;
            changes.devices_upserted += 1;
        }
    }
    for (scope_key, (command_id, result_json)) in &candidate.command_results {
        if current.command_results.get(scope_key) != Some(&(command_id.clone(), result_json.clone())) {
            transaction.execute(
                "INSERT INTO command_results (scope_key, command_id, result_json) \
                 VALUES (?1, ?2, ?3)",
                params![scope_key, command_id, result_json],
            )?;
            changes.command_results_inserted += 1;
        }
    }
    for (scope_key, (command_id, request_fingerprint)) in &candidate.idempotency_claims {
        if current.idempotency_claims.get(scope_key)
            != Some(&(command_id.clone(), request_fingerprint.clone()))
        {
            transaction.execute(
                "INSERT INTO idempotency_claims \
                 (scope_key, command_id, request_fingerprint) VALUES (?1, ?2, ?3)",
                params![scope_key, command_id, request_fingerprint],
            )?;
            changes.idempotency_claims_inserted += 1;
        }
    }
    for (command_id, (device_id, queue_position, command_json)) in &candidate.pending_commands {
        if current.pending_commands.get(command_id)
            != Some(&(device_id.clone(), *queue_position, command_json.clone()))
        {
            transaction.execute(
                "INSERT INTO pending_commands \
                 (command_id, device_id, queue_position, command_json) \
                 VALUES (?1, ?2, ?3, ?4)",
                params![command_id, device_id, queue_position, command_json],
            )?;
            changes.pending_commands_inserted += 1;
        }
    }

    Ok(changes)
}

fn encode_json<T: Serialize>(
    relation: &'static str,
    value: &T,
) -> Result<String, SnapshotCompareAndSwapError> {
    serde_json::to_string(value).map_err(|source| {
        SnapshotCompareAndSwapError::Store(SnapshotStoreError::Json { relation, source })
    })
}

#[cfg(test)]
#[path = "snapshot_compare_and_swap_tests.rs"]
mod tests;
