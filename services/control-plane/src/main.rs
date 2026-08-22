mod auth;
mod cli;
mod health;
mod projection;
mod request_context;
mod routes;
mod state;
mod state_sqlite_backend;

use crate::auth::AuthConfig;
use crate::cli::Cli;
use crate::health::router as health_router;
use crate::routes::router;
use crate::state::AppState;
use clap::Parser;
use tokio::net::TcpListener;
use tracing::info;

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    tracing_subscriber::fmt::init();
    let cli = Cli::parse();
    let auth = AuthConfig::new(cli.admin_token, cli.device_token, cli.ui_token)?;
    let state_path = cli.state_path.clone();
    let app = router(AppState::load(cli.state_path).await?, auth).merge(health_router(state_path));
    let listener = TcpListener::bind(&cli.listen).await?;
    info!("control-plane listening on {}", cli.listen);
    axum::serve(listener, app).await?;
    Ok(())
}
