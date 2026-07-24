use crate::auth::{AuthConfig, require_admin, require_device};
use crate::projection::{apply_public_probe, now_unix_secs};
use crate::{request_context::attach_request_context, state::AppState};
use axum::{
    Json, Router,
    extract::{Extension, Path, State},
    http::StatusCode,
    middleware,
    routing::{get, post},
};
use mobile_proxy_application::{
    AcknowledgeCommandError, AcknowledgeCommandInput, AcknowledgeCommandPort, HeartbeatError,
    HeartbeatInput, HeartbeatPort, IssueCommandError, IssueCommandInput, IssueCommandPort,
    PollCommandError, PollCommandInput, PollCommandPort, RegisterDeviceError, RegisterDeviceInput,
    RegisterDevicePort,
};
use mobile_proxy_foundation::{CommandId, RequestContext};
use proxy_core::{
    CommandAckRequest, DeviceCommand, DeviceRecord, HeartbeatRequest, IssueCommandRequest,
    PublicProbeReport, RegisterDeviceRequest,
};

pub fn router(state: AppState, auth: AuthConfig) -> Router {
    let admin = Router::new()
        .route("/api/v1/ip", get(get_ip))
        .route("/api/v1/devices", get(list_devices))
        .route("/api/v1/devices/ready", get(list_ready_devices))
        .route("/api/v1/devices/{id}/public-probe", post(public_probe))
        .route("/api/v1/devices/{id}/commands", post(issue_command))
        .route_layer(middleware::from_fn(attach_request_context))
        .route_layer(middleware::from_fn_with_state(auth.clone(), require_admin));
    let device = Router::new()
        .route("/api/v1/devices/register", post(register_device))
        .route("/api/v1/devices/heartbeat", post(heartbeat))
        .route("/api/v1/devices/{id}/commands/next", get(next_command))
        .route(
            "/api/v1/devices/{id}/commands/{command_id}/ack",
            post(ack_command),
        )
        .route_layer(middleware::from_fn(attach_request_context))
        .route_layer(middleware::from_fn_with_state(auth, require_device));
    Router::new().merge(admin).merge(device).with_state(state)
}

async fn get_ip() -> (StatusCode, Json<serde_json::Value>) {
    (
        StatusCode::NOT_IMPLEMENTED,
        Json(serde_json::json!({
            "error": "control-plane /api/v1/ip is not a phone public IP observer",
        })),
    )
}

async fn list_devices(State(state): State<AppState>) -> Json<Vec<DeviceRecord>> {
    let devices = state.devices.lock().await;
    Json(devices.values().cloned().map(mark_stale).collect())
}

async fn list_ready_devices(State(state): State<AppState>) -> Json<Vec<DeviceRecord>> {
    let devices = state.devices.lock().await;
    Json(
        devices
            .values()
            .cloned()
            .map(mark_stale)
            .filter(|device| device.availability == "ready")
            .collect(),
    )
}

async fn register_device(
    State(state): State<AppState>,
    Extension(context): Extension<RequestContext>,
    Json(req): Json<RegisterDeviceRequest>,
) -> Result<Json<serde_json::Value>, ControlPlaneRouteError> {
    match state
        .register_device(RegisterDeviceInput { request: req })
        .await
    {
        Ok(outcome) => {
            tracing::info!(
                request_id = %context.request_id(),
                correlation_id = %context.correlation_id(),
                classification = outcome.classification(),
                "device registration processed"
            );
            Ok(Json(serde_json::json!({ "accepted": outcome.accepted() })))
        }
        Err(RegisterDeviceError::StateConflict) => {
            tracing::error!(
                request_id = %context.request_id(),
                correlation_id = %context.correlation_id(),
                error_code = "device_state_conflict",
                "device registration failed"
            );
            Err((
                StatusCode::INTERNAL_SERVER_ERROR,
                Json(serde_json::json!({ "error": "device_state_conflict" })),
            ))
        }
        Err(RegisterDeviceError::CapacityExceeded) => {
            tracing::warn!(
                request_id = %context.request_id(),
                correlation_id = %context.correlation_id(),
                error_code = "device_capacity_exceeded",
                "device registration rejected"
            );
            Err((
                StatusCode::SERVICE_UNAVAILABLE,
                Json(serde_json::json!({ "error": "device_capacity_exceeded" })),
            ))
        }
        Err(RegisterDeviceError::Persistence) => {
            tracing::error!(
                request_id = %context.request_id(),
                correlation_id = %context.correlation_id(),
                error_code = "state_persistence_failed",
                "device registration failed"
            );
            Err((
                StatusCode::SERVICE_UNAVAILABLE,
                Json(serde_json::json!({ "error": "state_persistence_failed" })),
            ))
        }
    }
}

async fn heartbeat(
    State(state): State<AppState>,
    Extension(context): Extension<RequestContext>,
    Json(req): Json<HeartbeatRequest>,
) -> Result<Json<serde_json::Value>, ControlPlaneRouteError> {
    let node_id = req.node_id.clone();
    match state
        .record_heartbeat(HeartbeatInput { request: req })
        .await
    {
        Ok(outcome) => {
            if outcome.legacy_config_fingerprint() || outcome.legacy_binary_fingerprint() {
                tracing::warn!(
                    request_id = %context.request_id(),
                    correlation_id = %context.correlation_id(),
                    node_id = %node_id,
                    legacy_config_fingerprint = outcome.legacy_config_fingerprint(),
                    legacy_binary_fingerprint = outcome.legacy_binary_fingerprint(),
                    "legacy runtime fingerprint accepted for rolling migration and not persisted"
                );
            }
            tracing::info!(
                request_id = %context.request_id(),
                correlation_id = %context.correlation_id(),
                node_id = %node_id,
                classification = outcome.classification(),
                "device heartbeat processed"
            );
            Ok(Json(serde_json::json!({ "accepted": outcome.accepted() })))
        }
        Err(HeartbeatError::StateConflict) => {
            tracing::error!(
                request_id = %context.request_id(),
                correlation_id = %context.correlation_id(),
                node_id = %node_id,
                error_code = "device_state_conflict",
                "device heartbeat failed"
            );
            Err((
                StatusCode::INTERNAL_SERVER_ERROR,
                Json(serde_json::json!({ "error": "device_state_conflict" })),
            ))
        }
        Err(HeartbeatError::CapacityExceeded) => {
            tracing::warn!(
                request_id = %context.request_id(),
                correlation_id = %context.correlation_id(),
                node_id = %node_id,
                error_code = "device_capacity_exceeded",
                "device heartbeat rejected"
            );
            Err((
                StatusCode::SERVICE_UNAVAILABLE,
                Json(serde_json::json!({ "error": "device_capacity_exceeded" })),
            ))
        }
        Err(HeartbeatError::Persistence) => {
            tracing::error!(
                request_id = %context.request_id(),
                correlation_id = %context.correlation_id(),
                node_id = %node_id,
                error_code = "state_persistence_failed",
                "device heartbeat failed"
            );
            Err((
                StatusCode::SERVICE_UNAVAILABLE,
                Json(serde_json::json!({ "error": "state_persistence_failed" })),
            ))
        }
    }
}

async fn public_probe(
    State(state): State<AppState>,
    Path(id): Path<String>,
    Json(req): Json<PublicProbeReport>,
) -> Json<serde_json::Value> {
    let mut devices = state.devices.lock().await;
    if let Some(device) = devices.get_mut(&id) {
        apply_public_probe(device, req);
    }
    drop(devices);
    let _ = state.persist().await;
    Json(serde_json::json!({ "accepted": true }))
}

type ControlPlaneRouteError = (StatusCode, Json<serde_json::Value>);

async fn issue_command(
    State(state): State<AppState>,
    Extension(context): Extension<RequestContext>,
    Path(id): Path<String>,
    Json(req): Json<IssueCommandRequest>,
) -> Result<Json<DeviceCommand>, ControlPlaneRouteError> {
    match state
        .issue_command(IssueCommandInput {
            device_id: id.clone(),
            request: req,
        })
        .await
    {
        Ok(outcome) => {
            let (classification, command) = outcome.into_parts();
            tracing::info!(
                request_id = %context.request_id(),
                correlation_id = %context.correlation_id(),
                command_id = %command.command_id,
                device_id = %id,
                classification,
                "device command accepted"
            );
            Ok(Json(command))
        }
        Err(IssueCommandError::IdempotencyConflict) => {
            tracing::warn!(
                request_id = %context.request_id(),
                correlation_id = %context.correlation_id(),
                device_id = %id,
                error_code = "idempotency_conflict",
                "device command rejected"
            );
            Err((
                StatusCode::CONFLICT,
                Json(serde_json::json!({ "error": "idempotency_conflict" })),
            ))
        }
        Err(IssueCommandError::StateConflict) => {
            tracing::error!(
                request_id = %context.request_id(),
                correlation_id = %context.correlation_id(),
                device_id = %id,
                error_code = "command_state_conflict",
                "device command rejected"
            );
            Err((
                StatusCode::INTERNAL_SERVER_ERROR,
                Json(serde_json::json!({ "error": "command_state_conflict" })),
            ))
        }
        Err(IssueCommandError::CapacityExceeded) => {
            tracing::warn!(
                request_id = %context.request_id(),
                correlation_id = %context.correlation_id(),
                device_id = %id,
                error_code = "command_capacity_exceeded",
                "device command rejected"
            );
            Err((
                StatusCode::SERVICE_UNAVAILABLE,
                Json(serde_json::json!({ "error": "command_capacity_exceeded" })),
            ))
        }
        Err(IssueCommandError::Persistence) => {
            tracing::error!(
                request_id = %context.request_id(),
                correlation_id = %context.correlation_id(),
                device_id = %id,
                error_code = "state_persistence_failed",
                "device command rejected"
            );
            Err((
                StatusCode::SERVICE_UNAVAILABLE,
                Json(serde_json::json!({ "error": "state_persistence_failed" })),
            ))
        }
    }
}

async fn next_command(
    State(state): State<AppState>,
    Extension(context): Extension<RequestContext>,
    Path(id): Path<String>,
) -> Result<Json<Option<DeviceCommand>>, ControlPlaneRouteError> {
    match state
        .poll_command(PollCommandInput {
            device_id: id.clone(),
        })
        .await
    {
        Ok(outcome) => Ok(Json(outcome.into_option())),
        Err(PollCommandError::StateConflict) => {
            tracing::error!(
                request_id = %context.request_id(),
                correlation_id = %context.correlation_id(),
                device_id = %id,
                error_code = "command_state_conflict",
                "device command polling failed"
            );
            Err((
                StatusCode::INTERNAL_SERVER_ERROR,
                Json(serde_json::json!({ "error": "command_state_conflict" })),
            ))
        }
    }
}

async fn ack_command(
    State(state): State<AppState>,
    Extension(context): Extension<RequestContext>,
    Path((id, command_id)): Path<(String, CommandId)>,
    Json(req): Json<CommandAckRequest>,
) -> Result<Json<serde_json::Value>, ControlPlaneRouteError> {
    match state
        .acknowledge_command(AcknowledgeCommandInput {
            device_id: id.clone(),
            command_id,
            request: req,
        })
        .await
    {
        Ok(outcome) => {
            tracing::info!(
                request_id = %context.request_id(),
                correlation_id = %context.correlation_id(),
                command_id = %command_id,
                device_id = %id,
                classification = outcome.classification(),
                "device command acknowledgement processed"
            );
            Ok(Json(serde_json::json!({ "accepted": outcome.accepted() })))
        }
        Err(AcknowledgeCommandError::StateConflict) => {
            tracing::error!(
                request_id = %context.request_id(),
                correlation_id = %context.correlation_id(),
                command_id = %command_id,
                device_id = %id,
                error_code = "command_state_conflict",
                "device command acknowledgement failed"
            );
            Err((
                StatusCode::INTERNAL_SERVER_ERROR,
                Json(serde_json::json!({ "error": "command_state_conflict" })),
            ))
        }
        Err(AcknowledgeCommandError::Persistence) => {
            tracing::error!(
                request_id = %context.request_id(),
                correlation_id = %context.correlation_id(),
                command_id = %command_id,
                device_id = %id,
                error_code = "state_persistence_failed",
                "device command acknowledgement failed"
            );
            Err((
                StatusCode::SERVICE_UNAVAILABLE,
                Json(serde_json::json!({ "error": "state_persistence_failed" })),
            ))
        }
    }
}

fn mark_stale(mut device: DeviceRecord) -> DeviceRecord {
    const HEARTBEAT_TTL_SECS: u64 = 30;
    let Some(last) = device
        .last_heartbeat_at
        .as_deref()
        .and_then(|raw| raw.parse::<u64>().ok())
    else {
        return device;
    };
    let Ok(now) = now_unix_secs().parse::<u64>() else {
        return device;
    };
    if now.saturating_sub(last) <= HEARTBEAT_TTL_SECS {
        return device;
    }

    device.readiness_state = "waiting_cellular".into();
    device.serving = false;
    device.publicly_serving = false;
    device.reverse_tunnel_connected = Some(false);
    device.reverse_tunnel_last_error = Some("device heartbeat is stale".into());
    device.reverse_tunnel_active_transport = None;
    device.reverse_tunnel_freshness = Some("stale".into());
    device.availability = "degraded".into();
    device.degradation_reason_code = Some("heartbeat_stale".into());
    device.serving_failure_reason = Some("device heartbeat is stale".into());
    device
}

#[cfg(test)]
mod tests {
    use crate::{auth::AuthConfig, projection::now_unix_secs, routes::router, state::AppState};
    use axum::{
        body::Body,
        http::{Request, StatusCode},
    };
    use proxy_core::{
        Availability, BinaryFingerprint, DeviceCommand, DeviceRecord, RuntimeProjectionInput,
        RuntimeReadiness, project_runtime,
    };
    use tower::ServiceExt;
    use uuid::Uuid;

    async fn test_app() -> axum::Router {
        let path = std::env::temp_dir().join(format!(
            "mobile-proxy-control-plane-{}.json",
            Uuid::new_v4()
        ));
        router(
            AppState::load(path).await.unwrap(),
            AuthConfig::new("admin-token".into(), "device-token".into()).unwrap(),
        )
    }

    #[tokio::test]
    async fn routes_enforce_role_specific_bearer_tokens() {
        let unauthorized = test_app()
            .await
            .oneshot(Request::get("/api/v1/devices").body(Body::empty()).unwrap())
            .await
            .unwrap();
        assert_eq!(unauthorized.status(), StatusCode::UNAUTHORIZED);

        let admin = test_app()
            .await
            .oneshot(
                Request::get("/api/v1/devices")
                    .header("authorization", "Bearer admin-token")
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(admin.status(), StatusCode::OK);

        let wrong_role = test_app()
            .await
            .oneshot(
                Request::get("/api/v1/devices")
                    .header("authorization", "Bearer device-token")
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(wrong_role.status(), StatusCode::UNAUTHORIZED);
    }

    #[tokio::test]
    async fn request_context_generates_response_lineage() {
        let response = test_app()
            .await
            .oneshot(
                Request::get("/api/v1/devices")
                    .header("authorization", "Bearer admin-token")
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::OK);
        for header in ["x-request-id", "x-correlation-id"] {
            let raw = response.headers().get(header).unwrap().to_str().unwrap();
            Uuid::parse_str(raw).unwrap();
        }
    }

    #[tokio::test]
    async fn authentication_precedes_request_context_parsing() {
        let response = test_app()
            .await
            .oneshot(
                Request::get("/api/v1/devices")
                    .header("x-request-id", "credential=secret")
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::UNAUTHORIZED);
    }

    #[tokio::test]
    async fn malformed_or_expired_authenticated_context_fails_closed() {
        let malformed = test_app()
            .await
            .oneshot(
                Request::get("/api/v1/devices")
                    .header("authorization", "Bearer admin-token")
                    .header("x-request-id", "credential=secret")
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(malformed.status(), StatusCode::BAD_REQUEST);

        let expired = test_app()
            .await
            .oneshot(
                Request::get("/api/v1/devices")
                    .header("authorization", "Bearer admin-token")
                    .header("x-deadline-unix-secs", "1")
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(expired.status(), StatusCode::REQUEST_TIMEOUT);
    }

    #[tokio::test]
    async fn supplied_request_lineage_round_trips() {
        let response = test_app()
            .await
            .oneshot(
                Request::get("/api/v1/devices")
                    .header("authorization", "Bearer admin-token")
                    .header("x-request-id", "98da1dbc-7de7-4bd2-8a5c-e24af5131f38")
                    .header("x-correlation-id", "4cd306ef-716e-4f76-aef6-679b93bb7770")
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(
            response
                .headers()
                .get("x-request-id")
                .unwrap()
                .to_str()
                .unwrap(),
            "98da1dbc-7de7-4bd2-8a5c-e24af5131f38"
        );
        assert_eq!(
            response
                .headers()
                .get("x-correlation-id")
                .unwrap()
                .to_str()
                .unwrap(),
            "4cd306ef-716e-4f76-aef6-679b93bb7770"
        );
    }

    #[tokio::test]
    async fn typed_device_registration_preserves_json_and_first_write_semantics() {
        const FIRST: &str = r#"{
            "node_id":"device-1",
            "node_name":"first-name",
            "proxy_status":"starting",
            "tunnel_owner":"stock_wireguard_bridge"
        }"#;
        const CHANGED: &str = r#"{
            "node_id":"device-1",
            "node_name":"changed-name",
            "proxy_status":"running",
            "tunnel_owner":"first_party_reverse_tunnel"
        }"#;
        let app = test_app().await;
        for payload in [FIRST, CHANGED] {
            let response = app
                .clone()
                .oneshot(
                    Request::post("/api/v1/devices/register")
                        .header("authorization", "Bearer device-token")
                        .header("content-type", "application/json")
                        .body(Body::from(payload))
                        .unwrap(),
                )
                .await
                .unwrap();
            assert_eq!(response.status(), StatusCode::OK);
            let body = axum::body::to_bytes(response.into_body(), 16 * 1024)
                .await
                .unwrap();
            let json: serde_json::Value = serde_json::from_slice(&body).unwrap();
            assert_eq!(json["accepted"], true);
        }

        let response = app
            .oneshot(
                Request::get("/api/v1/devices")
                    .header("authorization", "Bearer admin-token")
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::OK);
        let body = axum::body::to_bytes(response.into_body(), 16 * 1024)
            .await
            .unwrap();
        let devices: Vec<DeviceRecord> = serde_json::from_slice(&body).unwrap();
        assert_eq!(devices.len(), 1);
        assert_eq!(devices[0].node_name, "first-name");
        assert_eq!(devices[0].proxy_status, "starting");
        assert_eq!(
            devices[0].tunnel_owner.as_deref(),
            Some("stock_wireguard_bridge")
        );
    }

    #[tokio::test]
    async fn typed_command_boundary_preserves_json_and_deduplicates() {
        const PAYLOAD: &str = r#"{
            "desired_state":"healthy_serving",
            "recovery_intent":"none",
            "deadline_secs":30,
            "idempotency_key":"command-123"
        }"#;
        let app = test_app().await;
        let first = app
            .clone()
            .oneshot(
                Request::post("/api/v1/devices/device-1/commands")
                    .header("authorization", "Bearer admin-token")
                    .header("content-type", "application/json")
                    .body(Body::from(PAYLOAD))
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(first.status(), StatusCode::OK);
        let first_body = axum::body::to_bytes(first.into_body(), 16 * 1024)
            .await
            .unwrap();
        let first_command: DeviceCommand = serde_json::from_slice(&first_body).unwrap();
        assert_eq!(first_command.deadline_secs.as_secs(), 30);
        assert_eq!(first_command.idempotency_key.as_str(), "command-123");

        let second = app
            .oneshot(
                Request::post("/api/v1/devices/device-1/commands")
                    .header("authorization", "Bearer admin-token")
                    .header("content-type", "application/json")
                    .body(Body::from(PAYLOAD))
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(second.status(), StatusCode::OK);
        let second_body = axum::body::to_bytes(second.into_body(), 16 * 1024)
            .await
            .unwrap();
        let second_command: DeviceCommand = serde_json::from_slice(&second_body).unwrap();
        assert_eq!(second_command.command_id, first_command.command_id);
    }

    #[tokio::test]
    async fn command_delivery_routes_preserve_success_json_and_retry_semantics() {
        const PAYLOAD: &str = r#"{
            "desired_state":"healthy_serving",
            "recovery_intent":"none",
            "deadline_secs":30,
            "idempotency_key":"delivery-command"
        }"#;
        let app = test_app().await;
        let issued = app
            .clone()
            .oneshot(
                Request::post("/api/v1/devices/device-1/commands")
                    .header("authorization", "Bearer admin-token")
                    .header("content-type", "application/json")
                    .body(Body::from(PAYLOAD))
                    .unwrap(),
            )
            .await
            .unwrap();
        let body = axum::body::to_bytes(issued.into_body(), 16 * 1024)
            .await
            .unwrap();
        let command: DeviceCommand = serde_json::from_slice(&body).unwrap();

        let polled = app
            .clone()
            .oneshot(
                Request::get("/api/v1/devices/device-1/commands/next")
                    .header("authorization", "Bearer device-token")
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(polled.status(), StatusCode::OK);
        let body = axum::body::to_bytes(polled.into_body(), 16 * 1024)
            .await
            .unwrap();
        let pending: Option<DeviceCommand> = serde_json::from_slice(&body).unwrap();
        assert_eq!(pending, Some(command.clone()));

        let rejected = app
            .clone()
            .oneshot(
                Request::post(format!(
                    "/api/v1/devices/device-1/commands/{}/ack",
                    command.command_id
                ))
                .header("authorization", "Bearer device-token")
                .header("content-type", "application/json")
                .body(Body::from(r#"{"ok":false,"message":"retry"}"#))
                .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(rejected.status(), StatusCode::OK);
        let body = axum::body::to_bytes(rejected.into_body(), 16 * 1024)
            .await
            .unwrap();
        let json: serde_json::Value = serde_json::from_slice(&body).unwrap();
        assert_eq!(json["accepted"], true);

        let completed = app
            .clone()
            .oneshot(
                Request::post(format!(
                    "/api/v1/devices/device-1/commands/{}/ack",
                    command.command_id
                ))
                .header("authorization", "Bearer device-token")
                .header("content-type", "application/json")
                .body(Body::from(r#"{"ok":true,"message":null}"#))
                .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(completed.status(), StatusCode::OK);
        let body = axum::body::to_bytes(completed.into_body(), 16 * 1024)
            .await
            .unwrap();
        let json: serde_json::Value = serde_json::from_slice(&body).unwrap();
        assert_eq!(json["accepted"], true);

        let empty = app
            .oneshot(
                Request::get("/api/v1/devices/device-1/commands/next")
                    .header("authorization", "Bearer device-token")
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();
        let body = axum::body::to_bytes(empty.into_body(), 16 * 1024)
            .await
            .unwrap();
        let pending: Option<DeviceCommand> = serde_json::from_slice(&body).unwrap();
        assert_eq!(pending, None);
    }

    #[tokio::test]
    async fn reused_command_idempotency_key_with_changed_parameters_returns_conflict() {
        const FIRST: &str = r#"{
            "desired_state":"healthy_serving",
            "recovery_intent":"none",
            "deadline_secs":30,
            "idempotency_key":"command-conflict"
        }"#;
        const CHANGED: &str = r#"{
            "desired_state":"degraded_safe",
            "recovery_intent":"none",
            "deadline_secs":30,
            "idempotency_key":"command-conflict"
        }"#;
        let app = test_app().await;
        let first = app
            .clone()
            .oneshot(
                Request::post("/api/v1/devices/device-1/commands")
                    .header("authorization", "Bearer admin-token")
                    .header("content-type", "application/json")
                    .body(Body::from(FIRST))
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(first.status(), StatusCode::OK);

        let conflict = app
            .oneshot(
                Request::post("/api/v1/devices/device-1/commands")
                    .header("authorization", "Bearer admin-token")
                    .header("content-type", "application/json")
                    .body(Body::from(CHANGED))
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(conflict.status(), StatusCode::CONFLICT);
        let body = axum::body::to_bytes(conflict.into_body(), 16 * 1024)
            .await
            .unwrap();
        let error: serde_json::Value = serde_json::from_slice(&body).unwrap();
        assert_eq!(error["error"], "idempotency_conflict");
    }

    #[tokio::test]
    async fn legacy_heartbeat_fingerprints_are_accepted_but_not_persisted() {
        let app = test_app().await;
        let response = app
            .clone()
            .oneshot(
                Request::post("/api/v1/devices/heartbeat")
                    .header("authorization", "Bearer device-token")
                    .header("content-type", "application/json")
                    .body(Body::from(
                        r#"{
                            "node_id":"device-1",
                            "node_name":"device",
                            "readiness_state":"booting",
                            "serving":false,
                            "proxy_status":"starting",
                            "config_fingerprint":"legacy-config",
                            "binary_fingerprint":"legacy-binary"
                        }"#,
                    ))
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::OK);

        let response = app
            .oneshot(
                Request::get("/api/v1/devices")
                    .header("authorization", "Bearer admin-token")
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();
        let body = axum::body::to_bytes(response.into_body(), 16 * 1024)
            .await
            .unwrap();
        let devices: Vec<DeviceRecord> = serde_json::from_slice(&body).unwrap();
        assert_eq!(devices.len(), 1);
        assert!(devices[0].config_fingerprint.is_none());
        assert!(devices[0].binary_fingerprint.is_none());
    }

    #[tokio::test]
    async fn typed_heartbeat_fingerprint_round_trips_as_the_existing_json_string_shape() {
        let binary = BinaryFingerprint::derive([b"binary"]);
        let payload = format!(
            r#"{{
                "node_id":"device-1",
                "node_name":"device",
                "readiness_state":"booting",
                "serving":false,
                "proxy_status":"starting",
                "binary_fingerprint":"{binary}"
            }}"#
        );
        let app = test_app().await;
        let response = app
            .clone()
            .oneshot(
                Request::post("/api/v1/devices/heartbeat")
                    .header("authorization", "Bearer device-token")
                    .header("content-type", "application/json")
                    .body(Body::from(payload))
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::OK);

        let response = app
            .oneshot(
                Request::get("/api/v1/devices")
                    .header("authorization", "Bearer admin-token")
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();
        let body = axum::body::to_bytes(response.into_body(), 16 * 1024)
            .await
            .unwrap();
        let json: serde_json::Value = serde_json::from_slice(&body).unwrap();
        assert_eq!(json[0]["binary_fingerprint"], binary.to_string());
    }

    #[tokio::test]
    async fn unknown_prefixed_heartbeat_fingerprint_fails_closed() {
        let response = test_app()
            .await
            .oneshot(
                Request::post("/api/v1/devices/heartbeat")
                    .header("authorization", "Bearer device-token")
                    .header("content-type", "application/json")
                    .body(Body::from(
                        r#"{
                            "node_id":"device-1",
                            "node_name":"device",
                            "readiness_state":"booting",
                            "serving":false,
                            "proxy_status":"starting",
                            "binary_fingerprint":"unknown:abcd"
                        }"#,
                    ))
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::UNPROCESSABLE_ENTITY);
    }

    #[tokio::test]
    async fn invalid_command_idempotency_and_deadline_are_rejected() {
        for payload in [
            r#"{"desired_state":"healthy_serving","recovery_intent":"none","deadline_secs":30,"idempotency_key":""}"#,
            r#"{"desired_state":"healthy_serving","recovery_intent":"none","deadline_secs":0,"idempotency_key":"command-123"}"#,
        ] {
            let response = test_app()
                .await
                .oneshot(
                    Request::post("/api/v1/devices/device-1/commands")
                        .header("authorization", "Bearer admin-token")
                        .header("content-type", "application/json")
                        .body(Body::from(payload))
                        .unwrap(),
                )
                .await
                .unwrap();
            assert_eq!(response.status(), StatusCode::UNPROCESSABLE_ENTITY);
        }
    }

    #[test]
    fn availability_requires_public_probe() {
        let projection = project_runtime(RuntimeProjectionInput {
            readiness_state: RuntimeReadiness::Healthy.to_string(),
            serving: true,
            publicly_serving: false,
            current_job: None,
            cellular_route_ready: Some(true),
            proxy_bind_ready: Some(true),
            local_serving_ready: Some(true),
        });
        assert_eq!(projection.availability, Availability::Degraded.to_string());
    }

    #[test]
    fn unix_clock_is_serialized() {
        let ts = now_unix_secs();
        assert!(ts.parse::<u64>().is_ok());
    }

    #[test]
    fn stale_heartbeat_is_not_ready() {
        let device = DeviceRecord {
            node_id: "n".into(),
            node_name: "node".into(),
            readiness_state: "healthy".into(),
            serving: true,
            proxy_status: "running".into(),
            proxy_pid: None,
            last_public_ip: None,
            current_job: None,
            last_proxy_error: None,
            version: None,
            config_fingerprint: None,
            binary_fingerprint: None,
            active_operator_profile: None,
            active_operator_plmn: None,
            publicly_serving: true,
            public_probe_error: None,
            public_probe_at: None,
            cellular_route_ready: Some(true),
            proxy_bind_ready: Some(true),
            local_serving_ready: Some(true),
            tun0_present: Some(true),
            wg_handshake_recent: Some(true),
            reverse_tunnel_connected: None,
            reverse_tunnel_last_error: None,
            reverse_tunnel_active_transport: Some("quic".into()),
            reverse_tunnel_freshness: Some("fresh".into()),
            reverse_tunnel_failover_reason: Some("connect_timeout".into()),
            tunnel_owner: Some("stock_wireguard_bridge".into()),
            last_heartbeat_at: Some("1".into()),
            availability: "ready".into(),
            degradation_reason_code: None,
            serving_failure_reason: None,
            desired_state: None,
            recovery_intent: None,
            last_event_at: None,
        };
        let projected = super::mark_stale(device);
        assert_eq!(projected.availability, "degraded");
        assert_eq!(projected.reverse_tunnel_connected, Some(false));
        assert_eq!(projected.reverse_tunnel_active_transport, None);
        assert_eq!(projected.reverse_tunnel_freshness.as_deref(), Some("stale"));
        assert_eq!(
            projected.reverse_tunnel_failover_reason.as_deref(),
            Some("connect_timeout")
        );
        assert_eq!(
            projected.degradation_reason_code.as_deref(),
            Some("heartbeat_stale")
        );
    }
}
