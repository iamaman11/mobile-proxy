# Reverse Tunnel Architecture Decision

Date: 2026-06-06

## Decision

The target 10/10 runtime path is `first_party_reverse_tunnel`.

WireGuard remains an optional backend, not the required production path. The required path is a first-party Rust userspace tunnel where the phone initiates and maintains an encrypted outbound session to the VM.

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
  -> outbound encrypted session
  -> VM reverse-tunnel server
  -> relay/control-plane/public proxy
```

The phone remains the connection initiator. This matches mobile NAT and carrier networks better than inbound VM-to-phone dialing.

## Technology Choice

Primary path:

- Rust userspace reverse tunnel
- persistent outbound session from phone to VM
- mutual authentication with env-provided device credentials
- stream framing, heartbeats, reconnect, backoff, and replay-safe session identity
- TLS/QUIC hardening before final live acceptance

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

Command:

```bash
cargo test -p reverse-tunnel
```

Result on 2026-06-06:

```text
5 passed
```

## Implemented Baseline Components

- `crates/reverse-tunnel`: shared protocol, heartbeat, reconnect, server session registry, required token authentication
- `services/reverse-tunnel-server`: VM-side listener on `0.0.0.0:18090`
- `services/host-daemon`: optional phone-side reverse-tunnel client from `reverse_tunnel` config
- `apps/operator-cli provision-vm`: packages `reverse-tunnel-server`, writes its systemd unit, and includes `tcp:18090` in the VM firewall rule
- `apps/operator-cli package-device-release --tunnel-owner first_party_reverse_tunnel`: disables WireGuard, enables reverse tunnel, injects the device tunnel token, and binds local proxy to `127.0.0.1:1080`

## Remaining Acceptance Work

Before this can replace the live path:

- forward public proxy streams over the reverse tunnel
- harden transport encryption beyond token-authenticated TCP
- run phone reboot, VM reboot, process kill, mobile data loss, airplane toggle, and long soak drills

The architecture is not final 10/10 until those live drills pass and `stock_wireguard_bridge` is no longer in the required runtime path.
