mod api;
mod auth;
mod cli;
mod config;
mod control_plane;
mod health;
mod reverse_tunnel;
mod rotation;
mod state;

use std::sync::Arc;

use clap::Parser;
use tokio::net::TcpListener;
use tokio::sync::Mutex;
use tracing::info;

use crate::api::router;
use crate::cli::Cli;
use crate::config::load_runtime_config;
use crate::control_plane::run_control_plane_sync;
use crate::health::run_health_probe;
use crate::reverse_tunnel::spawn_reverse_tunnel;
use crate::state::AppState;

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    tracing_subscriber::fmt::init();
    let cli = Cli::parse();
    let loaded = load_runtime_config(&cli)?;
    let runtime = Arc::new(Mutex::new(loaded.runtime_state));
    let state = AppState {
        admin_token: loaded.admin_token,
        runtime,
    };

    if let Some(sync) = loaded.control_plane_sync {
        let runtime_arc = state.runtime.clone();
        tokio::spawn(async move {
            run_control_plane_sync(runtime_arc, sync).await;
        });
    }
    if let Some(reverse_tunnel) = loaded.reverse_tunnel {
        spawn_reverse_tunnel(reverse_tunnel);
    }
    {
        let runtime_arc = state.runtime.clone();
        let probe = loaded.probe;
        tokio::spawn(async move {
            run_health_probe(runtime_arc, probe).await;
        });
    }

    let app = router(state);
    let listener = TcpListener::bind(&loaded.listen).await?;
    info!("host-daemon listening on {}", loaded.listen);
    axum::serve(listener, app).await?;
    Ok(())
}
