# Mobile Proxy Implementation Plan

The canonical implementation roadmap is stored at:

- [Ultimate Implementation Plan](docs/ULTIMATE_IMPLEMENTATION_PLAN.md)

Related normative architecture artifacts:

- [ADR-001: Bounded Contexts and Clean Dependency Rules](docs/architecture/ADR-001-bounded-contexts-and-clean-dependencies.md)
- [ADR-002: Cryptographic Hashing, Password Hashing and KDF Policy](docs/architecture/ADR-002-cryptographic-hashing-and-kdf-policy.md)
- [Digest Inventory and Migration Matrix](docs/architecture/digest-inventory-and-migration.md)
- [Foundation Identifiers, Request Lineage and Deadlines](docs/architecture/foundation-primitives.md)
- [Invariant Enforcement Audit](docs/architecture/invariant-enforcement.md)
- [Machine-readable Invariant Enforcement Matrix](contracts/governance/invariant-enforcement.json)
- [Protected Proxy Compatibility Contract](contracts/compatibility/proxy-surface-v1.json)

The plan is application-neutral: `site-analize-by-pl` is one consumer among many. The protected compatibility surface includes mixed proxy on `1080`, SOCKS5 on `1081`, HTTP/CONNECT on `3128`, QUIC-first transport, certificate-pinned TLS/TCP reserve transport, and controlled WireGuard compatibility until migration acceptance is complete.

This root file is intentionally a stable entry point rather than a duplicate copy, so the detailed roadmap has one canonical source and cannot drift between locations.
