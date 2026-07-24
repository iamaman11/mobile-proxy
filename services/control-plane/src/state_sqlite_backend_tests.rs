use std::collections::BTreeMap;
use std::fs;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicU64, Ordering};

use mobile_proxy_application::{
    AcknowledgeCommandInput, AcknowledgeCommandOutcome, AcknowledgeCommandPort, HeartbeatInput,
    HeartbeatPort, IssueCommandInput, IssueCommandOutcome, IssueCommandPort, PollCommandInput,
    PollCommandOutcome, PollCommandPort, PublicProbeInput, PublicProbeOutcome, PublicProbePort,
    RegisterDeviceError, RegisterDeviceInput, RegisterDeviceOutcome, RegisterDevicePort,
};
use mobile_proxy_control_plane_sqlite::{ControlPlaneSnapshot, SqliteStore};
use mobile_proxy_foundation::{DeadlineWindow, IdempotencyKey};
use proxy_core::{
    CommandAckRequest, DesiredState, DeviceRecord, HeartbeatRequest, IssueCommandRequest,
    PublicProbeReport, RecoveryIntent, RegisterDeviceRequest,
};
use serde_json::json;

use crate::cli::StateBackend;

use super::AppState;

static NEXT_DATABASE_ID: AtomicU64 = AtomicU64::new(1);

struct TempDatabase {
    path: PathBuf,
}

impl TempDatabase {
    fn new(label: &str) -> Self {
        let id = NEXT_DATABASE_ID.fetch_add(1, Ordering::Relaxed);
        Self {
            path: std::env::temp_dir().join(format!(
                "mobile-proxy-control-plane-{label}-{}-{id}.sqlite3",
                std::process::id()
            )),
        }
    }

    fn initialize(&self) {
        let mut store = SqliteStore::open(&self.path).unwrap();
        store
            .replace_snapshot(&ControlPlaneSnapshot::empty())
            .unwrap();
    }
}

impl Drop for TempDatabase {
    fn drop(&mut self) {
        let _ = fs::remove_file(&self.path);
        let _ = fs::remove_file(sidecar_path(&self.path, "-wal"));
        let _ = fs::remove_file(sidecar_path(&self.path, "-shm"));
    }
}

fn sidecar_path(path: &Path, suffix: &str) -> PathBuf {
    let mut value = path.as_os_str().to_os_string();
    value.push(suffix);
    PathBuf::from(value)
}

fn registration(node_id: &str) -> RegisterDeviceInput {
    RegisterDeviceInput {
        request: RegisterDeviceRequest {
            node_id: node_id.to_owned(),
            node_name: format!("node-{node_id}"),
            proxy_status: "starting".to_owned(),
            tunnel_owner: Some("stock_wireguard_bridge".to_owned()),
        },
    }
}

fn heartbeat(node_id: &str) -> HeartbeatInput {
    HeartbeatInput {
        request: serde_json::from_value::<HeartbeatRequest>(json!({
            "node_id": node_id,
            "node_name": format!("node-{node_id}"),
            "readiness_state": "healthy",
            "serving": true,
            "proxy_status": "running"
        }))
        .unwrap(),
    }
}

fn command_input(device_id: &str, desired_state: DesiredState) -> IssueCommandInput {
    IssueCommandInput {
        device_id: device_id.to_owned(),
        request: IssueCommandRequest {
            desired_state,
            recovery_intent: RecoveryIntent::None,
            deadline_secs: DeadlineWindow::new(30).unwrap(),
            idempotency_key: IdempotencyKey::parse("sqlite-command").unwrap(),
        },
    }
}

fn external_device(node_id: &str) -> DeviceRecord {
    serde_json::from_value(json!({
        "node_id": node_id,
        "node_name": format!("external-{node_id}"),
        "readiness_state": "healthy",
        "serving": true,
        "proxy_status": "running",
        "publicly_serving": true,
        "availability": "available"
    }))
    .unwrap()
}

#[tokio::test]
async fn explicit_sqlite_backend_requires_an_existing_migrated_file() {
    let database = TempDatabase::new("missing-sqlite");
    let error = AppState::load_with_backend(database.path.clone(), StateBackend::Sqlite)
        .await
        .unwrap_err();
    assert!(error.to_string().contains("run the migration utility"));
    assert!(!database.path.exists());
}

#[tokio::test]
async fn sqlite_backend_preserves_existing_mutation_outcomes_across_restart() {
    let database = TempDatabase::new("sqlite-restart");
    database.initialize();
    let state = AppState::load_with_backend(database.path.clone(), StateBackend::Sqlite)
        .await
        .unwrap();

    assert_eq!(
        state
            .register_device(registration("device-1"))
            .await
            .unwrap(),
        RegisterDeviceOutcome::Created
    );
    state.record_heartbeat(heartbeat("device-1")).await.unwrap();
    assert_eq!(
        state
            .record_public_probe(PublicProbeInput {
                device_id: "device-1".to_owned(),
                report: PublicProbeReport {
                    publicly_serving: true,
                    public_probe_error: None,
                    public_probe_at: "1".to_owned(),
                },
            })
            .await
            .unwrap(),
        PublicProbeOutcome::Updated
    );

    let created = state
        .issue_command(command_input("device-1", DesiredState::HealthyServing))
        .await
        .unwrap();
    let command = match created {
        IssueCommandOutcome::Created(command) => command,
        other => panic!("expected created command, got {other:?}"),
    };
    assert_eq!(
        state
            .issue_command(command_input("device-1", DesiredState::HealthyServing))
            .await
            .unwrap(),
        IssueCommandOutcome::ExactDuplicate(command.clone())
    );
    assert_eq!(
        state
            .poll_command(PollCommandInput {
                device_id: "device-1".to_owned(),
            })
            .await
            .unwrap(),
        PollCommandOutcome::Pending(command.clone())
    );
    assert_eq!(
        state
            .acknowledge_command(AcknowledgeCommandInput {
                device_id: "device-1".to_owned(),
                command_id: command.command_id,
                request: CommandAckRequest {
                    ok: true,
                    message: None,
                },
            })
            .await
            .unwrap(),
        AcknowledgeCommandOutcome::Completed
    );
    drop(state);

    let restarted = AppState::load_with_backend(database.path.clone(), StateBackend::Sqlite)
        .await
        .unwrap();
    assert_eq!(
        restarted
            .issue_command(command_input("device-1", DesiredState::HealthyServing))
            .await
            .unwrap(),
        IssueCommandOutcome::ExactDuplicate(command)
    );
    assert_eq!(
        restarted
            .poll_command(PollCommandInput {
                device_id: "device-1".to_owned(),
            })
            .await
            .unwrap(),
        PollCommandOutcome::Empty
    );
    let stored = restarted
        .devices
        .lock()
        .await
        .get("device-1")
        .unwrap()
        .clone();
    assert_eq!(stored.proxy_status, "running");
    assert!(stored.publicly_serving);
}

#[tokio::test]
async fn stale_external_sqlite_writer_prevents_in_memory_publication() {
    let database = TempDatabase::new("sqlite-stale-writer");
    database.initialize();
    let state = AppState::load_with_backend(database.path.clone(), StateBackend::Sqlite)
        .await
        .unwrap();

    let external = ControlPlaneSnapshot::from_parts(
        BTreeMap::from([(
            "external-device".to_owned(),
            external_device("external-device"),
        )]),
        BTreeMap::new(),
        Vec::new(),
    )
    .unwrap();
    let mut external_store = SqliteStore::open(&database.path).unwrap();
    external_store.replace_snapshot(&external).unwrap();
    drop(external_store);

    assert_eq!(
        state.register_device(registration("device-local")).await,
        Err(RegisterDeviceError::Persistence)
    );
    assert!(state.devices.lock().await.is_empty());

    let mut reopened = SqliteStore::open(&database.path).unwrap();
    let rehydrated = reopened.load_snapshot().unwrap();
    assert!(rehydrated.devices().contains_key("external-device"));
    assert!(!rehydrated.devices().contains_key("device-local"));
}
