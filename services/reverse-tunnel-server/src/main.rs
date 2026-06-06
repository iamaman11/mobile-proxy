mod cli;

use clap::Parser;
use reverse_tunnel::{
    ReverseTunnelServerConfig, ReverseTunnelServerState, TunnelTransport, decode_der_base64,
    run_quic_server, run_quic_tcp_forward_listener,
};
use tokio::net::TcpListener;
use tokio::sync::watch;
use tokio::task::JoinSet;
use tracing::info;

use crate::cli::Cli;

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    tracing_subscriber::fmt::init();
    let cli = Cli::parse();
    let bind_addr = cli.listen.parse()?;
    let server_config = ReverseTunnelServerConfig {
        auth_token: cli.auth_token,
        transport: TunnelTransport::Quic {
            server_name: cli.server_name,
            server_cert_der: decode_der_base64(&cli.cert_der_b64)?,
            server_key_der: Some(decode_der_base64(&cli.key_der_b64)?),
        },
    };
    let state = ReverseTunnelServerState::default();
    let (_shutdown_tx, shutdown_rx) = watch::channel(false);
    let public_proxy_listens: Vec<_> = cli
        .public_proxy_listen
        .split(',')
        .map(str::trim)
        .filter(|listen| !listen.is_empty())
        .map(str::to_string)
        .collect();
    let mut public_proxy_listeners = Vec::new();
    for listen in &public_proxy_listens {
        public_proxy_listeners.push((listen.clone(), TcpListener::bind(listen).await?));
    }
    info!(
        "reverse-tunnel-server listening on {}; public proxy listeners on {}",
        cli.listen,
        public_proxy_listens.join(",")
    );
    let mut tasks = JoinSet::new();
    tasks.spawn(run_quic_server(
        bind_addr,
        server_config,
        state.clone(),
        shutdown_rx.clone(),
    ));
    for (_listen, listener) in public_proxy_listeners {
        tasks.spawn(run_quic_tcp_forward_listener(
            listener,
            state.clone(),
            cli.target_node_id.clone(),
            shutdown_rx.clone(),
        ));
    }
    while let Some(result) = tasks.join_next().await {
        result??;
    }
    Ok(())
}
