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
    pub device_token: String,
    pub server_name: Option<String>,
    pub server_addr: Option<std::net::SocketAddr>,
    pub server_cert_der: Option<Vec<u8>>,
    pub heartbeat_interval_secs: u64,
    pub poll_interval_secs: u64,
}

pub async fn run_control_plane_sync(runtime_arc: SharedRuntime, config: ControlPlaneSyncConfig) {
    let mut builder = reqwest::Client::builder().timeout(Duration::from_secs(5));
    if let (Some(server_name), Some(server_addr)) = (&config.server_name, config.server_addr) {
        builder = builder.resolve(server_name, server_addr);
    }
    if let Some(cert_der) = &config.server_cert_der {
        match reqwest::Certificate::from_der(cert_der) {
            Ok(cert) => builder = builder.add_root_certificate(cert),
            Err(err) => {
                warn!("control-plane sync disabled: invalid pinned certificate: {err}");
                return;
            }
        }
    }
    let client = match builder.build() {
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

    if let Err(err) = send_register(&client, &config, runtime_arc.clone()).await {
        warn!("control-plane register failed: {err}");
    }

    loop {
        tokio::select! {
            _ = heartbeat_tick.tick() => {
                if let Err(err) = send_heartbeat(&client, &config, runtime_arc.clone()).await {
                    warn!("control-plane heartbeat failed: {err}");
                }
            }
            _ = poll_tick.tick() => {
                if let Err(err) = poll_and_ack_command(&client, &config, runtime_arc.clone()).await {
                    warn!("control-plane command poll failed: {err}");
                }
            }
        }
    }
}

async fn send_register(
    client: &reqwest::Client,
    config: &ControlPlaneSyncConfig,
    runtime_arc: SharedRuntime,
) -> anyhow::Result<()> {
    let runtime = runtime_arc.lock().await;
    let body = RegisterDeviceRequest {
        node_id: runtime.health.node_id.clone(),
        node_name: runtime.health.node_name.clone(),
        proxy_status: runtime.health.proxy_status.clone(),
        tunnel_owner: runtime.tunnel_owner.clone(),
    };
    drop(runtime);

    client
        .post(format!("{}/api/v1/devices/register", config.base_url))
        .bearer_auth(&config.device_token)
        .json(&body)
        .send()
        .await?
        .error_for_status()?;
    Ok(())
}

async fn send_heartbeat(
    client: &reqwest::Client,
    config: &ControlPlaneSyncConfig,
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
        config_fingerprint: runtime.health.config_fingerprint.clone(),
        binary_fingerprint: Some(runtime.health.binary_fingerprint.clone()),
        active_operator_profile: runtime.health.active_operator_profile.clone(),
        active_operator_plmn: runtime.health.active_operator_plmn.clone(),
        cellular_route_ready: runtime.health.cellular_route_ready,
        proxy_bind_ready: runtime.health.proxy_bind_ready,
        local_serving_ready: runtime.health.local_serving_ready,
        tun0_present: runtime.health.tun0_present,
        wg_handshake_recent: runtime.health.wg_handshake_recent,
        reverse_tunnel_connected: runtime.health.reverse_tunnel_connected,
        reverse_tunnel_last_error: runtime.health.reverse_tunnel_last_error.clone(),
        reverse_tunnel_active_transport: runtime.health.reverse_tunnel_active_transport.clone(),
        reverse_tunnel_freshness: runtime.health.reverse_tunnel_freshness.clone(),
        reverse_tunnel_failover_reason: runtime.health.reverse_tunnel_failover_reason.clone(),
        tunnel_owner: runtime.tunnel_owner.clone(),
    };
    drop(runtime);

    client
        .post(format!("{}/api/v1/devices/heartbeat", config.base_url))
        .bearer_auth(&config.device_token)
        .json(&body)
        .send()
        .await?
        .error_for_status()?;
    Ok(())
}

async fn poll_and_ack_command(
    client: &reqwest::Client,
    config: &ControlPlaneSyncConfig,
    runtime_arc: SharedRuntime,
) -> anyhow::Result<()> {
    let device_id = {
        let runtime = runtime_arc.lock().await;
        runtime.health.node_id.clone()
    };
    let next: Option<DeviceCommand> = client
        .get(format!(
            "{}/api/v1/devices/{device_id}/commands/next",
            config.base_url
        ))
        .bearer_auth(&config.device_token)
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
            "{}/api/v1/devices/{device_id}/commands/{}/ack",
            config.base_url, command.command_id
        ))
        .bearer_auth(&config.device_token)
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
