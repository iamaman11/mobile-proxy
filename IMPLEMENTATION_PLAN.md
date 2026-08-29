# Mobile Proxy Implementation Plan

The sole canonical roadmap for current development is:

- [Production Baseline Plan](docs/PRODUCTION_BASELINE_PLAN.md)

All work must begin by reading that document. It defines the active delivery order, protected compatibility surface, system invariants, module responsibilities, strict development protocol, Definition of Done and context-loss recovery procedure.

## Current execution checkpoint

Status: **temporary execution focus**  
Activated: **2026-08-30**  
Authority: subordinate to `docs/PRODUCTION_BASELINE_PLAN.md` and current repository state  
Removal condition: delete this entire section after software-complete release-candidate acceptance is recorded on one immutable Git SHA, or when an explicit product decision supersedes this focus.

The state-ownership governance slice is complete. The current priority is now to produce, exercise and accept a functional production-baseline candidate before undertaking further architecture or governance expansion.

Current execution order:

1. Treat non-essential architecture/governance framework expansion as temporarily closed.
2. Resume the first unfinished delivery item in Section 6 of the Production Baseline Plan and close only evidence-backed production gaps that block a software-complete candidate.
3. Complete all source-controlled and process-testable integrity, recovery, health, tunnel, proxy and rollback evidence required by the baseline on one unchanged candidate SHA.
4. Exercise the complete product path end to end:

   ```text
   startup
     -> state recovery
     -> control plane
     -> phone
     -> QUIC
     -> proxy 1080 / 1081 / 3128
     -> forced TLS/TCP fallback
     -> return to QUIC
     -> restart
     -> restore / rollback
   ```

5. Record software-complete acceptance on that immutable SHA.
6. Run the documented physical-phone acceptance on the same candidate when the physical execution boundary is available.
7. Only after the functional baseline is accepted, perform a fresh architecture re-audit and authorize further refactoring only for demonstrated problems or measured change cost.

At activation time, known incomplete evidence includes the remaining SQLite integrity/clean backup-restore acceptance represented by `PERSIST-002`, the health-surface split represented by `OPS-003`, and any later Production Baseline acceptance items that remain incomplete. This sentence is orientation only, not a second backlog: the Production Baseline Plan, invariant matrix and current repository state always win.

### Temporary architecture freeze

Until this checkpoint is removed, do not introduce architecture or governance refactoring merely to improve theoretical purity. In particular, do not bulk-migrate governance JSON contracts to Protocol Buffers, introduce gRPC, add generic plugin/extension frameworks or perform broad structural rewrites unless a concrete active-baseline blocker demonstrates that the current design cannot satisfy a required invariant.

This freeze does **not** block architecture work required by a demonstrated correctness, security, durability, compatibility, recovery or operational defect. The smallest complete fix remains preferred.

When the removal condition is reached, delete this section rather than moving it to `docs/history/`. Git history is the archive for this temporary sequencing decision.

Project-level authority is defined separately by:

- [Project Authority and Execution Satellites](docs/operations/project-authority.md)
- [Machine-readable Project Authority Contract](contracts/operations/project-authority-v1.json)

`iamaman11/mobile-proxy` is the only canonical repository for project information. The private
`iamaman11/mobile-proxy-production` repository is an execution satellite only and cannot expand,
replace or reinterpret this roadmap.

The previous broad platform roadmap is retained only as distant-future product direction:

- [Distant-Future Ultimate Implementation Plan](docs/future/ULTIMATE_IMPLEMENTATION_PLAN.md)

The future document is not an active backlog and does not authorize implementation work. Activating any part of it requires a separate product decision and an explicit update to the Production Baseline Plan.

Related bounded normative artifacts:

- [ADR-001: Bounded Contexts and Clean Dependency Rules](docs/architecture/ADR-001-bounded-contexts-and-clean-dependencies.md)
- [ADR-002: Cryptographic Hashing, Password Hashing and KDF Policy](docs/architecture/ADR-002-cryptographic-hashing-and-kdf-policy.md)
- [Architecture Quality Standard](docs/architecture/ARCHITECTURE_STANDARD.md)
- [Digest Inventory and Migration Matrix](docs/architecture/digest-inventory-and-migration.md)
- [Engineering Guardrails](docs/architecture/engineering-guardrails.md)
- [Foundation Identifiers, Request Lineage and Deadlines](docs/architecture/foundation-primitives.md)
- [Invariant Enforcement Audit](docs/architecture/invariant-enforcement.md)
- [Machine-readable Invariant Enforcement Matrix](contracts/governance/invariant-enforcement.json)
- [Machine-readable Module Boundaries](contracts/governance/module-boundaries-v1.json)
- [Machine-readable State Ownership](contracts/governance/state-ownership-v1.json)
- [Protected Proxy Compatibility Contract](contracts/compatibility/proxy-surface-v1.json)

Repository state and the canonical baseline plan take precedence over external checkpoints, chat history, private execution-satellite content or remembered intent.
