use std::{net::SocketAddr, time::Duration};

use anyhow::Context;
use clap::Parser;
use proxy_core::{DeviceRecord, PublicProbeReport};
use tokio::{net::TcpStream, time::sleep};
use tracing::{info, warn};

#[derive(Parser, Debug)]
#[command(name = "relay-gate")]
struct Cli {
    #[arg(
        long,
        env = "CONTROL_PLANE_URL",
        default_value = "http://127.0.0.1:8080"
    )]
    control_plane: String,
    #[arg(long, env = "RELAY_GATE_DEVICE_ID", default_value = proxy_core::DEVICE_ID)]
    device_id: String,
    #[arg(long, env = "RELAY_GATE_UPSTREAM", default_value = "10.66.66.2:1080")]
    upstream: String,
    #[arg(long, default_value_t = false)]
    once: bool,
}

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    tracing_subscriber::fmt::init();
    let cli = Cli::parse();
    let client = reqwest::Client::builder()
        .timeout(Duration::from_secs(10))
        .build()
        .context("failed to build relay-gate client")?;

    loop {
        let ready = evaluate_ready(&client, &cli).await;
        let report = PublicProbeReport {
            publicly_serving: ready,
            public_probe_error: if ready {
                None
            } else {
                Some("backend probe failed".into())
            },
            public_probe_at: format!("{:?}", std::time::SystemTime::now()),
        };
        let _ = client
            .post(format!(
                "{}/api/v1/devices/{}/public-probe",
                cli.control_plane, cli.device_id
            ))
            .json(&report)
            .send()
            .await;
        info!("relay-gate ready={ready}");
        if cli.once {
            break;
        }
        sleep(Duration::from_secs(2)).await;
    }

    Ok(())
}

async fn evaluate_ready(client: &reqwest::Client, cli: &Cli) -> bool {
    let response = match client
        .get(format!("{}/api/v1/devices", cli.control_plane))
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
        warn!("control-plane device fetch failed");
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
    device.serving && device.readiness_state == "healthy"
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
            availability: "degraded".into(),
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
