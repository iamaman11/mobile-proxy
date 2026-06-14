use anyhow::{Context, Result};
use proxy_core::{HealthRecord, JobRecord, RotateAccepted, RotateRequest};
use reqwest::header::{AUTHORIZATION, CONTENT_TYPE, HeaderMap, HeaderValue};
use tokio::time::{Duration, sleep};
use uuid::Uuid;

pub async fn issue_rotation(
    client: &reqwest::Client,
    api: &str,
    token: &str,
    request: &RotateRequest,
) -> Result<RotateAccepted> {
    Ok(client
        .post(format!("{}/v1/ip/rotate", api))
        .headers(auth_headers(token)?)
        .json(request)
        .send()
        .await?
        .error_for_status()?
        .json()
        .await?)
}

pub async fn wait_for_rotation(
    client: &reqwest::Client,
    api: &str,
    token: &str,
    job_id: Uuid,
    poll_secs: u64,
) -> Result<(JobRecord, HealthRecord)> {
    let started = std::time::Instant::now();
    let max_wait = Duration::from_secs(300);

    loop {
        if started.elapsed() > max_wait {
            anyhow::bail!("timeout waiting for rotation job {}", job_id);
        }

        let job: JobRecord = client
            .get(format!("{}/v1/jobs/{}", api, job_id))
            .headers(auth_headers(token)?)
            .send()
            .await?
            .error_for_status()?
            .json()
            .await?;
        if job.status != "running" {
            let health = fetch_health(client, api, token).await?;
            return Ok((job, health));
        }
        println!(
            "status={} old={:?} new={:?} changed={:?}",
            job.status, job.old_public_ip, job.new_public_ip, job.changed
        );
        sleep(Duration::from_secs(poll_secs.max(1))).await;
    }
}

pub async fn fetch_health(
    client: &reqwest::Client,
    api: &str,
    token: &str,
) -> Result<HealthRecord> {
    Ok(client
        .get(format!("{}/v1/health", api))
        .headers(auth_headers(token)?)
        .send()
        .await?
        .error_for_status()?
        .json()
        .await?)
}

fn auth_headers(token: &str) -> Result<HeaderMap> {
    let mut headers = HeaderMap::new();
    headers.insert(
        AUTHORIZATION,
        HeaderValue::from_str(&format!("Bearer {token}")).context("invalid bearer token")?,
    );
    headers.insert(CONTENT_TYPE, HeaderValue::from_static("application/json"));
    Ok(headers)
}
