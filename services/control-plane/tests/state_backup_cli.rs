use std::collections::{BTreeMap, VecDeque};
use std::fs;
use std::net::TcpListener;
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Output, Stdio};
use std::str::FromStr;
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::Duration;

use mobile_proxy_control_plane_sqlite::{ControlPlaneSnapshot, ReplayRecord, SqliteStore};
use mobile_proxy_foundation::{CommandId, DeadlineWindow, IdempotencyKey};
use proxy_core::{DesiredState, DeviceCommand, DeviceRecord, RecoveryIntent};
use reqwest::{Client, StatusCode};
use serde_json::{Value, json};
use tokio::time::{sleep, timeout};

static NEXT_DIRECTORY_ID: AtomicU64 = AtomicU64::new(1);

struct TempDirectory {
    path: PathBuf,
}

impl TempDirectory {
    fn new(label: &str) -> Self {
        let id = NEXT_DIRECTORY_ID.fetch_add(1, Ordering::Relaxed);
        let path = std::env::temp_dir().join(format!(
            "mobile-proxy-state-backup-{label}-{}-{id}",
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

struct ChildGuard(Child);

impl Drop for ChildGuard {
    fn drop(&mut self) {
        let _ = self.0.kill();
        let _ = self.0.wait();
    }
}

fn backup_binary() -> &'static str {
    env!("CARGO_BIN_EXE_control-plane-state-backup")
}

fn run_backup(source: &Path, backup: &Path) -> Output {
    Command::new(backup_binary())
        .args([
            "backup",
            "--sqlite",
            source.to_str().unwrap(),
            "--backup",
            backup.to_str().unwrap(),
        ])
        .output()
        .unwrap()
}

fn run_restore(backup: &Path, target: &Path) -> Output {
    Command::new(backup_binary())
        .args([
            "restore",
            "--backup",
            backup.to_str().unwrap(),
            "--sqlite",
            target.to_str().unwrap(),
        ])
        .output()
        .unwrap()
}

fn run_verify(sqlite: &Path) -> Output {
    Command::new(backup_binary())
        .args(["verify", "--sqlite", sqlite.to_str().unwrap()])
        .output()
        .unwrap()
}

fn stdout_json(output: &Output) -> Value {
    serde_json::from_slice(&output.stdout).unwrap_or_else(|error| {
        panic!(
            "stdout must be JSON: {error}; stdout={:?}; stderr={:?}",
            String::from_utf8_lossy(&output.stdout),
            String::from_utf8_lossy(&output.stderr)
        )
    })
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn backup_restore_and_clean_process_drill_preserve_canonical_state() {
    let directory = TempDirectory::new("drill");
    let source = directory.join("source.sqlite3");
    let backup = directory.join("backups/state.sqlite3");
    let restored = directory.join("clean/state.sqlite3");
    let expected = representative_snapshot();
    let expected_json = expected.to_canonical_json().unwrap();

    let mut store = SqliteStore::open(&source).unwrap();
    store.replace_snapshot(&expected).unwrap();
    drop(store);

    let backup_output = run_backup(&source, &backup);
    assert!(
        backup_output.status.success(),
        "backup failed: {}",
        String::from_utf8_lossy(&backup_output.stderr)
    );
    let backup_report = stdout_json(&backup_output);
    assert_eq!(backup_report["operation"], "backup");
    assert_eq!(backup_report["devices"], 1);
    assert_eq!(backup_report["pending_commands"], 1);
    assert_eq!(backup_report["replay_records"], 1);
    assert!(backup.is_file());
    assert_eq!(canonical(&source), expected_json);
    assert_eq!(canonical(&backup), expected_json);

    let verify = run_verify(&backup);
    assert!(verify.status.success());
    assert_eq!(stdout_json(&verify)["healthy"], true);

    let restore_output = run_restore(&backup, &restored);
    assert!(
        restore_output.status.success(),
        "restore failed: {}",
        String::from_utf8_lossy(&restore_output.stderr)
    );
    assert_eq!(stdout_json(&restore_output)["operation"], "restore");
    assert_eq!(canonical(&restored), expected_json);

    let existing_target = run_restore(&backup, &restored);
    assert!(!existing_target.status.success());
    assert_eq!(canonical(&restored), expected_json);

    prove_restored_process(restored).await;
}

#[test]
fn invalid_or_overlapping_restore_fails_without_creating_a_target() {
    let directory = TempDirectory::new("fail-closed");
    let corrupt = directory.join("corrupt.sqlite3");
    let target = directory.join("target.sqlite3");
    fs::write(&corrupt, b"not-a-sqlite-database").unwrap();

    let invalid = run_restore(&corrupt, &target);
    assert!(!invalid.status.success());
    assert!(!target.exists());
    assert!(!directory.join("target.sqlite3.tmp").exists());

    let overlap = run_restore(&corrupt, &corrupt);
    assert!(!overlap.status.success());
    assert_eq!(fs::read(&corrupt).unwrap(), b"not-a-sqlite-database");
}

fn representative_snapshot() -> ControlPlaneSnapshot {
    let command = DeviceCommand {
        command_id: CommandId::from_str("00000000000000000000000000000001").unwrap(),
        device_id: "device-1".into(),
        desired_state: DesiredState::HealthyServing,
        recovery_intent: RecoveryIntent::None,
        deadline_secs: DeadlineWindow::new(30).unwrap(),
        idempotency_key: IdempotencyKey::parse("backup-drill").unwrap(),
        issued_at: "1".into(),
    };
    ControlPlaneSnapshot::from_parts(
        BTreeMap::from([("device-1".into(), device("device-1"))]),
        BTreeMap::from([("device-1".into(), VecDeque::from([command.clone()]))]),
        vec![ReplayRecord::from_command(command)],
    )
    .unwrap()
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

fn canonical(path: &Path) -> Vec<u8> {
    let mut store = SqliteStore::open_existing(path).unwrap();
    store.load_snapshot().unwrap().to_canonical_json().unwrap()
}

async fn prove_restored_process(restored: PathBuf) {
    let listener = TcpListener::bind("127.0.0.1:0").unwrap();
    let address = listener.local_addr().unwrap();
    drop(listener);
    let address_string = address.to_string();

    let child = Command::new(env!("CARGO_BIN_EXE_control-plane"))
        .args([
            "--listen",
            &address_string,
            "--admin-token",
            "admin-secret",
            "--device-token",
            "device-secret",
            "--state-path",
            restored.to_str().unwrap(),
        ])
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn()
        .unwrap();
    let _child = ChildGuard(child);

    let client = Client::builder()
        .timeout(Duration::from_secs(1))
        .build()
        .unwrap();
    let base = format!("http://{address}");
    wait_for_status(&client, &format!("{base}/readyz"), StatusCode::OK).await;

    let devices = client
        .get(format!("{base}/api/v1/devices"))
        .bearer_auth("admin-secret")
        .send()
        .await
        .unwrap();
    assert_eq!(devices.status(), StatusCode::OK);
    let devices: Vec<DeviceRecord> = devices.json().await.unwrap();
    assert_eq!(devices.len(), 1);
    assert_eq!(devices[0].node_id, "device-1");

    let command = client
        .get(format!("{base}/api/v1/devices/device-1/commands/next"))
        .bearer_auth("device-secret")
        .send()
        .await
        .unwrap();
    assert_eq!(command.status(), StatusCode::OK);
    let command: DeviceCommand = command.json().await.unwrap();
    assert_eq!(
        command.command_id,
        CommandId::from_str("00000000000000000000000000000001").unwrap()
    );
}

async fn wait_for_status(client: &Client, url: &str, expected: StatusCode) {
    timeout(Duration::from_secs(5), async {
        loop {
            if let Ok(response) = client.get(url).send().await
                && response.status() == expected
            {
                return;
            }
            sleep(Duration::from_millis(25)).await;
        }
    })
    .await
    .unwrap_or_else(|_| panic!("timed out waiting for {expected} from {url}"));
}
