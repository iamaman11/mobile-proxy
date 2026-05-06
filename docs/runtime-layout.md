# Runtime Layout

## Phone

Current observed device:

- model: `SM-A022G`
- runtime owner: Magisk module `mobile-proxy-node`
- active processes:
  - `host-daemon`
  - `sing-box`
- current release path pattern:
  - `/data/adb/mobile-proxy-node/releases/<release-id>`
- active pointer:
  - `/data/adb/mobile-proxy-node/current`

Boot behavior:

- `service.sh` activates a versioned release
- `host-daemon` starts first
- `tun0` becomes ready after the WireGuard helper converges
- public serving is exposed only after VM gate confirms readiness

## VM

Current observed layout:

- host: `34.118.26.142`
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
- current deployment is effectively IPv4-only
- public relay is fail-closed
