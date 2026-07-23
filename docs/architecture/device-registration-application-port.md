# Device registration application port

Status: production migration slice  
Scope: existing `POST /api/v1/devices/register` route

## Contract

`mobile-proxy-application` owns the transport-independent device-registration port. Axum authenticates the device request, decodes the existing JSON request, invokes one use case and maps typed outcomes. The application crate has no runtime, filesystem, process, network or framework dependency.

Raw registration fields are not logged. Structured logs contain only authenticated request lineage, bounded classification and bounded error codes until device identity is represented by a validated type. The existing transport strings are compatibility inputs, not a claim that per-device identity or registration metadata is already strongly typed.

## Replay and compatibility semantics

The HTTP request and response shapes are unchanged. Successful first registration and a repeated registration both return `{ "accepted": true }`.

`node_id` is the natural replay key during the JSON migration period:

- the first accepted registration creates the initial device projection;
- a repeated registration does not overwrite the first registered `node_name`, `proxy_status` or `tunnel_owner`;
- mutable runtime state continues to arrive through heartbeat rather than registration;
- a persisted map whose key disagrees with the stored device `node_id` fails closed as `device_state_conflict`.

This preserves restart compatibility for the host daemon while preventing registration retries from silently rewriting canonical device metadata.

## Persistence ordering

Registration is a candidate transaction over the complete JSON-era device and command state:

1. lock device and command state in the established order;
2. clone the bounded device registry;
3. classify the request as `created` or `already_registered`;
4. serialize the complete candidate;
5. fsync the temporary file and atomically rename it;
6. publish a newly created device in memory only after the durable write succeeds.

A failed write returns `state_persistence_failed`. A new device is not published in memory, and a repeated registration is not acknowledged as durable when the backing state cannot be written.

## Capacity and typed failures

The transitional JSON registry is bounded at 10,000 devices. A new registration beyond that limit returns `device_capacity_exceeded` without evicting an existing device. Internal key/value disagreement returns `device_state_conflict`.

## Explicitly deferred

SQLite canonical storage, per-device cryptographic identity, durable registration history, domain events, audit, outbox, metrics and replacement of the shared device bearer token remain later bounded slices. Heartbeat and public-probe handlers are still transitional.
