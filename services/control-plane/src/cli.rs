use clap::Parser;
use std::path::PathBuf;

#[derive(Parser, Debug)]
#[command(name = "control-plane")]
#[command(about = "Reconstructed registry and public probe service")]
pub struct Cli {
    #[arg(long, env = "CONTROL_PLANE_LISTEN", default_value = "127.0.0.1:8080")]
    pub listen: String,
    #[arg(long, env = "CONTROL_PLANE_ADMIN_TOKEN", hide_env_values = true)]
    pub admin_token: String,
    #[arg(long, env = "CONTROL_PLANE_DEVICE_TOKEN", hide_env_values = true)]
    pub device_token: String,
    #[arg(
        long,
        env = "CONTROL_PLANE_STATE_PATH",
        default_value = "/var/lib/mobile-relaycontrolpoint/control-plane-state.json"
    )]
    pub state_path: PathBuf,
}
