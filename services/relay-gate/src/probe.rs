use std::net::SocketAddr;

use proxy_core::DeviceRecord;
use tokio::net::TcpStream;
use tracing::warn;

use crate::cli::Cli;

pub async fn evaluate_ready(client: &reqwest::Client, cli: &Cli) -> bool {
    let response = match client
        .get(format!("{}/api/v1/devices", cli.control_plane))
        .bearer_auth(&cli.admin_token)
        .send()
        .await
    {
        Ok(response) => response,
        Err(_) => {
            warn!("control-plane device fetch failed");
            return false;
        }
    };
    let devices: Vec<DeviceRecord> = match response.json().await {
        Ok(devices) => devices,
        Err(_) => {
            warn!("control-plane device decode failed");
            return false;
        }
    };
    if devices.is_empty() {
        warn!("control-plane returned no devices");
        return false;
    }
    let device_ready = devices
        .iter()
        .find(|d| d.node_id == cli.device_id)
        .is_some_and(is_device_ready);
    if !device_ready {
        return false;
    }
    let upstream: SocketAddr = match cli.upstream.parse() {
        Ok(addr) => addr,
        Err(_) => return false,
    };
    TcpStream::connect(upstream).await.is_ok()
}

fn is_device_ready(device: &DeviceRecord) -> bool {
    device.serving
        && device.readiness_state == "healthy"
        && device.degradation_reason_code.is_none()
}

#[cfg(test)]
mod tests {
    use super::is_device_ready;
    use proxy_core::DeviceRecord;

    fn sample_device() -> DeviceRecord {
        DeviceRecord {
            node_id: "node-1".into(),
            node_name: "node".into(),
            readiness_state: "healthy".into(),
            serving: true,
            proxy_status: "running".into(),
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
            cellular_route_ready: Some(true),
            proxy_bind_ready: Some(true),
            local_serving_ready: Some(true),
            tun0_present: Some(true),
            wg_handshake_recent: Some(true),
            reverse_tunnel_connected: None,
            reverse_tunnel_last_error: None,
            tunnel_owner: Some("stock_wireguard_bridge".into()),
            last_heartbeat_at: Some("1".into()),
            availability: "ready".into(),
            degradation_reason_code: None,
            serving_failure_reason: None,
            desired_state: None,
            recovery_intent: None,
            last_event_at: None,
        }
    }

    #[test]
    fn device_must_be_healthy_and_serving() {
        let ready = sample_device();
        assert!(is_device_ready(&ready));

        let mut not_serving = sample_device();
        not_serving.serving = false;
        assert!(!is_device_ready(&not_serving));

        let mut not_healthy = sample_device();
        not_healthy.readiness_state = "waiting_wireguard".into();
        assert!(!is_device_ready(&not_healthy));
    }
}
