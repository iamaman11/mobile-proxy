mod cli;

use std::collections::HashSet;
use std::net::SocketAddr;

use anyhow::{Context, Result, bail};
use clap::Parser;
use reverse_tunnel::{
    ProxyProtocol, ReverseTunnelServerConfig, ReverseTunnelServerState, TunnelTransport,
    decode_der_base64, run_quic_server, run_quic_tcp_forward_listener, run_server,
};
use tokio::net::TcpListener;
use tokio::sync::watch;
use tokio::task::JoinSet;
use tracing::info;

use crate::cli::Cli;

const MAX_PUBLIC_PROXY_LISTENERS: usize = 8;

#[tokio::main]
async fn main() -> Result<()> {
    tracing_subscriber::fmt::init();
    let cli = Cli::parse();
    let validated = validate_cli(&cli)?;
    let transport = TunnelTransport::Hybrid {
        server_name: cli.server_name,
        server_cert_der: decode_der_base64(&cli.cert_der_b64)?,
        server_key_der: Some(decode_der_base64(&cli.key_der_b64)?),
    };
    let server_config = ReverseTunnelServerConfig {
        auth_token: cli.auth_token,
        transport: transport.clone(),
    };
    let state = ReverseTunnelServerState::default();
    let (_shutdown_tx, shutdown_rx) = watch::channel(false);

    let mut public_proxy_listeners = Vec::new();
    for listen in &validated.public_proxy_listens {
        public_proxy_listeners.push((*listen, TcpListener::bind(listen).await?));
    }
    info!(
        "reverse-tunnel-server QUIC listening on {}; pinned TLS/TCP reserve backend on {}; public proxy listeners on {}",
        validated.quic_listen,
        validated.tcp_listen,
        validated
            .public_proxy_listens
            .iter()
            .map(SocketAddr::to_string)
            .collect::<Vec<_>>()
            .join(",")
    );

    let mut tasks = JoinSet::new();
    tasks.spawn(run_server(
        TcpListener::bind(validated.tcp_listen).await?,
        ReverseTunnelServerConfig {
            auth_token: server_config.auth_token.clone(),
            transport: TunnelTransport::Tcp,
        },
        state.clone(),
        shutdown_rx.clone(),
    ));
    tasks.spawn(run_quic_server(
        validated.quic_listen,
        server_config,
        state.clone(),
        shutdown_rx.clone(),
    ));

    for (listen, listener) in public_proxy_listeners {
        let protocol = match listen.port() {
            14081 => ProxyProtocol::Socks5,
            14128 => ProxyProtocol::Http,
            _ => ProxyProtocol::Mixed,
        };
        tasks.spawn(run_quic_tcp_forward_listener(
            listener,
            state.clone(),
            validated.target_node_id.clone(),
            protocol,
            shutdown_rx.clone(),
        ));
    }
    while let Some(result) = tasks.join_next().await {
        result??;
    }
    Ok(())
}

struct ValidatedCli {
    quic_listen: SocketAddr,
    tcp_listen: SocketAddr,
    public_proxy_listens: Vec<SocketAddr>,
    target_node_id: Option<String>,
}

fn validate_cli(cli: &Cli) -> Result<ValidatedCli> {
    if cli.transport != "hybrid" {
        bail!("production reverse-tunnel server transport must be hybrid")
    }
    validate_secret("reverse tunnel auth token", &cli.auth_token)?;
    validate_identifier("server name", &cli.server_name, 253)?;
    if cli.cert_der_b64.len() < 16 || cli.cert_der_b64.len() > 65_536 {
        bail!("reverse tunnel certificate value is invalid")
    }
    if cli.key_der_b64.len() < 16 || cli.key_der_b64.len() > 65_536 {
        bail!("reverse tunnel private key value is invalid")
    }

    let quic_listen: SocketAddr = cli.listen.parse().context("QUIC listen address is invalid")?;
    if quic_listen.ip().is_loopback() || quic_listen.ip().is_unspecified() {
        // An unspecified address is intentional for the public QUIC ingress.
    } else if quic_listen.ip().is_multicast() {
        bail!("QUIC listen address is invalid")
    }
    let tcp_listen: SocketAddr = cli
        .tcp_listen
        .parse()
        .context("TLS/TCP reserve backend address is invalid")?;
    if !tcp_listen.ip().is_loopback() {
        bail!("TLS/TCP reserve backend must bind to loopback behind the TLS terminator")
    }

    let public_proxy_listens = parse_public_proxy_listens(&cli.public_proxy_listen)?;
    let target_node_id = cli
        .target_node_id
        .as_deref()
        .map(|value| {
            validate_identifier("target node ID", value, 64)?;
            Ok(value.to_string())
        })
        .transpose()?;

    Ok(ValidatedCli {
        quic_listen,
        tcp_listen,
        public_proxy_listens,
        target_node_id,
    })
}

fn parse_public_proxy_listens(raw: &str) -> Result<Vec<SocketAddr>> {
    let values: Vec<_> = raw
        .split(',')
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .collect();
    if values.is_empty() || values.len() > MAX_PUBLIC_PROXY_LISTENERS {
        bail!("public proxy listener inventory is invalid")
    }
    let mut unique = HashSet::new();
    let mut parsed = Vec::with_capacity(values.len());
    for value in values {
        let listen: SocketAddr = value.parse().context("public proxy listen address is invalid")?;
        if !listen.ip().is_loopback() {
            bail!("reverse-tunnel public proxy backends must bind to loopback")
        }
        if !unique.insert(listen) {
            bail!("public proxy listener inventory contains duplicates")
        }
        parsed.push(listen);
    }
    Ok(parsed)
}

fn validate_secret(field: &str, value: &str) -> Result<()> {
    if value.len() < 16 || value.len() > 4096 || value.chars().any(char::is_control) {
        bail!("{field} is invalid")
    }
    Ok(())
}

fn validate_identifier(field: &str, value: &str, maximum: usize) -> Result<()> {
    if value.is_empty()
        || value.len() > maximum
        || !value.chars().all(|character| {
            character.is_ascii_alphanumeric() || matches!(character, '-' | '_' | '.' | ':')
        })
    {
        bail!("{field} is invalid")
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::parse_public_proxy_listens;

    #[test]
    fn public_proxy_backends_are_bounded_unique_and_loopback_only() {
        assert!(
            parse_public_proxy_listens(
                "127.0.0.1:14080,127.0.0.1:14081,127.0.0.1:14128"
            )
            .is_ok()
        );
        assert!(parse_public_proxy_listens("0.0.0.0:14080").is_err());
        assert!(parse_public_proxy_listens("127.0.0.1:14080,127.0.0.1:14080").is_err());
        assert!(parse_public_proxy_listens("").is_err());
    }
}
