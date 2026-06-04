mod cli;
mod probe;
mod report;

use std::time::Duration;

use anyhow::Context;
use clap::Parser;
use tokio::time::sleep;
use tracing::info;

use crate::cli::Cli;
use crate::probe::evaluate_ready;
use crate::report::report_ready;

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
        report_ready(&client, &cli, ready).await;
        info!("relay-gate ready={ready}");
        if cli.once {
            break;
        }
        sleep(Duration::from_secs(2)).await;
    }

    Ok(())
}
