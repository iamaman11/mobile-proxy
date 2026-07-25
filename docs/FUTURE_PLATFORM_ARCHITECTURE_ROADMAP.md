# Future Platform Architecture Roadmap

## Status and scope

This document records recommendations beyond the immutable physical-acceptance candidate
`778c9a6260f58ede0f5a337c5107bc96b022373c`.

It is intentionally developed on a separate branch and must not be merged into `main` before
issue #64 completes. Any merge or source change to `main` creates a new candidate and requires a
new complete software evidence cycle before physical acceptance.

The current candidate is a strong production baseline for one rooted phone and one relay VM. This
roadmap describes the additional work required for a hardened public deployment, a managed fleet,
multi-tenancy, high availability and multi-region operation.

## Executive decisions

1. Keep both Nginx and sing-box. They perform different roles and are not accidental duplication.
2. Keep Rust, Tokio, Axum, Quinn/rustls, systemd, SQLite and the first-party reverse tunnel for the
   current single-node baseline.
3. Do not replace the current VM deployment with one monolithic container containing the entire
   application.
4. Before considering containers, apply least privilege and systemd sandboxing to the current
   host-native services.
5. If containers are introduced later, use one independently versioned container per service and
   operate them through Podman Quadlet/systemd or an equivalent minimal OCI runtime.
6. Keep Nginx and WireGuard host-level initially because they own public listeners, TLS/L4 edge
   behavior and kernel networking. Revisit this only after a measured operational benefit exists.
7. Do not introduce Kubernetes, a service mesh, Kafka, NATS, Redis or PostgreSQL merely for
   appearance. Add them only when explicit scaling or availability requirements justify them.

## Current production architecture

```text
rooted Android phone
  root/Magisk service
    runtime-supervisor
      host-daemon
      sing-box on loopback
        direct cellular egress
      first-party reverse tunnel client
        QUIC primary
        pinned TLS/TCP reserve

relay VM
  Nginx
    TLS termination for the control plane
    public TCP proxy listeners
    atomic native/WireGuard backend switching
    TLS/TCP reverse-tunnel reserve on 443
  reverse-tunnel-server
  control-plane
  relay-gate
  standby WireGuard interface
  standby VM sing-box for WireGuard rollback
  SQLite durable control-plane state
```

### Nginx responsibility

Nginx is the static public edge and L4/TLS switching layer. It should continue to own:

- public TCP listeners;
- control-plane TLS termination;
- the pinned TLS/TCP reverse-tunnel reserve listener;
- stable public addresses while internal backends change;
- bounded connection and timeout policy;
- atomic native reverse-tunnel versus WireGuard rollback switching.

Nginx must not become the fleet scheduler or tenant authorization engine. It cannot make rich
routing decisions from device health, tenant policy, quotas or proxy credentials without excessive
complexity.

### sing-box responsibility

sing-box is the proxy protocol engine. On the phone it should continue to own:

- SOCKS5;
- HTTP proxy and CONNECT;
- local proxy authentication;
- protocol parsing and proxy compatibility;
- direct cellular egress.

The Rust reverse tunnel should continue to transport authenticated byte streams rather than
reimplementing every proxy protocol on the phone.

The VM sing-box is only a WireGuard rollback adapter. It should be dormant during normal native
operation.

## Technology disposition

### Keep

- Rust 2024 workspace boundaries;
- Tokio asynchronous runtime;
- Axum HTTP services;
- Quinn and rustls for QUIC and TLS;
- Nginx for public L4/TLS edge behavior;
- sing-box for SOCKS/HTTP protocol handling;
- systemd for the current single-VM deployment;
- SQLite WAL for one active control-plane writer;
- WireGuard as an explicit dormant rollback path;
- typed BLAKE3 internal integrity contracts and exact-byte deployment verification;
- Prometheus-compatible bounded metrics;
- immutable-SHA release evidence and destructive acceptance testing.

### Add when justified

- hardened systemd service identities and sandboxing;
- OS Login and IAP-only administration;
- Terraform or OpenTofu infrastructure as code;
- cloud secret management and automated rotation;
- signed OCI/release artifacts, SBOM and provenance;
- ARM64 Android build and acceptance;
- external synthetic SOCKS/HTTP/CONNECT probes;
- Prometheus-compatible collection, Alertmanager and Grafana or managed equivalents;
- per-device asymmetric identity and mTLS enrolment;
- OIDC, operator RBAC and immutable audit records;
- a Rust fleet-aware proxy ingress gateway;
- tenant, user, quota and admission-control models;
- relay directory, regional placement and controlled draining;
- PostgreSQL only when horizontal control-plane replicas or richer durable product data require it;
- Podman Quadlet per-service OCI deployment only after images are reproducible and signed.

### Do not add without a measured need

- one all-in-one application container;
- Kubernetes for a single VM or a small static relay set;
- Istio or another service mesh;
- Kafka or NATS for the current command volume;
- Redis as a default dependency;
- Envoy merely to replace a working static Nginx edge;
- a second custom SOCKS/HTTP implementation on the phone;
- PostgreSQL while the control plane remains a single writer;
- numerous microservices with no independent scaling or security boundary.

## VM deployment model decision

### Current state

The relay VM is not an application container. Components are installed directly onto the Linux
host and started as separate systemd services. Nginx and WireGuard are distribution packages,
while the Rust binaries and sing-box binary are copied into versioned application directories.
SQLite state, certificates, service environment files and Nginx/WireGuard configuration live in
host paths.

This is a host-native multi-process deployment, not a monolithic process and not a containerized
application.

### Should the whole application be put into one container?

No.

A single container containing Nginx, control-plane, reverse-tunnel-server, relay-gate, sing-box,
WireGuard tooling and SQLite would reduce rather than improve isolation:

- one restart would restart every subsystem;
- one compromised process would share a filesystem and namespace with all other services;
- readiness and rollback would become coarser;
- privileges required by WireGuard or public listeners would contaminate unrelated services;
- logs, resource limits and upgrades would be coupled;
- it would require an internal supervisor and recreate work already performed by systemd;
- independent versioning and canary rollout would be harder.

The desired invariant is one responsibility and one independently restartable security boundary per
service, whether that boundary is a systemd unit or an OCI container.

### Recommended near-term model

Keep host-native systemd for the physical baseline and the first hardened public deployment, but
change the service model to:

```text
host Linux
  nginx                     dedicated user/capabilities where practical
  wireguard                 host kernel/networking; normally inactive
  control-plane             dedicated unprivileged user
  reverse-tunnel-server     dedicated unprivileged user plus only required bind capability
  relay-gate                dedicated unprivileged user
  rollback sing-box         dedicated unprivileged user; normally inactive
  SQLite                    private state directory owned only by control-plane
```

Each systemd unit should use the strictest compatible subset of:

- `User=` and `Group=`;
- `DynamicUser=` where persistent ownership is unnecessary;
- `NoNewPrivileges=true`;
- `ProtectSystem=strict`;
- `ProtectHome=true`;
- `PrivateTmp=true`;
- `PrivateDevices=true` where compatible;
- `ProtectKernelTunables=true`;
- `ProtectKernelModules=true`;
- `ProtectControlGroups=true`;
- `RestrictSUIDSGID=true`;
- `LockPersonality=true`;
- `MemoryDenyWriteExecute=true` where compatible;
- `RestrictAddressFamilies=`;
- `CapabilityBoundingSet=` and `AmbientCapabilities=` only where required;
- `SystemCallFilter=` after compatibility tests;
- `StateDirectory=`, `RuntimeDirectory=` and `LogsDirectory=`;
- `ReadWritePaths=` limited to explicit state paths;
- `MemoryMax=`, `TasksMax=`, `LimitNOFILE=` and restart-rate limits.

This obtains most isolation and lifecycle benefits without adding container networking ambiguity to
QUIC, TLS/TCP fallback, Nginx stream listeners and WireGuard.

### Optional future container model

After service hardening, signed reproducible images and fleet operation exist, an OCI deployment may
be introduced using Podman Quadlet/systemd. Use separate containers, not one pod-like monolith:

```text
host-level
  Nginx edge
  WireGuard rollback and kernel networking
  Podman/Quadlet and systemd

separate containers
  mobile-control-plane
  mobile-reverse-tunnel-server
  mobile-relay-gate
  mobile-rollback-sing-box     normally stopped
```

Container requirements:

- immutable image digests;
- signed images and verified provenance;
- no privileged containers;
- rootless operation wherever public bind/network behavior permits;
- narrowly scoped capabilities for listeners below 1024 if needed;
- dedicated read-only root filesystems;
- explicit secrets mounted as credentials, not baked into images;
- private per-service writable volumes;
- a durable encrypted control-plane state volume;
- health checks that prove protocol behavior, not just process existence;
- host or dedicated bridge networking chosen from measured latency and source-address behavior;
- exact rollback to a previous image digest;
- resource and file-descriptor limits per container;
- external synthetic validation after every deployment.

Nginx can later be containerized separately if doing so provides a clear release or isolation
benefit, but it should remain a distinct edge container. WireGuard should remain host-level unless a
carefully reviewed privileged-network design is unavoidable.

### Kubernetes decision gate

Do not introduce Kubernetes until most of the following are true:

- multiple relay nodes are continuously active;
- independent horizontal scaling is required;
- automated placement and self-healing across nodes are required;
- rolling deployment across a relay pool is routine;
- a team can operate cluster upgrades, network policy, secret delivery and observability;
- the operational benefit exceeds the cost and attack surface.

Before that threshold, Podman Quadlet or hardened systemd is simpler and more reliable.

## Roadmap

## F0 — Complete the immutable physical baseline

Do not merge this roadmap or change candidate source before issue #64 completes.

Required outcomes:

- real cellular routing and SIM/operator behavior;
- reboot recovery;
- forced QUIC failure and pinned TLS/TCP reserve;
- return to fresh QUIC;
- public SOCKS5, HTTP and CONNECT validation;
- explicit WireGuard rollback and return to the exact native release;
- repeated recovery thresholds;
- 24-hour soak;
- complete physical report set with no secrets.

## F1 — Public-deployment hardening

### Host and service isolation

- create dedicated Unix identities;
- apply systemd sandboxing and resource limits;
- remove blanket `NOPASSWD:ALL`;
- define a minimal deployment sudo policy;
- ensure rollback services are inactive in native mode;
- verify no unexpected listeners after each transition.

### Network perimeter

- enable OS Login;
- use IAP-only SSH administration;
- remove public SSH ingress;
- restrict or close control-plane ingress not required by phones;
- keep WireGuard ingress closed while rollback is inactive where operationally possible;
- add Nginx connection limits, authentication-failure throttling and explicit timeouts;
- add IPv6 policy rather than relying on accidental behavior.

### Supply chain

- verify official sing-box archives with pinned upstream checksums before extraction;
- produce SBOMs for every release;
- sign release manifests and OCI images;
- record provenance for Rust binaries, sing-box and VM packages;
- enforce immutable dependency and image digests in CI.

### Identity and secrets

- separate public/control-plane, reverse-tunnel server and device client trust domains;
- move long-lived secrets to a cloud secret manager;
- automate rotation and revocation;
- prevent secrets from appearing in environment dumps, command lines and logs.

### Device compatibility

- make `aarch64-linux-android` the primary device target;
- retain armv7 only as a compatibility target;
- run CI and physical acceptance on both required architectures.

### Reliability and observability

- replace single DNS resolver dependency with a configurable redundant policy;
- use multiple independent public-IP observers and quorum rules;
- add external synthetic proxy probes;
- collect host, Nginx, process and tunnel metrics;
- add actionable alerts and documented runbooks;
- add encrypted off-host backups and recurring restore drills.

## F2 — Fleet and multi-tenant platform

### Per-device identity

- unique asymmetric device key pair;
- enrolment and ownership proof;
- short-lived or rotatable device certificates;
- per-device mTLS authentication;
- revocation and disabled-device enforcement;
- tunnel session cryptographically bound to registered device identity.

### Fleet-aware ingress gateway

Introduce a Rust ingress gateway between Nginx and the reverse-tunnel relay. It must own:

- SOCKS/HTTP ingress authentication or normalized authenticated sessions;
- user and tenant resolution;
- device or device-pool selection;
- country/operator/profile constraints;
- quota and concurrent-session enforcement;
- readiness-aware routing;
- connection admission control;
- draining during rotation or deployment;
- audit context and request correlation;
- fail-closed behavior when no unambiguous eligible device is available.

Target path:

```text
client
  -> Nginx edge
  -> Rust proxy-ingress-gateway
       authentication / tenant / quota / device selection
  -> reverse-tunnel relay
  -> selected phone sing-box
  -> cellular Internet
```

### Operator security

- OIDC login;
- role-based access control;
- scoped API tokens or service identities;
- immutable audit trail for rotation, rollback, revoke, credential and deployment actions;
- dual-control options for destructive operations.

### Infrastructure as code

- Terraform/OpenTofu modules for VPC, firewall, IAP, service accounts, static IPs, VM images,
  backups and monitoring;
- separate development, staging and production environments;
- policy checks and drift detection;
- immutable machine image or reproducible bootstrap.

### Telemetry

- Prometheus-compatible collection or managed equivalent;
- Alertmanager and Grafana or managed equivalents;
- SLOs for device availability, successful proxy sessions, reconnect time and rotation success;
- bounded-cardinality labels;
- external probes from more than one network/location;
- trace/correlation support where it provides diagnostic value.

## F3 — High availability

Move beyond SQLite only when multiple control-plane instances or richer durable product data are
required.

- introduce PostgreSQL with tested migrations and point-in-time recovery;
- deploy control plane across at least two failure domains;
- define leader/lease semantics for commands and rotations;
- ensure idempotent device reconnect and command acknowledgement;
- add relay directory and device-to-relay assignment;
- support controlled relay draining and device migration;
- remove single-VM assumptions from public ingress;
- test zonal loss and database restore.

SQLite remains the correct choice until this phase because it minimizes operational complexity for
one durable writer.

## F4 — Multi-region and scale

- regional relay pools;
- latency- and policy-aware device placement;
- reserve relay selection and reconnect;
- globally distributed public ingress;
- regional failure and split-brain drills;
- autoscaling based on connections, streams, bandwidth and reconnect pressure;
- large-scale reconnect-storm protection;
- load, soak and chaos tests;
- capacity models for memory, file descriptors, bandwidth and control-plane writes;
- canary and progressive delivery with automatic rollback;
- data residency and tenant policy controls.

## Product-level capabilities required for an ultimate platform

- tenant and organization model;
- users, roles and API credentials;
- device inventory and lifecycle;
- device pools and routing policy;
- subscription, quota and billing integration;
- usage accounting without high-cardinality metric abuse;
- abuse detection and response;
- credential rotation and customer-visible revoke;
- audit export;
- maintenance windows and fleet rollout policy;
- customer-facing availability and usage APIs;
- support tooling with controlled impersonation and full audit.

## Acceptance gates for future work

Every phase must preserve the existing principles:

- fail closed;
- immutable candidate SHA;
- typed internal integrity contracts;
- no secrets in evidence;
- bounded protocol frames, queues and labels;
- exact release identity and rollback;
- process tests plus real external traffic tests;
- independent failure containment;
- documented recovery drills.

A future architecture change is complete only when it has:

1. a written threat model and ADR;
2. automated architecture/policy checks;
3. unit, process, migration and rollback tests;
4. supply-chain evidence;
5. load and failure testing appropriate to the phase;
6. immutable release evidence;
7. an executable operational runbook;
8. a successful staged deployment and rollback.

## Recommended implementation order after issue #64

1. systemd least privilege and firewall/IAP/OS Login;
2. dormant rollback services in native mode;
3. sing-box checksum/provenance and release signing;
4. split TLS identities and cloud secret management;
5. ARM64 build and physical acceptance;
6. external synthetic probes and monitoring/alerts;
7. Terraform/OpenTofu infrastructure definition;
8. per-device identity and enrolment;
9. fleet-aware Rust ingress gateway;
10. tenant/RBAC/quota/audit capabilities;
11. relay directory and multi-node operation;
12. PostgreSQL and HA only when multiple writers/replicas are required;
13. optional per-service Podman Quadlet deployment;
14. multi-region scale and chaos validation.
