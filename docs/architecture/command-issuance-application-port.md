# Command issuance application port

Status: production migration slice
Scope: existing `POST /api/v1/devices/{id}/commands` behavior only

## Boundary

The transport handler authenticates through the existing admin middleware, receives already typed JSON, calls `IssueCommandPort::issue_command` once and maps its typed result. UUID generation, clock access, idempotency classification, queue policy, device projection and persistence are outside Axum.

`crates/application` is infrastructure-free. Permanent architecture validation permits only foundation and transitional domain-contract dependencies and rejects Axum, Tokio, filesystems, networking, SQL, environment access, clocks and random generation in that crate.

## Idempotency contract

The canonical durable-result key is a full typed BLAKE3 digest using domain:

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

The delivery queue remains bounded to 50 commands per device and 1000 pending commands globally. A full per-device or global queue fails with `command_capacity_exceeded`; no pending command is silently evicted. Idempotency results have a deterministic bound of 1000 canonical entries, and pending results are never selected for retention eviction.

The JSON schema adds optional `idempotency_results` and `idempotency_order` fields under `commands`. Serde defaults keep old state readable. The legacy concatenated claim remains as a compatibility alias while canonical result identity uses the typed digest. This lets a previous binary still deduplicate a pending command. If a rollback writer drops the added fields, the new binary reconstructs exact replay evidence from the queue and legacy claim; an unrecoverable retained claim rejects reuse fail closed. Legacy aliases plus canonical history remain bounded to at most 2000 claim records.

For a new command, the adapter builds a candidate containing the queue, idempotency claim/result and device projection, writes and fsyncs a temporary file, atomically renames it, and only then swaps the in-memory state. A failed write publishes no command in memory.

## Non-goals

This slice does not claim that JSON is the final canonical store, does not add SQLite, audit or outbox persistence, and does not extract registration, heartbeat, probe, polling or acknowledgement handlers. Those remain explicit matrix gaps.
