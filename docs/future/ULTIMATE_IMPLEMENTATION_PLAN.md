# Ultimate Implementation Plan — Distant Future

Status: archived long-horizon product direction; not normative for current development  
Repository: `iamaman11/mobile-proxy`  
Activation: requires a separate product decision supported by concrete demand and operating evidence

## Why this document was moved

The former Ultimate Implementation Plan described the transformation of a working mobile proxy into a broad autonomous multi-consumer mobile-egress platform. That direction remains technically coherent, but it is substantially larger than the needs of the current application and would distract from the smaller production baseline now required.

The canonical near-term roadmap is [`../PRODUCTION_BASELINE_PLAN.md`](../PRODUCTION_BASELINE_PLAN.md).

This document must not be used to justify near-term scope, create new production slices or block completion of the production baseline. Items below are future options, not current commitments.

## Reactivation criteria

The long-horizon plan may be reconsidered only when at least one of the following is demonstrated:

- several independent consumers require isolated ownership and policy;
- exclusive device allocation is a real product requirement;
- shared proxy credentials create a measured security or operational problem;
- current rotation handling cannot meet required recovery semantics;
- the existing Android/WireGuard model becomes an evidenced constraint;
- fleet scale requires the proposed platform controls;
- a funded product decision explicitly accepts the implementation and operating cost.

Reactivation requires a fresh review of repository state, product requirements, migration risk and the simpler alternatives available at that time.

## Preserved long-horizon direction

The future platform concept preserves the following compatibility surface during any later migration:

- mixed proxy on `1080`;
- SOCKS5 on `1081`;
- HTTP and CONNECT on `3128`;
- QUIC-first reverse tunnel;
- certificate-pinned TLS/TCP reserve transport;
- controlled WireGuard rollback until physical replacement acceptance;
- operator CLI and operator/admin APIs.

The future target is a versioned, authenticated, observable, recoverable and optionally exclusive mobile network identity rather than only a proxy address.

## Future architecture themes

### Clean dependency direction

```text
foundation <- domain <- application <- ports <- adapters <- composition roots
```

Pure domain modules remain isolated from HTTP frameworks, persistence libraries, Android APIs, filesystems, process execution and generated transport models.

### Potential bounded contexts

A future platform may separate:

- foundation and shared contracts;
- device registry;
- network lease management;
- network identity;
- rotation coordination;
- tunnel-session management;
- proxy access and credential brokering;
- persistence and security adapters;
- test support and composition roots.

These modules are not required by the current production baseline.

### Multi-consumer ownership

A future system may attribute operations to consumer, application and actor identities, with generic owner references and data-driven policies. Idempotency may be scoped by consumer, application, operation and key.

### Lease platform

Potential future lease behavior includes:

- exclusive allocation;
- monotonically increasing epochs;
- fencing tokens;
- TTL, renewal, release, revoke and expiry;
- deterministic allocation;
- database-enforced exclusivity;
- lease-bound descriptors and credentials.

No lease-domain work is currently authorized.

### Proxy descriptors and credentials

A later managed platform may return versioned descriptors containing mixed, SOCKS5 and HTTP endpoints, expected network identity, generations, expiry and fingerprints. Credentials may become short-lived, lease-bound, revocable and redacted.

### Extended durable state

Beyond the baseline SQLite store, a future design may introduce durable leases, events, outbox records, rotation jobs, identity observations, credential metadata, audit chains, quarantine records and richer migration machinery.

These tables must not be created pre-emptively.

### Consumer API

A future product may adopt Protocol Buffers and gRPC as canonical contracts with HTTP/JSON as a gateway. Existing raw device and command routes may become operator-only.

No gRPC migration is part of the production baseline.

### Network identity and rotation

A future platform may collect device, relay, external and consumer observations; detect unexpected egress drift; and execute durable fenced rotation workflows with crash recovery and generation management.

The current baseline requires only the existing practical behavior and physical acceptance, not this broader orchestration system.

### Android ownership

A future migration path may evolve from stock WireGuard to a first-party VpnService and eventually an embedded reverse-tunnel runtime, with Keystore-protected configuration and controlled rollback.

The current plan explicitly retains working WireGuard paths and does not authorize replacement.

### Expanded security and audit

Future work may separate platform-admin, operator, consumer, device and relay principals; introduce per-device certificates or signed proof; create lease-specific credentials; and build a transactionally chained audit ledger.

This is optional future platform scope, not a prerequisite for the present application.

### Expanded operations and release engineering

Potential later work includes richer fleet metrics, quarantine and maintenance workflows, disaster-recovery programs, SBOM, signatures, provenance, canary rollout and neutral downstream certification fixtures.

Only the minimum health, backup/restore and physical acceptance work is currently active.

## Archived phase model

The former plan organized the long-horizon transformation as:

0. architecture and compatibility baseline;
1. clean modular boundaries;
2. durable state;
3. multi-consumer lease domain;
4. proxy access and credentials;
5. network identity;
6. durable rotation;
7. tunnel hardening;
8. Android ownership;
9. operations and release.

The current roadmap uses only a deliberately bounded subset of former Phases 1, 2, 7 and 9. Former Phases 3–6 and 8 are deferred in full.

## Archived implementation sequence

The previous direction contemplated roughly 37 incremental production slices, including architecture baselines, application ports, SQLite, durable queues, leases, credentials, identity, rotation, tunnel identity, Android migration, observability, disaster recovery, supply-chain controls and final physical acceptance.

That sequence is no longer the active backlog. Its role is to preserve design thinking in case the project later grows into the platform it described.

## Rules while archived

- Do not mark items in this document as current work.
- Do not add near-term PRs solely to advance this roadmap.
- Do not expand governance to model future invariants before the corresponding feature is approved.
- Do not make the current baseline depend on leases, gRPC, credential brokering, identity consensus or Android replacement.
- Preserve relevant architectural lessons, but choose the simplest implementation that satisfies the active baseline.

## Historical preservation

The complete former normative text remains available in Git history before this roadmap reclassification. This archived document intentionally summarizes the long-horizon direction and its constraints rather than continuing to present every future item as an active requirement.
