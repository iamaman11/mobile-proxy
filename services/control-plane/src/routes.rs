use axum::{
    Json, Router,
    extract::{Extension, Path, State},
    http::StatusCode,
    middleware,
    routing::{get, post},
};
use mobile_proxy_foundation::{CommandId, RequestContext};
use proxy_core::{
    CommandAckRequest, DeviceCommand, DeviceRecord, HeartbeatRequest, IssueCommandRequest,
    PublicProbeReport, RecoveryIntent, RegisterDeviceRequest,
};
use uuid::Uuid;

use crate::auth::{AuthConfig, require_admin, require_device};
use crate::projection::{
    apply_public_probe, build_heartbeat_device, build_registered_device, now_unix_secs,
};
use crate::{request_context::attach_request_context, state::AppState};

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
    Json(req): Json<RegisterDeviceRequest>,
) -> Json<serde_json::Value> {
    let mut devices = state.devices.lock().await;
    devices
        .entry(req.node_id.clone())
        .or_insert_with(|| build_registered_device(req));
    drop(devices);
    let _ = state.persist().await;
    Json(serde_json::json!({ "accepted": true }))
}

async fn heartbeat(
    State(state): State<AppState>,
    Json(req): Json<HeartbeatRequest>,
) -> Json<serde_json::Value> {
    let legacy_config_fingerprint = req
        .config_fingerprint
        .as_ref()
        .is_some_and(proxy_core::ConfigFingerprintInput::is_legacy);
    let legacy_binary_fingerprint = req
        .binary_fingerprint
        .as_ref()
        .is_some_and(proxy_core::BinaryFingerprintInput::is_legacy);
    if legacy_config_fingerprint || legacy_binary_fingerprint {
        tracing::warn!(
            node_id = %req.node_id,
            legacy_config_fingerprint,
            legacy_binary_fingerprint,
            "legacy runtime fingerprint accepted for rolling migration and not persisted"
        );
    }
    let mut devices = state.devices.lock().await;
    let previous_probe = devices.get(&req.node_id).map(|device| {
        (
            device.publicly_serving,
            device.public_probe_error.clone(),
            device.public_probe_at.clone(),
        )
    });
    let (publicly_serving, public_probe_error, public_probe_at) =
        previous_probe.unwrap_or((false, None, None));
    let node_id = req.node_id.clone();
    devices.insert(
        node_id,
        build_heartbeat_device(req, publicly_serving, public_probe_error, public_probe_at),
    );
    drop(devices);
    let _ = state.persist().await;
    Json(serde_json::json!({ "accepted": true }))
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

async fn issue_command(
    State(state): State<AppState>,
    Extension(context): Extension<RequestContext>,
    Path(id): Path<String>,
    Json(req): Json<IssueCommandRequest>,
) -> Json<DeviceCommand> {
    let mut commands = state.commands.lock().await;
    let dedupe_key = format!("{id}:{}", req.idempotency_key);
    if let Some(existing_id) = commands.idempotency.get(&dedupe_key).copied()
        && let Some(existing) = commands.queues.get(&id).and_then(|queue| {
            queue
                .iter()
                .find(|command| command.command_id == existing_id)
        })
    {
        return Json(existing.clone());
    }

    let command = DeviceCommand {
        command_id: CommandId::from_uuid(Uuid::new_v4()),
        device_id: id.clone(),
        desired_state: req.desired_state,
        recovery_intent: req.recovery_intent,
        deadline_secs: req.deadline_secs,
        idempotency_key: req.idempotency_key,
        issued_at: now_unix_secs(),
    };
    let queue = commands.queues.entry(id.clone()).or_default();
    queue.push_back(command.clone());
    if queue.len() > 50 {
        queue.pop_front();
    }
    commands.idempotency.insert(dedupe_key, command.command_id);
    if commands.idempotency.len() > 1000 {
        let keys_to_remove: Vec<String> = commands.idempotency.keys().take(200).cloned().collect();
        for k in keys_to_remove {
            commands.idempotency.remove(&k);
        }
    }
    drop(commands);

    let mut devices = state.devices.lock().await;
    if let Some(device) = devices.get_mut(&id) {
        device.desired_state = Some(command.desired_state.to_string());
        device.recovery_intent = Some(command.recovery_intent.to_string());
        device.last_event_at = Some(command.issued_at.clone());
    }
    drop(devices);
    let _ = state.persist().await;
    tracing::info!(
        request_id = %context.request_id(),
        correlation_id = %context.correlation_id(),
        command_id = %command.command_id,
        device_id = %id,
        "device command accepted"
    );
    Json(command)
}

async fn next_command(
    State(state): State<AppState>,
    Path(id): Path<String>,
) -> Json<Option<DeviceCommand>> {
    let commands = state.commands.lock().await;
    let next = commands
        .queues
        .get(&id)
        .and_then(|queue| queue.front().cloned());
    Json(next)
}

async fn ack_command(
    State(state): State<AppState>,
    Path((id, command_id)): Path<(String, CommandId)>,
    Json(req): Json<CommandAckRequest>,
) -> Json<serde_json::Value> {
    let mut removed = false;
    let mut commands = state.commands.lock().await;
    if req.ok
        && let Some(queue) = commands.queues.get_mut(&id)
        && let Some(index) = queue
            .iter()
            .position(|command| command.command_id == command_id)
    {
        queue.remove(index);
        removed = true;
    }
    drop(commands);

    if req.ok {
        let mut devices = state.devices.lock().await;
        if let Some(device) = devices.get_mut(&id) {
            device.recovery_intent = Some(RecoveryIntent::None.to_string());
            device.last_event_at = Some(now_unix_secs());
        }
        drop(devices);
        let _ = state.persist().await;
    }

    Json(serde_json::json!({ "accepted": removed || !req.ok }))
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
