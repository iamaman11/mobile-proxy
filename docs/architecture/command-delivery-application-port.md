# Command delivery application ports

Status: production migration slice  
Scope: existing device command polling and acknowledgement routes

## Contract

`mobile-proxy-application` owns transport-independent ports for polling the oldest pending command for one device, acknowledging successful execution, and reporting a retryable negative acknowledgement without deleting the command. Axum authenticates the request, converts path and JSON values to typed inputs, invokes one port and maps typed outcomes. The application crate has no runtime, filesystem, process, network or framework dependency.

## Compatibility

The existing HTTP surface is unchanged:

- `GET /api/v1/devices/{id}/commands/next` returns either the command object or JSON `null`;
- successful and negative acknowledgements return `{ "accepted": true }`;
- a repeated successful acknowledgement for a command that is no longer pending returns `{ "accepted": false }`;
- device and admin bearer-token separation remains unchanged.

## Persistence ordering

Successful acknowledgement clones the bounded command and device state, validates the queue key and command identity, removes the pending command, clears the device recovery intent, fsyncs and atomically renames the complete JSON candidate, and only then publishes the candidate in memory. A failed write returns `state_persistence_failed` and leaves the in-memory command pending. Negative acknowledgement does not mutate durable state and remains safe for repeated delivery.

## Explicitly deferred

SQLite transactions, durable acknowledgement history, claim leases, attempt counters, domain events, audit, outbox, per-device cryptographic identity and deadline expiry remain later bounded slices. Registration, heartbeat and public-probe handlers remain transitional.
