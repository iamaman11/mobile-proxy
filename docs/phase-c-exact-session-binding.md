# Phase C Exact Device and Session Binding

Status: delivery item 9 implementation candidate  
Issue: #51  
Scope: exact routing authority only

## Named production defects

The public proxy listeners accepted an unset target and independently selected the first active entry from unordered session maps. With more than one eligible phone, traffic could be routed to an arbitrary device. QUIC connections were also keyed only by node ID, so a stale connection could survive session replacement and be selected under newer liveness.

## Bounded correction

- resolve one exact `node_id + session_id + server authority generation` before choosing QUIC or TLS/TCP;
- allow an unset target only when exactly one eligible active device exists;
- never fall back from an explicit target to another node;
- bind QUIC connections, TCP controls, heartbeat refresh, pending reserve streams and disconnect cleanup to the same authority generation;
- replace prior QUIC and TCP authority under one state transition, cancel only displaced pending work and close the displaced QUIC connection;
- ignore late heartbeat or disconnect activity from a superseded authority, including reconnects that reuse the same client session ID.

The server-side authority generation is intentionally internal. It closes the demonstrated race where the client may reuse one authenticated session ID across QUIC failure and TLS/TCP recovery while the old handler is still unwinding.

## Executable evidence

The reverse-tunnel unit suite now proves:

- an unset target succeeds with exactly one active device;
- an unset target fails closed with two active devices and emits no `OpenProxy` frame;
- an explicit target sends work only to that node;
- session-bound resource removal requires exact session and authority equality;
- a superseded authority cannot refresh heartbeat state or disconnect its replacement;
- existing pending-stream mismatch, timeout, cancellation, shutdown and capacity tests remain in place.

Repository validation must additionally pass architecture enforcement, Python regressions, rustfmt, strict Clippy and the complete workspace test suite on the production-branch SHA.

## Compatibility boundary

Mixed proxy `1080`, SOCKS5 `1081`, HTTP/CONNECT `3128`, QUIC-first behavior, certificate-pinned TLS/TCP reserve and WireGuard rollback remain unchanged. Forced failover/recovery proof, health semantics, backup/restore and physical-device work remain outside this slice.

## Stop condition

After acceptance, proceed only to delivery item 10: forced QUIC/TLS fallback and recovery proof.
