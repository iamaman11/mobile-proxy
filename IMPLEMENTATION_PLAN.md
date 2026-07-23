# Mobile Proxy Implementation Plan

The sole canonical roadmap for current development is:

- [Production Baseline Plan](docs/PRODUCTION_BASELINE_PLAN.md)

All work must begin by reading that document. It defines the active delivery order, protected compatibility surface, system invariants, module responsibilities, strict development protocol, Definition of Done and context-loss recovery procedure.

The previous broad platform roadmap is retained only as distant-future product direction:

- [Distant-Future Ultimate Implementation Plan](docs/future/ULTIMATE_IMPLEMENTATION_PLAN.md)

The future document is not an active backlog and does not authorize implementation work. Activating any part of it requires a separate product decision and an explicit update to the Production Baseline Plan.

Related bounded normative artifacts:

- [ADR-001: Bounded Contexts and Clean Dependency Rules](docs/architecture/ADR-001-bounded-contexts-and-clean-dependencies.md)
- [ADR-002: Cryptographic Hashing, Password Hashing and KDF Policy](docs/architecture/ADR-002-cryptographic-hashing-and-kdf-policy.md)
- [Digest Inventory and Migration Matrix](docs/architecture/digest-inventory-and-migration.md)
- [Foundation Identifiers, Request Lineage and Deadlines](docs/architecture/foundation-primitives.md)
- [Invariant Enforcement Audit](docs/architecture/invariant-enforcement.md)
- [Machine-readable Invariant Enforcement Matrix](contracts/governance/invariant-enforcement.json)
- [Protected Proxy Compatibility Contract](contracts/compatibility/proxy-surface-v1.json)

Repository state and the canonical baseline plan take precedence over external checkpoints, chat history or remembered intent.
