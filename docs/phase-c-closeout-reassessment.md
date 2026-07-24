# Phase C Final Closeout and Reassessment

Status: Phase C complete; delivery item 12 authorized after this closeout is accepted  
Baseline `main`: `0e314c8d844c7ffd6fd28c6284cfb669aa45a93f`  
Delivery item closed: 11 — Phase C closeout and reassessment

## Decision

Phase C is complete.

The accepted reserve pending-stream audit, exact device/session/authority binding, and controlled QUIC failure/recovery acceptance together satisfy the canonical Production Baseline Plan. The reverse-tunnel path now has bounded pending work, deterministic lifecycle cleanup, fail-closed target selection, generation-bound authority replacement, a certificate-pinned TLS/TCP reserve, and permanent executable evidence that the same logical client session returns to QUIC after the primary path is restored.

This closeout authorizes only delivery item 12: `separate liveness and readiness semantics`. It does not authorize backup/restore, release-candidate closeout, physical-phone acceptance, future platform scope, a lease platform, credential brokerage, protocol migration or a first-party Android runtime replacement.

## Completion criteria

1. **Pending reserve work is bounded.**
   - global and per-device ceilings are explicit;
   - every pending registration has bounded expiry;
   - success, timeout, cancellation, disconnect, replacement and shutdown remove matching state.
2. **Routing authority is exact and fail closed.**
   - explicit targets never fall through to another node;
   - an unset target is accepted only when exactly one eligible active device exists;
   - QUIC connections, TCP controls, heartbeat refresh and pending reserve streams share the exact node, session and server authority generation.
3. **Superseded authority cannot remain routable.**
   - replacement closes displaced QUIC authority and cancels only displaced reserve work;
   - late heartbeat or disconnect activity from the prior generation cannot mutate its replacement.
4. **QUIC failure is bounded and observable.**
   - an unavailable QUIC endpoint produces a finite failover reason;
   - the fallback is certificate-pinned TLS/TCP, not plaintext downgrade;
   - raw internal errors or credentials do not enter bounded observability fields.
5. **All protected proxy behavior works through reserve and recovered primary paths.**
   - mixed proxy behavior corresponding to `1080`;
   - SOCKS5 behavior corresponding to `1081`;
   - HTTP proxy and HTTP CONNECT behavior corresponding to `3128`.
6. **Recovery returns to QUIC safely.**
   - the QUIC listener is restored on the exact blocked endpoint;
   - reserve authority is terminated in a controlled manner;
   - the client performs a new QUIC-first attempt on the same logical session ID;
   - the server installs one connected QUIC authority generation;
   - the `tls_tcp -> quic` transition and reconnect success are counted.
7. **Compatibility remains protected.**
   - production ports are unchanged;
   - QUIC remains primary;
   - certificate-pinned TLS/TCP remains reserve;
   - WireGuard remains compatibility and rollback path.
8. **No unresolved P0/P1 defect blocks closeout.**
   - the final Phase C source passed architecture enforcement, rustfmt, strict Clippy and the complete workspace test suite;
   - no unresolved review thread or known P0/P1 defect affecting the Phase C guarantees was identified.

## Accepted evidence

### Delivery item 8 — pending-stream lifecycle and bounds

- PR #52;
- accepted source: `417d36fd42c941eb0a08efd6fb8d25499c0b863f`;
- squash merge: `7c49546d60ea0518cfefe356bfb9ff81dc252520`;
- decision: current implementation already satisfied deterministic cleanup, bounded expiry and global/per-device capacity without eviction.

### Delivery item 9 — exact device/session binding

- PR #54;
- accepted source: `12727a043814b73f1de2e96e80f9b5d13b082bd1`;
- squash merge: `c07b864ccb35b8410a74481509bb8836095a980b`;
- permanent `Rust Quality` run: `30126906116`;
- architecture enforcement, rustfmt, strict Clippy and complete workspace tests: successful.

### Delivery item 10 — forced fallback and recovery proof

- PR #56;
- accepted source: `d15010079eceb8815c8f1ecd931d22a130c23c19`;
- squash merge: `0e314c8d844c7ffd6fd28c6284cfb669aa45a93f`;
- permanent `Rust Quality` run: `30128584183`;
- architecture enforcement, rustfmt, strict Clippy and complete workspace tests: successful.

## Residual operational boundary

Phase C intentionally does not claim that process liveness, serving readiness, durable-store health and device/network availability are already separated. Existing health projection contains useful tunnel state, transport and freshness fields, but delivery item 12 must define bounded process-level semantics and prove that absence of a phone cannot make a healthy server process appear dead.

Backup/restore and clean-environment restore remain delivery item 13. Immutable release-candidate software acceptance remains delivery item 14. Physical-phone acceptance remains delivery item 15 and is the only item that may require the real device.

## Exact next delivery item

Delivery item 12: `separate liveness and readiness semantics`.

The next slice must expose bounded, secret-free process liveness and serving readiness; identify critical durable-store and worker readiness separately from device/network availability; retain exact reverse-tunnel state, active transport and freshness; and add process-level executable evidence. It must not pull forward backup/restore or physical-device work.
