use std::path::{Path, PathBuf};
use std::str::FromStr;
use std::sync::atomic::{AtomicU64, Ordering};

use mobile_proxy_foundation::{CommandId, DeadlineWindow, IdempotencyKey};
use proxy_core::{DesiredState, DeviceCommand, DeviceRecord, RecoveryIntent};

use super::{
    CommandQueues, ControlPlaneSnapshot, DeviceMap, InventoryCounts, ReplayRecord,
    SnapshotStoreError, SqliteStore,
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
                "mobile-proxy-snapshot-{label}-{}-{id}.sqlite3",
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

fn command(index: u128, device_id: &str, key: &str) -> DeviceCommand {
    DeviceCommand {
        command_id: CommandId::from_str(&format!("{index:032x}"))
            .unwrap_or_else(|_| panic!("test command id {index} must be valid")),
        device_id: device_id.to_owned(),
        desired_state: DesiredState::HealthyServing,
        recovery_intent: RecoveryIntent::None,
        deadline_secs: DeadlineWindow::new(30).unwrap(),
        idempotency_key: IdempotencyKey::parse(key).unwrap(),
        issued_at: format!("{index}"),
    }
}

fn device(node_id: &str) -> DeviceRecord {
    serde_json::from_value(serde_json::json!({
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

fn snapshot(device_id: &str, commands: &[DeviceCommand], pending: usize) -> ControlPlaneSnapshot {
    let mut devices = DeviceMap::new();
    devices.insert(device_id.to_owned(), device(device_id));

    let mut queues = CommandQueues::new();
    queues.insert(
        device_id.to_owned(),
        commands.iter().take(pending).cloned().collect(),
    );

    ControlPlaneSnapshot::from_parts(
        devices,
        queues,
        commands
            .iter()
            .cloned()
            .map(ReplayRecord::from_command)
            .collect(),
    )
    .unwrap()
}

#[test]
fn empty_store_loads_one_valid_empty_snapshot() {
    let mut store = SqliteStore::open_in_memory().unwrap();
    let loaded = store.load_snapshot().unwrap();

    assert!(loaded.devices().is_empty());
    assert!(loaded.queues().is_empty());
    assert!(loaded.replay_records().is_empty());
}

#[test]
fn atomic_snapshot_round_trip_survives_reopen_byte_exactly() {
    let database = TempDatabase::new("round-trip");
    let first = command(1, "device-1", "first");
    let second = command(2, "device-1", "second");
    let expected = snapshot("device-1", &[first, second], 2);
    let expected_json = expected.to_canonical_json().unwrap();

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

    let mut reopened = SqliteStore::open(&database.path).unwrap();
    let loaded = reopened.load_snapshot().unwrap();
    assert_eq!(loaded.to_canonical_json().unwrap(), expected_json);
}

#[test]
fn replacement_removes_every_stale_relation() {
    let first = command(1, "device-1", "first");
    let second = command(2, "device-1", "second");
    let populated = snapshot("device-1", &[first, second], 2);
    let empty = ControlPlaneSnapshot::empty();
    let mut store = SqliteStore::open_in_memory().unwrap();

    store.replace_snapshot(&populated).unwrap();
    store.replace_snapshot(&empty).unwrap();

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
        store.load_snapshot().unwrap().to_canonical_json().unwrap(),
        empty.to_canonical_json().unwrap()
    );
}

#[test]
fn failed_replacement_rolls_back_deletes_and_prior_inserts() {
    let baseline_command = command(1, "device-1", "baseline");
    let baseline = snapshot("device-1", &[baseline_command], 1);
    let candidate_command = command(2, "device-2", "candidate");
    let candidate = snapshot("device-2", &[candidate_command], 1);
    let baseline_json = baseline.to_canonical_json().unwrap();
    let mut store = SqliteStore::open_in_memory().unwrap();
    store.replace_snapshot(&baseline).unwrap();

    store
        .connection
        .execute_batch(
            "CREATE TRIGGER fail_snapshot_replace BEFORE INSERT ON devices \
             BEGIN SELECT RAISE(ABORT, 'forced snapshot failure'); END;",
        )
        .unwrap();
    let failure = store.replace_snapshot(&candidate);
    assert!(matches!(failure, Err(SnapshotStoreError::Store(_))));
    store
        .connection
        .execute_batch("DROP TRIGGER fail_snapshot_replace;")
        .unwrap();

    assert_eq!(
        store.load_snapshot().unwrap().to_canonical_json().unwrap(),
        baseline_json
    );
}

#[test]
fn corrupt_typed_relation_fails_closed_during_load() {
    let value = command(1, "device-1", "first");
    let result_json = serde_json::to_string(&value).unwrap();
    let command_id = value.command_id.to_string();
    let mut store = SqliteStore::open_in_memory().unwrap();
    store
        .write(|transaction| {
            transaction.insert_command_result("not-a-digest", &command_id, &result_json)?;
            transaction.insert_idempotency_claim(
                "not-a-digest",
                &command_id,
                "also-not-a-digest",
            )
        })
        .unwrap();

    assert!(matches!(
        store.load_snapshot(),
        Err(SnapshotStoreError::Foundation {
            relation: "command_results",
            field: "scope_key",
            ..
        })
    ));
}
