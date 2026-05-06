use std::{collections::HashMap, sync::Arc};

use axum::{
    Json, Router,
    extract::{Path, State},
    routing::{get, post},
};
use clap::Parser;
use proxy_core::{DeviceRecord, HeartbeatRequest, PublicProbeReport, RegisterDeviceRequest};
use tokio::{net::TcpListener, sync::Mutex};
use tracing::info;

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
}

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    tracing_subscriber::fmt::init();
    let cli = Cli::parse();
    let state = AppState {
        devices: Arc::new(Mutex::new(HashMap::new())),
    };
    let app = Router::new()
        .route("/api/v1/ip", get(get_ip))
        .route("/api/v1/devices", get(list_devices))
        .route("/api/v1/devices/ready", get(list_ready_devices))
        .route("/api/v1/devices/register", post(register_device))
        .route("/api/v1/devices/heartbeat", post(heartbeat))
        .route("/api/v1/devices/{id}/public-probe", post(public_probe))
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
    devices.entry(req.node_id.clone()).or_insert(DeviceRecord {
        node_id: req.node_id,
        node_name: req.node_name,
        readiness_state: "booting".into(),
        serving: false,
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
        availability: "degraded".into(),
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
    devices.insert(
        req.node_id.clone(),
        DeviceRecord {
            node_id: req.node_id,
            node_name: req.node_name,
            readiness_state: req.readiness_state,
            serving: req.serving,
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
            availability: compute_availability(req.serving, publicly_serving).into(),
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
        device.availability = compute_availability(device.serving, device.publicly_serving).into();
    }
    Json(serde_json::json!({ "accepted": true }))
}

fn compute_availability(serving: bool, publicly_serving: bool) -> &'static str {
    if serving && publicly_serving {
        "ready"
    } else {
        "degraded"
    }
}

#[cfg(test)]
mod tests {
    use super::compute_availability;

    #[test]
    fn availability_requires_public_probe() {
        assert_eq!(compute_availability(true, false), "degraded");
        assert_eq!(compute_availability(false, true), "degraded");
        assert_eq!(compute_availability(true, true), "ready");
    }
}
