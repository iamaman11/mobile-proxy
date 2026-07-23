# Mobile Proxy Implementation Plan

The canonical near-term implementation roadmap is:

- [Production Baseline Plan](docs/PRODUCTION_BASELINE_PLAN.md)

The previous broad platform roadmap is archived as distant-future direction and is not normative for current development:

- [Ultimate Implementation Plan — Distant Future](docs/future/ULTIMATE_IMPLEMENTATION_PLAN.md)

Related normative architecture and compatibility artifacts remain applicable where they protect current behavior or enforce an already accepted invariant:

- [ADR-001: Bounded Contexts and Clean Dependency Rules](docs/architecture/ADR-001-bounded-contexts-and-clean-dependencies.md)
- [ADR-002: Cryptographic Hashing, Password Hashing and KDF Policy](docs/architecture/ADR-002-cryptographic-hashing-and-kdf-policy.md)
- [Digest Inventory and Migration Matrix](docs/architecture/digest-inventory-and-migration.md)
- [Foundation Identifiers, Request Lineage and Deadlines](docs/architecture/foundation-primitives.md)
- [Invariant Enforcement Audit](docs/architecture/invariant-enforcement.md)
- [Machine-readable Invariant Enforcement Matrix](contracts/governance/invariant-enforcement.json)
- [Protected Proxy Compatibility Contract](contracts/compatibility/proxy-surface-v1.json)

The protected compatibility surface includes mixed proxy on `1080`, SOCKS5 on `1081`, HTTP/CONNECT on `3128`, QUIC-first transport, certificate-pinned TLS/TCP reserve transport and controlled WireGuard compatibility.

Current development is intentionally limited to the production baseline: finish the existing application boundaries, establish minimum SQLite durability, correct critical reverse-tunnel failure modes, and complete backup/restore plus physical acceptance. Future platform features require a separate explicit product decision.
