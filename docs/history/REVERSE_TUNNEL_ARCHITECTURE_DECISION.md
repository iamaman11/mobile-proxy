# Reverse Tunnel Architecture Decision

Date: 2026-06-06

## Decision

The target 10/10 runtime path is `first_party_reverse_tunnel`.

WireGuard remains an optional backend, not the required production path. The required path is a first-party Rust userspace tunnel where the phone initiates and maintains an encrypted outbound QUIC/TLS session to the VM.

## Why This Replaces The Required Android VPN Path

Android `VpnService` requires user consent and device-specific policy behavior. On the tested Samsung `SM_A022G`, the first-party VPN consent dialog opens and immediately closes in automation, and the live runtime remains dependent on stock WireGuard.

For a fully reproducible phone + VM product, the required path must not depend on:

- stock `com.wireguard.android`
- Android `VpnService` consent
- always-on VPN UI state
- editing another app's private config files

## Target Runtime Shape

```text
phone runtime-supervisor
  -> phone host-daemon
  -> reverse-tunnel client
  -> outbound QUIC/TLS session
  -> VM reverse-tunnel server
  -> VM loopback public proxy listeners
  -> nginx public ports
```

The phone remains the connection initiator. This matches mobile NAT and carrier networks better than inbound VM-to-phone dialing.

## Technology Choice

Primary path:

- Rust userspace reverse tunnel over QUIC/TLS
- persistent outbound session from phone to VM
- pinned server certificate and token-authenticated device hello
- stream framing, heartbeats, reconnect, backoff, and replay-safe session identity
- server-opened bidirectional streams for public proxy TCP forwarding
- phone-local proxy target fixed by phone config, not chosen by the VM
- QUIC keepalive and idle timeout for automatic reconnect after VM-side tunnel restarts
- phone health is gated on `reverse_tunnel_connected=true` for the required `first_party_reverse_tunnel` path
- post-rotation cellular bounces force a fresh QUIC client session before the rotation job can be accepted as successful
- server-side session cleanup is session-aware: stale disconnects cannot remove a newer active connection for the same node

WireGuard:

- optional backend only
- useful for overlay experiments or devices where VPN consent is acceptable
- not a 10/10 dependency

## Initial Test Evidence

The new `crates/reverse-tunnel` PoC has deterministic local Rust tests:

- client reconnects after server drops the connection
- client reconnects after VM listener restart on the same address
- client preserves session identity across reconnects
- server tracks connected/disconnected state from heartbeat flow
- server rejects clients with the wrong tunnel token
- QUIC/TLS transport carries the heartbeat/session protocol
- QUIC/TLS server rejects wrong-token clients without registering a session
- QUIC/TLS reverse tunnel forwards TCP bytes from a VM-side listener to the phone-local proxy and back
- stale disconnect after a newer session does not clear the active server session

Command:

```bash
cargo test -p reverse-tunnel
```

Result on 2026-06-06:

```text
9 passed
```

## Implemented Baseline Components

- `crates/reverse-tunnel`: shared protocol, QUIC/TLS transport, heartbeat, reconnect, server session registry, required token authentication, and public TCP stream forwarding
- `services/reverse-tunnel-server`: VM-side QUIC listener on `0.0.0.0:18090/udp` and loopback public proxy forward listeners on `127.0.0.1:14080,14081,14128`
- `services/host-daemon`: optional phone-side reverse-tunnel client from `reverse_tunnel` config
- `services/host-daemon`: reverse-tunnel manager with restart signal, health status projection, and post-rotation fresh-session refresh
- `apps/operator-cli provision-vm`: packages `reverse-tunnel-server`, writes its systemd unit, and includes `udp:18090` in the VM firewall rule
- `apps/operator-cli package-device-release --tunnel-owner first_party_reverse_tunnel`: disables WireGuard, enables QUIC reverse tunnel, injects the device tunnel token and pinned server certificate, and binds local proxy to `127.0.0.1:1080`

## Remaining Acceptance Work

Before this can be called live 10/10:

- complete the phone reboot matrix after fixing the current `SM-A022G`/`MTS BY` cellular boot latency; current automatic recovery is reliable in smoke but takes roughly `138-145s`, above the p95 `<60s` target
- replace JSON control frames with compact binary frames before performance acceptance
- run long soak on the first-party reverse-tunnel runtime

## Live Switch Evidence

On 2026-06-07, the live VM and rooted Samsung `SM_A022G` were switched to the first-party reverse tunnel:

- VM release: `first-party-quic-live-20260607-obs`
- phone release: `first-party-quic-phone-20260607-obs`
- `operator-cli verify-device --required-tunnel-owner first_party_reverse_tunnel` passed
- public proxy `34.118.88.54:3128` returned carrier IP `178.168.185.80`
- `stock_wireguard_bridge` is no longer the required live traffic path
- recovery drills passed for `host-daemon` kill, `sing-box` kill, `runtime-supervisor` kill, VM reverse tunnel service restart, one full phone reboot, and one full VM reboot after adding watchdog and QUIC keepalive hardening

On 2026-06-08, live hardening closed the main reverse-tunnel recovery bugs:

- phone health now includes `reverse_tunnel_connected` and `reverse_tunnel_last_error`
- first-party reverse-tunnel health no longer reports `healthy` when the QUIC client is disconnected
- server session cleanup no longer lets an old disconnect remove a newer active connection
- Android watchdog process no longer matches `pkill -f runtime-supervisor`
- post-rotation airplane bounce restarts the QUIC client and waits for a fresh connected session
- `4s` programmatic airplane bounce passed strict live validation `30/30` with IP change, healthy return, connected reverse tunnel, and public proxy carrier-IP smoke
- counted phone process recovery passed for `host-daemon`, `sing-box`, and `runtime-supervisor` kills, `20/20` each
- counted VM service recovery passed for `mobile-relaycontrolpoint`, `mobile-relay-gate`, `mobile-public-proxy`, `mobile-reverse-tunnel-server`, and `nginx`; full VM reset passed `10/10`
- QUIC client reconnect backoff now resets after a connected session drops, preventing VM reverse-tunnel service restarts from growing recovery time over repeated drills
- Android `service.sh` now validates the watchdog PID by `/proc/<pid>/cmdline`, preventing stale PID reuse from blocking runtime startup after phone reboot

The architecture is not final 10/10 until phone reboot recovery meets the accepted threshold or the threshold is explicitly re-baselined for this hardware/operator, followed by the full counted phone-reboot matrix and long soak.
