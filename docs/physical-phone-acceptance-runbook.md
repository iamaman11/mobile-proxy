# Immutable-SHA Physical Phone Acceptance Runbook

Status: executable external gate for delivery item 15  
Prerequisite: successful `Software Release Candidate` evidence for the exact candidate SHA

## 1. Freeze the candidate and evidence

Download `release-candidate-evidence.json` from the artifact named:

`software-release-candidate-<candidate-sha>`

Use a clean detached checkout of that exact SHA:

```bash
git fetch --all --tags
git checkout --detach <candidate-sha>
test "$(git rev-parse HEAD)" = "<candidate-sha>"
test -z "$(git status --porcelain)"
```

Record candidate SHA, workflow run URL, phone identifier, Android version, operator/SIM, VM identifier, tester and UTC timestamps. Never record tokens or proxy credentials.

## 2. Prepare API access and secret environment

Forward the phone host API to the workstation:

```bash
adb -s <adb-serial> forward tcp:18088 tcp:8088
```

The control-plane TLS certificate is intentionally pinned/private. Copy its public PEM certificate from the VM and make `mobile-proxy-relay` resolve to that VM through controlled DNS or the workstation hosts file. Then set:

```bash
export SSL_CERT_FILE="$PWD/control-plane.crt"
export HOST_ADMIN_TOKEN='<host-daemon admin token>'
export CONTROL_PLANE_ADMIN_TOKEN='<control-plane admin token>'
export PROXY_USERNAME='<relay proxy username>'
export PROXY_PASSWORD='<relay proxy password>'
```

The proxy username and password must equal the values rendered into both phone release variants.

## 3. Build two phone variants and one VM release from the same SHA

Use distinct release IDs so rollback never modifies an already verified package:

```bash
RELEASE_BASE="physical-<candidate-sha-short>"
REVERSE_RELEASE="${RELEASE_BASE}-reverse"
WIREGUARD_RELEASE="${RELEASE_BASE}-wireguard"
VM_RELEASE="${RELEASE_BASE}-vm"
```

Package both phone variants:

```bash
cargo run --release -p operator-cli -- package-device-release \
  --manifest-path <device-manifest> \
  --release-id "$REVERSE_RELEASE" \
  --tunnel-owner first_party_reverse_tunnel

cargo run --release -p operator-cli -- package-device-release \
  --manifest-path <device-manifest> \
  --release-id "$WIREGUARD_RELEASE" \
  --tunnel-owner stock_wireguard_bridge
```

Build and deploy the VM release:

```bash
cargo run --release -p operator-cli -- provision-vm \
  --manifest-path <vm-manifest> \
  --release-id "$VM_RELEASE" \
  --ssh-user <vm-ssh-user> \
  --ssh-key <absolute-vm-ssh-key>
```

Packaging cleans each output root, creates a BLAKE3 manifest and verifies it before success. Do not edit packaged files afterward.

The stock WireGuard app must already contain the tunnel named `WiGandroid`; the runtime supervisor uses that exact existing compatibility tunnel. Creating/importing it and granting Android VPN consent are physical prerequisites.

## 4. Deploy and verify the primary reverse-tunnel variant

Install the reverse variant:

```bash
cargo run --release -p operator-cli -- install-device-release \
  --manifest-path <device-manifest> \
  --release-id "$REVERSE_RELEASE" \
  --device-serial <adb-serial> \
  --tunnel-owner first_party_reverse_tunnel
```

Force the VM public ports to the reverse-tunnel listeners and record the exact loaded Nginx config:

```bash
python3 scripts/switch_vm_proxy_transport.py \
  --mode reverse-tunnel \
  --project <gcp-project> \
  --zone <gcp-zone> \
  --instance <instance-name> \
  --ssh-user <vm-ssh-user> \
  --ssh-key <absolute-vm-ssh-key> \
  --output physical-vm-primary-switch.json
```

Verify every active phone release file byte-for-byte, infer the intended owner from the immutable package, verify that no Android VPN owns the reverse-tunnel deployment, and compare every installed VM release file by SHA-256 with the local package root:

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
  --output physical-primary-deployment.json
```

Do not continue unless the report has the candidate SHA, owner `first_party_reverse_tunnel`, all four identity booleans and `accepted=true`.

## 5. Configure the stage runner

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

The runner reads secrets only from environment variables. Proxy credentials are sent to `curl` through stdin configuration, never process arguments. `NO_PROXY` is cleared and `--noproxy ''` is forced.

Each stage checks six authenticated paths:

- SOCKS5, HTTP and HTTPS/CONNECT on mixed port `1080`;
- SOCKS5 on `1081`;
- HTTP and HTTPS/CONNECT on `3128`.

It also requires the exact device ID, `serving=true`, an available durable device record, a recent heartbeat, cellular-route readiness, proxy-bind readiness and local-serving readiness. Reverse stages additionally require WireGuard disabled and no active `tun0`.

## 6. Primary QUIC, reboot, fallback and recovery

Clean startup and fresh QUIC:

```bash
python3 scripts/run_physical_phone_acceptance.py \
  --stage online "${COMMON_ARGS[@]}" \
  --output physical-online.json
```

Reboot the phone or restart the production phone-side service without deleting VM SQLite state. After the same device returns with fresh QUIC:

```bash
python3 scripts/run_physical_phone_acceptance.py \
  --stage post-reboot "${COMMON_ARGS[@]}" \
  --output physical-post-reboot.json
```

Block only QUIC UDP `18090` between phone and VM. Leave certificate-pinned TLS/TCP `443` reachable, force a new tunnel attempt, wait for fresh `tls_tcp`, then run:

```bash
python3 scripts/run_physical_phone_acceptance.py \
  --stage fallback "${COMMON_ARGS[@]}" \
  --output physical-fallback.json
```

Remove the UDP block, terminate the reserve connection through the production service manager, wait for fresh QUIC, then run:

```bash
python3 scripts/run_physical_phone_acceptance.py \
  --stage recovered "${COMMON_ARGS[@]}" \
  --output physical-recovered.json
```

## 7. Deploy and prove WireGuard rollback

Install the separately packaged WireGuard variant. The supervisor must activate the existing `WiGandroid` stock tunnel and obtain `tun0` plus a recent handshake:

```bash
cargo run --release -p operator-cli -- install-device-release \
  --manifest-path <device-manifest> \
  --release-id "$WIREGUARD_RELEASE" \
  --device-serial <adb-serial> \
  --tunnel-owner stock_wireguard_bridge
```

Switch public ports atomically to the VM WireGuard proxy listeners. The switcher restores the previous Nginx config automatically if validation fails:

```bash
python3 scripts/switch_vm_proxy_transport.py \
  --mode wireguard \
  --project <gcp-project> \
  --zone <gcp-zone> \
  --instance <instance-name> \
  --ssh-user <vm-ssh-user> \
  --ssh-key <absolute-vm-ssh-key> \
  --output physical-vm-wireguard-switch.json
```

Verify the active WireGuard phone variant, actual Android VPN owner `com.wireguard.android`, and unchanged VM release:

```bash
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

Run the rollback stage only after health reports owner `stock_wireguard_bridge`, `tun0_present=true`, `wg_handshake_recent=true`, and no active reverse tunnel:

```bash
python3 scripts/run_physical_phone_acceptance.py \
  --stage wireguard "${COMMON_ARGS[@]}" \
  --output physical-wireguard.json
```

## 8. Restore the primary variant and prove final QUIC

Switch VM public ports back to reverse tunnel:

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

Reapply the original reverse variant through the full controlled install lifecycle. Do not use the lightweight symlink-only rollback path for this acceptance: the full installer stops the active watchdog and processes, activates the intended package and starts it cleanly.

```bash
cargo run --release -p operator-cli -- install-device-release \
  --manifest-path <device-manifest> \
  --release-id "$REVERSE_RELEASE" \
  --device-serial <adb-serial> \
  --tunnel-owner first_party_reverse_tunnel
```

Re-run exact deployment and Android VPN-owner verification against the reverse package:

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

Wait for owner `first_party_reverse_tunnel`, WireGuard disabled, no `tun0`, and fresh QUIC, then run:

```bash
python3 scripts/run_physical_phone_acceptance.py \
  --stage post-wireguard-recovered "${COMMON_ARGS[@]}" \
  --output physical-post-wireguard-recovered.json
```

## 9. Verify the entire report set

```bash
python3 scripts/verify_physical_phone_acceptance_reports.py \
  --evidence ./release-candidate-evidence.json \
  --primary-deployment physical-primary-deployment.json \
  --wireguard-deployment physical-wireguard-deployment.json \
  --final-deployment physical-final-deployment.json \
  --primary-switch physical-vm-primary-switch.json \
  --wireguard-switch physical-vm-wireguard-switch.json \
  --reverse-switch physical-vm-reverse-switch.json \
  --online physical-online.json \
  --post-reboot physical-post-reboot.json \
  --fallback physical-fallback.json \
  --recovered physical-recovered.json \
  --wireguard physical-wireguard.json \
  --post-wireguard-recovered physical-post-wireguard-recovered.json \
  --output physical-acceptance-summary.json
```

The gate passes only when the summary contains one candidate SHA, one device ID, three owner-bound deployment checks, all three accepted VM transport switches, all six accepted stages, `physical_phone_acceptance_complete=true` and `accepted=true`.

Attach only the bounded JSON reports and operator timestamps to issue #64. Never attach tokens, private keys, raw configuration, credential-bearing URLs or unrestricted logs.

## 10. Stop conditions

Reject the candidate for any unresolved P0/P1 defect, SHA mismatch, dirty checkout, failed package/deployment identity, wrong Android VPN owner, missing device, missing heartbeat, unavailable cellular route, failed authenticated protocol path, stale/mismatched tunnel authority, plaintext downgrade, missing or lingering `tun0`, stale WireGuard handshake, failed VM transport switch, inability to return to QUIC or any report-set mismatch.

After any source change, rerun the complete `Software Release Candidate` workflow on the new immutable SHA, download its new evidence artifact, rebuild all three release variants and repeat this procedure from the beginning.
