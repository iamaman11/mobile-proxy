# Immutable-SHA Physical Phone Acceptance Runbook

Status: executable external gate for delivery item 15  
Prerequisite: successful `Software Release Candidate` evidence for the exact candidate SHA

## 1. Freeze the candidate

Download `release-candidate-evidence.json` from `software-release-candidate-<candidate-sha>` and use a clean detached checkout:

```bash
git fetch --all --tags
git checkout --detach <candidate-sha>
test "$(git rev-parse HEAD)" = "<candidate-sha>"
test -z "$(git status --porcelain)"
```

Record the candidate SHA, workflow run, phone/Android/operator, VM, tester and UTC timestamps. Never record tokens or proxy credentials.

## 2. Prepare access and secrets

Forward the phone host API:

```bash
adb -s <adb-serial> forward tcp:18088 tcp:8088
```

Copy the control-plane public PEM certificate from the VM, make `mobile-proxy-relay` resolve to that VM through controlled DNS or the workstation hosts file, then set:

```bash
export SSL_CERT_FILE="$PWD/control-plane.crt"
export HOST_ADMIN_TOKEN='<host-daemon admin token>'
export CONTROL_PLANE_ADMIN_TOKEN='<control-plane admin token>'
export PROXY_USERNAME='<relay proxy username>'
export PROXY_PASSWORD='<relay proxy password>'
```

The proxy credentials must equal the values rendered into both phone variants.

## 3. Build immutable variants from the same SHA

```bash
RELEASE_BASE="physical-<candidate-sha-short>"
REVERSE_RELEASE="${RELEASE_BASE}-reverse"
WIREGUARD_RELEASE="${RELEASE_BASE}-wireguard"
VM_RELEASE="${RELEASE_BASE}-vm"

cargo run --release -p operator-cli -- package-device-release \
  --manifest-path <device-manifest> \
  --release-id "$REVERSE_RELEASE" \
  --tunnel-owner first_party_reverse_tunnel

cargo run --release -p operator-cli -- package-device-release \
  --manifest-path <device-manifest> \
  --release-id "$WIREGUARD_RELEASE" \
  --tunnel-owner stock_wireguard_bridge

cargo run --release -p operator-cli -- provision-vm \
  --manifest-path <vm-manifest> \
  --release-id "$VM_RELEASE" \
  --ssh-user <vm-ssh-user> \
  --ssh-key <absolute-vm-ssh-key>
```

Do not edit package roots after their BLAKE3 manifests are written. The stock WireGuard app must already contain the tunnel named `WiGandroid`, with Android VPN consent granted.

## 4. Deploy and verify the reverse-tunnel variant

```bash
cargo run --release -p operator-cli -- install-device-release \
  --manifest-path <device-manifest> \
  --release-id "$REVERSE_RELEASE" \
  --device-serial <adb-serial> \
  --tunnel-owner first_party_reverse_tunnel

python3 scripts/switch_vm_proxy_transport.py \
  --mode reverse-tunnel \
  --project <gcp-project> \
  --zone <gcp-zone> \
  --instance <instance-name> \
  --ssh-user <vm-ssh-user> \
  --ssh-key <absolute-vm-ssh-key> \
  --output physical-vm-primary-switch.json

python3 scripts/verify_physical_deployment.py \
  --evidence ./release-candidate-evidence.json \
  --device-release-root "target/device-releases/$REVERSE_RELEASE" \
  --device-serial <adb-serial> \
  --vm-release-root "target/vm-releases/$VM_RELEASE" \
  --vm-project <gcp-project> \
  --vm-zone <gcp-zone> \
  --vm-instance <instance-name> \
  --vm-ssh-user <vm-ssh-user> \
  --vm-ssh-key <absolute-vm-ssh-key> \
  --output physical-primary-deployment.json
```

The deployment report must contain the candidate SHA, owner `first_party_reverse_tunnel`, exact phone/VM file matches, no active Android VPN, and `accepted=true`.

## 5. Configure stage checks

```bash
COMMON_ARGS=(
  --evidence ./release-candidate-evidence.json
  --host-api-base http://127.0.0.1:18088
  --control-plane-base https://mobile-proxy-relay:8443
  --proxy-host <protected-proxy-host>
  --http-probe-url http://<controlled-http-probe>/
  --https-probe-url https://<controlled-https-probe>/
  --device-id <expected-node-id>
)
```

Every stage requires exact device identity, serving/cellular/proxy readiness, durable heartbeat and six authenticated proxy paths: SOCKS5, HTTP and CONNECT on mixed `1080`; SOCKS5 on `1081`; HTTP and CONNECT on `3128`. Proxy credentials are passed to `curl` through stdin, and proxy bypass variables are disabled.

## 6. QUIC, reboot, TLS/TCP fallback and recovery

```bash
python3 scripts/run_physical_phone_acceptance.py \
  --stage online "${COMMON_ARGS[@]}" \
  --output physical-online.json
```

Reboot the phone or restart its production service without deleting VM SQLite state. After the same device returns with fresh QUIC:

```bash
python3 scripts/run_physical_phone_acceptance.py \
  --stage post-reboot "${COMMON_ARGS[@]}" \
  --output physical-post-reboot.json
```

Block only QUIC UDP `18090`, leave certificate-pinned TLS/TCP `443` reachable, force a new tunnel attempt and wait for fresh `tls_tcp`:

```bash
python3 scripts/run_physical_phone_acceptance.py \
  --stage fallback "${COMMON_ARGS[@]}" \
  --output physical-fallback.json
```

Remove the block, terminate the reserve connection through the production service manager and wait for fresh QUIC:

```bash
python3 scripts/run_physical_phone_acceptance.py \
  --stage recovered "${COMMON_ARGS[@]}" \
  --output physical-recovered.json
```

## 7. Prove stock WireGuard rollback

```bash
cargo run --release -p operator-cli -- install-device-release \
  --manifest-path <device-manifest> \
  --release-id "$WIREGUARD_RELEASE" \
  --device-serial <adb-serial> \
  --tunnel-owner stock_wireguard_bridge

python3 scripts/switch_vm_proxy_transport.py \
  --mode wireguard \
  --project <gcp-project> \
  --zone <gcp-zone> \
  --instance <instance-name> \
  --ssh-user <vm-ssh-user> \
  --ssh-key <absolute-vm-ssh-key> \
  --output physical-vm-wireguard-switch.json

python3 scripts/verify_physical_deployment.py \
  --evidence ./release-candidate-evidence.json \
  --device-release-root "target/device-releases/$WIREGUARD_RELEASE" \
  --device-serial <adb-serial> \
  --vm-release-root "target/vm-releases/$VM_RELEASE" \
  --vm-project <gcp-project> \
  --vm-zone <gcp-zone> \
  --vm-instance <instance-name> \
  --vm-ssh-user <vm-ssh-user> \
  --vm-ssh-key <absolute-vm-ssh-key> \
  --output physical-wireguard-deployment.json
```

The deployment verifier must identify `com.wireguard.android` as the active Android VPN owner. After health reports owner `stock_wireguard_bridge`, `tun0_present=true`, a recent handshake and no active reverse tunnel:

```bash
python3 scripts/run_physical_phone_acceptance.py \
  --stage wireguard "${COMMON_ARGS[@]}" \
  --output physical-wireguard.json
```

## 8. Reactivate the exact installed reverse release

First restore the VM public mapping:

```bash
python3 scripts/switch_vm_proxy_transport.py \
  --mode reverse-tunnel \
  --project <gcp-project> \
  --zone <gcp-zone> \
  --instance <instance-name> \
  --ssh-user <vm-ssh-user> \
  --ssh-key <absolute-vm-ssh-key> \
  --output physical-vm-reverse-switch.json
```

Reactivate the already installed reverse release without rebuilding or copying it. This performs a full runtime/watchdog restart and records the exact active symlink:

```bash
python3 scripts/activate_device_release.py \
  --evidence ./release-candidate-evidence.json \
  --release-id "$REVERSE_RELEASE" \
  --device-serial <adb-serial> \
  --output physical-reverse-activation.json
```

Verify the same original package bytes and absence of an Android VPN:

```bash
python3 scripts/verify_physical_deployment.py \
  --evidence ./release-candidate-evidence.json \
  --device-release-root "target/device-releases/$REVERSE_RELEASE" \
  --device-serial <adb-serial> \
  --vm-release-root "target/vm-releases/$VM_RELEASE" \
  --vm-project <gcp-project> \
  --vm-zone <gcp-zone> \
  --vm-instance <instance-name> \
  --vm-ssh-user <vm-ssh-user> \
  --vm-ssh-key <absolute-vm-ssh-key> \
  --output physical-final-deployment.json
```

After owner `first_party_reverse_tunnel`, WireGuard disabled, no `tun0`, and fresh QUIC:

```bash
python3 scripts/run_physical_phone_acceptance.py \
  --stage post-wireguard-recovered "${COMMON_ARGS[@]}" \
  --output physical-post-wireguard-recovered.json
```

## 9. Verify the whole immutable report set

```bash
python3 scripts/verify_physical_phone_acceptance_reports.py \
  --evidence ./release-candidate-evidence.json \
  --primary-deployment physical-primary-deployment.json \
  --wireguard-deployment physical-wireguard-deployment.json \
  --final-deployment physical-final-deployment.json \
  --primary-switch physical-vm-primary-switch.json \
  --wireguard-switch physical-vm-wireguard-switch.json \
  --reverse-switch physical-vm-reverse-switch.json \
  --reverse-activation physical-reverse-activation.json \
  --online physical-online.json \
  --post-reboot physical-post-reboot.json \
  --fallback physical-fallback.json \
  --recovered physical-recovered.json \
  --wireguard physical-wireguard.json \
  --post-wireguard-recovered physical-post-wireguard-recovered.json \
  --output physical-acceptance-summary.json
```

The summary must contain one candidate SHA, one device ID, three owner-bound deployment checks, all three VM switches, accepted immutable release reactivation, all six stages, `physical_phone_acceptance_complete=true` and `accepted=true`.

Attach only bounded JSON reports and operator timestamps to issue #64. Never attach tokens, private keys, raw configuration, credential-bearing URLs or unrestricted logs.

## 10. Stop conditions

Reject the candidate for any P0/P1 defect, SHA or dirty-tree mismatch, package/deployment mismatch, wrong Android VPN owner, missing heartbeat or cellular route, failed authenticated protocol path, stale/mismatched tunnel authority, plaintext downgrade, missing or lingering `tun0`, stale WireGuard handshake, failed reversible VM switch, changed release bytes, inability to return to QUIC or any report-set mismatch.

Any source change requires a new immutable candidate, new evidence, rebuilt variants and a complete restart of this procedure.
