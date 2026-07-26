# Immutable-SHA Physical Phone Acceptance Runbook

Status: executable external gate for production baseline item 15  
Prerequisite: successful evidence v2 from `Software Release Candidate` for the exact candidate SHA

## 1. Freeze and verify the candidate

Download `release-candidate-evidence.json` from the artifact named `software-release-candidate-<candidate-sha>` and use a clean detached checkout:

```bash
git fetch --all --tags
git checkout --detach <candidate-sha>
test "$(git rev-parse HEAD)" = "<candidate-sha>"
test -z "$(git status --porcelain)"
python3 -m json.tool release-candidate-evidence.json >/dev/null
```

The evidence must state:

- `format_version=2`;
- `primary_runtime=first_party_reverse_tunnel`;
- `primary_runtime_requires_android_vpn=false`;
- `rollback_runtime=stock_wireguard_bridge`;
- `software_10_of_10_ready=true`;
- `physical_phone_acceptance_required=true`;
- `baseline_complete=false`.

Record candidate SHA, workflow run, artifact identity, phone model/Android/operator, VM identity, tester and UTC timestamps. Do not record tokens, keys or proxy credentials.

## 2. Environment prerequisites

Primary runtime prerequisites:

- rooted phone and working ADB;
- no active Android VPN;
- no requirement to install `apps/android-app`;
- relay VM provisioned from the same candidate;
- controlled DNS or hosts entry for the pinned relay name;
- controlled HTTP and HTTPS probes.

Rollback prerequisites, used only in the WireGuard stage:

- stock package `com.wireguard.android` installed;
- tunnel `WiGandroid` imported and valid;
- Android VPN consent granted;
- VM stock WireGuard backend configured.

`operator-cli` detects Windows `adb.exe` in WSL and queries its Windows-loopback forward through PowerShell, passing the bearer token only through stdin. For manual workstation troubleshooting only, forward the phone host API:

```bash
adb -s <adb-serial> forward tcp:18088 tcp:8088
```

Copy the relay control-plane public PEM certificate to the workstation, make `mobile-proxy-relay` resolve to the relay and export secrets only through environment variables:

```bash
export SSL_CERT_FILE="$PWD/control-plane.crt"
export HOST_ADMIN_TOKEN='<host-daemon admin token>'
export CONTROL_PLANE_ADMIN_TOKEN='<control-plane admin token>'
export PROXY_USERNAME='<proxy username>'
export PROXY_PASSWORD='<proxy password>'
```

The scripts pass proxy credentials through `curl` stdin configuration, disable proxy bypass variables and do not write credentials to reports.

## 3. Build immutable variants

All variants must be built from the same clean detached SHA:

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

Do not modify release roots after their BLAKE3 manifests are written. Do not rebuild any variant during the physical sequence.

## 4. Install and prove the native primary release

```bash
cargo run --release -p operator-cli -- install-device-release \
  --manifest-path <device-manifest> \
  --release-id "$REVERSE_RELEASE" \
  --use-existing-release \
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
  --evidence release-candidate-evidence.json \
  --device-release-root "target/device-releases/$REVERSE_RELEASE" \
  --device-serial <adb-serial> \
  --expected-tunnel-owner first_party_reverse_tunnel \
  --vm-release-root "target/vm-releases/$VM_RELEASE" \
  --vm-project <gcp-project> \
  --vm-zone <gcp-zone> \
  --vm-instance <instance-name> \
  --vm-ssh-user <vm-ssh-user> \
  --vm-ssh-key <absolute-vm-ssh-key> \
  --output physical-primary-deployment.json
```

Acceptance requires:

- local BLAKE3 manifests valid;
- package SHA equals candidate SHA;
- active phone and static VM files equal package files byte-for-byte;
- VM proxy configuration equals the native mapping byte-for-byte;
- owner `first_party_reverse_tunnel`;
- WireGuard disabled;
- no active Android VPN owner;
- no `tun0` requirement.

## 5. Configure stage runner

```bash
COMMON_ARGS=(
  --evidence release-candidate-evidence.json
  --host-api-base http://127.0.0.1:18088
  --control-plane-base https://mobile-proxy-relay:8443
  --proxy-host <protected-proxy-host>
  --http-probe-url http://<controlled-http-probe>/
  --https-probe-url https://<controlled-https-probe>/
  --expected-device-id <expected-node-id>
)
```

Every stage requires the exact device, durable heartbeat, serving/cellular/proxy readiness and six authenticated paths:

- SOCKS5 on mixed `1080`;
- HTTP on mixed `1080`;
- HTTPS through CONNECT on mixed `1080`;
- SOCKS5 on `1081`;
- HTTP on `3128`;
- HTTPS through CONNECT on `3128`.

## 6. Native online stage

Wait for fresh QUIC and run:

```bash
python3 scripts/run_physical_phone_acceptance.py \
  --stage online "${COMMON_ARGS[@]}" \
  --output physical-online.json
```

Reject if an Android VPN is active, `tun0` is present, transport is not fresh QUIC or any proxy path fails.

## 7. Phone reboot and durable rehydration

Perform a full phone reboot. Do not clear relay SQLite state. Wait for the rooted boot hook, runtime processes, durable heartbeat and fresh QUIC:

```bash
python3 scripts/run_physical_phone_acceptance.py \
  --stage post-reboot "${COMMON_ARGS[@]}" \
  --output physical-post-reboot.json
```

The device ID must remain unchanged.

## 8. Forced pinned TLS/TCP reserve

Block only QUIC UDP `18090`. Leave pinned TLS/TCP `443` reachable. Force a new tunnel connection and wait for fresh `tls_tcp`:

```bash
python3 scripts/run_physical_phone_acceptance.py \
  --stage fallback "${COMMON_ARGS[@]}" \
  --output physical-fallback.json
```

Reject any plaintext fallback, stale authority, changed device identity or failed proxy path.

## 9. Return to QUIC

Remove the QUIC block, terminate the active reserve connection through the production service manager and wait for new fresh QUIC authority:

```bash
python3 scripts/run_physical_phone_acceptance.py \
  --stage recovered "${COMMON_ARGS[@]}" \
  --output physical-recovered.json
```

## 10. Explicit stock WireGuard rollback

Install the already built rollback release and switch the VM public mapping:

```bash
cargo run --release -p operator-cli -- install-device-release \
  --manifest-path <device-manifest> \
  --release-id "$WIREGUARD_RELEASE" \
  --use-existing-release \
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
  --evidence release-candidate-evidence.json \
  --device-release-root "target/device-releases/$WIREGUARD_RELEASE" \
  --device-serial <adb-serial> \
  --expected-tunnel-owner stock_wireguard_bridge \
  --vm-release-root "target/vm-releases/$VM_RELEASE" \
  --vm-project <gcp-project> \
  --vm-zone <gcp-zone> \
  --vm-instance <instance-name> \
  --vm-ssh-user <vm-ssh-user> \
  --vm-ssh-key <absolute-vm-ssh-key> \
  --output physical-wireguard-deployment.json
```

The verifier must identify `com.wireguard.android` as the actual Android VPN owner. Wait for owner `stock_wireguard_bridge`, `tun0_present=true`, recent handshake and inactive reverse tunnel:

```bash
python3 scripts/run_physical_phone_acceptance.py \
  --stage wireguard "${COMMON_ARGS[@]}" \
  --output physical-wireguard.json
```

## 11. Reactivate the exact native release

Restore the VM native mapping:

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

Reactivate the exact previously installed native release without rebuilding or copying it:

```bash
python3 scripts/activate_device_release.py \
  --evidence release-candidate-evidence.json \
  --release-id "$REVERSE_RELEASE" \
  --device-serial <adb-serial> \
  --output physical-reverse-activation.json
```

Re-verify original package bytes and native ownership:

```bash
python3 scripts/verify_physical_deployment.py \
  --evidence release-candidate-evidence.json \
  --device-release-root "target/device-releases/$REVERSE_RELEASE" \
  --device-serial <adb-serial> \
  --expected-tunnel-owner first_party_reverse_tunnel \
  --vm-release-root "target/vm-releases/$VM_RELEASE" \
  --vm-project <gcp-project> \
  --vm-zone <gcp-zone> \
  --vm-instance <instance-name> \
  --vm-ssh-user <vm-ssh-user> \
  --vm-ssh-key <absolute-vm-ssh-key> \
  --output physical-final-deployment.json
```

After WireGuard is disabled, the Android VPN owner is absent, `tun0` is gone and QUIC is fresh:

```bash
python3 scripts/run_physical_phone_acceptance.py \
  --stage post-wireguard-recovered "${COMMON_ARGS[@]}" \
  --output physical-post-wireguard-recovered.json
```

## 12. Verify the whole report set

```bash
python3 scripts/verify_physical_phone_acceptance_reports.py \
  --evidence release-candidate-evidence.json \
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

The summary must prove one SHA, one device ID, three exact deployment checks, three exact VM mappings, exact native release reactivation and all six stages. It must set `physical_phone_acceptance_complete=true` and `accepted=true`.

Attach only bounded JSON reports and operator timestamps to issue #64. Never attach tokens, keys, raw secret configuration, credential-bearing URLs or unrestricted logs.

## 13. Continue to repeated 10/10 validation

Passing this runbook completes the immutable physical stage but final 10/10 also requires the repeated recovery and 24-hour soak thresholds in `TEN_OUT_OF_TEN_VALIDATION_PLAN.md`.

## 14. Stop conditions

Reject the candidate for any:

- source, package-root or SHA change;
- dirty checkout;
- failed BLAKE3 integrity or exact-byte comparison;
- wrong tunnel or Android VPN owner;
- active Android VPN in a native stage;
- missing durable heartbeat or cellular route;
- failed authenticated proxy path;
- stale or mismatched tunnel authority;
- plaintext downgrade;
- missing/stale WireGuard handshake in rollback;
- lingering `tun0` after native restoration;
- failed transactional VM switch;
- inability to return to fresh QUIC;
- unresolved P0/P1 defect;
- report-set mismatch.

Any source change requires a new immutable candidate, new software evidence, rebuilt variants and a complete restart of the physical procedure.
