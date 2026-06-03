# Quick Reference

## Local Reconstruction

- project root: `\\wsl.localhost\Ubuntu\home\bose\projects\mobile-proxy`
- build Rust workspace: `cargo build`
- run Rust tests: `cargo test`
- start local dev stack: `.\scripts\start-local-stack.ps1 -Token replace_me`
- smoke-test local dev stack: `.\scripts\test-local-stack.ps1 -Token replace_me`

## Public Relay

- relay IP: `34.118.88.54`
- GCP project: `project-56ecc519-f3ab-429a-b0a`
- GCP zone: `europe-central2-a`
- GCP instance: `mobile-relaycontrolpoint-v2`
- mixed: `34.118.88.54:1080`
- SOCKS5: `34.118.88.54:1081`
- HTTP/HTTPS CONNECT: `34.118.88.54:3128`

Credentials are not committed. Set runtime credentials in environment variables:

- `MOBILE_PROXY_RELAY_USER`
- `MOBILE_PROXY_RELAY_PASSWORD`

Quick public proxy smoke test:

```powershell
.\scripts\test-public-proxy.ps1
```

## Required Secrets

```powershell
$env:MOBILE_PROXY_ADMIN_TOKEN='replace_admin_token'
$env:MOBILE_PROXY_DEVICE_TOKEN='replace_device_token'
$env:MOBILE_PROXY_RELAY_USER='replace_relay_user'
$env:MOBILE_PROXY_RELAY_PASSWORD='replace_relay_password'
```

## Device Runtime Deployment

Phone prerequisites:

- `adb shell su 0 sh -c "id"` returns `uid=0`
- `adb shell pm list packages com.wireguard.android` returns installed package
- tunnel `WiGandroid` exists in WireGuard app and can be started
- always-on VPN is pinned to WireGuard:
  - `adb shell su 0 sh -c "settings put secure always_on_vpn_app com.wireguard.android"`
  - `adb shell su 0 sh -c "settings put secure always_on_vpn_lockdown 0"`
- first bootstrap after reboot/install must allow screen unlock (runtime uses UI fallback to toggle WireGuard if Android blocks background broadcast)

Install a versioned release:

```bash
cargo run -p operator-cli -- install-device-release \
  --manifest-path deploy/manifests/devices/example-device.json \
  --release-id 2026.06.01
```

Legacy PowerShell path:

```powershell
.\scripts\device\install-device.ps1 `
  -ManifestPath .\deploy\manifests\devices\example-device.json `
  -ReleaseId 2026.06.01
```

Package a versioned release locally through Rust:

```bash
export MOBILE_PROXY_ADMIN_TOKEN=replace_admin_token
export MOBILE_PROXY_DEVICE_TOKEN=replace_device_token
export MOBILE_PROXY_RELAY_USER=replace_relay_user
export MOBILE_PROXY_RELAY_PASSWORD=replace_relay_password

cargo run -p operator-cli -- package-device-release \
  --manifest-path deploy/manifests/devices/example-device.json \
  --release-id 2026.06.01
```

Verify device health and proxy readiness:

```bash
cargo run -p operator-cli -- verify-device \
  --manifest-path deploy/manifests/devices/example-device.json
```

Legacy PowerShell path:

```powershell
.\scripts\device\verify-device.ps1 -ManifestPath .\deploy\manifests\devices\example-device.json
```

Roll back to previous or explicit release:

```bash
cargo run -p operator-cli -- rollback-device \
  --manifest-path deploy/manifests/devices/example-device.json
```

Legacy PowerShell path:

```powershell
.\scripts\device\rollback-device.ps1 -ManifestPath .\deploy\manifests\devices\example-device.json
.\scripts\device\rollback-device.ps1 -ManifestPath .\deploy\manifests\devices\example-device.json -ReleaseId 2026.05.31
```

## Rotate IP

If local API access is not configured yet:

```powershell
& "C:\Users\Bose\AppData\Local\Android\Sdk\platform-tools\adb.exe" forward tcp:18088 tcp:8088
```

Managed rotation (recommended, includes auto-repair if airplane bounce stalls):

```powershell
.\scripts\device\rotate-ip.ps1 -ManifestPath .\deploy\manifests\devices\example-device.json -Strategy airplane_bounce -RequirePublicIpChange $true
```

Raw API rotation (fallback):

```powershell
$h=@{Authorization="Bearer $env:MOBILE_PROXY_ADMIN_TOKEN"};$b='{"strategy":"airplane_bounce","require_public_ip_change":true,"reason":"manual-rotate"}';$id=(Invoke-RestMethod -Method POST -Uri 'http://127.0.0.1:18088/v1/ip/rotate' -Headers $h -ContentType 'application/json' -Body $b).job_id;do{$s=Invoke-RestMethod -Uri "http://127.0.0.1:18088/v1/jobs/$id" -Headers $h;$x=Invoke-RestMethod -Uri 'http://127.0.0.1:18088/v1/health' -Headers $h;"{0} job={1} state={2} serving={3} old={4} new={5}" -f (Get-Date -Format HH:mm:ss),$s.status,$x.readiness_state,$x.serving,$s.old_public_ip,$s.new_public_ip;Start-Sleep 2}while($s.status -eq 'running');$s|ConvertTo-Json -Depth 5
```

Runtime introspection endpoints (same bearer token):

- `GET http://127.0.0.1:18088/v1/health` - readiness, serving state, route/proxy probes
- `GET http://127.0.0.1:18088/v1/status` - current runtime job and WireGuard mode
- `GET http://127.0.0.1:18088/v1/proxy` - active proxy listener metadata

Live timing result as of `2026-06-03`:

- release `hard-rust-supervisor-20260603-1733` is installed on `SM_A022G`
- programmatic airplane matrix selected `4s` as the minimum reliable hold for `MTS BY`
- results: `1s=24/30`, `2s=28/30`, `3s=29/30`, `4s=30/30`, `5s=30/30`

## Reproducible Runtime Artifacts

Prepare ignored runtime binaries from source and official releases:

```bash
cargo run -p operator-cli -- prepare-runtime-binaries
```

This produces:

- `deploy/device-runtime/bin/runtime-supervisor`
- `deploy/device-runtime/bin/host-daemon`
- `deploy/device-runtime/bin/sing-box`
- `deploy/vm-runtime/bin/sing-box`

## VM Provisioning

Required environment variables:

```bash
export MOBILE_PROXY_CONTROL_TOKEN=replace_control_token
export MOBILE_PROXY_RELAY_USER=replace_relay_user
export MOBILE_PROXY_RELAY_PASSWORD=replace_relay_password
export MOBILE_PROXY_WG_SERVER_PRIVATE_KEY=replace_server_private_key
export MOBILE_PROXY_WG_PHONE_PUBLIC_KEY=replace_phone_public_key
```

Provision or re-provision the GCP relay VM from this repo:

```bash
cargo run -p operator-cli -- provision-vm \
  --manifest-path deploy/manifests/vms/example-gcp-relay.json \
  --release-id 2026.06.03 \
  --ssh-user bose \
  --ssh-key ~/.ssh/google_compute_engine
```

Delete a VM from its manifest:

```bash
cargo run -p operator-cli -- delete-vm \
  --manifest-path deploy/manifests/vms/example-gcp-relay.json \
  --delete-firewall-rules
```

Fresh VM smoke passed on `2026-06-03` with temporary instance `mobile-relaycontrolpoint-repro-test`; it was provisioned and then deleted through `operator-cli`.
