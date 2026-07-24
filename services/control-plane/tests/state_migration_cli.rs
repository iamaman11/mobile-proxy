use std::collections::{BTreeMap, VecDeque};
use std::fs;
use std::path::{Path, PathBuf};
use std::process::{Command, Output};
use std::str::FromStr;
use std::sync::atomic::{AtomicU64, Ordering};

use mobile_proxy_control_plane_sqlite::{ControlPlaneSnapshot, ReplayRecord, SqliteStore};
use mobile_proxy_foundation::{CommandId, DeadlineWindow, IdempotencyKey};
use proxy_core::{DesiredState, DeviceCommand, DeviceRecord, RecoveryIntent};
use serde_json::{Value, json};

static NEXT_DIRECTORY_ID: AtomicU64 = AtomicU64::new(1);

struct TempDirectory {
    path: PathBuf,
}

impl TempDirectory {
    fn new(label: &str) -> Self {
        let id = NEXT_DIRECTORY_ID.fetch_add(1, Ordering::Relaxed);
        let path = std::env::temp_dir().join(format!(
            "mobile-proxy-state-migration-{label}-{}-{id}",
            std::process::id()
        ));
        fs::create_dir_all(&path).unwrap();
        Self { path }
    }

    fn join(&self, name: &str) -> PathBuf {
        self.path.join(name)
    }
}

impl Drop for TempDirectory {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.path);
    }
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

fn legacy_body(device_id: &str, value: &DeviceCommand) -> Vec<u8> {
    let mut device_value = serde_json::to_value(device(device_id)).unwrap();
    device_value["config_fingerprint"] = json!("legacy-config");
    device_value["binary_fingerprint"] = json!("legacy-binary");
    serde_json::to_vec_pretty(&json!({
        "devices": {
            device_id: device_value
        },
        "commands": {
            "queues": {
                device_id: [value]
            },
            "idempotency": {
                format!("{device_id}:{}", value.idempotency_key): value.command_id
            }
        }
    }))
    .unwrap()
}

fn canonical_snapshot(device_id: &str, value: DeviceCommand) -> ControlPlaneSnapshot {
    ControlPlaneSnapshot::from_parts(
        BTreeMap::from([(device_id.to_owned(), device(device_id))]),
        BTreeMap::from([(
            device_id.to_owned(),
            VecDeque::from([value.clone()]),
        )]),
        vec![ReplayRecord::from_command(value)],
    )
    .unwrap()
}

fn migration_binary() -> &'static str {
    env!("CARGO_BIN_EXE_control-plane-state-migrate")
}

fn run_import(source: &Path, sqlite: &Path, diagnostic: &Path) -> Output {
    Command::new(migration_binary())
        .args([
            "import",
            "--legacy-json",
            source.to_str().unwrap(),
            "--sqlite",
            sqlite.to_str().unwrap(),
            "--diagnostic-json",
            diagnostic.to_str().unwrap(),
        ])
        .output()
        .unwrap()
}

fn run_export(sqlite: &Path, diagnostic: &Path) -> Output {
    Command::new(migration_binary())
        .args([
            "export",
            "--sqlite",
            sqlite.to_str().unwrap(),
            "--diagnostic-json",
            diagnostic.to_str().unwrap(),
        ])
        .output()
        .unwrap()
}

fn stdout_json(output: &Output) -> Value {
    serde_json::from_slice(&output.stdout).unwrap_or_else(|error| {
        panic!(
            "stdout must be one JSON document: {error}; stdout={:?}; stderr={:?}",
            String::from_utf8_lossy(&output.stdout),
            String::from_utf8_lossy(&output.stderr)
        )
    })
}

#[test]
fn import_reopen_and_export_preserve_source_and_canonical_parity() {
    let directory = TempDirectory::new("parity");
    let source = directory.join("legacy.json");
    let sqlite = directory.join("state.sqlite3");
    let imported_diagnostic = directory.join("imported.json");
    let exported_diagnostic = directory.join("exported.json");
    let value = command(1, "device-1", "process-parity");
    let source_bytes = legacy_body("device-1", &value);
    fs::write(&source, &source_bytes).unwrap();

    let first = run_import(&source, &sqlite, &imported_diagnostic);
    assert!(
        first.status.success(),
        "import failed: {}",
        String::from_utf8_lossy(&first.stderr)
    );
    assert_eq!(stdout_json(&first)["outcome"], "imported");
    assert_eq!(fs::read(&source).unwrap(), source_bytes);

    let mut store = SqliteStore::open(&sqlite).unwrap();
    let canonical = store.load_snapshot().unwrap().to_canonical_json().unwrap();
    assert_eq!(fs::read(&imported_diagnostic).unwrap(), canonical);
    drop(store);

    let replay = run_import(&source, &sqlite, &imported_diagnostic);
    assert!(
        replay.status.success(),
        "replay failed: {}",
        String::from_utf8_lossy(&replay.stderr)
    );
    assert_eq!(stdout_json(&replay)["outcome"], "already_imported");
    assert_eq!(fs::read(&source).unwrap(), source_bytes);

    let export = run_export(&sqlite, &exported_diagnostic);
    assert!(
        export.status.success(),
        "export failed: {}",
        String::from_utf8_lossy(&export.stderr)
    );
    assert_eq!(stdout_json(&export)["operation"], "export");
    assert_eq!(fs::read(&exported_diagnostic).unwrap(), canonical);
}

#[test]
fn different_nonempty_target_fails_without_changing_sqlite_or_export() {
    let directory = TempDirectory::new("conflict");
    let first_source = directory.join("first.json");
    let second_source = directory.join("second.json");
    let sqlite = directory.join("state.sqlite3");
    let first_diagnostic = directory.join("first-diagnostic.json");
    let second_diagnostic = directory.join("second-diagnostic.json");
    let first_command = command(1, "device-1", "first");
    let second_command = command(2, "device-2", "second");
    fs::write(&first_source, legacy_body("device-1", &first_command)).unwrap();
    fs::write(&second_source, legacy_body("device-2", &second_command)).unwrap();

    assert!(run_import(&first_source, &sqlite, &first_diagnostic).status.success());
    let before = {
        let mut store = SqliteStore::open(&sqlite).unwrap();
        store.load_snapshot().unwrap().to_canonical_json().unwrap()
    };
    let diagnostic_before = fs::read(&first_diagnostic).unwrap();

    let conflict = run_import(&second_source, &sqlite, &second_diagnostic);
    assert!(!conflict.status.success());
    assert!(!second_diagnostic.exists());
    let after = {
        let mut store = SqliteStore::open(&sqlite).unwrap();
        store.load_snapshot().unwrap().to_canonical_json().unwrap()
    };
    assert_eq!(after, before);
    assert_eq!(fs::read(&first_diagnostic).unwrap(), diagnostic_before);
}

#[test]
fn malformed_or_unsupported_source_fails_before_sqlite_creation() {
    let directory = TempDirectory::new("prevalidation");
    let malformed = directory.join("malformed.json");
    let unsupported = directory.join("unsupported.json");
    let malformed_sqlite = directory.join("malformed.sqlite3");
    let unsupported_sqlite = directory.join("unsupported.sqlite3");
    let malformed_diagnostic = directory.join("malformed-diagnostic.json");
    let unsupported_diagnostic = directory.join("unsupported-diagnostic.json");
    fs::write(&malformed, b"{not-json").unwrap();

    let value = command(1, "device-1", "unsupported");
    let mut unsupported_value: Value =
        serde_json::from_slice(&legacy_body("device-1", &value)).unwrap();
    unsupported_value["devices"]["device-1"]["config_fingerprint"] = json!("unknown:abcd");
    fs::write(
        &unsupported,
        serde_json::to_vec_pretty(&unsupported_value).unwrap(),
    )
    .unwrap();

    assert!(!run_import(&malformed, &malformed_sqlite, &malformed_diagnostic)
        .status
        .success());
    assert!(!malformed_sqlite.exists());
    assert!(!malformed_diagnostic.exists());

    assert!(!run_import(
        &unsupported,
        &unsupported_sqlite,
        &unsupported_diagnostic
    )
    .status
    .success());
    assert!(!unsupported_sqlite.exists());
    assert!(!unsupported_diagnostic.exists());
}

#[test]
fn overlapping_paths_are_rejected_before_file_access() {
    let directory = TempDirectory::new("path-conflict");
    let path = directory.join("same-path");
    let output = run_import(&path, &path, &path);
    assert!(!output.status.success());
    assert!(!path.exists());
}

#[test]
fn expected_fixture_matches_importer_canonical_state() {
    let value = command(1, "device-1", "fixture");
    let expected = canonical_snapshot("device-1", value.clone());
    let directory = TempDirectory::new("fixture");
    let source = directory.join("legacy.json");
    let sqlite = directory.join("state.sqlite3");
    let diagnostic = directory.join("diagnostic.json");
    fs::write(&source, legacy_body("device-1", &value)).unwrap();

    assert!(run_import(&source, &sqlite, &diagnostic).status.success());
    assert_eq!(
        fs::read(&diagnostic).unwrap(),
        expected.to_canonical_json().unwrap()
    );
}
