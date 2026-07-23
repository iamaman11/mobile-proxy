#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(relative: str, old: str, new: str) -> None:
    path = ROOT / relative
    body = path.read_text(encoding="utf-8")
    count = body.count(old)
    if count != 1:
        raise SystemExit(f"{relative}: expected one anchor, found {count}")
    path.write_text(body.replace(old, new), encoding="utf-8")


replace_once(
    "services/control-plane/src/routes.rs",
    "use mobile_proxy_foundation::{CommandId, RequestContext};\n",
    "use mobile_proxy_application::{IssueCommandError, IssueCommandInput, IssueCommandPort};\n"
    "use mobile_proxy_foundation::{CommandId, RequestContext};\n",
)
replace_once(
    "services/control-plane/src/routes.rs",
    "use uuid::Uuid;\n\n",
    "",
)
replace_once(
    "services/control-plane/src/routes.rs",
    '''async fn issue_command(
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
''',
    '''type CommandRouteError = (StatusCode, Json<serde_json::Value>);

async fn issue_command(
    State(state): State<AppState>,
    Extension(context): Extension<RequestContext>,
    Path(id): Path<String>,
    Json(req): Json<IssueCommandRequest>,
) -> Result<Json<DeviceCommand>, CommandRouteError> {
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
''',
)
replace_once(
    "services/control-plane/src/routes.rs",
    '''    #[tokio::test]
    async fn legacy_heartbeat_fingerprints_are_accepted_but_not_persisted() {
''',
    '''    #[tokio::test]
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
''',
)

(ROOT / "scripts/check_architecture_boundaries.py").write_text(
    '''#!/usr/bin/env python3
"""Fail closed when architecture, digest or invariant governance boundaries drift."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
import tomllib

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from check_digest_policy import check_repository as check_digest_policy
from check_invariant_enforcement import validate_repository as check_invariant_enforcement

INFRASTRUCTURE_SOURCE_TOKENS = (
    "wireguard",
    "axum",
    "tonic",
    "sqlx",
    "rusqlite",
    "reqwest",
    "tokio",
    "std::fs",
    "std::net",
    "std::process",
    "std::env",
    "systemtime",
    "instant::now",
    "new_v4",
    "getrandom",
    "android",
)

PURE_CRATES: dict[str, tuple[frozenset[str], tuple[str, ...]]] = {
    "crates/foundation": (
        frozenset({"blake3", "serde", "uuid"}),
        (*INFRASTRUCTURE_SOURCE_TOKENS, "proxy_core"),
    ),
    "crates/runtime-domain": (
        frozenset({"serde"}),
        (*INFRASTRUCTURE_SOURCE_TOKENS, "proxy_core"),
    ),
    "crates/application": (
        frozenset({"mobile-proxy-foundation", "proxy-core"}),
        INFRASTRUCTURE_SOURCE_TOKENS,
    ),
}


def dependency_tables(node: object, path: tuple[str, ...] = ()):
    if not isinstance(node, dict):
        return
    for key, value in node.items():
        next_path = (*path, key)
        if key in {"dependencies", "dev-dependencies", "build-dependencies"} and isinstance(
            value, dict
        ):
            yield ".".join(next_path), value
        else:
            yield from dependency_tables(value, next_path)


def check_repository(root: Path) -> list[str]:
    errors: list[str] = []
    for relative, (allowed_dependencies, forbidden_tokens) in PURE_CRATES.items():
        crate = root / relative
        manifest_path = crate / "Cargo.toml"
        if not manifest_path.is_file():
            errors.append(f"{relative}: missing Cargo.toml")
            continue

        manifest = tomllib.loads(manifest_path.read_text(encoding="utf-8"))
        for table_name, dependencies in dependency_tables(manifest):
            for dependency in dependencies:
                normalized = dependency.replace("-", "_")
                allowed = {item.replace("-", "_") for item in allowed_dependencies}
                if normalized not in allowed:
                    errors.append(
                        f"{relative}: forbidden dependency {dependency!r} in {table_name}"
                    )

        source_root = crate / "src"
        if not source_root.is_dir():
            errors.append(f"{relative}: missing src directory")
            continue
        for source in sorted(source_root.rglob("*.rs")):
            body = source.read_text(encoding="utf-8").lower()
            for token in forbidden_tokens:
                if token in body:
                    errors.append(
                        f"{source.relative_to(root)}: forbidden pure-crate token {token!r}"
                    )
    errors.extend(check_digest_policy(root))
    errors.extend(check_invariant_enforcement(root))
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
    )
    args = parser.parse_args()
    errors = check_repository(args.repo_root.resolve())
    if errors:
        print("architecture, digest and invariant validation failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print("architecture, digest and invariant validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
''',
    encoding="utf-8",
)

(ROOT / "scripts/tests/test_architecture_boundaries.py").write_text(
    '''import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "check_architecture_boundaries.py"
SPEC = importlib.util.spec_from_file_location("architecture_boundaries", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class ArchitectureBoundaryTests(unittest.TestCase):
    def create_repository(
        self,
        *,
        runtime_manifest: str = """[package]\nname = "runtime-domain"\nversion = "0.1.0"\n\n[dependencies]\nserde = "1"\n""",
        runtime_source: str = "pub enum RuntimeState { WaitingTunnel }\n",
        foundation_manifest: str = """[package]\nname = "mobile-proxy-foundation"\nversion = "0.1.0"\n\n[dependencies]\nblake3 = "1"\nserde = "1"\nuuid = "1"\n""",
        foundation_source: str = "pub struct RequestId;\n",
        application_manifest: str = """[package]\nname = "mobile-proxy-application"\nversion = "0.1.0"\n\n[dependencies]\nmobile-proxy-foundation = "1"\nproxy-core = "1"\n""",
        application_source: str = "use proxy_core::DeviceCommand;\npub trait UseCase {}\n",
    ) -> Path:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        for relative, manifest, source in [
            ("crates/runtime-domain", runtime_manifest, runtime_source),
            ("crates/foundation", foundation_manifest, foundation_source),
            ("crates/application", application_manifest, application_source),
        ]:
            crate = root / relative
            (crate / "src").mkdir(parents=True)
            (crate / "Cargo.toml").write_text(manifest, encoding="utf-8")
            (crate / "src/lib.rs").write_text(source, encoding="utf-8")
        return root

    def check_fixture(self, root: Path):
        with (
            patch.object(MODULE, "check_digest_policy", return_value=[]),
            patch.object(MODULE, "check_invariant_enforcement", return_value=[]),
        ):
            return MODULE.check_repository(root)

    def test_accepts_declared_pure_crates(self):
        self.assertEqual(self.check_fixture(self.create_repository()), [])

    def test_rejects_infrastructure_dependency_in_foundation(self):
        root = self.create_repository(
            foundation_manifest="""[package]\nname = "mobile-proxy-foundation"\nversion = "0.1.0"\n\n[dependencies]\nserde = "1"\ntokio = "1"\n"""
        )
        errors = self.check_fixture(root)
        self.assertTrue(any("forbidden dependency 'tokio'" in error for error in errors))

    def test_rejects_adapter_specific_domain_vocabulary(self):
        root = self.create_repository(
            runtime_source='pub const OWNER: &str = "wireguard";\n'
        )
        errors = self.check_fixture(root)
        self.assertTrue(any("forbidden pure-crate token 'wireguard'" in error for error in errors))

    def test_rejects_identity_generation_inside_foundation(self):
        root = self.create_repository(
            foundation_source="pub fn generate() { let _ = Uuid::new_v4(); }\n"
        )
        errors = self.check_fixture(root)
        self.assertTrue(any("forbidden pure-crate token 'new_v4'" in error for error in errors))

    def test_allows_domain_dependency_but_rejects_transport_in_application(self):
        accepted = self.create_repository()
        self.assertEqual(self.check_fixture(accepted), [])
        rejected = self.create_repository(
            application_manifest="""[package]\nname = "mobile-proxy-application"\nversion = "0.1.0"\n\n[dependencies]\nproxy-core = "1"\naxum = "1"\n"""
        )
        errors = self.check_fixture(rejected)
        self.assertTrue(any("forbidden dependency 'axum'" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
''',
    encoding="utf-8",
)

matrix_path = ROOT / "contracts/governance/invariant-enforcement.json"
matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
matrix["baseline_main_sha"] = "3f6a2bb98807d289b5e436911b9dd92c102543d4"
columns = {name: index for index, name in enumerate(matrix["columns"])}
rows = {row[columns["id"]]: row for row in matrix["invariants"]}


def update(invariant_id: str, **values: object) -> None:
    row = rows[invariant_id]
    for key, value in values.items():
        row[columns[key]] = value


update(
    "ARCH-001",
    evidence=[
        "scripts/check_architecture_boundaries.py",
        "scripts/tests/test_architecture_boundaries.py",
        "crates/application/Cargo.toml",
    ],
    evidence_note="Foundation, runtime-domain and the first application crate have layer-specific dependency and vocabulary gates; the complete target graph is not present.",
)
update(
    "ARCH-004",
    status="partially_enforced",
    evidence=[
        "crates/application/src/command_issue.rs",
        "services/control-plane/src/state.rs",
    ],
    ci_controls=["RQ-A", "RQ-T"],
    planned_slice="remaining-control-plane-application-ports",
    evidence_note="Command issuance mutates through a typed application port; registration, heartbeat, probe and acknowledgement are still direct handlers.",
)
update(
    "ARCH-005",
    status="partially_enforced",
    evidence=[
        "crates/application/src/command_issue.rs",
        "services/control-plane/src/routes.rs",
    ],
    ci_controls=["RQ-A", "RQ-T"],
    planned_slice="remaining-control-plane-application-ports",
    evidence_note="issue_command authenticates at the router, accepts typed input, calls one use case and maps typed outcomes; other handlers remain transitional.",
)
update(
    "PERSIST-003",
    status="partially_enforced",
    evidence=[
        "crates/application/src/command_issue.rs",
        "services/control-plane/src/state.rs",
    ],
    ci_controls=["RQ-T"],
    planned_slice="atomic-command-audit-outbox",
    activation_condition="",
    evidence_note="Command queue, durable idempotency result and device projection are written as one fsynced candidate before in-memory publication; domain event, audit and outbox persistence are absent.",
)
update(
    "CONTRACT-004",
    evidence=[
        "docs/architecture/foundation-primitives.md",
        "services/control-plane/src/request_context.rs",
        "crates/application/src/command_issue.rs",
        "services/control-plane/src/routes.rs",
    ],
    evidence_note="Request lineage, deadlines and exact/conflicting command idempotency are enforced; protocol version and generic consumer/application idempotency scope are absent.",
)
update(
    "DIGEST-003",
    evidence=[
        "crates/foundation/src/lib.rs",
        "crates/proxy-core/src/fingerprints.rs",
        "crates/application/src/command_issue.rs",
    ],
)
update(
    "DIGEST-004",
    evidence=[
        "crates/foundation/src/lib.rs",
        "crates/application/src/command_issue.rs",
    ],
)
update(
    "FOUND-004",
    evidence=[
        "crates/foundation/src/lib.rs",
        "crates/application/src/command_issue.rs",
        "services/control-plane/src/routes.rs",
    ],
    evidence_note="Validation and non-logging of raw command keys are enforced; repository-wide secret logging detection is absent.",
)
matrix_path.write_text(json.dumps(matrix, indent=2) + "\n", encoding="utf-8")

invariant_doc = ROOT / "docs/architecture/invariant-enforcement.md"
body = invariant_doc.read_text(encoding="utf-8")
body = body.replace(
    "Baseline `main`: `a6d289b9c8bc93a2bc961d6630dc124f71436746`",
    "Baseline `main`: `3f6a2bb98807d289b5e436911b9dd92c102543d4`",
)
body = body.replace("| `partially_enforced` | 18 |", "| `partially_enforced` | 21 |")
body = body.replace("| `planned` | 15 |", "| `planned` | 13 |")
body = body.replace("| `not_applicable_yet` | 8 |", "| `not_applicable_yet` | 7 |")
body = body.replace(
    "- current pure-crate dependency and vocabulary restrictions;",
    "- layer-specific dependency and vocabulary restrictions for foundation, runtime-domain and the first application crate;",
)
body = body.replace(
    "- single owner per aggregate and typed application-port mutation boundaries;\n- thin transport handlers and prohibition of SQL or business transitions in HTTP routes;",
    "- single owner per aggregate and application ports for the remaining mutation routes;\n- thin transport handlers beyond the extracted command-issuance route and prohibition of SQL or business transitions in all HTTP routes;",
)
command_section = '''## Command issuance application-port enforcement

The existing admin `issue_command` capability now has one bounded clean-dependency slice:

- `mobile-proxy-application` owns the typed port, deterministic request fingerprint, unambiguous BLAKE3 idempotency scope and exact/conflict classification;
- the Axum handler calls one use case and maps only typed outcomes to bounded HTTP errors;
- raw idempotency keys are not logged;
- original results are persisted separately from the bounded delivery queue, so acknowledgement or queue eviction cannot turn an exact replay into a new command;
- legacy concatenated idempotency claims are normalized through an isolated adapter when their original queued command is recoverable, while stale claims reject reuse fail closed;
- command queue, idempotency claim/result and device projection are fsynced and atomically renamed before in-memory publication;
- a failed write returns `state_persistence_failed` and leaves the in-memory state unchanged.

This evidence applies only to command issuance. Registration, heartbeat, public probe, command polling and acknowledgement remain transitional and keep `ARCH-004` and `ARCH-005` at `partially_enforced`.

'''
marker = "## Runtime fingerprint enforcement\n"
if marker not in body:
    raise SystemExit("invariant enforcement document marker missing")
body = body.replace(marker, command_section + marker)
invariant_doc.write_text(body, encoding="utf-8")

(ROOT / "docs/architecture/command-issuance-application-port.md").write_text(
    '''# Command issuance application port

Status: production migration slice  
Scope: existing `POST /api/v1/devices/{id}/commands` behavior only

## Boundary

The transport handler authenticates through the existing admin middleware, receives already typed JSON, calls `IssueCommandPort::issue_command` once and maps its typed result. UUID generation, clock access, idempotency classification, queue policy, device projection and persistence are outside Axum.

`crates/application` is infrastructure-free. Permanent architecture validation permits only foundation and transitional domain-contract dependencies and rejects Axum, Tokio, filesystems, networking, SQL, environment access, clocks and random generation in that crate.

## Idempotency contract

The canonical claim key is a full typed BLAKE3 digest using domain:

```text
mobile-proxy/control-plane-command-idempotency-scope/v1
```

It frames `device_id` and the opaque idempotency key independently. Request equality uses:

```text
mobile-proxy/control-plane-command-request/v1
```

with independently framed device ID, desired state, recovery intent and deadline window. The idempotency key is the claim key and is therefore not duplicated inside the request fingerprint.

An identical replay returns the original `DeviceCommand`. A reused key with changed parameters returns HTTP `409` and `idempotency_conflict`. The raw key is never logged.

## Durable result and queue semantics

The delivery queue remains bounded to 50 commands per device. Idempotency results have a separate deterministic bound of 1000 claims, so removal from the queue does not remove the original replay result.

The JSON schema adds optional `idempotency_results` and `idempotency_order` fields under `commands`. Serde defaults keep old state readable; previous binaries ignore the added fields, preserving software rollback. Existing concatenated claims are a legacy migration input only. Recoverable claims are rewritten to the typed scope; an unrecoverable retained claim rejects reuse rather than creating a duplicate command.

For a new command, the adapter builds a candidate containing the queue, idempotency claim/result and device projection, writes and fsyncs a temporary file, atomically renames it, and only then swaps the in-memory state. A failed write publishes no command in memory.

## Non-goals

This slice does not claim that JSON is the final canonical store, does not add SQLite, audit or outbox persistence, and does not extract registration, heartbeat, probe, polling or acknowledgement handlers. Those remain explicit matrix gaps.
''',
    encoding="utf-8",
)

print("command issuance follow-up applied")
