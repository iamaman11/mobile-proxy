use proxy_core::PublicProbeReport;

use crate::cli::Cli;

pub async fn report_ready(client: &reqwest::Client, cli: &Cli, ready: bool) {
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
        .bearer_auth(&cli.admin_token)
        .json(&report)
        .send()
        .await;
}
