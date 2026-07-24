# Public-Probe Application Port

Status: implemented production-baseline slice  
Baseline source: `4c48d08fc2f06f24c9bc23431547f425078d2eb7`

## Purpose

The authenticated admin transport no longer owns public-probe mutation or persistence ordering. It decodes the existing request, invokes one typed application port and maps only bounded outcomes or errors.

## Compatibility

The route remains `POST /api/v1/devices/{id}/public-probe` and successful requests retain the existing `{ "accepted": true }` response. A report for an unknown device remains an accepted no-op, now represented explicitly as the bounded `device_not_found` outcome rather than implicit map behavior.

The caller-supplied `public_probe_at` field remains a compatibility input and is not trusted as canonical time. The server records its own authoritative observation timestamp, matching the previous projection behavior.

## Durable mutation ordering

For an existing device the adapter:

1. locks the device projection and validates that the map key matches the stored `node_id`;
2. locks command state in the established devices-then-commands order;
3. clones the bounded candidate state;
4. applies the probe and recomputes the runtime projection on the candidate;
5. writes, syncs and atomically renames the complete stored state;
6. publishes the candidate in memory only after the durable write succeeds.

A failed write returns `state_persistence_failed` and leaves the prior in-memory projection unchanged. Inconsistent device identity returns `device_state_conflict` without attempting publication.

## Observability

Structured logs contain authenticated request lineage, device ID, bounded outcome classification and bounded error codes. The free-form probe error and raw request payload are neither logged nor returned in safe API errors.

## Evidence

Tests prove durable restart rehydration, authoritative timestamping, accepted unknown-device no-op compatibility, failed-write rollback and fail-closed identity mismatch behavior. The permanent workspace workflow validates architecture boundaries, formatting, strict Clippy and the complete test suite.

## Non-goals

This slice does not add a probe scheduler, external observer consensus, retry orchestration, new persistence concepts, new route versions or a separate ports crate.
