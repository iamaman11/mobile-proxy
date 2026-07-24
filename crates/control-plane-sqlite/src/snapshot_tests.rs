use std::str::FromStr;

use mobile_proxy_application::{idempotency_scope_key, request_fingerprint};
use mobile_proxy_foundation::{
    CommandId, ContentDigest, DeadlineWindow, DigestDomain, IdempotencyKey,
};
use proxy_core::{DesiredState, DeviceCommand, DeviceRecord, IssueCommandRequest, RecoveryIntent};
use serde_json::json;

use super::{
    CommandResultRow, ControlPlaneSnapshot, DeviceRow, IdempotencyClaimRow, PendingCommandRow,
    ReplayRecord, SNAPSHOT_FORMAT_VERSION, SnapshotError, SnapshotRows, SnapshotViolation,
};

fn command(index: u128, device_id: &str, key: &str) -> DeviceCommand {
    DeviceCommand {
        command_id: CommandId::from_str(&format!("{index:032x}"))
            .unwrap_or_else(|_| panic!("test command id {index} must be valid")),
        device_id: device_id.to_owned(),
        desired_state: DesiredState::HealthyServing,
        recovery_intent: RecoveryIntent::None,
        deadline_secs: DeadlineWindow::new(30).unwrap(),
        idempotency_key: IdempotencyKey::parse(key).unwrap(),
        issued_at: format!("{index}"),
    }
}

fn device(node_id: &str) -> DeviceRecord {
    serde_json::from_value(json!({
        "node_id": node_id,
        "node_name": format!("node-{node_id}"),
        "readiness_state": "healthy",
        "serving": true,
        "proxy_status": "running",
        "publicly_serving": true,
        "availability": "available"
    }))
    .unwrap()
}

fn exact_rows(commands: &[DeviceCommand], pending: &[(u32, DeviceCommand)]) -> SnapshotRows {
    SnapshotRows::new(
        Vec::new(),
        commands
            .iter()
            .cloned()
            .map(CommandResultRow::from_command)
            .collect(),
        commands
            .iter()
            .map(IdempotencyClaimRow::from_command)
            .collect(),
        pending
            .iter()
            .map(|(position, command)| PendingCommandRow::from_command(*position, command.clone()))
            .collect(),
    )
}

fn unrelated_digest(label: &'static str) -> ContentDigest {
    ContentDigest::derive(
        DigestDomain::new("mobile-proxy.control-plane-snapshot-test.v1"),
        [label.as_bytes()],
    )
}

fn assert_violation(rows: SnapshotRows, expected: SnapshotViolation) {
    assert_eq!(ControlPlaneSnapshot::from_rows(rows).unwrap_err(), expected);
}

#[test]
fn valid_rows_preserve_exact_replay_evidence_and_queue_order() {
    let first = command(1, "device-1", "first");
    let second = command(2, "device-1", "second");
    let rows = exact_rows(
        &[second.clone(), first.clone()],
        &[(1, second.clone()), (0, first.clone())],
    );

    let snapshot = ControlPlaneSnapshot::from_rows(rows).unwrap();
    let queue = snapshot.queues().get("device-1").unwrap();
    assert_eq!(queue[0], first);
    assert_eq!(queue[1], second);

    for replay in snapshot.replay_records() {
        let request = IssueCommandRequest {
            desired_state: replay.command().desired_state,
            recovery_intent: replay.command().recovery_intent,
            deadline_secs: replay.command().deadline_secs,
            idempotency_key: replay.command().idempotency_key.clone(),
        };
        assert_eq!(
            replay.scope_key(),
            idempotency_scope_key(
                &replay.command().device_id,
                &replay.command().idempotency_key
            )
        );
        assert_eq!(
            replay.request_fingerprint(),
            request_fingerprint(&replay.command().device_id, &request)
        );
    }
}

#[test]
fn canonical_json_is_deterministic_and_round_trips_exactly() {
    let first = command(1, "device-1", "first");
    let second = command(2, "device-1", "second");
    let left = ControlPlaneSnapshot::from_rows(SnapshotRows::new(
        vec![DeviceRow::from_record(device("device-1"))],
        vec![
            CommandResultRow::from_command(second.clone()),
            CommandResultRow::from_command(first.clone()),
        ],
        vec![
            IdempotencyClaimRow::from_command(&first),
            IdempotencyClaimRow::from_command(&second),
        ],
        vec![
            PendingCommandRow::from_command(1, second.clone()),
            PendingCommandRow::from_command(0, first.clone()),
        ],
    ))
    .unwrap();
    let right = ControlPlaneSnapshot::from_rows(SnapshotRows::new(
        vec![DeviceRow::from_record(device("device-1"))],
        vec![
            CommandResultRow::from_command(first.clone()),
            CommandResultRow::from_command(second.clone()),
        ],
        vec![
            IdempotencyClaimRow::from_command(&second),
            IdempotencyClaimRow::from_command(&first),
        ],
        vec![
            PendingCommandRow::from_command(0, first),
            PendingCommandRow::from_command(1, second),
        ],
    ))
    .unwrap();

    let left_json = left.to_canonical_json().unwrap();
    assert_eq!(left_json, right.to_canonical_json().unwrap());
    let rehydrated = ControlPlaneSnapshot::from_json(&left_json).unwrap();
    assert_eq!(rehydrated.to_canonical_json().unwrap(), left_json);
}

#[test]
fn device_key_mismatch_and_duplicate_device_fail_closed() {
    assert_violation(
        SnapshotRows::new(
            vec![DeviceRow::new("device-1", device("device-2"))],
            Vec::new(),
            Vec::new(),
            Vec::new(),
        ),
        SnapshotViolation::DeviceKeyMismatch,
    );
    assert_violation(
        SnapshotRows::new(
            vec![
                DeviceRow::from_record(device("device-1")),
                DeviceRow::from_record(device("device-1")),
            ],
            Vec::new(),
            Vec::new(),
            Vec::new(),
        ),
        SnapshotViolation::DuplicateDevice,
    );
}

#[test]
fn missing_or_extra_replay_relations_fail_closed() {
    let value = command(1, "device-1", "first");
    assert_violation(
        SnapshotRows::new(
            Vec::new(),
            vec![CommandResultRow::from_command(value.clone())],
            Vec::new(),
            Vec::new(),
        ),
        SnapshotViolation::ReplayClaimMissing,
    );
    assert_violation(
        SnapshotRows::new(
            Vec::new(),
            Vec::new(),
            vec![IdempotencyClaimRow::from_command(&value)],
            Vec::new(),
        ),
        SnapshotViolation::ClaimResultMissing,
    );
    assert_violation(
        SnapshotRows::new(
            Vec::new(),
            Vec::new(),
            Vec::new(),
            vec![PendingCommandRow::from_command(0, value)],
        ),
        SnapshotViolation::PendingReplayMissing,
    );
}

#[test]
fn mismatched_scope_fingerprint_and_claim_command_fail_closed() {
    let first = command(1, "device-1", "first");
    let second = command(2, "device-1", "second");
    let scope = idempotency_scope_key(&first.device_id, &first.idempotency_key);

    assert_violation(
        SnapshotRows::new(
            Vec::new(),
            vec![CommandResultRow::new(
                unrelated_digest("scope"),
                first.command_id,
                first.clone(),
            )],
            vec![IdempotencyClaimRow::from_command(&first)],
            Vec::new(),
        ),
        SnapshotViolation::ReplayScopeMismatch,
    );
    assert_violation(
        SnapshotRows::new(
            Vec::new(),
            vec![CommandResultRow::from_command(first.clone())],
            vec![IdempotencyClaimRow::new(
                scope,
                first.command_id,
                unrelated_digest("fingerprint"),
            )],
            Vec::new(),
        ),
        SnapshotViolation::ReplayEvidenceMismatch,
    );
    assert_violation(
        SnapshotRows::new(
            Vec::new(),
            vec![CommandResultRow::from_command(first.clone())],
            vec![IdempotencyClaimRow::new(
                scope,
                second.command_id,
                IdempotencyClaimRow::from_command(&first).request_fingerprint(),
            )],
            Vec::new(),
        ),
        SnapshotViolation::ClaimCommandMismatch,
    );
}

#[test]
fn duplicate_command_scope_claim_and_queue_position_fail_closed() {
    let first = command(1, "device-1", "first");
    let mut reused_id = command(2, "device-1", "second");
    reused_id.command_id = first.command_id;

    assert_violation(
        SnapshotRows::new(
            Vec::new(),
            vec![
                CommandResultRow::from_command(first.clone()),
                CommandResultRow::from_command(first.clone()),
            ],
            vec![IdempotencyClaimRow::from_command(&first)],
            Vec::new(),
        ),
        SnapshotViolation::DuplicateReplayScope,
    );
    assert_violation(
        SnapshotRows::new(
            Vec::new(),
            vec![
                CommandResultRow::from_command(first.clone()),
                CommandResultRow::from_command(reused_id.clone()),
            ],
            vec![
                IdempotencyClaimRow::from_command(&first),
                IdempotencyClaimRow::from_command(&reused_id),
            ],
            Vec::new(),
        ),
        SnapshotViolation::DuplicateCommandId,
    );
    assert_violation(
        SnapshotRows::new(
            Vec::new(),
            vec![CommandResultRow::from_command(first.clone())],
            vec![
                IdempotencyClaimRow::from_command(&first),
                IdempotencyClaimRow::from_command(&first),
            ],
            Vec::new(),
        ),
        SnapshotViolation::DuplicateClaimScope,
    );

    let second = command(2, "device-1", "second");
    assert_violation(
        SnapshotRows::new(
            Vec::new(),
            vec![
                CommandResultRow::from_command(first.clone()),
                CommandResultRow::from_command(second.clone()),
            ],
            vec![
                IdempotencyClaimRow::from_command(&first),
                IdempotencyClaimRow::from_command(&second),
            ],
            vec![
                PendingCommandRow::from_command(0, first),
                PendingCommandRow::from_command(0, second),
            ],
        ),
        SnapshotViolation::DuplicateQueuePosition,
    );
}

#[test]
fn pending_identity_device_content_and_position_gaps_fail_closed() {
    let first = command(1, "device-1", "first");
    let second = command(2, "device-2", "second");

    assert_violation(
        SnapshotRows::new(
            Vec::new(),
            vec![CommandResultRow::from_command(first.clone())],
            vec![IdempotencyClaimRow::from_command(&first)],
            vec![PendingCommandRow::new(
                second.command_id,
                "device-1",
                0,
                first.clone(),
            )],
        ),
        SnapshotViolation::PendingIdentityMismatch,
    );
    assert_violation(
        SnapshotRows::new(
            Vec::new(),
            vec![CommandResultRow::from_command(first.clone())],
            vec![IdempotencyClaimRow::from_command(&first)],
            vec![PendingCommandRow::new(
                first.command_id,
                "device-2",
                0,
                first.clone(),
            )],
        ),
        SnapshotViolation::PendingDeviceMismatch,
    );

    let mut changed = first.clone();
    changed.desired_state = DesiredState::DegradedSafe;
    assert_violation(
        SnapshotRows::new(
            Vec::new(),
            vec![CommandResultRow::from_command(first.clone())],
            vec![IdempotencyClaimRow::from_command(&first)],
            vec![PendingCommandRow::from_command(0, changed)],
        ),
        SnapshotViolation::PendingReplayMismatch,
    );
    assert_violation(
        exact_rows(&[first.clone()], &[(1, first)]),
        SnapshotViolation::NonContiguousQueuePosition,
    );
}

#[test]
fn version_corrupt_json_and_invalid_typed_identifier_fail_closed() {
    let value = command(1, "device-1", "first");
    let snapshot = ControlPlaneSnapshot::from_parts(
        Default::default(),
        Default::default(),
        vec![ReplayRecord::from_command(value)],
    )
    .unwrap();
    let canonical = snapshot.to_canonical_json().unwrap();
    let mut document: serde_json::Value = serde_json::from_slice(&canonical).unwrap();
    document["schema_version"] = json!(SNAPSHOT_FORMAT_VERSION + 1);
    let unsupported = serde_json::to_vec(&document).unwrap();
    assert!(matches!(
        ControlPlaneSnapshot::from_json(&unsupported),
        Err(SnapshotError::Violation(
            SnapshotViolation::UnsupportedSchemaVersion { found, supported }
        )) if found == SNAPSHOT_FORMAT_VERSION + 1 && supported == SNAPSHOT_FORMAT_VERSION
    ));

    assert!(matches!(
        ControlPlaneSnapshot::from_json(br#"{"schema_version":1"#),
        Err(SnapshotError::Json(_))
    ));

    document["schema_version"] = json!(SNAPSHOT_FORMAT_VERSION);
    document["command_results"][0]["command_id"] = json!("not-a-uuid");
    assert!(matches!(
        ControlPlaneSnapshot::from_json(&serde_json::to_vec(&document).unwrap()),
        Err(SnapshotError::Json(_))
    ));
}
