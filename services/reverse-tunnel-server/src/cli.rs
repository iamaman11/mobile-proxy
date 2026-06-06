use clap::Parser;

#[derive(Parser, Debug)]
#[command(name = "reverse-tunnel-server")]
#[command(about = "VM-side first-party reverse tunnel ingress")]
pub struct Cli {
    #[arg(long, env = "REVERSE_TUNNEL_LISTEN", default_value = "0.0.0.0:18090")]
    pub listen: String,
    #[arg(
        long,
        env = "REVERSE_TUNNEL_PUBLIC_PROXY_LISTEN",
        default_value = "127.0.0.1:14080,127.0.0.1:14081,127.0.0.1:14128"
    )]
    pub public_proxy_listen: String,
    #[arg(long, env = "REVERSE_TUNNEL_TARGET_NODE_ID")]
    pub target_node_id: Option<String>,
    #[arg(long, env = "REVERSE_TUNNEL_AUTH_TOKEN")]
    pub auth_token: String,
    #[arg(
        long,
        env = "REVERSE_TUNNEL_SERVER_NAME",
        default_value = "mobile-proxy-relay"
    )]
    pub server_name: String,
    #[arg(long, env = "REVERSE_TUNNEL_CERT_DER_B64")]
    pub cert_der_b64: String,
    #[arg(long, env = "REVERSE_TUNNEL_KEY_DER_B64")]
    pub key_der_b64: String,
}
