use clap::Parser;

const DEFAULT_RELAY_GATE_UPSTREAM: &str = "127.0.0.1:1080";

#[derive(Parser, Debug)]
#[command(name = "relay-gate")]
pub struct Cli {
    #[arg(
        long,
        env = "CONTROL_PLANE_URL",
        default_value = "http://127.0.0.1:8080"
    )]
    pub control_plane: String,
    #[arg(long, env = "CONTROL_PLANE_ADMIN_TOKEN", hide_env_values = true)]
    pub admin_token: String,
    #[arg(long, env = "RELAY_GATE_DEVICE_ID", default_value = proxy_core::DEVICE_ID)]
    pub device_id: String,
    #[arg(
        long,
        env = "RELAY_GATE_UPSTREAM",
        default_value = DEFAULT_RELAY_GATE_UPSTREAM
    )]
    pub upstream: String,
    #[arg(long, default_value_t = false)]
    pub once: bool,
}

#[cfg(test)]
mod tests {
    use clap::Parser;

    use super::{Cli, DEFAULT_RELAY_GATE_UPSTREAM};

    #[test]
    fn default_upstream_targets_public_loopback_listener() {
        let cli = Cli::parse_from(["relay-gate", "--admin-token", "test-token"]);
        assert_eq!(cli.upstream, DEFAULT_RELAY_GATE_UPSTREAM);
    }
}
