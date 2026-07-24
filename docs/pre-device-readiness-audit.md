# Pre-Device Readiness Audit

Status: implementation candidate for superseding the prior software release candidate  
Scope: everything that can be proved or made executable before a physical phone is attached

## Audit result

The prior software candidate passed its source and process tests, but a second operator-level audit found physical-gate gaps that could have produced false-positive or non-executable evidence. Those gaps are closed in this slice before a new immutable candidate is accepted.

## Findings and closures

1. **Local SHA did not prove deployed identity.**
   - Added exact phone-file and VM-file comparison against immutable package roots.
   - Device release metadata must contain the candidate SHA and clean-tree flag.
   - The intended tunnel owner is inferred from the packaged host configuration.
   - The actual Android VPN owner is verified from Android connectivity state.

2. **Mixed port `1080` was incompletely evidenced.**
   - Permanent software acceptance now proves HTTP and CONNECT over mixed `1080` through TLS/TCP fallback and recovered QUIC.
   - Physical stages require SOCKS5, HTTP and CONNECT on `1080`, plus the dedicated `1081` and `3128` paths.

3. **Public proxy authentication was absent from the physical runner.**
   - Proxy username/password are mandatory environment inputs.
   - Credentials are passed to `curl` through stdin configuration, not process arguments.
   - `NO_PROXY` and `no_proxy` are cleared and `--noproxy ''` is forced.

4. **WireGuard rollback was not an executable reversible procedure.**
   - Added bounded VM public-port switching between reverse-tunnel and WireGuard listeners.
   - Nginx configuration is validated before reload and restored automatically if validation fails.
   - Exact loaded configuration digest and public ports are recorded.

5. **Stock WireGuard ownership could false-pass.**
   - Removed the first-party VPN start from the stock WireGuard kick path.
   - Reverse-tunnel startup explicitly stops both compatibility VPN paths.
   - Deployment verification requires the stock WireGuard package UID to own the active Android VPN during rollback and requires no Android VPN during reverse operation.

6. **Return to the original phone release could rebuild or fail to restart.**
   - Added an immutable installed-release activator.
   - It accepts only a bounded release ID, performs a full watchdog/process restart, changes only the active symlink and records the exact active target.
   - Final deployment verification proves the same original package bytes after rollback.

7. **Stage health did not prove the phone was serving.**
   - Every stage now requires exact node identity, `serving=true`, running proxy, cellular-route readiness, proxy-bind readiness, local-serving readiness, durable availability and heartbeat.
   - Reverse stages require fresh exact transport, WireGuard disabled and no `tun0`.
   - WireGuard requires stock owner, `tun0`, recent handshake and inactive reverse tunnel.

8. **Reports could be accepted independently.**
   - Added one fail-closed report-set verifier for three owner-bound deployment checks, three VM transport switches, immutable reverse reactivation and six physical stages on one SHA and one device ID.

## Software evidence

The dedicated `Software Release Candidate` workflow must pass on one unchanged final SHA and produce a new evidence artifact. The previous candidate and evidence are superseded because they do not contain these pre-device guarantees.

The final software acceptance includes architecture and policy checks, Python regressions for all physical-gate tools, rustfmt, strict Clippy, process health, SQLite backup/restore, migration/rollback compatibility, forced QUIC fallback, mixed HTTP/CONNECT recovery and the complete workspace suite.

## Remaining physical-only facts

After the new immutable SHA succeeds, only facts requiring real hardware/network remain:

- Android VPN consent and the real `WiGandroid` tunnel;
- real cellular routing and public egress;
- real phone/service reboot;
- real QUIC UDP blocking while TLS/TCP remains reachable;
- real return to QUIC;
- real stock WireGuard handshake;
- real authenticated public proxy traversal.

No source-controlled or process-testable production-baseline work may remain when the new candidate is promoted to `main`.
