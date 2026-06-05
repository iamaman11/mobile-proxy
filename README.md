# Mobile Proxy

Reconstructed source tree for the live mobile relay, rebuilt as a Rust-first workspace instead of trying to recreate the lost monorepo byte-for-byte.

## Purpose

- keep a local source-of-truth that matches the current production architecture closely enough to rebuild and evolve it
- prioritize reliability and operability over historical fidelity
- keep runtime policy in Rust while moving Android VPN ownership into the first-party app

## Layout

- `crates/` - shared Rust crates and future domain/infra libraries
- `apps/` - operator-facing and user-facing executable applications
- `services/` - long-running backend and device services
- `deploy/` - deployable runtime bundles, templates, and device manifests
- `config/` - example environment files and local configuration inputs
- root `*.md` documents - architecture map, plan, runtime layout, and operator reference
- `TEN_OUT_OF_TEN_VALIDATION_PLAN.md` - required reliability drill matrix for reproducible `10/10` acceptance

Current primary entrypoints:

- `crates/proxy-core` - shared Rust models, runtime defaults, and proxy metadata
- `crates/runtime-domain` - pure runtime state machine baseline
- `apps/operator-cli` - Rust CLI for status, rotation, airplane timing study, device packaging/install/verify/rollback, and future VM provisioning
- `services/host-daemon` - phone-local API, rotation executor, health probe, and control-plane sync
- `services/control-plane` - registry and readiness service baseline
- `services/relay-gate` - VM-side readiness gate baseline
- `services/runtime-supervisor` - phone-side owner for process lifecycle and runtime recovery
- `apps/android-app` - first-party Android VPN lifecycle owner scaffold

## Reality Check

- this repo is a clean reconstruction, not a recovered copy of the original source tree
- live phone and VM runtimes are the current production reference
- Rust services here are intentionally simpler than the live stack, but they track the same roles and interfaces

## Build

Rust workspace:

```powershell
cd \\wsl.localhost\Ubuntu\home\bose\projects\mobile-proxy
cargo build
cargo test
```

Android app:

```bash
cargo run -p operator-cli -- install-android-app --device-serial R58T10QKGBE
```

The current Windows Android SDK is not a Linux SDK. `operator-cli install-android-app` copies `apps/android-app` to a Windows-path build directory, runs `gradlew.bat`, and installs the APK with `adb.exe`.

## Device Runtime Rollout

Target phone prerequisites:

- rooted device with `adb shell su 0 sh -c "id"` returning `uid=0`
- first-party Android app installed through `cargo run -p operator-cli -- install-android-app`

Temporary live bridge prerequisites until the app-owned tunnel engine replaces stock WireGuard:

- WireGuard Android app installed (`com.wireguard.android`)
- WireGuard tunnel named `WiGandroid` configured and valid
- WireGuard set as always-on VPN:
  - `adb shell su 0 sh -c "settings put secure always_on_vpn_app com.wireguard.android"`
  - `adb shell su 0 sh -c "settings put secure always_on_vpn_lockdown 0"`
- screen unlock available for first tunnel bootstrap

1. Set required secrets in the shell:

```powershell
$env:MOBILE_PROXY_ADMIN_TOKEN='replace_admin_token'
$env:MOBILE_PROXY_DEVICE_TOKEN='replace_device_token'
$env:MOBILE_PROXY_RELAY_USER='replace_relay_user'
$env:MOBILE_PROXY_RELAY_PASSWORD='replace_relay_password'
```

2. Install a release to a phone:

```bash
cargo run -p operator-cli -- install-device-stack \
  --manifest-path deploy/manifests/devices/example-device.json \
  --release-id 2026.06.01 \
  --device-serial R58T10QKGBE
```

This installs the first-party Android `VpnService` APK and then installs the Rust runtime release. Use `install-device-release` only when the Android app is already installed and you intentionally want to update only the rooted runtime.

2a. Or package the device release locally through Rust before pushing it to a phone:

```bash
cargo run -p operator-cli -- package-device-release \
  --manifest-path deploy/manifests/devices/example-device.json \
  --release-id 2026.06.01
```

3. Verify health and public proxy:

```bash
cargo run -p operator-cli -- verify-device \
  --manifest-path deploy/manifests/devices/example-device.json
```

For the final no-compromise gate, require the app-owned tunnel owner explicitly:

```bash
cargo run -p operator-cli -- verify-device \
  --manifest-path deploy/manifests/devices/example-device.json \
  --device-serial R58T10QKGBE \
  --required-tunnel-owner first_party_vpn_service
```

The current live bridge should be verified with `--required-tunnel-owner stock_wireguard_bridge`; it is healthy but not the final `10/10` tunnel architecture.

4. Perform managed IP rotation (auto-heals route/runtimes if airplane bounce stalls):

```bash
cargo run -p operator-cli -- rotate \
  --strategy airplane_bounce \
  --require-public-ip-change true
```

5. Roll back if needed:

```bash
cargo run -p operator-cli -- rollback-device \
  --manifest-path deploy/manifests/devices/example-device.json
```

6. Check fleet status through the control-plane API:

```bash
curl --noproxy '*' http://34.118.88.54:8080/api/v1/devices
```

## Reproducible Provisioning

Prepare runtime binaries that are intentionally not tracked in git:

```bash
cargo run -p operator-cli -- prepare-runtime-binaries
```

Provision or re-provision a GCP relay VM from the repo:

```bash
cargo run -p operator-cli -- provision-vm \
  --manifest-path deploy/manifests/vms/example-gcp-relay.json \
  --release-id 2026.06.03 \
  --ssh-user bose \
  --ssh-key ~/.ssh/google_compute_engine
```

Delete a VM from a manifest:

```bash
cargo run -p operator-cli -- delete-vm \
  --manifest-path deploy/manifests/vms/example-gcp-relay.json \
  --delete-firewall-rules
```

## Notes

- the control and operations path is Rust-first through `apps/operator-cli`
- legacy PowerShell operator scripts were removed after Rust CLI parity became the source of truth
- live phone testing on `2026-06-02` proved that `airplane_bounce` can change public IP while the old shell-owned runtime stayed in `waiting_cellular`; the repo now has Rust-owned recovery and policy-routing-aware health, but it still requires live phone validation
- live migration on `2026-06-03` created `mobile-relaycontrolpoint-v2` as an `e2-micro` GCP relay, migrated the phone to `34.118.88.54`, verified control-plane health and public HTTP proxy serving, then deleted the old VM
- the Android project now owns the `VpnService` lifecycle surface; the real embedded tunnel engine is still the next required step before removing stock WireGuard from production
- docs and manifests use placeholders for secrets; do not store live credentials in repo-tracked files
