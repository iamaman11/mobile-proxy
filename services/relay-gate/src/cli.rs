use clap::Parser;

#[derive(Parser, Debug)]
#[command(name = "relay-gate")]
pub struct Cli {
    #[arg(
        long,
        env = "CONTROL_PLANE_URL",
        default_value = "http://127.0.0.1:8080"
    )]
    pub control_plane: String,
    #[arg(long, env = "RELAY_GATE_DEVICE_ID", default_value = proxy_core::DEVICE_ID)]
    pub device_id: String,
    #[arg(long, env = "RELAY_GATE_UPSTREAM", default_value = "10.66.66.2:1080")]
    pub upstream: String,
    #[arg(long, default_value_t = false)]
    pub once: bool,
}
