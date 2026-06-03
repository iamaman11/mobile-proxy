use axum::{
    Json, Router,
    extract::{Path, State},
    routing::{get, post},
};
use proxy_core::{
    CommandAckRequest, DeviceCommand, DeviceRecord, HeartbeatRequest, IssueCommandRequest,
    PublicProbeReport, RecoveryIntent, RegisterDeviceRequest,
};
use uuid::Uuid;

use crate::projection::{
    apply_public_probe, build_heartbeat_device, build_registered_device, now_unix_secs,
};
use crate::state::AppState;

pub fn router(state: AppState) -> Router {
    Router::new()
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
        .with_state(state)
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
    devices
        .entry(req.node_id.clone())
        .or_insert_with(|| build_registered_device(req));
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
    let node_id = req.node_id.clone();
    devices.insert(
        node_id,
        build_heartbeat_device(req, publicly_serving, public_probe_error, public_probe_at),
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
        apply_public_probe(device, req);
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
    drop(commands);

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

#[cfg(test)]
mod tests {
    use crate::projection::now_unix_secs;
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
