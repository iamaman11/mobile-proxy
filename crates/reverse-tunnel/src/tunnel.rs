use std::net::SocketAddr;
use std::sync::Arc;
use std::time::Duration;

use anyhow::{Context, Result, bail};
use quinn::{ClientConfig, Endpoint, ServerConfig, TransportConfig};
use rustls::RootCertStore;
use rustls_pki_types::{CertificateDer, PrivatePkcs8KeyDer, ServerName};
use subtle::ConstantTimeEq;
use tokio::io::{
    AsyncBufRead, AsyncBufReadExt, AsyncRead, AsyncReadExt, AsyncWrite, AsyncWriteExt, BufReader,
};
use tokio::net::{TcpListener, TcpStream};
use tokio::sync::{mpsc, watch};
use tokio::time::{Instant, sleep, timeout};
use tokio_rustls::{TlsConnector, client::TlsStream};
use tracing::{debug, info, warn};
use uuid::Uuid;

use crate::model::*;
use crate::state::ReverseTunnelServerState;

pub async fn run_client(
    config: ReverseTunnelClientConfig,
    shutdown: watch::Receiver<bool>,
    status: watch::Sender<ClientSnapshot>,
) {
    run_client_with_counters(config, shutdown, status, TunnelEventCounters::default()).await;
}

pub async fn run_client_with_counters(
    config: ReverseTunnelClientConfig,
    mut shutdown: watch::Receiver<bool>,
    status: watch::Sender<ClientSnapshot>,
    initial_event_counters: TunnelEventCounters,
) {
    let session_id = Uuid::new_v4();
    let mut snapshot = ClientSnapshot::with_event_counters(session_id, initial_event_counters);
    let mut backoff = config.reconnect_floor;

    loop {
        if *shutdown.borrow() {
            snapshot.connected = false;
            snapshot.active_transport = None;
            snapshot.freshness = TunnelFreshness::Stale;
            let _ = status.send(snapshot);
            return;
        }

        snapshot.connected = false;
        snapshot.active_transport = None;
        snapshot.freshness = TunnelFreshness::Unknown;
        snapshot.attempts += 1;
        snapshot.event_counters.begin_attempt();
        let _ = status.send(snapshot.clone());

        match connect_and_pump(&config, session_id, &mut shutdown, &mut snapshot, &status).await {
            Ok(()) => {
                if snapshot.connected {
                    snapshot
                        .event_counters
                        .record_disconnect(TunnelDisconnectReason::Shutdown);
                }
                snapshot.connected = false;
                snapshot.active_transport = None;
                snapshot.freshness = TunnelFreshness::Stale;
                snapshot.last_error = None;
                let _ = status.send(snapshot.clone());
                backoff = config.reconnect_floor;
            }
            Err(err) => {
                let had_connected_session = snapshot.connected;
                if had_connected_session {
                    snapshot
                        .event_counters
                        .record_disconnect(disconnect_reason(&err));
                }
                snapshot.connected = false;
                snapshot.active_transport = None;
                snapshot.freshness = TunnelFreshness::Stale;
                snapshot.last_error = Some(format!("{err:#}"));
                let _ = status.send(snapshot.clone());
                if had_connected_session {
                    backoff = config.reconnect_floor;
                }
                if sleep_or_shutdown(backoff, &mut shutdown).await {
                    return;
                }
                backoff = next_backoff(backoff, config.reconnect_ceiling);
            }
        }
    }
}

pub async fn run_server(
    listener: TcpListener,
    config: ReverseTunnelServerConfig,
    state: ReverseTunnelServerState,
    mut shutdown: watch::Receiver<bool>,
) -> Result<()> {
    loop {
        tokio::select! {
            _ = shutdown.changed() => {
                state.shutdown_tcp().await;
                return Ok(());
            }
            accepted = listener.accept() => {
                let (stream, peer) = accepted.context("reverse tunnel accept failed")?;
                debug!(%peer, "accepted TCP reverse tunnel connection");
                let state = state.clone();
                let config = config.clone();
                tokio::spawn(async move {
                    if let Err(err) = handle_server_connection(stream, config, state).await {
                        warn!(error = %err, "TCP reverse tunnel control connection ended");
                    }
                });
            }
        }
    }
}

pub async fn run_quic_server(
    bind_addr: SocketAddr,
    config: ReverseTunnelServerConfig,
    state: ReverseTunnelServerState,
    mut shutdown: watch::Receiver<bool>,
) -> Result<()> {
    let (TunnelTransport::Quic {
        server_cert_der, ..
    }
    | TunnelTransport::Hybrid {
        server_cert_der, ..
    }) = &config.transport
    else {
        bail!("run_quic_server requires TunnelTransport::Quic");
    };
    let key = quic_server_key(&config.transport)?;
    let mut crypto = rustls::ServerConfig::builder()
        .with_no_client_auth()
        .with_single_cert(
            vec![CertificateDer::from(server_cert_der.clone())],
            key.into(),
        )
        .context("failed to build rustls server config")?;
    crypto.alpn_protocols = vec![b"mobile-proxy-tunnel".to_vec()];
    let mut server_config = ServerConfig::with_crypto(Arc::new(
        quinn::crypto::rustls::QuicServerConfig::try_from(crypto)?,
    ));
    *Arc::get_mut(&mut server_config.transport)
        .context("QUIC transport config is unexpectedly shared")? = quic_transport_config()?;
    let endpoint = Endpoint::server(server_config, bind_addr)?;

    loop {
        tokio::select! {
            _ = shutdown.changed() => {
                endpoint.close(0_u32.into(), b"shutdown");
                return Ok(());
            }
            incoming = endpoint.accept() => {
                let Some(incoming) = incoming else {
                    return Ok(());
                };
                let state = state.clone();
                let config = config.clone();
                tokio::spawn(async move {
                    if let Err(err) = handle_quic_incoming(incoming, config, state).await {
                        warn!(error = %err, "QUIC reverse tunnel connection ended");
                    }
                });
            }
        }
    }
}

pub async fn run_quic_tcp_forward_listener(
    listener: TcpListener,
    state: ReverseTunnelServerState,
    target_node_id: Option<String>,
    protocol: ProxyProtocol,
    mut shutdown: watch::Receiver<bool>,
) -> Result<()> {
    loop {
        tokio::select! {
            _ = shutdown.changed() => return Ok(()),
            accepted = listener.accept() => {
                let (mut stream, _) = accepted.context("reverse tunnel TCP forward accept failed")?;
                let state = state.clone();
                let target_node_id = target_node_id.clone();
                tokio::spawn(async move {
                    if !state.has_active_session(target_node_id.as_deref()).await {
                        reject_unavailable(&mut stream, protocol).await;
                        return;
                    }
                    if let Err(err) = forward_tcp_over_quic(stream, state, target_node_id.as_deref()).await {
                        warn!(error = %err, "reverse tunnel TCP forward failed");
                    }
                });
            }
        }
    }
}

async fn reject_unavailable(stream: &mut TcpStream, protocol: ProxyProtocol) {
    let protocol = match protocol {
        ProxyProtocol::Mixed => {
            let mut first = [0_u8; 1];
            match timeout(Duration::from_millis(500), stream.peek(&mut first)).await {
                Ok(Ok(1)) if first[0] == 5 => ProxyProtocol::Socks5,
                _ => ProxyProtocol::Http,
            }
        }
        protocol => protocol,
    };
    let response: &[u8] = match protocol {
        ProxyProtocol::Socks5 => &[5, 0xff],
        ProxyProtocol::Http | ProxyProtocol::Mixed => {
            b"HTTP/1.1 503 Service Unavailable\r\nConnection: close\r\nContent-Length: 31\r\nContent-Type: text/plain\r\nRetry-After: 5\r\n\r\nmobile proxy device is offline\n"
        }
    };
    let _ = stream.write_all(response).await;
    let _ = stream.shutdown().await;
}

async fn forward_tcp_over_quic(
    mut tcp_stream: TcpStream,
    state: ReverseTunnelServerState,
    target_node_id: Option<&str>,
) -> Result<()> {
    let Some(connection) = state.active_connection(target_node_id).await else {
        let mut upstream = state.open_tcp_proxy(target_node_id).await?;
        tokio::io::copy_bidirectional(&mut tcp_stream, &mut upstream).await?;
        return Ok(());
    };
    debug!("opening reverse tunnel proxy stream");
    let (mut quic_send, quic_recv) = connection
        .open_bi()
        .await
        .context("failed to open reverse tunnel proxy stream")?;
    write_server_frame(
        &mut quic_send,
        &ServerFrame::OpenProxy {
            stream_id: Uuid::new_v4(),
        },
    )
    .await?;
    debug!("reverse tunnel proxy stream opened");
    pipe_tcp_and_quic(tcp_stream, quic_send, quic_recv).await
}

async fn connect_and_pump(
    config: &ReverseTunnelClientConfig,
    session_id: Uuid,
    shutdown: &mut watch::Receiver<bool>,
    snapshot: &mut ClientSnapshot,
    status: &watch::Sender<ClientSnapshot>,
) -> Result<()> {
    if matches!(config.transport, TunnelTransport::Quic { .. }) {
        return connect_and_pump_quic(config, session_id, shutdown, snapshot, status).await;
    }
    if matches!(config.transport, TunnelTransport::Hybrid { .. }) {
        match connect_and_pump_quic(config, session_id, shutdown, snapshot, status).await {
            Ok(()) => return Ok(()),
            Err(error) => {
                let reason = record_quic_failover(snapshot, &error, status);
                warn!(
                    node_id = %config.node_id,
                    from_transport = "quic",
                    to_transport = "tls_tcp",
                    reason = reason.as_str(),
                    "reverse tunnel transport failover"
                );
            }
        }
        return connect_and_pump_tls_tcp(config, session_id, shutdown, snapshot, status).await;
    }
    let stream = timeout(
        config.connect_timeout,
        TcpStream::connect(config.server_addr),
    )
    .await
    .context("connect timed out")?
    .context("connect failed")?;
    let (reader, mut writer) = stream.into_split();
    let mut reader = BufReader::new(reader);
    let hello = ClientFrame::Hello(TunnelHello {
        node_id: config.node_id.clone(),
        session_id,
        protocol_version: 1,
        auth_token: config.auth_token.clone(),
    });
    write_frame(&mut writer, &hello).await?;

    mark_snapshot_connected(snapshot, TunnelActiveTransport::Tcp, false);
    let _ = status.send(snapshot.clone());
    let mut sequence = snapshot.sent_heartbeats;

    loop {
        let deadline = Instant::now() + config.heartbeat_interval;
        tokio::select! {
            _ = shutdown.changed() => {
                return Ok(());
            }
            maybe_line = read_optional_line(&mut reader) => {
                let Some(line) = maybe_line? else {
                    return Err(anyhow::anyhow!("server closed reverse tunnel"));
                };
                let frame: ServerFrame = serde_json::from_str(&line)
                    .context("failed to decode TCP reverse tunnel server frame")?;
                match frame {
                    ServerFrame::OpenProxy { stream_id } => {
                        let config = config.clone();
                        tokio::spawn(async move {
                            if let Err(err) = open_tcp_client_proxy_stream(&config, session_id, stream_id).await {
                                warn!(error = %err, "TCP client proxy stream failed");
                            }
                        });
                    }
                }
            }
            _ = sleep_until(deadline) => {
                sequence += 1;
                write_frame(&mut writer, &ClientFrame::Heartbeat(TunnelHeartbeat {
                    node_id: config.node_id.clone(),
                    session_id,
                    sequence,
                })).await?;
                snapshot.sent_heartbeats = sequence;
                let _ = status.send(snapshot.clone());
            }
        }
    }
}

fn mark_snapshot_connected(
    snapshot: &mut ClientSnapshot,
    transport: TunnelActiveTransport,
    preserve_failover_reason: bool,
) {
    snapshot.event_counters.record_connection(transport);
    snapshot.connected = true;
    snapshot.active_transport = Some(transport);
    snapshot.freshness = TunnelFreshness::Fresh;
    snapshot.last_error = None;
    if !preserve_failover_reason {
        snapshot.last_failover_reason = None;
    }
}

fn record_quic_failover(
    snapshot: &mut ClientSnapshot,
    error: &anyhow::Error,
    status: &watch::Sender<ClientSnapshot>,
) -> TunnelFailoverReason {
    let reason = quic_failover_reason(error);
    snapshot.connected = false;
    snapshot.active_transport = None;
    snapshot.freshness = TunnelFreshness::Unknown;
    snapshot.last_failover_reason = Some(reason);
    snapshot.event_counters.record_failover(reason);
    let _ = status.send(snapshot.clone());
    reason
}

fn quic_failover_reason(error: &anyhow::Error) -> TunnelFailoverReason {
    let message = error.to_string();
    if message.contains("timed out") {
        TunnelFailoverReason::ConnectTimeout
    } else if message.contains("connect failed") {
        TunnelFailoverReason::ConnectFailed
    } else if message.contains("authentication") {
        TunnelFailoverReason::AuthenticationFailed
    } else if message.contains("closed") {
        TunnelFailoverReason::SessionClosed
    } else {
        TunnelFailoverReason::SessionError
    }
}

fn disconnect_reason(error: &anyhow::Error) -> TunnelDisconnectReason {
    if error.to_string().contains("closed") {
        TunnelDisconnectReason::SessionClosed
    } else {
        TunnelDisconnectReason::SessionError
    }
}

async fn connect_and_pump_tls_tcp(
    config: &ReverseTunnelClientConfig,
    session_id: Uuid,
    shutdown: &mut watch::Receiver<bool>,
    snapshot: &mut ClientSnapshot,
    status: &watch::Sender<ClientSnapshot>,
) -> Result<()> {
    let stream = tls_tcp_connect(config).await?;
    let (reader, mut writer) = tokio::io::split(stream);
    let mut reader = BufReader::new(reader);
    write_frame(
        &mut writer,
        &ClientFrame::Hello(TunnelHello {
            node_id: config.node_id.clone(),
            session_id,
            protocol_version: 1,
            auth_token: config.auth_token.clone(),
        }),
    )
    .await?;
    mark_snapshot_connected(snapshot, TunnelActiveTransport::TlsTcp, true);
    let _ = status.send(snapshot.clone());
    let mut sequence = snapshot.sent_heartbeats;
    loop {
        let deadline = Instant::now() + config.heartbeat_interval;
        tokio::select! {
            _ = shutdown.changed() => return Ok(()),
            maybe_line = read_optional_line(&mut reader) => {
                let Some(line) = maybe_line? else { bail!("TLS/TCP server closed reverse tunnel"); };
                let ServerFrame::OpenProxy { stream_id } = serde_json::from_str(&line)?;
                let config = config.clone();
                tokio::spawn(async move {
                    if let Err(err) = open_tcp_client_proxy_stream(&config, session_id, stream_id).await {
                        warn!(error = %err, "TLS/TCP client proxy stream failed");
                    }
                });
            }
            _ = sleep_until(deadline) => {
                sequence += 1;
                write_frame(&mut writer, &ClientFrame::Heartbeat(TunnelHeartbeat {
                    node_id: config.node_id.clone(), session_id, sequence,
                })).await?;
                snapshot.sent_heartbeats = sequence;
                let _ = status.send(snapshot.clone());
            }
        }
    }
}

async fn tls_tcp_connect(config: &ReverseTunnelClientConfig) -> Result<TlsStream<TcpStream>> {
    let TunnelTransport::Hybrid {
        server_name,
        server_cert_der,
        ..
    } = &config.transport
    else {
        bail!("TLS/TCP fallback requires hybrid transport");
    };
    let mut roots = RootCertStore::empty();
    roots.add(CertificateDer::from(server_cert_der.clone()))?;
    let tls = rustls::ClientConfig::builder()
        .with_root_certificates(roots)
        .with_no_client_auth();
    let connector = TlsConnector::from(Arc::new(tls));
    let name =
        ServerName::try_from(server_name.clone()).context("invalid TLS fallback server name")?;
    let tcp = timeout(
        config.connect_timeout,
        TcpStream::connect(config.tcp_fallback_addr.unwrap_or(config.server_addr)),
    )
    .await
    .context("TLS/TCP connect timed out")??;
    timeout(config.connect_timeout, connector.connect(name, tcp))
        .await
        .context("TLS/TCP handshake timed out")?
        .context("TLS/TCP handshake failed")
}

async fn open_tcp_client_proxy_stream(
    config: &ReverseTunnelClientConfig,
    session_id: Uuid,
    stream_id: Uuid,
) -> Result<()> {
    if matches!(config.transport, TunnelTransport::Hybrid { .. }) {
        let mut server = tls_tcp_connect(config).await?;
        write_frame(
            &mut server,
            &ClientFrame::ProxyStream {
                node_id: config.node_id.clone(),
                session_id,
                stream_id,
                auth_token: config.auth_token.clone(),
            },
        )
        .await?;
        let mut local = TcpStream::connect(config.local_proxy_addr).await?;
        tokio::io::copy_bidirectional(&mut server, &mut local).await?;
        return Ok(());
    }
    let mut server = timeout(
        config.connect_timeout,
        TcpStream::connect(config.server_addr),
    )
    .await
    .context("TCP proxy stream connect timed out")??;
    write_frame(
        &mut server,
        &ClientFrame::ProxyStream {
            node_id: config.node_id.clone(),
            session_id,
            stream_id,
            auth_token: config.auth_token.clone(),
        },
    )
    .await?;
    let mut local = TcpStream::connect(config.local_proxy_addr).await?;
    tokio::io::copy_bidirectional(&mut server, &mut local).await?;
    Ok(())
}

async fn connect_and_pump_quic(
    config: &ReverseTunnelClientConfig,
    session_id: Uuid,
    shutdown: &mut watch::Receiver<bool>,
    snapshot: &mut ClientSnapshot,
    status: &watch::Sender<ClientSnapshot>,
) -> Result<()> {
    let (TunnelTransport::Quic {
        server_name,
        server_cert_der,
        ..
    }
    | TunnelTransport::Hybrid {
        server_name,
        server_cert_der,
        ..
    }) = &config.transport
    else {
        bail!("connect_and_pump_quic requires TunnelTransport::Quic");
    };
    let mut endpoint = Endpoint::client("0.0.0.0:0".parse()?)?;
    endpoint.set_default_client_config(quic_client_config(server_cert_der.clone())?);
    let connecting = endpoint.connect(config.server_addr, server_name)?;
    let connection = timeout(config.connect_timeout, connecting)
        .await
        .context("QUIC connect timed out")?
        .context("QUIC connect failed")?;
    info!(server_addr = %config.server_addr, "QUIC reverse tunnel connected");
    let (mut send, recv) = connection.open_bi().await?;
    let mut reader = BufReader::new(recv);
    let hello = ClientFrame::Hello(TunnelHello {
        node_id: config.node_id.clone(),
        session_id,
        protocol_version: 1,
        auth_token: config.auth_token.clone(),
    });
    write_frame(&mut send, &hello).await?;

    mark_snapshot_connected(snapshot, TunnelActiveTransport::Quic, false);
    let _ = status.send(snapshot.clone());
    let mut sequence = snapshot.sent_heartbeats;
    let proxy_connection = connection.clone();
    let local_proxy_addr = config.local_proxy_addr;
    tokio::spawn(async move {
        while let Ok((send, recv)) = proxy_connection.accept_bi().await {
            tokio::spawn(async move {
                if let Err(err) = handle_client_proxy_stream(send, recv, local_proxy_addr).await {
                    warn!(error = %err, "client proxy stream failed");
                }
            });
        }
        warn!("QUIC reverse tunnel proxy stream accept loop ended");
    });

    loop {
        let deadline = Instant::now() + config.heartbeat_interval;
        tokio::select! {
            _ = shutdown.changed() => {
                let _ = send.finish();
                connection.close(0_u32.into(), b"shutdown");
                endpoint.close(0_u32.into(), b"shutdown");
                return Ok(());
            }
            maybe_line = read_optional_line(&mut reader) => {
                let line = maybe_line?;
                if line.is_none() {
                    return Err(anyhow::anyhow!("server closed reverse tunnel"));
                }
            }
            _ = sleep_until(deadline) => {
                sequence += 1;
                write_frame(&mut send, &ClientFrame::Heartbeat(TunnelHeartbeat {
                    node_id: config.node_id.clone(),
                    session_id,
                    sequence,
                })).await?;
                snapshot.sent_heartbeats = sequence;
                let _ = status.send(snapshot.clone());
            }
        }
    }
}

async fn handle_quic_incoming(
    incoming: quinn::Incoming,
    config: ReverseTunnelServerConfig,
    state: ReverseTunnelServerState,
) -> Result<()> {
    let connection = incoming.await.context("QUIC incoming connection failed")?;
    debug!("accepted QUIC reverse tunnel connection");
    let (send, recv) = connection.accept_bi().await?;
    handle_quic_control_stream(send, recv, connection, config, state).await
}

async fn handle_quic_control_stream(
    _send: quinn::SendStream,
    recv: quinn::RecvStream,
    connection: quinn::Connection,
    config: ReverseTunnelServerConfig,
    state: ReverseTunnelServerState,
) -> Result<()> {
    let mut reader = BufReader::new(recv);
    let first = read_required_frame(&mut reader).await?;
    let ClientFrame::Hello(hello) = first else {
        bail!("reverse tunnel connection did not start with hello");
    };
    if !bool::from(
        hello
            .auth_token
            .as_bytes()
            .ct_eq(config.auth_token.as_bytes()),
    ) {
        bail!("reverse tunnel authentication failed");
    }
    info!(node_id = %hello.node_id, session_id = %hello.session_id, "reverse tunnel authenticated");
    mark_connected(&state, &hello, Some(connection)).await;

    loop {
        match read_optional_frame(&mut reader).await {
            Ok(Some(ClientFrame::Heartbeat(heartbeat))) => {
                mark_heartbeat(&state, &heartbeat).await;
            }
            Ok(Some(ClientFrame::Hello(_) | ClientFrame::ProxyStream { .. })) => {
                bail!("unexpected repeated hello on reverse tunnel session");
            }
            Ok(None) => {
                mark_disconnected(&state, &hello).await;
                return Ok(());
            }
            Err(err) => {
                mark_disconnected(&state, &hello).await;
                return Err(err);
            }
        }
    }
}

fn quic_client_config(server_cert_der: Vec<u8>) -> Result<ClientConfig> {
    let mut roots = RootCertStore::empty();
    roots.add(CertificateDer::from(server_cert_der))?;
    let mut crypto = rustls::ClientConfig::builder()
        .with_root_certificates(roots)
        .with_no_client_auth();
    crypto.alpn_protocols = vec![b"mobile-proxy-tunnel".to_vec()];
    let mut config = ClientConfig::new(Arc::new(
        quinn::crypto::rustls::QuicClientConfig::try_from(crypto)?,
    ));
    config.transport_config(Arc::new(quic_transport_config()?));
    Ok(config)
}

fn quic_transport_config() -> Result<TransportConfig> {
    let mut transport = TransportConfig::default();
    transport
        .max_concurrent_bidi_streams(256_u16.into())
        .max_concurrent_uni_streams(0_u8.into())
        .keep_alive_interval(Some(Duration::from_secs(2)))
        .max_idle_timeout(Some(Duration::from_secs(10).try_into()?));
    Ok(transport)
}

fn quic_server_key(transport: &TunnelTransport) -> Result<PrivatePkcs8KeyDer<'static>> {
    let (TunnelTransport::Quic { server_key_der, .. }
    | TunnelTransport::Hybrid { server_key_der, .. }) = transport
    else {
        bail!("QUIC server key requested for non-QUIC transport");
    };
    let key = server_key_der
        .clone()
        .context("QUIC server transport requires server_key_der")?;
    Ok(PrivatePkcs8KeyDer::from(key))
}

async fn handle_client_proxy_stream(
    quic_send: quinn::SendStream,
    quic_recv: quinn::RecvStream,
    local_proxy_addr: SocketAddr,
) -> Result<()> {
    let mut reader = BufReader::new(quic_recv);
    let first = read_required_server_frame(&mut reader).await?;
    match first {
        ServerFrame::OpenProxy { .. } => {
            debug!(local_proxy_addr = %local_proxy_addr, "opening phone-local proxy stream");
            let tcp_stream = TcpStream::connect(local_proxy_addr)
                .await
                .with_context(|| format!("failed to connect local proxy at {local_proxy_addr}"))?;
            pipe_tcp_and_quic(tcp_stream, quic_send, reader).await
        }
    }
}

async fn pipe_tcp_and_quic<R>(
    tcp_stream: TcpStream,
    mut quic_send: quinn::SendStream,
    mut quic_recv: R,
) -> Result<()>
where
    R: AsyncRead + Unpin,
{
    let (mut tcp_read, mut tcp_write) = tcp_stream.into_split();
    let to_quic = async {
        pump_with_flush(&mut tcp_read, &mut quic_send).await?;
        let _ = quic_send.finish();
        Result::<u64>::Ok(0)
    };
    let to_tcp = async {
        pump_with_flush(&mut quic_recv, &mut tcp_write).await?;
        tcp_write.shutdown().await?;
        Result::<u64>::Ok(0)
    };
    tokio::try_join!(to_quic, to_tcp).context("reverse tunnel byte stream copy failed")?;
    Ok(())
}

async fn pump_with_flush<R, W>(reader: &mut R, writer: &mut W) -> Result<u64>
where
    R: AsyncRead + Unpin,
    W: AsyncWrite + Unpin,
{
    let mut copied = 0_u64;
    let mut buffer = [0_u8; 16 * 1024];
    loop {
        let read = reader.read(&mut buffer).await?;
        if read == 0 {
            return Ok(copied);
        }
        writer.write_all(&buffer[..read]).await?;
        writer.flush().await?;
        copied += read as u64;
    }
}

async fn handle_server_connection(
    mut stream: TcpStream,
    config: ReverseTunnelServerConfig,
    state: ReverseTunnelServerState,
) -> Result<()> {
    let first = read_first_frame(&mut stream).await?;
    if let ClientFrame::ProxyStream {
        node_id,
        session_id,
        stream_id,
        auth_token,
    } = first
    {
        if !bool::from(auth_token.as_bytes().ct_eq(config.auth_token.as_bytes())) {
            bail!("reverse tunnel proxy stream authentication failed");
        }
        state
            .accept_tcp_proxy_stream(&node_id, session_id, stream_id, stream)
            .await?;
        return Ok(());
    }
    let ClientFrame::Hello(hello) = first else {
        bail!("reverse tunnel connection did not start with hello");
    };
    if !bool::from(
        hello
            .auth_token
            .as_bytes()
            .ct_eq(config.auth_token.as_bytes()),
    ) {
        bail!("reverse tunnel authentication failed");
    }
    let (reader, mut writer) = stream.into_split();
    let mut reader = BufReader::new(reader);
    let (control_tx, mut control_rx) = mpsc::channel(256);
    info!(node_id = %hello.node_id, session_id = %hello.session_id, "TCP reverse tunnel authenticated");
    mark_connected(&state, &hello, None).await;
    state
        .register_tcp_control(hello.node_id.clone(), hello.session_id, control_tx)
        .await;

    let result = loop {
        tokio::select! {
            frame = control_rx.recv() => {
                let Some(frame) = frame else { break Ok(()); };
                if let Err(error) = write_server_frame(&mut writer, &frame).await {
                    break Err(error);
                }
            }
            incoming = read_optional_frame(&mut reader) => match incoming {
                Ok(Some(ClientFrame::Heartbeat(heartbeat))) => {
                    mark_heartbeat(&state, &heartbeat).await;
                }
                Ok(Some(ClientFrame::Hello(_) | ClientFrame::ProxyStream { .. })) => {
                    break Err(anyhow::anyhow!(
                        "unexpected repeated hello on reverse tunnel session"
                    ));
                }
                Ok(None) => break Ok(()),
                Err(error) => break Err(error),
            }
        }
    };
    state
        .remove_tcp_control_for_session(&hello.node_id, hello.session_id)
        .await;
    mark_disconnected(&state, &hello).await;
    result
}

async fn read_first_frame(stream: &mut TcpStream) -> Result<ClientFrame> {
    let mut bytes = Vec::with_capacity(256);
    loop {
        let byte = stream
            .read_u8()
            .await
            .context("reverse tunnel closed before first frame")?;
        bytes.push(byte);
        if byte == b'\n' {
            break;
        }
        if bytes.len() > 64 * 1024 {
            bail!("reverse tunnel first frame is too large");
        }
    }
    serde_json::from_slice(&bytes).context("failed to decode reverse tunnel first frame")
}

async fn read_required_frame<R>(reader: &mut R) -> Result<ClientFrame>
where
    R: AsyncBufRead + Unpin,
{
    read_optional_frame(reader)
        .await?
        .context("reverse tunnel connection closed before first frame")
}

async fn read_required_server_frame<R>(reader: &mut R) -> Result<ServerFrame>
where
    R: AsyncBufRead + Unpin,
{
    read_optional_server_frame(reader)
        .await?
        .context("reverse tunnel proxy stream closed before first frame")
}

async fn read_optional_frame<R>(reader: &mut R) -> Result<Option<ClientFrame>>
where
    R: AsyncBufRead + Unpin,
{
    let Some(line) = read_optional_line(reader).await? else {
        return Ok(None);
    };
    serde_json::from_str(&line)
        .context("failed to decode reverse tunnel frame")
        .map(Some)
}

async fn read_optional_server_frame<R>(reader: &mut R) -> Result<Option<ServerFrame>>
where
    R: AsyncBufRead + Unpin,
{
    let Some(line) = read_optional_line(reader).await? else {
        return Ok(None);
    };
    serde_json::from_str(&line)
        .context("failed to decode reverse tunnel server frame")
        .map(Some)
}

async fn mark_connected(
    state: &ReverseTunnelServerState,
    hello: &TunnelHello,
    connection: Option<quinn::Connection>,
) {
    state
        .register_session_liveness(hello.node_id.clone(), hello.session_id)
        .await;
    let mut sessions = state.sessions.lock().await;
    let previous_session = sessions
        .get(&hello.node_id)
        .map(|session| session.session_id);
    let accepted_connections = sessions
        .get(&hello.node_id)
        .map(|existing| existing.accepted_connections + 1)
        .unwrap_or(1);
    sessions.insert(
        hello.node_id.clone(),
        ServerSessionSnapshot {
            node_id: hello.node_id.clone(),
            session_id: hello.session_id,
            connected: true,
            accepted_connections,
            last_heartbeat_sequence: None,
        },
    );
    drop(sessions);
    if let Some(previous_session) = previous_session {
        state.cancel_pending_for_session(&hello.node_id, previous_session);
        state
            .remove_tcp_control_for_session(&hello.node_id, previous_session)
            .await;
    }
    if let Some(connection) = connection {
        state
            .connections
            .lock()
            .await
            .insert(hello.node_id.clone(), connection);
    }
}

async fn mark_heartbeat(state: &ReverseTunnelServerState, heartbeat: &TunnelHeartbeat) {
    if !state
        .refresh_session_heartbeat(&heartbeat.node_id, heartbeat.session_id)
        .await
    {
        return;
    }
    let mut sessions = state.sessions.lock().await;
    if let Some(session) = sessions.get_mut(&heartbeat.node_id)
        && session.session_id == heartbeat.session_id
    {
        session.connected = true;
        session.last_heartbeat_sequence = Some(heartbeat.sequence);
    }
}

async fn mark_disconnected(state: &ReverseTunnelServerState, hello: &TunnelHello) {
    let mut sessions = state.sessions.lock().await;
    let mut remove_session_resources = false;
    if let Some(session) = sessions.get_mut(&hello.node_id)
        && session.session_id == hello.session_id
    {
        session.connected = false;
        remove_session_resources = true;
    }
    drop(sessions);
    if remove_session_resources {
        state.connections.lock().await.remove(&hello.node_id);
        state
            .remove_tcp_control_for_session(&hello.node_id, hello.session_id)
            .await;
        state
            .remove_session_liveness(&hello.node_id, hello.session_id)
            .await;
        state.cancel_pending_for_session(&hello.node_id, hello.session_id);
    }
}

async fn read_optional_line<R>(reader: &mut R) -> Result<Option<String>>
where
    R: AsyncBufRead + Unpin,
{
    let mut line = String::new();
    const MAX_LINE_LENGTH: usize = 1024 * 1024; // 1 MB limit
    let mut total_bytes = 0;

    loop {
        let buf = reader.fill_buf().await?;
        if buf.is_empty() {
            if total_bytes == 0 {
                return Ok(None);
            }
            break;
        }

        let mut found_newline = false;
        let mut chunk_len = 0;
        for &b in buf {
            chunk_len += 1;
            if b == b'\n' {
                found_newline = true;
                break;
            }
        }

        if total_bytes + chunk_len > MAX_LINE_LENGTH {
            bail!("line length limit exceeded");
        }

        let s = std::str::from_utf8(&buf[..chunk_len]).context("invalid utf8 sequence")?;
        line.push_str(s);
        total_bytes += chunk_len;

        reader.consume(chunk_len);

        if found_newline {
            break;
        }
    }

    Ok(Some(line))
}

async fn write_frame<W>(writer: &mut W, frame: &ClientFrame) -> Result<()>
where
    W: AsyncWrite + Unpin,
{
    let mut body = serde_json::to_vec(frame)?;
    body.push(b'\n');
    writer.write_all(&body).await?;
    writer.flush().await?;
    Ok(())
}

async fn write_server_frame<W>(writer: &mut W, frame: &ServerFrame) -> Result<()>
where
    W: AsyncWrite + Unpin,
{
    let mut body = serde_json::to_vec(frame)?;
    body.push(b'\n');
    writer.write_all(&body).await?;
    writer.flush().await?;
    Ok(())
}

async fn sleep_or_shutdown(duration: Duration, shutdown: &mut watch::Receiver<bool>) -> bool {
    tokio::select! {
        _ = sleep(duration) => false,
        _ = shutdown.changed() => true,
    }
}

async fn sleep_until(deadline: Instant) {
    sleep(deadline.saturating_duration_since(Instant::now())).await;
}

fn next_backoff(current: Duration, ceiling: Duration) -> Duration {
    (current * 2).min(ceiling)
}

#[cfg(test)]
mod tests {
    use std::net::UdpSocket;

    use tokio::sync::Mutex;

    use super::*;

    #[test]
    fn failover_observability_is_bounded_and_preserved_by_tls_fallback() {
        let mut snapshot = ClientSnapshot::new(Uuid::new_v4());
        mark_snapshot_connected(&mut snapshot, TunnelActiveTransport::Quic, false);
        let (status_tx, status_rx) = watch::channel(snapshot.clone());

        let reason = record_quic_failover(
            &mut snapshot,
            &anyhow::anyhow!("QUIC connect timed out"),
            &status_tx,
        );
        assert_eq!(reason, TunnelFailoverReason::ConnectTimeout);
        assert_eq!(
            snapshot
                .event_counters
                .failover_count(TunnelFailoverReason::ConnectTimeout),
            1
        );
        assert_eq!(
            status_rx.borrow().last_failover_reason,
            Some(TunnelFailoverReason::ConnectTimeout)
        );
        assert_eq!(status_rx.borrow().freshness, TunnelFreshness::Unknown);

        mark_snapshot_connected(&mut snapshot, TunnelActiveTransport::TlsTcp, true);
        assert_eq!(
            snapshot.last_failover_reason,
            Some(TunnelFailoverReason::ConnectTimeout)
        );
        assert_eq!(
            snapshot.active_transport,
            Some(TunnelActiveTransport::TlsTcp)
        );
        assert_eq!(snapshot.freshness, TunnelFreshness::Fresh);

        mark_snapshot_connected(&mut snapshot, TunnelActiveTransport::Quic, false);
        assert_eq!(snapshot.last_failover_reason, None);
    }

    #[test]
    fn failover_reason_never_exposes_raw_error_text() {
        assert_eq!(
            quic_failover_reason(&anyhow::anyhow!("credential=secret internal detail")),
            TunnelFailoverReason::SessionError
        );
        assert_eq!(
            quic_failover_reason(&anyhow::anyhow!("authentication rejected")),
            TunnelFailoverReason::AuthenticationFailed
        );
    }

    #[tokio::test]
    async fn client_reconnects_after_server_drops_connection() {
        let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
        let addr = listener.local_addr().unwrap();
        let received = Arc::new(Mutex::new(Vec::new()));
        let received_task = received.clone();
        let server = tokio::spawn(async move {
            for _ in 0..2 {
                let (stream, _) = listener.accept().await.unwrap();
                let mut reader = BufReader::new(stream);
                let mut line = String::new();
                reader.read_line(&mut line).await.unwrap();
                received_task.lock().await.push(line);
            }
        });

        let (shutdown_tx, shutdown_rx) = watch::channel(false);
        let (status_tx, status_rx) = watch::channel(ClientSnapshot::new(Uuid::nil()));
        let client = tokio::spawn(run_client(test_config(addr), shutdown_rx, status_tx));

        wait_for_attempts(status_rx.clone(), 2).await;
        shutdown_tx.send(true).unwrap();
        client.await.unwrap();
        server.await.unwrap();

        let final_snapshot = status_rx.borrow().clone();
        assert_eq!(
            final_snapshot
                .event_counters
                .connection_count(TunnelActiveTransport::Tcp),
            2
        );
        assert_eq!(final_snapshot.event_counters.reconnect_attempts(), 1);
        assert_eq!(final_snapshot.event_counters.reconnect_successes(), 1);

        let frames = received.lock().await;
        assert_eq!(frames.len(), 2);
        for raw in frames.iter() {
            let frame: ClientFrame = serde_json::from_str(raw).unwrap();
            assert!(matches!(frame, ClientFrame::Hello(_)));
        }
    }

    #[tokio::test]
    async fn client_resets_backoff_after_connected_session_drops() {
        let first_listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
        let addr = first_listener.local_addr().unwrap();
        let (shutdown_tx, shutdown_rx) = watch::channel(false);
        let (status_tx, status_rx) = watch::channel(ClientSnapshot::new(Uuid::nil()));
        let mut config = test_config(addr);
        config.reconnect_floor = Duration::from_millis(20);
        config.reconnect_ceiling = Duration::from_secs(5);
        let client = tokio::spawn(run_client(config, shutdown_rx, status_tx));

        let (first_stream, _) = first_listener.accept().await.unwrap();
        let mut reader = BufReader::new(first_stream);
        let mut line = String::new();
        reader.read_line(&mut line).await.unwrap();
        wait_for_connected(status_rx.clone()).await;
        drop(reader);
        drop(first_listener);

        sleep(Duration::from_millis(80)).await;
        let second_listener = TcpListener::bind(addr).await.unwrap();
        timeout(Duration::from_millis(500), second_listener.accept())
            .await
            .expect("client did not reconnect at floor backoff after connected drop")
            .unwrap();

        shutdown_tx.send(true).unwrap();
        client.await.unwrap();
    }

    async fn wait_for_connected(mut status: watch::Receiver<ClientSnapshot>) {
        timeout(Duration::from_secs(2), async move {
            loop {
                if status.borrow().connected {
                    return;
                }
                status.changed().await.unwrap();
            }
        })
        .await
        .unwrap();
    }

    #[tokio::test]
    async fn client_reconnects_after_vm_listener_restart() {
        let first_listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
        let addr = first_listener.local_addr().unwrap();
        let (shutdown_tx, shutdown_rx) = watch::channel(false);
        let (status_tx, status_rx) = watch::channel(ClientSnapshot::new(Uuid::nil()));
        let client = tokio::spawn(run_client(test_config(addr), shutdown_rx, status_tx));

        let (first_stream, _) = first_listener.accept().await.unwrap();
        drop(first_stream);
        drop(first_listener);

        wait_for_attempts(status_rx.clone(), 2).await;

        let second_listener = TcpListener::bind(addr).await.unwrap();
        let (second_stream, _) = second_listener.accept().await.unwrap();
        let mut reader = BufReader::new(second_stream);
        let mut line = String::new();
        reader.read_line(&mut line).await.unwrap();
        let frame: ClientFrame = serde_json::from_str(&line).unwrap();
        assert!(matches!(frame, ClientFrame::Hello(_)));

        shutdown_tx.send(true).unwrap();
        client.await.unwrap();
    }

    #[tokio::test]
    async fn client_preserves_session_identity_across_reconnects() {
        let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
        let addr = listener.local_addr().unwrap();
        let session_ids = Arc::new(Mutex::new(Vec::new()));
        let task_session_ids = session_ids.clone();
        let server = tokio::spawn(async move {
            for _ in 0..2 {
                let (stream, _) = listener.accept().await.unwrap();
                let mut reader = BufReader::new(stream);
                let mut line = String::new();
                reader.read_line(&mut line).await.unwrap();
                let frame: ClientFrame = serde_json::from_str(&line).unwrap();
                if let ClientFrame::Hello(hello) = frame {
                    task_session_ids.lock().await.push(hello.session_id);
                }
            }
        });

        let (shutdown_tx, shutdown_rx) = watch::channel(false);
        let (status_tx, status_rx) = watch::channel(ClientSnapshot::new(Uuid::nil()));
        let client = tokio::spawn(run_client(test_config(addr), shutdown_rx, status_tx));

        wait_for_attempts(status_rx, 2).await;
        shutdown_tx.send(true).unwrap();
        client.await.unwrap();
        server.await.unwrap();

        let session_ids = session_ids.lock().await;
        assert_eq!(session_ids.len(), 2);
        assert_eq!(session_ids[0], session_ids[1]);
    }

    #[tokio::test]
    async fn server_tracks_heartbeat_and_disconnect_state() {
        let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
        let addr = listener.local_addr().unwrap();
        let state = ReverseTunnelServerState::default();
        let (server_shutdown_tx, server_shutdown_rx) = watch::channel(false);
        let server = tokio::spawn(run_server(
            listener,
            test_server_config(),
            state.clone(),
            server_shutdown_rx,
        ));
        let (client_shutdown_tx, client_shutdown_rx) = watch::channel(false);
        let (status_tx, status_rx) = watch::channel(ClientSnapshot::new(Uuid::nil()));
        let client = tokio::spawn(run_client(test_config(addr), client_shutdown_rx, status_tx));

        wait_for_heartbeat_with_status(&state, status_rx.clone()).await;
        let client_snapshot = status_rx.borrow().clone();
        assert_eq!(
            client_snapshot.active_transport,
            Some(TunnelActiveTransport::Tcp)
        );
        assert_eq!(client_snapshot.freshness, TunnelFreshness::Fresh);
        assert_eq!(client_snapshot.last_failover_reason, None);
        assert_eq!(
            client_snapshot
                .event_counters
                .connection_count(TunnelActiveTransport::Tcp),
            1
        );
        assert_eq!(
            client_snapshot
                .event_counters
                .transition_count(TunnelTransportTransition::NoneToTcp),
            1
        );
        let sessions = state.snapshot().await;
        assert_eq!(sessions.len(), 1);
        assert!(sessions[0].connected);
        assert_eq!(sessions[0].accepted_connections, 1);
        assert!(sessions[0].last_heartbeat_sequence.unwrap_or_default() >= 1);

        client_shutdown_tx.send(true).unwrap();
        client.await.unwrap();
        wait_for_disconnected(&state).await;
        assert!(!state.snapshot().await[0].connected);

        server_shutdown_tx.send(true).unwrap();
        server.await.unwrap().unwrap();
        drop(status_rx);
    }

    #[tokio::test]
    async fn tcp_reverse_tunnel_forwards_proxy_bytes() {
        let proxy_listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
        let proxy_addr = proxy_listener.local_addr().unwrap();
        let proxy = tokio::spawn(async move {
            let (mut stream, _) = proxy_listener.accept().await.unwrap();
            let mut request = [0_u8; 4];
            stream.read_exact(&mut request).await.unwrap();
            assert_eq!(&request, b"ping");
            stream.write_all(b"pong").await.unwrap();
        });

        let server_listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
        let server_addr = server_listener.local_addr().unwrap();
        let state = ReverseTunnelServerState::default();
        let (server_shutdown_tx, server_shutdown_rx) = watch::channel(false);
        let server = tokio::spawn(run_server(
            server_listener,
            test_server_config(),
            state.clone(),
            server_shutdown_rx,
        ));
        let mut config = test_config(server_addr);
        config.local_proxy_addr = proxy_addr;
        let (client_shutdown_tx, client_shutdown_rx) = watch::channel(false);
        let (status_tx, status_rx) = watch::channel(ClientSnapshot::new(Uuid::nil()));
        let client = tokio::spawn(run_client(config, client_shutdown_rx, status_tx));
        wait_for_connected(status_rx).await;

        let forward_listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
        let forward_addr = forward_listener.local_addr().unwrap();
        let (forward_shutdown_tx, forward_shutdown_rx) = watch::channel(false);
        let forwarder = tokio::spawn(run_quic_tcp_forward_listener(
            forward_listener,
            state,
            Some("test-phone".into()),
            ProxyProtocol::Mixed,
            forward_shutdown_rx,
        ));
        timeout(Duration::from_secs(2), async {
            let mut stream = TcpStream::connect(forward_addr).await.unwrap();
            stream.write_all(b"ping").await.unwrap();
            let mut response = [0_u8; 4];
            stream.read_exact(&mut response).await.unwrap();
            assert_eq!(&response, b"pong");
        })
        .await
        .unwrap();

        forward_shutdown_tx.send(true).unwrap();
        client_shutdown_tx.send(true).unwrap();
        server_shutdown_tx.send(true).unwrap();
        forwarder.await.unwrap().unwrap();
        client.await.unwrap();
        server.await.unwrap().unwrap();
        proxy.await.unwrap();
    }

    #[tokio::test]
    async fn stale_disconnect_does_not_clear_newer_session() {
        let state = ReverseTunnelServerState::default();
        let old = TunnelHello {
            node_id: "test-phone".into(),
            session_id: Uuid::new_v4(),
            protocol_version: 1,
            auth_token: "test-token".into(),
        };
        let new = TunnelHello {
            node_id: old.node_id.clone(),
            session_id: Uuid::new_v4(),
            protocol_version: 1,
            auth_token: "test-token".into(),
        };

        mark_connected(&state, &old, None).await;
        mark_connected(&state, &new, None).await;
        mark_disconnected(&state, &old).await;

        let sessions = state.snapshot().await;
        assert_eq!(sessions.len(), 1);
        assert_eq!(sessions[0].session_id, new.session_id);
        assert!(sessions[0].connected);
    }

    #[tokio::test]
    async fn replacing_tcp_session_cancels_pending_proxy_request() {
        let state = ReverseTunnelServerState::default();
        let old = TunnelHello {
            node_id: "test-phone".into(),
            session_id: Uuid::new_v4(),
            protocol_version: 1,
            auth_token: "test-token".into(),
        };
        mark_connected(&state, &old, None).await;
        let (control_tx, mut control_rx) = mpsc::channel(1);
        state
            .register_tcp_control(old.node_id.clone(), old.session_id, control_tx)
            .await;

        let request_state = state.clone();
        let request =
            tokio::spawn(async move { request_state.open_tcp_proxy(Some("test-phone")).await });
        timeout(Duration::from_secs(1), control_rx.recv())
            .await
            .expect("pending request must reach the old control channel")
            .expect("old control channel must remain open");

        let new = TunnelHello {
            node_id: old.node_id.clone(),
            session_id: Uuid::new_v4(),
            protocol_version: 1,
            auth_token: "test-token".into(),
        };
        mark_connected(&state, &new, None).await;

        let error = timeout(Duration::from_secs(1), request)
            .await
            .expect("session replacement must cancel the pending request")
            .expect("request task must finish")
            .expect_err("old-session request must be cancelled");
        assert!(error.to_string().contains("cancelled"));
    }

    #[tokio::test]
    async fn server_rejects_wrong_auth_token() {
        let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
        let addr = listener.local_addr().unwrap();
        let state = ReverseTunnelServerState::default();
        let (server_shutdown_tx, server_shutdown_rx) = watch::channel(false);
        let server = tokio::spawn(run_server(
            listener,
            test_server_config(),
            state.clone(),
            server_shutdown_rx,
        ));
        let (client_shutdown_tx, client_shutdown_rx) = watch::channel(false);
        let (status_tx, status_rx) = watch::channel(ClientSnapshot::new(Uuid::nil()));
        let mut bad_config = test_config(addr);
        bad_config.auth_token = "wrong-token".into();
        let client = tokio::spawn(run_client(bad_config, client_shutdown_rx, status_tx));

        wait_for_attempts(status_rx, 2).await;
        assert!(state.snapshot().await.is_empty());

        client_shutdown_tx.send(true).unwrap();
        client.await.unwrap();
        server_shutdown_tx.send(true).unwrap();
        server.await.unwrap().unwrap();
    }

    #[tokio::test]
    async fn quic_server_tracks_heartbeat_and_disconnect_state() {
        let addr = unused_udp_addr();
        let identity = test_quic_identity();
        let state = ReverseTunnelServerState::default();
        let (server_shutdown_tx, server_shutdown_rx) = watch::channel(false);
        let server = tokio::spawn(run_quic_server(
            addr,
            test_quic_server_config(&identity),
            state.clone(),
            server_shutdown_rx,
        ));
        let (client_shutdown_tx, client_shutdown_rx) = watch::channel(false);
        let (status_tx, status_rx) = watch::channel(ClientSnapshot::new(Uuid::nil()));
        let client = tokio::spawn(run_client(
            test_quic_client_config(addr, &identity),
            client_shutdown_rx,
            status_tx,
        ));

        wait_for_heartbeat(&state).await;
        let client_snapshot = status_rx.borrow().clone();
        assert_eq!(
            client_snapshot.active_transport,
            Some(TunnelActiveTransport::Quic)
        );
        assert_eq!(client_snapshot.freshness, TunnelFreshness::Fresh);
        assert_eq!(client_snapshot.last_failover_reason, None);
        assert_eq!(
            client_snapshot
                .event_counters
                .connection_count(TunnelActiveTransport::Quic),
            1
        );
        assert_eq!(
            client_snapshot
                .event_counters
                .transition_count(TunnelTransportTransition::NoneToQuic),
            1
        );
        let sessions = state.snapshot().await;
        assert_eq!(sessions.len(), 1);
        assert!(sessions[0].connected);
        assert!(sessions[0].last_heartbeat_sequence.unwrap_or_default() >= 1);

        client_shutdown_tx.send(true).unwrap();
        client.await.unwrap();
        wait_for_disconnected(&state).await;
        assert!(!state.snapshot().await[0].connected);

        server_shutdown_tx.send(true).unwrap();
        server.await.unwrap().unwrap();
        drop(status_rx);
    }

    #[tokio::test]
    async fn quic_server_rejects_wrong_auth_token() {
        let addr = unused_udp_addr();
        let identity = test_quic_identity();
        let state = ReverseTunnelServerState::default();
        let (server_shutdown_tx, server_shutdown_rx) = watch::channel(false);
        let server = tokio::spawn(run_quic_server(
            addr,
            test_quic_server_config(&identity),
            state.clone(),
            server_shutdown_rx,
        ));
        let (client_shutdown_tx, client_shutdown_rx) = watch::channel(false);
        let (status_tx, status_rx) = watch::channel(ClientSnapshot::new(Uuid::nil()));
        let mut client_config = test_quic_client_config(addr, &identity);
        client_config.auth_token = "wrong-token".into();
        let client = tokio::spawn(run_client(client_config, client_shutdown_rx, status_tx));

        wait_for_attempts(status_rx, 2).await;
        assert!(state.snapshot().await.is_empty());

        client_shutdown_tx.send(true).unwrap();
        client.await.unwrap();
        server_shutdown_tx.send(true).unwrap();
        server.await.unwrap().unwrap();
    }

    #[tokio::test]
    async fn quic_reverse_tunnel_forwards_tcp_bytes_to_phone_proxy() {
        let proxy_listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
        let proxy_addr = proxy_listener.local_addr().unwrap();
        let proxy = tokio::spawn(async move {
            let (mut stream, _) = proxy_listener.accept().await.unwrap();
            let mut request = [0_u8; 4];
            stream.read_exact(&mut request).await.unwrap();
            assert_eq!(&request, b"ping");
            stream.write_all(b"pong").await.unwrap();
        });

        let quic_addr = unused_udp_addr();
        let identity = test_quic_identity();
        let state = ReverseTunnelServerState::default();
        let (server_shutdown_tx, server_shutdown_rx) = watch::channel(false);
        let server = tokio::spawn(run_quic_server(
            quic_addr,
            test_quic_server_config(&identity),
            state.clone(),
            server_shutdown_rx,
        ));

        let mut client_config = test_quic_client_config(quic_addr, &identity);
        client_config.local_proxy_addr = proxy_addr;
        let (client_shutdown_tx, client_shutdown_rx) = watch::channel(false);
        let (status_tx, status_rx) = watch::channel(ClientSnapshot::new(Uuid::nil()));
        let client = tokio::spawn(run_client(client_config, client_shutdown_rx, status_tx));
        wait_for_heartbeat(&state).await;

        let forward_listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
        let forward_addr = forward_listener.local_addr().unwrap();
        let (forward_shutdown_tx, forward_shutdown_rx) = watch::channel(false);
        let forwarder = tokio::spawn(run_quic_tcp_forward_listener(
            forward_listener,
            state.clone(),
            Some("test-phone".into()),
            ProxyProtocol::Mixed,
            forward_shutdown_rx,
        ));

        timeout(Duration::from_secs(2), async {
            let mut stream = TcpStream::connect(forward_addr).await.unwrap();
            stream.write_all(b"ping").await.unwrap();
            let mut response = [0_u8; 4];
            stream.read_exact(&mut response).await.unwrap();
            assert_eq!(&response, b"pong");
        })
        .await
        .unwrap();

        forward_shutdown_tx.send(true).unwrap();
        client_shutdown_tx.send(true).unwrap();
        server_shutdown_tx.send(true).unwrap();
        forwarder.await.unwrap().unwrap();
        client.await.unwrap();
        server.await.unwrap().unwrap();
        proxy.await.unwrap();
        drop(status_rx);
    }

    #[tokio::test]
    async fn forward_listener_fails_fast_when_phone_is_offline() {
        let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
        let addr = listener.local_addr().unwrap();
        let (_shutdown_tx, shutdown_rx) = watch::channel(false);
        let forwarder = tokio::spawn(run_quic_tcp_forward_listener(
            listener,
            ReverseTunnelServerState::default(),
            Some("offline-phone".into()),
            ProxyProtocol::Http,
            shutdown_rx,
        ));

        let response = timeout(Duration::from_secs(1), async {
            let mut stream = TcpStream::connect(addr).await.unwrap();
            stream
                .write_all(b"CONNECT example.com:443 HTTP/1.1\r\n\r\n")
                .await
                .unwrap();
            let mut response = Vec::new();
            stream.read_to_end(&mut response).await.unwrap();
            response
        })
        .await
        .unwrap();
        assert!(response.starts_with(b"HTTP/1.1 503 Service Unavailable"));
        forwarder.abort();
    }

    fn test_config(server_addr: SocketAddr) -> ReverseTunnelClientConfig {
        ReverseTunnelClientConfig {
            node_id: "test-phone".into(),
            server_addr,
            tcp_fallback_addr: None,
            local_proxy_addr: "127.0.0.1:9".parse().unwrap(),
            auth_token: "test-token".into(),
            transport: TunnelTransport::Tcp,
            connect_timeout: Duration::from_millis(100),
            heartbeat_interval: Duration::from_millis(20),
            reconnect_floor: Duration::from_millis(10),
            reconnect_ceiling: Duration::from_millis(50),
        }
    }

    fn test_server_config() -> ReverseTunnelServerConfig {
        ReverseTunnelServerConfig {
            auth_token: "test-token".into(),
            transport: TunnelTransport::Tcp,
        }
    }

    fn test_quic_client_config(
        server_addr: SocketAddr,
        identity: &TestQuicIdentity,
    ) -> ReverseTunnelClientConfig {
        ReverseTunnelClientConfig {
            node_id: "test-phone".into(),
            server_addr,
            tcp_fallback_addr: None,
            local_proxy_addr: "127.0.0.1:9".parse().unwrap(),
            auth_token: "test-token".into(),
            transport: TunnelTransport::Quic {
                server_name: "localhost".into(),
                server_cert_der: identity.cert_der.clone(),
                server_key_der: None,
            },
            connect_timeout: Duration::from_millis(500),
            heartbeat_interval: Duration::from_millis(20),
            reconnect_floor: Duration::from_millis(10),
            reconnect_ceiling: Duration::from_millis(50),
        }
    }

    fn test_quic_server_config(identity: &TestQuicIdentity) -> ReverseTunnelServerConfig {
        ReverseTunnelServerConfig {
            auth_token: "test-token".into(),
            transport: TunnelTransport::Quic {
                server_name: "localhost".into(),
                server_cert_der: identity.cert_der.clone(),
                server_key_der: Some(identity.key_der.clone()),
            },
        }
    }

    struct TestQuicIdentity {
        cert_der: Vec<u8>,
        key_der: Vec<u8>,
    }

    fn test_quic_identity() -> TestQuicIdentity {
        let certified = rcgen::generate_simple_self_signed(vec!["localhost".into()]).unwrap();
        TestQuicIdentity {
            cert_der: certified.cert.der().as_ref().to_vec(),
            key_der: certified.signing_key.serialize_der(),
        }
    }

    fn unused_udp_addr() -> SocketAddr {
        let socket = UdpSocket::bind("127.0.0.1:0").unwrap();
        socket.local_addr().unwrap()
    }

    async fn wait_for_attempts(mut status: watch::Receiver<ClientSnapshot>, attempts: u64) {
        timeout(Duration::from_secs(2), async move {
            loop {
                if status.borrow().attempts >= attempts {
                    return;
                }
                status.changed().await.unwrap();
            }
        })
        .await
        .unwrap();
    }

    async fn wait_for_heartbeat(state: &ReverseTunnelServerState) {
        timeout(Duration::from_secs(2), async {
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
        .unwrap();
    }

    async fn wait_for_heartbeat_with_status(
        state: &ReverseTunnelServerState,
        status: watch::Receiver<ClientSnapshot>,
    ) {
        if timeout(Duration::from_secs(2), async {
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
                "timed out waiting for reverse tunnel heartbeat; client={:?} server={:?}",
                status.borrow().clone(),
                state.snapshot().await
            );
        }
    }

    async fn wait_for_disconnected(state: &ReverseTunnelServerState) {
        timeout(Duration::from_secs(2), async {
            loop {
                if state
                    .snapshot()
                    .await
                    .first()
                    .is_some_and(|session| !session.connected)
                {
                    return;
                }
                sleep(Duration::from_millis(10)).await;
            }
        })
        .await
        .unwrap();
    }
}
