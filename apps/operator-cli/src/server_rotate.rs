use std::time::{Duration, Instant};

use anyhow::{Context, Result, bail};
use base64::{Engine as _, engine::general_purpose::STANDARD};
use proxy_core::DeviceRecord;
use serde::{Deserialize, Serialize};
use tokio::time::sleep;
use uuid::Uuid;

use crate::cli::{RotateServerArgs, StatusFormat};

#[derive(Debug, Serialize)]
struct ServerRotationResult {
    success: bool,
    command_id: String,
    device_id: String,
    old_ip: String,
    new_ip: String,
    elapsed_secs: u64,
    readiness: String,
    serving: bool,
    publicly_serving: bool,
    tunnel_owner: Option<String>,
    active_transport: Option<String>,
    transport_freshness: Option<String>,
}

#[derive(Debug, Deserialize)]
struct RotationAccepted {
    command_id: String,
}

pub async fn run(args: &RotateServerArgs) -> Result<()> {
    let client = build_client(args)?;
    let old = fetch_device(&client, args).await?;
    let old_ip = old
        .last_public_ip
        .clone()
        .context("control plane does not report the current public IP")?;
    let command = issue_rotation(&client, args).await?;

    if args.format == StatusFormat::Summary {
        eprintln!(
            "rotation command {} accepted by server; old_ip={old_ip}",
            command.command_id
        );
    }

    let started = Instant::now();
    let timeout = Duration::from_secs(u64::from(args.timeout_secs.max(1)));
    let poll = Duration::from_secs(args.poll_secs.max(1));
    let final_device = loop {
        if started.elapsed() >= timeout {
            bail!(
                "server rotation timed out after {}s; old_ip={old_ip}",
                args.timeout_secs
            );
        }
        sleep(poll).await;
        match fetch_device(&client, args).await {
            Ok(device) if rotation_complete(&device, &old_ip) => break device,
            Ok(_) => {}
            Err(error) => {
                eprintln!("control-plane status temporarily unavailable: {error:#}");
            }
        }
    };

    let new_ip = final_device
        .last_public_ip
        .clone()
        .context("rotation completed without a public IP")?;
    let result = ServerRotationResult {
        success: true,
        command_id: command.command_id.to_string(),
        device_id: args.device_id.clone(),
        old_ip,
        new_ip,
        elapsed_secs: started.elapsed().as_secs(),
        readiness: final_device.readiness_state,
        serving: final_device.serving,
        publicly_serving: final_device.publicly_serving,
        tunnel_owner: final_device.tunnel_owner,
        active_transport: final_device.reverse_tunnel_active_transport,
        transport_freshness: final_device.reverse_tunnel_freshness,
    };
    match args.format {
        StatusFormat::Json => println!("{}", serde_json::to_string_pretty(&result)?),
        StatusFormat::Summary => println!(
            "IP changed: {} -> {} in {}s; readiness={}; serving={}; publicly_serving={}; transport={}",
            result.old_ip,
            result.new_ip,
            result.elapsed_secs,
            result.readiness,
            result.serving,
            result.publicly_serving,
            result.active_transport.as_deref().unwrap_or("unknown")
        ),
    }
    Ok(())
}

fn build_client(args: &RotateServerArgs) -> Result<reqwest::Client> {
    let cert_der = STANDARD
        .decode(args.control_plane_cert_der_b64.trim())
        .context("invalid base64 in pinned control-plane certificate")?;
    let cert = reqwest::Certificate::from_der(&cert_der)
        .context("invalid pinned control-plane DER certificate")?;
    reqwest::Client::builder()
        .timeout(Duration::from_secs(10))
        .resolve(&args.control_plane_name, args.control_plane_addr)
        .add_root_certificate(cert)
        .build()
        .context("failed to build pinned control-plane client")
}

async fn fetch_device(client: &reqwest::Client, args: &RotateServerArgs) -> Result<DeviceRecord> {
    client
        .get(format!(
            "{}/api/v1/rotation/devices/{}",
            args.control_plane_url.trim_end_matches('/'),
            args.device_id
        ))
        .bearer_auth(&args.rotation_token)
        .send()
        .await
        .context("control-plane request failed")?
        .error_for_status()
        .context("control plane rejected status request")?
        .json()
        .await
        .context("invalid control-plane status response")
}

async fn issue_rotation(
    client: &reqwest::Client,
    args: &RotateServerArgs,
) -> Result<RotationAccepted> {
    let idempotency_key = format!("remote-ip-{}", Uuid::new_v4());
    let url = format!(
        "{}/api/v1/rotation/devices/{}",
        args.control_plane_url.trim_end_matches('/'),
        args.device_id
    );
    let mut last_error = None;
    for attempt in 1..=3 {
        match client
            .post(&url)
            .bearer_auth(&args.rotation_token)
            .header("idempotency-key", &idempotency_key)
            .send()
            .await
        {
            Ok(response) if response.status().is_success() => {
                return response
                    .json()
                    .await
                    .context("invalid rotation command response");
            }
            Ok(response) if response.status().is_server_error() && attempt < 3 => {
                last_error = Some(anyhow::anyhow!(
                    "control plane temporarily returned {}",
                    response.status()
                ));
            }
            Ok(response) => {
                return Err(response
                    .error_for_status()
                    .expect_err("non-success response must produce an error"))
                .context("control plane rejected rotation command");
            }
            Err(error) if attempt < 3 => last_error = Some(error.into()),
            Err(error) => return Err(error).context("failed to send rotation command"),
        }
        sleep(Duration::from_secs(attempt)).await;
    }
    Err(last_error.unwrap_or_else(|| anyhow::anyhow!("rotation request failed")))
}

fn rotation_complete(device: &DeviceRecord, old_ip: &str) -> bool {
    device.current_job.is_none()
        && device.serving
        && device.publicly_serving
        && device.readiness_state == "healthy"
        && device.reverse_tunnel_freshness.as_deref() == Some("fresh")
        && device
            .last_public_ip
            .as_deref()
            .is_some_and(|ip| ip != old_ip)
}

#[cfg(test)]
mod tests {
    use super::rotation_complete;
    use proxy_core::DeviceRecord;
    use uuid::Uuid;

    fn device(ip: &str) -> DeviceRecord {
        serde_json::from_value(serde_json::json!({
            "node_id": "phone",
            "node_name": "phone",
            "readiness_state": "healthy",
            "serving": true,
            "proxy_status": "running",
            "proxy_pid": null,
            "last_public_ip": ip,
            "current_job": null,
            "last_proxy_error": null,
            "version": null,
            "config_fingerprint": null,
            "binary_fingerprint": null,
            "active_operator_profile": "a1-by",
            "active_operator_plmn": "25701",
            "publicly_serving": true,
            "public_probe_error": null,
            "public_probe_at": null,
            "cellular_route_ready": true,
            "proxy_bind_ready": true,
            "local_serving_ready": true,
            "tun0_present": null,
            "wg_handshake_recent": null,
            "reverse_tunnel_connected": true,
            "reverse_tunnel_last_error": null,
            "reverse_tunnel_active_transport": "quic",
            "reverse_tunnel_freshness": "fresh",
            "reverse_tunnel_failover_reason": null,
            "tunnel_owner": "first_party_reverse_tunnel",
            "last_heartbeat_at": null,
            "availability": "online",
            "degradation_reason_code": null,
            "serving_failure_reason": null,
            "desired_state": "healthy_serving",
            "recovery_intent": "rotate_recovery",
            "last_event_at": null
        }))
        .unwrap()
    }

    #[test]
    fn completion_requires_a_new_ip_and_healthy_serving_runtime() {
        let old = device("198.51.100.1");
        assert!(!rotation_complete(&old, "198.51.100.1"));

        let changed = device("198.51.100.2");
        assert!(rotation_complete(&changed, "198.51.100.1"));

        let mut busy = changed.clone();
        busy.current_job = Some(Uuid::new_v4());
        assert!(!rotation_complete(&busy, "198.51.100.1"));

        let mut unavailable = changed;
        unavailable.serving = false;
        assert!(!rotation_complete(&unavailable, "198.51.100.1"));

        let mut public_probe_failed = device("198.51.100.2");
        public_probe_failed.publicly_serving = false;
        assert!(!rotation_complete(&public_probe_failed, "198.51.100.1"));

        let mut stale_tunnel = device("198.51.100.2");
        stale_tunnel.reverse_tunnel_freshness = Some("stale".into());
        assert!(!rotation_complete(&stale_tunnel, "198.51.100.1"));
    }
}
