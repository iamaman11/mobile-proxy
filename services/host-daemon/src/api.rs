use std::fmt::Write as _;

use axum::{
    Json, Router,
    extract::{Path, State},
    http::{HeaderMap, header::CONTENT_TYPE},
    response::IntoResponse,
    routing::{get, post},
};
use mobile_proxy_foundation::{DeadlineWindow, IdempotencyKey};
use proxy_core::{
    DesiredState, DeviceRecord, HealthRecord, IssueCommandRequest, JobRecord, ProxyRuntimeRecord,
    RecoveryIntent, RotateRequest, RuntimeStatusRecord,
};
use reverse_tunnel::{
    TunnelActiveTransport, TunnelDisconnectReason, TunnelEventCounters, TunnelFailoverReason,
    TunnelTransportTransition,
};
use serde::Serialize;
use uuid::Uuid;

use crate::auth::{ApiError, authorize, authorize_ui};
use crate::state::AppState;
use crate::{control_plane, rotation::start_rotation};

pub fn router(state: AppState) -> Router {
    Router::new()
        .route("/v1/health", get(get_health))
        .route("/v1/metrics", get(get_metrics))
        .route("/v1/status", get(get_status))
        .route("/v1/proxy", get(get_proxy))
        .route("/v1/ip/rotate", post(rotate_ip))
        .route("/v1/jobs/{id}", get(get_job))
        .route("/v1/ui/status", get(get_ui_status))
        .route("/v1/ui/ip/rotate", post(rotate_ip_from_ui))
        .route("/v1/ui/jobs/{id}", get(get_ui_job))
        .with_state(state)
}

#[derive(Serialize)]
struct UiStatus {
    public_ip: Option<String>,
    readiness: String,
    serving: bool,
    tunnel_owner: Option<String>,
    rotation_in_progress: bool,
}

#[derive(Serialize)]
struct UiJob {
    id: Uuid,
    status: String,
    old_public_ip: Option<String>,
    new_public_ip: Option<String>,
    changed: Option<bool>,
}

async fn get_ui_status(
    State(state): State<AppState>,
    headers: HeaderMap,
) -> Result<Json<UiStatus>, ApiError> {
    authorize_ui(&headers, state.ui_control_token.as_deref())?;
    let config = state.control_plane_sync.as_ref().ok_or_else(|| {
        ApiError(
            axum::http::StatusCode::SERVICE_UNAVAILABLE,
            "VM control is not configured".into(),
        )
    })?;
    let device_id = { state.runtime.lock().await.health.node_id.clone() };
    let client = control_plane::client(config).map_err(vm_error)?;
    let device: DeviceRecord = client
        .get(format!("{}/api/v1/ui/devices/{device_id}", config.base_url))
        .bearer_auth(&config.ui_token)
        .send()
        .await
        .map_err(vm_error)?
        .error_for_status()
        .map_err(vm_error)?
        .json()
        .await
        .map_err(vm_error)?;
    Ok(Json(UiStatus {
        public_ip: device.last_public_ip,
        readiness: device.readiness_state,
        serving: device.serving,
        tunnel_owner: device.tunnel_owner,
        rotation_in_progress: device.current_job.is_some(),
    }))
}

async fn rotate_ip_from_ui(
    State(state): State<AppState>,
    headers: HeaderMap,
) -> Result<Json<proxy_core::RotateAccepted>, ApiError> {
    authorize_ui(&headers, state.ui_control_token.as_deref())?;
    let config = state.control_plane_sync.as_ref().ok_or_else(|| {
        ApiError(
            axum::http::StatusCode::SERVICE_UNAVAILABLE,
            "VM control is not configured".into(),
        )
    })?;
    let device_id = { state.runtime.lock().await.health.node_id.clone() };
    let request = IssueCommandRequest {
        desired_state: DesiredState::HealthyServing,
        recovery_intent: RecoveryIntent::RotateRecovery,
        deadline_secs: DeadlineWindow::new(240).expect("constant deadline is valid"),
        idempotency_key: IdempotencyKey::parse(format!("android-ui-{}", Uuid::new_v4()))
            .expect("generated idempotency key is valid"),
    };
    let client = control_plane::client(config).map_err(vm_error)?;
    let command: proxy_core::DeviceCommand = client
        .post(format!(
            "{}/api/v1/ui/devices/{device_id}/commands",
            config.base_url
        ))
        .bearer_auth(&config.ui_token)
        .json(&request)
        .send()
        .await
        .map_err(vm_error)?
        .error_for_status()
        .map_err(vm_error)?
        .json()
        .await
        .map_err(vm_error)?;
    Ok(Json(proxy_core::RotateAccepted {
        job_id: command.command_id.as_uuid(),
        accepted: true,
    }))
}

fn vm_error(error: impl std::fmt::Display) -> ApiError {
    ApiError(
        axum::http::StatusCode::BAD_GATEWAY,
        format!("VM control request failed: {error}"),
    )
}

async fn get_ui_job(
    State(state): State<AppState>,
    headers: HeaderMap,
    Path(id): Path<Uuid>,
) -> Result<Json<UiJob>, ApiError> {
    authorize_ui(&headers, state.ui_control_token.as_deref())?;
    let runtime = state.runtime.lock().await;
    let job = runtime
        .jobs
        .get(&id)
        .ok_or_else(|| ApiError(axum::http::StatusCode::NOT_FOUND, "job not found".into()))?;
    Ok(Json(UiJob {
        id: job.id,
        status: job.status.clone(),
        old_public_ip: job.old_public_ip.clone(),
        new_public_ip: job.new_public_ip.clone(),
        changed: job.changed,
    }))
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
        runtime.reverse_tunnel_counter_persistence_healthy,
        &runtime.reverse_tunnel_counters,
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
    counter_persistence_healthy: bool,
    counters: &TunnelEventCounters,
) -> String {
    const FRESHNESS: &[&str] = &["unknown", "fresh", "stale"];

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
    for transport in TunnelActiveTransport::ALL {
        let label = transport.as_str();
        writeln!(
            output,
            r#"mobile_proxy_reverse_tunnel_active_transport{{transport="{label}"}} {}"#,
            u8::from(active_transport == Some(label))
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
    for reason in TunnelFailoverReason::ALL {
        let label = reason.as_str();
        writeln!(
            output,
            r#"mobile_proxy_reverse_tunnel_last_failover_reason{{reason="{label}"}} {}"#,
            u8::from(failover_reason == Some(label))
        )
        .unwrap();
    }

    writeln!(
        output,
        "# TYPE mobile_proxy_reverse_tunnel_connections_total counter"
    )
    .unwrap();
    for transport in TunnelActiveTransport::ALL {
        writeln!(
            output,
            r#"mobile_proxy_reverse_tunnel_connections_total{{transport="{}"}} {}"#,
            transport.as_str(),
            counters.connection_count(transport)
        )
        .unwrap();
    }
    writeln!(
        output,
        "# TYPE mobile_proxy_reverse_tunnel_transport_transitions_total counter"
    )
    .unwrap();
    for transition in TunnelTransportTransition::ALL {
        writeln!(
            output,
            r#"mobile_proxy_reverse_tunnel_transport_transitions_total{{from="{}",to="{}"}} {}"#,
            transition.from_str(),
            transition.to_str(),
            counters.transition_count(transition)
        )
        .unwrap();
    }
    writeln!(
        output,
        "# TYPE mobile_proxy_reverse_tunnel_failovers_total counter"
    )
    .unwrap();
    for reason in TunnelFailoverReason::ALL {
        writeln!(
            output,
            r#"mobile_proxy_reverse_tunnel_failovers_total{{reason="{}"}} {}"#,
            reason.as_str(),
            counters.failover_count(reason)
        )
        .unwrap();
    }
    writeln!(
        output,
        "# TYPE mobile_proxy_reverse_tunnel_disconnects_total counter"
    )
    .unwrap();
    for reason in TunnelDisconnectReason::ALL {
        writeln!(
            output,
            r#"mobile_proxy_reverse_tunnel_disconnects_total{{reason="{}"}} {}"#,
            reason.as_str(),
            counters.disconnect_count(reason)
        )
        .unwrap();
    }
    writeln!(
        output,
        "# TYPE mobile_proxy_reverse_tunnel_reconnect_attempts_total counter"
    )
    .unwrap();
    writeln!(
        output,
        "mobile_proxy_reverse_tunnel_reconnect_attempts_total {}",
        counters.reconnect_attempts()
    )
    .unwrap();
    writeln!(
        output,
        "# TYPE mobile_proxy_reverse_tunnel_reconnect_successes_total counter"
    )
    .unwrap();
    writeln!(
        output,
        "mobile_proxy_reverse_tunnel_reconnect_successes_total {}",
        counters.reconnect_successes()
    )
    .unwrap();
    writeln!(
        output,
        "# TYPE mobile_proxy_reverse_tunnel_counter_persistence_healthy gauge"
    )
    .unwrap();
    writeln!(
        output,
        "mobile_proxy_reverse_tunnel_counter_persistence_healthy {}",
        u8::from(counter_persistence_healthy)
    )
    .unwrap();
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
    use std::sync::Arc;

    use axum::extract::State;
    use axum::http::{HeaderMap, HeaderValue, StatusCode};
    use proxy_core::{BinaryFingerprint, BinaryFingerprintInput, HealthRecord};
    use reverse_tunnel::{
        TunnelActiveTransport, TunnelDisconnectReason, TunnelEventCounters, TunnelFailoverReason,
        TunnelTransportTransition,
    };
    use tokio::sync::Mutex;

    use super::{get_metrics, render_reverse_tunnel_metrics};
    use crate::state::{AppState, RotationCommands, RuntimeState};

    #[test]
    fn tunnel_metrics_have_fixed_cardinality_and_no_raw_labels() {
        let mut counters = TunnelEventCounters::default();
        counters.begin_attempt();
        counters.record_failover(TunnelFailoverReason::ConnectTimeout);
        counters.record_connection(TunnelActiveTransport::TlsTcp);
        counters.record_disconnect(TunnelDisconnectReason::SessionClosed);
        let metrics = render_reverse_tunnel_metrics(
            Some(true),
            Some("tls_tcp"),
            Some("fresh"),
            Some("connect_timeout"),
            true,
            &counters,
        );
        assert!(
            metrics
                .contains(r#"mobile_proxy_reverse_tunnel_active_transport{transport="tls_tcp"} 1"#)
        );
        assert!(metrics.contains(r#"mobile_proxy_reverse_tunnel_freshness{state="fresh"} 1"#));
        assert!(metrics.contains(
            r#"mobile_proxy_reverse_tunnel_last_failover_reason{reason="connect_timeout"} 1"#
        ));
        assert!(
            metrics.contains(
                r#"mobile_proxy_reverse_tunnel_connections_total{transport="tls_tcp"} 1"#
            )
        );
        assert!(metrics.contains(
            r#"mobile_proxy_reverse_tunnel_transport_transitions_total{from="none",to="tls_tcp"} 1"#
        ));
        assert!(metrics.contains(
            r#"mobile_proxy_reverse_tunnel_failovers_total{reason="connect_timeout"} 1"#
        ));
        assert!(metrics.contains("mobile_proxy_reverse_tunnel_counter_persistence_healthy 1"));
        assert_eq!(
            metrics
                .lines()
                .filter(|line| line.starts_with("mobile_proxy_reverse_tunnel_connections_total{"))
                .count(),
            3
        );
        assert_eq!(
            metrics
                .lines()
                .filter(|line| line
                    .starts_with("mobile_proxy_reverse_tunnel_transport_transitions_total{"))
                .count(),
            9
        );
        assert_eq!(
            metrics
                .lines()
                .filter(|line| line.starts_with("mobile_proxy_reverse_tunnel_failovers_total{"))
                .count(),
            5
        );
        assert_eq!(
            metrics
                .lines()
                .filter(|line| line.starts_with("mobile_proxy_reverse_tunnel_disconnects_total{"))
                .count(),
            3
        );

        let untrusted = render_reverse_tunnel_metrics(
            Some(true),
            Some("credential=secret"),
            Some("arbitrary"),
            Some("raw-provider-error"),
            true,
            &counters,
        );
        assert!(!untrusted.contains("credential=secret"));
        assert!(!untrusted.contains("arbitrary"));
        assert!(!untrusted.contains("raw-provider-error"));
        assert!(!untrusted.lines().any(|line| {
            line.ends_with(" 1")
                && (line.starts_with("mobile_proxy_reverse_tunnel_active_transport{")
                    || line.starts_with("mobile_proxy_reverse_tunnel_freshness{")
                    || line.starts_with("mobile_proxy_reverse_tunnel_last_failover_reason{"))
        }));
    }

    #[test]
    fn counter_persistence_health_is_bounded_and_label_free() {
        let counters = TunnelEventCounters::default();
        let metrics = render_reverse_tunnel_metrics(None, None, None, None, false, &counters);
        assert!(metrics.contains("mobile_proxy_reverse_tunnel_counter_persistence_healthy 0"));
        assert_eq!(
            metrics
                .lines()
                .filter(|line| {
                    line.starts_with("mobile_proxy_reverse_tunnel_counter_persistence_healthy ")
                })
                .count(),
            1
        );
        assert!(!metrics.lines().any(|line| {
            line.starts_with("mobile_proxy_reverse_tunnel_counter_persistence_healthy{")
        }));
    }

    #[test]
    fn stale_current_state_does_not_decrease_counters() {
        let mut counters = TunnelEventCounters::default();
        counters.begin_attempt();
        counters.record_connection(TunnelActiveTransport::Quic);
        let metrics =
            render_reverse_tunnel_metrics(Some(false), None, Some("stale"), None, true, &counters);
        assert!(metrics.contains("mobile_proxy_reverse_tunnel_connected 0"));
        assert!(
            metrics.contains(r#"mobile_proxy_reverse_tunnel_active_transport{transport="quic"} 0"#)
        );
        assert!(
            metrics
                .contains(r#"mobile_proxy_reverse_tunnel_connections_total{transport="quic"} 1"#)
        );
        assert_eq!(
            counters.transition_count(TunnelTransportTransition::NoneToQuic),
            1
        );
    }

    #[tokio::test]
    async fn metrics_endpoint_requires_admin_authentication() {
        let state = AppState {
            admin_token: "admin-secret".into(),
            ui_control_token: Some("ui-control-secret".into()),
            control_plane_sync: None,
            runtime: Arc::new(Mutex::new(RuntimeState::new(
                test_health(),
                false,
                None,
                "127.0.0.1:1080".into(),
                RotationCommands::default(),
                Vec::new(),
            ))),
        };
        match get_metrics(State(state.clone()), HeaderMap::new()).await {
            Err(error) => assert_eq!(error.0, StatusCode::UNAUTHORIZED),
            Ok(_) => panic!("metrics endpoint must reject missing authentication"),
        }

        let mut headers = HeaderMap::new();
        headers.insert(
            "authorization",
            HeaderValue::from_static("Bearer admin-secret"),
        );
        assert!(get_metrics(State(state), headers).await.is_ok());
    }

    fn test_health() -> HealthRecord {
        HealthRecord {
            node_id: "test-node".into(),
            node_name: "test-node".into(),
            config_fingerprint: None,
            binary_fingerprint: BinaryFingerprintInput::current(BinaryFingerprint::derive([
                b"test",
            ])),
            readiness_state: "booting".into(),
            serving: false,
            proxy_status: "starting".into(),
            last_public_ip: None,
            active_operator_profile: None,
            active_operator_plmn: None,
            last_proxy_error: None,
            serving_failure_reason: None,
            degradation_reason_code: None,
            cellular_route_ready: None,
            proxy_bind_ready: None,
            local_serving_ready: None,
            tun0_present: None,
            wg_handshake_recent: None,
            reverse_tunnel_connected: None,
            reverse_tunnel_last_error: None,
            reverse_tunnel_active_transport: None,
            reverse_tunnel_freshness: None,
            reverse_tunnel_failover_reason: None,
            tunnel_owner: None,
        }
    }
}
