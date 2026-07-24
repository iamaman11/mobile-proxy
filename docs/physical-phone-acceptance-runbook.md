# Immutable-SHA Physical Phone Acceptance Runbook

Status: executable external gate for delivery item 15  
Prerequisite: successful `Software Release Candidate` evidence for the exact candidate SHA

## 1. Freeze the candidate

Download `release-candidate-evidence.json` from the successful workflow artifact named:

`software-release-candidate-<candidate-sha>`

Use a clean checkout of that exact SHA. Do not test a branch name or a later commit.

```bash
git fetch --all --tags
git checkout --detach <candidate-sha>
test "$(git rev-parse HEAD)" = "<candidate-sha>"
test -z "$(git status --porcelain)"
```

Build and deploy the device and VM artifacts from this checkout only. Verify the packaged BLAKE3 integrity manifest before installation. Record candidate SHA, workflow run URL, phone identifier, Android version, operator/SIM, VM identifier, tester and UTC timestamps in the test record. Do not record tokens or proxy credentials.

## 2. Configure the staged runner

The runner reads tokens only from environment variables and never writes them to its report.

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

The controlled HTTP and HTTPS probes must be reachable only through the protected proxy path and must not require credentials embedded in their URLs.

## 3. Clean startup and QUIC-primary acceptance

Start the VM services and the phone-side deployed service from a clean stopped state. Wait until both `/livez` and `/readyz` are healthy, then run:

```bash
python3 scripts/run_physical_phone_acceptance.py \
  --stage online "${COMMON_ARGS[@]}" \
  --output physical-online.json
```

This stage must prove:

- host and control-plane process health;
- restored device inventory contains the expected phone;
- reverse tunnel is connected, fresh and using QUIC;
- mixed proxy behavior on `1080`;
- SOCKS5 on `1081`;
- HTTP proxy on `3128`;
- HTTPS through HTTP CONNECT on `3128`.

## 4. Phone or service reboot and state rehydration

Reboot the phone, or stop and start the deployed phone-side service using the production service manager. Do not reset the VM or delete SQLite state. Wait for the phone to re-register and the tunnel to become fresh, then run:

```bash
python3 scripts/run_physical_phone_acceptance.py \
  --stage post-reboot "${COMMON_ARGS[@]}" \
  --output physical-post-reboot.json
```

The same device ID must reappear from durable control-plane state and all protected proxy surfaces must work over fresh QUIC.

## 5. Forced TLS/TCP reserve

At the controlled VM or network firewall, block only the configured QUIC UDP path between the phone and reverse-tunnel server. Keep certificate-pinned TLS/TCP reserve reachable. Restart only the tunnel connection or phone-side service if necessary to create a new connection attempt; do not change credentials or the candidate binaries.

Wait until authenticated health reports `active_transport=tls_tcp` and `freshness=fresh`, then run:

```bash
python3 scripts/run_physical_phone_acceptance.py \
  --stage fallback "${COMMON_ARGS[@]}" \
  --output physical-fallback.json
```

All four protected proxy checks must succeed. Any plaintext fallback, stale authority, routing to another device or unbounded retry is a blocking defect.

## 6. Return to QUIC

Remove the QUIC UDP block. Terminate the current reserve tunnel connection through the existing deployment/service manager so the client performs a new QUIC-first attempt. Do not modify the tested binaries or configuration.

Wait until authenticated health reports fresh QUIC and run:

```bash
python3 scripts/run_physical_phone_acceptance.py \
  --stage recovered "${COMMON_ARGS[@]}" \
  --output physical-recovered.json
```

The same device and logical deployment must serve every protected proxy surface after recovery.

## 7. WireGuard rollback availability

Activate the existing documented WireGuard rollback configuration without replacing the candidate application binaries. Confirm the phone and VM establish the existing rollback path and authenticated status reports `wireguard_enabled=true`, then run:

```bash
python3 scripts/run_physical_phone_acceptance.py \
  --stage wireguard "${COMMON_ARGS[@]}" \
  --output physical-wireguard.json
```

All proxy surfaces must remain usable. Restore the normal QUIC-first configuration after the rollback proof and confirm fresh QUIC once more.

## 8. Acceptance record and stop conditions

The physical gate passes only when all five reports contain the same `candidate_sha` and `accepted=true`:

- `physical-online.json`;
- `physical-post-reboot.json`;
- `physical-fallback.json`;
- `physical-recovered.json`;
- `physical-wireguard.json`.

Attach those bounded reports and operator timestamps to the delivery-item issue. Never attach tokens, private keys, raw configuration, full proxy URLs with credentials or unrestricted service logs.

Stop and reject the candidate for any unresolved P0/P1 defect, SHA mismatch, dirty checkout, failed integrity verification, missing durable state, failed protected surface, stale/mismatched tunnel authority, plaintext downgrade, inability to return to QUIC or unavailable WireGuard rollback. After any source change, rerun the complete `Software Release Candidate` workflow on the new immutable SHA before repeating this physical sequence.
