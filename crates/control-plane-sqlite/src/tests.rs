use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicU64, Ordering};

use rusqlite::Connection;

use super::{BUSY_TIMEOUT, InventoryCounts, SCHEMA_VERSION, SqliteStore, StoreError};

static NEXT_DATABASE_ID: AtomicU64 = AtomicU64::new(1);

struct TempDatabase {
    path: PathBuf,
}

impl TempDatabase {
    fn new(label: &str) -> Self {
        let id = NEXT_DATABASE_ID.fetch_add(1, Ordering::Relaxed);
        Self {
            path: std::env::temp_dir().join(format!(
                "mobile-proxy-{label}-{}-{id}.sqlite3",
                std::process::id()
            )),
        }
    }
}

impl Drop for TempDatabase {
    fn drop(&mut self) {
        let _ = std::fs::remove_file(&self.path);
        let _ = std::fs::remove_file(sidecar_path(&self.path, "-wal"));
        let _ = std::fs::remove_file(sidecar_path(&self.path, "-shm"));
    }
}

fn sidecar_path(path: &Path, suffix: &str) -> PathBuf {
    let mut value = path.as_os_str().to_os_string();
    value.push(suffix);
    PathBuf::from(value)
}

#[test]
fn file_store_applies_required_pragmas_and_v1_schema() {
    let database = TempDatabase::new("sqlite-schema");
    let store = SqliteStore::open(&database.path).unwrap();

    assert_eq!(store.schema_version().unwrap(), SCHEMA_VERSION);
    assert_eq!(store.journal_mode().unwrap().to_ascii_lowercase(), "wal");
    assert!(store.foreign_keys_enabled().unwrap());
    assert_eq!(
        store.busy_timeout_millis().unwrap(),
        BUSY_TIMEOUT.as_millis() as i64
    );
    assert_eq!(
        store.inventory_counts().unwrap(),
        InventoryCounts {
            devices: 0,
            pending_commands: 0,
            command_results: 0,
            idempotency_claims: 0,
        }
    );
}

#[test]
fn migration_is_idempotent_across_reopen() {
    let database = TempDatabase::new("sqlite-reopen");
    let first = SqliteStore::open(&database.path).unwrap();
    assert_eq!(first.schema_version().unwrap(), SCHEMA_VERSION);
    drop(first);

    let second = SqliteStore::open(&database.path).unwrap();
    assert_eq!(second.schema_version().unwrap(), SCHEMA_VERSION);
}

#[test]
fn future_schema_version_fails_closed() {
    let database = TempDatabase::new("sqlite-future-schema");
    let connection = Connection::open(&database.path).unwrap();
    connection
        .pragma_update(None, "user_version", SCHEMA_VERSION + 1)
        .unwrap();
    drop(connection);

    let error = match SqliteStore::open(&database.path) {
        Ok(_) => panic!("future schema unexpectedly opened"),
        Err(error) => error,
    };
    assert!(matches!(
        error,
        StoreError::UnsupportedSchemaVersion {
            found,
            supported
        } if found == SCHEMA_VERSION + 1 && supported == SCHEMA_VERSION
    ));
}

#[test]
fn complete_candidate_commits_atomically_and_survives_reopen() {
    let database = TempDatabase::new("sqlite-commit");
    let mut store = SqliteStore::open(&database.path).unwrap();
    store
        .write(|transaction| {
            transaction.replace_device("device-1", r#"{"node_id":"device-1"}"#)?;
            transaction.insert_command_result(
                "scope-1",
                "command-1",
                r#"{"command_id":"command-1"}"#,
            )?;
            transaction.insert_idempotency_claim(
                "scope-1",
                "command-1",
                "b3:request-fingerprint",
            )?;
            transaction.insert_pending_command(
                "command-1",
                "device-1",
                0,
                r#"{"command_id":"command-1"}"#,
            )?;
            Ok(())
        })
        .unwrap();

    assert_eq!(
        store.inventory_counts().unwrap(),
        InventoryCounts {
            devices: 1,
            pending_commands: 1,
            command_results: 1,
            idempotency_claims: 1,
        }
    );
    drop(store);

    let reopened = SqliteStore::open(&database.path).unwrap();
    assert_eq!(
        reopened.inventory_counts().unwrap(),
        InventoryCounts {
            devices: 1,
            pending_commands: 1,
            command_results: 1,
            idempotency_claims: 1,
        }
    );
}

#[test]
fn failed_candidate_rolls_back_every_prior_write() {
    let mut store = SqliteStore::open_in_memory().unwrap();
    let result = store.write(|transaction| {
        transaction.replace_device("device-1", r#"{"node_id":"device-1"}"#)?;
        transaction.insert_idempotency_claim(
            "missing-scope",
            "missing-command",
            "b3:request-fingerprint",
        )
    });

    assert!(matches!(result, Err(StoreError::Database(_))));
    assert_eq!(
        store.inventory_counts().unwrap(),
        InventoryCounts {
            devices: 0,
            pending_commands: 0,
            command_results: 0,
            idempotency_claims: 0,
        }
    );
}

#[test]
fn conflicting_replay_evidence_fails_closed_without_replacement() {
    let mut store = SqliteStore::open_in_memory().unwrap();
    store
        .write(|transaction| {
            transaction.insert_command_result(
                "scope-1",
                "command-1",
                r#"{"command_id":"command-1"}"#,
            )?;
            transaction.insert_idempotency_claim("scope-1", "command-1", "b3:first-request")
        })
        .unwrap();

    let conflict = store.write(|transaction| {
        transaction.insert_command_result("scope-1", "command-2", r#"{"command_id":"command-2"}"#)
    });
    assert!(matches!(conflict, Err(StoreError::Database(_))));
    assert_eq!(
        store.inventory_counts().unwrap(),
        InventoryCounts {
            devices: 0,
            pending_commands: 0,
            command_results: 1,
            idempotency_claims: 1,
        }
    );
}

#[test]
fn pending_command_deletion_is_part_of_the_same_write_boundary() {
    let mut store = SqliteStore::open_in_memory().unwrap();
    store
        .write(|transaction| {
            transaction.insert_command_result(
                "scope-1",
                "command-1",
                r#"{"command_id":"command-1"}"#,
            )?;
            transaction.insert_pending_command(
                "command-1",
                "device-1",
                0,
                r#"{"command_id":"command-1"}"#,
            )?;
            assert!(transaction.delete_pending_command("command-1")?);
            Ok(())
        })
        .unwrap();

    assert_eq!(store.inventory_counts().unwrap().pending_commands, 0);
    assert_eq!(store.inventory_counts().unwrap().command_results, 1);
}
