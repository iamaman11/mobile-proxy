# Phase C Pending-Stream Lifecycle and Bounds Audit

Status: delivery item 8 complete when this audit is accepted  
Baseline `main`: `fa93ac860b3c699973936d20399458fbf6b74f89`  
Delivery item: 8 — pending-stream lifecycle and bounds

## Decision

No residual runtime change is required for delivery item 8.

The current reserve TLS/TCP implementation already gives every pending proxy-stream registration a bounded lifetime, deterministic cleanup and explicit global and per-device capacity. The controls were implemented and accepted before the canonical Production Baseline Plan isolated this delivery item. The current audit re-evaluates the code and executable evidence against the narrower baseline criteria rather than reimplementing an already-correct path.

Delivery item 8 is therefore complete when this audit is accepted. The next permitted item is delivery item 9, `exact device/session binding`. That next audit must remain separate because target selection when no node is configured is a routing-authority question, not a pending-lifecycle question.

## Inventory and owner

The authoritative pending registry is `ReverseTunnelServerState::pending_tcp` in `crates/reverse-tunnel/src/state.rs`.

Each `PendingTcpProxyRequest` records:

- a random `stream_id`;
- the expected `node_id`;
- the expected authenticated tunnel `session_id`;
- monotonic creation time;
- a monotonic deadline;
- the one-shot response sender for the accepted TCP stream.

There is no second mutable pending registry. The QUIC primary path opens a bidirectional QUIC stream directly and is bounded by the accepted Quinn transport stream ceiling; the explicit pending-registration map exists only for reserve TLS/TCP stream rendezvous.

## Lifecycle proof

The audit verified deterministic removal for every required terminal path.

1. **Successful delivery**
   - `accept_tcp_proxy_stream` validates stream, node, session, deadline, current session freshness and live control ownership;
   - it removes the registration before sending the accepted stream to the requester;
   - a duplicate stream ID is rejected and cannot consume the request twice.
2. **Timeout**
   - every request has a monotonic deadline;
   - both control-frame send and response wait are bounded by that deadline;
   - `PendingTcpCleanupGuard::drop` removes the registration when the request future returns after timeout.
3. **Requester cancellation**
   - aborting or dropping the requester drops the cleanup guard and removes the registration.
4. **Closed control channel**
   - send failure removes the session control and cancels only pending requests bound to that node/session;
   - the request-local cleanup guard also removes its own registration.
5. **Tunnel disconnect**
   - `mark_disconnected` removes matching transport/liveness resources and cancels pending registrations for the exact disconnected session.
6. **Session replacement**
   - `mark_connected` cancels registrations owned by the previous session before the new session becomes authoritative for future work.
7. **Heartbeat expiry**
   - stale session expiry removes the matching control and cancels the matching pending registrations;
   - a late proxy stream for an expired request is rejected.
8. **Explicit server shutdown**
   - `shutdown_tcp` drains controls and clears the pending registry;
   - waiting requesters observe cancellation.

Mismatched node or session attempts do not consume a still-valid request. This allows the legitimate expected phone/session to complete it while the fixed deadline still guarantees bounded retention.

## Capacity and expiry proof

The reserve pending registry is guarded by one synchronization boundary for insertion, capacity checks, acceptance and cleanup.

- global maximum: `256` pending TCP streams;
- per-device maximum: `32` pending TCP streams;
- ordinary request deadline: `5 seconds`;
- capacity exhaustion rejects the new request without evicting an existing unrelated registration;
- one device reaching its per-device ceiling does not prevent another device from using remaining global capacity;
- failed capacity checks do not insert partial state;
- all stored deadlines are monotonic and validated against creation time.

The implementation therefore satisfies the baseline invariant that pending registrations have explicit global/per-device bounds, bounded expiry and deterministic fail-closed exhaustion behavior.

## Executable evidence

Current unit tests prove:

- correct node/session completion removes the request;
- wrong node and wrong session are rejected without consuming the legitimate request;
- stale, replaced or inactive sessions cannot deliver a pending stream;
- timeout removes the request;
- requester cancellation removes the request;
- control-channel close removes the request;
- explicit shutdown clears requests and controls;
- global capacity is enforced without eviction;
- per-device capacity is enforced without eviction;
- one full device does not block another device;
- duplicate stream acceptance is rejected;
- session replacement and disconnect cancel only the affected session's pending work.

Original implementation acceptance:

- PR #3: `Bind TCP proxy streams to device sessions`;
- accepted source: `b2316b31f2633eb425446f3cc535c3f1f95126ef`;
- squash merge: `237fc455255eba8137821887f4016dcbc47ac125`;
- permanent `Rust Quality` run: `30011540110`;
- changed files: `crates/reverse-tunnel/src/state.rs` and `crates/reverse-tunnel/src/tunnel.rs`;
- branch lag before merge: `0`;
- reviews and unresolved inline threads: none.

Current-code revalidation:

- Phase B closeout source: `552602eca16f3351236747bbe891550f08bb8d0b`;
- permanent `Rust Quality` run: `30119869287`;
- architecture enforcement, rustfmt, strict Clippy and complete workspace tests: successful;
- current `main`: `fa93ac860b3c699973936d20399458fbf6b74f89`.

## Residual risks and scope boundary

No P0/P1 lifecycle or capacity defect was found for the pending registry.

This decision does not claim delivery item 9. The server still permits an unconfigured target to enter selection logic that searches active sessions. Whether every production listener must require an exact configured device and how session authority is bound across all transports must be audited under `exact device/session binding`.

This audit also does not claim forced QUIC/TLS fallback acceptance, health semantics, backup/restore or physical-device completion.

## Compatibility result

No code changes are required. Mixed proxy `1080`, SOCKS5 `1081`, HTTP/CONNECT `3128`, QUIC-first transport, certificate-pinned TLS/TCP reserve and WireGuard rollback remain unchanged.

## Exact next delivery item

Delivery item 9: `exact device/session binding`.

The next slice must audit all paths that select a tunnel or control channel, determine whether any production request can route through an arbitrary first active device, and fix only demonstrated selection or stale-authority gaps. It must not pull forward forced fallback/recovery, health, backup/restore or physical-device work.
