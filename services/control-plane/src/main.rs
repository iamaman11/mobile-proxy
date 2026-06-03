mod cli;
mod projection;
mod routes;
mod state;

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
    let app = router(AppState::new());
    let listener = TcpListener::bind(&cli.listen).await?;
    info!("control-plane listening on {}", cli.listen);
    axum::serve(listener, app).await?;
    Ok(())
}
