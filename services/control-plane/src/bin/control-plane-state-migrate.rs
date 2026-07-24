use std::collections::{BTreeMap, VecDeque};
use std::fs::{self, File, OpenOptions};
use std::io::Write;
use std::path::{Path, PathBuf};

use anyhow::{Context, Result, bail};
use clap::{Parser, Subcommand};
use mobile_proxy_control_plane_sqlite::{
    ControlPlaneSnapshot, LegacyJsonImportOutcome, LegacyJsonImportReport, SqliteStore,
    parse_legacy_json,
};
use mobile_proxy_foundation::CommandId;
use proxy_core::{DeviceCommand, DeviceRecord};
use serde::Serialize;
use serde_json::json;

#[derive(Debug, Parser)]
#[command(name = "control-plane-state-migrate")]
#[command(about = "Import legacy control-plane JSON and export SQLite state")]
struct Cli {
    #[command(subcommand)]
    command: Command,
}

#[derive(Debug, Subcommand)]
enum Command {
    Import {
        #[arg(long)]
        legacy_json: PathBuf,
        #[arg(long)]
        sqlite: PathBuf,
        #[arg(long)]
        diagnostic_json: PathBuf,
    },
    Export {
        #[arg(long)]
        sqlite: PathBuf,
        #[arg(long)]
        diagnostic_json: PathBuf,
    },
    RollbackExport {
        #[arg(long)]
        sqlite: PathBuf,
        #[arg(long)]
        rollback_json: PathBuf,
    },
}

#[derive(Serialize)]
struct JsonBackendState {
    devices: BTreeMap<String, DeviceRecord>,
    commands: JsonBackendCommands,
}

#[derive(Serialize)]
struct JsonBackendCommands {
    queues: BTreeMap<String, VecDeque<DeviceCommand>>,
    idempotency: BTreeMap<String, CommandId>,
    idempotency_results: BTreeMap<String, DeviceCommand>,
    idempotency_order: VecDeque<String>,
}

fn main() -> Result<()> {
    match Cli::parse().command {
        Command::Import {
            legacy_json,
            sqlite,
            diagnostic_json,
        } => import(&legacy_json, &sqlite, &diagnostic_json),
        Command::Export {
            sqlite,
            diagnostic_json,
        } => export(&sqlite, &diagnostic_json),
        Command::RollbackExport {
            sqlite,
            rollback_json,
        } => rollback_export(&sqlite, &rollback_json),
    }
}

fn import(legacy_json: &Path, sqlite: &Path, diagnostic_json: &Path) -> Result<()> {
    ensure_distinct(&[legacy_json, sqlite, diagnostic_json])?;
    let body = fs::read_to_string(legacy_json)
        .with_context(|| format!("failed to read legacy state from {}", legacy_json.display()))?;

    parse_legacy_json(&body).context("legacy state failed pre-write validation")?;

    let mut store = SqliteStore::open(sqlite)
        .with_context(|| format!("failed to open SQLite target {}", sqlite.display()))?;
    let report = store
        .import_legacy_json(&body)
        .context("legacy state import failed")?;
    let snapshot = store
        .load_snapshot()
        .context("failed to rehydrate imported SQLite state")?;
    let diagnostic = snapshot
        .to_canonical_json()
        .context("failed to serialize canonical diagnostic state")?;
    write_atomic(diagnostic_json, &diagnostic)?;
    print_import_report(report, &diagnostic);
    Ok(())
}

fn export(sqlite: &Path, diagnostic_json: &Path) -> Result<()> {
    ensure_distinct(&[sqlite, diagnostic_json])?;
    let snapshot = load_export_snapshot(sqlite, "diagnostic")?;
    let diagnostic = snapshot
        .to_canonical_json()
        .context("failed to serialize canonical diagnostic state")?;
    write_atomic(diagnostic_json, &diagnostic)?;
    println!(
        "{}",
        json!({
            "operation": "export",
            "devices": snapshot.devices().len(),
            "pending_commands": snapshot.queues().values().map(std::collections::VecDeque::len).sum::<usize>(),
            "replay_records": snapshot.replay_records().len(),
            "diagnostic_bytes": diagnostic.len(),
        })
    );
    Ok(())
}

fn rollback_export(sqlite: &Path, rollback_json: &Path) -> Result<()> {
    ensure_distinct(&[sqlite, rollback_json])?;
    let snapshot = load_export_snapshot(sqlite, "rollback")?;
    let devices = snapshot.devices().len();
    let pending_commands = snapshot
        .queues()
        .values()
        .map(std::collections::VecDeque::len)
        .sum::<usize>();
    let replay_records = snapshot.replay_records().len();
    let body = serialize_json_backend(snapshot)?;
    write_atomic(rollback_json, &body)?;
    println!(
        "{}",
        json!({
            "operation": "rollback_export",
            "devices": devices,
            "pending_commands": pending_commands,
            "replay_records": replay_records,
            "rollback_bytes": body.len(),
        })
    );
    Ok(())
}

fn load_export_snapshot(sqlite: &Path, purpose: &str) -> Result<ControlPlaneSnapshot> {
    if !sqlite.is_file() {
        bail!("SQLite {purpose} export source does not exist or is not a regular file");
    }
    let mut store = SqliteStore::open(sqlite)
        .with_context(|| format!("failed to open SQLite source {}", sqlite.display()))?;
    store
        .load_snapshot()
        .with_context(|| format!("failed to rehydrate SQLite state for {purpose} export"))
}

fn serialize_json_backend(snapshot: ControlPlaneSnapshot) -> Result<Vec<u8>> {
    let (devices, queues, replay_records) = snapshot.into_parts();
    let mut idempotency = BTreeMap::new();
    let mut idempotency_results = BTreeMap::new();
    let mut idempotency_order = VecDeque::new();

    for replay in replay_records {
        let scope = replay.scope_key().to_string();
        let command = replay.into_command();
        let legacy_scope = format!("{}:{}", command.device_id, command.idempotency_key);
        if idempotency
            .insert(legacy_scope, command.command_id)
            .is_some()
            || idempotency_results.insert(scope.clone(), command).is_some()
        {
            bail!("SQLite replay state cannot be represented by the JSON rollback backend");
        }
        idempotency_order.push_back(scope);
    }

    serde_json::to_vec_pretty(&JsonBackendState {
        devices,
        commands: JsonBackendCommands {
            queues,
            idempotency,
            idempotency_results,
            idempotency_order,
        },
    })
    .context("failed to serialize JSON rollback backend state")
}

fn print_import_report(report: LegacyJsonImportReport, diagnostic: &[u8]) {
    let outcome = match report.outcome {
        LegacyJsonImportOutcome::Imported => "imported",
        LegacyJsonImportOutcome::AlreadyImported => "already_imported",
    };
    println!(
        "{}",
        json!({
            "operation": "import",
            "outcome": outcome,
            "devices": report.devices,
            "pending_commands": report.pending_commands,
            "replay_records": report.replay_records,
            "diagnostic_bytes": diagnostic.len(),
            "migration": {
                "legacy_config_fingerprints": report.migration.legacy_config_fingerprints,
                "legacy_binary_fingerprints": report.migration.legacy_binary_fingerprints,
                "recovered_command_results": report.migration.recovered_command_results,
                "recovered_legacy_claims": report.migration.recovered_legacy_claims,
                "canonicalized_result_keys": report.migration.canonicalized_result_keys,
                "removed_canonical_claim_keys": report.migration.removed_canonical_claim_keys,
                "rebuilt_result_order": report.migration.rebuilt_result_order,
                "evicted_command_results": report.migration.evicted_command_results,
            }
        })
    );
}

fn ensure_distinct(paths: &[&Path]) -> Result<()> {
    let absolute = paths
        .iter()
        .map(std::path::absolute)
        .collect::<std::io::Result<Vec<_>>>()?;
    for (index, left) in absolute.iter().enumerate() {
        if absolute.iter().skip(index + 1).any(|right| right == left) {
            bail!("migration input, SQLite state and export output paths must be distinct");
        }
    }
    Ok(())
}

fn write_atomic(path: &Path, body: &[u8]) -> Result<()> {
    if let Some(parent) = path.parent()
        && !parent.as_os_str().is_empty()
    {
        fs::create_dir_all(parent)
            .with_context(|| format!("failed to create export directory {}", parent.display()))?;
    }
    let temporary = temporary_path(path);
    let mut file = OpenOptions::new()
        .create(true)
        .truncate(true)
        .write(true)
        .open(&temporary)
        .with_context(|| format!("failed to create temporary export {}", temporary.display()))?;
    file.write_all(body)
        .with_context(|| format!("failed to write temporary export {}", temporary.display()))?;
    file.sync_all()
        .with_context(|| format!("failed to sync temporary export {}", temporary.display()))?;
    drop(file);
    fs::rename(&temporary, path).with_context(|| {
        format!(
            "failed to publish export {} from {}",
            path.display(),
            temporary.display()
        )
    })?;
    sync_parent(path)?;
    Ok(())
}

fn temporary_path(path: &Path) -> PathBuf {
    let mut value = path.as_os_str().to_os_string();
    value.push(".tmp");
    PathBuf::from(value)
}

#[cfg(unix)]
fn sync_parent(path: &Path) -> Result<()> {
    if let Some(parent) = path.parent()
        && !parent.as_os_str().is_empty()
    {
        File::open(parent)
            .with_context(|| format!("failed to open export directory {}", parent.display()))?
            .sync_all()
            .with_context(|| format!("failed to sync export directory {}", parent.display()))?;
    }
    Ok(())
}

#[cfg(not(unix))]
fn sync_parent(_path: &Path) -> Result<()> {
    Ok(())
}
