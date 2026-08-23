# Reproducibility Test 2026-06-04

Workspace: `/home/bose/projects/mobile-proxy`
Device: `SM_A022G`, serial `R58T10QKGBE`
VM: `mobile-relaycontrolpoint-v2`
Static IP: `34.118.88.54`

## Verdict

The application is not yet `10/10`, but the live VM + phone path is currently serving.

The VM side is reproducible from the repository and environment secrets. The phone runtime can be deleted and reinstalled from the repository, the Rust supervisor boot hook starts the active release, and the public relay returns a mobile carrier IP. The remaining no-compromise blocker is fully programmatic WireGuard activation: the stock WireGuard Android app does not accept raw `am broadcast` tunnel toggles from shell/root under the current Android background-execution and permission model.

## What Passed

- Rust quality gates:
  - `cargo fmt`
  - `cargo test`
  - `cargo clippy --all-targets --all-features -- -D warnings`
- Runtime artifact gate:
  - `cargo run -p operator-cli -- prepare-runtime-binaries`
- VM destructive recreate:
  - deleted `mobile-relaycontrolpoint-v2`
  - deleted and recreated firewall rules
  - reattached static IP `34.118.88.54` through manifest `staticExternalIp`
  - provisioned release `recreate-vm-20260604`
  - redeployed release `recreate-vm-stalefix-20260604`
  - verified services active and ports listening
- Phone destructive runtime reinstall:
  - deleted `/data/adb/mobile-proxy-node`
  - removed legacy `/data/adb/service.d/99-mobile-proxy-routefix.sh`
  - installed release `recreate-phone-20260604`
  - installed release `recreate-phone-wgfix-20260604`
  - installed release `checkall-phone-observability-20260604`
  - installed `/data/adb/service.d/99-mobile-proxy-runtime.sh`
  - verified boot hook starts `runtime-supervisor` after phone reboot
- Live end-to-end check:
  - VM release `checkall-vm-observability-20260604` active
  - device health `healthy`, `serving=true`
  - control-plane reports `availability=ready`, `publicly_serving=true`
  - public proxy `34.118.88.54:3128` returned carrier IP `178.168.185.115`

## Bugs Found And Fixed

1. VM recreate did not pin the reserved IP.
   - Added `staticExternalIp` to the VM manifest.
   - `operator-cli provision-vm` now passes `--address` to `gcloud compute instances create`.

2. Rust device install did not install a Rust runtime boot hook.
   - `operator-cli install-device-release` now installs `/data/adb/service.d/99-mobile-proxy-runtime.sh`.
   - The install removes legacy route guard script `/data/adb/service.d/99-mobile-proxy-routefix.sh`.

3. Phone health falsely treated `tun0` presence as a recent WireGuard handshake.
   - `host-daemon` now checks reachability of WG gateway `10.66.66.1`.
   - `serving=true` is rejected if the WG gateway is unreachable.

4. `runtime-supervisor` did not recover stale WireGuard paths.
   - WireGuard recovery is enabled in the default phone runtime template.
   - Supervisor now kicks WireGuard when `wg_handshake_recent=false`.

5. Control-plane could expose stale healthy state when phone heartbeat disappears.
   - `DeviceRecord` now stores local readiness probe fields and `last_heartbeat_at`.
   - Device list projection marks stale heartbeats as `heartbeat_stale`.

6. Phone degraded as `waiting_cellular/proxy_bind_failed` when the true cause was missing WireGuard tunnel.
   - `host-daemon` now reports `waiting_wireguard` and `wireguard_path_not_ready` when `tun0` or the WG gateway is missing.
   - `runtime-supervisor` now defers `sing-box` startup until `tun0` exists when WireGuard is enabled.

7. Control-plane hid WireGuard probe fields.
   - Heartbeats and device records now carry `tun0_present` and `wg_handshake_recent`.

## Current Blocker

The phone currently has cellular data and the end-to-end proxy is healthy, but WireGuard activation is not fully application-owned:

- UI switch in WireGuard Android successfully creates `tun0=10.66.66.2/32`.
- After `tun0` appears, `runtime-supervisor` starts `sing-box` and health becomes `healthy`.
- Raw `am broadcast` attempts from shell/root do not create `tun0`.
- logcat reports Android background execution blocking for `com.wireguard.android.action.SET_TUNNEL_UP`.
- `com.android.shell` cannot be granted `com.wireguard.android.permission.CONTROL_TUNNELS` because it does not request that permission.

Required architecture fix:

- build/install a small companion APK that requests `com.wireguard.android.permission.CONTROL_TUNNELS` and exposes a controlled local command path for `runtime-supervisor`, or
- replace the stock WireGuard app dependency with a Rust-owned/native WireGuard backend that can create the tunnel from the application runtime.

## Current Running State

VM:

- `mobile-relaycontrolpoint-v2` is running on `e2-micro`
- static IP `34.118.88.54` is attached
- `wg-quick@wg0`, `mobile-relaycontrolpoint`, `mobile-relay-gate`, `mobile-public-proxy`, and `nginx` are active
- control-plane reports the phone as ready and publicly serving

Phone:

- Rust runtime is installed
- boot hook exists
- `runtime-supervisor`, `host-daemon`, and `sing-box` are running
- local health reports:
  - `readiness_state=healthy`
  - `serving=true`
  - `tun0_present=true`
  - `wg_handshake_recent=true`

## Required Next Gate

Before claiming `10/10`, remove the WireGuard app broadcast/UI dependency, then rerun:

1. `cargo run -p operator-cli -- install-device-release --manifest-path deploy/manifests/devices/example-device.json --release-id final-phone --device-serial R58T10QKGBE`
2. `cargo run -p operator-cli -- verify-device --manifest-path deploy/manifests/devices/example-device.json --device-serial R58T10QKGBE`
3. public proxy check through `34.118.88.54:3128`
4. phone reboot recovery
5. VM reboot recovery
6. process kill recovery matrix
7. selected `4s` airplane rotation soak
8. companion APK/native WireGuard backend recovery after phone reboot with no manual UI action
