# Engineering Guardrails

Status: bounded normative rules for current development  
Scope: modularity, cryptographic use and maintainability without expanding product scope

These rules support the canonical [Production Baseline Plan](../PRODUCTION_BASELINE_PLAN.md). They do not add a new phase, subsystem or product capability.

## Cryptographic boundaries

1. Continue using full BLAKE3-256 for first-party internal persisted digests, integrity manifests, deterministic fingerprints and replay evidence where the application owns the format.
2. Every BLAKE3 value must use the existing typed, algorithm-prefixed representation and purpose-specific versioned domain separation with canonical input framing.
3. BLAKE3 must not replace algorithms required by an external protocol or compatibility contract. SHA-256 remains valid for TLS certificate pinning, standardized artifact or signature formats, Cargo checksums, FIPS-constrained profiles and other external formats that require it.
4. Raw digest strings must not become business vocabulary. Domain and application code consume validated digest types; encoding and parsing remain at boundaries.
5. Algorithm migration is a versioned data-contract migration with compatibility and rollback evidence, never a blind replacement.

## Module and file responsibility

1. One production file should normally express one cohesive responsibility inside one architectural layer.
2. Transport, orchestration, persistence, policy and presentation concerns must not be combined merely to reduce the number of files.
3. A production source file approaching 400 lines requires an explicit responsibility review during the slice.
4. A production source file exceeding 700 non-generated lines requires either decomposition or a written justification in the PR explaining why splitting would reduce cohesion or correctness.
5. Generated code, declarative migration data, protocol fixtures and large test vectors may exceed the thresholds when clearly isolated and not used to hide mixed responsibilities.
6. Line count alone must not cause artificial fragmentation. A split is accepted only when the resulting modules have clear ownership, stable interfaces and lower cognitive coupling.
7. New modules must follow inward dependency direction and must not create cyclic ownership, duplicate canonical state or a generic utility dumping ground.
8. Public APIs should expose the smallest stable surface required by the current slice; implementation details remain private by default.

## Complexity and resource bounds

1. Every queue, registry, retry loop, spawned task set, input body and externally influenced collection has an explicit bound or a documented proof that it is intrinsically bounded.
2. Timeouts, cancellation and cleanup paths are part of normal correctness and require tests where resources or authority can outlive a request.
3. Errors crossing process or trust boundaries are typed, bounded and secret-safe.
4. Hidden fallback, silent coercion and arbitrary first-match selection are forbidden where identity, device, session, state version or cryptographic algorithm matters.
5. New abstractions require a demonstrated current duplication, dependency violation or testability problem. Anticipated future reuse alone is insufficient.

## Enforcement

These rules should use existing review and permanent CI mechanisms. A new checker or inventory is justified only when repeated violations show that review cannot reliably enforce a rule. Any automated file-size check must use a small explicit allowlist for generated or declarative exceptions and must remain advisory below the hard threshold.