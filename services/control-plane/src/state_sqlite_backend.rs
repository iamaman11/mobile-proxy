use std::collections::{BTreeMap, BTreeSet, HashMap, VecDeque};
use std::path::Path;

use anyhow::{Context, Result, anyhow, bail};
use mobile_proxy_application::idempotency_scope_key;
use mobile_proxy_control_plane_sqlite::{
    ControlPlaneSnapshot, ReplayRecord, SnapshotRowChanges, SqliteStore,
};
use mobile_proxy_foundation::CommandId;
use proxy_core::DeviceCommand;

use crate::state::{CommandState, StoredState};

pub(crate) fn load_existing(path: &Path) -> Result<StoredState> {
    if !path.is_file() {
        bail!(
            "SQLite state path {} does not exist or is not a regular file; run the migration utility before selecting the SQLite backend",
            path.display()
        );
    }
    let mut store = SqliteStore::open(path)
        .with_context(|| format!("failed to open SQLite state {}", path.display()))?;
    let snapshot = store
        .load_snapshot()
        .with_context(|| format!("failed to load SQLite state {}", path.display()))?;
    stored_from_snapshot(snapshot)
}

pub(crate) fn compare_and_swap(
    path: &Path,
    expected: &StoredState,
    candidate: &StoredState,
) -> Result<SnapshotRowChanges> {
    let expected = snapshot_from_stored(expected)?;
    let candidate = snapshot_from_stored(candidate)?;
    let mut store = SqliteStore::open(path)
        .with_context(|| format!("failed to open SQLite state {}", path.display()))?;
    store
        .compare_and_swap_snapshot(&expected, &candidate)
        .with_context(|| format!("failed to commit SQLite state {}", path.display()))
}

#[cfg(test)]
pub(crate) fn replace_for_test(path: &Path, state: &StoredState) -> Result<()> {
    let snapshot = snapshot_from_stored(state)?;
    let mut store = SqliteStore::open(path)
        .with_context(|| format!("failed to open SQLite test state {}", path.display()))?;
    store.replace_snapshot(&snapshot)?;
    Ok(())
}

pub(crate) fn snapshot_from_stored(state: &StoredState) -> Result<ControlPlaneSnapshot> {
    validate_legacy_claims(&state.commands)?;

    let mut seen_scopes = BTreeSet::new();
    let mut replay_records = Vec::with_capacity(state.commands.idempotency_results.len());
    for scope in &state.commands.idempotency_order {
        if !seen_scopes.insert(scope.clone()) {
            bail!("control-plane replay order contains a duplicate scope");
        }
        let command = state
            .commands
            .idempotency_results
            .get(scope)
            .ok_or_else(|| anyhow!("control-plane replay order references a missing result"))?;
        let canonical = idempotency_scope_key(&command.device_id, &command.idempotency_key);
        if canonical.to_string() != *scope {
            bail!("control-plane replay result is stored under a non-canonical scope");
        }
        replay_records.push(ReplayRecord::from_command(command.clone()));
    }
    if seen_scopes.len() != state.commands.idempotency_results.len() {
        bail!("control-plane replay result is missing from retention order");
    }

    let devices = state
        .devices
        .iter()
        .map(|(node_id, record)| (node_id.clone(), record.clone()))
        .collect::<BTreeMap<_, _>>();
    let queues = state
        .commands
        .queues
        .iter()
        .map(|(device_id, queue)| (device_id.clone(), queue.clone()))
        .collect::<BTreeMap<_, _>>();

    ControlPlaneSnapshot::from_parts(devices, queues, replay_records)
        .map_err(|error| anyhow!("control-plane state cannot be represented in SQLite: {error}"))
}

pub(crate) fn stored_from_snapshot(snapshot: ControlPlaneSnapshot) -> Result<StoredState> {
    let (devices, queues, replay_records) = snapshot.into_parts();
    let mut commands = CommandState {
        queues: queues.into_iter().collect::<HashMap<_, VecDeque<_>>>(),
        ..CommandState::default()
    };
    for replay in replay_records {
        let scope = replay.scope_key().to_string();
        let command = replay.into_command();
        let legacy = legacy_scope(&command);
        if commands
            .idempotency_results
            .insert(scope.clone(), command.clone())
            .is_some()
            || commands
                .idempotency
                .insert(legacy, command.command_id)
                .is_some()
        {
            bail!("SQLite replay state contains a duplicate command relation");
        }
        commands.idempotency_order.push_back(scope);
    }
    validate_legacy_claims(&commands)?;
    Ok(StoredState {
        devices: devices.into_iter().collect(),
        commands,
    })
}

fn validate_legacy_claims(commands: &CommandState) -> Result<()> {
    let mut expected = HashMap::<String, CommandId>::with_capacity(commands.idempotency_results.len());
    for (scope, command) in &commands.idempotency_results {
        let canonical = idempotency_scope_key(&command.device_id, &command.idempotency_key);
        if canonical.to_string() != *scope {
            bail!("control-plane command result uses a non-canonical scope");
        }
        let legacy = legacy_scope(command);
        if let Some(existing) = expected.insert(legacy, command.command_id)
            && existing != command.command_id
        {
            bail!("control-plane legacy claim scope is ambiguous");
        }
    }
    if commands.idempotency != expected {
        bail!("control-plane legacy claim map differs from durable replay results");
    }
    Ok(())
}

fn legacy_scope(command: &DeviceCommand) -> String {
    format!("{}:{}", command.device_id, command.idempotency_key)
}
