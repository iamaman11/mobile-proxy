from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    target = Path(path)
    body = target.read_text()
    count = body.count(old)
    if count != 1:
        raise RuntimeError(f"expected one match in {path}, found {count}: {old[:120]!r}")
    target.write_text(body.replace(old, new, 1))


state = "services/host-daemon/src/state.rs"
replace_once(
    state,
    "    pub reverse_tunnel_counters: TunnelEventCounters,\n    pub reverse_tunnel_restart: Option<watch::Sender<u64>>,\n",
    "    pub reverse_tunnel_counters: TunnelEventCounters,\n    pub reverse_tunnel_counter_persistence_healthy: bool,\n    pub reverse_tunnel_restart: Option<watch::Sender<u64>>,\n",
)
replace_once(
    state,
    "            reverse_tunnel_counters: TunnelEventCounters::default(),\n            reverse_tunnel_restart: None,\n",
    "            reverse_tunnel_counters: TunnelEventCounters::default(),\n            reverse_tunnel_counter_persistence_healthy: true,\n            reverse_tunnel_restart: None,\n",
)

reverse = "services/host-daemon/src/reverse_tunnel.rs"
replace_once(
    reverse,
    "        runtime.reverse_tunnel_counters = initial_counters;\n",
    "        runtime.reverse_tunnel_counters = initial_counters;\n        runtime.reverse_tunnel_counter_persistence_healthy = true;\n",
)
replace_once(
    reverse,
    '''    if let Err(error) = counter_store
        .lock()
        .await
        .persist_if_changed(&snapshot.event_counters)
    {
        warn!(error = %error, "failed to persist reverse tunnel counters");
    }
''',
    '''    let persistence_healthy = match counter_store
        .lock()
        .await
        .persist_if_changed(&snapshot.event_counters)
    {
        Ok(_) => true,
        Err(error) => {
            warn!(error = %error, "failed to persist reverse tunnel counters");
            false
        }
    };
''',
)
replace_once(
    reverse,
    "        runtime.reverse_tunnel_counters = snapshot.event_counters.clone();\n        runtime.reverse_tunnel = Some(snapshot.clone());\n",
    "        runtime.reverse_tunnel_counters = snapshot.event_counters.clone();\n        runtime.reverse_tunnel_counter_persistence_healthy = persistence_healthy;\n        runtime.reverse_tunnel = Some(snapshot.clone());\n",
)

api = "services/host-daemon/src/api.rs"
replace_once(
    api,
    "        runtime.health.reverse_tunnel_failover_reason.as_deref(),\n        &runtime.reverse_tunnel_counters,\n",
    "        runtime.health.reverse_tunnel_failover_reason.as_deref(),\n        runtime.reverse_tunnel_counter_persistence_healthy,\n        &runtime.reverse_tunnel_counters,\n",
)
replace_once(
    api,
    "    failover_reason: Option<&str>,\n    counters: &TunnelEventCounters,\n",
    "    failover_reason: Option<&str>,\n    counter_persistence_healthy: bool,\n    counters: &TunnelEventCounters,\n",
)
replace_once(
    api,
    '''    writeln!(
        output,
        "mobile_proxy_reverse_tunnel_reconnect_successes_total {}",
        counters.reconnect_successes()
    )
    .unwrap();
    output
''',
    '''    writeln!(
        output,
        "mobile_proxy_reverse_tunnel_reconnect_successes_total {}",
        counters.reconnect_successes()
    )
    .unwrap();
    writeln!(
        output,
        "# TYPE mobile_proxy_reverse_tunnel_counter_persistence_healthy gauge"
    )
    .unwrap();
    writeln!(
        output,
        "mobile_proxy_reverse_tunnel_counter_persistence_healthy {}",
        u8::from(counter_persistence_healthy)
    )
    .unwrap();
    output
''',
)
replace_once(
    api,
    "            Some(\"connect_timeout\"),\n            &counters,\n",
    "            Some(\"connect_timeout\"),\n            true,\n            &counters,\n",
)
replace_once(
    api,
    "            Some(\"raw-provider-error\"),\n            &counters,\n",
    "            Some(\"raw-provider-error\"),\n            true,\n            &counters,\n",
)
replace_once(
    api,
    "            render_reverse_tunnel_metrics(Some(false), None, Some(\"stale\"), None, &counters);\n",
    "            render_reverse_tunnel_metrics(Some(false), None, Some(\"stale\"), None, true, &counters);\n",
)
replace_once(
    api,
    '''        assert!(metrics.contains(
            r#"mobile_proxy_reverse_tunnel_failovers_total{reason="connect_timeout"} 1"#
        ));
''',
    '''        assert!(metrics.contains(
            r#"mobile_proxy_reverse_tunnel_failovers_total{reason="connect_timeout"} 1"#
        ));
        assert!(
            metrics.contains("mobile_proxy_reverse_tunnel_counter_persistence_healthy 1")
        );
''',
)
replace_once(
    api,
    '''    #[test]
    fn stale_current_state_does_not_decrease_counters() {
''',
    '''    #[test]
    fn counter_persistence_health_is_bounded_and_label_free() {
        let counters = TunnelEventCounters::default();
        let metrics = render_reverse_tunnel_metrics(None, None, None, None, false, &counters);
        assert!(metrics.contains("mobile_proxy_reverse_tunnel_counter_persistence_healthy 0"));
        assert_eq!(
            metrics
                .lines()
                .filter(|line| {
                    line.starts_with("mobile_proxy_reverse_tunnel_counter_persistence_healthy ")
                })
                .count(),
            1
        );
        assert!(!metrics.lines().any(|line| {
            line.starts_with("mobile_proxy_reverse_tunnel_counter_persistence_healthy{")
        }));
    }

    #[test]
    fn stale_current_state_does_not_decrease_counters() {
''',
)

store = "services/host-daemon/src/tunnel_counters.rs"
replace_once(
    store,
    '''    #[test]
    fn invalid_schema_fails_closed() {
''',
    '''    #[test]
    fn failed_write_does_not_advance_state_and_is_retryable() {
        let directory = std::env::temp_dir().join(format!(
            "mobile-proxy-tunnel-counter-retry-test-{}",
            Uuid::new_v4()
        ));
        let blocking_parent = directory.join("state");
        let path = blocking_parent.join("counters.json");
        let mut store = TunnelCounterStore::load(path.clone()).unwrap();
        fs::create_dir_all(&directory).unwrap();
        fs::write(&blocking_parent, b"not-a-directory").unwrap();

        let mut counters = TunnelEventCounters::default();
        counters.begin_attempt();
        counters.record_connection(TunnelActiveTransport::Quic);
        assert!(store.persist_if_changed(&counters).is_err());
        assert!(!store.counters().same_persisted_state(&counters));

        fs::remove_file(&blocking_parent).unwrap();
        fs::create_dir_all(&blocking_parent).unwrap();
        assert!(store.persist_if_changed(&counters).unwrap());
        let reloaded = TunnelCounterStore::load(path).unwrap();
        assert!(reloaded.counters().same_persisted_state(&counters));
        fs::remove_dir_all(directory).unwrap();
    }

    #[test]
    fn invalid_schema_fails_closed() {
''',
)

doc = Path("docs/operations/reverse-tunnel-counter-alerts.md")
doc.write_text('''# Reverse tunnel counter alerts and recovery

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
''')

counter_doc = "docs/operations/reverse-tunnel-event-counters.md"
replace_once(
    counter_doc,
    "Current-state gauges remain unchanged. No supplied health string is interpolated into a metric label, and diagnostic failover history does not change readiness.\n",
    "Current-state gauges remain unchanged. No supplied health string is interpolated into a metric label, and diagnostic failover history does not change readiness. Persistence health and operator response are documented in [Reverse tunnel counter alerts and recovery](reverse-tunnel-counter-alerts.md).\n",
)
