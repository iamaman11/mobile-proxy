# Command issuance application port

Status: production migration slice
Scope: existing `POST /api/v1/devices/{id}/commands` behavior only

## Boundary

The transport handler authenticates through the existing admin middleware, receives already typed JSON, calls `IssueCommandPort::issue_command` once and maps its typed result. UUID generation, clock access, idempotency classification, queue policy, device projection and persistence are outside Axum.

`crates/application` is infrastructure-free. Permanent architecture validation permits only foundation and transitional domain-contract dependencies and rejects Axum, Tokio, filesystems, networking, SQL, environment access, clocks and random generation in that crate.

## Idempotency contract

The canonical claim key is a full typed BLAKE3 digest using domain:

```text
mobile-proxy/control-plane-command-idempotency-scope/v1
```

It frames `device_id` and the opaque idempotency key independently. Request equality uses:

```text
mobile-proxy/control-plane-command-request/v1
```

with independently framed device ID, desired state, recovery intent and deadline window. The idempotency key is the claim key and is therefore not duplicated inside the request fingerprint.

An identical replay returns the original `DeviceCommand`. A reused key with changed parameters returns HTTP `409` and `idempotency_conflict`. The raw key is never logged.

## Durable result and queue semantics

The delivery queue remains bounded to 50 commands per device. Idempotency results have a separate deterministic bound of 1000 claims, so removal from the queue does not remove the original replay result.

The JSON schema adds optional `idempotency_results` and `idempotency_order` fields under `commands`. Serde defaults keep old state readable; previous binaries ignore the added fields, preserving software rollback. Existing concatenated claims are a legacy migration input only. Recoverable claims are rewritten to the typed scope; an unrecoverable retained claim rejects reuse rather than creating a duplicate command.

For a new command, the adapter builds a candidate containing the queue, idempotency claim/result and device projection, writes and fsyncs a temporary file, atomically renames it, and only then swaps the in-memory state. A failed write publishes no command in memory.

## Non-goals

This slice does not claim that JSON is the final canonical store, does not add SQLite, audit or outbox persistence, and does not extract registration, heartbeat, probe, polling or acknowledgement handlers. Those remain explicit matrix gaps.
