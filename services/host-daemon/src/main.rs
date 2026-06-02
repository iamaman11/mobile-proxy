use std::{
    collections::HashMap,
    env, fs,
    sync::Arc,
    time::{Duration, Instant},
};

use axum::{
    Json, Router,
    extract::{Path, State},
    http::{HeaderMap, StatusCode},
    response::IntoResponse,
    routing::{get, post},
};
use clap::Parser;
use proxy_core::{
    CommandAckRequest, DesiredState, DeviceCommand, HealthRecord, HeartbeatRequest, JobRecord,
    ProxyRuntimeRecord, RecoveryIntent, RegisterDeviceRequest, RotateAccepted, RotateRequest,
    RuntimeReadiness, RuntimeStatusRecord, default_rotate_request,
};
use serde::Deserialize;
use tokio::{
    net::TcpListener,
    sync::Mutex,
    time::{MissedTickBehavior, interval, sleep},
};
use tracing::{info, warn};
use uuid::Uuid;

#[derive(Parser, Debug)]
#[command(name = "host-daemon")]
#[command(about = "Reconstructed local device API and rotate job service")]
struct Cli {
    #[arg(long, env = "HOST_DAEMON_LISTEN")]
    listen: Option<String>,
    #[arg(long, env = "HOST_DAEMON_ADMIN_TOKEN")]
    admin_token: Option<String>,
    #[arg(long, env = "HOST_DAEMON_CONFIG")]
    config: Option<String>,
}

#[derive(Clone)]
struct AppState {
    admin_token: String,
    runtime: Arc<Mutex<RuntimeState>>,
}

struct RuntimeState {
    health: HealthRecord,
    jobs: HashMap<Uuid, JobRecord>,
    ip_pool: Vec<String>,
    ip_index: usize,
    current_job: Option<Uuid>,
    wireguard_enabled: bool,
    proxy_listen_address: String,
    proxy_pid: Option<u32>,
}

#[derive(Debug, Deserialize, Clone)]
struct FileConfig {
    node_id: Option<String>,
    node_name: Option<String>,
    listen: Option<String>,
    admin_token: Option<String>,
    operator_profiles: Option<FileOperatorProfiles>,
    proxy: Option<FileProxyConfig>,
    wireguard: Option<FileWireguardConfig>,
    control_plane: Option<FileControlPlaneConfig>,
}

#[derive(Debug, Deserialize, Clone)]
struct FileOperatorProfiles {
    default_profile: Option<String>,
}

#[derive(Debug, Deserialize, Clone)]
struct FileProxyConfig {
    listen_address: Option<String>,
}

#[derive(Debug, Deserialize, Clone)]
struct FileWireguardConfig {
    enabled: Option<bool>,
}

#[derive(Debug, Deserialize, Clone)]
struct FileControlPlaneConfig {
    base_url: Option<String>,
    heartbeat_interval_secs: Option<u64>,
    poll_interval_secs: Option<u64>,
}

#[derive(Debug, Clone)]
struct ControlPlaneSyncConfig {
    base_url: String,
    heartbeat_interval_secs: u64,
    poll_interval_secs: u64,
}

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    tracing_subscriber::fmt::init();
    let cli = Cli::parse();
    let file_config = load_file_config(cli.config.as_deref())?;
    let listen = cli
        .listen
        .or_else(|| file_config.as_ref().and_then(|c| c.listen.clone()))
        .unwrap_or_else(|| "127.0.0.1:8088".into());
    let admin_token = cli
        .admin_token
        .or_else(|| file_config.as_ref().and_then(|c| c.admin_token.clone()))
        .unwrap_or_else(|| "change-me".into());
    let node_id = file_config
        .as_ref()
        .and_then(|c| c.node_id.clone())
        .or_else(|| env::var("HOST_DAEMON_NODE_ID").ok())
        .unwrap_or_else(|| proxy_core::DEVICE_ID.to_string());
    let node_name = file_config
        .as_ref()
        .and_then(|c| c.node_name.clone())
        .or_else(|| env::var("HOST_DAEMON_NODE_NAME").ok())
        .unwrap_or_else(|| proxy_core::NODE_NAME.to_string());
    let active_profile = file_config
        .as_ref()
        .and_then(|c| c.operator_profiles.as_ref())
        .and_then(|p| p.default_profile.clone())
        .unwrap_or_else(|| "mts_by".into());
    let wireguard_enabled = file_config
        .as_ref()
        .and_then(|c| c.wireguard.as_ref())
        .and_then(|w| w.enabled)
        .unwrap_or(false);
    let proxy_listen_address = file_config
        .as_ref()
        .and_then(|c| c.proxy.as_ref())
        .and_then(|p| p.listen_address.clone())
        .unwrap_or_else(|| "10.66.66.2:1080".into());
    let control_plane_base_url = file_config
        .as_ref()
        .and_then(|c| c.control_plane.as_ref())
        .and_then(|cp| cp.base_url.clone())
        .or_else(|| env::var("HOST_DAEMON_CONTROL_PLANE_URL").ok());
    let control_plane_sync = control_plane_base_url.map(|base_url| ControlPlaneSyncConfig {
        base_url,
        heartbeat_interval_secs: file_config
            .as_ref()
            .and_then(|c| c.control_plane.as_ref())
            .and_then(|cp| cp.heartbeat_interval_secs)
            .or_else(|| {
                env::var("HOST_DAEMON_HEARTBEAT_INTERVAL_SECS")
                    .ok()
                    .and_then(|value| value.parse::<u64>().ok())
            })
            .unwrap_or(2),
        poll_interval_secs: file_config
            .as_ref()
            .and_then(|c| c.control_plane.as_ref())
            .and_then(|cp| cp.poll_interval_secs)
            .or_else(|| {
                env::var("HOST_DAEMON_COMMAND_POLL_INTERVAL_SECS")
                    .ok()
                    .and_then(|value| value.parse::<u64>().ok())
            })
            .unwrap_or(5),
    });

    let runtime = Arc::new(Mutex::new(RuntimeState {
        health: HealthRecord {
            node_id,
            node_name,
            binary_fingerprint: env::var("HOST_DAEMON_BINARY_FINGERPRINT")
                .unwrap_or_else(|_| "reconstructed".into()),
            readiness_state: RuntimeReadiness::Healthy.to_string(),
            serving: true,
            proxy_status: "running".into(),
            last_public_ip: Some("178.168.186.196".into()),
            active_operator_profile: Some(active_profile),
            active_operator_plmn: Some("25702".into()),
            last_proxy_error: None,
            serving_failure_reason: None,
            degradation_reason_code: None,
            cellular_route_ready: Some(true),
            proxy_bind_ready: Some(true),
            local_serving_ready: Some(true),
            tun0_present: Some(true),
            wg_handshake_recent: Some(true),
        },
        jobs: HashMap::new(),
        ip_pool: vec![
            "178.168.186.196".into(),
            "178.168.186.105".into(),
            "178.168.185.93".into(),
            "178.168.159.211".into(),
        ],
        ip_index: 0,
        current_job: None,
        wireguard_enabled,
        proxy_listen_address,
        proxy_pid: None,
    }));
    let state = AppState {
        admin_token,
        runtime,
    };

    if let Some(sync) = control_plane_sync {
        let runtime_arc = state.runtime.clone();
        tokio::spawn(async move {
            run_control_plane_sync(runtime_arc, sync).await;
        });
    }

    let app = Router::new()
        .route("/v1/health", get(get_health))
        .route("/v1/status", get(get_status))
        .route("/v1/proxy", get(get_proxy))
        .route("/v1/ip/rotate", post(rotate_ip))
        .route("/v1/jobs/{id}", get(get_job))
        .with_state(state);

    let listener = TcpListener::bind(&listen).await?;
    info!("host-daemon listening on {}", listen);
    axum::serve(listener, app).await?;
    Ok(())
}

fn load_file_config(path: Option<&str>) -> anyhow::Result<Option<FileConfig>> {
    if let Some(path) = path {
        let body = fs::read_to_string(path)?;
        let config = serde_json::from_str::<FileConfig>(&body)?;
        Ok(Some(config))
    } else {
        Ok(None)
    }
}

async fn get_health(
    State(state): State<AppState>,
    headers: HeaderMap,
) -> Result<Json<HealthRecord>, ApiError> {
    authorize(&headers, &state.admin_token)?;
    let runtime = state.runtime.lock().await;
    Ok(Json(runtime.health.clone()))
}

async fn get_status(
    State(state): State<AppState>,
    headers: HeaderMap,
) -> Result<Json<RuntimeStatusRecord>, ApiError> {
    authorize(&headers, &state.admin_token)?;
    let runtime = state.runtime.lock().await;
    Ok(Json(RuntimeStatusRecord {
        node_id: runtime.health.node_id.clone(),
        node_name: runtime.health.node_name.clone(),
        current_job: runtime.current_job,
        wireguard_enabled: runtime.wireguard_enabled,
    }))
}

async fn get_proxy(
    State(state): State<AppState>,
    headers: HeaderMap,
) -> Result<Json<ProxyRuntimeRecord>, ApiError> {
    authorize(&headers, &state.admin_token)?;
    let runtime = state.runtime.lock().await;
    Ok(Json(ProxyRuntimeRecord {
        status: runtime.health.proxy_status.clone(),
        listen_address: runtime.proxy_listen_address.clone(),
        pid: runtime.proxy_pid,
    }))
}

async fn rotate_ip(
    State(state): State<AppState>,
    headers: HeaderMap,
    Json(request): Json<RotateRequest>,
) -> Result<Json<RotateAccepted>, ApiError> {
    authorize(&headers, &state.admin_token)?;
    let mut runtime = state.runtime.lock().await;
    if runtime
        .current_job
        .and_then(|id| runtime.jobs.get(&id))
        .is_some_and(|job| job.status == "running")
    {
        return Err(ApiError(
            StatusCode::CONFLICT,
            "another job is already running".into(),
        ));
    }

    let request = normalize_rotate_request(request);
    let job_id = Uuid::new_v4();
    let current_ip = runtime.health.last_public_ip.clone();
    runtime.current_job = Some(job_id);
    runtime.health.readiness_state = RuntimeReadiness::WaitingCellular.to_string();
    runtime.health.serving = false;
    runtime.health.proxy_status = "draining".into();
    runtime.health.degradation_reason_code = Some("rotation_in_progress".into());
    runtime.health.serving_failure_reason = Some("rotation job is in progress".into());
    runtime.health.cellular_route_ready = Some(false);
    runtime.health.local_serving_ready = Some(false);
    runtime.health.proxy_bind_ready = Some(false);
    runtime.health.last_proxy_error = None;
    runtime.jobs.insert(
        job_id,
        JobRecord {
            id: job_id,
            kind: "rotate_ip".into(),
            status: "running".into(),
            old_public_ip: current_ip,
            new_public_ip: None,
            changed: None,
        },
    );

    let runtime_arc = state.runtime.clone();
    tokio::spawn(async move {
        if let Err(err) = execute_rotation(runtime_arc, job_id, request).await {
            warn!("rotation job failed: {err:#}");
        }
    });
    Ok(Json(RotateAccepted {
        job_id,
        accepted: true,
    }))
}

async fn get_job(
    State(state): State<AppState>,
    headers: HeaderMap,
    Path(id): Path<Uuid>,
) -> Result<Json<JobRecord>, ApiError> {
    authorize(&headers, &state.admin_token)?;
    let runtime = state.runtime.lock().await;
    let job = runtime
        .jobs
        .get(&id)
        .cloned()
        .ok_or_else(|| ApiError(StatusCode::NOT_FOUND, "job not found".into()))?;
    Ok(Json(job))
}

async fn execute_rotation(
    runtime_arc: Arc<Mutex<RuntimeState>>,
    job_id: Uuid,
    request: RotateRequest,
) -> anyhow::Result<()> {
    let started = Instant::now();
    sleep(Duration::from_secs(
        if request.strategy == "airplane_bounce" {
            4
        } else {
            2
        },
    ))
    .await;

    let mut runtime = runtime_arc.lock().await;
    let old_ip = runtime
        .jobs
        .get(&job_id)
        .and_then(|job| job.old_public_ip.clone());
    let mut next_index = (runtime.ip_index + 1) % runtime.ip_pool.len();
    if request.require_public_ip_change && runtime.ip_pool.len() > 1 {
        if let Some(old_ip_value) = old_ip.as_deref() {
            for _ in 0..runtime.ip_pool.len() {
                if runtime.ip_pool[next_index] != old_ip_value {
                    break;
                }
                next_index = (next_index + 1) % runtime.ip_pool.len();
            }
        }
    }
    runtime.ip_index = next_index;
    let new_ip = runtime.ip_pool[next_index].clone();

    runtime.health.last_public_ip = Some(new_ip.clone());
    runtime.health.readiness_state = RuntimeReadiness::Healthy.to_string();
    runtime.health.serving = true;
    runtime.health.proxy_status = "running".into();
    runtime.health.degradation_reason_code = None;
    runtime.health.serving_failure_reason = None;
    runtime.health.cellular_route_ready = Some(true);
    runtime.health.local_serving_ready = Some(true);
    runtime.health.proxy_bind_ready = Some(true);
    runtime.health.tun0_present = Some(true);
    runtime.health.wg_handshake_recent = Some(true);
    runtime.current_job = None;

    if let Some(job) = runtime.jobs.get_mut(&job_id) {
        job.status = "succeeded".into();
        job.new_public_ip = Some(new_ip.clone());
        job.changed = Some(job.old_public_ip.as_deref() != Some(new_ip.as_str()));
    }

    info!(
        "rotation finished in {:?}: {:?} -> {}",
        started.elapsed(),
        old_ip,
        new_ip
    );
    Ok(())
}

async fn run_control_plane_sync(
    runtime_arc: Arc<Mutex<RuntimeState>>,
    config: ControlPlaneSyncConfig,
) {
    let client = match reqwest::Client::builder()
        .timeout(Duration::from_secs(5))
        .build()
    {
        Ok(client) => client,
        Err(err) => {
            warn!("control-plane sync disabled: failed to create client: {err}");
            return;
        }
    };

    let mut heartbeat_tick = interval(Duration::from_secs(config.heartbeat_interval_secs.max(1)));
    heartbeat_tick.set_missed_tick_behavior(MissedTickBehavior::Delay);
    let mut poll_tick = interval(Duration::from_secs(config.poll_interval_secs.max(1)));
    poll_tick.set_missed_tick_behavior(MissedTickBehavior::Delay);

    if let Err(err) = send_register(&client, &config.base_url, runtime_arc.clone()).await {
        warn!("control-plane register failed: {err}");
    }

    loop {
        tokio::select! {
            _ = heartbeat_tick.tick() => {
                if let Err(err) = send_heartbeat(&client, &config.base_url, runtime_arc.clone()).await {
                    warn!("control-plane heartbeat failed: {err}");
                }
            }
            _ = poll_tick.tick() => {
                if let Err(err) = poll_and_ack_command(&client, &config.base_url, runtime_arc.clone()).await {
                    warn!("control-plane command poll failed: {err}");
                }
            }
        }
    }
}

async fn send_register(
    client: &reqwest::Client,
    base_url: &str,
    runtime_arc: Arc<Mutex<RuntimeState>>,
) -> anyhow::Result<()> {
    let runtime = runtime_arc.lock().await;
    let body = RegisterDeviceRequest {
        node_id: runtime.health.node_id.clone(),
        node_name: runtime.health.node_name.clone(),
        proxy_status: runtime.health.proxy_status.clone(),
    };
    drop(runtime);

    client
        .post(format!("{base_url}/api/v1/devices/register"))
        .json(&body)
        .send()
        .await?
        .error_for_status()?;
    Ok(())
}

async fn send_heartbeat(
    client: &reqwest::Client,
    base_url: &str,
    runtime_arc: Arc<Mutex<RuntimeState>>,
) -> anyhow::Result<()> {
    let runtime = runtime_arc.lock().await;
    let body = HeartbeatRequest {
        node_id: runtime.health.node_id.clone(),
        node_name: runtime.health.node_name.clone(),
        readiness_state: runtime.health.readiness_state.clone(),
        serving: runtime.health.serving,
        proxy_status: runtime.health.proxy_status.clone(),
        proxy_pid: runtime.proxy_pid,
        last_public_ip: runtime.health.last_public_ip.clone(),
        current_job: runtime.current_job,
        last_proxy_error: runtime.health.last_proxy_error.clone(),
        version: None,
        config_fingerprint: None,
        binary_fingerprint: Some(runtime.health.binary_fingerprint.clone()),
        active_operator_profile: runtime.health.active_operator_profile.clone(),
        active_operator_plmn: runtime.health.active_operator_plmn.clone(),
        cellular_route_ready: runtime.health.cellular_route_ready,
        proxy_bind_ready: runtime.health.proxy_bind_ready,
        local_serving_ready: runtime.health.local_serving_ready,
    };
    drop(runtime);

    client
        .post(format!("{base_url}/api/v1/devices/heartbeat"))
        .json(&body)
        .send()
        .await?
        .error_for_status()?;
    Ok(())
}

async fn poll_and_ack_command(
    client: &reqwest::Client,
    base_url: &str,
    runtime_arc: Arc<Mutex<RuntimeState>>,
) -> anyhow::Result<()> {
    let device_id = {
        let runtime = runtime_arc.lock().await;
        runtime.health.node_id.clone()
    };
    let next: Option<DeviceCommand> = client
        .get(format!(
            "{base_url}/api/v1/devices/{device_id}/commands/next"
        ))
        .send()
        .await?
        .error_for_status()?
        .json()
        .await?;
    let Some(command) = next else {
        return Ok(());
    };

    apply_command(runtime_arc.clone(), &command).await;
    let ack = CommandAckRequest {
        ok: true,
        message: None,
    };
    client
        .post(format!(
            "{base_url}/api/v1/devices/{device_id}/commands/{}/ack",
            command.command_id
        ))
        .json(&ack)
        .send()
        .await?
        .error_for_status()?;
    Ok(())
}

async fn apply_command(runtime_arc: Arc<Mutex<RuntimeState>>, command: &DeviceCommand) {
    let mut runtime = runtime_arc.lock().await;
    runtime.health.readiness_state = match command.desired_state {
        DesiredState::HealthyServing => RuntimeReadiness::Healthy.to_string(),
        DesiredState::DegradedSafe => RuntimeReadiness::WaitingCellular.to_string(),
    };
    runtime.health.serving = matches!(command.desired_state, DesiredState::HealthyServing);
    runtime.health.proxy_status = if runtime.health.serving {
        "running".into()
    } else {
        "draining".into()
    };

    match command.recovery_intent {
        RecoveryIntent::None => {}
        RecoveryIntent::RouteRepair => {
            runtime.health.cellular_route_ready = Some(true);
            runtime.health.local_serving_ready = Some(true);
            runtime.health.proxy_bind_ready = Some(true);
            runtime.health.degradation_reason_code = None;
            runtime.health.serving_failure_reason = None;
        }
        RecoveryIntent::RestartRuntime => {
            runtime.health.proxy_status = "running".into();
            runtime.health.proxy_bind_ready = Some(true);
            runtime.health.local_serving_ready = Some(true);
            runtime.health.last_proxy_error = None;
        }
        RecoveryIntent::RotateRecovery => {
            runtime.health.degradation_reason_code = Some("rotation_in_progress".into());
            runtime.health.serving_failure_reason =
                Some("rotation recovery command accepted".into());
        }
    }
}

fn normalize_rotate_request(request: RotateRequest) -> RotateRequest {
    if request.strategy.is_empty() {
        default_rotate_request()
    } else {
        request
    }
}

fn authorize(headers: &HeaderMap, token: &str) -> Result<(), ApiError> {
    let actual = headers
        .get("authorization")
        .and_then(|v| v.to_str().ok())
        .and_then(|v| v.strip_prefix("Bearer "));
    if actual == Some(token) {
        Ok(())
    } else {
        Err(ApiError(
            StatusCode::UNAUTHORIZED,
            "invalid bearer token".into(),
        ))
    }
}

struct ApiError(StatusCode, String);

impl IntoResponse for ApiError {
    fn into_response(self) -> axum::response::Response {
        (self.0, Json(serde_json::json!({ "error": self.1 }))).into_response()
    }
}
