use std::fs;
use std::path::Path;

use anyhow::{Context, Result};

use crate::cli::{
    InstallDeviceReleaseArgs, PackageDeviceReleaseArgs, RollbackDeviceArgs, VerifyDeviceArgs,
};
use crate::device_support::{
    adb, admin_token, assert_active_vpn_owner, assert_healthy, assert_tunnel_owner,
    ensure_root_access, load_manifest, proxy_smoke, release_root, shell_quote_validated,
    validate_device_path, validate_release_id, validate_tunnel_owner,
    verify_installed_release_files, wait_for_health, write_temp_script,
};
use crate::provision::package_device_release;

pub async fn install_device_release(args: &InstallDeviceReleaseArgs) -> Result<()> {
    validate_release_id(&args.release_id)?;
    validate_device_path(&args.device_root, "device_root")?;
    validate_device_path(&args.temp_root, "temp_root")?;
    validate_tunnel_owner(&args.tunnel_owner)?;

    package_device_release(&PackageDeviceReleaseArgs {
        manifest_path: args.manifest_path.clone(),
        release_id: args.release_id.clone(),
        output_dir: args.output_dir.clone(),
        host_daemon_config_path: args.host_daemon_config_path.clone(),
        sing_box_config_path: args.sing_box_config_path.clone(),
        tunnel_owner: args.tunnel_owner.clone(),
    })?;

    let manifest = load_manifest(&args.manifest_path)?;
    let token = admin_token(&manifest)?;
    let release_root = release_root(&args.output_dir, &args.release_id)?;
    ensure_root_access(args.device_serial.as_deref())?;

    let remote_staging = format!("{}/{}", args.temp_root, args.release_id);
    adb(
        args.device_serial.as_deref(),
        &["shell", "rm", "-rf", &remote_staging],
    )?;
    adb(
        args.device_serial.as_deref(),
        &["shell", "mkdir", "-p", &args.temp_root],
    )?;
    adb(
        args.device_serial.as_deref(),
        &[
            "push",
            release_root.to_str().context("invalid release root path")?,
            &args.temp_root,
        ],
    )?;

    let root = shell_quote_validated(&args.device_root);
    let release = shell_quote_validated(&args.release_id);
    let staging = shell_quote_validated(&remote_staging);
    let apply_script = format!(
        r#"set -eu
umask 077
ROOT={root}
REL={release}
TMP={staging}
BOOT='/data/adb/service.d/99-mobile-proxy-runtime.sh'
TARGET="$ROOT/releases/$REL"
mkdir -p "$ROOT/releases" "$ROOT/logs" /data/adb/service.d
chmod 0700 "$ROOT" "$ROOT/releases" "$ROOT/logs"
if command -v pkill >/dev/null 2>&1; then
  pkill -f /data/local/tmp/mobile-proxy-logs/runtime-watchdog.sh || true
  pkill -f "$ROOT/.*/bin/runtime-supervisor" || true
  pkill -f "$ROOT/.*/bin/host-daemon" || true
  pkill -f "$ROOT/.*/bin/sing-box" || true
fi
for pid in $(pidof runtime-supervisor host-daemon sing-box 2>/dev/null || true); do
  kill "$pid" || true
done
rm -f /data/local/tmp/mobile-proxy-logs/runtime-watchdog.pid
sleep 1
rm -rf "$TARGET"
mkdir -p "$TARGET"
cp -R "$TMP/." "$TARGET/"
rm -rf "$TMP"
find "$TARGET" -type d -exec chmod 0700 {{}} +
find "$TARGET" -type f -exec chmod 0600 {{}} +
chmod 0700 "$TARGET/service.sh" "$TARGET/bin/runtime-supervisor" "$TARGET/bin/host-daemon" "$TARGET/bin/sing-box" "$TARGET/bin/curl"
ln -sfn "$TARGET" "$ROOT/current"
rm -f /data/adb/service.d/99-mobile-proxy-routefix.sh
cat > "$BOOT" <<'MOBILE_PROXY_BOOT'
#!/system/bin/sh
set -eu
umask 077
ROOT='/data/adb/mobile-proxy-node'
LOG_DIR='/data/local/tmp/mobile-proxy-logs'
BOOT_LOG="$LOG_DIR/boot-service.log"
mkdir -p "$LOG_DIR"
chmod 0700 "$LOG_DIR"
timestamp() {{ date '+%Y-%m-%dT%H:%M:%S%z'; }}
log_boot() {{ echo "$(timestamp) $*" >> "$BOOT_LOG"; }}
log_boot "boot_hook_started"
i=0
while [ "$i" -lt 30 ]; do
  if [ -x "$ROOT/current/service.sh" ]; then
    log_boot "boot_hook_starting_release attempt=$i"
    sh "$ROOT/current/service.sh" >> "$BOOT_LOG" 2>&1
    code="$?"
    log_boot "boot_hook_service_returned code=$code"
    exit "$code"
  fi
  i=$((i + 1))
  sleep 1
done
log_boot "active release service is missing"
exit 1
MOBILE_PROXY_BOOT
chmod 0700 "$BOOT"
sh "$ROOT/current/service.sh"
"#
    );
    let apply_path = write_temp_script("mobile-proxy-apply", &apply_script)?;
    let remote_apply = format!("{}/apply-{}.sh", args.temp_root, std::process::id());
    let apply_result = (|| -> Result<()> {
        adb(
            args.device_serial.as_deref(),
            &[
                "push",
                apply_path.to_str().context("invalid apply script path")?,
                &remote_apply,
            ],
        )?;
        let remote_apply_quoted = shell_quote_validated(&remote_apply);
        let apply_command =
            format!("sh {remote_apply_quoted}; code=$?; rm -f {remote_apply_quoted}; exit $code");
        adb(
            args.device_serial.as_deref(),
            &["shell", "su", "0", "sh", "-c", &apply_command],
        )?;
        Ok(())
    })();
    let _ = fs::remove_file(&apply_path);
    apply_result?;

    verify_installed_release_files(
        &release_root,
        args.device_serial.as_deref(),
        &args.device_root,
    )?;

    let health = wait_for_health(
        args.device_serial.as_deref(),
        args.health_port,
        &token,
        75,
        2,
    )
    .await?;
    assert_healthy(&health)?;
    assert_tunnel_owner(&health, &args.tunnel_owner)?;
    assert_active_vpn_owner(args.device_serial.as_deref(), &args.tunnel_owner)?;
    if !args.skip_proxy_smoke {
        proxy_smoke(&manifest).await?;
    }

    println!(
        "Device runtime installed: release={} device={} owner={} readiness={}",
        args.release_id,
        manifest.device_id(),
        args.tunnel_owner,
        health.readiness_state
    );
    Ok(())
}

pub async fn verify_device(args: &VerifyDeviceArgs) -> Result<()> {
    validate_tunnel_owner(&args.required_tunnel_owner)?;
    let manifest = load_manifest(&args.manifest_path)?;
    let token = admin_token(&manifest)?;
    let health = wait_for_health(
        args.device_serial.as_deref(),
        args.health_port,
        &token,
        1,
        1,
    )
    .await?;
    assert_healthy(&health)?;
    assert_tunnel_owner(&health, &args.required_tunnel_owner)?;
    assert_active_vpn_owner(args.device_serial.as_deref(), &args.required_tunnel_owner)?;
    if !args.skip_proxy_smoke {
        proxy_smoke(&manifest).await?;
    }
    println!(
        "Device verify passed: node={} owner={} ip={:?}",
        health.node_id, args.required_tunnel_owner, health.last_public_ip
    );
    Ok(())
}

pub async fn rollback_device(args: &RollbackDeviceArgs) -> Result<()> {
    validate_device_path(&args.device_root, "device_root")?;
    let manifest = load_manifest(&args.manifest_path)?;
    let token = admin_token(&manifest)?;
    ensure_root_access(args.device_serial.as_deref())?;

    let root = shell_quote_validated(&args.device_root);
    let current = adb(
        args.device_serial.as_deref(),
        &[
            "shell",
            "su",
            "0",
            "sh",
            "-c",
            &format!("readlink {root}/current"),
        ],
    )?;
    let current_release = Path::new(current.trim())
        .file_name()
        .and_then(|name| name.to_str())
        .unwrap_or_default()
        .to_string();
    let releases = adb(
        args.device_serial.as_deref(),
        &[
            "shell",
            "su",
            "0",
            "sh",
            "-c",
            &format!("ls -1t {root}/releases"),
        ],
    )?;
    let target_release = args.release_id.clone().or_else(|| {
        releases
            .lines()
            .map(str::trim)
            .find(|release| !release.is_empty() && *release != current_release)
            .map(ToOwned::to_owned)
    });
    let target_release = target_release.context("could not select rollback target release")?;
    validate_release_id(&target_release)?;
    let release = shell_quote_validated(&target_release);
    let command = format!(
        r#"set -eu
ROOT={root}
REL={release}
TARGET="$ROOT/releases/$REL"
test -x "$TARGET/service.sh"
if command -v pkill >/dev/null 2>&1; then
  pkill -f /data/local/tmp/mobile-proxy-logs/runtime-watchdog.sh || true
  pkill -f "$ROOT/.*/bin/runtime-supervisor" || true
  pkill -f "$ROOT/.*/bin/host-daemon" || true
  pkill -f "$ROOT/.*/bin/sing-box" || true
fi
for pid in $(pidof runtime-supervisor host-daemon sing-box 2>/dev/null || true); do
  kill "$pid" || true
done
rm -f /data/local/tmp/mobile-proxy-logs/runtime-watchdog.pid
sleep 1
ln -sfn "$TARGET" "$ROOT/current"
sh "$ROOT/current/service.sh"
test "$(readlink "$ROOT/current")" = "$TARGET"
"#
    );
    adb(
        args.device_serial.as_deref(),
        &["shell", "su", "0", "sh", "-c", &command],
    )?;

    let health = wait_for_health(
        args.device_serial.as_deref(),
        args.health_port,
        &token,
        40,
        2,
    )
    .await?;
    assert_healthy(&health)?;
    println!(
        "Rollback applied with full runtime restart: current={} readiness={}",
        target_release, health.readiness_state
    );
    Ok(())
}
