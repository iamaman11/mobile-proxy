from pathlib import Path
import json

path = Path("contracts/governance/invariant-enforcement.json")
data = json.loads(path.read_text(encoding="utf-8"))
columns = data["columns"]
for row in data["invariants"]:
    invariant = dict(zip(columns, row, strict=True))
    if invariant["id"] == "DIGEST-008":
        invariant["owner"] = "migration"
        invariant["enforcement"] = [
            "crates/proxy-core/src/fingerprints.rs",
            "crates/proxy-core/src/records.rs",
            "crates/control-plane-sqlite/src/legacy_json_import.rs",
            "services/control-plane/src/bin/control-plane-state-migrate.rs",
            "scripts/check_digest_policy.py",
        ]
        invariant["evidence_note"] = (
            "Field types fix domain/version; the isolated SQLite import adapter rejects "
            "unsupported legacy values, and the production daemon has no legacy reader."
        )
    elif invariant["id"] == "DIGEST-009":
        invariant["status"] = "enforced"
        invariant["owner"] = "migration"
        invariant["enforcement"] = [
            "crates/control-plane-sqlite/src/legacy_json_import.rs",
            "services/control-plane/src/bin/control-plane-state-migrate.rs",
            "services/control-plane/tests/state_migration_cli.rs",
            "services/control-plane/tests/sqlite_backend_process_acceptance.rs",
            "docs/architecture/control-plane-sqlite-runtime-retirement.md",
        ]
        invariant["ci"] = ["RQ-A", "RQ-T"]
        invariant["planned_slice"] = ""
        invariant["activation_condition"] = ""
        invariant["evidence_note"] = (
            "Legacy normalization is isolated to deterministic import; the SQLite-only daemon "
            "has no legacy reader, and rollback-export preserves previous-release compatibility."
        )
        invariant["expires_on"] = ""
    row[:] = [invariant[column] for column in columns]

path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
