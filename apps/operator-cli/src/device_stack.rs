use anyhow::Result;

use crate::android_app::install_android_app;
use crate::cli::{InstallAndroidAppArgs, InstallDeviceReleaseArgs, InstallDeviceStackArgs};
use crate::device::install_device_release;

pub async fn install_device_stack(args: &InstallDeviceStackArgs) -> Result<()> {
    install_android_app(&InstallAndroidAppArgs {
        project_dir: args.android_project_dir.clone(),
        windows_build_dir: args.android_windows_build_dir.clone(),
        windows_build_dir_cmd: args.android_windows_build_dir_cmd.clone(),
        apk_windows_path: args.android_apk_windows_path.clone(),
        device_serial: args.device_serial.clone(),
        skip_install: false,
    })?;

    install_device_release(&InstallDeviceReleaseArgs {
        manifest_path: args.manifest_path.clone(),
        release_id: args.release_id.clone(),
        output_dir: args.output_dir.clone(),
        host_daemon_config_path: args.host_daemon_config_path.clone(),
        sing_box_config_path: args.sing_box_config_path.clone(),
        device_root: args.device_root.clone(),
        temp_root: args.temp_root.clone(),
        device_serial: args.device_serial.clone(),
        health_port: args.health_port,
        skip_proxy_smoke: args.skip_proxy_smoke,
    })
    .await
}
