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

    if runtime.jobs.len() >= 100 {
        let to_remove: Vec<Uuid> = runtime.jobs.iter()
            .filter(|(id, job)| job.status != "running" && Some(**id) != runtime.current_job)
            .map(|(id, _)| *id)
            .take(50)
            .collect();
        for id in to_remove {
            runtime.jobs.remove(&id);
        }
    }

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
    let command_output = run_shell_command(&command).await;
    let new_ip = observe_public_ip(&observer_urls).await;

    let command_error = command_output.as_ref().err().map(ToString::to_string);
    let reverse_tunnel_ready = refresh_reverse_tunnel_after_rotation(&runtime_arc).await;
    let mut runtime = runtime_arc.lock().await;
    apply_rotation_result(
        &mut runtime,
        job_id,
        request.require_public_ip_change,
        command_output.is_ok(),
        reverse_tunnel_ready,
        command_error,
        new_ip.clone(),
    );

    info!(
        "rotation finished in {:?}: {:?} -> {:?}",
        started.elapsed(),
        old_ip,
        new_ip
    );
    Ok(())
}

fn apply_rotation_result(
    runtime: &mut crate::state::RuntimeState,
    job_id: Uuid,
    require_public_ip_change: bool,
    command_succeeded: bool,
    reverse_tunnel_ready: bool,
    command_error: Option<String>,
    new_ip: Option<String>,
) {
    let old_ip = runtime
        .jobs
        .get(&job_id)
        .and_then(|job| job.old_public_ip.clone());
    let changed = old_ip.as_deref() != new_ip.as_deref();
    let succeeded = command_succeeded
        && reverse_tunnel_ready
        && new_ip.is_some()
        && (!require_public_ip_change || changed);

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
    runtime.health.cellular_route_ready = Some(succeeded);
    runtime.health.local_serving_ready = Some(succeeded);
    runtime.health.proxy_bind_ready = Some(succeeded);
    runtime.health.degradation_reason_code = if succeeded {
        None
    } else {
        Some("rotation_failed".into())
    };
    runtime.health.serving_failure_reason = if succeeded {
        None
    } else {
        command_error.or_else(|| {
            if reverse_tunnel_ready {
                Some("rotation did not produce the required public IP change".into())
            } else {
                Some("reverse tunnel did not reconnect after rotation".into())
            }
        })
    };
    runtime.current_job = None;

    if let Some(job) = runtime.jobs.get_mut(&job_id) {
        job.status = if succeeded {
            "succeeded".into()
        } else {
            "failed".into()
        };
        job.new_public_ip = new_ip;
        job.changed = Some(changed);
    }
}

async fn refresh_reverse_tunnel_after_rotation(runtime_arc: &SharedRuntime) -> bool {
    let restart_tx = {
        let runtime = runtime_arc.lock().await;
        if runtime.tunnel_owner.as_deref() != Some("first_party_reverse_tunnel") {
            return true;
        }
        runtime.reverse_tunnel_restart.clone()
    };
    let Some(restart_tx) = restart_tx else {
        return false;
    };
    let next_generation = restart_tx.borrow().saturating_add(1);
    if restart_tx.send(next_generation).is_err() {
        return false;
    }

    for _ in 0..20 {
        sleep(Duration::from_secs(1)).await;
        let runtime = runtime_arc.lock().await;
        if runtime
            .reverse_tunnel
            .as_ref()
            .is_some_and(|snapshot| snapshot.connected)
        {
            return true;
        }
    }
    false
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
        "settings put global airplane_mode_on 1 && am broadcast -a android.intent.action.AIRPLANE_MODE --ez state true && sleep {} && settings put global airplane_mode_on 0 && am broadcast -a android.intent.action.AIRPLANE_MODE --ez state false",
        hold_secs.unwrap_or(DEFAULT_AIRPLANE_HOLD_SECS)
    )
}

async fn run_shell_command(command: &str) -> anyhow::Result<String> {
    let command = command.to_string();
    tokio::task::spawn_blocking(move || {
        let output = Command::new("sh").arg("-c").arg(&command).output()?;
        if output.status.success() {
            Ok(String::from_utf8_lossy(&output.stdout).trim().to_string())
        } else {
            anyhow::bail!("{}", String::from_utf8_lossy(&output.stderr).trim())
        }
    })
    .await
    .unwrap_or_else(|_| Err(anyhow::anyhow!("spawn_blocking failed")))
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

#[cfg(test)]
mod tests {
    use std::collections::HashMap;

    use proxy_core::{HealthRecord, JobRecord, RuntimeReadiness};
    use uuid::Uuid;

    use crate::rotation::{apply_rotation_result, fallback_airplane_command};
    use crate::state::{RotationCommands, RuntimeState};

    #[test]
    fn successful_rotation_restores_readiness_flags() {
        let job_id = Uuid::new_v4();
        let mut jobs = HashMap::new();
        jobs.insert(
            job_id,
            JobRecord {
                id: job_id,
                kind: "rotate_ip".into(),
                status: "running".into(),
                old_public_ip: Some("1.1.1.1".into()),
                new_public_ip: None,
                changed: None,
            },
        );
        let mut runtime = RuntimeState::new(
            HealthRecord {
                node_id: "node".into(),
                node_name: "node".into(),
                binary_fingerprint: "fp".into(),
                readiness_state: RuntimeReadiness::WaitingCellular.to_string(),
                serving: false,
                proxy_status: "draining".into(),
                last_public_ip: Some("1.1.1.1".into()),
                active_operator_profile: None,
                active_operator_plmn: None,
                last_proxy_error: None,
                serving_failure_reason: Some("rotation job is in progress".into()),
                degradation_reason_code: Some("rotation_in_progress".into()),
                cellular_route_ready: Some(false),
                proxy_bind_ready: Some(false),
                local_serving_ready: Some(false),
                tun0_present: Some(true),
                wg_handshake_recent: Some(true),
                reverse_tunnel_connected: None,
                reverse_tunnel_last_error: None,
                tunnel_owner: Some("stock_wireguard_bridge".into()),
            },
            true,
            Some("stock_wireguard_bridge".into()),
            "10.66.66.2:1080".into(),
            RotationCommands::default(),
            Vec::new(),
        );
        runtime.jobs = jobs;
        runtime.current_job = Some(job_id);

        apply_rotation_result(
            &mut runtime,
            job_id,
            true,
            true,
            true,
            None,
            Some("2.2.2.2".into()),
        );

        let job = runtime.jobs.get(&job_id).expect("job remains recorded");
        assert_eq!(job.status, "succeeded");
        assert_eq!(job.changed, Some(true));
        assert_eq!(runtime.current_job, None);
        assert_eq!(
            runtime.health.readiness_state,
            RuntimeReadiness::Healthy.to_string()
        );
        assert!(runtime.health.serving);
        assert_eq!(runtime.health.proxy_status, "running");
        assert_eq!(runtime.health.cellular_route_ready, Some(true));
        assert_eq!(runtime.health.proxy_bind_ready, Some(true));
        assert_eq!(runtime.health.local_serving_ready, Some(true));
        assert_eq!(runtime.health.degradation_reason_code, None);
        assert_eq!(runtime.health.serving_failure_reason, None);
    }

    #[test]
    fn fallback_airplane_command_uses_settings_broadcast_path() {
        let command = fallback_airplane_command(Some(5));
        assert!(command.contains("settings put global airplane_mode_on 1"));
        assert!(command.contains("android.intent.action.AIRPLANE_MODE --ez state true"));
        assert!(command.contains("sleep 5"));
        assert!(command.contains("settings put global airplane_mode_on 0"));
        assert!(command.contains("android.intent.action.AIRPLANE_MODE --ez state false"));
    }
}
