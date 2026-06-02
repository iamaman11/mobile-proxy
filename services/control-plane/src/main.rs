use std::{
    collections::{HashMap, VecDeque},
    sync::Arc,
    time::{SystemTime, UNIX_EPOCH},
};

use axum::{
    Json, Router,
    extract::{Path, State},
    routing::{get, post},
};
use clap::Parser;
use proxy_core::{
    CommandAckRequest, DeviceCommand, DeviceRecord, HeartbeatRequest, IssueCommandRequest,
    PublicProbeReport, RecoveryIntent, RegisterDeviceRequest, RuntimeProjectionInput,
    project_runtime,
};
use tokio::{net::TcpListener, sync::Mutex};
use tracing::info;
use uuid::Uuid;

#[derive(Parser, Debug)]
#[command(name = "control-plane")]
#[command(about = "Reconstructed registry and public probe service")]
struct Cli {
    #[arg(long, env = "CONTROL_PLANE_LISTEN", default_value = "0.0.0.0:8080")]
    listen: String,
}

#[derive(Clone)]
struct AppState {
    devices: Arc<Mutex<HashMap<String, DeviceRecord>>>,
    commands: Arc<Mutex<CommandState>>,
}

#[derive(Default)]
struct CommandState {
    queues: HashMap<String, VecDeque<DeviceCommand>>,
    idempotency: HashMap<String, Uuid>,
}

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    tracing_subscriber::fmt::init();
    let cli = Cli::parse();
    let state = AppState {
        devices: Arc::new(Mutex::new(HashMap::new())),
        commands: Arc::new(Mutex::new(CommandState::default())),
    };
    let app = Router::new()
        .route("/api/v1/ip", get(get_ip))
        .route("/api/v1/devices", get(list_devices))
        .route("/api/v1/devices/ready", get(list_ready_devices))
        .route("/api/v1/devices/register", post(register_device))
        .route("/api/v1/devices/heartbeat", post(heartbeat))
        .route("/api/v1/devices/{id}/public-probe", post(public_probe))
        .route("/api/v1/devices/{id}/commands", post(issue_command))
        .route("/api/v1/devices/{id}/commands/next", get(next_command))
        .route(
            "/api/v1/devices/{id}/commands/{command_id}/ack",
            post(ack_command),
        )
        .with_state(state);
    let listener = TcpListener::bind(&cli.listen).await?;
    info!("control-plane listening on {}", cli.listen);
    axum::serve(listener, app).await?;
    Ok(())
}

async fn get_ip() -> Json<serde_json::Value> {
    Json(serde_json::json!({ "ip": "178.168.186.196" }))
}

async fn list_devices(State(state): State<AppState>) -> Json<Vec<DeviceRecord>> {
    let devices = state.devices.lock().await;
    Json(devices.values().cloned().collect())
}

async fn list_ready_devices(State(state): State<AppState>) -> Json<Vec<DeviceRecord>> {
    let devices = state.devices.lock().await;
    Json(
        devices
            .values()
            .filter(|device| device.availability == "ready")
            .cloned()
            .collect(),
    )
}

async fn register_device(
    State(state): State<AppState>,
    Json(req): Json<RegisterDeviceRequest>,
) -> Json<serde_json::Value> {
    let mut devices = state.devices.lock().await;
    devices.entry(req.node_id.clone()).or_insert_with(|| {
        let projection = project_runtime(RuntimeProjectionInput {
            readiness_state: "booting".into(),
            serving: false,
            publicly_serving: false,
            current_job: None,
            cellular_route_ready: None,
            proxy_bind_ready: None,
            local_serving_ready: None,
        });
        DeviceRecord {
            node_id: req.node_id,
            node_name: req.node_name,
            readiness_state: projection.readiness_state,
            serving: projection.serving,
            proxy_status: req.proxy_status,
            proxy_pid: None,
            last_public_ip: None,
            current_job: None,
            last_proxy_error: None,
            version: None,
            config_fingerprint: None,
            binary_fingerprint: None,
            active_operator_profile: None,
            active_operator_plmn: None,
            publicly_serving: false,
            public_probe_error: None,
            public_probe_at: None,
            availability: projection.availability,
            degradation_reason_code: projection.degradation_reason_code,
            serving_failure_reason: projection.serving_failure_reason,
            desired_state: Some("degraded_safe".into()),
            recovery_intent: Some("none".into()),
            last_event_at: Some(now_unix_secs()),
        }
    });
    Json(serde_json::json!({ "accepted": true }))
}

async fn heartbeat(
    State(state): State<AppState>,
    Json(req): Json<HeartbeatRequest>,
) -> Json<serde_json::Value> {
    let mut devices = state.devices.lock().await;
    let previous_probe = devices.get(&req.node_id).map(|device| {
        (
            device.publicly_serving,
            device.public_probe_error.clone(),
            device.public_probe_at.clone(),
        )
    });
    let (publicly_serving, public_probe_error, public_probe_at) =
        previous_probe.unwrap_or((false, None, None));
    let projection = project_runtime(RuntimeProjectionInput {
        readiness_state: req.readiness_state,
        serving: req.serving,
        publicly_serving,
        current_job: req.current_job,
        cellular_route_ready: req.cellular_route_ready,
        proxy_bind_ready: req.proxy_bind_ready,
        local_serving_ready: req.local_serving_ready,
    });
    devices.insert(
        req.node_id.clone(),
        DeviceRecord {
            node_id: req.node_id,
            node_name: req.node_name,
            readiness_state: projection.readiness_state,
            serving: projection.serving,
            proxy_status: req.proxy_status,
            proxy_pid: req.proxy_pid,
            last_public_ip: req.last_public_ip,
            current_job: req.current_job,
            last_proxy_error: req.last_proxy_error,
            version: req.version,
            config_fingerprint: req.config_fingerprint,
            binary_fingerprint: req.binary_fingerprint,
            active_operator_profile: req.active_operator_profile,
            active_operator_plmn: req.active_operator_plmn,
            publicly_serving,
            public_probe_error,
            public_probe_at,
            availability: projection.availability,
            degradation_reason_code: projection.degradation_reason_code,
            serving_failure_reason: projection.serving_failure_reason,
            desired_state: Some("healthy_serving".into()),
            recovery_intent: Some("none".into()),
            last_event_at: Some(now_unix_secs()),
        },
    );
    Json(serde_json::json!({ "accepted": true }))
}

async fn public_probe(
    State(state): State<AppState>,
    Path(id): Path<String>,
    Json(req): Json<PublicProbeReport>,
) -> Json<serde_json::Value> {
    let mut devices = state.devices.lock().await;
    if let Some(device) = devices.get_mut(&id) {
        device.publicly_serving = req.publicly_serving;
        device.public_probe_error = req.public_probe_error;
        device.public_probe_at = Some(req.public_probe_at);
        let projection = project_runtime(RuntimeProjectionInput {
            readiness_state: device.readiness_state.clone(),
            serving: device.serving,
            publicly_serving: device.publicly_serving,
            current_job: device.current_job,
            cellular_route_ready: None,
            proxy_bind_ready: None,
            local_serving_ready: None,
        });
        device.readiness_state = projection.readiness_state;
        device.serving = projection.serving;
        device.availability = projection.availability;
        device.degradation_reason_code = projection.degradation_reason_code;
        device.serving_failure_reason = projection.serving_failure_reason;
        device.last_event_at = Some(now_unix_secs());
    }
    Json(serde_json::json!({ "accepted": true }))
}

async fn issue_command(
    State(state): State<AppState>,
    Path(id): Path<String>,
    Json(req): Json<IssueCommandRequest>,
) -> Json<DeviceCommand> {
    let mut commands = state.commands.lock().await;
    let dedupe_key = format!("{id}:{}", req.idempotency_key);
    if let Some(existing_id) = commands.idempotency.get(&dedupe_key).copied()
        && let Some(existing) = commands.queues.get(&id).and_then(|queue| {
            queue
                .iter()
                .find(|command| command.command_id == existing_id)
        })
    {
        return Json(existing.clone());
    }

    let command = DeviceCommand {
        command_id: Uuid::new_v4(),
        device_id: id.clone(),
        desired_state: req.desired_state,
        recovery_intent: req.recovery_intent,
        deadline_secs: req.deadline_secs,
        idempotency_key: req.idempotency_key,
        issued_at: now_unix_secs(),
    };
    commands
        .queues
        .entry(id.clone())
        .or_default()
        .push_back(command.clone());
    commands.idempotency.insert(dedupe_key, command.command_id);

    let mut devices = state.devices.lock().await;
    if let Some(device) = devices.get_mut(&id) {
        device.desired_state = Some(command.desired_state.to_string());
        device.recovery_intent = Some(command.recovery_intent.to_string());
        device.last_event_at = Some(command.issued_at.clone());
    }
    Json(command)
}

async fn next_command(
    State(state): State<AppState>,
    Path(id): Path<String>,
) -> Json<Option<DeviceCommand>> {
    let commands = state.commands.lock().await;
    let next = commands
        .queues
        .get(&id)
        .and_then(|queue| queue.front().cloned());
    Json(next)
}

async fn ack_command(
    State(state): State<AppState>,
    Path((id, command_id)): Path<(String, Uuid)>,
    Json(req): Json<CommandAckRequest>,
) -> Json<serde_json::Value> {
    let mut removed = false;
    let mut commands = state.commands.lock().await;
    if req.ok
        && let Some(queue) = commands.queues.get_mut(&id)
        && let Some(index) = queue
            .iter()
            .position(|command| command.command_id == command_id)
    {
        queue.remove(index);
        removed = true;
    }
    drop(commands);

    if req.ok {
        let mut devices = state.devices.lock().await;
        if let Some(device) = devices.get_mut(&id) {
            device.recovery_intent = Some(RecoveryIntent::None.to_string());
            device.last_event_at = Some(now_unix_secs());
        }
    }

    Json(serde_json::json!({ "accepted": removed || !req.ok }))
}

fn now_unix_secs() -> String {
    match SystemTime::now().duration_since(UNIX_EPOCH) {
        Ok(duration) => duration.as_secs().to_string(),
        Err(_) => "0".into(),
    }
}

#[cfg(test)]
mod tests {
    use super::now_unix_secs;
    use proxy_core::{Availability, RuntimeProjectionInput, RuntimeReadiness, project_runtime};

    #[test]
    fn availability_requires_public_probe() {
        let projection = project_runtime(RuntimeProjectionInput {
            readiness_state: RuntimeReadiness::Healthy.to_string(),
            serving: true,
            publicly_serving: false,
            current_job: None,
            cellular_route_ready: Some(true),
            proxy_bind_ready: Some(true),
            local_serving_ready: Some(true),
        });
        assert_eq!(projection.availability, Availability::Degraded.to_string());
    }

    #[test]
    fn unix_clock_is_serialized() {
        let ts = now_unix_secs();
        assert!(ts.parse::<u64>().is_ok());
    }
}
