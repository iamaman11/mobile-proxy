# Runtime Layout

## Phone

Current observed device:

- model: `SM-A022G`
- runtime owner: Magisk module `mobile-proxy-node`
- active processes:
  - `runtime-supervisor`
  - `host-daemon`
  - `sing-box`
- current release path pattern:
  - `/data/adb/mobile-proxy-node/releases/<release-id>`
- active pointer:
  - `/data/adb/mobile-proxy-node/current`

Boot behavior:

- `/data/adb/service.d/99-mobile-proxy-runtime.sh` is a minimal boot hook that starts the active runtime release
- `service.sh` is bootstrap-only and starts `bin/runtime-supervisor`
- `runtime-supervisor` starts and supervises `host-daemon` and `sing-box`
- `runtime-supervisor` attempts WireGuard activation when `tun0` is missing
- when WireGuard is enabled, `runtime-supervisor` defers `sing-box` startup until `tun0` exists so proxy bind failures do not mask a missing tunnel
- `runtime-supervisor` attempts route repair and falls back to data bounce when health reports missing cellular route
- `host-daemon` reports health from real probes: cellular route, proxy TCP bind, public IP observer, `tun0`, and WireGuard gateway reachability
- cellular route detection is Android policy-routing aware and accepts default routes in tables such as `rmnet*`, not only `main`
- public serving is exposed only after VM gate confirms readiness
- legacy shell route guards such as `/data/adb/service.d/99-mobile-proxy-routefix.sh` must not exist after a Rust-managed install
- current remaining gap: stock WireGuard Android tunnel activation still requires UI or a permissioned companion APK; raw shell/root broadcasts are blocked by Android background-execution/permission rules

## VM

Current observed layout:

- host: `34.118.88.54`
- GCP project: `project-56ecc519-f3ab-429a-b0a`
- GCP instance: `mobile-relaycontrolpoint-v2`
- GCP zone: `europe-central2-a`
- control plane binary:
  - `/opt/mobile-relaycontrolpoint/current/control-plane`
- control plane state:
  - `/var/lib/mobile-relaycontrolpoint/control-plane-state.json`
- relay gate binary:
  - `/opt/mobile-relaycontrolpoint/current/relay-gate`
- public proxy backend:
  - `/opt/mobile-public-proxy/sing-box run -c /opt/mobile-public-proxy/config.json`

Active services:

- `mobile-relaycontrolpoint.service`
- `mobile-relay-gate.service`
- `mobile-public-proxy.service`
- `nginx.service`

Current access status:

- GCP API can identify and describe the instance
- HTTP control-plane endpoint is reachable and returns `401` without a bearer token
- SSH access was recovered on `2026-06-03` with local user `bose` and sudo
- recovery snapshot: `mobile-relaycontrolpoint-pre-ssh-recovery-20260603`
- `operator-cli provision-vm` successfully re-provisioned the VM release `vm-hard-check-20260603`
- public proxy ports `1080`, `1081`, `3128` and control-plane port `8080` were verified listening after reprovision

Current exposure model:

- internal proxy listeners:
  - `127.0.0.1:11080`
  - `127.0.0.1:11081`
  - `127.0.0.1:13128`
- public listeners:
  - `0.0.0.0:1080`
  - `0.0.0.0:1081`
  - `0.0.0.0:3128`
- nginx stream publishes the public ports
- relay-gate enables exposure only when the phone is actually ready

## Current Product Truth

- current operator profile: `mts_by`
- `rotate_ip` works on `MTS BY`
- `airplane_bounce` rotation holds airplane mode for 4 seconds before disabling it
- current deployment is effectively IPv4-only
- public relay is fail-closed
