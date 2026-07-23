#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASELINE_MAIN = "dd49efd7d90c85ecd6f9a05ab99744b137ff6042"


def replace_once(path: str, old: str, new: str) -> None:
    target = ROOT / path
    body = target.read_text(encoding="utf-8")
    count = body.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected exactly one replacement anchor, found {count}: {old!r}")
    target.write_text(body.replace(old, new, 1), encoding="utf-8")


def write(path: str, body: str) -> None:
    target = ROOT / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(body, encoding="utf-8")


write(
    "crates/application/src/device_registration.rs",
    r'''use std::error::Error;
use std::fmt::{Display, Formatter};
use std::future::Future;
use std::pin::Pin;

use proxy_core::RegisterDeviceRequest;

pub const MAX_REGISTERED_DEVICES: usize = 10_000;

#[derive(Debug, Clone)]
pub struct RegisterDeviceInput {
    pub request: RegisterDeviceRequest,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum RegisterDeviceOutcome {
    Created,
    AlreadyRegistered,
}

impl RegisterDeviceOutcome {
    pub const fn accepted(self) -> bool {
        matches!(self, Self::Created | Self::AlreadyRegistered)
    }

    pub const fn classification(self) -> &'static str {
        match self {
            Self::Created => "created",
            Self::AlreadyRegistered => "already_registered",
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum RegisterDeviceError {
    StateConflict,
    CapacityExceeded,
    Persistence,
}

impl Display for RegisterDeviceError {
    fn fmt(&self, formatter: &mut Formatter<'_>) -> std::fmt::Result {
        formatter.write_str(match self {
            Self::StateConflict => "persisted device registry is internally inconsistent",
            Self::CapacityExceeded => "registered device capacity is exhausted",
            Self::Persistence => "device registration state could not be persisted",
        })
    }
}

impl Error for RegisterDeviceError {}

pub type RegisterDeviceFuture<'a> =
    Pin<Box<dyn Future<Output = Result<RegisterDeviceOutcome, RegisterDeviceError>> + Send + 'a>>;

pub trait RegisterDevicePort {
    fn register_device(&self, input: RegisterDeviceInput) -> RegisterDeviceFuture<'_>;
}

#[cfg(test)]
mod tests {
    use super::{MAX_REGISTERED_DEVICES, RegisterDeviceOutcome};

    #[test]
    fn registration_outcomes_preserve_the_existing_accepted_shape() {
        assert!(RegisterDeviceOutcome::Created.accepted());
        assert!(RegisterDeviceOutcome::AlreadyRegistered.accepted());
    }

    #[test]
    fn registration_classifications_are_bounded() {
        assert_eq!(RegisterDeviceOutcome::Created.classification(), "created");
        assert_eq!(
            RegisterDeviceOutcome::AlreadyRegistered.classification(),
            "already_registered"
        );
        assert!(MAX_REGISTERED_DEVICES > 0);
    }
}
''',
)

replace_once(
    "crates/application/src/lib.rs",
    '''mod command_delivery;
mod command_issue;
''',
    '''mod command_delivery;
mod command_issue;
mod device_registration;
''',
)
replace_once(
    "crates/application/src/lib.rs",
    '''pub use command_issue::{
''',
    '''pub use device_registration::{
    MAX_REGISTERED_DEVICES, RegisterDeviceError, RegisterDeviceFuture, RegisterDeviceInput,
    RegisterDeviceOutcome, RegisterDevicePort,
};
pub use command_issue::{
''',
)

replace_once(
    "services/control-plane/src/state.rs",
    '''use mobile_proxy_application::{
    AcknowledgeCommandError, AcknowledgeCommandFuture, AcknowledgeCommandInput,
    AcknowledgeCommandOutcome, AcknowledgeCommandPort, IssueCommandError, IssueCommandFuture,
    IssueCommandInput, IssueCommandOutcome, IssueCommandPort, MAX_COMMAND_QUEUE_PER_DEVICE,
    MAX_IDEMPOTENCY_RESULTS, MAX_PENDING_COMMANDS, PollCommandError, PollCommandFuture,
    PollCommandInput, PollCommandOutcome, PollCommandPort, classify_existing,
    idempotency_scope_key,
};
''',
    '''use mobile_proxy_application::{
    AcknowledgeCommandError, AcknowledgeCommandFuture, AcknowledgeCommandInput,
    AcknowledgeCommandOutcome, AcknowledgeCommandPort, IssueCommandError, IssueCommandFuture,
    IssueCommandInput, IssueCommandOutcome, IssueCommandPort, MAX_COMMAND_QUEUE_PER_DEVICE,
    MAX_IDEMPOTENCY_RESULTS, MAX_PENDING_COMMANDS, MAX_REGISTERED_DEVICES, PollCommandError,
    PollCommandFuture, PollCommandInput, PollCommandOutcome, PollCommandPort, RegisterDeviceError,
    RegisterDeviceFuture, RegisterDeviceInput, RegisterDeviceOutcome, RegisterDevicePort,
    classify_existing, idempotency_scope_key,
};
''',
)
replace_once(
    "services/control-plane/src/state.rs",
    "use crate::projection::now_unix_secs;\n",
    "use crate::projection::{build_registered_device, now_unix_secs};\n",
)
replace_once(
    "services/control-plane/src/state.rs",
    '''    pub async fn persist(&self) -> Result<()> {
        let devices = self.devices.lock().await;
        let commands = self.commands.lock().await;
        let stored = StoredState {
            devices: devices.clone(),
            commands: commands.clone(),
        };
        write_stored_state(self.state_path.as_ref(), &stored)
    }

    async fn issue_command_transaction(
''',
    '''    pub async fn persist(&self) -> Result<()> {
        let devices = self.devices.lock().await;
        let commands = self.commands.lock().await;
        let stored = StoredState {
            devices: devices.clone(),
            commands: commands.clone(),
        };
        write_stored_state(self.state_path.as_ref(), &stored)
    }

    async fn register_device_transaction(
        &self,
        input: RegisterDeviceInput,
    ) -> Result<RegisterDeviceOutcome, RegisterDeviceError> {
        let mut devices_guard = self.devices.lock().await;
        let commands_guard = self.commands.lock().await;
        let mut devices = devices_guard.clone();
        let request = input.request;
        let node_id = request.node_id.clone();

        let outcome = if let Some(existing) = devices.get(&node_id) {
            if existing.node_id != node_id {
                return Err(RegisterDeviceError::StateConflict);
            }
            RegisterDeviceOutcome::AlreadyRegistered
        } else {
            if devices.len() >= MAX_REGISTERED_DEVICES {
                return Err(RegisterDeviceError::CapacityExceeded);
            }
            let device = build_registered_device(request);
            let stored_node_id = device.node_id.clone();
            if devices.insert(stored_node_id, device).is_some() {
                return Err(RegisterDeviceError::StateConflict);
            }
            RegisterDeviceOutcome::Created
        };

        let stored = StoredState {
            devices: devices.clone(),
            commands: commands_guard.clone(),
        };
        write_stored_state(self.state_path.as_ref(), &stored)
            .map_err(|_| RegisterDeviceError::Persistence)?;
        *devices_guard = devices;
        Ok(outcome)
    }

    async fn issue_command_transaction(
''',
)
replace_once(
    "services/control-plane/src/state.rs",
    '''impl IssueCommandPort for AppState {
''',
    '''impl RegisterDevicePort for AppState {
    fn register_device(&self, input: RegisterDeviceInput) -> RegisterDeviceFuture<'_> {
        Box::pin(async move { self.register_device_transaction(input).await })
    }
}

impl IssueCommandPort for AppState {
''',
)
replace_once(
    "services/control-plane/src/state.rs",
    '''    use mobile_proxy_application::{
        AcknowledgeCommandError, AcknowledgeCommandInput, AcknowledgeCommandOutcome,
        AcknowledgeCommandPort, IssueCommandError, IssueCommandInput, IssueCommandOutcome,
        IssueCommandPort, MAX_COMMAND_QUEUE_PER_DEVICE, MAX_PENDING_COMMANDS, PollCommandError,
        PollCommandInput, PollCommandOutcome, PollCommandPort, idempotency_scope_key,
    };
''',
    '''    use mobile_proxy_application::{
        AcknowledgeCommandError, AcknowledgeCommandInput, AcknowledgeCommandOutcome,
        AcknowledgeCommandPort, IssueCommandError, IssueCommandInput, IssueCommandOutcome,
        IssueCommandPort, MAX_COMMAND_QUEUE_PER_DEVICE, MAX_PENDING_COMMANDS,
        MAX_REGISTERED_DEVICES, PollCommandError, PollCommandInput, PollCommandOutcome,
        PollCommandPort, RegisterDeviceError, RegisterDeviceInput, RegisterDeviceOutcome,
        RegisterDevicePort, idempotency_scope_key,
    };
''',
)
replace_once(
    "services/control-plane/src/state.rs",
    '''    use proxy_core::{
        CommandAckRequest, DesiredState, DeviceCommand, IssueCommandRequest, RecoveryIntent,
    };
''',
    '''    use proxy_core::{
        CommandAckRequest, DesiredState, DeviceCommand, IssueCommandRequest, RecoveryIntent,
        RegisterDeviceRequest,
    };
''',
)
replace_once(
    "services/control-plane/src/state.rs",
    '''    use super::{AppState, CommandState};
''',
    '''    use crate::projection::build_registered_device;

    use super::{AppState, CommandState};
''',
)
replace_once(
    "services/control-plane/src/state.rs",
    '''    fn acknowledgement(command_id: CommandId, ok: bool) -> AcknowledgeCommandInput {
        AcknowledgeCommandInput {
            device_id: "device-1".into(),
            command_id,
            request: CommandAckRequest { ok, message: None },
        }
    }

    #[tokio::test]
''',
    '''    fn acknowledgement(command_id: CommandId, ok: bool) -> AcknowledgeCommandInput {
        AcknowledgeCommandInput {
            device_id: "device-1".into(),
            command_id,
            request: CommandAckRequest { ok, message: None },
        }
    }

    fn registration(node_id: &str, node_name: &str) -> RegisterDeviceInput {
        RegisterDeviceInput {
            request: RegisterDeviceRequest {
                node_id: node_id.into(),
                node_name: node_name.into(),
                proxy_status: "starting".into(),
                tunnel_owner: Some("stock_wireguard_bridge".into()),
            },
        }
    }

    #[tokio::test]
''',
)
replace_once(
    "services/control-plane/src/state.rs",
    '''    #[tokio::test]
    async fn failed_persistence_does_not_publish_in_memory_command() {
''',
    '''    #[tokio::test]
    async fn registration_is_durable_and_preserves_first_registered_metadata() {
        let path = std::env::temp_dir().join(format!(
            "mobile-proxy-control-plane-device-registration-{}.json",
            Uuid::new_v4()
        ));
        let state = AppState::load(path.clone()).await.unwrap();
        assert_eq!(
            state
                .register_device(registration("device-1", "first-name"))
                .await
                .unwrap(),
            RegisterDeviceOutcome::Created
        );
        assert_eq!(
            state
                .register_device(RegisterDeviceInput {
                    request: RegisterDeviceRequest {
                        node_id: "device-1".into(),
                        node_name: "changed-name".into(),
                        proxy_status: "running".into(),
                        tunnel_owner: Some("first_party_reverse_tunnel".into()),
                    },
                })
                .await
                .unwrap(),
            RegisterDeviceOutcome::AlreadyRegistered
        );
        let registered = state
            .devices
            .lock()
            .await
            .get("device-1")
            .unwrap()
            .clone();
        assert_eq!(registered.node_name, "first-name");
        assert_eq!(registered.proxy_status, "starting");
        assert_eq!(
            registered.tunnel_owner.as_deref(),
            Some("stock_wireguard_bridge")
        );
        drop(state);

        let restarted = AppState::load(path.clone()).await.unwrap();
        let registered = restarted
            .devices
            .lock()
            .await
            .get("device-1")
            .unwrap()
            .clone();
        assert_eq!(registered.node_name, "first-name");
        assert_eq!(registered.proxy_status, "starting");
        let _ = fs::remove_file(path);
    }

    #[tokio::test]
    async fn failed_registration_persistence_does_not_publish_a_new_device() {
        let blocking_parent = std::env::temp_dir().join(format!(
            "mobile-proxy-control-plane-registration-persistence-{}",
            Uuid::new_v4()
        ));
        fs::write(&blocking_parent, b"not a directory").unwrap();
        let state = AppState {
            devices: Arc::new(Mutex::new(HashMap::new())),
            commands: Arc::new(Mutex::new(CommandState::default())),
            state_path: Arc::new(blocking_parent.join("state.json")),
        };

        assert_eq!(
            state.register_device(registration("device-1", "node")).await,
            Err(RegisterDeviceError::Persistence)
        );
        assert!(state.devices.lock().await.is_empty());
        let _ = fs::remove_file(blocking_parent);
    }

    #[tokio::test]
    async fn duplicate_registration_reports_persistence_failure() {
        let blocking_parent = std::env::temp_dir().join(format!(
            "mobile-proxy-control-plane-registration-replay-persistence-{}",
            Uuid::new_v4()
        ));
        fs::write(&blocking_parent, b"not a directory").unwrap();
        let device = build_registered_device(registration("device-1", "node").request);
        let mut devices = HashMap::new();
        devices.insert("device-1".into(), device);
        let state = AppState {
            devices: Arc::new(Mutex::new(devices)),
            commands: Arc::new(Mutex::new(CommandState::default())),
            state_path: Arc::new(blocking_parent.join("state.json")),
        };

        assert_eq!(
            state.register_device(registration("device-1", "node")).await,
            Err(RegisterDeviceError::Persistence)
        );
        assert_eq!(state.devices.lock().await.len(), 1);
        let _ = fs::remove_file(blocking_parent);
    }

    #[tokio::test]
    async fn registered_device_capacity_is_bounded() {
        let template = build_registered_device(registration("template", "template").request);
        let mut devices = HashMap::new();
        for index in 0..MAX_REGISTERED_DEVICES {
            let node_id = format!("device-{index}");
            let mut device = template.clone();
            device.node_id = node_id.clone();
            device.node_name = node_id.clone();
            devices.insert(node_id, device);
        }
        let state = AppState {
            devices: Arc::new(Mutex::new(devices)),
            commands: Arc::new(Mutex::new(CommandState::default())),
            state_path: Arc::new(std::path::PathBuf::from("unused")),
        };

        assert_eq!(
            state
                .register_device(registration("overflow-device", "overflow"))
                .await,
            Err(RegisterDeviceError::CapacityExceeded)
        );
        assert_eq!(state.devices.lock().await.len(), MAX_REGISTERED_DEVICES);
    }

    #[tokio::test]
    async fn registration_fails_closed_on_a_mismatched_stored_device() {
        let mismatched = build_registered_device(registration("device-2", "node").request);
        let mut devices = HashMap::new();
        devices.insert("device-1".into(), mismatched);
        let state = AppState {
            devices: Arc::new(Mutex::new(devices)),
            commands: Arc::new(Mutex::new(CommandState::default())),
            state_path: Arc::new(std::path::PathBuf::from("unused")),
        };

        assert_eq!(
            state.register_device(registration("device-1", "node")).await,
            Err(RegisterDeviceError::StateConflict)
        );
    }

    #[tokio::test]
    async fn failed_persistence_does_not_publish_in_memory_command() {
''',
)

replace_once(
    "services/control-plane/src/routes.rs",
    '''use crate::projection::{
    apply_public_probe, build_heartbeat_device, build_registered_device, now_unix_secs,
};
''',
    '''use crate::projection::{apply_public_probe, build_heartbeat_device, now_unix_secs};
''',
)
replace_once(
    "services/control-plane/src/routes.rs",
    '''use mobile_proxy_application::{
    AcknowledgeCommandError, AcknowledgeCommandInput, AcknowledgeCommandPort, IssueCommandError,
    IssueCommandInput, IssueCommandPort, PollCommandError, PollCommandInput, PollCommandPort,
};
''',
    '''use mobile_proxy_application::{
    AcknowledgeCommandError, AcknowledgeCommandInput, AcknowledgeCommandPort, IssueCommandError,
    IssueCommandInput, IssueCommandPort, PollCommandError, PollCommandInput, PollCommandPort,
    RegisterDeviceError, RegisterDeviceInput, RegisterDevicePort,
};
''',
)
replace_once(
    "services/control-plane/src/routes.rs",
    '''async fn register_device(
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
''',
    '''async fn register_device(
    State(state): State<AppState>,
    Extension(context): Extension<RequestContext>,
    Json(req): Json<RegisterDeviceRequest>,
) -> Result<Json<serde_json::Value>, ControlPlaneRouteError> {
    let node_id = req.node_id.clone();
    match state
        .register_device(RegisterDeviceInput { request: req })
        .await
    {
        Ok(outcome) => {
            tracing::info!(
                request_id = %context.request_id(),
                correlation_id = %context.correlation_id(),
                node_id = %node_id,
                classification = outcome.classification(),
                "device registration processed"
            );
            Ok(Json(serde_json::json!({ "accepted": outcome.accepted() })))
        }
        Err(RegisterDeviceError::StateConflict) => {
            tracing::error!(
                request_id = %context.request_id(),
                correlation_id = %context.correlation_id(),
                node_id = %node_id,
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
                node_id = %node_id,
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
                node_id = %node_id,
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
''',
)
routes_path = ROOT / "services/control-plane/src/routes.rs"
routes_body = routes_path.read_text(encoding="utf-8")
if routes_body.count("CommandRouteError") != 4:
    raise SystemExit(
        f"services/control-plane/src/routes.rs: expected four CommandRouteError anchors, found {routes_body.count('CommandRouteError')}"
    )
routes_path.write_text(
    routes_body.replace("CommandRouteError", "ControlPlaneRouteError"),
    encoding="utf-8",
)
replace_once(
    "services/control-plane/src/routes.rs",
    '''    #[tokio::test]
    async fn typed_command_boundary_preserves_json_and_deduplicates() {
''',
    '''    #[tokio::test]
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
''',
)

catalog_path = ROOT / "contracts/governance/invariant-enforcement.json"
catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
catalog["audit_revision"] = "2026-07-24"
catalog["baseline_main_sha"] = BASELINE_MAIN
rows = {row[0]: row for row in catalog["invariants"]}
for invariant_id in ("ARCH-004", "ARCH-005", "PERSIST-003"):
    if invariant_id not in rows:
        raise SystemExit(f"missing invariant row: {invariant_id}")


def add_evidence(invariant_id: str, path: str) -> None:
    evidence = rows[invariant_id][6]
    if path not in evidence:
        evidence.append(path)


add_evidence("ARCH-004", "crates/application/src/device_registration.rs")
add_evidence("ARCH-005", "crates/application/src/device_registration.rs")
add_evidence("PERSIST-003", "crates/application/src/device_registration.rs")
rows["ARCH-004"][10] = (
    "Command issuance, device registration and successful acknowledgement mutate through typed "
    "application ports; heartbeat and probe are still direct handlers."
)
rows["ARCH-005"][10] = (
    "Command issue, poll, acknowledgement and device registration handlers authenticate at the "
    "router, call one typed use case and map typed outcomes; heartbeat and probe remain transitional."
)
rows["PERSIST-003"][10] = (
    "Command issuance, successful acknowledgement and device registration write their complete "
    "JSON candidate before in-memory publication; domain event, audit and outbox persistence are absent."
)
catalog_path.write_text(json.dumps(catalog, indent=2) + "\n", encoding="utf-8")

replace_once(
    "docs/architecture/invariant-enforcement.md",
    "Baseline `main`: `960745007e543c9245a69e57a4856b4f39ab3730`",
    f"Baseline `main`: `{BASELINE_MAIN}`",
)
replace_once(
    "docs/architecture/invariant-enforcement.md",
    "- thin transport handlers beyond the extracted command lifecycle routes and prohibition of SQL or business transitions in all HTTP routes;",
    "- thin transport handlers beyond the extracted command lifecycle and device-registration routes, plus prohibition of SQL or business transitions in all HTTP routes;",
)
replace_once(
    "docs/architecture/invariant-enforcement.md",
    '''## Command lifecycle application-port enforcement

The existing command issue, poll and acknowledgement capabilities now have bounded clean-dependency slices:

- `mobile-proxy-application` owns the typed port, deterministic request fingerprint, unambiguous BLAKE3 idempotency scope and exact/conflict classification;
- the Axum handler calls one use case and maps only typed outcomes to bounded HTTP errors;
- raw idempotency keys are not logged;
- original results are persisted separately from the bounded delivery queue, so acknowledgement or queue eviction cannot turn an exact replay into a new command;
- legacy concatenated idempotency claims are normalized through an isolated adapter when their original queued command is recoverable, while stale claims reject reuse fail closed;
- command queue, idempotency claim/result and device projection are fsynced and atomically renamed before in-memory publication;
- a failed write returns `state_persistence_failed` and leaves the in-memory state unchanged.

Command polling validates queue ownership and returns a typed pending-or-empty outcome without transport logic reaching into the queue. Successful acknowledgement removes the command and updates the device projection in one fsynced candidate before publishing either in memory. Negative acknowledgement preserves the pending command and the existing `{ "accepted": true }` compatibility shape.

Registration, heartbeat and public probe remain transitional and keep `ARCH-004` and `ARCH-005` at `partially_enforced`.
''',
    '''## Command lifecycle and device-registration application-port enforcement

The existing command issue, poll, acknowledgement and device-registration capabilities now have bounded clean-dependency slices:

- `mobile-proxy-application` owns typed ports and bounded outcomes;
- command issuance retains deterministic request fingerprints, unambiguous BLAKE3 idempotency scope and exact/conflict classification;
- Axum handlers call one use case and map only typed outcomes to bounded HTTP errors;
- raw idempotency keys are not logged;
- original command results are persisted separately from the bounded delivery queue, so acknowledgement or queue eviction cannot turn an exact replay into a new command;
- legacy concatenated idempotency claims are normalized through an isolated adapter when their original queued command is recoverable, while stale claims reject reuse fail closed;
- command queue, idempotency claim/result and device projection are fsynced and atomically renamed before in-memory publication;
- command polling validates queue ownership and returns a typed pending-or-empty outcome without transport logic reaching into the queue;
- successful acknowledgement removes the command and updates the device projection in one fsynced candidate before publishing either in memory;
- negative acknowledgement preserves the pending command and the existing `{ "accepted": true }` compatibility shape;
- device registration uses `node_id` as its natural replay key, preserves first-write metadata and bounds the JSON-era registry at 10,000 devices;
- new and repeated registration persist the complete candidate before returning `{ "accepted": true }`;
- a failed write returns `state_persistence_failed` and does not publish a new device in memory.

Heartbeat and public probe remain transitional and keep `ARCH-004` and `ARCH-005` at `partially_enforced`.
''',
)

write(
    "docs/architecture/device-registration-application-port.md",
    '''# Device registration application port

Status: production migration slice  
Scope: existing `POST /api/v1/devices/register` route

## Contract

`mobile-proxy-application` owns the transport-independent device-registration port. Axum authenticates the device request, decodes the existing JSON request, invokes one use case and maps typed outcomes. The application crate has no runtime, filesystem, process, network or framework dependency.

## Replay and compatibility semantics

The HTTP request and response shapes are unchanged. Successful first registration and a repeated registration both return `{ "accepted": true }`.

`node_id` is the natural replay key during the JSON migration period:

- the first accepted registration creates the initial device projection;
- a repeated registration does not overwrite the first registered `node_name`, `proxy_status` or `tunnel_owner`;
- mutable runtime state continues to arrive through heartbeat rather than registration;
- a persisted map whose key disagrees with the stored device `node_id` fails closed as `device_state_conflict`.

This preserves restart compatibility for the host daemon while preventing registration retries from silently rewriting canonical device metadata.

## Persistence ordering

Registration is a candidate transaction over the complete JSON-era device and command state:

1. lock device and command state in the established order;
2. clone the bounded device registry;
3. classify the request as `created` or `already_registered`;
4. serialize the complete candidate;
5. fsync the temporary file and atomically rename it;
6. publish a newly created device in memory only after the durable write succeeds.

A failed write returns `state_persistence_failed`. A new device is not published in memory, and a repeated registration is not acknowledged as durable when the backing state cannot be written.

## Capacity and typed failures

The transitional JSON registry is bounded at 10,000 devices. A new registration beyond that limit returns `device_capacity_exceeded` without evicting an existing device. Internal key/value disagreement returns `device_state_conflict`.

## Explicitly deferred

SQLite canonical storage, per-device cryptographic identity, durable registration history, domain events, audit, outbox, metrics and replacement of the shared device bearer token remain later bounded slices. Heartbeat and public-probe handlers are still transitional.
''',
)
