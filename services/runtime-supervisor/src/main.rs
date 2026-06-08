mod android;
mod cli;
mod config;
mod health;
mod process;

use std::time::Duration;

use anyhow::{Context, Result};
use clap::Parser;
use tokio::time::sleep;
use tracing::warn;

use crate::cli::Cli;
use crate::config::load_config;
use crate::health::{
    SupervisorState, fetch_health, reconcile_health, reconcile_startup_cellular_bootstrap,
    reconcile_wireguard,
};
use crate::process::{RuntimeChildren, cleanup_stale_runtime_processes};

#[tokio::main]
async fn main() -> Result<()> {
    tracing_subscriber::fmt::init();
    let config = load_config(Cli::parse())?;
    let client = reqwest::Client::builder()
        .timeout(Duration::from_secs(5))
        .build()
        .context("failed to build HTTP client")?;
    let mut children = RuntimeChildren::new();
    let mut state = SupervisorState::new();

    cleanup_stale_runtime_processes();
    reconcile_startup_cellular_bootstrap(&config, &mut state);

    loop {
        children.ensure(&config)?;
        reconcile_wireguard(&config);

        match fetch_health(&client, &config).await {
            Ok(health) => {
                if let Err(err) = reconcile_health(&config, &mut state, &health) {
                    warn!("runtime health reconciliation failed: {err:#}");
                }
            }
            Err(err) => warn!("host-daemon health unavailable: {err:#}"),
        }

        if config.once {
            break;
        }
        sleep(Duration::from_secs(config.poll_secs.max(1))).await;
    }

    Ok(())
}
