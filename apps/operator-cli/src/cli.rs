use clap::{Args, Parser, Subcommand, ValueEnum};
use proxy_core::LOCAL_API;

pub const PRIMARY_TUNNEL_OWNER: &str = "first_party_reverse_tunnel";

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
    Status(StatusArgs),
    Metrics,
    Proxy,
    Rotate(RotateArgs),
    /// Rotate the mobile IP through the remote control plane (no ADB required).
    RotateServer(RotateServerArgs),
    AirplaneStudy(AirplaneStudyArgs),
    PrepareRuntimeBinaries(PrepareRuntimeBinariesArgs),
    ProvisionVm(ProvisionVmArgs),
    DeleteVm(DeleteVmArgs),
    InstallAndroidApp(InstallAndroidAppArgs),
    InstallDeviceStack(InstallDeviceStackArgs),
    PackageDeviceRelease(PackageDeviceReleaseArgs),
    InstallDeviceRelease(InstallDeviceReleaseArgs),
    VerifyReleaseIntegrity(VerifyReleaseIntegrityArgs),
    VerifyDevice(VerifyDeviceArgs),
    RollbackDevice(RollbackDeviceArgs),
    GenerateReverseTunnelIdentity(GenerateReverseTunnelIdentityArgs),
}

#[derive(Args, Debug, Clone)]
pub struct StatusArgs {
    #[arg(long, value_enum, default_value_t = StatusFormat::Json)]
    pub format: StatusFormat,
}

#[derive(ValueEnum, Debug, Clone, Copy, PartialEq, Eq)]
pub enum StatusFormat {
    Json,
    Summary,
}

#[derive(Args, Debug, Clone)]
pub struct GenerateReverseTunnelIdentityArgs {
    #[arg(long, default_value = ".secrets/reverse-tunnel.env")]
    pub output_env_file: String,
    #[arg(long, default_value = "mobile-proxy-relay")]
    pub server_name: String,
    #[arg(long, default_value_t = false)]
    pub overwrite: bool,
}

#[derive(Args, Debug, Clone)]
pub struct InstallDeviceStackArgs {
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
    #[arg(long, default_value = PRIMARY_TUNNEL_OWNER)]
    pub tunnel_owner: String,
    #[arg(long, default_value = "apps/android-app")]
    pub android_project_dir: String,
    #[arg(long, default_value = "/mnt/c/Users/Bose/mobile-proxy-android-build")]
    pub android_windows_build_dir: String,
    #[arg(long, default_value = "C:\\Users\\Bose\\mobile-proxy-android-build")]
    pub android_windows_build_dir_cmd: String,
    #[arg(
        long,
        default_value = "C:\\Users\\Bose\\mobile-proxy-android-build\\app\\build\\outputs\\apk\\debug\\app-debug.apk"
    )]
    pub android_apk_windows_path: String,
}

#[derive(Args, Debug, Clone)]
pub struct InstallAndroidAppArgs {
    #[arg(long, default_value = "apps/android-app")]
    pub project_dir: String,
    #[arg(long, default_value = "/mnt/c/Users/Bose/mobile-proxy-android-build")]
    pub windows_build_dir: String,
    #[arg(long, default_value = "C:\\Users\\Bose\\mobile-proxy-android-build")]
    pub windows_build_dir_cmd: String,
    #[arg(
        long,
        default_value = "C:\\Users\\Bose\\mobile-proxy-android-build\\app\\build\\outputs\\apk\\debug\\app-debug.apk"
    )]
    pub apk_windows_path: String,
    #[arg(long)]
    pub device_serial: Option<String>,
    #[arg(long, default_value_t = false)]
    pub skip_install: bool,
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
pub struct RotateServerArgs {
    #[arg(long, default_value = "https://mobile-proxy-relay:8443")]
    pub control_plane_url: String,
    #[arg(long, default_value = "34.118.88.54:8443")]
    pub control_plane_addr: std::net::SocketAddr,
    #[arg(long, default_value = "mobile-proxy-relay")]
    pub control_plane_name: String,
    #[arg(
        long,
        env = "MOBILE_PROXY_REVERSE_TUNNEL_CERT_DER_B64",
        hide_env_values = true
    )]
    pub control_plane_cert_der_b64: String,
    #[arg(long, env = "MOBILE_PROXY_UI_TOKEN", hide_env_values = true)]
    pub ui_token: String,
    #[arg(long, default_value = "b4a6b2f4-5f6f-4fd1-baa4-b7d241b49a06")]
    pub device_id: String,
    #[arg(long, default_value_t = 240)]
    pub timeout_secs: u32,
    #[arg(long, default_value_t = 2)]
    pub poll_secs: u64,
    #[arg(long, value_enum, default_value_t = StatusFormat::Summary)]
    pub format: StatusFormat,
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
    #[arg(long, default_value = PRIMARY_TUNNEL_OWNER)]
    pub tunnel_owner: String,
}

#[derive(Args, Debug, Clone)]
pub struct InstallDeviceReleaseArgs {
    #[arg(long)]
    pub manifest_path: String,
    #[arg(long)]
    pub release_id: String,
    #[arg(long, default_value = "target/device-releases")]
    pub output_dir: String,
    #[arg(long, default_value_t = false)]
    pub use_existing_release: bool,
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
    #[arg(long, default_value = PRIMARY_TUNNEL_OWNER)]
    pub tunnel_owner: String,
}

#[derive(Args, Debug, Clone)]
pub struct VerifyReleaseIntegrityArgs {
    #[arg(long)]
    pub root: String,
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
    #[arg(long, default_value = PRIMARY_TUNNEL_OWNER)]
    pub required_tunnel_owner: String,
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

#[cfg(test)]
mod tests {
    use clap::Parser;

    use super::{Cli, Command, PRIMARY_TUNNEL_OWNER, StatusFormat};

    #[test]
    fn status_preserves_json_as_the_default_output() {
        let cli = Cli::try_parse_from(["operator-cli", "status"]).unwrap();
        let Command::Status(args) = cli.command else {
            panic!("status command must parse");
        };
        assert_eq!(args.format, StatusFormat::Json);
    }

    #[test]
    fn status_summary_and_metrics_are_explicit_operator_surfaces() {
        let cli = Cli::try_parse_from(["operator-cli", "status", "--format", "summary"]).unwrap();
        let Command::Status(args) = cli.command else {
            panic!("status command must parse");
        };
        assert_eq!(args.format, StatusFormat::Summary);

        let metrics = Cli::try_parse_from(["operator-cli", "metrics"]).unwrap();
        assert!(matches!(metrics.command, Command::Metrics));
    }

    #[test]
    fn server_rotation_is_an_explicit_remote_surface() {
        let cli = Cli::try_parse_from([
            "operator-cli",
            "rotate-server",
            "--control-plane-cert-der-b64",
            "certificate",
            "--ui-token",
            "token",
        ])
        .unwrap();
        let Command::RotateServer(args) = cli.command else {
            panic!("rotate-server command must parse");
        };
        assert_eq!(args.format, StatusFormat::Summary);
        assert_eq!(args.timeout_secs, 240);
    }

    #[test]
    fn native_reverse_tunnel_is_the_default_for_all_device_operations() {
        let package = Cli::try_parse_from([
            "operator-cli",
            "package-device-release",
            "--manifest-path",
            "device.json",
            "--release-id",
            "candidate",
        ])
        .unwrap();
        let Command::PackageDeviceRelease(package) = package.command else {
            panic!("package-device-release must parse");
        };
        assert_eq!(package.tunnel_owner, PRIMARY_TUNNEL_OWNER);

        let install = Cli::try_parse_from([
            "operator-cli",
            "install-device-release",
            "--manifest-path",
            "device.json",
            "--release-id",
            "candidate",
        ])
        .unwrap();
        let Command::InstallDeviceRelease(install) = install.command else {
            panic!("install-device-release must parse");
        };
        assert_eq!(install.tunnel_owner, PRIMARY_TUNNEL_OWNER);
        assert!(!install.use_existing_release);

        let immutable_install = Cli::try_parse_from([
            "operator-cli",
            "install-device-release",
            "--manifest-path",
            "device.json",
            "--release-id",
            "candidate",
            "--use-existing-release",
        ])
        .unwrap();
        let Command::InstallDeviceRelease(immutable_install) = immutable_install.command else {
            panic!("install-device-release must parse immutable mode");
        };
        assert!(immutable_install.use_existing_release);

        let verify = Cli::try_parse_from([
            "operator-cli",
            "verify-device",
            "--manifest-path",
            "device.json",
        ])
        .unwrap();
        let Command::VerifyDevice(verify) = verify.command else {
            panic!("verify-device must parse");
        };
        assert_eq!(verify.required_tunnel_owner, PRIMARY_TUNNEL_OWNER);
    }

    #[test]
    fn release_integrity_verification_is_an_explicit_offline_surface() {
        let cli = Cli::try_parse_from([
            "operator-cli",
            "verify-release-integrity",
            "--root",
            "target/device-releases/candidate",
        ])
        .unwrap();
        let Command::VerifyReleaseIntegrity(args) = cli.command else {
            panic!("verify-release-integrity command must parse");
        };
        assert_eq!(args.root, "target/device-releases/candidate");
    }
}
