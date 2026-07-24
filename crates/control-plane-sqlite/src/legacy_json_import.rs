use std::collections::{BTreeMap, HashMap, VecDeque};
use std::error::Error;
use std::fmt::{Display, Formatter};

use mobile_proxy_application::{MAX_IDEMPOTENCY_RESULTS, idempotency_scope_key};
use mobile_proxy_foundation::CommandId;
use proxy_core::{
    BinaryFingerprintInput, ConfigFingerprintInput, DeviceCommand, DeviceRecord,
    FingerprintInputError,
};
use serde::Deserialize;
use serde_json::Value;

use crate::{
    ControlPlaneSnapshot, ReplayRecord, SnapshotError, SnapshotStoreError, SnapshotViolation,
    SqliteStore,
};

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum LegacyJsonImportOutcome {
    Imported,
    AlreadyImported,
}

#[derive(Debug, Clone, Copy, Default, PartialEq, Eq)]
pub struct LegacyJsonMigrationStats {
    pub legacy_config_fingerprints: u64,
    pub legacy_binary_fingerprints: u64,
    pub recovered_command_results: u64,
    pub recovered_legacy_claims: u64,
    pub canonicalized_result_keys: u64,
    pub removed_canonical_claim_keys: u64,
    pub rebuilt_result_order: bool,
    pub evicted_command_results: u64,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct LegacyJsonImportReport {
    pub outcome: LegacyJsonImportOutcome,
    pub devices: usize,
    pub pending_commands: usize,
    pub replay_records: usize,
    pub migration: LegacyJsonMigrationStats,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum LegacyJsonViolation {
    FingerprintFieldShape,
    ConflictingCommandResult,
    ConflictingLegacyClaim,
    OrphanLegacyClaim,
    ReplayCapacityExceeded,
    ReplayOrderInconsistent,
}

impl Display for LegacyJsonViolation {
    fn fmt(&self, formatter: &mut Formatter<'_>) -> std::fmt::Result {
        formatter.write_str(match self {
            Self::FingerprintFieldShape => "legacy fingerprint field has an invalid JSON shape",
            Self::ConflictingCommandResult => {
                "legacy command result conflicts with canonical replay state"
            }
            Self::ConflictingLegacyClaim => "legacy idempotency claim conflicts with its command",
            Self::OrphanLegacyClaim => "legacy idempotency claim has no recoverable command result",
            Self::ReplayCapacityExceeded => "legacy replay capacity cannot be normalized safely",
            Self::ReplayOrderInconsistent => "legacy replay order is inconsistent",
        })
    }
}

impl Error for LegacyJsonViolation {}

#[derive(Debug)]
pub enum LegacyJsonImportError {
    Json(serde_json::Error),
    Fingerprint {
        field: &'static str,
        source: FingerprintInputError,
    },
    Violation(LegacyJsonViolation),
    Snapshot(SnapshotViolation),
    SnapshotJson(SnapshotError),
    Store(SnapshotStoreError),
    TargetContainsDifferentState,
    ParityMismatch,
}

impl Display for LegacyJsonImportError {
    fn fmt(&self, formatter: &mut Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Json(_) => formatter.write_str("legacy control-plane JSON is invalid"),
            Self::Fingerprint { field, .. } => {
                write!(formatter, "legacy {field} value is unsupported")
            }
            Self::Violation(error) => Display::fmt(error, formatter),
            Self::Snapshot(error) => Display::fmt(error, formatter),
            Self::SnapshotJson(_) => {
                formatter.write_str("canonical snapshot JSON could not be produced")
            }
            Self::Store(_) => formatter.write_str("SQLite legacy import operation failed"),
            Self::TargetContainsDifferentState => {
                formatter.write_str("SQLite target already contains different canonical state")
            }
            Self::ParityMismatch => formatter
                .write_str("SQLite rehydration does not match the imported canonical snapshot"),
        }
    }
}

impl Error for LegacyJsonImportError {
    fn source(&self) -> Option<&(dyn Error + 'static)> {
        match self {
            Self::Json(error) => Some(error),
            Self::Fingerprint { source, .. } => Some(source),
            Self::Violation(error) => Some(error),
            Self::Snapshot(error) => Some(error),
            Self::SnapshotJson(error) => Some(error),
            Self::Store(error) => Some(error),
            Self::TargetContainsDifferentState | Self::ParityMismatch => None,
        }
    }
}

impl From<serde_json::Error> for LegacyJsonImportError {
    fn from(error: serde_json::Error) -> Self {
        Self::Json(error)
    }
}

impl From<LegacyJsonViolation> for LegacyJsonImportError {
    fn from(error: LegacyJsonViolation) -> Self {
        Self::Violation(error)
    }
}

impl From<SnapshotViolation> for LegacyJsonImportError {
    fn from(error: SnapshotViolation) -> Self {
        Self::Snapshot(error)
    }
}

impl From<SnapshotError> for LegacyJsonImportError {
    fn from(error: SnapshotError) -> Self {
        Self::SnapshotJson(error)
    }
}

impl From<SnapshotStoreError> for LegacyJsonImportError {
    fn from(error: SnapshotStoreError) -> Self {
        Self::Store(error)
    }
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct LegacyStoredState {
    devices: HashMap<String, DeviceRecord>,
    commands: LegacyCommandState,
}

#[derive(Debug, Default, Deserialize)]
#[serde(deny_unknown_fields)]
struct LegacyCommandState {
    queues: HashMap<String, VecDeque<DeviceCommand>>,
    idempotency: HashMap<String, CommandId>,
    #[serde(default)]
    idempotency_results: HashMap<String, DeviceCommand>,
    #[serde(default)]
    idempotency_order: VecDeque<String>,
}

impl SqliteStore {
    pub fn import_legacy_json(
        &mut self,
        body: &str,
    ) -> Result<LegacyJsonImportReport, LegacyJsonImportError> {
        let (snapshot, migration) = parse_legacy_json(body)?;
        let expected = snapshot.to_canonical_json()?;
        let existing = self.load_snapshot()?;
        let existing_canonical = existing.to_canonical_json()?;

        let outcome = if existing_canonical == expected {
            LegacyJsonImportOutcome::AlreadyImported
        } else {
            if !snapshot_is_empty(&existing) {
                return Err(LegacyJsonImportError::TargetContainsDifferentState);
            }
            self.replace_snapshot(&snapshot)?;
            let rehydrated = self.load_snapshot()?;
            if rehydrated.to_canonical_json()? != expected {
                return Err(LegacyJsonImportError::ParityMismatch);
            }
            LegacyJsonImportOutcome::Imported
        };

        Ok(LegacyJsonImportReport {
            outcome,
            devices: snapshot.devices().len(),
            pending_commands: snapshot.queues().values().map(VecDeque::len).sum(),
            replay_records: snapshot.replay_records().len(),
            migration,
        })
    }
}

pub fn parse_legacy_json(
    body: &str,
) -> Result<(ControlPlaneSnapshot, LegacyJsonMigrationStats), LegacyJsonImportError> {
    let raw: Value = serde_json::from_str(body)?;
    let mut stats = fingerprint_stats(&raw)?;
    let mut stored: LegacyStoredState = serde_json::from_value(raw)?;
    normalize_commands(&mut stored.commands, &mut stats)?;

    let devices = stored.devices.into_iter().collect::<BTreeMap<_, _>>();
    let queues = stored
        .commands
        .queues
        .into_iter()
        .collect::<BTreeMap<_, _>>();
    let mut replay_records = Vec::with_capacity(stored.commands.idempotency_results.len());
    for scope in stored.commands.idempotency_order {
        let command = stored
            .commands
            .idempotency_results
            .remove(&scope)
            .ok_or(LegacyJsonViolation::ReplayOrderInconsistent)?;
        replay_records.push(ReplayRecord::from_command(command));
    }
    if !stored.commands.idempotency_results.is_empty() {
        return Err(LegacyJsonViolation::ReplayOrderInconsistent.into());
    }

    Ok((
        ControlPlaneSnapshot::from_parts(devices, queues, replay_records)?,
        stats,
    ))
}

fn fingerprint_stats(raw: &Value) -> Result<LegacyJsonMigrationStats, LegacyJsonImportError> {
    let mut stats = LegacyJsonMigrationStats::default();
    let Some(devices) = raw.get("devices").and_then(Value::as_object) else {
        return Ok(stats);
    };
    for device in devices.values() {
        let Some(object) = device.as_object() else {
            continue;
        };
        classify_fingerprint(
            object.get("config_fingerprint"),
            "config_fingerprint",
            |raw| ConfigFingerprintInput::parse(raw).map(|value| value.is_legacy()),
            &mut stats.legacy_config_fingerprints,
        )?;
        classify_fingerprint(
            object.get("binary_fingerprint"),
            "binary_fingerprint",
            |raw| BinaryFingerprintInput::parse(raw).map(|value| value.is_legacy()),
            &mut stats.legacy_binary_fingerprints,
        )?;
    }
    Ok(stats)
}

fn classify_fingerprint(
    value: Option<&Value>,
    field: &'static str,
    classify: impl FnOnce(&str) -> Result<bool, FingerprintInputError>,
    counter: &mut u64,
) -> Result<(), LegacyJsonImportError> {
    let Some(value) = value else {
        return Ok(());
    };
    if value.is_null() {
        return Ok(());
    }
    let raw = value
        .as_str()
        .ok_or(LegacyJsonViolation::FingerprintFieldShape)?;
    if classify(raw).map_err(|source| LegacyJsonImportError::Fingerprint { field, source })? {
        *counter += 1;
    }
    Ok(())
}

fn normalize_commands(
    commands: &mut LegacyCommandState,
    stats: &mut LegacyJsonMigrationStats,
) -> Result<(), LegacyJsonImportError> {
    let result_entries = commands
        .idempotency_results
        .iter()
        .map(|(key, command)| (key.clone(), command.clone()))
        .collect::<Vec<_>>();
    for (stored_key, command) in result_entries {
        let canonical = canonical_scope(&command);
        if stored_key != canonical {
            commands.idempotency_results.remove(&stored_key);
            if let Some(existing) = commands.idempotency_results.get(&canonical)
                && existing != &command
            {
                return Err(LegacyJsonViolation::ConflictingCommandResult.into());
            }
            commands.idempotency_results.insert(canonical, command);
            stats.canonicalized_result_keys += 1;
        }
    }

    let queued_commands = commands
        .queues
        .iter()
        .flat_map(|(device_id, queue)| {
            queue
                .iter()
                .cloned()
                .map(move |command| (device_id.clone(), command))
        })
        .collect::<Vec<_>>();
    for (device_id, command) in queued_commands {
        if command.device_id != device_id {
            return Err(SnapshotViolation::PendingDeviceMismatch.into());
        }
        let canonical = canonical_scope(&command);
        match commands.idempotency_results.get(&canonical) {
            Some(existing) if existing != &command => {
                return Err(LegacyJsonViolation::ConflictingCommandResult.into());
            }
            Some(_) => {}
            None => {
                commands
                    .idempotency_results
                    .insert(canonical, command.clone());
                stats.recovered_command_results += 1;
            }
        }
        ensure_legacy_claim(commands, &command, stats)?;
    }

    let canonical_results = commands
        .idempotency_results
        .iter()
        .map(|(scope, command)| (scope.clone(), command.clone()))
        .collect::<Vec<_>>();
    for (canonical, command) in canonical_results {
        ensure_legacy_claim(commands, &command, stats)?;
        let legacy = legacy_scope(&command);
        if canonical != legacy
            && let Some(existing) = commands.idempotency.get(&canonical).copied()
        {
            if existing != command.command_id {
                return Err(LegacyJsonViolation::ConflictingLegacyClaim.into());
            }
            commands.idempotency.remove(&canonical);
            stats.removed_canonical_claim_keys += 1;
        }
    }

    rebuild_order(commands, stats);
    trim_results(commands, stats)?;
    validate_legacy_claims(commands)?;
    Ok(())
}

fn ensure_legacy_claim(
    commands: &mut LegacyCommandState,
    command: &DeviceCommand,
    stats: &mut LegacyJsonMigrationStats,
) -> Result<(), LegacyJsonImportError> {
    let legacy = legacy_scope(command);
    match commands.idempotency.get(&legacy) {
        Some(existing) if *existing != command.command_id => {
            Err(LegacyJsonViolation::ConflictingLegacyClaim.into())
        }
        Some(_) => Ok(()),
        None => {
            commands.idempotency.insert(legacy, command.command_id);
            stats.recovered_legacy_claims += 1;
            Ok(())
        }
    }
}

fn rebuild_order(commands: &mut LegacyCommandState, stats: &mut LegacyJsonMigrationStats) {
    let original = std::mem::take(&mut commands.idempotency_order);
    let mut normalized = VecDeque::new();
    for key in &original {
        if commands.idempotency_results.contains_key(key) && !normalized.contains(key) {
            normalized.push_back(key.clone());
        }
    }
    let mut missing = commands
        .idempotency_results
        .keys()
        .filter(|key| !normalized.contains(key))
        .cloned()
        .collect::<Vec<_>>();
    missing.sort();
    normalized.extend(missing);
    stats.rebuilt_result_order = normalized != original;
    commands.idempotency_order = normalized;
}

fn trim_results(
    commands: &mut LegacyCommandState,
    stats: &mut LegacyJsonMigrationStats,
) -> Result<(), LegacyJsonImportError> {
    while commands.idempotency_order.len() > MAX_IDEMPOTENCY_RESULTS {
        let position = commands
            .idempotency_order
            .iter()
            .position(|key| {
                commands
                    .idempotency_results
                    .get(key)
                    .is_some_and(|command| !command_is_pending(commands, command.command_id))
            })
            .ok_or(LegacyJsonViolation::ReplayCapacityExceeded)?;
        let key = commands
            .idempotency_order
            .remove(position)
            .ok_or(LegacyJsonViolation::ReplayOrderInconsistent)?;
        let command = commands
            .idempotency_results
            .remove(&key)
            .ok_or(LegacyJsonViolation::ReplayOrderInconsistent)?;
        let legacy = legacy_scope(&command);
        if commands.idempotency.get(&legacy) == Some(&command.command_id) {
            commands.idempotency.remove(&legacy);
        }
        if commands.idempotency.get(&key) == Some(&command.command_id) {
            commands.idempotency.remove(&key);
        }
        stats.evicted_command_results += 1;
    }
    Ok(())
}

fn validate_legacy_claims(commands: &LegacyCommandState) -> Result<(), LegacyJsonImportError> {
    let mut expected = HashMap::with_capacity(commands.idempotency_results.len());
    for command in commands.idempotency_results.values() {
        let key = legacy_scope(command);
        if let Some(existing) = expected.insert(key, command.command_id)
            && existing != command.command_id
        {
            return Err(LegacyJsonViolation::ConflictingLegacyClaim.into());
        }
    }
    if commands.idempotency.len() != expected.len() {
        return Err(LegacyJsonViolation::OrphanLegacyClaim.into());
    }
    for (key, command_id) in &commands.idempotency {
        if expected.get(key) != Some(command_id) {
            return Err(LegacyJsonViolation::OrphanLegacyClaim.into());
        }
    }
    Ok(())
}

fn command_is_pending(commands: &LegacyCommandState, command_id: CommandId) -> bool {
    commands
        .queues
        .values()
        .any(|queue| queue.iter().any(|command| command.command_id == command_id))
}

fn canonical_scope(command: &DeviceCommand) -> String {
    idempotency_scope_key(&command.device_id, &command.idempotency_key).to_string()
}

fn legacy_scope(command: &DeviceCommand) -> String {
    format!("{}:{}", command.device_id, command.idempotency_key)
}

fn snapshot_is_empty(snapshot: &ControlPlaneSnapshot) -> bool {
    snapshot.devices().is_empty()
        && snapshot.queues().is_empty()
        && snapshot.replay_records().is_empty()
}
