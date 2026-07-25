use anyhow::{Result, bail};

use crate::android_app::install_android_app;
use crate::cli::{InstallAndroidAppArgs, InstallDeviceReleaseArgs, InstallDeviceStackArgs};
use crate::device::install_device_release;

const FIRST_PARTY_VPN_OWNER: &str = "first_party_vpn_service";
const PRIMARY_TUNNEL_OWNER: &str = "first_party_reverse_tunnel";
const STOCK_WIREGUARD_OWNER: &str = "stock_wireguard_bridge";

pub async fn install_device_stack(args: &InstallDeviceStackArgs) -> Result<()> {
    match args.tunnel_owner.as_str() {
        FIRST_PARTY_VPN_OWNER => install_android_app(&InstallAndroidAppArgs {
            project_dir: args.android_project_dir.clone(),
            windows_build_dir: args.android_windows_build_dir.clone(),
            windows_build_dir_cmd: args.android_windows_build_dir_cmd.clone(),
            apk_windows_path: args.android_apk_windows_path.clone(),
            device_serial: args.device_serial.clone(),
            skip_install: false,
        })?,
        PRIMARY_TUNNEL_OWNER | STOCK_WIREGUARD_OWNER => {}
        other => bail!(
            "unsupported tunnel owner {other}; expected {PRIMARY_TUNNEL_OWNER}, {STOCK_WIREGUARD_OWNER}, or {FIRST_PARTY_VPN_OWNER}"
        ),
    }

    install_device_release(&InstallDeviceReleaseArgs {
        manifest_path: args.manifest_path.clone(),
        release_id: args.release_id.clone(),
        output_dir: args.output_dir.clone(),
        host_daemon_config_path: args.host_daemon_config_path.clone(),
        sing_box_config_path: args.sing_box_config_path.clone(),
        tunnel_owner: args.tunnel_owner.clone(),
        device_root: args.device_root.clone(),
        temp_root: args.temp_root.clone(),
        device_serial: args.device_serial.clone(),
        health_port: args.health_port,
        skip_proxy_smoke: args.skip_proxy_smoke,
    })
    .await
}

#[cfg(test)]
mod tests {
    use super::{FIRST_PARTY_VPN_OWNER, PRIMARY_TUNNEL_OWNER, STOCK_WIREGUARD_OWNER};

    #[test]
    fn primary_and_stock_modes_do_not_require_the_first_party_android_app() {
        assert_ne!(PRIMARY_TUNNEL_OWNER, FIRST_PARTY_VPN_OWNER);
        assert_ne!(STOCK_WIREGUARD_OWNER, FIRST_PARTY_VPN_OWNER);
    }
}
