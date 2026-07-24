# ADR-001: Bounded Contexts and Clean Dependency Rules

- Status: Accepted for implementation
- Date: 2026-07-23
- Scope: `mobile-proxy` architecture baseline

## Context

The current repository is already split into Rust crates and executable services, but several boundaries remain transitional:

- control-plane HTTP handlers contain application and persistence orchestration;
- canonical state is persisted as JSON from in-memory maps and queues;
- runtime-domain uses WireGuard-specific state names;
- shared endpoint models do not fully represent authenticated runtime endpoints;
- Android owns service lifecycle but still delegates tunnel operation to the WireGuard backend;
- `site-analize-by-pl` is an important consumer, but cannot define the platform's canonical domain model.

A big-bang rewrite would create unacceptable regression risk for existing proxy users and protocols. The architecture therefore evolves through independently testable production slices.

## Decision

### 1. Dependency direction

The permitted dependency direction is:

```text
foundation <- domain <- application <- ports <- adapters <- composition roots
```

A layer may depend only on layers to its left.

### 2. Domain restrictions

Domain crates may contain:

- validated value objects and typed IDs;
- aggregates and entities;
- deterministic state machines;
- invariants and policies;
- domain events;
- typed domain errors.

Domain crates must not depend on:

- Axum or HTTP concepts;
- Tonic or generated protobuf types;
- SQLx, SQLite or migration code;
- Reqwest or external probes;
- Android SDK APIs;
- filesystem APIs;
- process execution;
- deployment manifests;
- environment variables.

### 3. Bounded contexts

The following list describes the long-horizon target decomposition, not the active Production Baseline backlog. During the current baseline, only existing Foundation, Device Registry/command application responsibilities, Tunnel Session and Proxy Access responsibilities may be advanced. Network Lease, Network Identity, Rotation, Credential Broker and Audit Ledger remain inactive unless the Production Baseline Plan is changed by a separate product decision.

The long-horizon target contexts are:

- Foundation;
- Device Registry;
- Network Lease;
- Network Identity;
- Rotation;
- Tunnel Session;
- Proxy Access;
- Credential Broker;
- Audit Ledger.

Each current mutable behavior and state has a single authoritative owner. Other responsibilities interact through typed application ports. Architectural roles do not require a dedicated crate per layer; ports may live in the application crate while dependencies remain inward and ownership remains explicit.

### 4. Multi-consumer platform

Canonical ownership is represented by:

```text
consumer_id
application_id
owner_reference(namespace, resource_type, resource_id)
```

No canonical domain type may require a `site-analize-by-pl`-specific concept. Application-specific integrations are adapters or certification fixtures.

### 5. Protocol and transport separation

Proxy protocol and tunnel transport are separate dimensions.

Proxy protocols:

```text
MIXED
SOCKS5
HTTP
```

Tunnel transports:

```text
QUIC
TLS_TCP
WIREGUARD_COMPATIBILITY
```

The consumer may select an allowed proxy protocol. The platform normally owns internal tunnel selection.

### 6. Backward compatibility

The following are protected compatibility commitments until explicitly deprecated:

- mixed proxy on `1080`;
- SOCKS5 proxy on `1081`;
- HTTP/CONNECT proxy on `3128`;
- QUIC-first reverse tunnel;
- TLS/TCP reserve tunnel;
- controlled WireGuard compatibility and rollback;
- existing operator/admin surfaces.

No implementation PR may change this inventory without updating the machine-readable compatibility contract and migration documentation.

### 7. Durable state

SQLite with WAL is the initial canonical durable store for the closed Production Baseline inventory: device records, authoritative current health/runtime projection fields, pending commands, durable command results, idempotency claims and replay evidence, plus minimal schema metadata. Lease, identity, rotation, credential, audit and outbox tables are future-only and must not be created without a separate product decision.

JSON remains temporarily as migration input and diagnostic export, not as the final canonical transaction store.

### 8. Composition roots

Executable services own dependency construction. Transport handlers must be thin and limited to:

1. authenticate;
2. authorize;
3. decode and validate transport input;
4. call one application use case;
5. map a typed result to the transport response.

Handlers must not contain business state transitions or SQL.

### 9. Incremental extraction

Existing crates remain operational. Responsibilities move only through small PRs with tests and compatibility evidence. No phase may require all later phases to land simultaneously.

## Consequences

### Positive

- new consumers can integrate without leaking application-specific concepts into core;
- proxy protocols and tunnel transports can evolve independently;
- domain behavior is testable without networking or storage;
- persistence can migrate without rewriting business rules;
- compatibility regressions become machine-detectable;
- Android and server runtimes can share domain concepts while keeping platform adapters separate.

### Costs

- temporary adapters and translation layers will coexist with legacy models;
- some data will be dual-read or migrated during transition;
- more crates and explicit interfaces increase initial ceremony;
- composition and contract tests become mandatory maintenance work.

## Enforcement

CI will progressively add checks that reject:

- infrastructure dependencies in domain crates;
- raw string status and error taxonomies;
- public proxy inventory drift;
- application-specific canonical fields;
- SQL or business transitions in HTTP handlers;
- generated protobuf types in domain crates;
- unbounded queues and session maps;
- secret-bearing Debug output.

## Review trigger

This ADR may be superseded only by another ADR that preserves or explicitly migrates all compatibility commitments and demonstrates equivalent or stronger isolation, reliability and upgrade safety.
