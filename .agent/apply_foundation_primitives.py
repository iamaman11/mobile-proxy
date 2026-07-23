from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def write(path: str, content: str) -> None:
    target = ROOT / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


def replace_once(path: str, old: str, new: str) -> None:
    target = ROOT / path
    content = target.read_text(encoding="utf-8")
    if content.count(old) != 1:
        raise RuntimeError(f"expected exactly one anchor in {path}: {old!r}")
    target.write_text(content.replace(old, new, 1), encoding="utf-8")


replace_once(
    "Cargo.toml",
    '    "crates/runtime-domain",\n',
    '    "crates/runtime-domain",\n    "crates/foundation",\n',
)
replace_once(
    "Cargo.toml",
    'base64 = "0.22"\n',
    'base64 = "0.22"\nblake3 = "1"\n',
)
replace_once(
    "Cargo.toml",
    'clap = { version = "4.5", features = ["derive", "env"] }\n',
    'clap = { version = "4.5", features = ["derive", "env"] }\nmobile-proxy-foundation = { path = "crates/foundation" }\n',
)
replace_once(
    "crates/proxy-core/Cargo.toml",
    "[dependencies]\n",
    "[dependencies]\nmobile-proxy-foundation.workspace = true\n",
)
replace_once(
    "services/control-plane/Cargo.toml",
    "clap.workspace = true\n",
    "clap.workspace = true\nmobile-proxy-foundation.workspace = true\n",
)

write(
    "crates/proxy-core/src/commands.rs",
    r'''use mobile_proxy_foundation::{CommandId, DeadlineWindow, IdempotencyKey};
use serde::{Deserialize, Serialize};
use std::fmt::{Display, Formatter};
use uuid::Uuid;

use crate::constants::DEFAULT_AIRPLANE_HOLD_SECS;

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum DesiredState {
    HealthyServing,
    DegradedSafe,
}

impl Display for DesiredState {
    fn fmt(&self, f: &mut Formatter<'_>) -> std::fmt::Result {
        let value = match self {
            Self::HealthyServing => "healthy_serving",
            Self::DegradedSafe => "degraded_safe",
        };
        write!(f, "{value}")
    }
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum RecoveryIntent {
    None,
    RouteRepair,
    RestartRuntime,
    RotateRecovery,
}

impl Display for RecoveryIntent {
    fn fmt(&self, f: &mut Formatter<'_>) -> std::fmt::Result {
        let value = match self {
            Self::None => "none",
            Self::RouteRepair => "route_repair",
            Self::RestartRuntime => "restart_runtime",
            Self::RotateRecovery => "rotate_recovery",
        };
        write!(f, "{value}")
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct IssueCommandRequest {
    pub desired_state: DesiredState,
    pub recovery_intent: RecoveryIntent,
    pub deadline_secs: DeadlineWindow,
    pub idempotency_key: IdempotencyKey,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct DeviceCommand {
    pub command_id: CommandId,
    pub device_id: String,
    pub desired_state: DesiredState,
    pub recovery_intent: RecoveryIntent,
    pub deadline_secs: DeadlineWindow,
    pub idempotency_key: IdempotencyKey,
    pub issued_at: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CommandAckRequest {
    pub ok: bool,
    pub message: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RotateRequest {
    pub strategy: String,
    pub require_public_ip_change: bool,
    pub reason: String,
    pub hold_secs: Option<u64>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RotateAccepted {
    pub job_id: Uuid,
    pub accepted: bool,
}

pub fn default_rotate_request() -> RotateRequest {
    RotateRequest {
        strategy: "airplane_bounce".to_string(),
        require_public_ip_change: true,
        reason: "manual-rotate".to_string(),
        hold_secs: Some(DEFAULT_AIRPLANE_HOLD_SECS),
    }
}
''',
)

replace_once(
    "services/control-plane/src/main.rs",
    "mod projection;\n",
    "mod projection;\nmod request_context;\n",
)
replace_once(
    "services/control-plane/src/routes.rs",
    "    extract::{Path, State},\n",
    "    extract::{Extension, Path, State},\n",
)
replace_once(
    "services/control-plane/src/routes.rs",
    "use uuid::Uuid;\n",
    "use mobile_proxy_foundation::{CommandId, RequestContext};\nuse uuid::Uuid;\n",
)
replace_once(
    "services/control-plane/src/routes.rs",
    "use crate::state::AppState;\n",
    "use crate::{request_context::attach_request_context, state::AppState};\n",
)
replace_once(
    "services/control-plane/src/routes.rs",
    "        .route_layer(middleware::from_fn_with_state(auth.clone(), require_admin));\n",
    "        .route_layer(middleware::from_fn(attach_request_context))\n        .route_layer(middleware::from_fn_with_state(auth.clone(), require_admin));\n",
)
replace_once(
    "services/control-plane/src/routes.rs",
    "        .route_layer(middleware::from_fn_with_state(auth, require_device));\n",
    "        .route_layer(middleware::from_fn(attach_request_context))\n        .route_layer(middleware::from_fn_with_state(auth, require_device));\n",
)
replace_once(
    "services/control-plane/src/routes.rs",
    "async fn issue_command(\n    State(state): State<AppState>,\n    Path(id): Path<String>,\n    Json(req): Json<IssueCommandRequest>,\n) -> Json<DeviceCommand> {\n",
    "async fn issue_command(\n    State(state): State<AppState>,\n    Extension(context): Extension<RequestContext>,\n    Path(id): Path<String>,\n    Json(req): Json<IssueCommandRequest>,\n) -> Json<DeviceCommand> {\n",
)
replace_once(
    "services/control-plane/src/routes.rs",
    "        command_id: Uuid::new_v4(),\n",
    "        command_id: CommandId::from_uuid(Uuid::new_v4()),\n",
)
replace_once(
    "services/control-plane/src/routes.rs",
    "    let _ = state.persist().await;\n    Json(command)\n}\n\nasync fn next_command",
    "    let _ = state.persist().await;\n    tracing::info!(\n        request_id = %context.request_id(),\n        correlation_id = %context.correlation_id(),\n        command_id = %command.command_id,\n        device_id = %id,\n        \"device command accepted\"\n    );\n    Json(command)\n}\n\nasync fn next_command",
)
replace_once(
    "services/control-plane/src/routes.rs",
    "    Path((id, command_id)): Path<(String, Uuid)>,\n",
    "    Path((id, command_id)): Path<(String, CommandId)>,\n",
)
replace_once(
    "services/control-plane/src/routes.rs",
    "        Availability, DeviceRecord, RuntimeProjectionInput, RuntimeReadiness, project_runtime,\n",
    "        Availability, DeviceCommand, DeviceRecord, RuntimeProjectionInput, RuntimeReadiness,\n        project_runtime,\n",
)
replace_once(
    "services/control-plane/src/routes.rs",
    "    #[test]\n    fn availability_requires_public_probe() {\n",
    r'''    #[tokio::test]
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
                    .header(
                        "x-correlation-id",
                        "4cd306ef-716e-4f76-aef6-679b93bb7770",
                    )
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(
            response.headers().get("x-request-id").unwrap().to_str().unwrap(),
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
''',
)

replace_once(
    "services/control-plane/src/state.rs",
    "use proxy_core::{DeviceCommand, DeviceRecord};\n",
    "use mobile_proxy_foundation::CommandId;\nuse proxy_core::{DeviceCommand, DeviceRecord};\n",
)
replace_once(
    "services/control-plane/src/state.rs",
    "use uuid::Uuid;\n",
    "",
)
replace_once(
    "services/control-plane/src/state.rs",
    "    pub idempotency: HashMap<String, Uuid>,\n",
    "    pub idempotency: HashMap<String, CommandId>,\n",
)

write(
    "scripts/check_architecture_boundaries.py",
    r'''#!/usr/bin/env python3
"""Fail closed when pure crates gain infrastructure dependencies or vocabulary."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
import tomllib

PURE_CRATES: dict[str, frozenset[str]] = {
    "crates/foundation": frozenset({"blake3", "serde", "uuid"}),
    "crates/runtime-domain": frozenset({"serde"}),
}

FORBIDDEN_SOURCE_TOKENS = (
    "wireguard",
    "proxy_core",
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
    for relative, allowed_dependencies in PURE_CRATES.items():
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
            for token in FORBIDDEN_SOURCE_TOKENS:
                if token in body:
                    errors.append(
                        f"{source.relative_to(root)}: forbidden pure-crate token {token!r}"
                    )
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
        print("architecture boundary validation failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print("architecture boundary validation passed for foundation and runtime-domain")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
''',
)

write(
    "scripts/tests/test_architecture_boundaries.py",
    r'''import importlib.util
from pathlib import Path
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "check_architecture_boundaries.py"
SPEC = importlib.util.spec_from_file_location("architecture_boundaries", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class ArchitectureBoundaryTests(unittest.TestCase):
    def create_repository(
        self,
        *,
        runtime_manifest: str = """[package]\nname = \"runtime-domain\"\nversion = \"0.1.0\"\n\n[dependencies]\nserde = \"1\"\n""",
        runtime_source: str = "pub enum RuntimeState { WaitingTunnel }\n",
        foundation_manifest: str = """[package]\nname = \"mobile-proxy-foundation\"\nversion = \"0.1.0\"\n\n[dependencies]\nblake3 = \"1\"\nserde = \"1\"\nuuid = \"1\"\n""",
        foundation_source: str = "pub struct RequestId;\n",
    ) -> Path:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        for relative, manifest, source in [
            ("crates/runtime-domain", runtime_manifest, runtime_source),
            ("crates/foundation", foundation_manifest, foundation_source),
        ]:
            crate = root / relative
            (crate / "src").mkdir(parents=True)
            (crate / "Cargo.toml").write_text(manifest, encoding="utf-8")
            (crate / "src/lib.rs").write_text(source, encoding="utf-8")
        return root

    def test_accepts_pure_crates(self):
        self.assertEqual(MODULE.check_repository(self.create_repository()), [])

    def test_rejects_infrastructure_dependency_in_foundation(self):
        root = self.create_repository(
            foundation_manifest="""[package]\nname = \"mobile-proxy-foundation\"\nversion = \"0.1.0\"\n\n[dependencies]\nserde = \"1\"\ntokio = \"1\"\n"""
        )
        errors = MODULE.check_repository(root)
        self.assertTrue(any("forbidden dependency 'tokio'" in error for error in errors))

    def test_rejects_adapter_specific_domain_vocabulary(self):
        root = self.create_repository(
            runtime_source='pub const OWNER: &str = "wireguard";\n'
        )
        errors = MODULE.check_repository(root)
        self.assertTrue(any("forbidden pure-crate token 'wireguard'" in error for error in errors))

    def test_rejects_identity_generation_inside_foundation(self):
        root = self.create_repository(
            foundation_source="pub fn generate() { let _ = Uuid::new_v4(); }\n"
        )
        errors = MODULE.check_repository(root)
        self.assertTrue(any("forbidden pure-crate token 'new_v4'" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
''',
)

replace_once(
    "IMPLEMENTATION_PLAN.md",
    "- [ADR-001: Bounded Contexts and Clean Dependency Rules](docs/architecture/ADR-001-bounded-contexts-and-clean-dependencies.md)\n",
    "- [ADR-001: Bounded Contexts and Clean Dependency Rules](docs/architecture/ADR-001-bounded-contexts-and-clean-dependencies.md)\n- [ADR-002: Cryptographic Hashing, Password Hashing and KDF Policy](docs/architecture/ADR-002-cryptographic-hashing-and-kdf-policy.md)\n- [Foundation Identifiers, Request Lineage and Deadlines](docs/architecture/foundation-primitives.md)\n",
)
replace_once(
    "docs/ULTIMATE_IMPLEMENTATION_PLAN.md",
    "### 2.5 Compatibility before replacement\n\nNo migration may silently remove an existing proxy protocol, public port, operator endpoint or tunnel fallback. Replacement requires an explicit compatibility contract, parity tests, a deprecation window and physical acceptance evidence.\n\n## 3. Target bounded contexts\n",
    "### 2.5 Compatibility before replacement\n\nNo migration may silently remove an existing proxy protocol, public port, operator endpoint or tunnel fallback. Replacement requires an explicit compatibility contract, parity tests, a deprecation window and physical acceptance evidence.\n\n### 2.6 Cryptographic primitive policy\n\nCryptographic primitives are selected by purpose, not by crate preference. New internal content and deterministic digests use full BLAKE3-256 values with algorithm prefixes, versioned domain separation, canonical input bytes and length framing. SHA-256 remains for TLS certificate pinning, standardized artifact/signature formats, FIPS profiles and existing external or persisted compatibility contracts. Passwords use Argon2id; standard protocols retain their specified HMAC, HKDF, signature and AEAD algorithms. Algorithm migration is a versioned data-contract migration and never a blind search-and-replace. The normative rules are in [ADR-002](architecture/ADR-002-cryptographic-hashing-and-kdf-policy.md).\n\n## 3. Target bounded contexts\n",
)
replace_once(
    "docs/ULTIMATE_IMPLEMENTATION_PLAN.md",
    "Typed IDs, clocks, deadlines, protocol versions, request IDs, correlation IDs and idempotency keys. No business behavior.\n",
    "Typed IDs, injected clocks, deadlines, protocol versions, request IDs, correlation IDs, actor/consumer/application identities, idempotency keys and typed algorithm-versioned digests. Foundation validates values but does not generate randomness, read system time, resolve secrets or contain business behavior.\n",
)
