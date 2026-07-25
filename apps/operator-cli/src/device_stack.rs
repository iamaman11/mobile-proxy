use anyhow::Result;

use crate::cli::{InstallDeviceReleaseArgs, InstallDeviceStackArgs};
use crate::device::install_device_release;
use crate::device_support::validate_tunnel_owner;

pub async fn install_device_stack(args: &InstallDeviceStackArgs) -> Result<()> {
    validate_tunnel_owner(&args.tunnel_owner)?;
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
    use crate::device_support::validate_tunnel_owner;

    #[test]
    fn stack_accepts_only_native_primary_and_stock_rollback() {
        assert!(validate_tunnel_owner("first_party_reverse_tunnel").is_ok());
        assert!(validate_tunnel_owner("stock_wireguard_bridge").is_ok());
        assert!(validate_tunnel_owner("first_party_vpn_service").is_ok());
    }
}
