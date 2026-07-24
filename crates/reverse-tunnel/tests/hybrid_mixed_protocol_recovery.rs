mod recovery {
    include!("hybrid_transport_recovery.rs");

    #[tokio::test]
    async fn mixed_proxy_accepts_http_and_connect_over_fallback_and_recovered_quic() {
        let identity = test_tls_identity();
        let phone_proxy = TestPhoneProxy::start().await;
        let state = ReverseTunnelServerState::default();

        let reverse_listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
        let reverse_addr = reverse_listener.local_addr().unwrap();
        let (reverse_shutdown_tx, reverse_shutdown_rx) = watch::channel(false);
        let reverse_server = tokio::spawn(run_server(
            reverse_listener,
            ReverseTunnelServerConfig {
                auth_token: AUTH_TOKEN.into(),
                transport: TunnelTransport::Tcp,
            },
            state.clone(),
            reverse_shutdown_rx,
        ));

        let tls_listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
        let tls_addr = tls_listener.local_addr().unwrap();
        let (tls_shutdown_tx, tls_shutdown_rx) = watch::channel(false);
        let tls_terminator = tokio::spawn(run_tls_terminator(
            tls_listener,
            test_tls_acceptor(&identity),
            reverse_addr,
            tls_shutdown_rx,
        ));

        let blocked_quic_socket = UdpSocket::bind("127.0.0.1:0").unwrap();
        let quic_addr = blocked_quic_socket.local_addr().unwrap();
        let (client_shutdown_tx, client_shutdown_rx) = watch::channel(false);
        let (status_tx, status_rx) = watch::channel(ClientSnapshot {
            session_id: Uuid::nil(),
            connected: false,
            attempts: 0,
            sent_heartbeats: 0,
            last_error: None,
            active_transport: None,
            freshness: TunnelFreshness::Unknown,
            last_failover_reason: None,
            event_counters: reverse_tunnel::TunnelEventCounters::default(),
        });
        let client = tokio::spawn(run_client(
            ReverseTunnelClientConfig {
                node_id: NODE_ID.into(),
                server_addr: quic_addr,
                tcp_fallback_addr: Some(tls_addr),
                local_proxy_addr: phone_proxy.addr,
                auth_token: AUTH_TOKEN.into(),
                transport: TunnelTransport::Hybrid {
                    server_name: "localhost".into(),
                    server_cert_der: identity.cert_der.clone(),
                    server_key_der: None,
                },
                connect_timeout: Duration::from_millis(150),
                heartbeat_interval: Duration::from_millis(20),
                reconnect_floor: Duration::from_millis(10),
                reconnect_ceiling: Duration::from_millis(50),
            },
            client_shutdown_rx,
            status_tx,
        ));

        let mixed = TcpListener::bind("127.0.0.1:0").await.unwrap();
        let mixed_addr = mixed.local_addr().unwrap();
        let (mixed_shutdown_tx, mixed_shutdown_rx) = watch::channel(false);
        let mixed_listener = tokio::spawn(run_quic_tcp_forward_listener(
            mixed,
            state.clone(),
            Some(NODE_ID.into()),
            ProxyProtocol::Mixed,
            mixed_shutdown_rx,
        ));

        wait_for_transport(
            status_rx.clone(),
            TunnelActiveTransport::TlsTcp,
            "TLS/TCP fallback",
        )
        .await;
        wait_for_authenticated_heartbeat(&state, status_rx.clone()).await;
        http_get(mixed_addr).await;
        http_connect_round_trip(mixed_addr).await;

        drop(blocked_quic_socket);
        let (quic_shutdown_tx, quic_shutdown_rx) = watch::channel(false);
        let quic_server = tokio::spawn(run_quic_server(
            quic_addr,
            ReverseTunnelServerConfig {
                auth_token: AUTH_TOKEN.into(),
                transport: TunnelTransport::Hybrid {
                    server_name: "localhost".into(),
                    server_cert_der: identity.cert_der.clone(),
                    server_key_der: Some(identity.key_der.clone()),
                },
            },
            state.clone(),
            quic_shutdown_rx,
        ));

        tls_shutdown_tx.send(true).unwrap();
        tls_terminator.await.unwrap().unwrap();
        wait_for_transport(
            status_rx.clone(),
            TunnelActiveTransport::Quic,
            "recovered QUIC",
        )
        .await;
        wait_for_authenticated_heartbeat(&state, status_rx).await;
        http_get(mixed_addr).await;
        http_connect_round_trip(mixed_addr).await;

        mixed_shutdown_tx.send(true).unwrap();
        mixed_listener.await.unwrap().unwrap();
        client_shutdown_tx.send(true).unwrap();
        client.await.unwrap();
        quic_shutdown_tx.send(true).unwrap();
        reverse_shutdown_tx.send(true).unwrap();
        quic_server.await.unwrap().unwrap();
        reverse_server.await.unwrap().unwrap();
        phone_proxy.shutdown().await;
    }
}
