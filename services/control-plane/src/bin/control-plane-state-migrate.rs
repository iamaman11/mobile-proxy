use std::fs::{self, File, OpenOptions};
use std::io::Write;
use std::path::{Path, PathBuf};

use anyhow::{Context, Result, bail};
use clap::{Parser, Subcommand};
use mobile_proxy_control_plane_sqlite::{
    LegacyJsonImportOutcome, LegacyJsonImportReport, SqliteStore, parse_legacy_json,
};
use serde_json::json;

#[derive(Debug, Parser)]
#[command(name = "control-plane-state-migrate")]
#[command(about = "Import legacy control-plane JSON into SQLite and export canonical diagnostics")]
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
    let mut store = SqliteStore::open(sqlite)
        .with_context(|| format!("failed to open SQLite source {}", sqlite.display()))?;
    let snapshot = store
        .load_snapshot()
        .context("failed to rehydrate SQLite state for diagnostic export")?;
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
            bail!("migration input, SQLite state and diagnostic output paths must be distinct");
        }
    }
    Ok(())
}

fn write_atomic(path: &Path, body: &[u8]) -> Result<()> {
    if let Some(parent) = path.parent()
        && !parent.as_os_str().is_empty()
    {
        fs::create_dir_all(parent).with_context(|| {
            format!("failed to create diagnostic directory {}", parent.display())
        })?;
    }
    let temporary = temporary_path(path);
    let mut file = OpenOptions::new()
        .create(true)
        .truncate(true)
        .write(true)
        .open(&temporary)
        .with_context(|| {
            format!(
                "failed to create temporary diagnostic {}",
                temporary.display()
            )
        })?;
    file.write_all(body).with_context(|| {
        format!(
            "failed to write temporary diagnostic {}",
            temporary.display()
        )
    })?;
    file.sync_all().with_context(|| {
        format!(
            "failed to sync temporary diagnostic {}",
            temporary.display()
        )
    })?;
    drop(file);
    fs::rename(&temporary, path).with_context(|| {
        format!(
            "failed to publish diagnostic {} from {}",
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
            .with_context(|| format!("failed to open diagnostic directory {}", parent.display()))?
            .sync_all()
            .with_context(|| format!("failed to sync diagnostic directory {}", parent.display()))?;
    }
    Ok(())
}

#[cfg(not(unix))]
fn sync_parent(_path: &Path) -> Result<()> {
    Ok(())
}
