# Device heartbeat application port

Status: production migration slice  
Scope: existing `POST /api/v1/devices/heartbeat` route

## Contract

`mobile-proxy-application` owns the transport-independent heartbeat port. Axum authenticates the device request, decodes the existing JSON shape, invokes one use case and maps typed outcomes. The application crate remains independent of Axum, Tokio, filesystems and persistence adapters.

The successful response remains `{ "accepted": true }`. Unknown typed-fingerprint prefixes still fail during request decoding. Bounded legacy fingerprint inputs remain accepted only for the existing rolling migration and are reported through a bounded outcome classification without persisting the legacy values.

## State transition

Heartbeat replaces the mutable runtime projection for one exact `node_id` while preserving the latest public-probe projection owned by the existing device record. The transition fails closed when the persisted map key disagrees with the stored `node_id`.

A heartbeat may create the first runtime projection for a device to preserve existing compatibility. The JSON-era registry remains bounded at 10,000 devices: an update for an existing device is allowed at capacity, while a new device is rejected with `device_capacity_exceeded`.

## Persistence ordering

Heartbeat is a candidate transaction over the complete JSON-era device and command state:

1. lock device and command state in the established order;
2. clone the bounded device registry;
3. validate exact device ownership and capacity;
4. build the replacement runtime projection while retaining public-probe fields;
5. serialize the complete candidate;
6. fsync the temporary file and atomically rename it;
7. publish the replacement projection in memory only after the durable write succeeds.

A failed durable write returns `state_persistence_failed` and leaves the prior in-memory projection unchanged. A successful response therefore never acknowledges a heartbeat that exists only in memory.

## Observability

Structured logs contain authenticated request lineage, `node_id`, bounded classification and bounded error codes. Raw fingerprint values, proxy errors and request payloads are not logged. Legacy fingerprint warnings are emitted only after the durable transition succeeds.

## Explicitly deferred

Public-probe extraction, SQLite canonical storage, cryptographic device identity, heartbeat sequencing, domain events, audit, outbox and replacement of the shared device bearer token remain separate bounded work. This slice does not add a new bounded context or persistence concept.
