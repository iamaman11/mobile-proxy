use axum::{Json, Router, extract::State, http::StatusCode, response::IntoResponse, routing::get};
use serde_json::{Value, json};

use crate::state::{AppState, RuntimeState};

pub fn router(state: AppState) -> Router {
    Router::new()
        .route("/livez", get(liveness))
        .route("/readyz", get(readiness))
        .with_state(state)
}

async fn liveness() -> Json<Value> {
    Json(json!({
        "status": "live"
    }))
}

async fn readiness(State(state): State<AppState>) -> impl IntoResponse {
    let runtime = state.runtime.lock().await;
    let (status, body) = readiness_document(&runtime);
    (status, Json(body))
}

fn readiness_document(runtime: &RuntimeState) -> (StatusCode, Value) {
    let tunnel_worker_required = matches!(
        runtime.tunnel_owner.as_deref(),
        Some("first_party_reverse_tunnel" | "first_party_android_egress")
    );
    let tunnel_worker_ready = !tunnel_worker_required || runtime.reverse_tunnel_restart.is_some();
    let counter_store_healthy = runtime.reverse_tunnel_counter_persistence_healthy;
    let ready = tunnel_worker_ready && counter_store_healthy;
    let status = if ready {
        StatusCode::OK
    } else {
        StatusCode::SERVICE_UNAVAILABLE
    };

    let transport = bounded_transport(runtime.health.reverse_tunnel_active_transport.as_deref());
    let freshness = bounded_freshness(runtime.health.reverse_tunnel_freshness.as_deref());

    (
        status,
        json!({
            "status": if ready { "ready" } else { "not_ready" },
            "critical_dependencies": {
                "reverse_tunnel_worker": {
                    "required": tunnel_worker_required,
                    "healthy": tunnel_worker_ready
                },
                "tunnel_counter_store": {
                    "healthy": counter_store_healthy
                }
            },
            "device_availability": {
                "serving": runtime.health.serving,
                "cellular_route_ready": runtime.health.cellular_route_ready,
                "proxy_bind_ready": runtime.health.proxy_bind_ready,
                "local_serving_ready": runtime.health.local_serving_ready
            },
            "reverse_tunnel": {
                "connected": runtime.health.reverse_tunnel_connected,
                "active_transport": transport,
                "freshness": freshness
            }
        }),
    )
}

fn bounded_transport(value: Option<&str>) -> Option<&str> {
    match value {
        Some("quic") => Some("quic"),
        Some("tls_tcp") => Some("tls_tcp"),
        Some("tcp") => Some("tcp"),
        _ => None,
    }
}

fn bounded_freshness(value: Option<&str>) -> Option<&str> {
    match value {
        Some("unknown") => Some("unknown"),
        Some("fresh") => Some("fresh"),
        Some("stale") => Some("stale"),
        _ => None,
    }
}

#[cfg(test)]
mod tests {
    use axum::http::StatusCode;
    use proxy_core::{BinaryFingerprint, BinaryFingerprintInput, HealthRecord};

    use super::readiness_document;
    use crate::state::{RotationCommands, RuntimeState};

    #[test]
    fn device_unavailability_does_not_make_the_process_not_ready() {
        let runtime = RuntimeState::new(
            test_health(),
            false,
            None,
            "127.0.0.1:1080".into(),
            RotationCommands::default(),
            Vec::new(),
        );

        let (status, body) = readiness_document(&runtime);
        assert_eq!(status, StatusCode::OK);
        assert_eq!(body["status"], "ready");
        assert_eq!(body["device_availability"]["serving"], false);
        assert_eq!(body["reverse_tunnel"]["connected"], serde_json::Value::Null);
    }

    #[test]
    fn critical_persistence_failure_fails_readiness_closed() {
        let mut runtime = RuntimeState::new(
            test_health(),
            false,
            None,
            "127.0.0.1:1080".into(),
            RotationCommands::default(),
            Vec::new(),
        );
        runtime.reverse_tunnel_counter_persistence_healthy = false;

        let (status, body) = readiness_document(&runtime);
        assert_eq!(status, StatusCode::SERVICE_UNAVAILABLE);
        assert_eq!(body["status"], "not_ready");
        assert_eq!(
            body["critical_dependencies"]["tunnel_counter_store"]["healthy"],
            false
        );
    }

    #[test]
    fn untrusted_tunnel_strings_are_not_exposed() {
        let mut health = test_health();
        health.reverse_tunnel_active_transport = Some("credential=secret".into());
        health.reverse_tunnel_freshness = Some("raw-provider-error".into());
        let runtime = RuntimeState::new(
            health,
            false,
            None,
            "127.0.0.1:1080".into(),
            RotationCommands::default(),
            Vec::new(),
        );

        let (_, body) = readiness_document(&runtime);
        let rendered = body.to_string();
        assert!(!rendered.contains("credential=secret"));
        assert!(!rendered.contains("raw-provider-error"));
        assert_eq!(
            body["reverse_tunnel"]["active_transport"],
            serde_json::Value::Null
        );
        assert_eq!(body["reverse_tunnel"]["freshness"], serde_json::Value::Null);
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
            cellular_route_ready: Some(false),
            proxy_bind_ready: Some(false),
            local_serving_ready: Some(false),
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
