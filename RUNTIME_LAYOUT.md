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

- `service.sh` is bootstrap-only and starts `bin/runtime-supervisor`
- `runtime-supervisor` starts and supervises `host-daemon` and `sing-box`
- `runtime-supervisor` attempts WireGuard activation when `tun0` is missing
- `runtime-supervisor` attempts route repair and falls back to data bounce when health reports missing cellular route
- `host-daemon` reports health from real probes: cellular route, proxy TCP bind, public IP observer, and `tun0`
- cellular route detection is Android policy-routing aware and accepts default routes in tables such as `rmnet*`, not only `main`
- public serving is exposed only after VM gate confirms readiness

## VM

Current observed layout:

- host: `34.118.26.142`
- GCP project: `project-56ecc519-f3ab-429a-b0a`
- GCP instance: `mobile-relaycontrolpoint`
- GCP zone: `europe-central2-a`
- control plane binary:
  - `/opt/mobile-relaycontrolpoint/current/control-plane`
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
- direct SSH and `gcloud compute ssh` currently fail with `Permission denied (publickey)`
- OS Login profile exists for `sarov8502905@gmail.com`, but SSH key propagation still does not grant shell access
- do not rewrite startup metadata or reboot the VM unless explicitly performing VM recovery/provisioning work

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
