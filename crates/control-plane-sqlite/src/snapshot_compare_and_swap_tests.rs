use std::collections::{BTreeMap, VecDeque};
use std::str::FromStr;

use mobile_proxy_foundation::{CommandId, DeadlineWindow, IdempotencyKey};
use proxy_core::{DesiredState, DeviceCommand, DeviceRecord, RecoveryIntent};
use serde_json::json;

use crate::{ControlPlaneSnapshot, ReplayRecord, SnapshotStoreError, SqliteStore, StoreError};

use super::{SnapshotCompareAndSwapError, SnapshotRowChanges};

fn command(index: u128, device_id: &str, key: &str) -> DeviceCommand {
    DeviceCommand {
        command_id: CommandId::from_str(&format!("{index:032x}")).unwrap(),
        device_id: device_id.to_owned(),
        desired_state: DesiredState::HealthyServing,
        recovery_intent: RecoveryIntent::None,
        deadline_secs: DeadlineWindow::new(30).unwrap(),
        idempotency_key: IdempotencyKey::parse(key).unwrap(),
        issued_at: index.to_string(),
    }
}

fn device(node_id: &str, proxy_status: &str) -> DeviceRecord {
    serde_json::from_value(json!({
        "node_id": node_id,
        "node_name": format!("node-{node_id}"),
        "readiness_state": "healthy",
        "serving": true,
        "proxy_status": proxy_status,
        "publicly_serving": true,
        "availability": "available"
    }))
    .unwrap()
}

fn snapshot(
    proxy_status: &str,
    pending: Vec<DeviceCommand>,
    replay: Vec<DeviceCommand>,
) -> ControlPlaneSnapshot {
    let queues = if pending.is_empty() {
        BTreeMap::new()
    } else {
        BTreeMap::from([("device-1".to_owned(), VecDeque::from(pending))])
    };
    ControlPlaneSnapshot::from_parts(
        BTreeMap::from([("device-1".to_owned(), device("device-1", proxy_status))]),
        queues,
        replay.into_iter().map(ReplayRecord::from_command).collect(),
    )
    .unwrap()
}

fn canonical(snapshot: &ControlPlaneSnapshot) -> Vec<u8> {
    snapshot.to_canonical_json().unwrap()
}

#[test]
fn issue_like_candidate_updates_only_changed_relations() {
    let first = command(1, "device-1", "first");
    let second = command(2, "device-1", "second");
    let expected = snapshot("starting", vec![first.clone()], vec![first.clone()]);
    let candidate = snapshot(
        "running",
        vec![first.clone(), second.clone()],
        vec![first, second],
    );
    let mut store = SqliteStore::open_in_memory().unwrap();
    store.replace_snapshot(&expected).unwrap();

    let changes = store
        .compare_and_swap_snapshot(&expected, &candidate)
        .unwrap();

    assert_eq!(
        changes,
        SnapshotRowChanges {
            devices_upserted: 1,
            command_results_inserted: 1,
            idempotency_claims_inserted: 1,
            pending_commands_inserted: 1,
            ..SnapshotRowChanges::default()
        }
    );
    assert_eq!(
        canonical(&store.load_snapshot().unwrap()),
        canonical(&candidate)
    );
}

#[test]
fn ack_like_candidate_deletes_pending_row_but_preserves_replay() {
    let value = command(1, "device-1", "ack");
    let expected = snapshot("running", vec![value.clone()], vec![value.clone()]);
    let candidate = snapshot("running", Vec::new(), vec![value]);
    let mut store = SqliteStore::open_in_memory().unwrap();
    store.replace_snapshot(&expected).unwrap();

    let changes = store
        .compare_and_swap_snapshot(&expected, &candidate)
        .unwrap();

    assert_eq!(
        changes,
        SnapshotRowChanges {
            pending_commands_deleted: 1,
            ..SnapshotRowChanges::default()
        }
    );
    assert_eq!(store.inventory_counts().unwrap().pending_commands, 0);
    assert_eq!(store.inventory_counts().unwrap().command_results, 1);
}

#[test]
fn replay_eviction_deletes_claim_and_result_without_touching_device() {
    let value = command(1, "device-1", "evict");
    let expected = snapshot("running", Vec::new(), vec![value]);
    let candidate = snapshot("running", Vec::new(), Vec::new());
    let mut store = SqliteStore::open_in_memory().unwrap();
    store.replace_snapshot(&expected).unwrap();

    let changes = store
        .compare_and_swap_snapshot(&expected, &candidate)
        .unwrap();

    assert_eq!(
        changes,
        SnapshotRowChanges {
            command_results_deleted: 1,
            idempotency_claims_deleted: 1,
            ..SnapshotRowChanges::default()
        }
    );
    assert_eq!(
        canonical(&store.load_snapshot().unwrap()),
        canonical(&candidate)
    );
}

#[test]
fn queue_reorder_rewrites_pending_rows_without_rewriting_replay() {
    let first = command(1, "device-1", "first");
    let second = command(2, "device-1", "second");
    let replay = vec![first.clone(), second.clone()];
    let expected = snapshot(
        "running",
        vec![first.clone(), second.clone()],
        replay.clone(),
    );
    let candidate = snapshot("running", vec![second, first], replay);
    let mut store = SqliteStore::open_in_memory().unwrap();
    store.replace_snapshot(&expected).unwrap();

    let changes = store
        .compare_and_swap_snapshot(&expected, &candidate)
        .unwrap();

    assert_eq!(
        changes,
        SnapshotRowChanges {
            pending_commands_inserted: 2,
            pending_commands_deleted: 2,
            ..SnapshotRowChanges::default()
        }
    );
    assert_eq!(
        canonical(&store.load_snapshot().unwrap()),
        canonical(&candidate)
    );
}

#[test]
fn complete_candidate_deletion_respects_foreign_key_order() {
    let value = command(1, "device-1", "delete");
    let expected = snapshot("running", vec![value.clone()], vec![value]);
    let candidate = ControlPlaneSnapshot::empty();
    let mut store = SqliteStore::open_in_memory().unwrap();
    store.replace_snapshot(&expected).unwrap();

    let changes = store
        .compare_and_swap_snapshot(&expected, &candidate)
        .unwrap();

    assert_eq!(
        changes,
        SnapshotRowChanges {
            devices_deleted: 1,
            command_results_deleted: 1,
            idempotency_claims_deleted: 1,
            pending_commands_deleted: 1,
            ..SnapshotRowChanges::default()
        }
    );
    assert_eq!(
        canonical(&store.load_snapshot().unwrap()),
        canonical(&candidate)
    );
}

#[test]
fn stale_expected_state_fails_without_mutation() {
    let value = command(1, "device-1", "stale");
    let current = snapshot("running", vec![value.clone()], vec![value]);
    let expected = ControlPlaneSnapshot::empty();
    let candidate = snapshot("changed", Vec::new(), Vec::new());
    let mut store = SqliteStore::open_in_memory().unwrap();
    store.replace_snapshot(&current).unwrap();

    assert!(matches!(
        store.compare_and_swap_snapshot(&expected, &candidate),
        Err(SnapshotCompareAndSwapError::StaleExpectedState)
    ));
    assert_eq!(
        canonical(&store.load_snapshot().unwrap()),
        canonical(&current)
    );
}

#[test]
fn exact_noop_candidate_checks_expected_state_without_writes() {
    let value = command(1, "device-1", "noop");
    let snapshot = snapshot("running", vec![value.clone()], vec![value]);
    let mut store = SqliteStore::open_in_memory().unwrap();
    store.replace_snapshot(&snapshot).unwrap();

    assert_eq!(
        store
            .compare_and_swap_snapshot(&snapshot, &snapshot)
            .unwrap(),
        SnapshotRowChanges::default()
    );
    assert_eq!(
        canonical(&store.load_snapshot().unwrap()),
        canonical(&snapshot)
    );
}

#[test]
fn late_sql_failure_rolls_back_every_earlier_row_change() {
    let value = command(1, "device-1", "late-failure");
    let expected = snapshot("starting", Vec::new(), Vec::new());
    let candidate = snapshot("running", vec![value.clone()], vec![value]);
    let mut store = SqliteStore::open_in_memory().unwrap();
    store.replace_snapshot(&expected).unwrap();
    store
        .connection
        .execute_batch(
            "CREATE TRIGGER reject_runtime_pending \
             BEFORE INSERT ON pending_commands \
             BEGIN SELECT RAISE(ABORT, 'blocked'); END;",
        )
        .unwrap();

    assert!(matches!(
        store.compare_and_swap_snapshot(&expected, &candidate),
        Err(SnapshotCompareAndSwapError::Store(
            SnapshotStoreError::Store(StoreError::Database(_))
        ))
    ));
    assert_eq!(
        canonical(&store.load_snapshot().unwrap()),
        canonical(&expected)
    );
}

#[test]
fn post_write_trigger_drift_fails_parity_and_rolls_back() {
    let expected = snapshot("starting", Vec::new(), Vec::new());
    let candidate = snapshot("running", Vec::new(), Vec::new());
    let mut store = SqliteStore::open_in_memory().unwrap();
    store.replace_snapshot(&expected).unwrap();
    store
        .connection
        .execute_batch(
            "CREATE TRIGGER revert_runtime_device \
             AFTER UPDATE OF record_json ON devices \
             BEGIN \
                 UPDATE devices SET record_json = OLD.record_json \
                 WHERE node_id = NEW.node_id; \
             END;",
        )
        .unwrap();

    assert!(matches!(
        store.compare_and_swap_snapshot(&expected, &candidate),
        Err(SnapshotCompareAndSwapError::PostWriteParityMismatch)
    ));
    assert_eq!(
        canonical(&store.load_snapshot().unwrap()),
        canonical(&expected)
    );
}
