use std::time::Duration;

use proxy_core::{
    CommandAckRequest, DesiredState, DeviceCommand, HeartbeatRequest, RecoveryIntent,
    RegisterDeviceRequest, RuntimeReadiness,
};
use tokio::time::{MissedTickBehavior, interval};
use tracing::warn;

use crate::state::SharedRuntime;

#[derive(Debug, Clone)]
pub struct ControlPlaneSyncConfig {
    pub base_url: String,
    pub heartbeat_interval_secs: u64,
    pub poll_interval_secs: u64,
}

pub async fn run_control_plane_sync(runtime_arc: SharedRuntime, config: ControlPlaneSyncConfig) {
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
    runtime_arc: SharedRuntime,
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
    runtime_arc: SharedRuntime,
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
    runtime_arc: SharedRuntime,
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

async fn apply_command(runtime_arc: SharedRuntime, command: &DeviceCommand) {
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
