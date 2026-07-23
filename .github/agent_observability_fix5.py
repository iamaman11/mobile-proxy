from pathlib import Path

path = Path('.github/agent_observability.py')
text = path.read_text()
marker = '''workflow = subprocess.check_output(
    ["git", "show", "origin/main:.github/workflows/rust-quality.yml"],
    text=True,
)
'''
addition = '''replace_once(
    "crates/reverse-tunnel/tests/hybrid_tls_fallback.rs",
    ''' + "'''" + '''    ClientSnapshot, ProxyProtocol, ReverseTunnelClientConfig, ReverseTunnelServerConfig,
    ReverseTunnelServerState, TunnelTransport, run_client, run_quic_tcp_forward_listener,
    run_server,
''' + "'''" + ''',
    ''' + "'''" + '''    ClientSnapshot, ProxyProtocol, ReverseTunnelClientConfig, ReverseTunnelServerConfig,
    ReverseTunnelServerState, TunnelActiveTransport, TunnelFailoverReason, TunnelFreshness,
    TunnelTransport, run_client, run_quic_tcp_forward_listener, run_server,
''' + "'''" + '''
)
replace_once(
    "crates/reverse-tunnel/tests/hybrid_tls_fallback.rs",
    ''' + "'''" + '''        sent_heartbeats: 0,
        last_error: None,
    };
''' + "'''" + ''',
    ''' + "'''" + '''        sent_heartbeats: 0,
        last_error: None,
        active_transport: None,
        freshness: TunnelFreshness::Unknown,
        last_failover_reason: None,
    };
''' + "'''" + '''
)
replace_once(
    "crates/reverse-tunnel/tests/hybrid_tls_fallback.rs",
    ''' + "'''" + '''    wait_for_authenticated_heartbeat(&state, status_rx).await;
    assert!(state.active_connection(Some("test-phone")).await.is_none());
''' + "'''" + ''',
    ''' + "'''" + '''    let observability_rx = status_rx.clone();
    wait_for_authenticated_heartbeat(&state, status_rx).await;
    let snapshot = observability_rx.borrow().clone();
    assert_eq!(
        snapshot.active_transport,
        Some(TunnelActiveTransport::TlsTcp)
    );
    assert_eq!(snapshot.freshness, TunnelFreshness::Fresh);
    assert_eq!(
        snapshot.last_failover_reason,
        Some(TunnelFailoverReason::ConnectTimeout)
    );
    assert!(state.active_connection(Some("test-phone")).await.is_none());
''' + "'''" + '''
)
'''
if text.count(marker) != 1:
    raise RuntimeError('expected one workflow restoration marker')
path.write_text(text.replace(marker, addition + marker, 1))
Path(__file__).unlink()
