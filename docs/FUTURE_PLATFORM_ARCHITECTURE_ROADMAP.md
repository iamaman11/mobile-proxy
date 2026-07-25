# Future Platform Architecture Roadmap

> **STATUS: FUTURE / POST-BASELINE RECOMMENDATIONS**
>
> This document is intentionally stored in `main` as the long-term architecture source of truth.
> Items below are **not part of the currently frozen physical-phone runtime candidate** unless they
> are explicitly promoted into a new implementation issue, implemented, tested and accepted on a
> new immutable release SHA.

## Release and physical-acceptance policy

The runtime candidate prepared for the first real-phone acceptance remains:

```text
778c9a6260f58ede0f5a337c5107bc96b022373c
```

Documentation-only commits may be added to `main` when they are clearly marked as future work and do
not alter runtime source, build inputs, deployment templates, dependencies, manifests or packaged
artifacts. The physical run must still install and verify the exact already-approved candidate and
its immutable evidence.

Any change to runtime code, dependency resolution, build scripts, deployment inputs, manifests,
configuration templates or packaged binaries creates a new candidate and requires the complete
software evidence cycle before physical acceptance.

The current candidate is a strong baseline for one rooted phone and one relay VM. This roadmap covers
future public hardening, fleet management, multi-tenancy, high availability and multi-region scale.

## Executive decisions

1. Keep both Nginx and sing-box. They perform different roles and are not accidental duplication.
2. Keep Rust, Tokio, Axum, Quinn/rustls, systemd, SQLite and the first-party reverse tunnel for the
   current single-node baseline.
3. Do not put the entire VM application into one monolithic container.
4. Harden the current host-native systemd services before introducing OCI containers.
5. If containers are later justified, use one independently versioned container per service.
6. Keep Nginx and WireGuard host-level initially because they own edge listeners and kernel
   networking.
7. Do not add Kubernetes, a service mesh, Kafka, NATS, Redis or PostgreSQL merely for appearance.
8. Promote roadmap items into implementation only through a new issue, immutable candidate and full
   acceptance cycle.

## Current architecture

```text
rooted Android phone
  Magisk/root boot service
    runtime-supervisor
      host-daemon
      sing-box on loopback
        SOCKS5 / HTTP / CONNECT
        direct cellular egress
      first-party reverse tunnel client
        pinned QUIC primary
        pinned TLS/TCP reserve

relay VM
  Nginx
    control-plane TLS termination
    public TCP proxy listeners
    atomic native/WireGuard backend switch
    TLS/TCP tunnel reserve on 443
  reverse-tunnel-server
  control-plane
  relay-gate
  SQLite durable state
  dormant WireGuard rollback
  dormant VM sing-box rollback adapter
```

### Nginx responsibility

Keep Nginx as the static public L4/TLS edge. It should own:

- public TCP listeners;
- control-plane TLS termination;
- the TLS/TCP reserve listener;
- stable public addresses while internal backends change;
- bounded connection and timeout policy;
- atomic native reverse-tunnel versus WireGuard switching.

Nginx must not become the fleet scheduler, quota engine or tenant authorization service.

### sing-box responsibility

Keep sing-box as the proxy protocol engine. On the phone it should own:

- SOCKS5;
- HTTP proxy and CONNECT;
- local proxy authentication;
- protocol compatibility;
- direct cellular egress.

The Rust tunnel should transport authenticated byte streams rather than duplicate every proxy
protocol. VM sing-box is only a WireGuard rollback adapter and should be stopped during native mode.

## Technology disposition

### Keep

- Rust 2024 workspace boundaries;
- Tokio and Axum;
- Quinn and rustls;
- Nginx at the edge;
- sing-box for proxy protocols;
- hardened systemd for the first production deployment;
- SQLite WAL while there is one active control-plane writer;
- WireGuard only as explicit dormant rollback;
- typed BLAKE3 internal integrity contracts;
- exact-byte deployment verification;
- Prometheus-compatible bounded metrics;
- immutable release evidence and destructive acceptance testing.

### Add after the physical baseline

- dedicated non-root service users and systemd sandboxing;
- OS Login and IAP-only administration;
- Terraform or OpenTofu;
- cloud secret management and automated rotation;
- verified upstream checksums, SBOM, signatures and provenance;
- ARM64 Android build and acceptance;
- external synthetic SOCKS5/HTTP/CONNECT probes;
- metric collection, alerts and dashboards;
- per-device asymmetric identity and mTLS enrolment;
- OIDC, operator RBAC and immutable audit records;
- a Rust fleet-aware proxy ingress gateway;
- tenant, user, quota and admission-control models;
- relay directory, placement and controlled draining;
- PostgreSQL only after horizontal replicas or richer durable product data require it;
- per-service Podman Quadlet deployment only after images are reproducible and signed.

### Do not add without measured need

- one all-in-one application container;
- Kubernetes for one VM or a small static relay set;
- Istio or another service mesh;
- Kafka or NATS for the current command volume;
- Redis as a default dependency;
- Envoy merely to replace a working Nginx edge;
- another custom SOCKS/HTTP implementation on the phone;
- PostgreSQL while the control plane remains a single writer;
- many microservices without independent scaling or security boundaries.

## VM deployment model

### Current state

The relay VM is currently a host-native multi-process deployment, not a container:

- Nginx, WireGuard and operating-system packages are installed on Linux;
- Rust and sing-box binaries are copied into versioned application directories;
- components are started as separate systemd services;
- SQLite, certificates, environment files and network configuration live in host paths.

### One container containing everything

Do not do this. One container containing Nginx, control-plane, reverse-tunnel-server, relay-gate,
sing-box, WireGuard tooling and SQLite would:

- couple every restart and upgrade;
- mix high networking privileges with unrelated services;
- enlarge the compromise boundary;
- make resource limits and logs coarser;
- complicate readiness, rollback and canary deployment;
- require an internal supervisor and duplicate systemd;
- make independent versioning harder.

The invariant is one responsibility and one independently restartable security boundary per service,
whether implemented as a systemd unit or a container.

### Recommended near-term VM model

```text
host Linux
  nginx                     host edge
  wireguard                 host kernel networking; normally inactive
  control-plane             dedicated unprivileged user
  reverse-tunnel-server     dedicated unprivileged user
  relay-gate                dedicated unprivileged user
  rollback sing-box         dedicated unprivileged user; normally inactive
  SQLite                    private control-plane state directory
```

Apply the strictest compatible systemd controls:

- `User=` and `Group=`;
- `DynamicUser=` where appropriate;
- `NoNewPrivileges=true`;
- `ProtectSystem=strict`;
- `ProtectHome=true`;
- `PrivateTmp=true`;
- kernel, control-group and device protections;
- `RestrictAddressFamilies=`;
- minimal `CapabilityBoundingSet=`;
- `SystemCallFilter=` after compatibility tests;
- explicit state/runtime/log directories;
- narrow writable paths;
- memory, task, file-descriptor and restart-rate limits.

### Optional future container model

After host hardening and reproducible signed images exist, Podman Quadlet/systemd may run separate
containers:

```text
host-level
  Nginx edge
  WireGuard rollback/kernel networking
  Podman/Quadlet and systemd

separate containers
  mobile-control-plane
  mobile-reverse-tunnel-server
  mobile-relay-gate
  mobile-rollback-sing-box     normally stopped
```

Requirements:

- immutable image digests;
- verified signatures and provenance;
- no privileged all-in-one container;
- rootless operation where compatible;
- read-only root filesystems;
- narrowly scoped capabilities;
- secrets mounted at runtime, never baked into images;
- private per-service writable volumes;
- encrypted durable control-plane storage;
- protocol-level health checks;
- exact rollback to a previous digest;
- per-container resource limits;
- external synthetic validation after deployment.

Keep WireGuard host-level. Nginx may later become a separate edge container only when there is a
measured operational or isolation benefit.

## F0 — Physical baseline: current gate

This is the only current acceptance phase. Use the exact frozen runtime candidate.

Required outcomes:

- real cellular routing and SIM/operator behavior;
- installation on the rooted phone;
- boot and reboot recovery;
- authenticated public mixed, SOCKS5, HTTP and CONNECT paths;
- forced QUIC failure and pinned TLS/TCP reserve;
- automatic return to fresh QUIC;
- cellular identity rotation and required public-IP change;
- explicit WireGuard rollback;
- return to the exact already-installed native release;
- repeated recovery thresholds;
- 24-hour soak;
- complete physical evidence without secrets.

### Non-blocking pre-public transport hardening discovered after the software baseline

These items do not prevent the first physical functional run, but must be implemented before claiming
a hardened public service candidate:

- validate `TunnelHello.protocol_version` against an explicit supported protocol constant before
  authenticating or registering a session;
- reduce and centralize the JSON control-frame size limit from the current 1 MiB ceiling to a small
  protocol-appropriate bound, with tests for oversized unauthenticated frames;
- add explicit timeout/budget tests for incomplete first frames and slow-reader behavior;
- version the frame contract and document compatibility/upgrade rules.

Implementing these changes creates a new runtime candidate and therefore belongs after the first
physical baseline unless the baseline is deliberately restarted.

## F1 — Public-deployment hardening

### Host and services

- create dedicated Unix identities;
- apply systemd sandboxing and resource limits;
- remove blanket `NOPASSWD:ALL`;
- define minimal deployment sudo rules;
- keep rollback services inactive in native mode;
- verify no unexpected listeners after transitions.

### Network perimeter

- enable OS Login;
- use IAP-only SSH;
- remove public SSH ingress;
- restrict control-plane ingress;
- close WireGuard ingress while rollback is inactive where practical;
- add Nginx limits, throttling and explicit timeouts;
- define an explicit IPv6 policy.

### Supply chain

- verify sing-box archives with pinned upstream checksums before extraction;
- produce SBOMs;
- sign release manifests and images;
- record build provenance;
- enforce immutable dependency and image digests.

### Identity and secrets

- separate public/control-plane, tunnel-server and device-client trust domains;
- move long-lived secrets to a cloud secret manager;
- automate rotation and revocation;
- prevent secrets from appearing in arguments, dumps and logs.

### Device compatibility

- make `aarch64-linux-android` the primary target;
- retain armv7 only when required;
- run CI and physical acceptance on every supported architecture.

### Reliability and observability

- redundant configurable DNS policy;
- multiple public-IP observers with quorum;
- external synthetic proxy probes;
- host, Nginx, process and tunnel metrics;
- actionable alerts and runbooks;
- encrypted off-host backups and restore drills;
- load tests and reconnect-storm tests.

## F2 — Fleet and multi-tenant platform

- unique asymmetric identity per phone;
- enrolment, ownership proof, certificate rotation and revocation;
- mTLS-bound tunnel sessions;
- Rust ingress gateway between Nginx and the reverse-tunnel relay;
- tenant/user resolution;
- device and pool selection;
- quota and concurrent-session enforcement;
- readiness-aware routing and admission control;
- controlled draining during rotation and deployment;
- OIDC and operator RBAC;
- immutable audit records;
- usage accounting and abuse controls;
- relay directory and device placement.

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

## F3 — High availability

Promote SQLite to PostgreSQL only when multiple active control-plane replicas or richer durable data
require it. Then add:

- multi-zone control-plane replicas;
- point-in-time recovery;
- leader/lease semantics for commands and rotations;
- relay migration and controlled reconnect;
- zonal-loss drills;
- tested backup and restore objectives.

## F4 — Multi-region and large scale

- regional relay pools;
- global ingress and policy-aware placement;
- autoscaling and reconnect-storm protection;
- progressive delivery and automatic rollback;
- load, soak and chaos testing;
- data-residency controls;
- capacity and cost models.

### Kubernetes decision gate

Do not introduce Kubernetes until most of these are true:

- multiple relay nodes are continuously active;
- independent horizontal scaling is required;
- automatic placement and self-healing are required;
- rolling deployment across a relay pool is routine;
- the team can operate upgrades, network policy, secrets and observability;
- the operational benefit exceeds the cost and attack surface.

Before that threshold, hardened systemd or Podman Quadlet is simpler and more reliable.

## Promotion rule

A future item becomes current work only when:

1. a dedicated issue defines scope and acceptance criteria;
2. the change is implemented on a new branch;
3. all software quality and release-candidate workflows pass on one immutable SHA;
4. evidence names that SHA and exact artifacts;
5. physical or infrastructure acceptance appropriate to the change is completed;
6. documentation is updated from `FUTURE` to the implemented status.
