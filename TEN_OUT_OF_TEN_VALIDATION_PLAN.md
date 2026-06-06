# 10/10 Reproducibility and Reliability Validation Plan

Date: 2026-06-03
Workspace: `/home/bose/projects/mobile-proxy`

This is the acceptance matrix for calling the system reproducible and production-grade. Unit tests are required, but they are not enough: the system is accepted only after fresh infrastructure creation, fresh phone installation, repeated failure drills, and public proxy checks all pass.

## Current production baseline

- GCP project: `project-56ecc519-f3ab-429a-b0a`
- Zone: `europe-central2-a`
- Relay VM: `mobile-relaycontrolpoint-v2`
- Machine type: `e2-micro`
- Boot disk: 10 GB Debian 12
- Static IP: `34.118.88.54`
- Phone profile: `mts_by`
- Selected airplane hold: `4s`

Cost guardrail:
- use `e2-micro` unless a measured CPU or memory bottleneck requires escalation
- do not add GPU, local SSD, load balancer, or oversized boot disks
- reserve the external IPv4 only for the active production relay
- keep `staticExternalIp` in the VM manifest so delete-and-recreate reattaches the same relay endpoint
- delete test VMs immediately after validation

## Source and artifact gates

Required:
- `cargo fmt --check`
- `cargo test`
- `cargo clippy --all-targets --all-features -- -D warnings`
- `cargo run -p operator-cli -- prepare-runtime-binaries`
- `cargo run -p operator-cli -- install-android-app --device-serial R58T10QKGBE`
- `cargo run -p operator-cli -- install-device-stack --manifest-path deploy/manifests/devices/example-device.json --release-id validation-phone --device-serial R58T10QKGBE`
- `cargo test -p reverse-tunnel`
- `cargo run -p operator-cli -- verify-device --manifest-path deploy/manifests/devices/example-device.json --device-serial R58T10QKGBE --required-tunnel-owner first_party_reverse_tunnel`
- `cargo run -p operator-cli -- package-device-release --manifest-path deploy/manifests/devices/example-device.json --release-id validation-package`

Acceptance:
- all Rust sources, configs, manifests, docs, VM provisioning code, `runtime-supervisor`, and `host-daemon` source are in git
- generated Android runtime binaries stay out of git under `deploy/device-runtime/bin/*`
- `runtime-supervisor` and `host-daemon` are rebuildable from source
- `sing-box` is downloaded or supplied separately by `prepare-runtime-binaries`
- live secrets are supplied only through environment variables

## Fresh VM drill

Command:

```bash
cargo run -p operator-cli -- provision-vm \
  --manifest-path deploy/manifests/vms/example-gcp-relay.json \
  --release-id validation-vm \
  --ssh-user bose \
  --ssh-key ~/.ssh/google_compute_engine
```

Acceptance:
- instance exists with the manifest machine type and zone
- instance uses the manifest `staticExternalIp`
- SSH admin access works
- `wg-quick@wg0`, `mobile-relaycontrolpoint`, `mobile-relay-gate`, `mobile-public-proxy`, and `nginx` are active
- control-plane state exists at `/var/lib/mobile-relaycontrolpoint/control-plane-state.json` after registration/heartbeat and survives service restart
- ports `8080`, `1080`, `1081`, `3128`, and `51820/udp` are reachable as designed
- the provision command is idempotent against an existing VM
- deleting a test VM with `operator-cli delete-vm --delete-firewall-rules` leaves no orphan test instance

## Fresh phone drill

Command:

```bash
cargo run -p operator-cli -- install-device-stack \
  --manifest-path deploy/manifests/devices/example-device.json \
  --release-id validation-phone \
  --device-serial R58T10QKGBE
```

Acceptance:
- first-party Android APK is installed for boot/enrollment UI only; the required runtime path does not depend on Android `VpnService`
- root access is detected before installation
- release bundle contains architecture-correct Android binaries
- `service.sh` starts only `runtime-supervisor`
- `/data/adb/service.d/99-mobile-proxy-runtime.sh` exists and only starts the active Rust-owned release
- legacy route guard scripts are absent
- `runtime-supervisor` owns `host-daemon` and `sing-box`
- local health reaches `healthy`
- control-plane reports the device as `serving=true` and `publicly_serving=true`
- local health and control-plane report `tunnel_owner=first_party_reverse_tunnel`
- public HTTP proxy `:3128` returns the phone carrier IP
- active Android VPN ownership is not required for the primary path

## Rotation timing gate

Matrix:
- programmatic toggle only
- hold windows: `1s`, `2s`, `3s`, `4s`, `5s`
- minimum 30 runs per window

Decision rule:
- choose the shortest hold with at least `99%` successful IP change and return to `healthy`
- current measured winner on `SM_A022G` + `MTS BY`: `4s`

Acceptance:
- no false success when IP does not change
- no false success while runtime remains degraded
- failure reason is machine-readable
- route readiness distinguishes Android policy routing from true cellular unavailability

## Recovery drills

Phone:
- 20 phone reboots
- 20 `host-daemon` kills
- 20 `sing-box` kills
- 30 rotations at the selected airplane hold
- 60-minute soak with periodic public proxy checks

VM:
- 20 `control-plane` restarts
- 20 `relay-gate` restarts
- 20 `mobile-public-proxy` restarts
- 10 full VM reboots
- one delete-and-recreate drill using the manifest

Acceptance thresholds:
- automatic recovery success `>= 99.5%`
- median recovery `< 20s`
- p95 recovery `< 60s`
- no silent stuck state longer than `60s`
- no degraded state without a reason code

## Final 10/10 gate

The system is not 10/10 until all of these are true:
- new VM can be created from the repository and env vars
- new rooted phone can be installed from the repository and env vars
- phone and VM recover automatically after reboot and process crashes
- IP rotation is evidence-based and repeatedly verified
- control-plane state survives restart or has a documented durable replacement
- release artifacts are reproducible and rollback-safe
- docs in the project root explain the architecture, runtime layout, and validation procedure
- stock WireGuard and Android `VpnService` are optional backends, not required for the production runtime path

Current live destructive test result:
- see [REPRODUCIBILITY_TEST_2026_06_04.md](/home/bose/projects/mobile-proxy/REPRODUCIBILITY_TEST_2026_06_04.md)
- VM delete-and-recreate passed with static IP reattach
- phone runtime delete-and-reinstall passed
- live VM release `checkall-vm-observability-20260604` is active
- live phone release `validation-phone-stack-20260605` is active after `operator-cli install-device-stack`
- `operator-cli verify-device` passed against `SM_A022G` and validated the first-party Android `VpnService` package surface
- relay control-plane reports `healthy`, `serving=true`, `publicly_serving=true`, `tun0_present=true`, and recent WireGuard handshake
- VM service check passed for `wg-quick@wg0`, `mobile-relaycontrolpoint`, `mobile-relay-gate`, `mobile-public-proxy`, and `nginx`
- end-to-end public proxy currently passes and returns a carrier IP
- live rotation smoke on 2026-06-05: `4s` and `5s` programmatic airplane bounces did not change IP on the tested run; `5s` temporarily degraded to `waiting_wireguard` and then recovered to `healthy`
- live VM and phone release `tunnel-owner-contract-20260605` deployed; control-plane now reports `tunnel_owner=stock_wireguard_bridge`, making the remaining external tunnel dependency explicit and machine-readable
- Android APK now embeds the WireGuard userspace backend through a vendored `wireguard-tunnel-1.0.20260102.aar`; strict first-party releases require `MOBILE_PROXY_WG_PHONE_PRIVATE_KEY` and `MOBILE_PROXY_WG_SERVER_PUBLIC_KEY`
- live phone release `app-owned-backend-b64-bridge-20260606` is active with `tunnel_owner=stock_wireguard_bridge`; app-owned WireGuard config delivery uses base64 and was verified at the Android app storage layer
- attempted direct stock WireGuard key rotation by editing app files did not re-import the tunnel reliably and was rolled back to restore service; key rotation must use a first-party release or a validated stock-app import path
- remaining non-10/10 blocker: fully programmatic tunnel activation through the stock WireGuard Android app is blocked by Android broadcast/background/permission behavior; remove this dependency with the selected first-party app-owned `VpnService` tunnel engine before claiming no-compromise recovery
- architecture decision: use first-party app-owned `VpnService`; see [ANDROID_TUNNEL_ARCHITECTURE_DECISION.md](/home/bose/projects/mobile-proxy/ANDROID_TUNNEL_ARCHITECTURE_DECISION.md)
- first implementation step completed: Android APK now declares and installs an app-owned `VpnService`, command receiver, and boot receiver; real embedded tunnel engine is still required before 10/10
- superseding architecture decision: make `first_party_reverse_tunnel` the required 10/10 path and keep WireGuard/Android `VpnService` optional; see [REVERSE_TUNNEL_ARCHITECTURE_DECISION.md](/home/bose/projects/mobile-proxy/REVERSE_TUNNEL_ARCHITECTURE_DECISION.md)
- first reverse-tunnel PoC completed: `cargo test -p reverse-tunnel` passed locally on 2026-06-06 for reconnect after server drop, reconnect after VM listener restart, and stable session identity across reconnects
- reverse-tunnel baseline expanded: VM `reverse-tunnel-server` service, phone `host-daemon` reverse client config, token-authenticated hello, server heartbeat registry, wrong-token rejection test, and operator VM/device packaging are implemented
- package checks passed with dummy env: `first_party_reverse_tunnel` phone release renders `wireguard.enabled=false`, `reverse_tunnel.enabled=true`, and VM release includes `mobile-reverse-tunnel-server.service`
- remaining non-10/10 blocker after reverse baseline: public proxy streams are not yet forwarded over the reverse tunnel, so live production traffic still uses the optional stock WireGuard bridge
