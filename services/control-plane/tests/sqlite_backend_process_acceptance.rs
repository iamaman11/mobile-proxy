use std::fs;
use std::net::TcpListener;
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Output, Stdio};
use std::str::FromStr;
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::Duration;

use mobile_proxy_application::idempotency_scope_key;
use mobile_proxy_foundation::{CommandId, DeadlineWindow, IdempotencyKey};
use proxy_core::{
    CommandAckRequest, DesiredState, DeviceCommand, DeviceRecord, IssueCommandRequest,
    RecoveryIntent,
};
use reqwest::{Client, StatusCode};
use serde_json::json;

const ADMIN_TOKEN: &str = "process-admin-token";
const DEVICE_TOKEN: &str = "process-device-token";
const DEVICE_ID: &str = "device-1";

static NEXT_DIRECTORY_ID: AtomicU64 = AtomicU64::new(1);

struct TempDirectory {
    path: PathBuf,
}

impl TempDirectory {
    fn new(label: &str) -> Self {
        let id = NEXT_DIRECTORY_ID.fetch_add(1, Ordering::Relaxed);
        let path = std::env::temp_dir().join(format!(
            "mobile-proxy-sqlite-process-{label}-{}-{id}",
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

struct Daemon {
    child: Child,
    base_url: String,
}

impl Daemon {
    async fn start(backend: &str, state_path: &Path, client: &Client) -> Self {
        let listener = TcpListener::bind("127.0.0.1:0").unwrap();
        let address = listener.local_addr().unwrap();
        drop(listener);

        let child = Command::new(control_plane_binary())
            .arg("--listen")
            .arg(address.to_string())
            .arg("--admin-token")
            .arg(ADMIN_TOKEN)
            .arg("--device-token")
            .arg(DEVICE_TOKEN)
            .arg("--state-backend")
            .arg(backend)
            .arg("--state-path")
            .arg(state_path)
            .stdin(Stdio::null())
            .stdout(Stdio::null())
            .stderr(Stdio::inherit())
            .spawn()
            .unwrap();

        let mut daemon = Self {
            child,
            base_url: format!("http://{address}"),
        };
        for _ in 0..100 {
            if let Some(status) = daemon.child.try_wait().unwrap() {
                panic!("control-plane exited before readiness with {status}");
            }
            match client
                .get(format!("{}/api/v1/devices", daemon.base_url))
                .bearer_auth(ADMIN_TOKEN)
                .send()
                .await
            {
                Ok(response) if response.status().is_success() => return daemon,
                _ => tokio::time::sleep(Duration::from_millis(25)).await,
            }
        }
        panic!("control-plane did not become ready");
    }

    fn stop(&mut self) {
        if self.child.try_wait().unwrap().is_none() {
            self.child.kill().unwrap();
        }
        self.child.wait().unwrap();
    }
}

impl Drop for Daemon {
    fn drop(&mut self) {
        if self.child.try_wait().ok().flatten().is_none() {
            let _ = self.child.kill();
            let _ = self.child.wait();
        }
    }
}

fn control_plane_binary() -> &'static str {
    env!("CARGO_BIN_EXE_control-plane")
}

fn migration_binary() -> &'static str {
    env!("CARGO_BIN_EXE_control-plane-state-migrate")
}

fn command() -> DeviceCommand {
    DeviceCommand {
        command_id: CommandId::from_str("00000000000000000000000000000001").unwrap(),
        device_id: DEVICE_ID.to_owned(),
        desired_state: DesiredState::HealthyServing,
        recovery_intent: RecoveryIntent::None,
        deadline_secs: DeadlineWindow::new(30).unwrap(),
        idempotency_key: IdempotencyKey::parse("process-cutover").unwrap(),
        issued_at: "1".to_owned(),
    }
}

fn issue_request(desired_state: DesiredState) -> IssueCommandRequest {
    IssueCommandRequest {
        desired_state,
        recovery_intent: RecoveryIntent::None,
        deadline_secs: DeadlineWindow::new(30).unwrap(),
        idempotency_key: IdempotencyKey::parse("process-cutover").unwrap(),
    }
}

fn device() -> DeviceRecord {
    serde_json::from_value(json!({
        "node_id": DEVICE_ID,
        "node_name": "node-device-1",
        "readiness_state": "healthy",
        "serving": true,
        "proxy_status": "running",
        "publicly_serving": true,
        "availability": "available"
    }))
    .unwrap()
}

fn canonical_json_source(value: &DeviceCommand) -> Vec<u8> {
    let legacy_scope = format!("{DEVICE_ID}:{}", value.idempotency_key);
    let canonical_scope = idempotency_scope_key(DEVICE_ID, &value.idempotency_key).to_string();
    serde_json::to_vec_pretty(&json!({
        "devices": {
            DEVICE_ID: device()
        },
        "commands": {
            "queues": {
                DEVICE_ID: [value]
            },
            "idempotency": {
                legacy_scope: value.command_id
            },
            "idempotency_results": {
                canonical_scope.clone(): value
            },
            "idempotency_order": [canonical_scope]
        }
    }))
    .unwrap()
}

fn run_import(source: &Path, sqlite: &Path, diagnostic: &Path) -> Output {
    Command::new(migration_binary())
        .args(["import", "--legacy-json"])
        .arg(source)
        .arg("--sqlite")
        .arg(sqlite)
        .arg("--diagnostic-json")
        .arg(diagnostic)
        .output()
        .unwrap()
}

async fn list_devices(client: &Client, daemon: &Daemon) -> Vec<DeviceRecord> {
    client
        .get(format!("{}/api/v1/devices", daemon.base_url))
        .bearer_auth(ADMIN_TOKEN)
        .send()
        .await
        .unwrap()
        .error_for_status()
        .unwrap()
        .json()
        .await
        .unwrap()
}

async fn next_command(client: &Client, daemon: &Daemon) -> Option<DeviceCommand> {
    client
        .get(format!(
            "{}/api/v1/devices/{DEVICE_ID}/commands/next",
            daemon.base_url
        ))
        .bearer_auth(DEVICE_TOKEN)
        .send()
        .await
        .unwrap()
        .error_for_status()
        .unwrap()
        .json()
        .await
        .unwrap()
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn sqlite_restart_replay_and_json_rollback_work_through_real_daemon() {
    let directory = TempDirectory::new("acceptance");
    let source = directory.join("control-plane-state.json");
    let sqlite = directory.join("control-plane-state.sqlite3");
    let diagnostic = directory.join("control-plane-state-diagnostic.json");
    let original_command = command();
    let source_bytes = canonical_json_source(&original_command);
    fs::write(&source, &source_bytes).unwrap();

    let import = run_import(&source, &sqlite, &diagnostic);
    assert!(
        import.status.success(),
        "migration failed: {}",
        String::from_utf8_lossy(&import.stderr)
    );
    assert!(diagnostic.is_file());
    assert_eq!(fs::read(&source).unwrap(), source_bytes);

    let client = Client::builder()
        .timeout(Duration::from_secs(2))
        .build()
        .unwrap();

    {
        let mut daemon = Daemon::start("sqlite", &sqlite, &client).await;
        let devices = list_devices(&client, &daemon).await;
        assert_eq!(devices.len(), 1);
        assert_eq!(devices[0].node_id, DEVICE_ID);
        assert_eq!(next_command(&client, &daemon).await, Some(original_command.clone()));

        let acknowledgement = client
            .post(format!(
                "{}/api/v1/devices/{DEVICE_ID}/commands/{}/ack",
                daemon.base_url, original_command.command_id
            ))
            .bearer_auth(DEVICE_TOKEN)
            .json(&CommandAckRequest {
                ok: true,
                message: None,
            })
            .send()
            .await
            .unwrap();
        assert!(acknowledgement.status().is_success());
        daemon.stop();
    }

    {
        let mut daemon = Daemon::start("sqlite", &sqlite, &client).await;
        assert_eq!(next_command(&client, &daemon).await, None);

        let replayed: DeviceCommand = client
            .post(format!(
                "{}/api/v1/devices/{DEVICE_ID}/commands",
                daemon.base_url
            ))
            .bearer_auth(ADMIN_TOKEN)
            .json(&issue_request(DesiredState::HealthyServing))
            .send()
            .await
            .unwrap()
            .error_for_status()
            .unwrap()
            .json()
            .await
            .unwrap();
        assert_eq!(replayed, original_command);

        let conflict = client
            .post(format!(
                "{}/api/v1/devices/{DEVICE_ID}/commands",
                daemon.base_url
            ))
            .bearer_auth(ADMIN_TOKEN)
            .json(&issue_request(DesiredState::DegradedSafe))
            .send()
            .await
            .unwrap();
        assert_eq!(conflict.status(), StatusCode::CONFLICT);
        daemon.stop();
    }

    assert_eq!(fs::read(&source).unwrap(), source_bytes);

    {
        let mut rollback = Daemon::start("json", &source, &client).await;
        let devices = list_devices(&client, &rollback).await;
        assert_eq!(devices.len(), 1);
        assert_eq!(devices[0].node_id, DEVICE_ID);
        assert_eq!(
            next_command(&client, &rollback).await,
            Some(original_command)
        );
        rollback.stop();
    }

    assert_eq!(fs::read(&source).unwrap(), source_bytes);
}
