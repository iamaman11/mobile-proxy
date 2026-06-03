use clap::{Args, Parser, Subcommand};
use proxy_core::LOCAL_API;

#[derive(Parser)]
#[command(name = "operator-cli")]
#[command(about = "Rust-first operator client for the mobile relay")]
pub struct Cli {
    #[arg(long, default_value = LOCAL_API)]
    pub api: String,
    #[arg(long)]
    pub token: Option<String>,
    #[command(subcommand)]
    pub command: Command,
}

#[derive(Subcommand)]
pub enum Command {
    Status,
    Proxy,
    Rotate(RotateArgs),
    AirplaneStudy(AirplaneStudyArgs),
    PrepareRuntimeBinaries(PrepareRuntimeBinariesArgs),
    ProvisionVm(ProvisionVmArgs),
    DeleteVm(DeleteVmArgs),
    PackageDeviceRelease(PackageDeviceReleaseArgs),
    InstallDeviceRelease(InstallDeviceReleaseArgs),
    VerifyDevice(VerifyDeviceArgs),
    RollbackDevice(RollbackDeviceArgs),
}

#[derive(Args, Debug, Clone)]
pub struct RotateArgs {
    #[arg(long, default_value = "airplane_bounce")]
    pub strategy: String,
    #[arg(long, default_value_t = true)]
    pub require_public_ip_change: bool,
    #[arg(long, default_value = "manual-rotate")]
    pub reason: String,
    #[arg(long)]
    pub hold_secs: Option<u64>,
    #[arg(long, default_value_t = 2)]
    pub poll_secs: u64,
}

#[derive(Args, Debug, Clone)]
pub struct AirplaneStudyArgs {
    #[arg(long, value_delimiter = ',', default_values_t = vec![1_u64, 2, 3, 4, 5])]
    pub hold_secs: Vec<u64>,
    #[arg(long, default_value_t = 30)]
    pub runs: u32,
    #[arg(long, default_value_t = true)]
    pub require_public_ip_change: bool,
    #[arg(long, default_value = "airplane-study")]
    pub reason_prefix: String,
    #[arg(long, default_value_t = 2)]
    pub poll_secs: u64,
}

#[derive(Args, Debug, Clone)]
pub struct PrepareRuntimeBinariesArgs {
    #[arg(long, default_value = "1.13.12")]
    pub sing_box_version: String,
    #[arg(long, default_value = "/usr/lib/android-ndk")]
    pub android_ndk: String,
    #[arg(long, default_value_t = false)]
    pub skip_android_rust_build: bool,
    #[arg(long, default_value_t = false)]
    pub skip_sing_box_download: bool,
}

#[derive(Args, Debug, Clone)]
pub struct ProvisionVmArgs {
    #[arg(long)]
    pub manifest_path: String,
    #[arg(long, default_value = "target/vm-releases")]
    pub output_dir: String,
    #[arg(long, default_value = "manual")]
    pub release_id: String,
    #[arg(long, default_value = "bose")]
    pub ssh_user: String,
    #[arg(long, default_value = "~/.ssh/google_compute_engine")]
    pub ssh_key: String,
    #[arg(long, default_value_t = false)]
    pub create_only: bool,
}

#[derive(Args, Debug, Clone)]
pub struct DeleteVmArgs {
    #[arg(long)]
    pub manifest_path: String,
    #[arg(long, default_value_t = false)]
    pub delete_firewall_rules: bool,
}

#[derive(Args, Debug, Clone)]
pub struct PackageDeviceReleaseArgs {
    #[arg(long)]
    pub manifest_path: String,
    #[arg(long)]
    pub release_id: String,
    #[arg(long, default_value = "target/device-releases")]
    pub output_dir: String,
    #[arg(long)]
    pub host_daemon_config_path: Option<String>,
    #[arg(long)]
    pub sing_box_config_path: Option<String>,
}

#[derive(Args, Debug, Clone)]
pub struct InstallDeviceReleaseArgs {
    #[arg(long)]
    pub manifest_path: String,
    #[arg(long)]
    pub release_id: String,
    #[arg(long, default_value = "target/device-releases")]
    pub output_dir: String,
    #[arg(long)]
    pub host_daemon_config_path: Option<String>,
    #[arg(long)]
    pub sing_box_config_path: Option<String>,
    #[arg(long, default_value = "/data/adb/mobile-proxy-node")]
    pub device_root: String,
    #[arg(long, default_value = "/data/local/tmp/mobile-proxy-install")]
    pub temp_root: String,
    #[arg(long)]
    pub device_serial: Option<String>,
    #[arg(long, default_value_t = 18088)]
    pub health_port: u16,
    #[arg(long, default_value_t = false)]
    pub skip_proxy_smoke: bool,
}

#[derive(Args, Debug, Clone)]
pub struct VerifyDeviceArgs {
    #[arg(long)]
    pub manifest_path: String,
    #[arg(long)]
    pub device_serial: Option<String>,
    #[arg(long, default_value_t = 18088)]
    pub health_port: u16,
    #[arg(long, default_value_t = false)]
    pub skip_proxy_smoke: bool,
}

#[derive(Args, Debug, Clone)]
pub struct RollbackDeviceArgs {
    #[arg(long)]
    pub manifest_path: String,
    #[arg(long)]
    pub release_id: Option<String>,
    #[arg(long)]
    pub device_serial: Option<String>,
    #[arg(long, default_value = "/data/adb/mobile-proxy-node")]
    pub device_root: String,
    #[arg(long, default_value_t = 18088)]
    pub health_port: u16,
}
