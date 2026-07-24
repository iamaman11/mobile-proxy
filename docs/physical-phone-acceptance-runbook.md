# Immutable-SHA Physical Phone Acceptance Runbook

Status: executable external gate for delivery item 15  
Prerequisite: successful `Software Release Candidate` evidence for the exact candidate SHA

## 1. Freeze the candidate

Download `release-candidate-evidence.json` from the successful workflow artifact named:

`software-release-candidate-<candidate-sha>`

Use a clean detached checkout of that exact SHA. Do not test a branch name or a later commit.

```bash
git fetch --all --tags
git checkout --detach <candidate-sha>
test "$(git rev-parse HEAD)" = "<candidate-sha>"
test -z "$(git status --porcelain)"
```

Record candidate SHA, workflow run URL, phone identifier, Android version, operator/SIM, VM identifier, tester and UTC timestamps. Never record tokens or proxy credentials.

## 2. Build and deploy from the frozen checkout

Build and deploy both release roots from this clean checkout using the normal operator commands. The packaging commands clean their release output before writing, create a BLAKE3 integrity manifest and verify it locally before returning success.

```bash
cargo run --release -p operator-cli -- package-device-release \
  --manifest-path <device-manifest> \
  --release-id <release-id> \
  --tunnel-owner first_party_reverse_tunnel

cargo run --release -p operator-cli -- provision-vm \
  --manifest-path <vm-manifest> \
  --release-id <release-id> \
  --ssh-user <vm-ssh-user> \
  --ssh-key <vm-ssh-key>

cargo run --release -p operator-cli -- install-device-release \
  --manifest-path <device-manifest> \
  --release-id <release-id> \
  --device-serial <adb-serial> \
  --tunnel-owner first_party_reverse_tunnel
```

Use the exact output roots produced by these commands. Do not edit packaged files after manifest generation.

## 3. Prove deployed artifact identity

Before any network acceptance, compare every packaged device file byte-for-byte with the active phone release and every supported VM release file by SHA-256 with the installed VM copy. The verifier also requires device `release-metadata.json` to contain the evidence SHA and a clean build flag.

```bash
python3 scripts/verify_physical_deployment.py \
  --evidence ./release-candidate-evidence.json \
  --device-release-root target/device-releases/<release-id> \
  --device-serial <adb-serial> \
  --vm-release-root target/vm-releases/<release-id> \
  --vm-project <gcp-project> \
  --vm-zone <gcp-zone> \
  --vm-instance <instance-name> \
  --vm-ssh-user <vm-ssh-user> \
  --vm-ssh-key <vm-ssh-key> \
  --output physical-deployment-integrity.json
```

Do not proceed unless the report contains the same candidate SHA, `device_release_metadata_match=true`, `device_deployment_match=true`, `vm_deployment_match=true` and `accepted=true`.

## 4. Configure the staged runner

The runner reads tokens only from environment variables and never writes them to reports.

```bash
export HOST_ADMIN_TOKEN='<host-daemon admin token>'
export CONTROL_PLANE_ADMIN_TOKEN='<control-plane admin token>'

COMMON_ARGS=(
  --evidence ./release-candidate-evidence.json
  --host-api-base https://<host-api>
  --control-plane-base https://<control-plane-api>
  --proxy-host <protected-proxy-host>
  --http-probe-url http://<controlled-http-probe>/
  --https-probe-url https://<controlled-https-probe>/
  --device-id <expected-node-id>
)
```

The controlled HTTP and HTTPS probes must be reachable only through the protected proxy path and must not contain credentials in their URLs.

Every stage checks six protected protocol paths:

- SOCKS5 through mixed port `1080`;
- HTTP through mixed port `1080`;
- HTTPS through HTTP CONNECT on mixed port `1080`;
- SOCKS5 on `1081`;
- HTTP on `3128`;
- HTTPS through HTTP CONNECT on `3128`.

## 5. Clean startup and QUIC-primary acceptance

Start the VM services and phone-side release from a clean stopped state. Wait until both `/livez` and `/readyz` are healthy, then run:

```bash
python3 scripts/run_physical_phone_acceptance.py \
  --stage online "${COMMON_ARGS[@]}" \
  --output physical-online.json
```

This stage must prove process health, expected durable device inventory, a connected fresh QUIC tunnel and all six proxy paths.

## 6. Phone or service reboot and state rehydration

Reboot the phone, or stop and start the deployed phone-side service using the production service manager. Do not reset the VM or delete SQLite state. Wait for the same device to re-register and the tunnel to become fresh, then run:

```bash
python3 scripts/run_physical_phone_acceptance.py \
  --stage post-reboot "${COMMON_ARGS[@]}" \
  --output physical-post-reboot.json
```

The expected device ID must remain present in durable control-plane state and all six proxy paths must work over fresh QUIC.

## 7. Forced TLS/TCP reserve

At the controlled VM or network firewall, block only the configured QUIC UDP path between the phone and reverse-tunnel server. Keep certificate-pinned TLS/TCP reserve reachable. Restart only the tunnel connection or phone-side service if needed to create a new attempt; do not change credentials, binaries or configuration.

Wait until authenticated health reports `active_transport=tls_tcp` and `freshness=fresh`, then run:

```bash
python3 scripts/run_physical_phone_acceptance.py \
  --stage fallback "${COMMON_ARGS[@]}" \
  --output physical-fallback.json
```

All six proxy paths must succeed. Plaintext fallback, stale authority, routing to another device or unbounded retry is a blocking defect.

## 8. Return to QUIC

Remove the QUIC UDP block. Terminate the current reserve tunnel connection through the existing deployment/service manager so the client performs a new QUIC-first attempt. Do not modify the tested release.

Wait until authenticated health reports fresh QUIC and run:

```bash
python3 scripts/run_physical_phone_acceptance.py \
  --stage recovered "${COMMON_ARGS[@]}" \
  --output physical-recovered.json
```

The same device and deployment must serve all six proxy paths after recovery.

## 9. WireGuard rollback availability

Activate the existing documented WireGuard rollback configuration without replacing candidate binaries. Confirm the phone and VM establish the rollback path and authenticated status reports `wireguard_enabled=true`, then run:

```bash
python3 scripts/run_physical_phone_acceptance.py \
  --stage wireguard "${COMMON_ARGS[@]}" \
  --output physical-wireguard.json
```

All six proxy paths must remain usable. Restore normal QUIC-first configuration afterward and confirm fresh QUIC again.

## 10. Verify the complete report set

Do not close the physical gate by visual inspection alone. Validate deployment integrity plus all five stage reports as one exact-SHA set:

```bash
python3 scripts/verify_physical_phone_acceptance_reports.py \
  --evidence ./release-candidate-evidence.json \
  --deployment physical-deployment-integrity.json \
  --online physical-online.json \
  --post-reboot physical-post-reboot.json \
  --fallback physical-fallback.json \
  --recovered physical-recovered.json \
  --wireguard physical-wireguard.json \
  --output physical-acceptance-summary.json
```

The gate passes only when the summary contains the evidence SHA, all five accepted stages, `deployment_integrity_accepted=true`, `physical_phone_acceptance_complete=true` and `accepted=true`.

Attach these bounded files and operator timestamps to the delivery-item issue:

- `physical-deployment-integrity.json`;
- `physical-online.json`;
- `physical-post-reboot.json`;
- `physical-fallback.json`;
- `physical-recovered.json`;
- `physical-wireguard.json`;
- `physical-acceptance-summary.json`.

Never attach tokens, private keys, raw configuration, credential-bearing proxy URLs or unrestricted service logs.

## 11. Stop conditions

Reject the candidate for any unresolved P0/P1 defect, SHA mismatch, dirty checkout, failed package or deployed-file integrity, missing durable state, missing expected device, failed proxy protocol path, stale or mismatched tunnel authority, plaintext downgrade, inability to return to QUIC or unavailable WireGuard rollback.

After any source change, rerun the complete `Software Release Candidate` workflow on the new immutable SHA, download its new evidence artifact, rebuild both release roots and repeat this physical sequence from the beginning.
