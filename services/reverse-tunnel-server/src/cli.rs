use clap::Parser;

#[derive(Parser, Debug)]
#[command(name = "reverse-tunnel-server")]
#[command(about = "VM-side first-party reverse tunnel ingress")]
pub struct Cli {
    #[arg(long, env = "REVERSE_TUNNEL_LISTEN", default_value = "0.0.0.0:18090")]
    pub listen: String,
    #[arg(long, env = "REVERSE_TUNNEL_AUTH_TOKEN")]
    pub auth_token: String,
}
