use std::collections::HashMap;
use std::net::SocketAddr;
use std::sync::Arc;
use std::time::Duration;

use anyhow::{Context, Result, bail};
use base64::Engine;
use quinn::{ClientConfig, Endpoint, ServerConfig, TransportConfig};
use rustls::RootCertStore;
use rustls_pki_types::{CertificateDer, PrivatePkcs8KeyDer};
use serde::{Deserialize, Serialize};
use tokio::io::{
    AsyncBufRead, AsyncBufReadExt, AsyncRead, AsyncReadExt, AsyncWrite, AsyncWriteExt, BufReader,
};
use tokio::net::{TcpListener, TcpStream};
use tokio::sync::{Mutex, watch};
use tokio::time::{Instant, sleep, timeout};
use tracing::{debug, info, warn};
use uuid::Uuid;

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct TunnelHello {
    pub node_id: String,
    pub session_id: Uuid,
    pub protocol_version: u16,
    pub auth_token: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct TunnelHeartbeat {
    pub node_id: String,
    pub session_id: Uuid,
    pub sequence: u64,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(tag = "type")]
pub enum ClientFrame {
    Hello(TunnelHello),
    Heartbeat(TunnelHeartbeat),
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(tag = "type")]
pub enum ServerFrame {
    OpenProxy { stream_id: Uuid },
}

#[derive(Debug, Clone)]
pub struct ReverseTunnelClientConfig {
    pub node_id: String,
    pub server_addr: SocketAddr,
    pub local_proxy_addr: SocketAddr,
    pub auth_token: String,
    pub transport: TunnelTransport,
    pub connect_timeout: Duration,
    pub heartbeat_interval: Duration,
    pub reconnect_floor: Duration,
    pub reconnect_ceiling: Duration,
}

#[derive(Debug, Clone)]
pub struct ReverseTunnelServerConfig {
    pub auth_token: String,
    pub transport: TunnelTransport,
}

#[derive(Debug, Clone)]
pub enum TunnelTransport {
    Tcp,
    Quic {
        server_name: String,
        server_cert_der: Vec<u8>,
        server_key_der: Option<Vec<u8>>,
    },
}

pub fn decode_der_base64(raw: &str) -> Result<Vec<u8>> {
    base64::engine::general_purpose::STANDARD
        .decode(raw.trim())
        .context("failed to decode base64 DER")
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ClientSnapshot {
    pub session_id: Uuid,
    pub connected: bool,
    pub attempts: u64,
    pub sent_heartbeats: u64,
    pub last_error: Option<String>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ServerSessionSnapshot {
    pub node_id: String,
    pub session_id: Uuid,
    pub connected: bool,
    pub accepted_connections: u64,
    pub last_heartbeat_sequence: Option<u64>,
}

#[derive(Debug, Clone, Default)]
pub struct ReverseTunnelServerState {
    sessions: Arc<Mutex<HashMap<String, ServerSessionSnapshot>>>,
    connections: Arc<Mutex<HashMap<String, quinn::Connection>>>,
}

impl ReverseTunnelServerState {
    pub async fn snapshot(&self) -> Vec<ServerSessionSnapshot> {
        let mut sessions: Vec<_> = self.sessions.lock().await.values().cloned().collect();
        sessions.sort_by(|left, right| left.node_id.cmp(&right.node_id));
        sessions
    }

    pub async fn active_connection(&self, node_id: Option<&str>) -> Option<quinn::Connection> {
        let sessions = self.sessions.lock().await;
        let selected_node = if let Some(node_id) = node_id {
            sessions
                .get(node_id)
                .filter(|session| session.connected)
                .map(|session| session.node_id.clone())
        } else {
            sessions
                .values()
                .find(|session| session.connected)
                .map(|session| session.node_id.clone())
        }?;
        drop(sessions);
        self.connections.lock().await.get(&selected_node).cloned()
    }
}

impl ClientSnapshot {
    fn new(session_id: Uuid) -> Self {
        Self {
            session_id,
            connected: false,
            attempts: 0,
            sent_heartbeats: 0,
            last_error: None,
        }
    }
}

pub async fn run_client(
    config: ReverseTunnelClientConfig,
    mut shutdown: watch::Receiver<bool>,
    status: watch::Sender<ClientSnapshot>,
) {
    let session_id = Uuid::new_v4();
    let mut snapshot = ClientSnapshot::new(session_id);
    let mut backoff = config.reconnect_floor;

    loop {
        if *shutdown.borrow() {
            let _ = status.send(snapshot);
            return;
        }

        snapshot.connected = false;
        snapshot.attempts += 1;
        let _ = status.send(snapshot.clone());

        match connect_and_pump(&config, session_id, &mut shutdown, &mut snapshot).await {
            Ok(()) => {
                snapshot.connected = false;
                snapshot.last_error = None;
                backoff = config.reconnect_floor;
            }
            Err(err) => {
                snapshot.connected = false;
                snapshot.last_error = Some(err.to_string());
                let _ = status.send(snapshot.clone());
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
            _ = shutdown.changed() => return Ok(()),
            accepted = listener.accept() => {
                let (stream, _) = accepted.context("reverse tunnel accept failed")?;
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
    let TunnelTransport::Quic {
        server_cert_der, ..
    } = &config.transport
    else {
        bail!("run_quic_server requires TunnelTransport::Quic");
    };
    let key = quic_server_key(&config.transport)?;
    let mut server_config = ServerConfig::with_single_cert(
        vec![CertificateDer::from(server_cert_der.clone())],
        key.into(),
    )
    .context("failed to create QUIC server config")?;
    Arc::get_mut(&mut server_config.transport)
        .context("QUIC transport config is unexpectedly shared")?
        .max_concurrent_bidi_streams(256_u16.into())
        .max_concurrent_uni_streams(0_u8.into());
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
    mut shutdown: watch::Receiver<bool>,
) -> Result<()> {
    loop {
        tokio::select! {
            _ = shutdown.changed() => return Ok(()),
            accepted = listener.accept() => {
                let (stream, _) = accepted.context("reverse tunnel TCP forward accept failed")?;
                let state = state.clone();
                let target_node_id = target_node_id.clone();
                tokio::spawn(async move {
                    if let Err(err) = forward_tcp_over_quic(stream, state, target_node_id.as_deref()).await {
                        warn!(error = %err, "reverse tunnel TCP forward failed");
                    }
                });
            }
        }
    }
}

async fn forward_tcp_over_quic(
    tcp_stream: TcpStream,
    state: ReverseTunnelServerState,
    target_node_id: Option<&str>,
) -> Result<()> {
    let connection = state
        .active_connection(target_node_id)
        .await
        .context("no authenticated reverse tunnel connection is active")?;
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
) -> Result<()> {
    if matches!(config.transport, TunnelTransport::Quic { .. }) {
        return connect_and_pump_quic(config, session_id, shutdown, snapshot).await;
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

    snapshot.connected = true;
    snapshot.last_error = None;
    let mut sequence = snapshot.sent_heartbeats;

    loop {
        let deadline = Instant::now() + config.heartbeat_interval;
        tokio::select! {
            _ = shutdown.changed() => {
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
                write_frame(&mut writer, &ClientFrame::Heartbeat(TunnelHeartbeat {
                    node_id: config.node_id.clone(),
                    session_id,
                    sequence,
                })).await?;
                snapshot.sent_heartbeats = sequence;
            }
        }
    }
}

async fn connect_and_pump_quic(
    config: &ReverseTunnelClientConfig,
    session_id: Uuid,
    shutdown: &mut watch::Receiver<bool>,
    snapshot: &mut ClientSnapshot,
) -> Result<()> {
    let TunnelTransport::Quic {
        server_name,
        server_cert_der,
        ..
    } = &config.transport
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

    snapshot.connected = true;
    snapshot.last_error = None;
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
    if hello.auth_token != config.auth_token {
        bail!("reverse tunnel authentication failed");
    }
    info!(node_id = %hello.node_id, session_id = %hello.session_id, "reverse tunnel authenticated");
    mark_connected(&state, &hello, Some(connection)).await;

    loop {
        match read_optional_frame(&mut reader).await {
            Ok(Some(ClientFrame::Heartbeat(heartbeat))) => {
                mark_heartbeat(&state, &heartbeat).await;
            }
            Ok(Some(ClientFrame::Hello(_))) => {
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
    let mut config = ClientConfig::with_root_certificates(Arc::new(roots))?;
    let mut transport = TransportConfig::default();
    transport
        .max_concurrent_bidi_streams(256_u16.into())
        .max_concurrent_uni_streams(0_u8.into());
    config.transport_config(Arc::new(transport));
    Ok(config)
}

fn quic_server_key(transport: &TunnelTransport) -> Result<PrivatePkcs8KeyDer<'static>> {
    let TunnelTransport::Quic { server_key_der, .. } = transport else {
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
    stream: TcpStream,
    config: ReverseTunnelServerConfig,
    state: ReverseTunnelServerState,
) -> Result<()> {
    let mut reader = BufReader::new(stream);
    let first = read_required_frame(&mut reader).await?;
    let ClientFrame::Hello(hello) = first else {
        bail!("reverse tunnel connection did not start with hello");
    };
    if hello.auth_token != config.auth_token {
        bail!("reverse tunnel authentication failed");
    }
    mark_connected(&state, &hello, None).await;

    loop {
        match read_optional_frame(&mut reader).await {
            Ok(Some(ClientFrame::Heartbeat(heartbeat))) => {
                mark_heartbeat(&state, &heartbeat).await;
            }
            Ok(Some(ClientFrame::Hello(_))) => {
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
    let mut sessions = state.sessions.lock().await;
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
    if let Some(connection) = connection {
        state
            .connections
            .lock()
            .await
            .insert(hello.node_id.clone(), connection);
    }
}

async fn mark_heartbeat(state: &ReverseTunnelServerState, heartbeat: &TunnelHeartbeat) {
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
    if let Some(session) = sessions.get_mut(&hello.node_id)
        && session.session_id == hello.session_id
    {
        session.connected = false;
    }
    drop(sessions);
    state.connections.lock().await.remove(&hello.node_id);
}

async fn read_optional_line<R>(reader: &mut R) -> Result<Option<String>>
where
    R: AsyncBufRead + Unpin,
{
    let mut line = String::new();
    let bytes = reader.read_line(&mut line).await?;
    if bytes == 0 {
        return Ok(None);
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

        let frames = received.lock().await;
        assert_eq!(frames.len(), 2);
        for raw in frames.iter() {
            let frame: ClientFrame = serde_json::from_str(raw).unwrap();
            assert!(matches!(frame, ClientFrame::Hello(_)));
        }
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

    fn test_config(server_addr: SocketAddr) -> ReverseTunnelClientConfig {
        ReverseTunnelClientConfig {
            node_id: "test-phone".into(),
            server_addr,
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
