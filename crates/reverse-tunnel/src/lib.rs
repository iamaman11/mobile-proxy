use std::collections::HashMap;
use std::net::SocketAddr;
use std::sync::Arc;
use std::time::Duration;

use anyhow::{Context, Result, bail};
use serde::{Deserialize, Serialize};
use tokio::io::{AsyncBufRead, AsyncBufReadExt, AsyncWrite, AsyncWriteExt, BufReader};
use tokio::net::{TcpListener, TcpStream};
use tokio::sync::{Mutex, watch};
use tokio::time::{Instant, sleep, timeout};
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

#[derive(Debug, Clone)]
pub struct ReverseTunnelClientConfig {
    pub node_id: String,
    pub server_addr: SocketAddr,
    pub auth_token: String,
    pub connect_timeout: Duration,
    pub heartbeat_interval: Duration,
    pub reconnect_floor: Duration,
    pub reconnect_ceiling: Duration,
}

#[derive(Debug, Clone)]
pub struct ReverseTunnelServerConfig {
    pub auth_token: String,
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
}

impl ReverseTunnelServerState {
    pub async fn snapshot(&self) -> Vec<ServerSessionSnapshot> {
        let mut sessions: Vec<_> = self.sessions.lock().await.values().cloned().collect();
        sessions.sort_by(|left, right| left.node_id.cmp(&right.node_id));
        sessions
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
                    let _ = handle_server_connection(stream, config, state).await;
                });
            }
        }
    }
}

async fn connect_and_pump(
    config: &ReverseTunnelClientConfig,
    session_id: Uuid,
    shutdown: &mut watch::Receiver<bool>,
    snapshot: &mut ClientSnapshot,
) -> Result<()> {
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
    mark_connected(&state, &hello).await;

    loop {
        match read_optional_frame(&mut reader).await? {
            Some(ClientFrame::Heartbeat(heartbeat)) => {
                mark_heartbeat(&state, &heartbeat).await;
            }
            Some(ClientFrame::Hello(_)) => {
                bail!("unexpected repeated hello on reverse tunnel session");
            }
            None => {
                mark_disconnected(&state, &hello).await;
                return Ok(());
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

async fn mark_connected(state: &ReverseTunnelServerState, hello: &TunnelHello) {
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

        wait_for_heartbeat(&state).await;
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

    fn test_config(server_addr: SocketAddr) -> ReverseTunnelClientConfig {
        ReverseTunnelClientConfig {
            node_id: "test-phone".into(),
            server_addr,
            auth_token: "test-token".into(),
            connect_timeout: Duration::from_millis(100),
            heartbeat_interval: Duration::from_millis(20),
            reconnect_floor: Duration::from_millis(10),
            reconnect_ceiling: Duration::from_millis(50),
        }
    }

    fn test_server_config() -> ReverseTunnelServerConfig {
        ReverseTunnelServerConfig {
            auth_token: "test-token".into(),
        }
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
