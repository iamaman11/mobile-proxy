# Reverse tunnel event counters

## Scope

The host daemon exposes process-restart-persistent reverse-tunnel event counters through the existing authenticated `GET /v1/metrics` endpoint. The operator CLI continues to return the complete Prometheus exposition through `operator-cli metrics` without changing `operator-cli status` output.

## Authoritative boundary

The reverse-tunnel client lifecycle is the only event authority. It increments a fixed `TunnelEventCounters` value exactly where an attempt begins, a transport becomes connected, QUIC falls back, or a connected session terminates. The host daemon never reconstructs event frequency from current-state gauges and never increments a second copy. It only persists and projects the cumulative snapshot.

Each attempt has bounded duplicate guards, so repeated calls or repeated delivery of an identical snapshot cannot increment the same connection, failover or disconnect event twice. Counters use saturating `u64` increments and therefore never decrease or wrap.

## Transition model

Transitions describe changes between successful active transports, not attempted transports. The fixed inventory contains:

- `none` to `tcp`, `quic` or `tls_tcp`;
- `tcp` to `quic` or `tls_tcp`;
- `quic` to `tcp` or `tls_tcp`;
- `tls_tcp` to `tcp` or `quic`.

A first-start QUIC timeout followed by successful TLS/TCP fallback records `none -> tls_tcp` plus one `connect_timeout` failover. If a previously successful QUIC session later reconnects through TLS/TCP, it records `quic -> tls_tcp`. Reconnecting on the same transport is a connection and reconnect success, but not a transport transition.

## Persistence

The host daemon stores one schema-versioned JSON document at `reverse_tunnel.counter_state_path`, `HOST_DAEMON_REVERSE_TUNNEL_COUNTER_STATE_PATH`, or the default `state/reverse-tunnel-counters-v1.json`.

The file contains only fixed arrays, bounded enums, monotonic counters and the last successful transport. It contains no node ID, session ID, IP, hostname, token, credential, payload or free-form error. The encoded size is limited to 16 KiB. Writes use a same-directory temporary file, file sync and atomic rename. Unknown fields, invalid JSON, oversized files and unsupported schema versions fail closed during startup rather than silently resetting counters.

## Cardinality

The exposition has a compile-time upper bound:

- 3 connection series;
- 9 transition series;
- 5 QUIC failover series;
- 3 disconnect series;
- 2 label-free reconnect counters.

Current-state gauges remain unchanged. No supplied health string is interpolated into a metric label, and diagnostic failover history does not change readiness.
