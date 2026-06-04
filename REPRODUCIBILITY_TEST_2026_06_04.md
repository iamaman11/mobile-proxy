# Reproducibility Test 2026-06-04

Workspace: `/home/bose/projects/mobile-proxy`
Device: `SM_A022G`, serial `R58T10QKGBE`
VM: `mobile-relaycontrolpoint-v2`
Static IP: `34.118.88.54`

## Verdict

The application is not yet `10/10`.

The VM side is reproducible from the repository and environment secrets. The phone runtime can be deleted and reinstalled from the repository, and the Rust supervisor boot hook starts after reboot. Full end-to-end public proxy recovery is blocked by the phone radio/SIM state: Android reports `gsm.sim.state=ABSENT,ABSENT` and telephony `OUT_OF_SERVICE`, so no cellular `rmnet*` interface or route exists.

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
  - installed `/data/adb/service.d/99-mobile-proxy-runtime.sh`
  - verified boot hook starts `runtime-supervisor` after phone reboot

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

## Current Blocker

The phone is currently not registered on the cellular network:

- `gsm.sim.state=ABSENT,ABSENT`
- `MobileVoice=OUT_OF_SERVICE`
- `MobileData=OUT_OF_SERVICE`
- no `rmnet*` interface
- no cellular default route
- only `dummy0` default route remains

Attempted recovery:

- phone reboot
- `svc data disable/enable`
- airplane mode enable/disable
- `ril-daemon` and `ril-daemon1` restart
- WireGuard app force-stop
- always-on VPN disabled temporarily

Result:

- SIM remains absent
- cellular route remains unavailable
- public proxy remains unavailable with `502` because VM cannot reach phone `10.66.66.2:1080`

## Current Running State

VM:

- `mobile-relaycontrolpoint-v2` is running on `e2-micro`
- static IP `34.118.88.54` is attached
- `wg-quick@wg0`, `mobile-relaycontrolpoint`, `mobile-relay-gate`, `mobile-public-proxy`, and `nginx` are active
- control-plane has no current ready device because the phone has no cellular underlay

Phone:

- Rust runtime is installed
- boot hook exists
- `runtime-supervisor` and `host-daemon` are running
- `sing-box` cannot stay serving without cellular/WireGuard path
- local health correctly reports degraded:
  - `readiness_state=waiting_cellular`
  - `serving=false`
  - `degradation_reason_code=cellular_route_missing`

## Required Next Gate

Before claiming `10/10`, restore physical SIM/radio service, then rerun:

1. `cargo run -p operator-cli -- install-device-release --manifest-path deploy/manifests/devices/example-device.json --release-id final-phone --device-serial R58T10QKGBE`
2. `cargo run -p operator-cli -- verify-device --manifest-path deploy/manifests/devices/example-device.json --device-serial R58T10QKGBE`
3. public proxy check through `34.118.88.54:3128`
4. phone reboot recovery
5. VM reboot recovery
6. process kill recovery matrix
7. selected `4s` airplane rotation soak
