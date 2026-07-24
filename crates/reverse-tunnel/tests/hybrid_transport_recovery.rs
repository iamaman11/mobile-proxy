use std::net::{SocketAddr, UdpSocket};
use std::sync::Arc;
use std::time::Duration;

use anyhow::{Context, Result, bail};
use reverse_tunnel::{
    ClientSnapshot, ProxyProtocol, ReverseTunnelClientConfig, ReverseTunnelServerConfig,
    ReverseTunnelServerState, TunnelActiveTransport, TunnelFailoverReason, TunnelFreshness,
    TunnelTransport, TunnelTransportTransition, run_client, run_quic_server,
    run_quic_tcp_forward_listener, run_server,
};
use rustls_pki_types::{CertificateDer, PrivatePkcs8KeyDer};
use tokio::io::{AsyncReadExt, AsyncWriteExt};
use tokio::net::{TcpListener, TcpStream};
use tokio::sync::watch;
use tokio::task::{JoinHandle, JoinSet};
use tokio::time::{sleep, timeout};
use tokio_rustls::TlsAcceptor;
use uuid::Uuid;

const NODE_ID: &str = "test-phone";
const AUTH_TOKEN: &str = "test-token";

#[tokio::test]
async fn hybrid_client_falls_back_then_recovers_quic_on_same_session() {
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

    let public = PublicProxySurface::start(state.clone()).await;

    wait_for_transport(
        status_rx.clone(),
        TunnelActiveTransport::TlsTcp,
        "TLS/TCP fallback",
    )
    .await;
    wait_for_authenticated_heartbeat(&state, status_rx.clone()).await;
    let fallback = status_rx.borrow().clone();
    assert_ne!(fallback.session_id, Uuid::nil());
    assert_eq!(fallback.freshness, TunnelFreshness::Fresh);
    assert_eq!(
        fallback.last_failover_reason,
        Some(TunnelFailoverReason::ConnectTimeout)
    );
    assert_eq!(
        fallback
            .event_counters
            .connection_count(TunnelActiveTransport::TlsTcp),
        1
    );
    assert_eq!(
        fallback
            .event_counters
            .transition_count(TunnelTransportTransition::NoneToTlsTcp),
        1
    );
    assert!(state.active_connection(Some(NODE_ID)).await.is_none());

    public.prove_all_surfaces().await;

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
    wait_for_authenticated_heartbeat(&state, status_rx.clone()).await;
    let recovered = status_rx.borrow().clone();
    assert_eq!(recovered.session_id, fallback.session_id);
    assert_eq!(recovered.freshness, TunnelFreshness::Fresh);
    assert_eq!(recovered.last_failover_reason, None);
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
    assert!(recovered.event_counters.reconnect_successes() >= 1);
    assert!(state.active_connection(Some(NODE_ID)).await.is_some());

    let sessions = state.snapshot().await;
    assert_eq!(sessions.len(), 1);
    assert_eq!(sessions[0].session_id, fallback.session_id);
    assert!(sessions[0].connected);

    public.prove_all_surfaces().await;

    public.shutdown().await;
    client_shutdown_tx.send(true).unwrap();
    client.await.unwrap();
    quic_shutdown_tx.send(true).unwrap();
    reverse_shutdown_tx.send(true).unwrap();
    quic_server.await.unwrap().unwrap();
    reverse_server.await.unwrap().unwrap();
    phone_proxy.shutdown().await;
}

struct PublicProxySurface {
    mixed_addr: SocketAddr,
    socks_addr: SocketAddr,
    http_addr: SocketAddr,
    shutdown_tx: watch::Sender<bool>,
    tasks: Vec<JoinHandle<Result<()>>>,
}

impl PublicProxySurface {
    async fn start(state: ReverseTunnelServerState) -> Self {
        let mixed = TcpListener::bind("127.0.0.1:0").await.unwrap();
        let mixed_addr = mixed.local_addr().unwrap();
        let socks = TcpListener::bind("127.0.0.1:0").await.unwrap();
        let socks_addr = socks.local_addr().unwrap();
        let http = TcpListener::bind("127.0.0.1:0").await.unwrap();
        let http_addr = http.local_addr().unwrap();
        let (shutdown_tx, shutdown_rx) = watch::channel(false);

        let tasks = vec![
            tokio::spawn(run_quic_tcp_forward_listener(
                mixed,
                state.clone(),
                Some(NODE_ID.into()),
                ProxyProtocol::Mixed,
                shutdown_rx.clone(),
            )),
            tokio::spawn(run_quic_tcp_forward_listener(
                socks,
                state.clone(),
                Some(NODE_ID.into()),
                ProxyProtocol::Socks5,
                shutdown_rx.clone(),
            )),
            tokio::spawn(run_quic_tcp_forward_listener(
                http,
                state,
                Some(NODE_ID.into()),
                ProxyProtocol::Http,
                shutdown_rx,
            )),
        ];

        Self {
            mixed_addr,
            socks_addr,
            http_addr,
            shutdown_tx,
            tasks,
        }
    }

    async fn prove_all_surfaces(&self) {
        socks_round_trip(self.mixed_addr, "mixed proxy").await;
        socks_round_trip(self.socks_addr, "SOCKS5 proxy").await;
        http_get(self.http_addr).await;
        http_connect_round_trip(self.http_addr).await;
    }

    async fn shutdown(self) {
        self.shutdown_tx.send(true).unwrap();
        for task in self.tasks {
            task.await.unwrap().unwrap();
        }
    }
}

struct TestPhoneProxy {
    addr: SocketAddr,
    shutdown_tx: watch::Sender<bool>,
    task: JoinHandle<Result<()>>,
}

impl TestPhoneProxy {
    async fn start() -> Self {
        let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
        let addr = listener.local_addr().unwrap();
        let (shutdown_tx, mut shutdown_rx) = watch::channel(false);
        let task = tokio::spawn(async move {
            let mut connections = JoinSet::new();
            loop {
                tokio::select! {
                    _ = shutdown_rx.changed() => break,
                    accepted = listener.accept() => {
                        let (stream, _) = accepted.context("phone proxy accept failed")?;
                        connections.spawn(async move { handle_phone_proxy_connection(stream).await });
                    }
                    completed = connections.join_next(), if !connections.is_empty() => {
                        let _ = completed.context("phone proxy task join failed")??;
                    }
                }
            }
            connections.abort_all();
            while connections.join_next().await.is_some() {}
            Ok(())
        });
        Self {
            addr,
            shutdown_tx,
            task,
        }
    }

    async fn shutdown(self) {
        self.shutdown_tx.send(true).unwrap();
        self.task.await.unwrap().unwrap();
    }
}

async fn handle_phone_proxy_connection(mut stream: TcpStream) -> Result<()> {
    let mut first = [0_u8; 1];
    stream.peek(&mut first).await?;
    if first[0] == 5 {
        handle_socks_proxy(&mut stream).await
    } else {
        handle_http_proxy(&mut stream).await
    }
}

async fn handle_socks_proxy(stream: &mut TcpStream) -> Result<()> {
    let mut greeting = [0_u8; 3];
    stream.read_exact(&mut greeting).await?;
    if greeting != [5, 1, 0] {
        bail!("unexpected SOCKS5 greeting: {greeting:?}");
    }
    stream.write_all(&[5, 0]).await?;

    let mut request = [0_u8; 10];
    stream.read_exact(&mut request).await?;
    if request[0..4] != [5, 1, 0, 1] {
        bail!("unexpected SOCKS5 connect request: {request:?}");
    }
    stream.write_all(&[5, 0, 0, 1, 127, 0, 0, 1, 0, 0]).await?;
    assert_ping_pong(stream).await
}

async fn handle_http_proxy(stream: &mut TcpStream) -> Result<()> {
    let request = read_http_headers(stream).await?;
    if request.starts_with(b"CONNECT ") {
        stream
            .write_all(b"HTTP/1.1 200 Connection Established\r\n\r\n")
            .await?;
        assert_ping_pong(stream).await
    } else {
        stream
            .write_all(b"HTTP/1.1 200 OK\r\nContent-Length: 8\r\nConnection: close\r\n\r\nproxy-ok")
            .await?;
        stream.shutdown().await?;
        Ok(())
    }
}

async fn assert_ping_pong(stream: &mut TcpStream) -> Result<()> {
    let mut request = [0_u8; 4];
    stream.read_exact(&mut request).await?;
    if &request != b"ping" {
        bail!("unexpected tunneled payload: {request:?}");
    }
    stream.write_all(b"pong").await?;
    Ok(())
}

async fn read_http_headers(stream: &mut TcpStream) -> Result<Vec<u8>> {
    let mut request = Vec::with_capacity(256);
    loop {
        if request.len() >= 8 * 1024 {
            bail!("HTTP proxy request headers are too large");
        }
        let byte = stream.read_u8().await?;
        request.push(byte);
        if request.ends_with(b"\r\n\r\n") {
            return Ok(request);
        }
    }
}

async fn socks_round_trip(addr: SocketAddr, surface: &str) {
    timeout(Duration::from_secs(3), async {
        let mut stream = TcpStream::connect(addr).await.unwrap();
        stream.write_all(&[5, 1, 0]).await.unwrap();
        let mut greeting = [0_u8; 2];
        stream.read_exact(&mut greeting).await.unwrap();
        assert_eq!(greeting, [5, 0], "{surface} greeting failed");

        stream
            .write_all(&[5, 1, 0, 1, 127, 0, 0, 1, 0, 80])
            .await
            .unwrap();
        let mut connected = [0_u8; 10];
        stream.read_exact(&mut connected).await.unwrap();
        assert_eq!(connected[0..2], [5, 0], "{surface} connect failed");

        stream.write_all(b"ping").await.unwrap();
        let mut response = [0_u8; 4];
        stream.read_exact(&mut response).await.unwrap();
        assert_eq!(&response, b"pong", "{surface} payload failed");
    })
    .await
    .unwrap_or_else(|_| panic!("{surface} did not traverse the active reverse tunnel"));
}

async fn http_get(addr: SocketAddr) {
    let response = timeout(Duration::from_secs(3), async {
        let mut stream = TcpStream::connect(addr).await.unwrap();
        stream
            .write_all(b"GET http://example.test/ HTTP/1.1\r\nHost: example.test\r\n\r\n")
            .await
            .unwrap();
        let mut response = Vec::new();
        stream.read_to_end(&mut response).await.unwrap();
        response
    })
    .await
    .expect("HTTP proxy request did not traverse the active reverse tunnel");
    assert!(response.starts_with(b"HTTP/1.1 200 OK"));
    assert!(response.ends_with(b"proxy-ok"));
}

async fn http_connect_round_trip(addr: SocketAddr) {
    timeout(Duration::from_secs(3), async {
        let mut stream = TcpStream::connect(addr).await.unwrap();
        stream
            .write_all(b"CONNECT example.test:443 HTTP/1.1\r\nHost: example.test:443\r\n\r\n")
            .await
            .unwrap();
        let response = read_http_headers(&mut stream).await.unwrap();
        assert!(response.starts_with(b"HTTP/1.1 200 Connection Established"));
        stream.write_all(b"ping").await.unwrap();
        let mut payload = [0_u8; 4];
        stream.read_exact(&mut payload).await.unwrap();
        assert_eq!(&payload, b"pong");
    })
    .await
    .expect("HTTP CONNECT did not traverse the active reverse tunnel");
}

async fn run_tls_terminator(
    listener: TcpListener,
    acceptor: TlsAcceptor,
    upstream_addr: SocketAddr,
    mut shutdown: watch::Receiver<bool>,
) -> Result<()> {
    let mut connections = JoinSet::new();
    loop {
        tokio::select! {
            _ = shutdown.changed() => break,
            accepted = listener.accept() => {
                let (stream, _) = accepted.context("TLS terminator accept failed")?;
                let acceptor = acceptor.clone();
                connections.spawn(async move {
                    proxy_tls_connection(acceptor, stream, upstream_addr).await
                });
            }
            completed = connections.join_next(), if !connections.is_empty() => {
                let _ = completed.context("TLS terminator task join failed")??;
            }
        }
    }
    connections.abort_all();
    while connections.join_next().await.is_some() {}
    Ok(())
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

async fn wait_for_transport(
    mut status: watch::Receiver<ClientSnapshot>,
    expected: TunnelActiveTransport,
    label: &str,
) {
    if timeout(Duration::from_secs(5), async {
        loop {
            if status.borrow().connected
                && status.borrow().active_transport == Some(expected)
                && status.borrow().freshness == TunnelFreshness::Fresh
            {
                return;
            }
            status.changed().await.unwrap();
        }
    })
    .await
    .is_err()
    {
        panic!(
            "timed out waiting for {label}; latest client snapshot: {:?}",
            status.borrow().clone()
        );
    }
}

async fn wait_for_authenticated_heartbeat(
    state: &ReverseTunnelServerState,
    status: watch::Receiver<ClientSnapshot>,
) {
    if timeout(Duration::from_secs(5), async {
        loop {
            if state.snapshot().await.first().is_some_and(|session| {
                session.connected && session.last_heartbeat_sequence.is_some()
            }) {
                return;
            }
            sleep(Duration::from_millis(10)).await;
        }
    })
    .await
    .is_err()
    {
        panic!(
            "timed out waiting for authenticated heartbeat; client={:?} server={:?}",
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
