use std::fmt::Write as _;

use axum::{
    Json, Router,
    extract::{Path, State},
    http::{HeaderMap, header::CONTENT_TYPE},
    response::IntoResponse,
    routing::{get, post},
};
use proxy_core::{HealthRecord, JobRecord, ProxyRuntimeRecord, RotateRequest, RuntimeStatusRecord};
use uuid::Uuid;

use crate::auth::{ApiError, authorize};
use crate::rotation::start_rotation;
use crate::state::AppState;

pub fn router(state: AppState) -> Router {
    Router::new()
        .route("/v1/health", get(get_health))
        .route("/v1/metrics", get(get_metrics))
        .route("/v1/status", get(get_status))
        .route("/v1/proxy", get(get_proxy))
        .route("/v1/ip/rotate", post(rotate_ip))
        .route("/v1/jobs/{id}", get(get_job))
        .with_state(state)
}

async fn get_health(
    State(state): State<AppState>,
    headers: HeaderMap,
) -> Result<Json<HealthRecord>, ApiError> {
    authorize(&headers, &state.admin_token)?;
    let runtime = state.runtime.lock().await;
    Ok(Json(runtime.health.clone()))
}

async fn get_metrics(
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
    writeln!(
        output,
        "# TYPE mobile_proxy_reverse_tunnel_active_transport gauge"
    )
    .unwrap();
    for transport in TRANSPORTS {
        writeln!(
            output,
            r#"mobile_proxy_reverse_tunnel_active_transport{{transport="{transport}"}} {}"#,
            u8::from(active_transport == Some(*transport))
        )
        .unwrap();
    }
    writeln!(output, "# TYPE mobile_proxy_reverse_tunnel_freshness gauge").unwrap();
    for state in FRESHNESS {
        writeln!(
            output,
            r#"mobile_proxy_reverse_tunnel_freshness{{state="{state}"}} {}"#,
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
            r#"mobile_proxy_reverse_tunnel_last_failover_reason{{reason="{reason}"}} {}"#,
            u8::from(failover_reason == Some(*reason))
        )
        .unwrap();
    }
    output
}

async fn get_status(
    State(state): State<AppState>,
    headers: HeaderMap,
) -> Result<Json<RuntimeStatusRecord>, ApiError> {
    authorize(&headers, &state.admin_token)?;
    let runtime = state.runtime.lock().await;
    Ok(Json(RuntimeStatusRecord {
        node_id: runtime.health.node_id.clone(),
        node_name: runtime.health.node_name.clone(),
        current_job: runtime.current_job,
        wireguard_enabled: runtime.wireguard_enabled,
        tunnel_owner: runtime.tunnel_owner.clone(),
    }))
}

async fn get_proxy(
    State(state): State<AppState>,
    headers: HeaderMap,
) -> Result<Json<ProxyRuntimeRecord>, ApiError> {
    authorize(&headers, &state.admin_token)?;
    let runtime = state.runtime.lock().await;
    Ok(Json(ProxyRuntimeRecord {
        status: runtime.health.proxy_status.clone(),
        listen_address: runtime.proxy_listen_address.clone(),
        pid: runtime.proxy_pid,
    }))
}

async fn rotate_ip(
    State(state): State<AppState>,
    headers: HeaderMap,
    Json(request): Json<RotateRequest>,
) -> Result<Json<proxy_core::RotateAccepted>, ApiError> {
    authorize(&headers, &state.admin_token)?;
    let accepted = start_rotation(&state, request).await?;
    Ok(Json(accepted))
}

async fn get_job(
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
        assert!(
            metrics
                .contains(r#"mobile_proxy_reverse_tunnel_active_transport{transport="tls_tcp"} 1"#)
        );
        assert!(metrics.contains(r#"mobile_proxy_reverse_tunnel_freshness{state="fresh"} 1"#));
        assert!(metrics.contains(
            r#"mobile_proxy_reverse_tunnel_last_failover_reason{reason="connect_timeout"} 1"#
        ));
        assert_eq!(metrics.matches(r#"transport=""#).count(), 3);
        assert_eq!(metrics.matches(r#"state=""#).count(), 3);
        assert_eq!(metrics.matches(r#"reason=""#).count(), 5);

        let untrusted = render_reverse_tunnel_metrics(
            Some(true),
            Some("credential=secret"),
            Some("arbitrary"),
            Some("raw-provider-error"),
        );
        assert!(!untrusted.contains("credential=secret"));
        assert!(!untrusted.contains("arbitrary"));
        assert!(!untrusted.contains("raw-provider-error"));
        assert!(
            !untrusted
                .lines()
                .any(|line| line.ends_with(" 1") && line.contains('{'))
        );
    }
}
