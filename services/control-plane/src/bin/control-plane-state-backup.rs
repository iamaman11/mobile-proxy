use std::fs::{self, File};
use std::path::{Path, PathBuf};

use anyhow::{Context, Result, bail};
use clap::{Parser, Subcommand};
use mobile_proxy_control_plane_sqlite::{SCHEMA_VERSION, SqliteStore};
use serde_json::json;

#[derive(Debug, Parser)]
#[command(name = "control-plane-state-backup")]
#[command(about = "Create, verify and restore canonical control-plane SQLite backups")]
struct Cli {
    #[command(subcommand)]
    command: Command,
}

#[derive(Debug, Subcommand)]
enum Command {
    Backup {
        #[arg(long)]
        sqlite: PathBuf,
        #[arg(long)]
        backup: PathBuf,
    },
    Restore {
        #[arg(long)]
        backup: PathBuf,
        #[arg(long)]
        sqlite: PathBuf,
    },
    Verify {
        #[arg(long)]
        sqlite: PathBuf,
    },
}

struct ValidatedState {
    canonical: Vec<u8>,
    devices: usize,
    pending_commands: usize,
    replay_records: usize,
}

fn main() -> Result<()> {
    match Cli::parse().command {
        Command::Backup { sqlite, backup } => backup_state(&sqlite, &backup),
        Command::Restore { backup, sqlite } => restore_state(&backup, &sqlite),
        Command::Verify { sqlite } => verify_state(&sqlite),
    }
}

fn backup_state(sqlite: &Path, backup: &Path) -> Result<()> {
    materialize_validated(
        sqlite,
        backup,
        "backup",
        "backup source",
        "backup candidate",
    )
}

fn restore_state(backup: &Path, sqlite: &Path) -> Result<()> {
    materialize_validated(
        backup,
        sqlite,
        "restore",
        "restore source",
        "restore candidate",
    )
}

fn materialize_validated(
    source_path: &Path,
    target_path: &Path,
    operation: &str,
    source_purpose: &str,
    candidate_purpose: &str,
) -> Result<()> {
    ensure_distinct(source_path, target_path)?;
    ensure_new_target(target_path, operation)?;
    let source = validate(source_path, source_purpose)?;
    prepare_parent(target_path)?;
    let temporary = temporary_path(target_path);

    if let Err(error) = materialize(source_path, &temporary, operation) {
        cleanup(&temporary);
        return Err(error);
    }
    let candidate = match validate(&temporary, candidate_purpose) {
        Ok(candidate) => candidate,
        Err(error) => {
            cleanup(&temporary);
            return Err(error);
        }
    };
    if let Err(error) = ensure_parity(&source, &candidate, operation) {
        cleanup(&temporary);
        return Err(error);
    }

    let bytes = fs::metadata(&temporary)?.len();
    publish(&temporary, target_path)?;
    print_report(operation, &source, bytes);
    Ok(())
}

fn materialize(source: &Path, target: &Path, operation: &str) -> Result<()> {
    let store = SqliteStore::open_existing(source).with_context(|| {
        format!(
            "failed to open SQLite {operation} source {}",
            source.display()
        )
    })?;
    store
        .vacuum_into(target)
        .with_context(|| format!("failed to materialize SQLite {operation} artifact"))
}

fn verify_state(sqlite: &Path) -> Result<()> {
    let state = validate(sqlite, "verification source")?;
    println!(
        "{}",
        json!({
            "operation": "verify",
            "schema_version": SCHEMA_VERSION,
            "devices": state.devices,
            "pending_commands": state.pending_commands,
            "replay_records": state.replay_records,
            "healthy": true
        })
    );
    Ok(())
}

fn validate(path: &Path, purpose: &str) -> Result<ValidatedState> {
    if !path.is_file() {
        bail!("SQLite {purpose} does not exist or is not a regular file");
    }
    let mut store = SqliteStore::open_existing(path)
        .with_context(|| format!("failed to open SQLite {purpose} {}", path.display()))?;
    if store.schema_version()? != SCHEMA_VERSION {
        bail!("SQLite {purpose} schema version changed during validation");
    }
    let snapshot = store
        .load_snapshot()
        .with_context(|| format!("failed to rehydrate SQLite {purpose}"))?;
    Ok(ValidatedState {
        devices: snapshot.devices().len(),
        pending_commands: snapshot
            .queues()
            .values()
            .map(std::collections::VecDeque::len)
            .sum(),
        replay_records: snapshot.replay_records().len(),
        canonical: snapshot.to_canonical_json()?,
    })
}

fn ensure_parity(left: &ValidatedState, right: &ValidatedState, operation: &str) -> Result<()> {
    if left.canonical != right.canonical {
        bail!("SQLite {operation} candidate does not match canonical source state");
    }
    Ok(())
}

fn print_report(operation: &str, state: &ValidatedState, bytes: u64) {
    println!(
        "{}",
        json!({
            "operation": operation,
            "schema_version": SCHEMA_VERSION,
            "devices": state.devices,
            "pending_commands": state.pending_commands,
            "replay_records": state.replay_records,
            "artifact_bytes": bytes
        })
    );
}

fn ensure_distinct(left: &Path, right: &Path) -> Result<()> {
    if std::path::absolute(left)? == std::path::absolute(right)? {
        bail!("SQLite source and target paths must be distinct");
    }
    Ok(())
}

fn ensure_new_target(path: &Path, purpose: &str) -> Result<()> {
    let temporary = temporary_path(path);
    if path.exists() {
        bail!("SQLite {purpose} target already exists");
    }
    if temporary.exists() || wal_path(&temporary).exists() || shm_path(&temporary).exists() {
        bail!("SQLite {purpose} temporary artifact already exists");
    }
    Ok(())
}

fn prepare_parent(path: &Path) -> Result<()> {
    if let Some(parent) = path.parent()
        && !parent.as_os_str().is_empty()
    {
        fs::create_dir_all(parent)
            .with_context(|| format!("failed to create SQLite directory {}", parent.display()))?;
    }
    Ok(())
}

fn publish(temporary: &Path, target: &Path) -> Result<()> {
    remove_sidecars(temporary);
    fs::rename(temporary, target).with_context(|| {
        format!(
            "failed to publish SQLite artifact {} from {}",
            target.display(),
            temporary.display()
        )
    })?;
    sync_parent(target)
}

fn temporary_path(path: &Path) -> PathBuf {
    let mut value = path.as_os_str().to_os_string();
    value.push(".tmp");
    PathBuf::from(value)
}

fn wal_path(path: &Path) -> PathBuf {
    let mut value = path.as_os_str().to_os_string();
    value.push("-wal");
    PathBuf::from(value)
}

fn shm_path(path: &Path) -> PathBuf {
    let mut value = path.as_os_str().to_os_string();
    value.push("-shm");
    PathBuf::from(value)
}

fn cleanup(path: &Path) {
    let _ = fs::remove_file(path);
    remove_sidecars(path);
}

fn remove_sidecars(path: &Path) {
    let _ = fs::remove_file(wal_path(path));
    let _ = fs::remove_file(shm_path(path));
}

#[cfg(unix)]
fn sync_parent(path: &Path) -> Result<()> {
    if let Some(parent) = path.parent()
        && !parent.as_os_str().is_empty()
    {
        File::open(parent)?.sync_all()?;
    }
    Ok(())
}

#[cfg(not(unix))]
fn sync_parent(_path: &Path) -> Result<()> {
    Ok(())
}
