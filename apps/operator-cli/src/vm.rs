use std::env;
use std::fs;
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::thread::sleep;
use std::time::Duration;

use anyhow::{Context, Result, bail};
use serde::Deserialize;
use sha2::{Digest, Sha256};

use crate::artifacts::ensure_elf_machine;
use crate::cli::{DeleteVmArgs, ProvisionVmArgs};

#[derive(Debug, Deserialize)]
struct VmManifest {
    project: String,
    zone: String,
    #[serde(rename = "instanceName")]
    instance_name: String,
    #[serde(rename = "machineType")]
    machine_type: Option<String>,
    #[serde(rename = "imageFamily")]
    image_family: Option<String>,
    #[serde(rename = "imageProject")]
    image_project: Option<String>,
    network: Option<String>,
    #[serde(rename = "staticExternalIp")]
    static_external_ip: Option<String>,
    tags: Option<Vec<String>>,
    tokens: VmTokenEnv,
    wireguard: VmWireguard,
}

#[derive(Debug, Deserialize)]
struct VmTokenEnv {
    #[serde(rename = "controlTokenEnv")]
    control_token_env: String,
    #[serde(rename = "deviceTokenEnv")]
    device_token_env: String,
    #[serde(rename = "reverseTunnelCertDerB64Env")]
    reverse_tunnel_cert_der_b64_env: String,
    #[serde(rename = "reverseTunnelKeyDerB64Env")]
    reverse_tunnel_key_der_b64_env: String,
    #[serde(rename = "relayUserEnv")]
    relay_user_env: String,
    #[serde(rename = "relayPasswordEnv")]
    relay_password_env: String,
}

#[derive(Debug, Deserialize)]
struct VmWireguard {
    #[serde(rename = "serverPrivateKeyEnv")]
    server_private_key_env: String,
    #[serde(rename = "phonePublicKeyEnv")]
    phone_public_key_env: String,
    #[serde(rename = "phoneAllowedIp")]
    phone_allowed_ip: Option<String>,
    #[serde(rename = "listenPort")]
    listen_port: Option<u16>,
}

struct VmSecrets {
    control_token: String,
    device_token: String,
    reverse_tunnel_cert_der_b64: String,
    reverse_tunnel_key_der_b64: String,
    relay_user: String,
    relay_password: String,
    server_private_key: String,
    phone_public_key: String,
}

pub fn provision_vm(args: &ProvisionVmArgs) -> Result<()> {
    let repo = repo_root()?;
    let manifest = load_manifest(&repo, &args.manifest_path)?;
    let secrets = load_secrets(&manifest)?;
    let ssh_key = expand_home(&args.ssh_key)?;
    let ssh_pub = fs::read_to_string(format!("{}.pub", ssh_key.display()))
        .with_context(|| format!("failed to read {}.pub", ssh_key.display()))?;

    build_linux_binaries(&repo)?;
    let release_root = build_vm_release(&repo, args, &manifest, &secrets)?;
    ensure_firewall_rules(&manifest)?;
    ensure_instance(args, &manifest, &ssh_pub)?;
    wait_for_ssh(args, &manifest, &ssh_key)?;
    if !args.create_only {
        deploy_release(args, &manifest, &ssh_key, &release_root)?;
        verify_vm(args, &manifest, &ssh_key)?;
    }
    println!(
        "VM provisioned: project={} zone={} instance={}",
        manifest.project, manifest.zone, manifest.instance_name
    );
    Ok(())
}

pub fn delete_vm(args: &DeleteVmArgs) -> Result<()> {
    let repo = repo_root()?;
    let manifest = load_manifest(&repo, &args.manifest_path)?;
    if gcloud_status([
        "compute",
        "instances",
        "describe",
        &manifest.instance_name,
        "--project",
        &manifest.project,
        "--zone",
        &manifest.zone,
    ])? {
        run(
            Command::new("gcloud")
                .arg("compute")
                .arg("instances")
                .arg("delete")
                .arg(&manifest.instance_name)
                .arg("--project")
                .arg(&manifest.project)
                .arg("--zone")
                .arg(&manifest.zone)
                .arg("--quiet"),
            Path::new("."),
        )?;
    }
    if args.delete_firewall_rules {
        for suffix in ["ingress", "control", "proxy"] {
            let name = format!("{}-{suffix}", manifest.instance_name);
            if gcloud_status([
                "compute",
                "firewall-rules",
                "describe",
                &name,
                "--project",
                &manifest.project,
            ])? {
                run(
                    Command::new("gcloud")
                        .arg("compute")
                        .arg("firewall-rules")
                        .arg("delete")
                        .arg(&name)
                        .arg("--project")
                        .arg(&manifest.project)
                        .arg("--quiet"),
                    Path::new("."),
                )?;
            }
        }
    }
    println!(
        "VM deleted: project={} zone={} instance={}",
        manifest.project, manifest.zone, manifest.instance_name
    );
    Ok(())
}

fn build_linux_binaries(repo: &Path) -> Result<()> {
    run(
        Command::new("cargo")
            .arg("build")
            .arg("--release")
            .arg("-p")
            .arg("control-plane")
            .arg("-p")
            .arg("relay-gate")
            .arg("-p")
            .arg("reverse-tunnel-server"),
        repo,
    )
}

fn build_vm_release(
    repo: &Path,
    args: &ProvisionVmArgs,
    manifest: &VmManifest,
    secrets: &VmSecrets,
) -> Result<PathBuf> {
    let release_root = repo.join(&args.output_dir).join(&args.release_id);
    if release_root.exists() {
        fs::remove_dir_all(&release_root)?;
    }
    fs::create_dir_all(release_root.join("bin"))?;
    fs::create_dir_all(release_root.join("config"))?;
    fs::create_dir_all(release_root.join("systemd"))?;
    fs::create_dir_all(release_root.join("nginx"))?;

    let control_plane = repo.join("target/release/control-plane");
    let relay_gate = repo.join("target/release/relay-gate");
    let reverse_tunnel_server = repo.join("target/release/reverse-tunnel-server");
    let sing_box = repo.join("deploy/vm-runtime/bin/sing-box");
    ensure_elf_machine(&control_plane, 62, "Linux x86_64 control-plane")?;
    ensure_elf_machine(&relay_gate, 62, "Linux x86_64 relay-gate")?;
    ensure_elf_machine(
        &reverse_tunnel_server,
        62,
        "Linux x86_64 reverse-tunnel-server",
    )?;
    ensure_elf_machine(&sing_box, 62, "Linux x86_64 sing-box")?;
    fs::copy(control_plane, release_root.join("bin/control-plane"))?;
    fs::copy(relay_gate, release_root.join("bin/relay-gate"))?;
    fs::copy(
        reverse_tunnel_server,
        release_root.join("bin/reverse-tunnel-server"),
    )?;
    fs::copy(sing_box, release_root.join("bin/sing-box"))?;

    fs::write(
        release_root.join("config/public-proxy.json"),
        public_proxy_config(secrets),
    )?;
    fs::write(
        release_root.join("config/wg0.conf"),
        wg_config(manifest, secrets),
    )?;
    fs::write(
        release_root.join("config/control-plane.env"),
        format!(
            "CONTROL_PLANE_LISTEN='0.0.0.0:8080'\nCONTROL_PLANE_BEARER_TOKEN='{}'\n",
            shell_escape(&secrets.control_token),
        ),
    )?;
    fs::write(
        release_root.join("config/relay-gate.env"),
        format!(
            "CONTROL_PLANE_BEARER_TOKEN='{}'\nCONTROL_PLANE_URL='http://127.0.0.1:8080'\nRELAY_GATE_DEVICE_ID='{}'\nRELAY_GATE_UPSTREAM='10.66.66.2:1080'\n",
            shell_escape(&secrets.control_token),
            "b4a6b2f4-5f6f-4fd1-baa4-b7d241b49a06"
        ),
    )?;
    fs::write(
        release_root.join("config/reverse-tunnel-server.env"),
        format!(
            "REVERSE_TUNNEL_LISTEN='0.0.0.0:18090'\nREVERSE_TUNNEL_PUBLIC_PROXY_LISTEN='127.0.0.1:14080,127.0.0.1:14081,127.0.0.1:14128'\nREVERSE_TUNNEL_AUTH_TOKEN='{}'\nREVERSE_TUNNEL_SERVER_NAME='mobile-proxy-relay'\nREVERSE_TUNNEL_CERT_DER_B64='{}'\nREVERSE_TUNNEL_KEY_DER_B64='{}'\n",
            shell_escape(&secrets.device_token),
            shell_escape(&secrets.reverse_tunnel_cert_der_b64),
            shell_escape(&secrets.reverse_tunnel_key_der_b64)
        ),
    )?;
    fs::write(
        release_root.join("systemd/mobile-relaycontrolpoint.service"),
        CONTROL_PLANE_UNIT,
    )?;
    fs::write(
        release_root.join("systemd/mobile-relay-gate.service"),
        RELAY_GATE_UNIT,
    )?;
    fs::write(
        release_root.join("systemd/mobile-public-proxy.service"),
        PUBLIC_PROXY_UNIT,
    )?;
    fs::write(
        release_root.join("systemd/mobile-reverse-tunnel-server.service"),
        REVERSE_TUNNEL_SERVER_UNIT,
    )?;
    fs::write(
        release_root.join("nginx/mobile-relaycontrolpoint"),
        NGINX_HTTP_CONFIG,
    )?;
    fs::write(
        release_root.join("nginx/mobile-public-proxy.conf"),
        NGINX_STREAM_CONFIG,
    )?;
    write_checksums(&release_root)?;
    Ok(release_root)
}

fn ensure_firewall_rules(manifest: &VmManifest) -> Result<()> {
    let tag = primary_tag(manifest);
    let rules = [
        (
            format!("{}-ingress", manifest.instance_name),
            "tcp:22,tcp:80,tcp:443,udp:18090,udp:51820",
        ),
        (format!("{}-control", manifest.instance_name), "tcp:8080"),
        (
            format!("{}-proxy", manifest.instance_name),
            "tcp:1080,tcp:1081,tcp:3128",
        ),
    ];
    for (name, ports) in rules {
        if gcloud_status([
            "compute",
            "firewall-rules",
            "describe",
            &name,
            "--project",
            &manifest.project,
        ])? {
            run(
                Command::new("gcloud")
                    .arg("compute")
                    .arg("firewall-rules")
                    .arg("update")
                    .arg(&name)
                    .arg("--project")
                    .arg(&manifest.project)
                    .arg("--allow")
                    .arg(ports),
                Path::new("."),
            )?;
            continue;
        }
        run(
            Command::new("gcloud")
                .arg("compute")
                .arg("firewall-rules")
                .arg("create")
                .arg(&name)
                .arg("--project")
                .arg(&manifest.project)
                .arg("--network")
                .arg(manifest.network.as_deref().unwrap_or("default"))
                .arg("--allow")
                .arg(ports)
                .arg("--source-ranges")
                .arg("0.0.0.0/0")
                .arg("--target-tags")
                .arg(tag),
            Path::new("."),
        )?;
    }
    Ok(())
}

fn ensure_instance(args: &ProvisionVmArgs, manifest: &VmManifest, ssh_pub: &str) -> Result<()> {
    if gcloud_status([
        "compute",
        "instances",
        "describe",
        &manifest.instance_name,
        "--project",
        &manifest.project,
        "--zone",
        &manifest.zone,
    ])? {
        return Ok(());
    }
    let startup = write_temp(
        "mobile-proxy-vm-bootstrap.sh",
        &bootstrap_script(&args.ssh_user, ssh_pub),
    )?;
    let mut command = Command::new("gcloud");
    command
        .arg("compute")
        .arg("instances")
        .arg("create")
        .arg(&manifest.instance_name)
        .arg("--project")
        .arg(&manifest.project)
        .arg("--zone")
        .arg(&manifest.zone)
        .arg("--machine-type")
        .arg(manifest.machine_type.as_deref().unwrap_or("e2-micro"))
        .arg("--image-family")
        .arg(manifest.image_family.as_deref().unwrap_or("debian-12"))
        .arg("--image-project")
        .arg(manifest.image_project.as_deref().unwrap_or("debian-cloud"))
        .arg("--network")
        .arg(manifest.network.as_deref().unwrap_or("default"))
        .arg("--tags")
        .arg(
            manifest
                .tags
                .clone()
                .unwrap_or_else(|| vec![primary_tag(manifest).into()])
                .join(","),
        )
        .arg("--metadata")
        .arg("enable-oslogin=FALSE")
        .arg("--metadata-from-file")
        .arg(format!("startup-script={}", startup.display()));
    if let Some(ip) = &manifest.static_external_ip {
        command.arg("--address").arg(ip);
    }
    run(&mut command, Path::new("."))
}

fn wait_for_ssh(args: &ProvisionVmArgs, manifest: &VmManifest, ssh_key: &Path) -> Result<()> {
    for _ in 0..60 {
        if ssh(args, manifest, ssh_key, "id >/dev/null").is_ok() {
            return Ok(());
        }
        sleep(Duration::from_secs(5));
    }
    bail!("VM SSH did not become ready")
}

fn deploy_release(
    args: &ProvisionVmArgs,
    manifest: &VmManifest,
    ssh_key: &Path,
    release_root: &Path,
) -> Result<()> {
    let remote_dir = format!("/tmp/mobile-proxy-vm-release-{}", args.release_id);
    let remote = format!(
        "{}@{}:{}",
        args.ssh_user, manifest.instance_name, remote_dir
    );
    run(
        Command::new("gcloud")
            .arg("compute")
            .arg("scp")
            .arg("--recurse")
            .arg("--project")
            .arg(&manifest.project)
            .arg("--zone")
            .arg(&manifest.zone)
            .arg("--ssh-key-file")
            .arg(ssh_key)
            .arg(release_root)
            .arg(remote),
        Path::new("."),
    )?;
    ssh(
        args,
        manifest,
        ssh_key,
        &format!(
            "sudo bash -c {}",
            shell_quote(&install_script(&args.release_id))
        ),
    )
}

fn verify_vm(args: &ProvisionVmArgs, manifest: &VmManifest, ssh_key: &Path) -> Result<()> {
    ssh(
        args,
        manifest,
        ssh_key,
        "sudo systemctl is-active mobile-relaycontrolpoint.service mobile-relay-gate.service mobile-public-proxy.service mobile-reverse-tunnel-server.service nginx.service wg-quick@wg0.service && sudo ss -lntup | grep -E ':(1080|1081|3128|8080|14080|14081|14128|18090) '",
    )
}

fn ssh(args: &ProvisionVmArgs, manifest: &VmManifest, ssh_key: &Path, command: &str) -> Result<()> {
    run(
        Command::new("gcloud")
            .arg("compute")
            .arg("ssh")
            .arg(format!("{}@{}", args.ssh_user, manifest.instance_name))
            .arg("--project")
            .arg(&manifest.project)
            .arg("--zone")
            .arg(&manifest.zone)
            .arg("--ssh-key-file")
            .arg(ssh_key)
            .arg("--command")
            .arg(command),
        Path::new("."),
    )
}

fn install_script(release_id: &str) -> String {
    format!(
        r#"set -euxo pipefail
REL='{release_id}'
SRC="/tmp/mobile-proxy-vm-release-{release_id}"
install -d /opt/mobile-relaycontrolpoint/releases/"$REL" /opt/mobile-public-proxy /etc/mobile-relaycontrolpoint /var/lib/mobile-relaycontrolpoint /etc/wireguard /etc/nginx/stream-available /etc/nginx/stream-enabled
install -m 0755 "$SRC/bin/control-plane" /opt/mobile-relaycontrolpoint/releases/"$REL"/control-plane
install -m 0755 "$SRC/bin/relay-gate" /opt/mobile-relaycontrolpoint/releases/"$REL"/relay-gate
install -m 0755 "$SRC/bin/reverse-tunnel-server" /opt/mobile-relaycontrolpoint/releases/"$REL"/reverse-tunnel-server
install -m 0755 "$SRC/bin/sing-box" /opt/mobile-public-proxy/sing-box
install -m 0600 "$SRC/config/control-plane.env" /etc/mobile-relaycontrolpoint/control-plane.env
install -m 0600 "$SRC/config/relay-gate.env" /etc/mobile-relaycontrolpoint/relay-gate.env
install -m 0600 "$SRC/config/reverse-tunnel-server.env" /etc/mobile-relaycontrolpoint/reverse-tunnel-server.env
install -m 0600 "$SRC/config/wg0.conf" /etc/wireguard/wg0.conf
install -m 0600 "$SRC/config/public-proxy.json" /opt/mobile-public-proxy/config.json
install -m 0644 "$SRC/systemd/mobile-relaycontrolpoint.service" /etc/systemd/system/mobile-relaycontrolpoint.service
install -m 0644 "$SRC/systemd/mobile-relay-gate.service" /etc/systemd/system/mobile-relay-gate.service
install -m 0644 "$SRC/systemd/mobile-public-proxy.service" /etc/systemd/system/mobile-public-proxy.service
install -m 0644 "$SRC/systemd/mobile-reverse-tunnel-server.service" /etc/systemd/system/mobile-reverse-tunnel-server.service
install -m 0644 "$SRC/nginx/mobile-relaycontrolpoint" /etc/nginx/sites-available/mobile-relaycontrolpoint
install -m 0644 "$SRC/nginx/mobile-public-proxy.conf" /etc/nginx/stream-available/mobile-public-proxy.conf
ln -sfn /opt/mobile-relaycontrolpoint/releases/"$REL" /opt/mobile-relaycontrolpoint/current
rm -f /etc/nginx/sites-enabled/default
ln -sfn /etc/nginx/sites-available/mobile-relaycontrolpoint /etc/nginx/sites-enabled/mobile-relaycontrolpoint
ln -sfn /etc/nginx/stream-available/mobile-public-proxy.conf /etc/nginx/stream-enabled/mobile-public-proxy.conf
grep -q 'stream-enabled' /etc/nginx/nginx.conf || printf '\nstream {{ include /etc/nginx/stream-enabled/*.conf; }}\n' >> /etc/nginx/nginx.conf
systemctl daemon-reload
systemctl enable --now wg-quick@wg0 mobile-relaycontrolpoint.service mobile-public-proxy.service nginx.service mobile-relay-gate.service mobile-reverse-tunnel-server.service
systemctl restart wg-quick@wg0 mobile-relaycontrolpoint.service mobile-public-proxy.service nginx.service mobile-relay-gate.service mobile-reverse-tunnel-server.service
nginx -t
"#
    )
}

fn bootstrap_script(ssh_user: &str, ssh_pub: &str) -> String {
    format!(
        r#"#!/bin/bash
set -euxo pipefail
USER_NAME='{ssh_user}'
PUB_KEY='{ssh_pub}'
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y ca-certificates curl nginx libnginx-mod-stream wireguard-tools openssh-server
if ! id -u "$USER_NAME" >/dev/null 2>&1; then
  useradd -m -s /bin/bash "$USER_NAME"
fi
install -d -m 700 -o "$USER_NAME" -g "$USER_NAME" "/home/$USER_NAME/.ssh"
printf '%s\n' "$PUB_KEY" > "/home/$USER_NAME/.ssh/authorized_keys"
chown "$USER_NAME:$USER_NAME" "/home/$USER_NAME/.ssh/authorized_keys"
chmod 600 "/home/$USER_NAME/.ssh/authorized_keys"
usermod -aG sudo "$USER_NAME"
printf '%s\n' "$USER_NAME ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/90-mobile-proxy
chmod 0440 /etc/sudoers.d/90-mobile-proxy
cat > /etc/ssh/sshd_config.d/99-mobile-proxy.conf <<'SSHD'
PubkeyAuthentication yes
AuthorizedKeysFile .ssh/authorized_keys
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitRootLogin prohibit-password
SSHD
systemctl restart ssh || systemctl restart sshd || true
"#
    )
}

fn public_proxy_config(secrets: &VmSecrets) -> String {
    format!(
        r#"{{
  "log": {{ "level": "info", "timestamp": true }},
  "inbounds": [
    {{ "type": "mixed", "tag": "mixed-public", "listen": "127.0.0.1", "listen_port": 11080, "users": [{{ "username": "{}", "password": "{}" }}], "set_system_proxy": false }},
    {{ "type": "socks", "tag": "socks-public", "listen": "127.0.0.1", "listen_port": 11081, "users": [{{ "username": "{}", "password": "{}" }}] }},
    {{ "type": "http", "tag": "http-public", "listen": "127.0.0.1", "listen_port": 13128, "users": [{{ "username": "{}", "password": "{}" }}], "set_system_proxy": false }}
  ],
  "outbounds": [
    {{ "type": "socks", "tag": "phone-upstream", "server": "10.66.66.2", "server_port": 1080, "version": "5", "username": "{}", "password": "{}" }}
  ],
  "route": {{ "final": "phone-upstream" }}
}}
"#,
        secrets.relay_user,
        secrets.relay_password,
        secrets.relay_user,
        secrets.relay_password,
        secrets.relay_user,
        secrets.relay_password,
        secrets.relay_user,
        secrets.relay_password
    )
}

fn wg_config(manifest: &VmManifest, secrets: &VmSecrets) -> String {
    format!(
        r#"[Interface]
Address = 10.66.66.1/24
ListenPort = {}
PrivateKey = {}
SaveConfig = false

[Peer]
PublicKey = {}
AllowedIPs = {}
PersistentKeepalive = 25
"#,
        manifest.wireguard.listen_port.unwrap_or(51820),
        secrets.server_private_key,
        secrets.phone_public_key,
        manifest
            .wireguard
            .phone_allowed_ip
            .as_deref()
            .unwrap_or("10.66.66.2/32")
    )
}

const CONTROL_PLANE_UNIT: &str = r#"[Unit]
Description=Mobile Relay Control Plane
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
EnvironmentFile=/etc/mobile-relaycontrolpoint/control-plane.env
ExecStart=/opt/mobile-relaycontrolpoint/current/control-plane
Restart=always
RestartSec=2
User=root

[Install]
WantedBy=multi-user.target
"#;

const RELAY_GATE_UNIT: &str = r#"[Unit]
Description=Mobile Relay Gate
After=network-online.target mobile-relaycontrolpoint.service mobile-public-proxy.service nginx.service
Wants=network-online.target mobile-public-proxy.service nginx.service

[Service]
Type=simple
EnvironmentFile=/etc/mobile-relaycontrolpoint/relay-gate.env
ExecStart=/opt/mobile-relaycontrolpoint/current/relay-gate
Restart=always
RestartSec=2
User=root

[Install]
WantedBy=multi-user.target
"#;

const PUBLIC_PROXY_UNIT: &str = r#"[Unit]
Description=Mobile Public Proxy Relay
After=network-online.target wg-quick@wg0.service
Wants=network-online.target wg-quick@wg0.service

[Service]
Type=simple
ExecStart=/opt/mobile-public-proxy/sing-box run -c /opt/mobile-public-proxy/config.json
Restart=always
RestartSec=2
User=root

[Install]
WantedBy=multi-user.target
"#;

const REVERSE_TUNNEL_SERVER_UNIT: &str = r#"[Unit]
Description=Mobile Reverse Tunnel Server
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
EnvironmentFile=/etc/mobile-relaycontrolpoint/reverse-tunnel-server.env
ExecStart=/opt/mobile-relaycontrolpoint/current/reverse-tunnel-server
Restart=always
RestartSec=2
User=root

[Install]
WantedBy=multi-user.target
"#;

const NGINX_HTTP_CONFIG: &str = r#"server {
    listen 80 default_server;
    listen [::]:80 default_server;
    server_name _;

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
"#;

const NGINX_STREAM_CONFIG: &str = r#"server { listen 0.0.0.0:1080; proxy_pass 127.0.0.1:14080; }
server { listen 0.0.0.0:1081; proxy_pass 127.0.0.1:14081; }
server { listen 0.0.0.0:3128; proxy_pass 127.0.0.1:14128; }
"#;

fn load_manifest(repo: &Path, raw: &str) -> Result<VmManifest> {
    let path = resolve_path(repo, raw);
    serde_json::from_str(&fs::read_to_string(&path)?)
        .with_context(|| format!("failed to parse VM manifest {}", path.display()))
}

fn load_secrets(manifest: &VmManifest) -> Result<VmSecrets> {
    Ok(VmSecrets {
        control_token: required_env(&manifest.tokens.control_token_env)?,
        device_token: required_env(&manifest.tokens.device_token_env)?,
        reverse_tunnel_cert_der_b64: required_env(
            &manifest.tokens.reverse_tunnel_cert_der_b64_env,
        )?,
        reverse_tunnel_key_der_b64: required_env(&manifest.tokens.reverse_tunnel_key_der_b64_env)?,
        relay_user: required_env(&manifest.tokens.relay_user_env)?,
        relay_password: required_env(&manifest.tokens.relay_password_env)?,
        server_private_key: required_env(&manifest.wireguard.server_private_key_env)?,
        phone_public_key: required_env(&manifest.wireguard.phone_public_key_env)?,
    })
}

fn primary_tag(manifest: &VmManifest) -> &str {
    manifest
        .tags
        .as_ref()
        .and_then(|tags| tags.first())
        .map(String::as_str)
        .unwrap_or("mobile-relay")
}

fn required_env(name: &str) -> Result<String> {
    env::var(name).with_context(|| format!("missing required environment variable: {name}"))
}

fn shell_escape(value: &str) -> String {
    value.replace('\'', "'\\''")
}

fn shell_quote(value: &str) -> String {
    format!("'{}'", shell_escape(value))
}

fn expand_home(raw: &str) -> Result<PathBuf> {
    if let Some(suffix) = raw.strip_prefix("~/") {
        Ok(Path::new(&env::var("HOME").context("HOME is not set")?).join(suffix))
    } else {
        Ok(PathBuf::from(raw))
    }
}

fn resolve_path(repo: &Path, raw: &str) -> PathBuf {
    let path = Path::new(raw);
    if path.is_absolute() {
        path.to_path_buf()
    } else {
        repo.join(path)
    }
}

fn write_temp(name: &str, body: &str) -> Result<PathBuf> {
    let path = env::temp_dir().join(name);
    fs::write(&path, body)?;
    Ok(path)
}

fn write_checksums(root: &Path) -> Result<()> {
    let mut files = Vec::new();
    collect_files(root, root, &mut files)?;
    files.sort_by(|a, b| a.0.cmp(&b.0));
    let mut lines = Vec::new();
    for (relative, absolute) in files {
        if relative == "SHA256SUMS" {
            continue;
        }
        let body = fs::read(&absolute)?;
        let mut hasher = Sha256::new();
        hasher.update(&body);
        lines.push(format!("{:x}  {}", hasher.finalize(), relative));
    }
    fs::write(root.join("SHA256SUMS"), lines.join("\n") + "\n")?;
    Ok(())
}

fn collect_files(root: &Path, current: &Path, files: &mut Vec<(String, PathBuf)>) -> Result<()> {
    for entry in fs::read_dir(current)? {
        let entry = entry?;
        let path = entry.path();
        if path.is_dir() {
            collect_files(root, &path, files)?;
        } else {
            files.push((
                path.strip_prefix(root)?
                    .to_string_lossy()
                    .replace('\\', "/"),
                path,
            ));
        }
    }
    Ok(())
}

fn gcloud_status<const N: usize>(args: [&str; N]) -> Result<bool> {
    let status = Command::new("gcloud")
        .args(args)
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .status()?;
    Ok(status.success())
}

fn run(command: &mut Command, cwd: &Path) -> Result<()> {
    let status = command.current_dir(cwd).status()?;
    if status.success() {
        Ok(())
    } else {
        bail!("command failed with status {status}: {:?}", command)
    }
}

fn repo_root() -> Result<PathBuf> {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../..")
        .canonicalize()
        .context("failed to resolve repo root")
}
