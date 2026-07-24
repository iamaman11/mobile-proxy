use std::collections::{BTreeMap, VecDeque};
use std::path::{Path, PathBuf};
use std::str::FromStr;
use std::sync::atomic::{AtomicU64, Ordering};

use mobile_proxy_application::idempotency_scope_key;
use mobile_proxy_foundation::{CommandId, DeadlineWindow, IdempotencyKey};
use proxy_core::{DesiredState, DeviceCommand, DeviceRecord, RecoveryIntent};
use serde_json::{Value, json};

use crate::{ControlPlaneSnapshot, ReplayRecord, SqliteStore};

use super::{
    LegacyJsonImportError, LegacyJsonImportOutcome, LegacyJsonViolation, parse_legacy_json,
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
                "mobile-proxy-legacy-import-{label}-{}-{id}.sqlite3",
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
        command_id: CommandId::from_str(&format!("{index:032x}")).unwrap(),
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

fn legacy_device(node_id: &str) -> Value {
    let mut value = serde_json::to_value(device(node_id)).unwrap();
    value["config_fingerprint"] = json!("legacy-config");
    value["binary_fingerprint"] = json!("legacy-binary");
    value
}

fn legacy_body(
    device_id: &str,
    command: &DeviceCommand,
    claim_id: CommandId,
    result_key: Option<String>,
    order: Vec<String>,
) -> String {
    let mut results = serde_json::Map::new();
    if let Some(key) = result_key {
        results.insert(key, serde_json::to_value(command).unwrap());
    }
    json!({
        "devices": {
            device_id: legacy_device(device_id)
        },
        "commands": {
            "queues": {
                device_id: [command]
            },
            "idempotency": {
                format!("{device_id}:{}", command.idempotency_key): claim_id
            },
            "idempotency_results": results,
            "idempotency_order": order
        }
    })
    .to_string()
}

fn canonical(snapshot: &ControlPlaneSnapshot) -> Vec<u8> {
    snapshot.to_canonical_json().unwrap()
}

#[test]
fn representative_legacy_state_imports_and_reopens_with_exact_parity() {
    let database = TempDatabase::new("representative");
    let value = command(1, "device-1", "legacy-command");
    let body = legacy_body("device-1", &value, value.command_id, None, Vec::new());
    let (expected, expected_stats) = parse_legacy_json(&body).unwrap();
    let mut store = SqliteStore::open(&database.path).unwrap();

    let report = store.import_legacy_json(&body).unwrap();
    assert_eq!(report.outcome, LegacyJsonImportOutcome::Imported);
    assert_eq!(report.devices, 1);
    assert_eq!(report.pending_commands, 1);
    assert_eq!(report.replay_records, 1);
    assert_eq!(report.migration, expected_stats);
    assert_eq!(report.migration.legacy_config_fingerprints, 1);
    assert_eq!(report.migration.legacy_binary_fingerprints, 1);
    assert_eq!(report.migration.recovered_command_results, 1);
    assert!(report.migration.rebuilt_result_order);
    drop(store);

    let mut reopened = SqliteStore::open(&database.path).unwrap();
    assert_eq!(
        canonical(&reopened.load_snapshot().unwrap()),
        canonical(&expected)
    );
}

#[test]
fn legacy_result_keys_and_order_are_canonicalized_deterministically() {
    let first = command(1, "device-1", "first");
    let second = command(2, "device-1", "second");
    let first_scope = idempotency_scope_key(&first.device_id, &first.idempotency_key).to_string();
    let second_scope =
        idempotency_scope_key(&second.device_id, &second.idempotency_key).to_string();
    let first_result = serde_json::to_string(&first).unwrap();
    let second_result = serde_json::to_string(&second).unwrap();
    let device_json = serde_json::to_string(&legacy_device("device-1")).unwrap();
    let left = format!(
        r#"{{"devices":{{"device-1":{device_json}}},"commands":{{"queues":{{"device-1":[{first_result},{second_result}]}},"idempotency":{{"device-1:first":"{}","device-1:second":"{}"}},"idempotency_results":{{"device-1:second":{second_result},"device-1:first":{first_result}}},"idempotency_order":["device-1:second","device-1:first"]}}}}"#,
        first.command_id, second.command_id
    );
    let right = format!(
        r#"{{"commands":{{"idempotency_order":["{first_scope}","{second_scope}"],"idempotency_results":{{"{first_scope}":{first_result},"{second_scope}":{second_result}}},"idempotency":{{"device-1:second":"{}","device-1:first":"{}"}},"queues":{{"device-1":[{first_result},{second_result}]}}}},"devices":{{"device-1":{device_json}}}}}"#,
        second.command_id, first.command_id
    );

    let (left_snapshot, left_stats) = parse_legacy_json(&left).unwrap();
    let (right_snapshot, right_stats) = parse_legacy_json(&right).unwrap();
    assert_eq!(canonical(&left_snapshot), canonical(&right_snapshot));
    assert_eq!(left_stats.canonicalized_result_keys, 2);
    assert!(left_stats.rebuilt_result_order);
    assert_eq!(right_stats.canonicalized_result_keys, 0);
    assert!(!right_stats.rebuilt_result_order);
}

#[test]
fn exact_import_replay_is_idempotent() {
    let value = command(1, "device-1", "replay");
    let body = legacy_body("device-1", &value, value.command_id, None, Vec::new());
    let mut store = SqliteStore::open_in_memory().unwrap();

    assert_eq!(
        store.import_legacy_json(&body).unwrap().outcome,
        LegacyJsonImportOutcome::Imported
    );
    let before = canonical(&store.load_snapshot().unwrap());
    assert_eq!(
        store.import_legacy_json(&body).unwrap().outcome,
        LegacyJsonImportOutcome::AlreadyImported
    );
    assert_eq!(canonical(&store.load_snapshot().unwrap()), before);
}

#[test]
fn different_nonempty_target_fails_without_replacement() {
    let existing_command = command(1, "device-existing", "existing");
    let existing = ControlPlaneSnapshot::from_parts(
        BTreeMap::from([("device-existing".to_owned(), device("device-existing"))]),
        BTreeMap::from([(
            "device-existing".to_owned(),
            VecDeque::from([existing_command.clone()]),
        )]),
        vec![ReplayRecord::from_command(existing_command)],
    )
    .unwrap();
    let imported_command = command(2, "device-import", "import");
    let body = legacy_body(
        "device-import",
        &imported_command,
        imported_command.command_id,
        None,
        Vec::new(),
    );
    let mut store = SqliteStore::open_in_memory().unwrap();
    store.replace_snapshot(&existing).unwrap();
    let before = canonical(&store.load_snapshot().unwrap());

    assert!(matches!(
        store.import_legacy_json(&body),
        Err(LegacyJsonImportError::TargetContainsDifferentState)
    ));
    assert_eq!(canonical(&store.load_snapshot().unwrap()), before);
}

#[test]
fn conflicting_or_orphan_legacy_claims_fail_closed() {
    let value = command(1, "device-1", "conflict");
    let conflicting = command(2, "device-1", "other");
    let conflicting_body =
        legacy_body("device-1", &value, conflicting.command_id, None, Vec::new());
    assert!(matches!(
        parse_legacy_json(&conflicting_body),
        Err(LegacyJsonImportError::Violation(
            LegacyJsonViolation::ConflictingLegacyClaim
        ))
    ));

    let mut orphan: Value = serde_json::from_str(&legacy_body(
        "device-1",
        &value,
        value.command_id,
        None,
        Vec::new(),
    ))
    .unwrap();
    orphan["commands"]["idempotency"]["orphan:key"] = json!(conflicting.command_id);
    assert!(matches!(
        parse_legacy_json(&orphan.to_string()),
        Err(LegacyJsonImportError::Violation(
            LegacyJsonViolation::OrphanLegacyClaim
        ))
    ));
}

#[test]
fn unsupported_fingerprint_and_malformed_json_fail_before_sqlite_write() {
    let value = command(1, "device-1", "fingerprint");
    let mut unsupported: Value = serde_json::from_str(&legacy_body(
        "device-1",
        &value,
        value.command_id,
        None,
        Vec::new(),
    ))
    .unwrap();
    unsupported["devices"]["device-1"]["config_fingerprint"] = json!("unknown:abcd");
    let mut store = SqliteStore::open_in_memory().unwrap();

    assert!(matches!(
        store.import_legacy_json(&unsupported.to_string()),
        Err(LegacyJsonImportError::Fingerprint {
            field: "config_fingerprint",
            ..
        })
    ));
    assert!(matches!(
        store.import_legacy_json("{not-json"),
        Err(LegacyJsonImportError::Json(_))
    ));
    assert!(store.load_snapshot().unwrap().devices().is_empty());
}
