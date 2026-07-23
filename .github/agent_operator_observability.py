from pathlib import Path
import subprocess


def replace_once(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text()
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{path}: expected exactly one match, found {count}")
    file.write_text(text.replace(old, new, 1))


replace_once(
    "apps/operator-cli/src/cli.rs",
    "use clap::{Args, Parser, Subcommand};",
    "use clap::{Args, Parser, Subcommand, ValueEnum};",
)
replace_once(
    "apps/operator-cli/src/cli.rs",
    '''pub enum Command {
    Status,
    Proxy,
''',
    '''pub enum Command {
    Status(StatusArgs),
    Metrics,
    Proxy,
''',
)
replace_once(
    "apps/operator-cli/src/cli.rs",
    '''#[derive(Args, Debug, Clone)]
pub struct GenerateReverseTunnelIdentityArgs {
''',
    '''#[derive(Args, Debug, Clone)]
pub struct StatusArgs {
    #[arg(long, value_enum, default_value_t = StatusFormat::Json)]
    pub format: StatusFormat,
}

#[derive(ValueEnum, Debug, Clone, Copy, PartialEq, Eq)]
pub enum StatusFormat {
    Json,
    Summary,
}

#[derive(Args, Debug, Clone)]
pub struct GenerateReverseTunnelIdentityArgs {
''',
)
replace_once(
    "apps/operator-cli/src/cli.rs",
    '''pub struct RollbackDeviceArgs {
    #[arg(long)]
    pub manifest_path: String,
    #[arg(long)]
    pub release_id: Option<String>,
    #[arg(long)]
    pub device_serial: Option<String>,
    #[arg(long, default_value = "/data/adb/mobile-proxy-node")]
    pub device_root: String,
    #[arg(long, default_value_t = 18088)]
    pub health_port: u16,
}
''',
    '''pub struct RollbackDeviceArgs {
    #[arg(long)]
    pub manifest_path: String,
    #[arg(long)]
    pub release_id: Option<String>,
    #[arg(long)]
    pub device_serial: Option<String>,
    #[arg(long, default_value = "/data/adb/mobile-proxy-node")]
    pub device_root: String,
    #[arg(long, default_value_t = 18088)]
    pub health_port: u16,
}

#[cfg(test)]
mod tests {
    use clap::Parser;

    use super::{Cli, Command, StatusFormat};

    #[test]
    fn status_preserves_json_as_the_default_output() {
        let cli = Cli::try_parse_from(["operator-cli", "status"]).unwrap();
        let Command::Status(args) = cli.command else {
            panic!("status command must parse");
        };
        assert_eq!(args.format, StatusFormat::Json);
    }

    #[test]
    fn status_summary_and_metrics_are_explicit_operator_surfaces() {
        let cli = Cli::try_parse_from(["operator-cli", "status", "--format", "summary"]).unwrap();
        let Command::Status(args) = cli.command else {
            panic!("status command must parse");
        };
        assert_eq!(args.format, StatusFormat::Summary);

        let metrics = Cli::try_parse_from(["operator-cli", "metrics"]).unwrap();
        assert!(matches!(metrics.command, Command::Metrics));
    }
}
''',
)

replace_once(
    "apps/operator-cli/src/main.rs",
    "use crate::commands::{run_airplane_study, run_proxy, run_rotate, run_status};",
    "use crate::commands::{run_airplane_study, run_metrics, run_proxy, run_rotate, run_status};",
)
replace_once(
    "apps/operator-cli/src/main.rs",
    '''        Command::Status => {
            let token = resolve_token(cli.token.as_deref())?;
            run_status(&client, &cli.api, &token).await?
        }
        Command::Proxy => run_proxy()?,
''',
    '''        Command::Status(args) => {
            let token = resolve_token(cli.token.as_deref())?;
            run_status(&client, &cli.api, &token, &args).await?
        }
        Command::Metrics => {
            let token = resolve_token(cli.token.as_deref())?;
            run_metrics(&client, &cli.api, &token).await?
        }
        Command::Proxy => run_proxy()?,
''',
)

replace_once(
    "apps/operator-cli/src/http.rs",
    '''pub async fn fetch_health(
    client: &reqwest::Client,
    api: &str,
    token: &str,
) -> Result<HealthRecord> {
''',
    '''pub async fn fetch_metrics(client: &reqwest::Client, api: &str, token: &str) -> Result<String> {
    Ok(client
        .get(format!("{}/v1/metrics", api))
        .headers(auth_headers(token)?)
        .send()
        .await?
        .error_for_status()?
        .text()
        .await?)
}

pub async fn fetch_health(
    client: &reqwest::Client,
    api: &str,
    token: &str,
) -> Result<HealthRecord> {
''',
)

replace_once(
    "apps/operator-cli/src/commands.rs",
    "use crate::cli::{AirplaneStudyArgs, RotateArgs};",
    "use crate::cli::{AirplaneStudyArgs, RotateArgs, StatusArgs, StatusFormat};",
)
replace_once(
    "apps/operator-cli/src/commands.rs",
    "use crate::http::{fetch_health, issue_rotation, wait_for_rotation};",
    "use crate::http::{fetch_health, fetch_metrics, issue_rotation, wait_for_rotation};",
)
replace_once(
    "apps/operator-cli/src/commands.rs",
    '''pub async fn run_status(client: &reqwest::Client, api: &str, token: &str) -> Result<()> {
    let health = fetch_health(client, api, token).await?;
    println!("{}", serde_json::to_string_pretty(&health)?);
    Ok(())
}
''',
    '''pub async fn run_status(
    client: &reqwest::Client,
    api: &str,
    token: &str,
    args: &StatusArgs,
) -> Result<()> {
    let health = fetch_health(client, api, token).await?;
    println!("{}", render_status(&health, args.format)?);
    Ok(())
}

pub async fn run_metrics(client: &reqwest::Client, api: &str, token: &str) -> Result<()> {
    let metrics = fetch_metrics(client, api, token).await?;
    print!("{metrics}");
    Ok(())
}

fn render_status(health: &HealthRecord, format: StatusFormat) -> Result<String> {
    match format {
        StatusFormat::Json => Ok(serde_json::to_string_pretty(health)?),
        StatusFormat::Summary => Ok(render_status_summary(health)),
    }
}

fn render_status_summary(health: &HealthRecord) -> String {
    format!(
        "node={} readiness={} serving={} proxy={} public_ip={}\ntunnel_owner={} connected={} transport={} freshness={} failover_reason={}",
        health.node_id,
        health.readiness_state,
        health.serving,
        health.proxy_status,
        health.last_public_ip.as_deref().unwrap_or("unknown"),
        health.tunnel_owner.as_deref().unwrap_or("unknown"),
        health.reverse_tunnel_connected.unwrap_or(false),
        health
            .reverse_tunnel_active_transport
            .as_deref()
            .unwrap_or("none"),
        health
            .reverse_tunnel_freshness
            .as_deref()
            .unwrap_or("unknown"),
        health
            .reverse_tunnel_failover_reason
            .as_deref()
            .unwrap_or("none"),
    )
}
''',
)
replace_once(
    "apps/operator-cli/src/commands.rs",
    "    use super::{build_rotate_request, is_successful_rotation};",
    "    use super::{build_rotate_request, is_successful_rotation, render_status};",
)
replace_once(
    "apps/operator-cli/src/commands.rs",
    "    use crate::cli::RotateArgs;",
    "    use crate::cli::{RotateArgs, StatusFormat};",
)
replace_once(
    "apps/operator-cli/src/commands.rs",
    '''        assert!(is_successful_rotation(&job, &health, true));

        let mut unhealthy = health.clone();
''',
    '''        assert!(is_successful_rotation(&job, &health, true));

        let mut tunnel_health = health.clone();
        tunnel_health.reverse_tunnel_connected = Some(true);
        tunnel_health.reverse_tunnel_active_transport = Some("tls_tcp".into());
        tunnel_health.reverse_tunnel_freshness = Some("fresh".into());
        tunnel_health.reverse_tunnel_failover_reason = Some("connect_timeout".into());
        tunnel_health.reverse_tunnel_last_error = Some("credential=secret raw error".into());
        let summary = render_status(&tunnel_health, StatusFormat::Summary).unwrap();
        assert!(summary.contains("connected=true transport=tls_tcp freshness=fresh"));
        assert!(summary.contains("failover_reason=connect_timeout"));
        assert!(!summary.contains("credential=secret"));
        let json = render_status(&tunnel_health, StatusFormat::Json).unwrap();
        assert!(json.contains("reverse_tunnel_active_transport"));

        let mut unhealthy = health.clone();
''',
)

replace_once(
    "services/host-daemon/src/api.rs",
    "use axum::{\n",
    "use std::fmt::Write as _;\n\nuse axum::{\n",
)
replace_once(
    "services/host-daemon/src/api.rs",
    '''    http::HeaderMap,
    routing::{get, post},
''',
    '''    http::{HeaderMap, header::CONTENT_TYPE},
    response::IntoResponse,
    routing::{get, post},
''',
)
replace_once(
    "services/host-daemon/src/api.rs",
    '''        .route("/v1/health", get(get_health))
        .route("/v1/status", get(get_status))
''',
    '''        .route("/v1/health", get(get_health))
        .route("/v1/metrics", get(get_metrics))
        .route("/v1/status", get(get_status))
''',
)
replace_once(
    "services/host-daemon/src/api.rs",
    '''async fn get_status(
''',
    '''async fn get_metrics(
    State(state): State<AppState>,
    headers: HeaderMap,
) -> Result<impl IntoResponse, ApiError> {
    authorize(&headers, &state.admin_token)?;
    let runtime = state.runtime.lock().await;
    let body = render_reverse_tunnel_metrics(
        runtime.health.reverse_tunnel_connected,
        runtime.health.reverse_tunnel_active_transport.as_deref(),
        runtime.health.reverse_tunnel_freshness.as_deref(),
        runtime.health.reverse_tunnel_failover_reason.as_deref(),
    );
    Ok((
        [(CONTENT_TYPE, "text/plain; version=0.0.4; charset=utf-8")],
        body,
    ))
}

fn render_reverse_tunnel_metrics(
    connected: Option<bool>,
    active_transport: Option<&str>,
    freshness: Option<&str>,
    failover_reason: Option<&str>,
) -> String {
    const TRANSPORTS: &[&str] = &["tcp", "quic", "tls_tcp"];
    const FRESHNESS: &[&str] = &["unknown", "fresh", "stale"];
    const FAILOVER_REASONS: &[&str] = &[
        "connect_timeout",
        "connect_failed",
        "authentication_failed",
        "session_closed",
        "session_error",
    ];

    let mut output = String::new();
    writeln!(output, "# TYPE mobile_proxy_reverse_tunnel_connected gauge").unwrap();
    writeln!(
        output,
        "mobile_proxy_reverse_tunnel_connected {}",
        u8::from(connected == Some(true))
    )
    .unwrap();
    writeln!(output, "# TYPE mobile_proxy_reverse_tunnel_active_transport gauge").unwrap();
    for transport in TRANSPORTS {
        writeln!(
            output,
            "mobile_proxy_reverse_tunnel_active_transport{{transport=\"{transport}\"}} {}",
            u8::from(active_transport == Some(*transport))
        )
        .unwrap();
    }
    writeln!(output, "# TYPE mobile_proxy_reverse_tunnel_freshness gauge").unwrap();
    for state in FRESHNESS {
        writeln!(
            output,
            "mobile_proxy_reverse_tunnel_freshness{{state=\"{state}\"}} {}",
            u8::from(freshness == Some(*state))
        )
        .unwrap();
    }
    writeln!(
        output,
        "# TYPE mobile_proxy_reverse_tunnel_last_failover_reason gauge"
    )
    .unwrap();
    for reason in FAILOVER_REASONS {
        writeln!(
            output,
            "mobile_proxy_reverse_tunnel_last_failover_reason{{reason=\"{reason}\"}} {}",
            u8::from(failover_reason == Some(*reason))
        )
        .unwrap();
    }
    output
}

async fn get_status(
''',
)
replace_once(
    "services/host-daemon/src/api.rs",
    '''async fn get_job(
    State(state): State<AppState>,
    headers: HeaderMap,
    Path(id): Path<Uuid>,
) -> Result<Json<JobRecord>, ApiError> {
    authorize(&headers, &state.admin_token)?;
    let runtime = state.runtime.lock().await;
    let job = runtime
        .jobs
        .get(&id)
        .cloned()
        .ok_or_else(|| ApiError(axum::http::StatusCode::NOT_FOUND, "job not found".into()))?;
    Ok(Json(job))
}
''',
    '''async fn get_job(
    State(state): State<AppState>,
    headers: HeaderMap,
    Path(id): Path<Uuid>,
) -> Result<Json<JobRecord>, ApiError> {
    authorize(&headers, &state.admin_token)?;
    let runtime = state.runtime.lock().await;
    let job = runtime
        .jobs
        .get(&id)
        .cloned()
        .ok_or_else(|| ApiError(axum::http::StatusCode::NOT_FOUND, "job not found".into()))?;
    Ok(Json(job))
}

#[cfg(test)]
mod tests {
    use super::render_reverse_tunnel_metrics;

    #[test]
    fn tunnel_metrics_have_fixed_cardinality_and_no_raw_labels() {
        let metrics = render_reverse_tunnel_metrics(
            Some(true),
            Some("tls_tcp"),
            Some("fresh"),
            Some("connect_timeout"),
        );
        assert!(metrics.contains(
            "mobile_proxy_reverse_tunnel_active_transport{transport=\"tls_tcp\"} 1"
        ));
        assert!(metrics.contains("mobile_proxy_reverse_tunnel_freshness{state=\"fresh\"} 1"));
        assert!(metrics.contains(
            "mobile_proxy_reverse_tunnel_last_failover_reason{reason=\"connect_timeout\"} 1"
        ));
        assert_eq!(metrics.matches("transport=\"").count(), 3);
        assert_eq!(metrics.matches("state=\"").count(), 3);
        assert_eq!(metrics.matches("reason=\"").count(), 5);

        let untrusted = render_reverse_tunnel_metrics(
            Some(true),
            Some("credential=secret"),
            Some("arbitrary"),
            Some("raw-provider-error"),
        );
        assert!(!untrusted.contains("credential=secret"));
        assert!(!untrusted.contains("arbitrary"));
        assert!(!untrusted.contains("raw-provider-error"));
        assert!(!untrusted.lines().any(|line| line.ends_with(" 1") && line.contains('{')));
    }
}
''',
)

workflow = subprocess.check_output(
    ["git", "show", "origin/main:.github/workflows/rust-quality.yml"],
    text=True,
)
Path(".github/workflows/rust-quality.yml").write_text(workflow)
Path(__file__).unlink()
