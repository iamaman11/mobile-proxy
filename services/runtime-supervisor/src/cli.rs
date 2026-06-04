use clap::Parser;

#[derive(Parser, Debug)]
#[command(name = "runtime-supervisor")]
#[command(about = "Phone-side owner for host-daemon, sing-box, and runtime recovery")]
pub struct Cli {
    #[arg(long, default_value = "/data/adb/mobile-proxy-node/current")]
    pub runtime_root: String,
    #[arg(long, default_value_t = 1)]
    pub poll_secs: u64,
    #[arg(long, default_value_t = 15)]
    pub repair_cooldown_secs: u64,
    #[arg(long, default_value_t = 2)]
    pub data_bounce_down_secs: u64,
    #[arg(long, default_value_t = 8)]
    pub data_bounce_settle_secs: u64,
    #[arg(long, default_value_t = false)]
    pub once: bool,
}
