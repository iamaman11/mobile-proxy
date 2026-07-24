use std::fs::{self, File, OpenOptions};
use std::io;
use std::path::{Path, PathBuf};

use anyhow::{Context, Result, bail};
use clap::{Parser, Subcommand};
use mobile_proxy_control_plane_sqlite::{SCHEMA_VERSION, SqliteStore};
use rusqlite::{Connection, OpenFlags, params};
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
    ensure_distinct(sqlite, backup)?;
    ensure_new_target(backup, "backup")?;
    let source = validate(sqlite, "backup source")?;
    prepare_parent(backup)?;
    let temporary = temporary_path(backup);

    let connection = Connection::open_with_flags(
        sqlite,
        OpenFlags::SQLITE_OPEN_READ_WRITE | OpenFlags::SQLITE_OPEN_NO_MUTEX,
    )
    .with_context(|| format!("failed to open SQLite backup source {}", sqlite.display()))?;
    connection
        .busy_timeout(mobile_proxy_control_plane_sqlite::BUSY_TIMEOUT)
        .context("failed to configure SQLite backup timeout")?;
    if let Err(error) = connection.execute(
        "VACUUM main INTO ?1",
        params![temporary.to_string_lossy().as_ref()],
    ) {
        cleanup(&temporary);
        return Err(error).with_context(|| {
            format!("failed to create SQLite backup {}", backup.display())
        });
    }
    drop(connection);

    let candidate = validate(&temporary, "backup candidate")?;
    ensure_parity(&source, &candidate, "backup")?;
    let bytes = fs::metadata(&temporary)?.len();
    publish(&temporary, backup)?;
    print_report("backup", &source, "backup_bytes", bytes);
    Ok(())
}

fn restore_state(backup: &Path, sqlite: &Path) -> Result<()> {
    ensure_distinct(backup, sqlite)?;
    ensure_new_target(sqlite, "restore target")?;
    let source = validate(backup, "restore source")?;
    prepare_parent(sqlite)?;
    let temporary = temporary_path(sqlite);
    if let Err(error) = copy_synced(backup, &temporary) {
        cleanup(&temporary);
        return Err(error);
    }

    let candidate = validate(&temporary, "restore candidate")?;
    ensure_parity(&source, &candidate, "restore")?;
    let bytes = fs::metadata(&temporary)?.len();
    publish(&temporary, sqlite)?;
    print_report("restore", &source, "restored_bytes", bytes);
    Ok(())
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
    let state = ValidatedState {
        devices: snapshot.devices().len(),
        pending_commands: snapshot
            .queues()
            .values()
            .map(std::collections::VecDeque::len)
            .sum(),
        replay_records: snapshot.replay_records().len(),
        canonical: snapshot.to_canonical_json()?,
    };
    Ok(state)
}

fn ensure_parity(left: &ValidatedState, right: &ValidatedState, operation: &str) -> Result<()> {
    if left.canonical != right.canonical {
        bail!("SQLite {operation} candidate does not match canonical source state");
    }
    Ok(())
}

fn print_report(operation: &str, state: &ValidatedState, bytes_key: &str, bytes: u64) {
    println!(
        "{}",
        json!({
            "operation": operation,
            "schema_version": SCHEMA_VERSION,
            "devices": state.devices,
            "pending_commands": state.pending_commands,
            "replay_records": state.replay_records,
            bytes_key: bytes
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
        bail!("SQLite {purpose} already exists");
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

fn copy_synced(source: &Path, target: &Path) -> Result<()> {
    let mut input = File::open(source)
        .with_context(|| format!("failed to open SQLite backup {}", source.display()))?;
    let mut output = OpenOptions::new()
        .create_new(true)
        .write(true)
        .open(target)
        .with_context(|| format!("failed to create restore candidate {}", target.display()))?;
    io::copy(&mut input, &mut output)?;
    output.sync_all()?;
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
