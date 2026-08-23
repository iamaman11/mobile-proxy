use std::env;
use std::fs;
use std::io::Read;
use std::path::{Path, PathBuf};
use std::process::Command;

use anyhow::{Context, Result, bail};
use mobile_proxy_foundation::{ContentDigest, DigestDomain};
use serde::Deserialize;
use serde_json::Value;

use crate::cli::PackageDeviceReleaseArgs;
use crate::device_support::{
    ANDROID_EGRESS_TUNNEL_OWNER, APP_OWNED_TUNNEL_OWNER, PRIMARY_TUNNEL_OWNER,
    STOCK_WIREGUARD_OWNER, validate_release_id, validate_tunnel_owner,
};
use crate::release_integrity::{verify_integrity_manifest, write_integrity_manifest};

const CURL_SHIM: &str = r#"#!/system/bin/sh
set -eu
umask 077

LOG_FILE="/data/adb/mobile-proxy-node/logs/curl-shim.log"
max_time=5
url=""
proxy_url=""
proxy_user=""

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
  if [ -n "$effective_proxy" ]; then
    if [ -n "$WGET_BIN" ]; then
      http_proxy="$effective_proxy" https_proxy="$effective_proxy" "$WGET_BIN" wget -Y on -qO- --timeout "$max_time" "$url" 2>/dev/null
    else
      http_proxy="$effective_proxy" https_proxy="$effective_proxy" wget -Y on -qO- --timeout "$max_time" "$url" 2>/dev/null
    fi
  elif [ -n "$WGET_BIN" ]; then
    "$WGET_BIN" wget -qO- --timeout "$max_time" "$url" 2>/dev/null
  else
    wget -qO- --timeout "$max_time" "$url" 2>/dev/null
  fi
}

if run_wget; then
  echo "$(date '+%Y-%m-%dT%H:%M:%S%z') result:ok" >> "$LOG_FILE" 2>/dev/null || true
  exit 0
fi

echo "$(date '+%Y-%m-%dT%H:%M:%S%z') result:fail" >> "$LOG_FILE" 2>/dev/null || true
exit 1
"#;

const UI_CONTROL_TOKEN_DOMAIN: DigestDomain =
    DigestDomain::new("mobile-proxy/local-ui-control-token/v1");

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
    #[serde(rename = "uiTokenEnv")]
    ui_token_env: String,
    #[serde(rename = "relayUserEnv")]
    relay_user_env: String,
    #[serde(rename = "relayPasswordEnv")]
    relay_password_env: String,
    #[serde(rename = "reverseTunnelCertDerB64Env")]
    reverse_tunnel_cert_der_b64_env: Option<String>,
}

#[derive(Debug, Deserialize)]
struct ManifestRelay {
    host: String,
}

#[derive(Debug, Deserialize)]
struct DeviceProfile {
    operator_profile: String,
    airplane_hold_secs: u64,
}

pub fn package_device_release(args: &PackageDeviceReleaseArgs) -> Result<()> {
    validate_release_id(&args.release_id)?;
    validate_tunnel_owner(&args.tunnel_owner)?;
    let root = repo_root()?;
    ensure_clean_worktree(&root)?;
    let manifest_path = resolve_path(&root, &args.manifest_path);
    let manifest: DeviceManifest = serde_json::from_str(
        &fs::read_to_string(&manifest_path)
            .with_context(|| format!("failed to read manifest {}", manifest_path.display()))?,
    )
    .with_context(|| format!("failed to parse manifest {}", manifest_path.display()))?;
    validate_manifest(&manifest)?;

    let profile_name = manifest.operator_profile.as_deref().unwrap_or("default");
    validate_profile_name(profile_name)?;
    let profile_path = root
        .join("deploy/device-runtime/profiles")
        .join(format!("{profile_name}.json"));
    let profile: DeviceProfile = serde_json::from_str(
        &fs::read_to_string(&profile_path)
            .with_context(|| format!("failed to read profile {}", profile_path.display()))?,
    )
    .with_context(|| format!("failed to parse profile {}", profile_path.display()))?;
    validate_profile_name(&profile.operator_profile)?;

    let admin_token = required_env(&manifest.tokens.admin_token_env)?;
    let device_token = required_env(&manifest.tokens.device_token_env)?;
    let control_plane_ui_token = required_env(&manifest.tokens.ui_token_env)?;
    let relay_user = required_env(&manifest.tokens.relay_user_env)?;
    let relay_password = required_env(&manifest.tokens.relay_password_env)?;
    let ui_control_token = stable_ui_control_token(&manifest.device_id, &admin_token);

    let bin_dir = root.join("deploy/device-runtime/bin");
    let runtime_supervisor_bin = bin_dir.join("runtime-supervisor");
    let host_daemon_bin = bin_dir.join("host-daemon");
    let sing_box_bin = bin_dir.join("sing-box");
    ensure_android_arm_binary(&runtime_supervisor_bin)?;
    ensure_runtime_owner_support(&runtime_supervisor_bin, &args.tunnel_owner)?;
    ensure_android_arm_binary(&host_daemon_bin)?;
    ensure_android_arm_binary(&sing_box_bin)?;

    let release_root = resolve_path(&root, &args.output_dir).join(&args.release_id);
    if release_root.exists() {
        fs::remove_dir_all(&release_root)
            .with_context(|| format!("failed to clean {}", release_root.display()))?;
    }
    fs::create_dir_all(release_root.join("bin"))?;
    fs::create_dir_all(release_root.join("config"))?;

    fs::copy(
        root.join("deploy/device-runtime/module/service.sh"),
        release_root.join("service.sh"),
    )?;
    fs::copy(
        root.join("deploy/device-runtime/module/module.prop"),
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
        let body = fs::read_to_string(resolve_path(&root, path))?;
        validate_host_config(&body, &args.tunnel_owner)?;
        body
    } else {
        let template =
            fs::read_to_string(root.join("deploy/device-runtime/templates/host-daemon.base.json"))?;
        let relay_host = manifest
            .relay
            .as_ref()
            .map(|relay| relay.host.as_str())
            .unwrap_or("34.118.88.54");
        let reverse_cert = reverse_tunnel_cert_der_b64(&manifest, &args.tunnel_owner)?;
        let strings = [
            ("NODE_ID", manifest.device_id.as_str()),
            ("NODE_NAME", manifest.node_name.as_str()),
            ("ADMIN_TOKEN", admin_token.as_str()),
            ("UI_CONTROL_TOKEN", ui_control_token.as_str()),
            ("RELAY_USER", relay_user.as_str()),
            ("RELAY_PASSWORD", relay_password.as_str()),
            ("CONTROL_PLANE_URL", manifest.control_plane_url.as_str()),
            ("CONTROL_PLANE_RESOLVE_ADDR", &format!("{relay_host}:8443")),
            ("DEVICE_TOKEN", device_token.as_str()),
            ("CONTROL_PLANE_UI_TOKEN", control_plane_ui_token.as_str()),
            ("OPERATOR_PROFILE", profile.operator_profile.as_str()),
            ("TUNNEL_OWNER", args.tunnel_owner.as_str()),
            (
                "PROXY_LISTEN_ADDRESS",
                proxy_listen_address(&args.tunnel_owner),
            ),
            (
                "LOCAL_PROXY_ADDRESS",
                proxy_listen_address(&args.tunnel_owner),
            ),
            (
                "REVERSE_TUNNEL_ADDR",
                &reverse_tunnel_addr(&manifest, &args.tunnel_owner)?,
            ),
            (
                "REVERSE_TUNNEL_TCP_ADDR",
                &reverse_tunnel_tcp_addr(&manifest, &args.tunnel_owner)?,
            ),
            ("REVERSE_TUNNEL_SERVER_NAME", "mobile-proxy-relay"),
            ("REVERSE_TUNNEL_CERT_DER_B64", reverse_cert.as_str()),
        ];
        let raw = [
            (
                "WIREGUARD_ENABLED",
                bool_literal(
                    args.tunnel_owner == STOCK_WIREGUARD_OWNER
                        || args.tunnel_owner == APP_OWNED_TUNNEL_OWNER,
                ),
            ),
            (
                "REVERSE_TUNNEL_ENABLED",
                bool_literal(uses_reverse_tunnel(&args.tunnel_owner)),
            ),
            (
                "AIRPLANE_HOLD_SECS",
                &profile.airplane_hold_secs.to_string(),
            ),
            ("APP_EGRESS_PORT", "18080"),
            (
                "REVERSE_TUNNEL_QUIC_ENABLED",
                bool_literal(args.tunnel_owner != ANDROID_EGRESS_TUNNEL_OWNER),
            ),
            (
                "REVERSE_TUNNEL_SOCKS5_ADDR",
                if args.tunnel_owner == ANDROID_EGRESS_TUNNEL_OWNER {
                    "\"127.0.0.1:18080\""
                } else {
                    "null"
                },
            ),
        ];
        let body = render_json_template(&template, &strings, &raw)?;
        validate_host_config(&body, &args.tunnel_owner)?;
        body
    };

    let sing_box_rendered = if let Some(path) = &args.sing_box_config_path {
        let body = fs::read_to_string(resolve_path(&root, path))?;
        validate_json(&body, "sing-box configuration")?;
        body
    } else {
        let template =
            fs::read_to_string(root.join("deploy/device-runtime/templates/sing-box.base.json"))?;
        let outbound = sing_box_outbound(
            &args.tunnel_owner,
            relay_user.as_str(),
            relay_password.as_str(),
        );
        render_json_template(
            &template,
            &[
                ("RELAY_USER", relay_user.as_str()),
                ("RELAY_PASSWORD", relay_password.as_str()),
                (
                    "SING_BOX_LISTEN_HOST",
                    sing_box_listen_host(&args.tunnel_owner),
                ),
                (
                    "SING_BOX_FINAL_OUTBOUND",
                    sing_box_final_outbound(&args.tunnel_owner),
                ),
            ],
            &[("PROXY_OUTBOUND", outbound.as_str())],
        )?
    };

    fs::write(release_root.join("config/host-daemon.json"), host_rendered)?;
    fs::write(release_root.join("config/sing-box.json"), sing_box_rendered)?;
    if args.tunnel_owner == APP_OWNED_TUNNEL_OWNER {
        let template =
            fs::read_to_string(root.join("deploy/device-runtime/templates/app-wireguard.conf"))?;
        let relay_host = manifest
            .relay
            .as_ref()
            .map(|relay| relay.host.as_str())
            .unwrap_or("34.118.88.54");
        let rendered = render_text_template(
            &template,
            &[
                (
                    "WG_PHONE_PRIVATE_KEY",
                    &required_env("MOBILE_PROXY_WG_PHONE_PRIVATE_KEY")?,
                ),
                (
                    "WG_SERVER_PUBLIC_KEY",
                    &required_env("MOBILE_PROXY_WG_SERVER_PUBLIC_KEY")?,
                ),
                ("WG_ENDPOINT_HOST", relay_host),
                ("WG_ENDPOINT_PORT", "51820"),
            ],
        )?;
        fs::write(release_root.join("config/app-wireguard.conf"), rendered)?;
    }
    write_release_metadata(&root, &release_root, &args.release_id)?;
    write_integrity_manifest(&release_root)?;
    verify_integrity_manifest(&release_root)?;

    println!("{}", release_root.display());
    Ok(())
}

fn stable_ui_control_token(device_id: &str, admin_token: &str) -> String {
    ContentDigest::derive(
        UI_CONTROL_TOKEN_DOMAIN,
        [device_id.as_bytes(), admin_token.as_bytes()],
    )
    .as_bytes()
    .iter()
    .map(|byte| format!("{byte:02x}"))
    .collect()
}

fn render_json_template(
    template: &str,
    strings: &[(&str, &str)],
    raw_values: &[(&str, &str)],
) -> Result<String> {
    let mut rendered = template.to_string();
    for (key, value) in strings {
        let placeholder = format!("\"{{{{{key}}}}}\"");
        if !rendered.contains(&placeholder) {
            bail!("JSON template is missing string placeholder {key}")
        }
        rendered = rendered.replace(&placeholder, &serde_json::to_string(value)?);
    }
    for (key, value) in raw_values {
        let placeholder = format!("{{{{{key}}}}}");
        if !rendered.contains(&placeholder) {
            bail!("JSON template is missing raw placeholder {key}")
        }
        rendered = rendered.replace(&placeholder, value);
    }
    if rendered.contains("{{") || rendered.contains("}}") {
        bail!("JSON template contains unresolved placeholders")
    }
    validate_json(&rendered, "rendered JSON template")?;
    Ok(rendered)
}

fn render_text_template(template: &str, values: &[(&str, &str)]) -> Result<String> {
    let mut rendered = template.to_string();
    for (key, value) in values {
        let placeholder = format!("{{{{{key}}}}}");
        if !rendered.contains(&placeholder) {
            bail!("text template is missing placeholder {key}")
        }
        rendered = rendered.replace(&placeholder, value);
    }
    if rendered.contains("{{") || rendered.contains("}}") {
        bail!("text template contains unresolved placeholders")
    }
    Ok(rendered)
}

fn validate_json(body: &str, label: &str) -> Result<Value> {
    serde_json::from_str(body).with_context(|| format!("{label} is invalid JSON"))
}

fn validate_host_config(body: &str, expected_owner: &str) -> Result<()> {
    let config = validate_json(body, "host-daemon configuration")?;
    validate_proxy_shape(&config)?;
    let owner = config
        .pointer("/wireguard/owner")
        .and_then(Value::as_str)
        .context("host-daemon tunnel owner is missing")?;
    if owner != expected_owner {
        bail!("host-daemon tunnel owner differs from requested package owner")
    }
    let wireguard_enabled = config
        .pointer("/wireguard/enabled")
        .and_then(Value::as_bool)
        .context("host-daemon wireguard.enabled is missing")?;
    let reverse_enabled = config
        .pointer("/reverse_tunnel/enabled")
        .and_then(Value::as_bool)
        .context("host-daemon reverse_tunnel.enabled is missing")?;
    match expected_owner {
        PRIMARY_TUNNEL_OWNER | ANDROID_EGRESS_TUNNEL_OWNER
            if !wireguard_enabled && reverse_enabled =>
        {
            Ok(())
        }
        STOCK_WIREGUARD_OWNER | APP_OWNED_TUNNEL_OWNER if wireguard_enabled && !reverse_enabled => {
            Ok(())
        }
        _ => bail!("host-daemon tunnel enable flags contradict requested owner"),
    }
}

fn validate_proxy_shape(config: &Value) -> Result<()> {
    let proxy = config
        .get("proxy")
        .and_then(Value::as_object)
        .context("host-daemon proxy configuration is missing")?;
    for required in ["listen_address", "username", "password"] {
        if !proxy.contains_key(required) {
            bail!("host-daemon proxy.{required} is missing");
        }
    }
    for key in proxy.keys() {
        if !matches!(
            key.as_str(),
            "listen_address" | "username" | "password" | "binary" | "args" | "working_dir" | "env"
        ) {
            bail!("host-daemon proxy contains unsupported field {key}");
        }
    }
    Ok(())
}

fn write_release_metadata(root: &Path, release_root: &Path, release_id: &str) -> Result<()> {
    let revision = Command::new("git")
        .args(["rev-parse", "HEAD"])
        .current_dir(root)
        .output()
        .context("failed to read Git revision for release metadata")?;
    if !revision.status.success() {
        bail!("git rev-parse HEAD failed while packaging release")
    }
    let git_sha = String::from_utf8_lossy(&revision.stdout).trim().to_string();
    if git_sha.len() != 40 || !git_sha.bytes().all(|byte| byte.is_ascii_hexdigit()) {
        bail!("Git revision is not a full commit SHA")
    }
    let metadata = serde_json::json!({
        "release_id": release_id,
        "git_sha": git_sha,
        "git_worktree_clean": true,
        "format_version": 1
    });
    fs::write(
        release_root.join("release-metadata.json"),
        serde_json::to_vec_pretty(&metadata)?,
    )?;
    Ok(())
}

fn ensure_clean_worktree(root: &Path) -> Result<()> {
    let status = Command::new("git")
        .args(["status", "--porcelain", "--untracked-files=normal"])
        .current_dir(root)
        .output()
        .context("failed to inspect Git worktree")?;
    if !status.status.success() {
        bail!("git status failed while packaging release")
    }
    if !status.stdout.is_empty() {
        bail!("device release packaging requires a clean Git worktree")
    }
    Ok(())
}

fn validate_manifest(manifest: &DeviceManifest) -> Result<()> {
    for (field, value) in [
        ("deviceId", manifest.device_id.as_str()),
        ("nodeName", manifest.node_name.as_str()),
        ("controlPlaneUrl", manifest.control_plane_url.as_str()),
    ] {
        validate_bounded_text(field, value, 512)?;
    }
    if let Some(relay) = &manifest.relay {
        validate_bounded_text("relay.host", &relay.host, 253)?;
    }
    Ok(())
}

fn validate_profile_name(value: &str) -> Result<()> {
    if value.is_empty()
        || value.len() > 64
        || !value
            .chars()
            .all(|character| character.is_ascii_alphanumeric() || matches!(character, '-' | '_'))
    {
        bail!("operator profile name is invalid")
    }
    Ok(())
}

fn validate_bounded_text(field: &str, value: &str, maximum: usize) -> Result<()> {
    if value.is_empty() || value.len() > maximum || value.chars().any(char::is_control) {
        bail!("{field} is invalid")
    }
    Ok(())
}

fn bool_literal(value: bool) -> &'static str {
    if value { "true" } else { "false" }
}

fn proxy_listen_address(tunnel_owner: &str) -> &'static str {
    if uses_reverse_tunnel(tunnel_owner) {
        "127.0.0.1:1080"
    } else {
        "10.66.66.2:1080"
    }
}

fn sing_box_listen_host(tunnel_owner: &str) -> &'static str {
    if uses_reverse_tunnel(tunnel_owner) {
        "127.0.0.1"
    } else {
        "10.66.66.2"
    }
}

fn sing_box_final_outbound(tunnel_owner: &str) -> &'static str {
    if tunnel_owner == ANDROID_EGRESS_TUNNEL_OWNER {
        "cellular-egress"
    } else {
        "direct"
    }
}

fn sing_box_outbound(tunnel_owner: &str, username: &str, password: &str) -> String {
    if tunnel_owner == ANDROID_EGRESS_TUNNEL_OWNER {
        serde_json::json!({
            "type": "socks",
            "tag": "cellular-egress",
            "server": "127.0.0.1",
            "server_port": 18080,
            "version": "5",
            "username": username,
            "password": password
        })
        .to_string()
    } else {
        serde_json::json!({"type": "direct", "tag": "direct"}).to_string()
    }
}

fn reverse_tunnel_addr(manifest: &DeviceManifest, tunnel_owner: &str) -> Result<String> {
    if !uses_reverse_tunnel(tunnel_owner) {
        return Ok("127.0.0.1:18090".into());
    }
    let relay = manifest
        .relay
        .as_ref()
        .context("first_party_reverse_tunnel requires relay host in device manifest")?;
    // UDP/443 gives QUIC the best chance of crossing carrier networks. TCP/443
    // remains an independently pinned TLS fallback when UDP is unavailable.
    Ok(format!("{}:443", relay.host))
}

fn reverse_tunnel_tcp_addr(manifest: &DeviceManifest, tunnel_owner: &str) -> Result<String> {
    if !uses_reverse_tunnel(tunnel_owner) {
        return Ok("127.0.0.1:443".into());
    }
    let relay = manifest
        .relay
        .as_ref()
        .context("first_party_reverse_tunnel requires relay config")?;
    Ok(format!("{}:443", relay.host))
}

fn reverse_tunnel_cert_der_b64(manifest: &DeviceManifest, tunnel_owner: &str) -> Result<String> {
    if !uses_reverse_tunnel(tunnel_owner) {
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

fn uses_reverse_tunnel(tunnel_owner: &str) -> bool {
    matches!(
        tunnel_owner,
        PRIMARY_TUNNEL_OWNER | ANDROID_EGRESS_TUNNEL_OWNER
    )
}

fn repo_root() -> Result<PathBuf> {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../..")
        .canonicalize()
        .context("failed to resolve repo root")
}

fn resolve_path(root: &Path, raw: &str) -> PathBuf {
    let path = Path::new(raw);
    if path.is_absolute() {
        path.to_path_buf()
    } else {
        root.join(path)
    }
}

fn required_env(name: &str) -> Result<String> {
    validate_bounded_text("environment variable name", name, 128)?;
    let value =
        env::var(name).with_context(|| format!("missing required environment variable: {name}"))?;
    validate_bounded_text(name, &value, 4096)?;
    Ok(value)
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
        )
    }
    Ok(())
}

fn ensure_runtime_owner_support(path: &Path, tunnel_owner: &str) -> Result<()> {
    let binary = fs::read(path)
        .with_context(|| format!("failed to read runtime binary {}", path.display()))?;
    if !binary_contains_marker(&binary, tunnel_owner.as_bytes()) {
        bail!(
            "runtime-supervisor does not support tunnel owner {tunnel_owner}; rebuild runtime binaries before packaging"
        )
    }
    if tunnel_owner == ANDROID_EGRESS_TUNNEL_OWNER
        && !binary_contains_marker(&binary, b"android-egress-mixed-proxy-v1")
    {
        bail!(
            "runtime-supervisor does not contain the Android egress mixed-proxy feature; rebuild runtime binaries before packaging"
        )
    }
    Ok(())
}

fn binary_contains_marker(binary: &[u8], marker: &[u8]) -> bool {
    !marker.is_empty() && binary.windows(marker.len()).any(|window| window == marker)
}

fn is_android_arm_elf_header(header: &[u8; 20]) -> bool {
    let magic = &header[0..4] == b"\x7FELF";
    let elf32 = header[4] == 1;
    let little_endian = header[5] == 1;
    let machine = u16::from_le_bytes([header[18], header[19]]);
    magic && elf32 && little_endian && machine == 40
}

#[cfg(test)]
mod tests {
    use super::{
        binary_contains_marker, is_android_arm_elf_header, proxy_listen_address,
        render_json_template, sing_box_final_outbound, sing_box_listen_host, sing_box_outbound,
        validate_host_config, validate_profile_name,
    };

    #[test]
    fn json_template_escapes_values_and_rejects_unresolved_placeholders() {
        let rendered = render_json_template(
            r#"{"value":"{{VALUE}}","enabled":{{ENABLED}}}"#,
            &[("VALUE", "a\"b\\c")],
            &[("ENABLED", "true")],
        )
        .unwrap();
        let parsed: serde_json::Value = serde_json::from_str(&rendered).unwrap();
        assert_eq!(parsed["value"], "a\"b\\c");
        assert_eq!(parsed["enabled"], true);
        assert!(render_json_template("{{MISSING}}", &[], &[]).is_err());
    }

    #[test]
    fn host_config_owner_and_flags_must_agree() {
        let reverse = r#"{"proxy":{"listen_address":"127.0.0.1:1080","username":"user","password":"pass"},"wireguard":{"enabled":false,"owner":"first_party_reverse_tunnel"},"reverse_tunnel":{"enabled":true}}"#;
        assert!(validate_host_config(reverse, "first_party_reverse_tunnel").is_ok());
        assert!(validate_host_config(reverse, "stock_wireguard_bridge").is_err());
    }

    #[test]
    fn host_config_accepts_shared_proxy_launcher_fields() {
        let valid = r#"{"proxy":{"listen_address":"127.0.0.1:1080","username":"user","password":"pass","binary":"/bin/sing-box","args":["run","-c","/tmp/sing-box.json"],"working_dir":"/tmp","env":{}},"wireguard":{"enabled":false,"owner":"first_party_reverse_tunnel"},"reverse_tunnel":{"enabled":true}}"#;
        assert!(validate_host_config(valid, "first_party_reverse_tunnel").is_ok());
    }

    #[test]
    fn profile_name_rejects_path_traversal() {
        assert!(validate_profile_name("mts_by").is_ok());
        assert!(validate_profile_name("../mts_by").is_err());
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

    #[test]
    fn runtime_owner_marker_rejects_stale_binary() {
        let binary = b"first_party_reverse_tunnel\0first_party_android_egress\0";
        assert!(binary_contains_marker(
            binary,
            b"first_party_android_egress"
        ));
        assert!(!binary_contains_marker(binary, b"stock_wireguard_bridge"));
    }

    #[test]
    fn android_egress_keeps_mixed_proxy_in_front_of_cellular_socks() {
        let owner = "first_party_android_egress";
        assert_eq!(proxy_listen_address(owner), "127.0.0.1:1080");
        assert_eq!(sing_box_listen_host(owner), "127.0.0.1");
        assert_eq!(sing_box_final_outbound(owner), "cellular-egress");
        let outbound: serde_json::Value =
            serde_json::from_str(&sing_box_outbound(owner, "user", "password")).unwrap();
        assert_eq!(outbound["type"], "socks");
        assert_eq!(outbound["server_port"], 18080);
    }
}
