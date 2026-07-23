use std::net::{SocketAddr, UdpSocket};
use std::sync::Arc;
use std::time::Duration;

use anyhow::{Context, Result};
use reverse_tunnel::{
    ClientSnapshot, ProxyProtocol, ReverseTunnelClientConfig, ReverseTunnelServerConfig,
    ReverseTunnelServerState, TunnelTransport, run_client, run_quic_tcp_forward_listener,
    run_server,
};
use rustls_pki_types::{CertificateDer, PrivatePkcs8KeyDer};
use tokio::io::{AsyncReadExt, AsyncWriteExt};
use tokio::net::{TcpListener, TcpStream};
use tokio::sync::watch;
use tokio::time::{sleep, timeout};
use tokio_rustls::TlsAcceptor;
use uuid::Uuid;

#[tokio::test]
async fn hybrid_client_falls_back_to_tls_tcp_and_forwards_proxy_bytes() {
    let identity = test_tls_identity();

    let phone_proxy_listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
    let phone_proxy_addr = phone_proxy_listener.local_addr().unwrap();
    let phone_proxy = tokio::spawn(async move {
        let (mut stream, _) = phone_proxy_listener.accept().await.unwrap();
        let mut request = [0_u8; 4];
        stream.read_exact(&mut request).await.unwrap();
        assert_eq!(&request, b"ping");
        stream.write_all(b"pong").await.unwrap();
    });

    let reverse_listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
    let reverse_addr = reverse_listener.local_addr().unwrap();
    let state = ReverseTunnelServerState::default();
    let (reverse_shutdown_tx, reverse_shutdown_rx) = watch::channel(false);
    let reverse_server = tokio::spawn(run_server(
        reverse_listener,
        ReverseTunnelServerConfig {
            auth_token: "test-token".into(),
            transport: TunnelTransport::Tcp,
        },
        state.clone(),
        reverse_shutdown_rx,
    ));

    let tls_listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
    let tls_addr = tls_listener.local_addr().unwrap();
    let tls_acceptor = test_tls_acceptor(&identity);
    let (tls_shutdown_tx, tls_shutdown_rx) = watch::channel(false);
    let tls_terminator = tokio::spawn(run_tls_terminator(
        tls_listener,
        tls_acceptor,
        reverse_addr,
        tls_shutdown_rx,
    ));

    // Keep the UDP port occupied by a non-QUIC socket. The primary QUIC attempt
    // cannot complete, so Hybrid must use the certificate-pinned TLS/TCP path.
    let blocked_quic_socket = UdpSocket::bind("127.0.0.1:0").unwrap();
    let blocked_quic_addr = blocked_quic_socket.local_addr().unwrap();

    let client_config = ReverseTunnelClientConfig {
        node_id: "test-phone".into(),
        server_addr: blocked_quic_addr,
        tcp_fallback_addr: Some(tls_addr),
        local_proxy_addr: phone_proxy_addr,
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
    };
    let (client_shutdown_tx, client_shutdown_rx) = watch::channel(false);
    let initial_snapshot = ClientSnapshot {
        session_id: Uuid::nil(),
        connected: false,
        attempts: 0,
        sent_heartbeats: 0,
        last_error: None,
    };
    let (status_tx, status_rx) = watch::channel(initial_snapshot);
    let client = tokio::spawn(run_client(client_config, client_shutdown_rx, status_tx));

    wait_for_authenticated_heartbeat(&state, status_rx).await;
    assert!(state.active_connection(Some("test-phone")).await.is_none());

    let public_listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
    let public_addr = public_listener.local_addr().unwrap();
    let (forward_shutdown_tx, forward_shutdown_rx) = watch::channel(false);
    let forwarder = tokio::spawn(run_quic_tcp_forward_listener(
        public_listener,
        state,
        Some("test-phone".into()),
        ProxyProtocol::Mixed,
        forward_shutdown_rx,
    ));

    timeout(Duration::from_secs(3), async {
        let mut stream = TcpStream::connect(public_addr).await.unwrap();
        stream.write_all(b"ping").await.unwrap();
        let mut response = [0_u8; 4];
        stream.read_exact(&mut response).await.unwrap();
        assert_eq!(&response, b"pong");
    })
    .await
    .expect("proxy bytes were not forwarded through TLS/TCP fallback");

    forward_shutdown_tx.send(true).unwrap();
    client_shutdown_tx.send(true).unwrap();
    tls_shutdown_tx.send(true).unwrap();
    reverse_shutdown_tx.send(true).unwrap();

    forwarder.await.unwrap().unwrap();
    client.await.unwrap();
    tls_terminator.await.unwrap().unwrap();
    reverse_server.await.unwrap().unwrap();
    phone_proxy.await.unwrap();
    drop(blocked_quic_socket);
}

async fn run_tls_terminator(
    listener: TcpListener,
    acceptor: TlsAcceptor,
    upstream_addr: SocketAddr,
    mut shutdown: watch::Receiver<bool>,
) -> Result<()> {
    loop {
        tokio::select! {
            _ = shutdown.changed() => return Ok(()),
            accepted = listener.accept() => {
                let (stream, _) = accepted.context("TLS terminator accept failed")?;
                let acceptor = acceptor.clone();
                tokio::spawn(async move {
                    if let Err(error) = proxy_tls_connection(acceptor, stream, upstream_addr).await {
                        panic!("TLS terminator connection failed: {error:#}");
                    }
                });
            }
        }
    }
}

async fn proxy_tls_connection(
    acceptor: TlsAcceptor,
    stream: TcpStream,
    upstream_addr: SocketAddr,
) -> Result<()> {
    let mut tls = acceptor.accept(stream).await.context("TLS accept failed")?;
    let mut upstream = TcpStream::connect(upstream_addr)
        .await
        .context("plain reverse-tunnel upstream connect failed")?;
    tokio::io::copy_bidirectional(&mut tls, &mut upstream)
        .await
        .context("TLS terminator copy failed")?;
    Ok(())
}

async fn wait_for_authenticated_heartbeat(
    state: &ReverseTunnelServerState,
    status: watch::Receiver<ClientSnapshot>,
) {
    if timeout(Duration::from_secs(3), async {
        loop {
            if state
                .snapshot()
                .await
                .first()
                .and_then(|session| session.last_heartbeat_sequence)
                .is_some()
            {
                return;
            }
            sleep(Duration::from_millis(10)).await;
        }
    })
    .await
    .is_err()
    {
        panic!(
            "timed out waiting for TLS/TCP fallback heartbeat; client={:?} server={:?}",
            status.borrow().clone(),
            state.snapshot().await
        );
    }
}

struct TestTlsIdentity {
    cert_der: Vec<u8>,
    key_der: Vec<u8>,
}

fn test_tls_identity() -> TestTlsIdentity {
    let certified = rcgen::generate_simple_self_signed(vec!["localhost".into()]).unwrap();
    TestTlsIdentity {
        cert_der: certified.cert.der().as_ref().to_vec(),
        key_der: certified.signing_key.serialize_der(),
    }
}

fn test_tls_acceptor(identity: &TestTlsIdentity) -> TlsAcceptor {
    let config = rustls::ServerConfig::builder()
        .with_no_client_auth()
        .with_single_cert(
            vec![CertificateDer::from(identity.cert_der.clone())],
            PrivatePkcs8KeyDer::from(identity.key_der.clone()).into(),
        )
        .unwrap();
    TlsAcceptor::from(Arc::new(config))
}
