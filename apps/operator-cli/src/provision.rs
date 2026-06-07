use std::env;
use std::fs;
use std::io::Read;
use std::path::{Path, PathBuf};

use anyhow::{Context, Result, bail};
use serde::Deserialize;
use sha2::{Digest, Sha256};

use crate::cli::PackageDeviceReleaseArgs;

const CURL_SHIM: &str = r#"#!/system/bin/sh
set -eu

LOG_FILE="/data/adb/mobile-proxy-node/logs/curl-shim.log"

max_time=5
url=""
proxy_url=""
proxy_user=""

echo "$(date '+%Y-%m-%dT%H:%M:%S%z') args:$*" >> "$LOG_FILE" 2>/dev/null || true

while [ "$#" -gt 0 ]; do
  case "$1" in
    --proxy)
      proxy_url="${2:-}"
      shift 2
      ;;
    --proxy-user)
      proxy_user="${2:-}"
      shift 2
      ;;
    --max-time|--connect-timeout)
      max_time="${2:-5}"
      shift 2
      ;;
    --silent|--show-error|-s|-S|-k|-L|-f)
      shift
      ;;
    http://*|https://*)
      url="$1"
      shift
      ;;
    *)
      shift
      ;;
  esac
done

if [ -z "$url" ]; then
  echo "$(date '+%Y-%m-%dT%H:%M:%S%z') result:no_url" >> "$LOG_FILE" 2>/dev/null || true
  exit 2
fi

effective_proxy=""
if [ -n "$proxy_url" ]; then
  proxy_hostport="${proxy_url#*://}"
  if [ -z "$proxy_user" ] && [ "$proxy_hostport" = "10.66.66.2:1080" ] && [ -f "/data/adb/mobile-proxy-node/current/config/sing-box.json" ]; then
    local_user="$(sed -n 's/.*"username"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' /data/adb/mobile-proxy-node/current/config/sing-box.json | head -n1)"
    local_pass="$(sed -n 's/.*"password"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' /data/adb/mobile-proxy-node/current/config/sing-box.json | head -n1)"
    if [ -n "$local_user" ] && [ -n "$local_pass" ]; then
      proxy_user="${local_user}:${local_pass}"
    fi
  fi
  if [ -n "$proxy_user" ] && ! echo "$proxy_hostport" | grep -q '@'; then
    proxy_hostport="${proxy_user}@${proxy_hostport}"
  fi
  effective_proxy="http://${proxy_hostport}"
fi

if [ -x "/data/adb/magisk/busybox" ]; then
  WGET_BIN="/data/adb/magisk/busybox"
elif [ -x "/debug_ramdisk/.magisk/busybox/busybox" ]; then
  WGET_BIN="/debug_ramdisk/.magisk/busybox/busybox"
else
  WGET_BIN=""
fi

run_wget() {
  _url="$1"
  if [ -n "$effective_proxy" ]; then
    if [ -n "$WGET_BIN" ]; then
      http_proxy="$effective_proxy" https_proxy="$effective_proxy" "$WGET_BIN" wget -Y on -qO- --timeout "$max_time" "$_url" 2>/dev/null
    else
      http_proxy="$effective_proxy" https_proxy="$effective_proxy" wget -Y on -qO- --timeout "$max_time" "$_url" 2>/dev/null
    fi
  else
    if [ -n "$WGET_BIN" ]; then
      "$WGET_BIN" wget -qO- --timeout "$max_time" "$_url" 2>/dev/null
    else
      wget -qO- --timeout "$max_time" "$_url" 2>/dev/null
    fi
  fi
}

if run_wget "$url"; then
  echo "$(date '+%Y-%m-%dT%H:%M:%S%z') result:ok url:$url" >> "$LOG_FILE" 2>/dev/null || true
  exit 0
fi

case "$url" in
  https://*)
    alt_url="http://${url#https://}"
    if run_wget "$alt_url"; then
      echo "$(date '+%Y-%m-%dT%H:%M:%S%z') result:ok_alt url:$alt_url" >> "$LOG_FILE" 2>/dev/null || true
      exit 0
    fi
    echo "$(date '+%Y-%m-%dT%H:%M:%S%z') result:fail url:$url alt:$alt_url" >> "$LOG_FILE" 2>/dev/null || true
    exit 1
    ;;
  *)
    echo "$(date '+%Y-%m-%dT%H:%M:%S%z') result:fail url:$url" >> "$LOG_FILE" 2>/dev/null || true
    exit 1
    ;;
esac
"#;

#[derive(Debug, Deserialize)]
struct DeviceManifest {
    #[serde(rename = "deviceId")]
    device_id: String,
    #[serde(rename = "nodeName")]
    node_name: String,
    #[serde(rename = "operatorProfile")]
    operator_profile: Option<String>,
    #[serde(rename = "controlPlaneUrl")]
    control_plane_url: String,
    tokens: ManifestTokens,
    relay: Option<ManifestRelay>,
}

#[derive(Debug, Deserialize)]
struct ManifestTokens {
    #[serde(rename = "adminTokenEnv")]
    admin_token_env: String,
    #[serde(rename = "deviceTokenEnv")]
    device_token_env: String,
    #[serde(rename = "relayUserEnv")]
    relay_user_env: String,
    #[serde(rename = "relayPasswordEnv")]
    relay_password_env: String,
    #[serde(rename = "wireguardPhonePrivateKeyEnv")]
    wireguard_phone_private_key_env: Option<String>,
    #[serde(rename = "wireguardServerPublicKeyEnv")]
    wireguard_server_public_key_env: Option<String>,
    #[serde(rename = "reverseTunnelCertDerB64Env")]
    reverse_tunnel_cert_der_b64_env: Option<String>,
}

#[derive(Debug, Deserialize)]
struct ManifestRelay {
    host: String,
    #[serde(rename = "wireguardPort")]
    wireguard_port: Option<u16>,
}

#[derive(Debug, Deserialize)]
struct DeviceProfile {
    operator_profile: String,
    airplane_hold_secs: u64,
}

pub fn package_device_release(args: &PackageDeviceReleaseArgs) -> Result<()> {
    let repo_root = repo_root()?;
    let manifest_path = resolve_path(&repo_root, &args.manifest_path);
    let manifest: DeviceManifest = serde_json::from_str(
        &fs::read_to_string(&manifest_path)
            .with_context(|| format!("failed to read manifest {}", manifest_path.display()))?,
    )?;

    let profile_name = manifest
        .operator_profile
        .clone()
        .unwrap_or_else(|| "default".into());
    let profile_path = repo_root
        .join("deploy/device-runtime/profiles")
        .join(format!("{profile_name}.json"));
    let profile: DeviceProfile = serde_json::from_str(
        &fs::read_to_string(&profile_path)
            .with_context(|| format!("failed to read profile {}", profile_path.display()))?,
    )?;

    let admin_token = required_env(&manifest.tokens.admin_token_env)?;
    let device_token = required_env(&manifest.tokens.device_token_env)?;
    let relay_user = required_env(&manifest.tokens.relay_user_env)?;
    let relay_password = required_env(&manifest.tokens.relay_password_env)?;
    validate_tunnel_owner(&args.tunnel_owner)?;

    let bin_dir = repo_root.join("deploy/device-runtime/bin");
    let runtime_supervisor_bin = bin_dir.join("runtime-supervisor");
    let host_daemon_bin = bin_dir.join("host-daemon");
    let sing_box_bin = bin_dir.join("sing-box");
    ensure_android_arm_binary(&runtime_supervisor_bin)?;
    ensure_android_arm_binary(&host_daemon_bin)?;
    ensure_android_arm_binary(&sing_box_bin)?;

    let release_root = resolve_path(&repo_root, &args.output_dir).join(&args.release_id);
    if release_root.exists() {
        fs::remove_dir_all(&release_root)
            .with_context(|| format!("failed to clean {}", release_root.display()))?;
    }
    fs::create_dir_all(release_root.join("bin"))?;
    fs::create_dir_all(release_root.join("config"))?;

    fs::copy(
        repo_root.join("deploy/device-runtime/module/service.sh"),
        release_root.join("service.sh"),
    )?;
    fs::copy(
        repo_root.join("deploy/device-runtime/module/module.prop"),
        release_root.join("module.prop"),
    )?;
    fs::copy(
        &runtime_supervisor_bin,
        release_root.join("bin/runtime-supervisor"),
    )?;
    fs::copy(&host_daemon_bin, release_root.join("bin/host-daemon"))?;
    fs::copy(&sing_box_bin, release_root.join("bin/sing-box"))?;
    fs::write(release_root.join("bin/curl"), CURL_SHIM)?;

    let host_rendered = if let Some(path) = &args.host_daemon_config_path {
        fs::read_to_string(resolve_path(&repo_root, path))?
    } else {
        let template = fs::read_to_string(
            repo_root.join("deploy/device-runtime/templates/host-daemon.base.json"),
        )?;
        render_template(
            &template,
            &[
                ("NODE_ID", manifest.device_id.as_str()),
                ("NODE_NAME", manifest.node_name.as_str()),
                ("ADMIN_TOKEN", admin_token.as_str()),
                ("CONTROL_PLANE_URL", manifest.control_plane_url.as_str()),
                ("DEVICE_TOKEN", device_token.as_str()),
                ("OPERATOR_PROFILE", profile.operator_profile.as_str()),
                ("TUNNEL_OWNER", args.tunnel_owner.as_str()),
                (
                    "PROXY_LISTEN_ADDRESS",
                    proxy_listen_address(&args.tunnel_owner),
                ),
                (
                    "WIREGUARD_ENABLED",
                    bool_literal(args.tunnel_owner != "first_party_reverse_tunnel"),
                ),
                (
                    "REVERSE_TUNNEL_ENABLED",
                    bool_literal(args.tunnel_owner == "first_party_reverse_tunnel"),
                ),
                (
                    "REVERSE_TUNNEL_ADDR",
                    &reverse_tunnel_addr(&manifest, &args.tunnel_owner)?,
                ),
                ("REVERSE_TUNNEL_SERVER_NAME", "mobile-proxy-relay"),
                (
                    "REVERSE_TUNNEL_CERT_DER_B64",
                    &reverse_tunnel_cert_der_b64(&manifest, &args.tunnel_owner)?,
                ),
                (
                    "AIRPLANE_HOLD_SECS",
                    &profile.airplane_hold_secs.to_string(),
                ),
            ],
        )
    };
    if args.tunnel_owner == "first_party_vpn_service" {
        let phone_private_key = required_env(
            manifest
                .tokens
                .wireguard_phone_private_key_env
                .as_deref()
                .unwrap_or("MOBILE_PROXY_WG_PHONE_PRIVATE_KEY"),
        )?;
        let server_public_key = required_env(
            manifest
                .tokens
                .wireguard_server_public_key_env
                .as_deref()
                .unwrap_or("MOBILE_PROXY_WG_SERVER_PUBLIC_KEY"),
        )?;
        let relay = manifest
            .relay
            .as_ref()
            .context("first_party_vpn_service requires relay host in device manifest")?;
        let template = fs::read_to_string(
            repo_root.join("deploy/device-runtime/templates/app-wireguard.conf"),
        )?;
        let rendered = render_template(
            &template,
            &[
                ("WG_PHONE_PRIVATE_KEY", phone_private_key.as_str()),
                ("WG_SERVER_PUBLIC_KEY", server_public_key.as_str()),
                ("WG_ENDPOINT_HOST", relay.host.as_str()),
                (
                    "WG_ENDPOINT_PORT",
                    &relay.wireguard_port.unwrap_or(51820).to_string(),
                ),
            ],
        );
        fs::write(release_root.join("config/app-wireguard.conf"), rendered)?;
    }

    let sing_box_rendered = if let Some(path) = &args.sing_box_config_path {
        fs::read_to_string(resolve_path(&repo_root, path))?
    } else {
        let template = fs::read_to_string(
            repo_root.join("deploy/device-runtime/templates/sing-box.base.json"),
        )?;
        render_template(
            &template,
            &[
                ("RELAY_USER", relay_user.as_str()),
                ("RELAY_PASSWORD", relay_password.as_str()),
                (
                    "SING_BOX_LISTEN_HOST",
                    sing_box_listen_host(&args.tunnel_owner),
                ),
            ],
        )
    };

    fs::write(release_root.join("config/host-daemon.json"), host_rendered)?;
    fs::write(release_root.join("config/sing-box.json"), sing_box_rendered)?;
    write_checksums(&release_root)?;

    println!("{}", release_root.display());
    Ok(())
}

fn validate_tunnel_owner(raw: &str) -> Result<()> {
    match raw {
        "stock_wireguard_bridge" | "first_party_vpn_service" | "first_party_reverse_tunnel" => {
            Ok(())
        }
        _ => bail!(
            "invalid tunnel owner {}; expected stock_wireguard_bridge, first_party_vpn_service, or first_party_reverse_tunnel",
            raw
        ),
    }
}

fn bool_literal(value: bool) -> &'static str {
    if value { "true" } else { "false" }
}

fn proxy_listen_address(tunnel_owner: &str) -> &'static str {
    if tunnel_owner == "first_party_reverse_tunnel" {
        "127.0.0.1:1080"
    } else {
        "10.66.66.2:1080"
    }
}

fn sing_box_listen_host(tunnel_owner: &str) -> &'static str {
    if tunnel_owner == "first_party_reverse_tunnel" {
        "127.0.0.1"
    } else {
        "10.66.66.2"
    }
}

fn reverse_tunnel_addr(manifest: &DeviceManifest, tunnel_owner: &str) -> Result<String> {
    if tunnel_owner != "first_party_reverse_tunnel" {
        return Ok("127.0.0.1:18090".into());
    }
    let relay = manifest
        .relay
        .as_ref()
        .context("first_party_reverse_tunnel requires relay host in device manifest")?;
    Ok(format!("{}:{}", relay.host, 18090))
}

fn reverse_tunnel_cert_der_b64(manifest: &DeviceManifest, tunnel_owner: &str) -> Result<String> {
    if tunnel_owner != "first_party_reverse_tunnel" {
        return Ok(String::new());
    }
    required_env(
        manifest
            .tokens
            .reverse_tunnel_cert_der_b64_env
            .as_deref()
            .unwrap_or("MOBILE_PROXY_REVERSE_TUNNEL_CERT_DER_B64"),
    )
}

fn repo_root() -> Result<PathBuf> {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../..")
        .canonicalize()
        .context("failed to resolve repo root")
}

fn resolve_path(repo_root: &Path, raw: &str) -> PathBuf {
    let path = Path::new(raw);
    if path.is_absolute() {
        path.to_path_buf()
    } else {
        repo_root.join(path)
    }
}

fn required_env(name: &str) -> Result<String> {
    env::var(name).with_context(|| format!("missing required environment variable: {name}"))
}

fn ensure_file(path: &Path) -> Result<()> {
    if path.is_file() {
        Ok(())
    } else {
        bail!("missing required file: {}", path.display())
    }
}

fn ensure_android_arm_binary(path: &Path) -> Result<()> {
    ensure_file(path)?;
    let mut header = [0_u8; 20];
    let mut file = fs::File::open(path)
        .with_context(|| format!("failed to open binary {}", path.display()))?;
    file.read_exact(&mut header)
        .with_context(|| format!("failed to read ELF header {}", path.display()))?;
    if !is_android_arm_elf_header(&header) {
        bail!(
            "runtime binary is not Android ARM 32-bit ELF: {}",
            path.display()
        );
    }
    Ok(())
}

fn is_android_arm_elf_header(header: &[u8; 20]) -> bool {
    let magic = &header[0..4] == b"\x7FELF";
    let elf32 = header[4] == 1;
    let little_endian = header[5] == 1;
    let machine = u16::from_le_bytes([header[18], header[19]]);
    magic && elf32 && little_endian && machine == 40
}

fn render_template(template: &str, values: &[(&str, &str)]) -> String {
    let mut rendered = template.to_string();
    for (key, value) in values {
        rendered = rendered.replace(&format!("{{{{{key}}}}}"), value);
    }
    rendered
}

fn write_checksums(root: &Path) -> Result<()> {
    let mut files = Vec::new();
    collect_files(root, root, &mut files)?;
    files.sort_by(|a, b| a.0.cmp(&b.0));
    let mut lines = Vec::new();
    for (relative, absolute) in files {
        let mut file = fs::File::open(&absolute)?;
        let mut hasher = Sha256::new();
        let mut buf = [0_u8; 8192];
        loop {
            let read = file.read(&mut buf)?;
            if read == 0 {
                break;
            }
            hasher.update(&buf[..read]);
        }
        let digest = hasher.finalize();
        lines.push(format!("{digest:x} *{relative}"));
    }
    fs::write(root.join("checksums.sha256"), lines.join("\n"))?;
    Ok(())
}

fn collect_files(root: &Path, dir: &Path, out: &mut Vec<(String, PathBuf)>) -> Result<()> {
    for entry in fs::read_dir(dir)? {
        let entry = entry?;
        let path = entry.path();
        if path.is_dir() {
            collect_files(root, &path, out)?;
        } else if path.is_file() {
            let relative = path
                .strip_prefix(root)
                .context("failed to compute relative path")?
                .to_string_lossy()
                .replace('\\', "/");
            out.push((relative, path));
        }
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::{is_android_arm_elf_header, render_template};

    #[test]
    fn template_render_replaces_all_tokens() {
        let rendered = render_template(
            "hello {{NAME}} {{NAME}} {{PLACE}}",
            &[("NAME", "world"), ("PLACE", "here")],
        );
        assert_eq!(rendered, "hello world world here");
    }

    #[test]
    fn android_arm_elf_header_is_recognized() {
        let mut header = [0_u8; 20];
        header[0..4].copy_from_slice(b"\x7FELF");
        header[4] = 1;
        header[5] = 1;
        header[18..20].copy_from_slice(&40_u16.to_le_bytes());
        assert!(is_android_arm_elf_header(&header));

        header[4] = 2;
        assert!(!is_android_arm_elf_header(&header));
    }
}
