# Ultimate Implementation Plan

Status: normative roadmap  
Target: production-grade 10/10  
Repository: `iamaman11/mobile-proxy`

## 1. Mission

`mobile-proxy` is an autonomous multi-consumer platform for managed mobile network egress. It must not be modeled as an internal component of `site-analize-by-pl`; that project is one consumer among many.

The platform must preserve the existing compatibility surface throughout the migration:

- mixed proxy on public port `1080`;
- SOCKS5 proxy on public port `1081`;
- HTTP proxy, including CONNECT, on public port `3128`;
- QUIC-first reverse tunnel;
- certificate-pinned TLS/TCP reserve tunnel;
- current WireGuard paths as controlled compatibility and rollback paths until physical acceptance proves the first-party replacement;
- operator CLI and operator/admin APIs.

The target product is not merely a proxy address. It is a versioned, authenticated, observable, recoverable and optionally exclusive mobile network identity.

## 2. Non-negotiable architecture rules

### 2.1 Dependency direction

Dependencies point inward:

```text
foundation <- domain <- application <- ports <- adapters <- composition roots
```

Domain crates must not depend on Axum, Tonic, SQLx, SQLite, Reqwest, Android SDK APIs, filesystems, process execution or generated protobuf types.

### 2.2 Single owner per aggregate

| Aggregate | Owner |
| --- | --- |
| Device | Device Registry |
| NetworkLease | Lease Service |
| RotationJob | Rotation Coordinator |
| NetworkIdentity | Identity Service |
| TunnelSession | Tunnel Session Manager |
| ProxyCredential | Credential Broker |
| AuditChain | Audit Ledger |

Other modules interact through typed application ports and never mutate another module's state directly.

### 2.3 Canonical state

Canonical mutable state must not live only in memory, JSON, YAML, Android SharedPreferences, a process table or an in-memory queue. SQLite with WAL is the initial durable store, with explicit migrations and transaction boundaries.

### 2.4 Typed contracts

Statuses, identifiers, error codes, proxy protocols, tunnel transports, rotation strategies, principals, permissions and release reasons are validated newtypes or enums. Raw strings are accepted only at transport boundaries and converted immediately.

### 2.5 Compatibility before replacement

No migration may silently remove an existing proxy protocol, public port, operator endpoint or tunnel fallback. Replacement requires an explicit compatibility contract, parity tests, a deprecation window and physical acceptance evidence.

## 3. Target bounded contexts

The workspace will evolve incrementally toward the following modules without a big-bang rewrite:

```text
crates/
  mp-foundation/
  mp-contracts/
  mp-device-domain/
  mp-lease-domain/
  mp-network-identity-domain/
  mp-rotation-domain/
  mp-tunnel-domain/
  mp-proxy-access-domain/
  mp-application/
  mp-persistence-ports/
  mp-security-ports/
  mp-runtime-ports/
  mp-sqlite-adapter/
  mp-credential-adapter/
  mp-reverse-tunnel/
  mp-test-support/
```

Existing crates remain operational while responsibilities are extracted one production slice at a time.

### 3.1 Foundation

Typed IDs, clocks, deadlines, protocol versions, request IDs, correlation IDs and idempotency keys. No business behavior.

### 3.2 Device domain

Registration, capabilities, operator profile, readiness evidence, health class, quarantine, maintenance and device generation.

### 3.3 Lease domain

Exclusive allocation, lease state machine, epoch, fencing, TTL, renew, release, revoke, expiry, ownership and idempotency semantics.

### 3.4 Network identity domain

Device, relay, external and consumer observations; consensus, staleness, mismatch and unexpected egress drift.

### 3.5 Rotation domain

Durable jobs, attempts, strategies, previous identity, `require_ip_change`, retry policy and typed outcomes.

### 3.6 Tunnel domain

Transport-neutral lifecycle:

```text
STOPPED
STARTING
CONNECTING_PRIMARY
CONNECTED_PRIMARY
CONNECTING_RESERVE
CONNECTED_RESERVE
DEGRADED
RECOVERING
STOPPING
FAILED
```

QUIC, TLS/TCP and WireGuard are adapter capabilities, not domain states.

### 3.7 Proxy access domain

The canonical protocols are:

```text
MIXED
SOCKS5
HTTP
```

HTTP includes CONNECT. A lease may expose multiple endpoints simultaneously.

## 4. Multi-consumer ownership

Every external operation is attributed to a principal:

```text
consumer_id
application_id
actor_id
granted_scopes
authentication_context
```

External ownership is generic:

```text
OwnerReference {
  namespace
  resource_type
  resource_id
}
```

Examples include a site-analysis run, CRM import job, monitoring task or another future workload. Canonical contracts must not contain application-specific fields such as a mandatory `owner_run_id`.

Idempotency is scoped by:

```text
consumer_id + application_id + operation + idempotency_key
```

Consumer policy is data-driven and may constrain active leases, TTL, operators, regions, protocols, rotation rate and device pools. There must be no application-name conditionals in domain code.

## 5. Proxy descriptor model

A managed lease returns a descriptor containing all allowed endpoints:

```text
ProxyDescriptor {
  descriptor_id
  lease_id
  lease_epoch
  generation
  endpoints[]
  expected_network_identity
  valid_from
  expires_at
  descriptor_fingerprint
}
```

Each endpoint contains:

```text
ProxyEndpoint {
  endpoint_id
  protocol
  host
  port
  authentication_mode
  username_handle
  password_handle
  expires_at
  endpoint_fingerprint
}
```

The first managed version should normally expose mixed `1080`, SOCKS5 `1081` and HTTP `3128` for the same lease. Credentials are short-lived, lease-bound, revocable and redacted. Full proxy URLs never appear in logs or safe errors.

Legacy shared endpoints remain an isolated compatibility module until all known users are migrated through an explicit deprecation process.

## 6. Lease model and invariants

The lease aggregate contains:

```text
lease_id
consumer_id
application_id
owner_reference
device_id
lease_epoch
fencing_token_digest
status
requested_capabilities
granted_capabilities
acquired_at
activated_at
expires_at
released_at
rotation_generation
descriptor_generation
version
```

Required invariants:

1. At most one active exclusive lease per physical device.
2. Device lease epoch increases monotonically.
3. Every lease receives a cryptographically random 256-bit fencing token.
4. Only a digest of the fencing token is persisted.
5. Stale epoch or token returns `LEASE_FENCED` and is never retryable.
6. Mutations verify consumer, application, lease, epoch, token, status and deadline.
7. Duplicate requests with an identical fingerprint return the original result.
8. Reuse of an idempotency key with different parameters returns `IDEMPOTENCY_CONFLICT`.
9. Release, revoke and expiry permanently invalidate previous credentials and control authority.
10. Expired devices return to the available pool only after cleanup and readiness reconciliation.

Database-level exclusivity must complement application checks through a partial unique index over active lease statuses.

## 7. Durable persistence

Initial storage: SQLite with WAL, foreign keys, busy timeout, single-writer discipline, short transactions, online backup and integrity checks.

Core tables:

```text
devices
device_capabilities
device_health_observations
device_epochs
network_leases
lease_events
lease_idempotency
rotation_jobs
rotation_attempts
network_identities
network_identity_observations
device_commands
device_command_attempts
device_command_acknowledgements
proxy_descriptors
proxy_credential_metadata
consumer_principals
consumer_policies
audit_events
outbox_events
quarantine_records
schema_migrations
```

Business state, idempotency result, domain events, audit and outbox messages are committed atomically.

The existing JSON state becomes a read-only migration source and diagnostic export. Migration sequence: import, validate parity, switch writes to SQLite, retain export, then retire JSON persistence after the compatibility window.

## 8. Consumer API

Protocol Buffers and gRPC are canonical. HTTP/JSON is a gateway adapter. Generated protobuf models do not enter domain crates.

Logical operations:

- `DescribeCapabilities`;
- `ListAvailableDevices`;
- `AcquireNetworkLease`;
- `GetNetworkLease`;
- `RenewNetworkLease`;
- `RotateNetworkLease`;
- `VerifyNetworkLease`;
- `ReleaseNetworkLease`.

Existing raw device and command routes remain operator/admin-only. Consumer applications never call raw device commands, ADB, airplane mode, relay configuration or provisioning APIs.

Every request carries protocol version, request ID, correlation ID and deadline. Mutations also carry idempotency data. Lease-bound mutations carry lease ID, epoch and fencing token.

## 9. Reverse tunnel architecture

Proxy protocol and tunnel transport are separate concepts:

```text
proxy protocol: MIXED | SOCKS5 | HTTP
tunnel transport: QUIC | TLS_TCP | WIREGUARD_COMPATIBILITY
```

The default policy is QUIC primary with certificate-pinned TLS/TCP on port 443 as reserve. Reserve mode must preserve device binding, lease binding, credentials, protocol support and network identity guarantees.

Required hardening of the current implementation:

1. Remove pending TCP stream entries on success, cancellation and timeout.
2. Bound global and per-device pending stream counts.
3. Attach expiry to pending stream registrations.
4. Never select an arbitrary first device when a lease expects a specific device.
5. Bind streams to device ID, tunnel session ID, runtime generation and lease generation.
6. Replace a global tunnel token with per-device credentials.
7. Track primary/reserve transport state and failover reason.
8. Require heartbeat freshness, not only a stored `connected` flag.
9. Audit every transport failover and recovery.
10. Quarantine repeated authentication, identity and unstable-tunnel failures.

Mandatory reserve-tunnel acceptance:

```text
active QUIC
-> verify mixed/SOCKS5/HTTP/CONNECT
-> block UDP 18090
-> establish TLS/TCP through 443
-> verify authenticated heartbeat
-> verify all proxy protocols and mobile IP
-> unblock QUIC
-> prove new connections return to QUIC
```

## 10. Network identity and rotation

Identity observations are recorded independently at device, relay, external probe and consumer points. Each observation includes time, IP, operator, region, network type, DNS fingerprint, tunnel transport and evidence digest.

A lease becomes active only after validated cellular connectivity, authenticated tunnel, healthy proxy listener, successful public probe and fresh evidence.

Unexpected IP drift outside a rotation moves an active lease to `DEGRADED`, records `EGRESS_CHANGED` and requires verification before normal operation resumes.

Rotation is a durable, lease-bound, fenced workflow:

```text
validate fencing
-> persist job
-> issue idempotent device command
-> acknowledge execution
-> wait for readiness
-> verify public proxy
-> verify identity
-> increment generation
-> regenerate descriptor only when necessary
-> persist audit evidence
```

Crash recovery resumes from persisted evidence without duplicate commands or duplicate rotation results.

## 11. Android architecture

Android code is layered into UI, application, domain, runtime, transport, platform and storage packages. UI never calls a backend directly.

Tunnel config and credentials must move from plain SharedPreferences strings to a versioned encrypted envelope protected by Android Keystore. Revocation and reprovisioning wipe obsolete material.

Migration sequence:

```text
stock WireGuard bridge
-> first-party VpnService using WireGuard backend
-> embedded first-party reverse tunnel
-> physical acceptance
-> first-party runtime becomes default
-> WireGuard retained temporarily as controlled rollback adapter
```

## 12. Security

Separate principals:

- platform admin;
- operator;
- consumer application;
- device;
- relay.

A token is never shared across principal types. Consumer scopes cover only own lease operations. Device provisioning and raw commands require separate operator/admin permissions.

Tunnel authentication evolves from per-device tokens to per-device certificates or signed device proof with revocation. Proxy credentials are unique per lease, short-lived, revocable, absent from metrics and redacted from logs and Debug output.

Audit events contain sequence, actor, consumer, application, lease, device, correlation ID, result, reason, previous hash and event hash. Sequence and previous hash are assigned transactionally.

## 13. Observability and operations

Structured logs include service, release ID, Git SHA, request/correlation IDs, consumer, lease, device, rotation, runtime generation, transport and result code. Secrets are prohibited.

Metrics cover devices, leases, consumers, protocols, rotations, tunnel failovers, fallback duration, queue depth, pending streams, identity mismatch, idempotency conflicts and audit failures. High-cardinality IDs are not permanent metric labels.

Health endpoints are split into liveness, readiness, dependencies, fleet, device and lease health. Control-plane liveness must not depend on a phone; readiness depends on durable storage and critical workers, not on free device availability.

## 14. Upgrade model

Protobuf field numbers are never reused. Removed fields are reserved. `buf lint` and `buf breaking` are mandatory. Contract snapshots have SHA-256 parity checks.

Database changes use expand-migrate-contract over multiple releases. Rollback must remain possible after an expansion migration.

Every process publishes release ID, Git SHA, supported protocol range, schema version and capabilities. Rollout follows package, checksum, signature, staging, canary, fleet rollout and post-deploy verification.

## 15. Delivery phases

### Phase 0 - architecture and compatibility baseline

1. ADRs for bounded contexts, dependency rules, multi-consumer ownership, protocol compatibility, tunnel separation, persistence, credentials and upgrade policy.
2. Machine-readable compatibility inventory.
3. Automated parity tests for proxy protocols and public ports.
4. Forced reserve-tunnel integration proof.

### Phase 1 - clean modular boundaries

1. Typed foundation primitives.
2. Transport-neutral runtime domain.
3. Application ports.
4. Thin control-plane transport handlers.
5. CI dependency boundary checks.

### Phase 2 - durable state

1. SQLite migrations and transaction abstraction.
2. Durable device and command repositories.
3. Atomic event, audit and outbox persistence.
4. JSON state migration and parity verification.

### Phase 3 - multi-consumer lease domain

1. Lease aggregate, state machine, fencing and property tests.
2. Deterministic allocation and database exclusivity.
3. Acquire/Get production slice.
4. Renew/Release/Expiry production slice.

### Phase 4 - proxy access and credentials

1. Multi-protocol descriptor.
2. Lease-bound credential broker.
3. Revocation and redaction.
4. Isolated legacy compatibility module.

### Phase 5 - network identity

1. Observation model.
2. Verify lease.
3. Consensus and mismatch.
4. Unexpected drift handling.

### Phase 6 - rotation

1. Durable rotation jobs.
2. Attempt and acknowledgement recovery.
3. Descriptor generation management.
4. Physical airplane and reconnect acceptance.

### Phase 7 - tunnel hardening

1. Per-device tunnel identity.
2. Explicit hybrid transport state machine.
3. Lease/session binding.
4. QUIC/TLS fault injection matrix.

### Phase 8 - Android ownership

1. Android clean layering.
2. Keystore-backed config.
3. Embedded first-party runtime.
4. Production default migration with rollback.

### Phase 9 - operations and release

1. Metrics, traces and health.
2. Quarantine and maintenance.
3. Backup, restore and disaster recovery drills.
4. SBOM, signatures and provenance.
5. Neutral consumer certification fixture.
6. Physical final acceptance on one immutable SHA.

## 16. Pull request sequence

The intended sequence is deliberately incremental:

1. Architecture ADRs and compatibility inventory.
2. Compatibility parity test.
3. Reserve tunnel bounds and forced fallback test.
4. Foundation types.
5. Transport-neutral runtime domain.
6. Application ports and thin routes.
7. SQLite persistence.
8. Durable command queue.
9. Audit and outbox.
10. JSON migration.
11. Lease state machine.
12. Allocation policy.
13. Acquire/Get.
14. Renew/Release/Expiry.
15. Multi-protocol descriptors.
16. Lease-bound credentials.
17. Legacy compatibility isolation.
18. Identity observations.
19. Verify lease.
20. Egress drift handling.
21. Rotation jobs.
22. Rotation recovery.
23. Descriptor regeneration.
24. Per-device tunnel identity.
25. Hybrid state machine.
26. Session/lease binding.
27. Tunnel fault injection.
28. Android layering.
29. Secure Android config.
30. First-party tunnel runtime.
31. Production migration.
32. Observability.
33. Quarantine and maintenance.
34. Backup/disaster recovery.
35. Signed supply chain.
36. Neutral downstream fixture.
37. Physical final acceptance.

## 17. Required tests and gates

Domain tests cover every transition, invalid transition, fencing, TTL, allocation, protocol selection, identity consensus and rotation policy.

Property tests prove:

- at most one active exclusive lease per device;
- epoch monotonicity;
- fenced clients cannot mutate state;
- duplicate requests do not duplicate operations;
- release is irreversible;
- expired credentials never regain authority;
- rotation generation is monotonic.

The protocol matrix requires mixed, SOCKS5, HTTP and HTTP CONNECT over QUIC, TLS/TCP reserve and WireGuard compatibility until deprecation.

Permanent CI gates:

```text
cargo fmt --all -- --check
cargo clippy --workspace --all-targets --all-features -- -D warnings
cargo nextest run --workspace --all-features
cargo test --doc --workspace
cargo audit
cargo deny check
cargo machete
cargo semver-checks
buf lint
buf breaking
gitleaks detect
migration validation
architecture dependency validation
contract snapshot parity
Android unit tests
Android lint
```

Final acceptance additionally requires real binaries, a physical phone, reboot recovery, rotation, credential revocation, reserve tunnel failover, return to QUIC, all proxy protocols and rollback.

## 18. Definition of Done for every production slice

A slice is complete only when it has:

- domain invariant;
- application use case;
- typed port;
- production adapter;
- composition registration;
- authentication and authorization;
- idempotency classification;
- audit;
- typed errors;
- metrics;
- unit, integration and process tests;
- documentation;
- compatibility verification.

Domain code without production composition is not complete.

## 19. Prohibited shortcuts

The project must reject:

- a big-bang rewrite;
- canonical models designed only for `site-analize-by-pl`;
- replacing three protocols with one proxy URL;
- silent removal of legacy ports;
- lease state only in memory;
- SQL or business rules inside HTTP handlers;
- generated protobuf types inside domain crates;
- application-name conditionals;
- consumer access to raw device commands or ADB;
- global shared credentials for all consumers or devices;
- unbounded queues, maps or task spawning;
- plaintext tunnel downgrade;
- silent operator, region, device or protocol fallback;
- readiness based only on heartbeat.

## 20. Expert acceptance score

The design target is evaluated across modularity, clean dependencies, extensibility, backward compatibility, multi-consumer isolation, reliability, security, upgradeability, testability and operations.

The plan itself meets the architectural 10/10 target. The current implementation is not yet 10/10 because JSON canonical state, mixed control-plane layers, incomplete reserve-tunnel proof, global tunnel authentication and Android WireGuard coupling remain. Production 10/10 is earned only when all critical invariants and the physical matrix pass on one immutable commit SHA with no unresolved P0/P1 defects.
