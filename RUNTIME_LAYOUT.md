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
- `runtime-supervisor` attempts WireGuard activation only when an optional WireGuard backend is enabled
- when WireGuard is enabled, `runtime-supervisor` defers `sing-box` startup until `tun0` exists so proxy bind failures do not mask a missing optional tunnel
- in the required `first_party_reverse_tunnel` path, `runtime-supervisor` starts `sing-box` on loopback and `host-daemon` owns the QUIC/TLS reverse tunnel to the VM
- `runtime-supervisor` attempts route repair, mobile-data enable, and data bounce when health reports cellular or public reachability degradation
- `service.sh` validates the watchdog PID by checking `/proc/<pid>/cmdline`, not only `kill -0`, so a stale PID reused by another Android process cannot block runtime startup
- `host-daemon` reports health from real probes: cellular route, proxy TCP bind, public IP observer, `tun0`, and WireGuard gateway reachability
- cellular route detection is Android policy-routing aware and accepts default routes in tables such as `rmnet*`, not only `main`
- public serving is exposed only after VM gate confirms readiness
- legacy shell route guards such as `/data/adb/service.d/99-mobile-proxy-routefix.sh` must not exist after a Rust-managed install
- stock WireGuard and Android `VpnService` are optional backends, not the required production traffic path
- current remaining recovery gap on `SM-A022G`: after full phone reboot, Android/MTS cellular Internet becomes usable roughly 135-145 seconds after reboot in live tests, so the system recovers automatically but does not yet meet the target p95 `<60s` phone-reboot threshold

## VM

Current observed layout:

- host: `34.118.88.54`
- GCP project: `project-56ecc519-f3ab-429a-b0a`
- GCP instance: `mobile-relaycontrolpoint-v2`
- GCP zone: `europe-central2-a`
- control plane binary:
  - `/opt/mobile-relaycontrolpoint/current/control-plane`
- control plane state:
  - `/var/lib/mobile-relaycontrolpoint/control-plane-state.sqlite3` (canonical runtime)
  - `/var/lib/mobile-relaycontrolpoint/control-plane-state.json` (preserved migration input only)
- relay gate binary:
  - `/opt/mobile-relaycontrolpoint/current/relay-gate`
- public proxy backend:
  - `/opt/mobile-public-proxy/sing-box run -c /opt/mobile-public-proxy/config.json`

Active services:

- `mobile-relaycontrolpoint.service`
- `mobile-relay-gate.service`
- `mobile-reverse-tunnel-server.service`
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
- required live tunnel owner: `first_party_reverse_tunnel`
- optional WireGuard backend remains installable for experiments/fallback, but is not required for production traffic
