#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(path: str, old: str, new: str) -> None:
    target = ROOT / path
    body = target.read_text(encoding="utf-8")
    count = body.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected exactly one replacement anchor, found {count}")
    target.write_text(body.replace(old, new, 1), encoding="utf-8")


def write(path: str, body: str) -> None:
    target = ROOT / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(body, encoding="utf-8")


write(
    "crates/application/src/command_delivery.rs",
    r'''use std::error::Error;
use std::fmt::{Display, Formatter};
use std::future::Future;
use std::pin::Pin;

use mobile_proxy_foundation::CommandId;
use proxy_core::{CommandAckRequest, DeviceCommand};

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct PollCommandInput {
    pub device_id: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum PollCommandOutcome {
    Available(DeviceCommand),
    Empty,
}

impl PollCommandOutcome {
    pub fn into_option(self) -> Option<DeviceCommand> {
        match self {
            Self::Available(command) => Some(command),
            Self::Empty => None,
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum PollCommandError {
    StateConflict,
}

impl Display for PollCommandError {
    fn fmt(&self, formatter: &mut Formatter<'_>) -> std::fmt::Result {
        formatter.write_str("persisted command queue is internally inconsistent")
    }
}

impl Error for PollCommandError {}

pub type PollCommandFuture<'a> =
    Pin<Box<dyn Future<Output = Result<PollCommandOutcome, PollCommandError>> + Send + 'a>>;

pub trait PollCommandPort {
    fn poll_command(&self, input: PollCommandInput) -> PollCommandFuture<'_>;
}

#[derive(Debug, Clone)]
pub struct AcknowledgeCommandInput {
    pub device_id: String,
    pub command_id: CommandId,
    pub request: CommandAckRequest,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum AcknowledgeCommandOutcome {
    Acknowledged,
    RetryRequested,
    NotPending,
}

impl AcknowledgeCommandOutcome {
    pub fn accepted(self) -> bool {
        matches!(self, Self::Acknowledged | Self::RetryRequested)
    }

    pub fn classification(self) -> &'static str {
        match self {
            Self::Acknowledged => "acknowledged",
            Self::RetryRequested => "retry_requested",
            Self::NotPending => "not_pending",
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum AcknowledgeCommandError {
    StateConflict,
    Persistence,
}

impl Display for AcknowledgeCommandError {
    fn fmt(&self, formatter: &mut Formatter<'_>) -> std::fmt::Result {
        formatter.write_str(match self {
            Self::StateConflict => "persisted command queue is internally inconsistent",
            Self::Persistence => "command acknowledgement state could not be persisted",
        })
    }
}

impl Error for AcknowledgeCommandError {}

pub type AcknowledgeCommandFuture<'a> = Pin<
    Box<
        dyn Future<Output = Result<AcknowledgeCommandOutcome, AcknowledgeCommandError>>
            + Send
            + 'a,
    >,
>;

pub trait AcknowledgeCommandPort {
    fn acknowledge_command(
        &self,
        input: AcknowledgeCommandInput,
    ) -> AcknowledgeCommandFuture<'_>;
}

#[cfg(test)]
mod tests {
    use super::AcknowledgeCommandOutcome;

    #[test]
    fn acknowledgement_outcomes_preserve_the_existing_accepted_shape() {
        assert!(AcknowledgeCommandOutcome::Acknowledged.accepted());
        assert!(AcknowledgeCommandOutcome::RetryRequested.accepted());
        assert!(!AcknowledgeCommandOutcome::NotPending.accepted());
    }

    #[test]
    fn acknowledgement_classifications_are_bounded() {
        assert_eq!(
            AcknowledgeCommandOutcome::Acknowledged.classification(),
            "acknowledged"
        );
        assert_eq!(
            AcknowledgeCommandOutcome::RetryRequested.classification(),
            "retry_requested"
        );
        assert_eq!(
            AcknowledgeCommandOutcome::NotPending.classification(),
            "not_pending"
        );
    }
}
''',
)

replace_once(
    "crates/application/src/lib.rs",
    '''mod command_issue;

pub use command_issue::{
''',
    '''mod command_delivery;
mod command_issue;

pub use command_delivery::{
    AcknowledgeCommandError, AcknowledgeCommandFuture, AcknowledgeCommandInput,
    AcknowledgeCommandOutcome, AcknowledgeCommandPort, PollCommandError, PollCommandFuture,
    PollCommandInput, PollCommandOutcome, PollCommandPort,
};

pub use command_issue::{
''',
)

replace_once(
    "services/control-plane/src/state.rs",
    '''use mobile_proxy_application::{
    IssueCommandError, IssueCommandFuture, IssueCommandInput, IssueCommandOutcome,
    IssueCommandPort, MAX_COMMAND_QUEUE_PER_DEVICE, MAX_IDEMPOTENCY_RESULTS, MAX_PENDING_COMMANDS,
    classify_existing, idempotency_scope_key,
};
use mobile_proxy_foundation::CommandId;
use proxy_core::{DeviceCommand, DeviceRecord};
''',
    '''use mobile_proxy_application::{
    AcknowledgeCommandError, AcknowledgeCommandFuture, AcknowledgeCommandInput,
    AcknowledgeCommandOutcome, AcknowledgeCommandPort, IssueCommandError, IssueCommandFuture,
    IssueCommandInput, IssueCommandOutcome, IssueCommandPort, MAX_COMMAND_QUEUE_PER_DEVICE,
    MAX_IDEMPOTENCY_RESULTS, MAX_PENDING_COMMANDS, PollCommandError, PollCommandFuture,
    PollCommandInput, PollCommandOutcome, PollCommandPort, classify_existing,
    idempotency_scope_key,
};
use mobile_proxy_foundation::CommandId;
use proxy_core::{DeviceCommand, DeviceRecord, RecoveryIntent};
''',
)

replace_once(
    "services/control-plane/src/state.rs",
    '''        *commands_guard = commands;
        Ok(IssueCommandOutcome::Created(command))
    }
}

impl IssueCommandPort for AppState {
''',
    '''        *commands_guard = commands;
        Ok(IssueCommandOutcome::Created(command))
    }

    async fn poll_command_transaction(
        &self,
        input: PollCommandInput,
    ) -> Result<PollCommandOutcome, PollCommandError> {
        let commands = self.commands.lock().await;
        let Some(command) = commands
            .queues
            .get(&input.device_id)
            .and_then(|queue| queue.front())
            .cloned()
        else {
            return Ok(PollCommandOutcome::Empty);
        };
        if command.device_id != input.device_id {
            return Err(PollCommandError::StateConflict);
        }
        Ok(PollCommandOutcome::Available(command))
    }

    async fn acknowledge_command_transaction(
        &self,
        input: AcknowledgeCommandInput,
    ) -> Result<AcknowledgeCommandOutcome, AcknowledgeCommandError> {
        let mut devices_guard = self.devices.lock().await;
        let mut commands_guard = self.commands.lock().await;
        let mut devices = devices_guard.clone();
        let mut commands = commands_guard.clone();

        let pending_index = commands.queues.get(&input.device_id).and_then(|queue| {
            queue
                .iter()
                .position(|command| command.command_id == input.command_id)
        });

        if !input.request.ok {
            if let Some(index) = pending_index {
                let command = commands
                    .queues
                    .get(&input.device_id)
                    .and_then(|queue| queue.get(index))
                    .ok_or(AcknowledgeCommandError::StateConflict)?;
                if command.device_id != input.device_id
                    || command.command_id != input.command_id
                {
                    return Err(AcknowledgeCommandError::StateConflict);
                }
            }
            return Ok(AcknowledgeCommandOutcome::RetryRequested);
        }

        let Some(index) = pending_index else {
            return Ok(AcknowledgeCommandOutcome::NotPending);
        };
        let command = commands
            .queues
            .get(&input.device_id)
            .and_then(|queue| queue.get(index))
            .cloned()
            .ok_or(AcknowledgeCommandError::StateConflict)?;
        if command.device_id != input.device_id || command.command_id != input.command_id {
            return Err(AcknowledgeCommandError::StateConflict);
        }
        let removed = commands
            .queues
            .get_mut(&input.device_id)
            .and_then(|queue| queue.remove(index))
            .ok_or(AcknowledgeCommandError::StateConflict)?;
        if removed != command {
            return Err(AcknowledgeCommandError::StateConflict);
        }
        if commands
            .queues
            .get(&input.device_id)
            .is_some_and(VecDeque::is_empty)
        {
            commands.queues.remove(&input.device_id);
        }

        if let Some(device) = devices.get_mut(&input.device_id) {
            device.recovery_intent = Some(RecoveryIntent::None.to_string());
            device.last_event_at = Some(now_unix_secs());
        }

        let stored = StoredState {
            devices: devices.clone(),
            commands: commands.clone(),
        };
        write_stored_state(self.state_path.as_ref(), &stored)
            .map_err(|_| AcknowledgeCommandError::Persistence)?;
        *devices_guard = devices;
        *commands_guard = commands;
        Ok(AcknowledgeCommandOutcome::Acknowledged)
    }
}

impl IssueCommandPort for AppState {
''',
)

replace_once(
    "services/control-plane/src/state.rs",
    '''impl IssueCommandPort for AppState {
    fn issue_command(&self, input: IssueCommandInput) -> IssueCommandFuture<'_> {
        Box::pin(async move { self.issue_command_transaction(input).await })
    }
}

fn legacy_idempotency_scope_key(input: &IssueCommandInput) -> String {
''',
    '''impl IssueCommandPort for AppState {
    fn issue_command(&self, input: IssueCommandInput) -> IssueCommandFuture<'_> {
        Box::pin(async move { self.issue_command_transaction(input).await })
    }
}

impl PollCommandPort for AppState {
    fn poll_command(&self, input: PollCommandInput) -> PollCommandFuture<'_> {
        Box::pin(async move { self.poll_command_transaction(input).await })
    }
}

impl AcknowledgeCommandPort for AppState {
    fn acknowledge_command(&self, input: AcknowledgeCommandInput) -> AcknowledgeCommandFuture<'_> {
        Box::pin(async move { self.acknowledge_command_transaction(input).await })
    }
}

fn legacy_idempotency_scope_key(input: &IssueCommandInput) -> String {
''',
)

replace_once(
    "services/control-plane/src/state.rs",
    '''    use mobile_proxy_application::{
        IssueCommandError, IssueCommandInput, IssueCommandOutcome, IssueCommandPort,
        MAX_COMMAND_QUEUE_PER_DEVICE, MAX_PENDING_COMMANDS, idempotency_scope_key,
    };
    use mobile_proxy_foundation::{CommandId, DeadlineWindow, IdempotencyKey};
    use proxy_core::{DesiredState, DeviceCommand, IssueCommandRequest, RecoveryIntent};
''',
    '''    use mobile_proxy_application::{
        AcknowledgeCommandError, AcknowledgeCommandInput, AcknowledgeCommandOutcome,
        AcknowledgeCommandPort, IssueCommandError, IssueCommandInput, IssueCommandOutcome,
        IssueCommandPort, MAX_COMMAND_QUEUE_PER_DEVICE, MAX_PENDING_COMMANDS, PollCommandInput,
        PollCommandOutcome, PollCommandPort, idempotency_scope_key,
    };
    use mobile_proxy_foundation::{CommandId, DeadlineWindow, IdempotencyKey};
    use proxy_core::{
        CommandAckRequest, DesiredState, DeviceCommand, IssueCommandRequest, RecoveryIntent,
    };
''',
)

replace_once(
    "services/control-plane/src/state.rs",
    '''    fn command_input(desired_state: DesiredState) -> IssueCommandInput {
        IssueCommandInput {
            device_id: "device-1".into(),
            request: IssueCommandRequest {
                desired_state,
                recovery_intent: RecoveryIntent::None,
                deadline_secs: DeadlineWindow::new(30).unwrap(),
                idempotency_key: IdempotencyKey::parse("command-123").unwrap(),
            },
        }
    }

    #[tokio::test]
    async fn legacy_fingerprint_migration_is_restart_safe() {
''',
    '''    fn command_input(desired_state: DesiredState) -> IssueCommandInput {
        IssueCommandInput {
            device_id: "device-1".into(),
            request: IssueCommandRequest {
                desired_state,
                recovery_intent: RecoveryIntent::None,
                deadline_secs: DeadlineWindow::new(30).unwrap(),
                idempotency_key: IdempotencyKey::parse("command-123").unwrap(),
            },
        }
    }

    fn pending_command() -> DeviceCommand {
        DeviceCommand {
            command_id: CommandId::from_uuid(Uuid::from_u128(1)),
            device_id: "device-1".into(),
            desired_state: DesiredState::HealthyServing,
            recovery_intent: RecoveryIntent::None,
            deadline_secs: DeadlineWindow::new(30).unwrap(),
            idempotency_key: IdempotencyKey::parse("command-123").unwrap(),
            issued_at: "1".into(),
        }
    }

    #[tokio::test]
    async fn legacy_fingerprint_migration_is_restart_safe() {
''',
)

replace_once(
    "services/control-plane/src/state.rs",
    '''    #[tokio::test]
    async fn failed_persistence_does_not_publish_in_memory_command() {
''',
    '''    #[tokio::test]
    async fn command_poll_and_acknowledgement_are_typed_and_restart_safe() {
        let path = std::env::temp_dir().join(format!(
            "mobile-proxy-control-plane-command-delivery-{}.json",
            Uuid::new_v4()
        ));
        let state = AppState::load(path.clone()).await.unwrap();
        let issued = state
            .issue_command(command_input(DesiredState::HealthyServing))
            .await
            .unwrap();
        let (_, command) = issued.into_parts();

        assert_eq!(
            state
                .poll_command(PollCommandInput {
                    device_id: "device-1".into(),
                })
                .await
                .unwrap(),
            PollCommandOutcome::Available(command.clone())
        );
        assert_eq!(
            state
                .acknowledge_command(AcknowledgeCommandInput {
                    device_id: "device-1".into(),
                    command_id: command.command_id,
                    request: CommandAckRequest {
                        ok: true,
                        message: None,
                    },
                })
                .await
                .unwrap(),
            AcknowledgeCommandOutcome::Acknowledged
        );
        drop(state);

        let restarted = AppState::load(path.clone()).await.unwrap();
        assert_eq!(
            restarted
                .poll_command(PollCommandInput {
                    device_id: "device-1".into(),
                })
                .await
                .unwrap(),
            PollCommandOutcome::Empty
        );
        let _ = fs::remove_file(path);
    }

    #[tokio::test]
    async fn failed_acknowledgement_keeps_the_command_pending() {
        let path = std::env::temp_dir().join(format!(
            "mobile-proxy-control-plane-command-retry-{}.json",
            Uuid::new_v4()
        ));
        let state = AppState::load(path.clone()).await.unwrap();
        let issued = state
            .issue_command(command_input(DesiredState::HealthyServing))
            .await
            .unwrap();
        let (_, command) = issued.into_parts();
        let result = state
            .acknowledge_command(AcknowledgeCommandInput {
                device_id: "device-1".into(),
                command_id: command.command_id,
                request: CommandAckRequest {
                    ok: false,
                    message: Some("retry".into()),
                },
            })
            .await
            .unwrap();
        assert_eq!(result, AcknowledgeCommandOutcome::RetryRequested);
        assert_eq!(
            state
                .poll_command(PollCommandInput {
                    device_id: "device-1".into(),
                })
                .await
                .unwrap(),
            PollCommandOutcome::Available(command)
        );
        let _ = fs::remove_file(path);
    }

    #[tokio::test]
    async fn failed_ack_persistence_does_not_publish_queue_removal() {
        let blocking_parent = std::env::temp_dir().join(format!(
            "mobile-proxy-control-plane-ack-persistence-{}",
            Uuid::new_v4()
        ));
        fs::write(&blocking_parent, b"not a directory").unwrap();
        let command = pending_command();
        let mut commands = CommandState::default();
        commands
            .queues
            .entry("device-1".into())
            .or_default()
            .push_back(command.clone());
        let state = AppState {
            devices: Arc::new(Mutex::new(HashMap::new())),
            commands: Arc::new(Mutex::new(commands)),
            state_path: Arc::new(blocking_parent.join("state.json")),
        };

        let result = state
            .acknowledge_command(AcknowledgeCommandInput {
                device_id: "device-1".into(),
                command_id: command.command_id,
                request: CommandAckRequest {
                    ok: true,
                    message: None,
                },
            })
            .await;
        assert_eq!(result, Err(AcknowledgeCommandError::Persistence));
        assert_eq!(
            state.commands.lock().await.queues["device-1"].front(),
            Some(&command)
        );
        let _ = fs::remove_file(blocking_parent);
    }

    #[tokio::test]
    async fn failed_persistence_does_not_publish_in_memory_command() {
''',
)

replace_once(
    "services/control-plane/src/routes.rs",
    '''use mobile_proxy_application::{IssueCommandError, IssueCommandInput, IssueCommandPort};
use mobile_proxy_foundation::{CommandId, RequestContext};
use proxy_core::{
    CommandAckRequest, DeviceCommand, DeviceRecord, HeartbeatRequest, IssueCommandRequest,
    PublicProbeReport, RecoveryIntent, RegisterDeviceRequest,
};
''',
    '''use mobile_proxy_application::{
    AcknowledgeCommandError, AcknowledgeCommandInput, AcknowledgeCommandPort, IssueCommandError,
    IssueCommandInput, IssueCommandPort, PollCommandError, PollCommandInput, PollCommandPort,
};
use mobile_proxy_foundation::{CommandId, RequestContext};
use proxy_core::{
    CommandAckRequest, DeviceCommand, DeviceRecord, HeartbeatRequest, IssueCommandRequest,
    PublicProbeReport, RegisterDeviceRequest,
};
''',
)

replace_once(
    "services/control-plane/src/routes.rs",
    '''async fn next_command(
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
''',
    '''async fn next_command(
    State(state): State<AppState>,
    Extension(context): Extension<RequestContext>,
    Path(id): Path<String>,
) -> Result<Json<Option<DeviceCommand>>, CommandRouteError> {
    match state
        .poll_command(PollCommandInput {
            device_id: id.clone(),
        })
        .await
    {
        Ok(outcome) => {
            let command = outcome.into_option();
            tracing::info!(
                request_id = %context.request_id(),
                correlation_id = %context.correlation_id(),
                device_id = %id,
                command_available = command.is_some(),
                "device command polled"
            );
            Ok(Json(command))
        }
        Err(PollCommandError::StateConflict) => {
            tracing::error!(
                request_id = %context.request_id(),
                correlation_id = %context.correlation_id(),
                device_id = %id,
                error_code = "command_state_conflict",
                "device command poll rejected"
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
) -> Result<Json<serde_json::Value>, CommandRouteError> {
    match state
        .acknowledge_command(AcknowledgeCommandInput {
            device_id: id.clone(),
            command_id,
            request: req,
        })
        .await
    {
        Ok(outcome) => {
            let accepted = outcome.accepted();
            tracing::info!(
                request_id = %context.request_id(),
                correlation_id = %context.correlation_id(),
                device_id = %id,
                command_id = %command_id,
                classification = outcome.classification(),
                accepted,
                "device command acknowledgement classified"
            );
            Ok(Json(serde_json::json!({ "accepted": accepted })))
        }
        Err(AcknowledgeCommandError::StateConflict) => {
            tracing::error!(
                request_id = %context.request_id(),
                correlation_id = %context.correlation_id(),
                device_id = %id,
                command_id = %command_id,
                error_code = "command_state_conflict",
                "device command acknowledgement rejected"
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
                device_id = %id,
                command_id = %command_id,
                error_code = "state_persistence_failed",
                "device command acknowledgement rejected"
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

replace_once(
    "services/control-plane/src/routes.rs",
    '''    #[tokio::test]
    async fn legacy_heartbeat_fingerprints_are_accepted_but_not_persisted() {
''',
    '''    #[tokio::test]
    async fn typed_command_delivery_preserves_poll_and_ack_json_shapes() {
        const PAYLOAD: &str = r#"{
            "desired_state":"healthy_serving",
            "recovery_intent":"none",
            "deadline_secs":30,
            "idempotency_key":"delivery-command-123"
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
        let issued_body = axum::body::to_bytes(issued.into_body(), 16 * 1024)
            .await
            .unwrap();
        let command: DeviceCommand = serde_json::from_slice(&issued_body).unwrap();

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
        let polled_body = axum::body::to_bytes(polled.into_body(), 16 * 1024)
            .await
            .unwrap();
        let polled_command: Option<DeviceCommand> = serde_json::from_slice(&polled_body).unwrap();
        assert_eq!(polled_command, Some(command.clone()));

        let acknowledged = app
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
        assert_eq!(acknowledged.status(), StatusCode::OK);
        let acknowledged_body = axum::body::to_bytes(acknowledged.into_body(), 16 * 1024)
            .await
            .unwrap();
        let acknowledged_json: serde_json::Value =
            serde_json::from_slice(&acknowledged_body).unwrap();
        assert_eq!(acknowledged_json["accepted"], true);

        let empty = app
            .oneshot(
                Request::get("/api/v1/devices/device-1/commands/next")
                    .header("authorization", "Bearer device-token")
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(empty.status(), StatusCode::OK);
        let empty_body = axum::body::to_bytes(empty.into_body(), 16 * 1024)
            .await
            .unwrap();
        let empty_command: Option<DeviceCommand> = serde_json::from_slice(&empty_body).unwrap();
        assert_eq!(empty_command, None);
    }

    #[tokio::test]
    async fn legacy_heartbeat_fingerprints_are_accepted_but_not_persisted() {
''',
)

replace_once(
    "contracts/governance/invariant-enforcement.json",
    '  "baseline_main_sha": "3f6a2bb98807d289b5e436911b9dd92c102543d4",',
    '  "baseline_main_sha": "960745007e543c9245a69e57a4856b4f39ab3730",',
)
replace_once(
    "contracts/governance/invariant-enforcement.json",
    '''        "crates/application/src/command_issue.rs",
        "services/control-plane/src/state.rs"
''',
    '''        "crates/application/src/command_issue.rs",
        "crates/application/src/command_delivery.rs",
        "services/control-plane/src/state.rs"
''',
)
replace_once(
    "contracts/governance/invariant-enforcement.json",
    '      "Command issuance mutates through a typed application port; registration, heartbeat, probe and acknowledgement are still direct handlers.",',
    '      "Command issuance and successful acknowledgement mutate through typed application ports; registration, heartbeat and probe are still direct handlers.",',
)
replace_once(
    "contracts/governance/invariant-enforcement.json",
    '''        "crates/application/src/command_issue.rs",
        "services/control-plane/src/routes.rs"
''',
    '''        "crates/application/src/command_issue.rs",
        "crates/application/src/command_delivery.rs",
        "services/control-plane/src/routes.rs"
''',
)
replace_once(
    "contracts/governance/invariant-enforcement.json",
    '      "issue_command authenticates at the router, accepts typed input, calls one use case and maps typed outcomes; other handlers remain transitional.",',
    '      "Command issue, poll and acknowledgement handlers authenticate at the router, call one typed use case and map typed outcomes; registration, heartbeat and probe remain transitional.",',
)
replace_once(
    "contracts/governance/invariant-enforcement.json",
    '      "Command queue, durable idempotency result and device projection are written as one fsynced candidate before in-memory publication; domain event, audit and outbox persistence are absent.",',
    '      "Command issuance and successful acknowledgement write queue, durable idempotency result and device projection as one fsynced candidate before in-memory publication; domain event, audit and outbox persistence are absent.",',
)

replace_once(
    "docs/architecture/invariant-enforcement.md",
    "Baseline `main`: `3f6a2bb98807d289b5e436911b9dd92c102543d4`",
    "Baseline `main`: `960745007e543c9245a69e57a4856b4f39ab3730`",
)
replace_once(
    "docs/architecture/invariant-enforcement.md",
    '''- thin transport handlers beyond the extracted command-issuance route and prohibition of SQL or business transitions in all HTTP routes;
- durable SQLite canonical state, transactional audit/outbox semantics and JSON migration;
''',
    '''- thin transport handlers beyond the extracted command lifecycle routes and prohibition of SQL or business transitions in all HTTP routes;
- durable SQLite canonical state, durable acknowledgement history, transactional audit/outbox semantics and JSON migration;
''',
)
replace_once(
    "docs/architecture/invariant-enforcement.md",
    '''## Command issuance application-port enforcement

The existing admin `issue_command` capability now has one bounded clean-dependency slice:
''',
    '''## Command lifecycle application-port enforcement

The existing command issue, poll and acknowledgement capabilities now have bounded clean-dependency slices:
''',
)
replace_once(
    "docs/architecture/invariant-enforcement.md",
    '''- a failed write returns `state_persistence_failed` and leaves the in-memory state unchanged.

This evidence applies only to command issuance. Registration, heartbeat, public probe, command polling and acknowledgement remain transitional and keep `ARCH-004` and `ARCH-005` at `partially_enforced`.
''',
    '''- a failed write returns `state_persistence_failed` and leaves the in-memory state unchanged.
- command polling validates queue ownership and returns a typed `available` or `empty` outcome without transport logic reaching into the queue;
- successful acknowledgement removes the command and updates the device projection in one fsynced candidate before publishing either in memory;
- negative acknowledgement preserves the pending command and the existing `{ "accepted": true }` compatibility shape.

Registration, heartbeat and public probe remain transitional and keep `ARCH-004` and `ARCH-005` at `partially_enforced`.
''',
)

write(
    "docs/architecture/command-delivery-application-port.md",
    '''# Command delivery application ports

Status: production migration slice  
Scope: existing device command polling and acknowledgement routes

## Contract

`mobile-proxy-application` owns transport-independent ports for:

- polling the oldest pending command for one device;
- acknowledging successful execution;
- reporting a retryable negative acknowledgement without deleting the command.

Axum authenticates the device request, converts path and JSON values to typed inputs, invokes one port and maps typed outcomes. The application crate has no runtime, filesystem, process, network or framework dependency.

## Compatibility

The existing HTTP surface is unchanged:

- `GET /api/v1/devices/{id}/commands/next` still returns either the command object or JSON `null`;
- `POST /api/v1/devices/{id}/commands/{command_id}/ack` still returns `{ "accepted": true }` for a removed successful command and for a negative acknowledgement;
- a repeated successful acknowledgement for a command that is no longer pending still returns `{ "accepted": false }`;
- device and admin bearer-token separation remains unchanged.

## Persistence ordering

Successful acknowledgement is a candidate transaction over the command queue and device projection:

1. clone the current bounded state;
2. validate the queue key, command device and command identifier;
3. remove the matching pending command and clear the device recovery intent;
4. serialize the complete candidate;
5. fsync the temporary file and atomically rename it;
6. publish the candidate in memory only after the durable write succeeds.

A failed write returns `state_persistence_failed` and leaves the in-memory command pending. Negative acknowledgement does not mutate durable state and therefore remains safe for repeated delivery.

## Bounded outcomes

Polling returns `available` or `empty`. Acknowledgement returns one of:

- `acknowledged`;
- `retry_requested`;
- `not_pending`.

Internal queue mismatches fail closed as `command_state_conflict`. Raw acknowledgement messages are neither persisted nor logged in this slice.

## Explicitly deferred

SQLite transactions, durable acknowledgement history, claim leases, attempt counters, domain events, audit, outbox, per-device cryptographic identity and deadline expiry remain later bounded slices. Registration, heartbeat and public-probe handlers are still transitional.
''',
)

print("command delivery production slice applied")
