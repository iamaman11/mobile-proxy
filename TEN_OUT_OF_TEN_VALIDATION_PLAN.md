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
- `cargo run -p operator-cli -- generate-reverse-tunnel-identity --output-env-file .secrets/reverse-tunnel.env`
- `cargo run -p operator-cli -- prepare-runtime-binaries`
- `cargo run -p operator-cli -- install-android-app --device-serial R58T10QKGBE`
- `cargo run -p operator-cli -- install-device-stack --manifest-path deploy/manifests/devices/example-device.json --release-id validation-phone --device-serial R58T10QKGBE`
- `cargo test -p reverse-tunnel`
- `cargo run -p operator-cli -- verify-device --manifest-path deploy/manifests/devices/example-device.json --device-serial R58T10QKGBE --required-tunnel-owner first_party_reverse_tunnel`
- `cargo run -p operator-cli -- package-device-release --manifest-path deploy/manifests/devices/example-device.json --release-id validation-package`
- `cargo test -p reverse-tunnel quic_reverse_tunnel_forwards_tcp_bytes_to_phone_proxy`

Acceptance:
- all Rust sources, configs, manifests, docs, VM provisioning code, `runtime-supervisor`, and `host-daemon` source are in git
- generated Android runtime binaries stay out of git under `deploy/device-runtime/bin/*`
- `runtime-supervisor` and `host-daemon` are rebuildable from source
- `sing-box` is downloaded or supplied separately by `prepare-runtime-binaries`
- live secrets are supplied only through environment variables
- reverse tunnel cert/key env can be generated reproducibly with `operator-cli generate-reverse-tunnel-identity`; the generated `.secrets/` file is local-only and ignored by git

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
- `mobile-relaycontrolpoint`, `mobile-relay-gate`, `mobile-reverse-tunnel-server`, and `nginx` are active
- `wg-quick@wg0` and `mobile-public-proxy` may remain installed only as optional WireGuard backend components, not as required first-party reverse-tunnel dependencies
- control-plane state exists at `/var/lib/mobile-relaycontrolpoint/control-plane-state.json` after registration/heartbeat and survives service restart
- ports `8080`, `1080`, `1081`, `3128`, and `18090/udp` are reachable as designed
- VM nginx public ports `1080`, `1081`, and `3128` forward to Rust reverse-tunnel-server loopback listeners `14080`, `14081`, and `14128`
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
- first-party reverse tunnel is refreshed after each successful cellular bounce before rotation is accepted as `succeeded`

Latest live evidence:
- invalid pre-fix matrix `target/rotation-matrix-20260607-sessionfix.jsonl` exposed the bug: rapid back-to-back rotations could leave VM public proxy streams returning `Empty reply from server` while phone-local health was already `healthy`
- fix added: post-rotation QUIC client restart/refresh in `host-daemon`, session-aware disconnect handling in `reverse-tunnel-server`, and reverse tunnel connected state in phone/control-plane health records
- valid post-fix matrix `target/rotation-matrix-20260608-rt-refresh-4s-strict-retry.jsonl`: `4s` programmatic airplane bounce passed `30/30`; every run changed IP, returned to `healthy`, kept `reverse_tunnel_connected=true`, and public proxy smoke returned a non-empty carrier IPv4
- supporting matrix `target/rotation-matrix-20260608-rt-refresh-4s5s.jsonl`: `4s` and `5s` both passed `30/30` for job + health + reverse-tunnel readiness; single-shot public smoke had transient empty bodies, so the strict retry matrix is the acceptance source
- measured rejected windows before the refresh fix: `1s=23/30`, `2s=26/30`, `3s=28/30`; they do not meet the `>=99%` rule
- selected minimum window: `4s`

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
- QUIC/TLS baseline added: reverse tunnel now supports pinned-certificate QUIC transport on `udp:18090`; local tests cover QUIC heartbeat/disconnect and wrong-token rejection
- reverse tunnel secrets now require `MOBILE_PROXY_REVERSE_TUNNEL_CERT_DER_B64` and `MOBILE_PROXY_REVERSE_TUNNEL_KEY_DER_B64` for VM packaging, and the certificate pin for phone packaging
- QUIC/TLS data-plane added: `cargo test -p reverse-tunnel` now includes `quic_reverse_tunnel_forwards_tcp_bytes_to_phone_proxy`, proving local VM-side TCP listener -> QUIC/TLS -> phone-local proxy -> QUIC/TLS -> VM response forwarding
- live first-party reverse tunnel switch completed on 2026-06-07: VM release `first-party-quic-live-20260607-obs` and phone release `first-party-quic-phone-20260607-obs` are active
- `operator-cli verify-device --required-tunnel-owner first_party_reverse_tunnel` passed on 2026-06-07, including public proxy smoke
- public proxy `34.118.88.54:3128` returned carrier IP `178.168.185.80` through the Rust QUIC/TLS reverse tunnel
- packaging bug fixed: `first_party_reverse_tunnel` phone releases now render `sing-box` loopback listeners on `127.0.0.1`, matching `host-daemon` and reverse tunnel local proxy config
- recovery fixes added on 2026-06-07: Android bootstrap now runs a watchdog loop for `runtime-supervisor`; supervisor no longer exits on failed Android recovery commands; proxy restarts in reverse-tunnel mode refresh `host-daemon` and the QUIC session
- live recovery drills passed on 2026-06-07 for `host-daemon` kill, `sing-box` kill, `runtime-supervisor` kill, VM `mobile-reverse-tunnel-server.service` restart, one full phone reboot, and one full VM reboot
- QUIC keepalive/idle timeout added so phone reconnects automatically after VM reverse tunnel service restart
- 2026-06-08 hardening completed: control-plane `/api/v1/ip` no longer returns a stale fake observer IP; phone observer uses external `api.ipify.org`; airplane fallback uses Android `settings put global airplane_mode_on` plus `AIRPLANE_MODE` broadcast
- 2026-06-08 watchdog fix completed: Android runtime watchdog now runs from `runtime-watchdog.sh`, so `pkill runtime-supervisor` no longer kills the watchdog command line; installer cleanup removes both old and new watchdog forms before applying a release
- 2026-06-08 reverse tunnel health fix completed: `HealthRecord`, heartbeat, and control-plane records include `reverse_tunnel_connected` and `reverse_tunnel_last_error`; first-party reverse-tunnel health cannot be `healthy` unless QUIC client status is connected
- 2026-06-08 reverse tunnel session fix completed: stale session disconnects no longer delete newer active server connections
- 2026-06-08 post-rotation refresh completed: after airplane bounce, host-daemon restarts the QUIC reverse tunnel client and waits for a fresh connected session before accepting rotation success
- live releases after hardening: VM `first-party-quic-live-20260607-sessionfix`, phone `first-party-quic-phone-20260608-rotation-rt-refresh`
- `cargo fmt --check && cargo test && cargo clippy --all-targets --all-features -- -D warnings` passed after these changes
- `operator-cli verify-device --required-tunnel-owner first_party_reverse_tunnel` passed after VM restart and after `runtime-supervisor` kill recovery
- strict rotation acceptance passed for selected `4s`: `target/rotation-matrix-20260608-rt-refresh-4s-strict-retry.jsonl` reports `30/30`
- 2026-06-08 counted phone process recovery passed: `target/recovery-drill-phone-processes-20260608.jsonl` reports `host-daemon=20/20`, `sing-box=20/20`, and `runtime-supervisor=20/20`
- 2026-06-08 counted VM service recovery passed: `target/recovery-drill-vm-services-20260608-retry.jsonl` reports `mobile-relaycontrolpoint=20/20`, `mobile-relay-gate=20/20`, and `mobile-public-proxy=20/20`
- 2026-06-08 VM reverse-tunnel restart backoff bug fixed: the phone QUIC client now resets reconnect backoff after a previously connected session drops; `target/recovery-drill-vm-reverse-tunnel-20260608-backoff-reset.jsonl` reports `mobile-reverse-tunnel-server=20/20`, median `14.357s`, p95 `17.358s`
- 2026-06-08 nginx restart recovery passed: `target/recovery-drill-vm-nginx-20260608.jsonl` reports `20/20`, median `1.09s`, p95 `2.324s`
- 2026-06-08 full VM reset recovery passed: `target/recovery-drill-vm-reboots-20260608.jsonl` reports `10/10`, median `28.916s`, p95 `38.042s`
- 2026-06-08 Android boot hook hardening completed: `/data/adb/service.d/99-mobile-proxy-runtime.sh` no longer has a fixed `sleep 20`; it starts the active release immediately with a bounded retry loop and timestamp logs
- 2026-06-08 Android watchdog stale-PID bug fixed: `service.sh` now validates the watchdog PID through `/proc/<pid>/cmdline`, not only `kill -0`; this prevents a reused Android PID from blocking runtime startup after reboot
- 2026-06-08 phone reboot recovery after stale-PID fix passed as a smoke: `target/recovery-drill-phone-reboots-20260608-watchdog-pidfix-smoke.jsonl` reports automatic recovery and public proxy success, but elapsed time is `141.324s`
- 2026-06-08 feasibility profiling found that the p95 `<60s` phone full-reboot target is not currently achievable on the tested `SM-A022G`/`MTS BY` path: after full reboot, Android/root returns around `45s`, but modem/data registration and usable Internet can remain unavailable far beyond `60s`; one profiler run stayed non-serving for the full `567s` observation window before later recovering
- 2026-06-08 fresh phone runtime reinstall passed: `/data/adb/mobile-proxy-node` and boot hook were removed, release `fresh-phone-runtime-20260608-pidfix` was installed from repo/env, and `verify-device --required-tunnel-owner first_party_reverse_tunnel` passed
- 2026-06-08 VM reproducibility check passed: `operator-cli provision-vm --release-id repro-vm-20260608-final` rebuilt from source, installed the VM release, restarted services, verified listeners, and `verify-device` passed afterward
- 2026-06-08 final soak completed: `target/soak-20260608-final.jsonl` ran `120` samples over roughly `60` minutes; `119/120` single-shot samples passed, and the only failure had phone health `healthy`, `reverse_tunnel_connected=true`, and an empty single-shot public proxy response; an immediate follow-up public proxy check passed `20/20`
- `operator-cli` public proxy smoke now requires a valid IPv4 body, not only HTTP 2xx, and keeps bounded retries
- remaining non-10/10 blocker after live reverse switch: phone full-reboot recovery on `SM-A022G`/`MTS BY` is reliable in normal smoke but too slow and too operator/modem-dependent for the target p95 `<60s`; do not claim 10/10 until this is solved with a different device/operator/modem strategy or the acceptance target is explicitly re-baselined
- remaining work before claiming 10/10: choose the phone-reboot acceptance strategy, then run the full `20` phone-reboot matrix on the final accepted hardware/profile
