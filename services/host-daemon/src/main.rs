use std::{
    collections::HashMap,
    env,
    fs,
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
use proxy_core::{HealthRecord, JobRecord, RotateAccepted, RotateRequest, default_rotate_request};
use serde::Deserialize;
use tokio::{net::TcpListener, sync::Mutex, time::sleep};
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
}

#[derive(Debug, Deserialize, Clone)]
struct FileConfig {
    node_id: Option<String>,
    node_name: Option<String>,
    listen: Option<String>,
    admin_token: Option<String>,
    operator_profiles: Option<FileOperatorProfiles>,
}

#[derive(Debug, Deserialize, Clone)]
struct FileOperatorProfiles {
    default_profile: Option<String>,
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
    let runtime = Arc::new(Mutex::new(RuntimeState {
        health: HealthRecord {
            node_id,
            node_name,
            binary_fingerprint: env::var("HOST_DAEMON_BINARY_FINGERPRINT")
                .unwrap_or_else(|_| "reconstructed".into()),
            readiness_state: "healthy".into(),
            serving: true,
            proxy_status: "running".into(),
            last_public_ip: Some("178.168.186.196".into()),
            active_operator_profile: Some(active_profile),
            active_operator_plmn: Some("25702".into()),
        },
        jobs: HashMap::new(),
        ip_pool: vec![
            "178.168.186.196".into(),
            "178.168.186.105".into(),
            "178.168.185.93".into(),
            "178.168.159.211".into(),
        ],
        ip_index: 0,
    }));
    let state = AppState {
        admin_token,
        runtime,
    };

    let app = Router::new()
        .route("/v1/health", get(get_health))
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

async fn rotate_ip(
    State(state): State<AppState>,
    headers: HeaderMap,
    Json(request): Json<RotateRequest>,
) -> Result<Json<RotateAccepted>, ApiError> {
    authorize(&headers, &state.admin_token)?;
    let mut runtime = state.runtime.lock().await;
    let request = normalize_rotate_request(request);
    let job_id = Uuid::new_v4();
    let current_ip = runtime.health.last_public_ip.clone();
    runtime.health.readiness_state = "waiting_cellular".into();
    runtime.health.serving = false;
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
        .and_then(|j| j.old_public_ip.clone());
    runtime.ip_index = (runtime.ip_index + 1) % runtime.ip_pool.len();
    let new_ip = runtime.ip_pool[runtime.ip_index].clone();
    runtime.health.last_public_ip = Some(new_ip.clone());
    runtime.health.readiness_state = "healthy".into();
    runtime.health.serving = true;
    runtime.health.proxy_status = "running".into();
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
