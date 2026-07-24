from pathlib import Path


def replace_once(path: Path, old: str, new: str, label: str) -> None:
    content = path.read_text(encoding="utf-8")
    count = content.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected exactly one match, found {count}")
    path.write_text(content.replace(old, new, 1), encoding="utf-8")


tunnel_path = Path("crates/reverse-tunnel/src/tunnel.rs")
vm_path = Path("apps/operator-cli/src/vm.rs")
doc_path = Path("docs/phase-c-fallback-recovery-proof.md")

anchor = "    fn test_config(server_addr: SocketAddr) -> ReverseTunnelClientConfig {\n"
insert = r'''    #[tokio::test]
    async fn hybrid_fallback_and_quic_recovery_preserve_proxy_surfaces() {
        let quic_addr = unused_udp_addr();
        let identity = test_quic_identity();
        let state = ReverseTunnelServerState::default();

        let backend_listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
        let backend_addr = backend_listener.local_addr().unwrap();
        let (backend_shutdown_tx, backend_shutdown_rx) = watch::channel(false);
        let backend = tokio::spawn(run_server(
            backend_listener,
            ReverseTunnelServerConfig {
                auth_token: "test-token".into(),
                transport: TunnelTransport::Tcp,
            },
            state.clone(),
            backend_shutdown_rx,
        ));

        let tls_listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
        let tls_addr = tls_listener.local_addr().unwrap();
        let (tls_shutdown_tx, tls_shutdown_rx) = watch::channel(false);
        let terminator = tokio::spawn(run_test_tls_terminator(
            tls_listener,
            backend_addr,
            identity.cert_der.clone(),
            identity.key_der.clone(),
            tls_shutdown_rx,
        ));

        let local_proxy_listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
        let local_proxy_addr = local_proxy_listener.local_addr().unwrap();
        let local_proxy = tokio::spawn(run_protocol_fixture(local_proxy_listener, 10));

        let mixed_listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
        let mixed_addr = mixed_listener.local_addr().unwrap();
        let (mixed_shutdown_tx, mixed_shutdown_rx) = watch::channel(false);
        let mixed_forwarder = tokio::spawn(run_quic_tcp_forward_listener(
            mixed_listener,
            state.clone(),
            Some("test-phone".into()),
            ProxyProtocol::Mixed,
            mixed_shutdown_rx,
        ));

        let socks_listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
        let socks_addr = socks_listener.local_addr().unwrap();
        let (socks_shutdown_tx, socks_shutdown_rx) = watch::channel(false);
        let socks_forwarder = tokio::spawn(run_quic_tcp_forward_listener(
            socks_listener,
            state.clone(),
            Some("test-phone".into()),
            ProxyProtocol::Socks5,
            socks_shutdown_rx,
        ));

        let http_listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
        let http_addr = http_listener.local_addr().unwrap();
        let (http_shutdown_tx, http_shutdown_rx) = watch::channel(false);
        let http_forwarder = tokio::spawn(run_quic_tcp_forward_listener(
            http_listener,
            state.clone(),
            Some("test-phone".into()),
            ProxyProtocol::Http,
            http_shutdown_rx,
        ));

        let mut client_config = test_hybrid_client_config(quic_addr, tls_addr, &identity);
        client_config.local_proxy_addr = local_proxy_addr;
        let (client_shutdown_tx, client_shutdown_rx) = watch::channel(false);
        let (status_tx, status_rx) = watch::channel(ClientSnapshot::new(Uuid::nil()));
        let client = tokio::spawn(run_client(client_config, client_shutdown_rx, status_tx));

        let fallback = wait_for_transport(status_rx.clone(), TunnelActiveTransport::TlsTcp).await;
        let fallback_reason = fallback
            .last_failover_reason
            .expect("forced QUIC failure must record a bounded failover reason");
        assert!(matches!(
            fallback_reason,
            TunnelFailoverReason::ConnectTimeout | TunnelFailoverReason::ConnectFailed
        ));
        assert_eq!(
            fallback
                .event_counters
                .connection_count(TunnelActiveTransport::TlsTcp),
            1
        );
        let recorded_failovers = fallback
            .event_counters
            .failover_count(TunnelFailoverReason::ConnectTimeout)
            + fallback
                .event_counters
                .failover_count(TunnelFailoverReason::ConnectFailed);
        assert_eq!(recorded_failovers, 1);
        let session_id = fallback.session_id;

        exercise_proxy_surfaces(mixed_addr, socks_addr, http_addr).await;

        let (quic_shutdown_tx, quic_shutdown_rx) = watch::channel(false);
        let quic_server = tokio::spawn(run_quic_server(
            quic_addr,
            test_hybrid_server_config(&identity),
            state.clone(),
            quic_shutdown_rx,
        ));
        sleep(Duration::from_millis(50)).await;

        tls_shutdown_tx.send(true).unwrap();
        terminator.await.unwrap().unwrap();

        let recovered = wait_for_transport(status_rx.clone(), TunnelActiveTransport::Quic).await;
        assert_eq!(recovered.session_id, session_id);
        assert_eq!(recovered.last_failover_reason, None);
        assert_eq!(
            recovered
                .event_counters
                .connection_count(TunnelActiveTransport::TlsTcp),
            1
        );
        assert_eq!(
            recovered
                .event_counters
                .connection_count(TunnelActiveTransport::Quic),
            1
        );
        assert_eq!(
            recovered
                .event_counters
                .transition_count(TunnelTransportTransition::TlsTcpToQuic),
            1
        );
        assert!(recovered.event_counters.reconnect_attempts() >= 1);
        assert_eq!(recovered.event_counters.reconnect_successes(), 1);

        let sessions = state.snapshot().await;
        assert_eq!(sessions.len(), 1);
        assert_eq!(sessions[0].session_id, session_id);
        assert!(sessions[0].connected);
        assert!(sessions[0].accepted_connections >= 2);

        exercise_proxy_surfaces(mixed_addr, socks_addr, http_addr).await;
        local_proxy.await.unwrap().unwrap();

        mixed_shutdown_tx.send(true).unwrap();
        socks_shutdown_tx.send(true).unwrap();
        http_shutdown_tx.send(true).unwrap();
        client_shutdown_tx.send(true).unwrap();
        quic_shutdown_tx.send(true).unwrap();
        backend_shutdown_tx.send(true).unwrap();

        mixed_forwarder.await.unwrap().unwrap();
        socks_forwarder.await.unwrap().unwrap();
        http_forwarder.await.unwrap().unwrap();
        client.await.unwrap();
        quic_server.await.unwrap().unwrap();
        backend.await.unwrap().unwrap();
    }

    async fn run_test_tls_terminator(
        listener: TcpListener,
        backend_addr: SocketAddr,
        cert_der: Vec<u8>,
        key_der: Vec<u8>,
        mut shutdown: watch::Receiver<bool>,
    ) -> Result<()> {
        let tls = rustls::ServerConfig::builder()
            .with_no_client_auth()
            .with_single_cert(
                vec![CertificateDer::from(cert_der)],
                PrivatePkcs8KeyDer::from(key_der).into(),
            )?;
        let acceptor = tokio_rustls::TlsAcceptor::from(Arc::new(tls));
        let mut connections = Vec::new();

        loop {
            tokio::select! {
                _ = shutdown.changed() => {
                    for connection in &connections {
                        connection.abort();
                    }
                    for connection in connections {
                        let _ = connection.await;
                    }
                    return Ok(());
                }
                accepted = listener.accept() => {
                    let (stream, _) = accepted?;
                    let acceptor = acceptor.clone();
                    connections.push(tokio::spawn(async move {
                        let result = async {
                            let mut tls = acceptor.accept(stream).await?;
                            let mut backend = TcpStream::connect(backend_addr).await?;
                            tokio::io::copy_bidirectional(&mut tls, &mut backend).await?;
                            Result::<()>::Ok(())
                        }
                        .await;
                        if let Err(error) = result {
                            debug!(error = %error, "test TLS terminator connection ended");
                        }
                    }));
                }
            }
        }
    }

    async fn run_protocol_fixture(
        listener: TcpListener,
        expected_connections: usize,
    ) -> Result<()> {
        for _ in 0..expected_connections {
            let (stream, _) = listener.accept().await?;
            handle_protocol_fixture_connection(stream).await?;
        }
        Ok(())
    }

    async fn handle_protocol_fixture_connection(mut stream: TcpStream) -> Result<()> {
        let first = stream.read_u8().await?;
        if first == 5 {
            let mut greeting = [0_u8; 2];
            stream.read_exact(&mut greeting).await?;
            if greeting != [1, 0] {
                bail!("unexpected SOCKS5 greeting: {greeting:?}");
            }
            stream.write_all(&[5, 0]).await?;

            let mut request = [0_u8; 9];
            stream.read_exact(&mut request).await?;
            if request[..3] != [1, 0, 1] {
                bail!("unexpected SOCKS5 connect request: {request:?}");
            }
            stream
                .write_all(&[5, 0, 0, 1, 127, 0, 0, 1, 0, 80])
                .await?;
            let mut payload = [0_u8; 4];
            stream.read_exact(&mut payload).await?;
            if &payload != b"ping" {
                bail!("unexpected SOCKS5 payload: {payload:?}");
            }
            stream.write_all(b"pong").await?;
            stream.shutdown().await?;
            return Ok(());
        }

        let mut headers = vec![first];
        while !headers.ends_with(b"\r\n\r\n") {
            if headers.len() >= 4096 {
                bail!("HTTP fixture header exceeded bound");
            }
            headers.push(stream.read_u8().await?);
        }
        if headers.starts_with(b"CONNECT example.test:443 HTTP/1.1\r\n") {
            stream
                .write_all(b"HTTP/1.1 200 Connection Established\r\n\r\n")
                .await?;
            let mut payload = [0_u8; 4];
            stream.read_exact(&mut payload).await?;
            if &payload != b"ping" {
                bail!("unexpected CONNECT payload: {payload:?}");
            }
            stream.write_all(b"pong").await?;
        } else if headers.starts_with(b"GET http://example.test/ HTTP/1.1\r\n") {
            stream
                .write_all(
                    b"HTTP/1.1 200 OK\r\nContent-Length: 4\r\nConnection: close\r\n\r\npong",
                )
                .await?;
        } else {
            bail!("unexpected HTTP fixture request: {headers:?}");
        }
        stream.shutdown().await?;
        Ok(())
    }

    async fn exercise_proxy_surfaces(
        mixed_addr: SocketAddr,
        socks_addr: SocketAddr,
        http_addr: SocketAddr,
    ) {
        timeout(Duration::from_secs(5), async {
            assert_socks_proxy(mixed_addr).await;
            assert_http_proxy(mixed_addr).await;
            assert_socks_proxy(socks_addr).await;
            assert_http_proxy(http_addr).await;
            assert_http_connect_proxy(http_addr).await;
        })
        .await
        .expect("protected proxy surface exercise timed out");
    }

    async fn assert_socks_proxy(addr: SocketAddr) {
        let mut stream = TcpStream::connect(addr).await.unwrap();
        stream.write_all(&[5, 1, 0]).await.unwrap();
        let mut selection = [0_u8; 2];
        stream.read_exact(&mut selection).await.unwrap();
        assert_eq!(selection, [5, 0]);

        stream
            .write_all(&[5, 1, 0, 1, 127, 0, 0, 1, 0, 80])
            .await
            .unwrap();
        let mut response = [0_u8; 10];
        stream.read_exact(&mut response).await.unwrap();
        assert_eq!(&response[..2], &[5, 0]);
        stream.write_all(b"ping").await.unwrap();
        let mut payload = [0_u8; 4];
        stream.read_exact(&mut payload).await.unwrap();
        assert_eq!(&payload, b"pong");
    }

    async fn assert_http_proxy(addr: SocketAddr) {
        let mut stream = TcpStream::connect(addr).await.unwrap();
        stream
            .write_all(b"GET http://example.test/ HTTP/1.1\r\nHost: example.test\r\n\r\n")
            .await
            .unwrap();
        let mut response = Vec::new();
        stream.read_to_end(&mut response).await.unwrap();
        assert!(response.starts_with(b"HTTP/1.1 200 OK\r\n"));
        assert!(response.ends_with(b"pong"));
    }

    async fn assert_http_connect_proxy(addr: SocketAddr) {
        let mut stream = TcpStream::connect(addr).await.unwrap();
        stream
            .write_all(b"CONNECT example.test:443 HTTP/1.1\r\nHost: example.test:443\r\n\r\n")
            .await
            .unwrap();
        let headers = read_http_headers(&mut stream).await.unwrap();
        assert!(headers.starts_with(b"HTTP/1.1 200 Connection Established\r\n"));
        stream.write_all(b"ping").await.unwrap();
        let mut payload = [0_u8; 4];
        stream.read_exact(&mut payload).await.unwrap();
        assert_eq!(&payload, b"pong");
    }

    async fn read_http_headers(stream: &mut TcpStream) -> Result<Vec<u8>> {
        let mut headers = Vec::new();
        while !headers.ends_with(b"\r\n\r\n") {
            if headers.len() >= 4096 {
                bail!("HTTP response header exceeded bound");
            }
            headers.push(stream.read_u8().await?);
        }
        Ok(headers)
    }

    async fn wait_for_transport(
        mut status: watch::Receiver<ClientSnapshot>,
        expected: TunnelActiveTransport,
    ) -> ClientSnapshot {
        timeout(Duration::from_secs(5), async move {
            loop {
                let snapshot = status.borrow().clone();
                if snapshot.connected && snapshot.active_transport == Some(expected) {
                    return snapshot;
                }
                status
                    .changed()
                    .await
                    .expect("reverse tunnel status sender ended unexpectedly");
            }
        })
        .await
        .expect("timed out waiting for reverse tunnel transport")
    }

    fn test_hybrid_client_config(
        quic_addr: SocketAddr,
        tls_addr: SocketAddr,
        identity: &TestQuicIdentity,
    ) -> ReverseTunnelClientConfig {
        ReverseTunnelClientConfig {
            node_id: "test-phone".into(),
            server_addr: quic_addr,
            tcp_fallback_addr: Some(tls_addr),
            local_proxy_addr: "127.0.0.1:9".parse().unwrap(),
            auth_token: "test-token".into(),
            transport: TunnelTransport::Hybrid {
                server_name: "localhost".into(),
                server_cert_der: identity.cert_der.clone(),
                server_key_der: None,
            },
            connect_timeout: Duration::from_millis(150),
            heartbeat_interval: Duration::from_millis(20),
            reconnect_floor: Duration::from_millis(10),
            reconnect_ceiling: Duration::from_millis(50),
        }
    }

    fn test_hybrid_server_config(identity: &TestQuicIdentity) -> ReverseTunnelServerConfig {
        ReverseTunnelServerConfig {
            auth_token: "test-token".into(),
            transport: TunnelTransport::Hybrid {
                server_name: "localhost".into(),
                server_cert_der: identity.cert_der.clone(),
                server_key_der: Some(identity.key_der.clone()),
            },
        }
    }

'''
replace_once(tunnel_path, anchor, insert + anchor, "fallback/recovery acceptance insertion")

vm = vm_path.read_text(encoding="utf-8")
marker = "nginx_stream_config_preserves_public_ports_and_tls_reserve"
if marker in vm:
    raise SystemExit("VM TLS reserve deployment test already exists")
vm += r'''

#[cfg(test)]
mod tests {
    use super::NGINX_STREAM_CONFIG;

    #[test]
    fn nginx_stream_config_preserves_public_ports_and_tls_reserve() {
        for expected in [
            "listen 0.0.0.0:1080",
            "listen 0.0.0.0:1081",
            "listen 0.0.0.0:3128",
            "listen 0.0.0.0:443 ssl",
            "proxy_pass 127.0.0.1:18091",
            "ssl_protocols TLSv1.2 TLSv1.3",
            "ssl_session_tickets off",
        ] {
            assert!(
                NGINX_STREAM_CONFIG.contains(expected),
                "missing protected deployment invariant: {expected}"
            );
        }
    }
}
'''
vm_path.write_text(vm, encoding="utf-8")

if doc_path.exists():
    raise SystemExit(f"{doc_path} already exists")
doc_path.write_text(
    """# Phase C forced fallback and recovery proof

Delivery item 10 is proved by a controlled process-level acceptance test in `crates/reverse-tunnel/src/tunnel.rs`.

The test uses the production transport composition rather than a branch mock:

1. the configured QUIC UDP endpoint is initially unbound;
2. a generated self-signed relay certificate is the hybrid client's only trust root;
3. a test TLS stream terminator models the production Nginx `443 ssl -> 127.0.0.1:18091` reserve path;
4. the client records a bounded QUIC connection failure and establishes the certificate-pinned TLS/TCP authority;
5. mixed, SOCKS5, HTTP forward-proxy and HTTP CONNECT conversations cross the reserve tunnel;
6. the QUIC listener is restored, the TLS terminator closes all reserve connections, and the same logical client session reconnects QUIC-first;
7. status clears the prior failover reason, records the `tls_tcp -> quic` transition, and the protected proxy conversations cross the recovered QUIC tunnel again.

The protocol fixture is test-only and bounded. It validates representative wire conversations while the reverse tunnel remains byte-transparent. The deployment test in `apps/operator-cli/src/vm.rs` separately pins the public ports and Nginx TLS reserve mapping.

No plaintext fallback was added. Public ports `1080`, `1081`, `3128`, QUIC primary behavior, certificate-pinned TLS/TCP reserve, and the existing WireGuard rollback path remain unchanged.

Acceptance requires architecture validation, Python regressions, rustfmt, strict Clippy, and the complete Cargo workspace test suite on one immutable SHA.
""",
    encoding="utf-8",
)
