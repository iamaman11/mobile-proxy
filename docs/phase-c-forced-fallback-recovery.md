# Phase C Forced Fallback and Recovery Proof

Status: delivery item 10 implementation candidate  
Issue: #55  
Scope: controlled software evidence only

## Controlled failure and recovery sequence

The permanent integration test now exercises one logical client session through the complete bounded transport lifecycle:

1. start the certificate-pinned TLS/TCP reserve path while the configured QUIC UDP address is occupied by a non-QUIC socket;
2. start the Hybrid client and require a bounded `connect_timeout` failover reason;
3. prove mixed, SOCKS5, HTTP proxy and HTTP CONNECT behavior through the reserve authority;
4. release the blocked UDP address and start the real QUIC listener on that exact endpoint;
5. terminate the TLS terminator and all active reserve connections so the client must begin a new QUIC-first attempt;
6. require the replacement authority to become QUIC while preserving the same logical client session ID;
7. prove mixed, SOCKS5, HTTP proxy and HTTP CONNECT behavior again through the recovered QUIC authority.

## Executable evidence

`crates/reverse-tunnel/tests/hybrid_transport_recovery.rs` proves:

- the unavailable QUIC path cannot accidentally accept the initial attempt;
- the reserve path is certificate-pinned TLS/TCP rather than plaintext downgrade;
- the fallback reason remains finite and secret-free;
- the first successful transport is TLS/TCP and no QUIC server connection exists during fallback;
- all protected proxy behaviors traverse the reserve tunnel;
- reserve termination removes the currently usable reserve authority and triggers reconnect;
- the client reuses the same logical session ID safely while the server installs a new authority generation;
- the recovered transport is QUIC, the previous failover reason is cleared, and the `tls_tcp -> quic` transition is counted;
- all protected proxy behaviors traverse the recovered QUIC tunnel;
- the server exposes one connected session matching the client session and an active QUIC connection after recovery.

Repository validation must additionally pass architecture enforcement, Python regressions, rustfmt, strict Clippy and the complete workspace test suite on the production-branch SHA.

## Compatibility boundary

The controlled listeners use ephemeral loopback ports to avoid CI collisions while exercising the behavior corresponding to mixed `1080`, SOCKS5 `1081`, and HTTP/CONNECT `3128`. Production port constants and listener configuration are unchanged. QUIC remains primary, certificate-pinned TLS/TCP remains reserve, and WireGuard remains the compatibility and rollback path.

No phone, Android runtime replacement, lease platform, credential broker, protocol migration or future-roadmap scope is introduced.

## Stop condition

After acceptance, delivery item 10 is complete. Stop and reassess Phase C before health semantics, backup/restore or release-candidate work begins.
