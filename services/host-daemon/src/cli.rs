use clap::Parser;

#[derive(Parser, Debug)]
#[command(name = "host-daemon")]
#[command(about = "Reconstructed local device API and rotate job service")]
pub struct Cli {
    #[arg(long, env = "HOST_DAEMON_LISTEN")]
    pub listen: Option<String>,
    #[arg(long, env = "HOST_DAEMON_ADMIN_TOKEN")]
    pub admin_token: Option<String>,
    #[arg(long, env = "HOST_DAEMON_CONFIG")]
    pub config: Option<String>,
}
