# Phase D Liveness and Readiness Semantics

Status: delivery item 12 implementation candidate  
Issue: #58  
Scope: bounded process and dependency health only

## Decision

Process liveness, local service readiness and device/network availability are separate signals.

- `/livez` answers only whether the HTTP process is alive and able to serve the bounded probe.
- `/readyz` answers whether local critical dependencies are healthy.
- phone, cellular, local proxy and reverse-tunnel availability are reported separately and do not redefine process liveness.
- the existing authenticated health, status and metrics APIs remain unchanged.

## Control-plane semantics

The control-plane `/readyz` probe:

- requires the configured state path to remain an existing regular file;
- opens it with the existing SQLite-only `open_existing` path;
- validates schema and connection configuration;
- rehydrates the complete typed snapshot;
- never creates a missing database;
- returns only bounded backend and health fields.

The process-level acceptance starts a real control-plane process with an empty valid SQLite store and no registered device. It proves:

1. `/livez` returns `200 live` without a phone;
2. `/readyz` returns `200 ready` while SQLite is valid;
3. deleting the SQLite file causes `/readyz` to return `503 not_ready` without recreating the database;
4. `/livez` remains `200 live` after durable-store failure;
5. admin and device tokens never appear in the health output.

## Host-daemon semantics

The host-daemon `/readyz` response separates:

- critical reverse-tunnel worker initialization;
- reverse-tunnel counter-store persistence health;
- device serving, cellular-route, proxy-bind and local-serving availability;
- reverse-tunnel connected state, active transport and freshness.

An absent cellular path, disconnected tunnel or non-serving phone is a device-availability condition, not process death. A missing required worker or failed counter persistence is a local readiness failure and returns `503`.

Active transport and freshness are allow-listed to their finite protocol values. Raw errors, credentials and arbitrary strings are not exposed.

## Compatibility and scope boundary

Existing authenticated `/v1/health`, `/v1/status`, `/v1/proxy` and `/v1/metrics` behavior is unchanged. Protected mixed `1080`, SOCKS5 `1081`, HTTP/CONNECT `3128`, QUIC-first behavior, certificate-pinned TLS/TCP reserve and WireGuard rollback are unchanged.

No backup/restore behavior, physical-device requirement, Android runtime replacement, protocol migration or future-platform scope is introduced.

## Stop condition

After acceptance, delivery item 12 is complete. Proceed only to delivery item 13: backup, restore and clean-environment restore drill.
