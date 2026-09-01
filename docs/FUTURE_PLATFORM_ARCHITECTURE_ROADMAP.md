# Future Platform Architecture Roadmap

> **STATUS: FUTURE / POST-BASELINE RECOMMENDATIONS ONLY**
>
> This document is not an active implementation roadmap, not a release/candidate tracker and not a source of operational current state. The sole active implementation roadmap is `docs/PRODUCTION_BASELINE_PLAN.md`.
>
> Any exact SHA, run ID or acceptance result belongs in a machine-readable contract, generated checkpoint or explicitly historical evidence document. Resolve the exact current protected `main` revision at execution time; do not maintain a hand-edited “current candidate” in this future roadmap.

## Promotion rule

A future item becomes active only when:

1. a dedicated issue defines scope and acceptance criteria;
2. the active Production Baseline (or its explicitly approved successor) adopts the work;
3. implementation is reviewed through protected Git delivery;
4. software quality/evidence pass on the exact immutable candidate selected for that work;
5. physical/infrastructure acceptance appropriate to the change is completed;
6. documentation and machine contracts are updated to the implemented status.

Until promotion, everything below is non-normative future architecture guidance.

## Executive decisions

1. Keep Nginx and sing-box while they retain distinct proven responsibilities.
2. Keep Rust, Tokio, Axum, Quinn/rustls, systemd, SQLite and the first-party reverse tunnel for the current baseline architecture; future changes require measured need.
3. Do not put the VM application into one monolithic container.
4. Harden host-native systemd services before adding a container platform.
5. If containers become justified, use independently versioned service images with immutable digests and narrow privileges.
6. Keep edge/kernel networking responsibilities outside arbitrary application containers unless an explicit redesign proves otherwise.
7. Do not add Kubernetes, a service mesh, Kafka, NATS, Redis or PostgreSQL for appearance.
8. Future platform work never authorizes release or physical acceptance by itself.

## Baseline architecture reference

This future roadmap assumes the stable architectural roles documented by `RUNTIME_LAYOUT.md` and machine contracts:

```text
rooted Android phone
  native rooted runtime
    runtime-supervisor
    host-daemon
    sing-box
    first-party reverse tunnel
      pinned QUIC primary
      pinned TLS/TCP reserve
  managed Android auxiliary component where topology requires
    cellular Network.bindSocket() egress and/or compatibility path

relay VM
  Nginx edge
  reverse-tunnel-server
  control-plane
  relay-gate
  SQLite durable state
  explicit rollback/compatibility components
```

The Android app is not the primary reverse-tunnel owner. Future work must preserve the distinction between the native primary runtime and managed Android auxiliary functions unless a separately accepted architecture change replaces it.

## Technology disposition

### Keep while baseline assumptions hold

- Rust workspace/application boundaries;
- Tokio and Axum;
- Quinn and rustls;
- Nginx at the static edge;
- sing-box for proxy protocol handling;
- hardened systemd for small deployments;
- SQLite WAL while there is one active control-plane writer;
- WireGuard as explicit rollback/compatibility rather than silent default;
- typed project integrity contracts;
- exact-byte deployment verification;
- bounded metrics/evidence;
- immutable release and destructive-acceptance discipline.

### Consider after baseline acceptance

- dedicated non-root service users and stricter systemd sandboxing;
- infrastructure-as-code for reproducible provider state;
- managed secret rotation;
- stronger SBOM/signature/provenance distribution where not already activated;
- broader Android architecture/device compatibility matrices;
- external synthetic proxy probes and alerting;
- per-device asymmetric identity and mTLS enrollment;
- OIDC/operator RBAC and immutable audit records;
- fleet-aware ingress/routing and controlled draining;
- tenant/quota/admission models;
- PostgreSQL only after multi-writer/horizontal-replica requirements justify it;
- per-service containers only after reproducible signed images provide a measured benefit.

### Do not add without measured need

- one all-in-one application container;
- Kubernetes for one VM or a small static relay set;
- a service mesh;
- Kafka/NATS for current command volume;
- Redis as a default dependency;
- Envoy merely to replace a working Nginx edge;
- another custom SOCKS/HTTP implementation on the phone;
- PostgreSQL while a single durable writer remains sufficient;
- microservice splits without independent scaling/security boundaries.

## Future VM hardening

Candidate future controls include dedicated Unix identities, compatible systemd sandboxing, narrow writable paths, capability/system-call restrictions, explicit resource limits, reproducible provisioning and external health validation.

A future container model, if justified, should preserve one responsibility and independently restartable security boundary per service. Rootless/read-only operation, narrow capabilities, runtime-mounted secrets, immutable image digests, verified provenance and exact rollback are prerequisites. WireGuard/kernel networking and static edge ownership remain host-level unless a measured redesign proves a safer alternative.

## F1 — Public-deployment hardening

Possible future work:

- stronger host/service sandboxing;
- narrower administration paths;
- explicit perimeter/IPv6 policy;
- signed/verified supply-chain outputs;
- stronger identity and secret rotation;
- broader supported-device architecture acceptance;
- synthetic probes, metrics, alerts, encrypted backups and reconnect/load drills.

None of these bullets is an active gate until promoted.

## F2 — Fleet and multi-tenant platform

Possible future work:

- unique asymmetric identity per phone;
- enrollment/rotation/revocation lifecycle;
- mTLS-bound tunnel sessions;
- fleet-aware proxy ingress;
- tenant/user resolution and quota enforcement;
- readiness-aware routing/admission;
- controlled draining;
- operator RBAC and immutable audit records;
- relay directory and placement.

## F3 — High availability

Promote SQLite to PostgreSQL only when multiple active control-plane replicas or richer durable product data require it. Then consider multi-zone replicas, point-in-time recovery, command leadership/lease semantics, relay migration and zonal-loss drills.

## F4 — Multi-region and large scale

Possible future work includes regional relay pools, global ingress/placement, autoscaling, progressive delivery, chaos/load/soak programs, data-residency controls and capacity/cost models.

### Kubernetes decision gate

Do not introduce Kubernetes until most of these are demonstrably true:

- multiple relay nodes are continuously active;
- independent horizontal scaling is required;
- automatic placement/self-healing is required;
- rolling deployment across a relay pool is routine;
- operators can safely own upgrades, network policy, secrets and observability;
- measured operational benefit exceeds complexity and attack surface.

Before that threshold, hardened systemd or narrowly scoped service containers are simpler.

## Historical references

Historical acceptance SHAs and run IDs may be cited only in documents whose purpose is to preserve immutable historical evidence, such as Item 19 closeout records. They must not be copied here as “current candidate”, “current gate” or “current synchronized SHA”.
