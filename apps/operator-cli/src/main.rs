use anyhow::{Context, Result};
use clap::{Parser, Subcommand};
use proxy_core::{
    HealthRecord, JobRecord, LOCAL_API, RotateAccepted, default_rotate_request, proxy_endpoints,
};
use reqwest::header::{AUTHORIZATION, CONTENT_TYPE, HeaderMap, HeaderValue};
use std::env;
use std::time::Duration;
use tokio::time::sleep;

#[derive(Parser)]
#[command(name = "operator-cli")]
#[command(about = "Rust-first operator client for the mobile relay")]
struct Cli {
    #[arg(long, default_value = LOCAL_API)]
    api: String,
    #[arg(long)]
    token: Option<String>,
    #[command(subcommand)]
    command: Command,
}

#[derive(Subcommand)]
enum Command {
    Status,
    Proxy,
    Rotate,
}

#[tokio::main]
async fn main() -> Result<()> {
    let cli = Cli::parse();
    let token = cli
        .token
        .or_else(|| env::var("MOBILE_PROXY_ADMIN_TOKEN").ok())
        .context("missing token: pass --token or set MOBILE_PROXY_ADMIN_TOKEN")?;
    let client = reqwest::Client::builder()
        .timeout(Duration::from_secs(15))
        .build()
        .context("failed to build HTTP client")?;

    match cli.command {
        Command::Status => {
            let health: HealthRecord = client
                .get(format!("{}/v1/health", cli.api))
                .headers(auth_headers(&token)?)
                .send()
                .await?
                .error_for_status()?
                .json()
                .await?;
            println!("{}", serde_json::to_string_pretty(&health)?);
        }
        Command::Proxy => {
            println!("{}", serde_json::to_string_pretty(&proxy_endpoints())?);
        }
        Command::Rotate => {
            let accepted: RotateAccepted = client
                .post(format!("{}/v1/ip/rotate", cli.api))
                .headers(auth_headers(&token)?)
                .json(&default_rotate_request())
                .send()
                .await?
                .error_for_status()?
                .json()
                .await?;
            println!("job accepted: {}", accepted.job_id);
            loop {
                let job: JobRecord = client
                    .get(format!("{}/v1/jobs/{}", cli.api, accepted.job_id))
                    .headers(auth_headers(&token)?)
                    .send()
                    .await?
                    .error_for_status()?
                    .json()
                    .await?;
                println!(
                    "status={} old={:?} new={:?} changed={:?}",
                    job.status, job.old_public_ip, job.new_public_ip, job.changed
                );
                if job.status != "running" {
                    println!("{}", serde_json::to_string_pretty(&job)?);
                    break;
                }
                sleep(Duration::from_secs(2)).await;
            }
        }
    }

    Ok(())
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
