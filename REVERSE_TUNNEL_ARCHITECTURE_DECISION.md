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

Command:

```bash
cargo test -p reverse-tunnel
```

Result on 2026-06-06:

```text
3 passed
```

## Remaining Acceptance Work

Before this can replace the live path:

- implement VM reverse-tunnel server service
- implement phone reverse-tunnel client service or integrate it into `host-daemon`
- forward public proxy streams over the reverse tunnel
- add mutual authentication and transport encryption
- add operator install/provision support
- run phone reboot, VM reboot, process kill, mobile data loss, airplane toggle, and long soak drills

The architecture is not final 10/10 until those live drills pass and `stock_wireguard_bridge` is no longer in the required runtime path.
