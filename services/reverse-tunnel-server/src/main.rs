mod cli;

use clap::Parser;
use reverse_tunnel::{ReverseTunnelServerConfig, ReverseTunnelServerState, run_server};
use tokio::net::TcpListener;
use tokio::sync::watch;
use tracing::info;

use crate::cli::Cli;

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    tracing_subscriber::fmt::init();
    let cli = Cli::parse();
    let listener = TcpListener::bind(&cli.listen).await?;
    let server_config = ReverseTunnelServerConfig {
        auth_token: cli.auth_token,
    };
    let state = ReverseTunnelServerState::default();
    let (_shutdown_tx, shutdown_rx) = watch::channel(false);
    info!("reverse-tunnel-server listening on {}", cli.listen);
    run_server(listener, server_config, state, shutdown_rx).await
}
