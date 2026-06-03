use std::process::Command;
use std::time::{Duration, Instant};

use proxy_core::{
    DEFAULT_AIRPLANE_HOLD_SECS, JobRecord, RotateAccepted, RotateRequest, RuntimeReadiness,
    default_rotate_request,
};
use serde::Deserialize;
use tokio::{spawn, time::sleep};
use tracing::{info, warn};
use uuid::Uuid;

use crate::auth::ApiError;
use crate::state::{AppState, SharedRuntime};

pub async fn start_rotation(
    state: &AppState,
    request: RotateRequest,
) -> Result<RotateAccepted, ApiError> {
    let mut runtime = state.runtime.lock().await;
    if runtime
        .current_job
        .and_then(|id| runtime.jobs.get(&id))
        .is_some_and(|job| job.status == "running")
    {
        return Err(ApiError(
            axum::http::StatusCode::CONFLICT,
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
    spawn(async move {
        if let Err(err) = execute_rotation(runtime_arc, job_id, request).await {
            warn!("rotation job failed: {err:#}");
        }
    });

    Ok(RotateAccepted {
        job_id,
        accepted: true,
    })
}

pub async fn execute_rotation(
    runtime_arc: SharedRuntime,
    job_id: Uuid,
    request: RotateRequest,
) -> anyhow::Result<()> {
    let started = Instant::now();
    let (command, observer_urls, old_ip) = {
        let runtime = runtime_arc.lock().await;
        (
            rotation_command(&runtime.rotation_commands, &request),
            runtime.observer_urls.clone(),
            runtime
                .jobs
                .get(&job_id)
                .and_then(|job| job.old_public_ip.clone()),
        )
    };

    let command = command.unwrap_or_else(|| fallback_airplane_command(request.hold_secs));
    let command_output = run_shell_command(&command);
    let new_ip = observe_public_ip(&observer_urls).await;

    let mut runtime = runtime_arc.lock().await;
    let changed = old_ip.as_deref() != new_ip.as_deref();
    let succeeded = command_output.is_ok()
        && new_ip.is_some()
        && (!request.require_public_ip_change || changed);

    if let Some(ip) = new_ip.clone() {
        runtime.health.last_public_ip = Some(ip);
    }
    runtime.health.readiness_state = if succeeded {
        RuntimeReadiness::Healthy.to_string()
    } else {
        RuntimeReadiness::WaitingCellular.to_string()
    };
    runtime.health.serving = succeeded;
    runtime.health.proxy_status = if succeeded {
        "running".into()
    } else {
        "degraded".into()
    };
    runtime.health.degradation_reason_code = if succeeded {
        None
    } else {
        Some("rotation_failed".into())
    };
    runtime.health.serving_failure_reason = if succeeded {
        None
    } else {
        command_output
            .err()
            .map(|err| err.to_string())
            .or_else(|| Some("rotation did not produce the required public IP change".into()))
    };
    runtime.current_job = None;

    if let Some(job) = runtime.jobs.get_mut(&job_id) {
        job.status = if succeeded {
            "succeeded".into()
        } else {
            "failed".into()
        };
        job.new_public_ip = new_ip.clone();
        job.changed = Some(changed);
    }

    info!(
        "rotation finished in {:?}: {:?} -> {:?}",
        started.elapsed(),
        old_ip,
        new_ip
    );
    Ok(())
}

pub fn normalize_rotate_request(mut request: RotateRequest) -> RotateRequest {
    if request.strategy.is_empty() {
        return default_rotate_request();
    }
    if request.strategy == "airplane_bounce" && request.hold_secs.is_none() {
        request.hold_secs = Some(DEFAULT_AIRPLANE_HOLD_SECS);
    }
    request
}

fn rotation_command(
    commands: &crate::state::RotationCommands,
    request: &RotateRequest,
) -> Option<String> {
    match request.strategy.as_str() {
        "data_reconnect" => commands.data_reconnect.clone(),
        "network_mode_bounce" => commands.network_mode_bounce.clone(),
        "ril_bounce" => commands.ril_bounce.clone(),
        "airplane_bounce" => Some(fallback_airplane_command(request.hold_secs)),
        _ => commands.airplane_bounce.clone(),
    }
}

fn fallback_airplane_command(hold_secs: Option<u64>) -> String {
    format!(
        "cmd connectivity airplane-mode enable && sleep {} && cmd connectivity airplane-mode disable",
        hold_secs.unwrap_or(DEFAULT_AIRPLANE_HOLD_SECS)
    )
}

fn run_shell_command(command: &str) -> anyhow::Result<String> {
    let output = Command::new("sh").arg("-c").arg(command).output()?;
    if output.status.success() {
        Ok(String::from_utf8_lossy(&output.stdout).trim().to_string())
    } else {
        anyhow::bail!("{}", String::from_utf8_lossy(&output.stderr).trim())
    }
}

#[derive(Debug, Deserialize)]
struct IpifyResponse {
    ip: Option<String>,
}

async fn observe_public_ip(urls: &[String]) -> Option<String> {
    sleep(Duration::from_secs(2)).await;
    let client = reqwest::Client::builder()
        .timeout(Duration::from_secs(10))
        .build()
        .ok()?;
    for _ in 0..10 {
        for url in urls {
            let Ok(response) = client.get(url).send().await else {
                continue;
            };
            let Ok(response) = response.error_for_status() else {
                continue;
            };
            let Ok(body) = response.text().await else {
                continue;
            };
            if let Ok(parsed) = serde_json::from_str::<IpifyResponse>(&body)
                && let Some(ip) = parsed.ip
            {
                return Some(ip);
            }
            let trimmed = body.trim();
            if !trimmed.is_empty() && trimmed.len() <= 64 {
                return Some(trimmed.to_string());
            }
        }
        sleep(Duration::from_secs(2)).await;
    }
    None
}
