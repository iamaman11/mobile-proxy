mod auth;
mod cli;
mod fingerprint_migration;
mod projection;
mod request_context;
mod routes;
mod state;
mod state_sqlite_backend;

use crate::auth::AuthConfig;
use crate::cli::Cli;
use crate::routes::router;
use crate::state::AppState;
use clap::Parser;
use tokio::net::TcpListener;
use tracing::info;

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    tracing_subscriber::fmt::init();
    let cli = Cli::parse();
    let auth = AuthConfig::new(cli.admin_token, cli.device_token)?;
    let app = router(
        AppState::load_with_backend(cli.state_path, cli.state_backend).await?,
        auth,
    );
    let listener = TcpListener::bind(&cli.listen).await?;
    info!("control-plane listening on {}", cli.listen);
    axum::serve(listener, app).await?;
    Ok(())
}
