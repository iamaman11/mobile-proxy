use std::collections::{BTreeMap, VecDeque};
use std::path::{Path, PathBuf};
use std::str::FromStr;
use std::sync::atomic::{AtomicU64, Ordering};

use mobile_proxy_foundation::{CommandId, DeadlineWindow, IdempotencyKey};
use proxy_core::{DesiredState, DeviceCommand, DeviceRecord, RecoveryIntent};
use rusqlite::params;
use serde_json::json;

use crate::{InventoryCounts, SqliteStore, StoreError};

use super::{
    ControlPlaneSnapshot, IdempotencyClaimRow, ReplayRecord, SnapshotStoreError, SnapshotViolation,
};

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

fn command(index: u64, device_id: &str, key: &str) -> DeviceCommand {
    DeviceCommand {
        command_id: CommandId::from_str(&format!("00000000-0000-0000-0000-{index:012x}")).unwrap(),
        device_id: device_id.to_owned(),
        desired_state: DesiredState::HealthyServing,
        recovery_intent: RecoveryIntent::None,
        deadline_secs: DeadlineWindow::new(30).unwrap(),
        idempotency_key: IdempotencyKey::parse(key).unwrap(),
        issued_at: index.to_string(),
    }
}

fn device(node_id: &str) -> DeviceRecord {
    serde_json::from_value(json!({
        "node_id": node_id,
        "node_name": format!("node-{node_id}"),
        "readiness_state": "healthy",
        "serving": true,
        "proxy_status": "running",
        "publicly_serving": true,
        "availability": "available"
    }))
    .unwrap()
}

fn snapshot(label: &str, device_id: &str) -> ControlPlaneSnapshot {
    let first = command(1, device_id, &format!("{label}-first"));
    let second = command(2, device_id, &format!("{label}-second"));
    let devices = BTreeMap::from([(device_id.to_owned(), device(device_id))]);
    let queues = BTreeMap::from([(
        device_id.to_owned(),
        VecDeque::from([first.clone(), second.clone()]),
    )]);
    ControlPlaneSnapshot::from_parts(
        devices,
        queues,
        vec![
            ReplayRecord::from_command(first),
            ReplayRecord::from_command(second),
        ],
    )
    .unwrap()
}

fn canonical(snapshot: &ControlPlaneSnapshot) -> Vec<u8> {
    snapshot.to_canonical_json().unwrap()
}

#[test]
fn snapshot_commit_reopen_and_load_preserve_exact_canonical_state() {
    let database = TempDatabase::new("snapshot-reopen");
    let expected = snapshot("reopen", "device-1");
    let mut store = SqliteStore::open(&database.path).unwrap();

    store.replace_snapshot(&expected).unwrap();
    assert_eq!(
        store.inventory_counts().unwrap(),
        InventoryCounts {
            devices: 1,
            pending_commands: 2,
            command_results: 2,
            idempotency_claims: 2,
        }
    );
    drop(store);

    let reopened = SqliteStore::open(&database.path).unwrap();
    let actual = reopened.load_snapshot().unwrap();
    assert_eq!(canonical(&actual), canonical(&expected));
    let queue = actual.queues().get("device-1").unwrap();
    assert_eq!(queue[0].idempotency_key.as_str(), "reopen-first");
    assert_eq!(queue[1].idempotency_key.as_str(), "reopen-second");
}

#[test]
fn replacing_snapshot_removes_every_omitted_relation_atomically() {
    let mut store = SqliteStore::open_in_memory().unwrap();
    store
        .replace_snapshot(&snapshot("before-clear", "device-1"))
        .unwrap();

    store
        .replace_snapshot(&ControlPlaneSnapshot::empty())
        .unwrap();

    assert_eq!(
        store.inventory_counts().unwrap(),
        InventoryCounts {
            devices: 0,
            pending_commands: 0,
            command_results: 0,
            idempotency_claims: 0,
        }
    );
    assert_eq!(
        canonical(&store.load_snapshot().unwrap()),
        canonical(&ControlPlaneSnapshot::empty())
    );
}

#[test]
fn failed_candidate_rolls_back_deletes_and_partial_inserts() {
    let mut store = SqliteStore::open_in_memory().unwrap();
    let original = snapshot("original", "device-1");
    let replacement = snapshot("replacement", "device-2");
    store.replace_snapshot(&original).unwrap();
    store
        .connection
        .execute_batch(
            "CREATE TRIGGER reject_pending_snapshot \
             BEFORE INSERT ON pending_commands \
             BEGIN SELECT RAISE(ABORT, 'blocked'); END;",
        )
        .unwrap();

    let error = store.replace_snapshot(&replacement).unwrap_err();
    assert!(matches!(
        error,
        SnapshotStoreError::Store(StoreError::Database(_))
    ));
    assert_eq!(
        canonical(&store.load_snapshot().unwrap()),
        canonical(&original)
    );
}

#[test]
fn invalid_typed_json_fails_closed_during_rehydration() {
    let store = SqliteStore::open_in_memory().unwrap();
    store
        .connection
        .execute(
            "INSERT INTO devices (node_id, record_json) VALUES (?1, ?2)",
            params!["device-1", r#"{"node_id":"device-1"}"#],
        )
        .unwrap();

    let error = store.load_snapshot().unwrap_err();
    assert!(matches!(
        error,
        SnapshotStoreError::Json {
            field: "devices.record_json",
            ..
        }
    ));
}

#[test]
fn invalid_digest_text_fails_closed_before_relation_validation() {
    let store = SqliteStore::open_in_memory().unwrap();
    let value = command(1, "device-1", "invalid-digest");
    store
        .connection
        .execute(
            "INSERT INTO command_results (scope_key, command_id, result_json) \
             VALUES (?1, ?2, ?3)",
            params![
                "not-a-supported-digest",
                value.command_id.to_string(),
                serde_json::to_string(&value).unwrap()
            ],
        )
        .unwrap();

    let error = store.load_snapshot().unwrap_err();
    assert!(matches!(
        error,
        SnapshotStoreError::InvalidField {
            field: "command_results.scope_key"
        }
    ));
}

#[test]
fn cross_table_corruption_fails_closed_even_if_foreign_keys_were_bypassed() {
    let store = SqliteStore::open_in_memory().unwrap();
    let value = command(1, "device-1", "missing-result");
    let claim = IdempotencyClaimRow::from_command(&value);
    store
        .connection
        .pragma_update(None, "foreign_keys", false)
        .unwrap();
    store
        .connection
        .execute(
            "INSERT INTO idempotency_claims \
             (scope_key, command_id, request_fingerprint) VALUES (?1, ?2, ?3)",
            params![
                claim.scope_key().to_string(),
                claim.command_id().to_string(),
                claim.request_fingerprint().to_string()
            ],
        )
        .unwrap();
    store
        .connection
        .pragma_update(None, "foreign_keys", true)
        .unwrap();

    let error = store.load_snapshot().unwrap_err();
    assert!(matches!(
        error,
        SnapshotStoreError::InvalidSnapshot(SnapshotViolation::ClaimResultMissing)
    ));
}
