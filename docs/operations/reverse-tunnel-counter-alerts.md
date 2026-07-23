# Reverse tunnel counter alerts and recovery

## Scope

This runbook uses the existing authenticated `/v1/metrics` exposition. It does not introduce another event source, does not change readiness, and never requires high-cardinality labels.

## Persistence health

`mobile_proxy_reverse_tunnel_counter_persistence_healthy` is a label-free current-state gauge:

- `1` means the last required persistence operation succeeded, or no changed counter state required a write;
- `0` means the latest changed snapshot could not be persisted. In-process counters remain monotonic and the next changed snapshot retries the same absolute cumulative state.

Recommended page condition:

```promql
mobile_proxy_reverse_tunnel_counter_persistence_healthy == 0
```

Apply an environment-appropriate `for` duration to avoid paging on a transient filesystem interruption. This gauge is diagnostic and must not be folded into proxy readiness.

On alert:

1. Check host-daemon logs for `failed to persist reverse tunnel counters` without copying credential-bearing context into tickets.
2. Verify that the configured counter-state parent is a directory, writable by the host-daemon user, and located on the expected persistent filesystem.
3. Check free space, inode availability and filesystem health.
4. Do not delete a valid state file merely to clear the alert. Correct the storage problem and allow the next changed snapshot to retry.
5. If startup fails because the file is corrupt, oversized or has an unsupported schema, preserve it as evidence, move it out of the active path, document the monotonicity discontinuity and restart with an empty version-1 state only under an explicit operator decision.

## Event-rate signals

Use counter deltas rather than the current-state failover gauge:

```promql
increase(mobile_proxy_reverse_tunnel_failovers_total[15m])
increase(mobile_proxy_reverse_tunnel_reconnect_attempts_total[15m])
increase(mobile_proxy_reverse_tunnel_reconnect_successes_total[15m])
increase(mobile_proxy_reverse_tunnel_disconnects_total[15m])
```

Alert thresholds must be calibrated from the deployment baseline. A single bounded failover may be an expected reserve-path success; sustained failovers, reconnect attempts without matching successes, or repeated session errors are stronger operational signals.

Useful bounded breakdowns:

```promql
sum by (reason) (increase(mobile_proxy_reverse_tunnel_failovers_total[15m]))
sum by (reason) (increase(mobile_proxy_reverse_tunnel_disconnects_total[15m]))
sum by (from, to) (increase(mobile_proxy_reverse_tunnel_transport_transitions_total[15m]))
```

Never add node ID, session ID, hostname, IP, token, credential or raw error text as permanent labels when adapting these rules for a fleet monitoring system.
