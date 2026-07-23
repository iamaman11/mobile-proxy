#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(path: str, old: str, new: str) -> None:
    target = ROOT / path
    body = target.read_text(encoding="utf-8")
    count = body.count(old)
    if count != 1:
        raise SystemExit(
            f"{path}: expected exactly one replacement anchor, found {count}: {old!r}"
        )
    target.write_text(body.replace(old, new, 1), encoding="utf-8")


replace_once(
    "services/control-plane/src/state.rs",
    'PathBuf::from("unused")',
    'std::path::PathBuf::from("unused")',
)

governance_path = ROOT / "contracts/governance/invariant-enforcement.json"
governance = json.loads(governance_path.read_text(encoding="utf-8"))
governance["baseline_main_sha"] = "960745007e543c9245a69e57a4856b4f39ab3730"
rows = {row[0]: row for row in governance["invariants"]}

evidence_path = "crates/application/src/command_delivery.rs"
for invariant_id in ("ARCH-004", "ARCH-005", "PERSIST-003"):
    row = rows[invariant_id]
    if evidence_path not in row[6]:
        issue_index = row[6].index("crates/application/src/command_issue.rs")
        row[6].insert(issue_index + 1, evidence_path)

rows["ARCH-004"][10] = (
    "Command issuance and successful acknowledgement mutate through typed application ports; "
    "registration, heartbeat and probe are still direct handlers."
)
rows["ARCH-005"][10] = (
    "Command issue, poll and acknowledgement handlers authenticate at the router, call one typed "
    "use case and map typed outcomes; registration, heartbeat and probe remain transitional."
)
rows["PERSIST-003"][10] = (
    "Command issuance and successful acknowledgement write queue, durable idempotency result and "
    "device projection as one fsynced candidate before in-memory publication; domain event, audit "
    "and outbox persistence are absent."
)
governance_path.write_text(
    json.dumps(governance, indent=2, ensure_ascii=False) + "\n",
    encoding="utf-8",
)

replace_once(
    "docs/architecture/invariant-enforcement.md",
    "Baseline `main`: `3f6a2bb98807d289b5e436911b9dd92c102543d4`",
    "Baseline `main`: `960745007e543c9245a69e57a4856b4f39ab3730`",
)
replace_once(
    "docs/architecture/invariant-enforcement.md",
    "thin transport handlers beyond the extracted command-issuance route",
    "thin transport handlers beyond the extracted command lifecycle routes",
)
replace_once(
    "docs/architecture/invariant-enforcement.md",
    "durable SQLite canonical state, transactional audit/outbox semantics and JSON migration",
    "durable SQLite canonical state, durable acknowledgement history, transactional audit/outbox semantics and JSON migration",
)
replace_once(
    "docs/architecture/invariant-enforcement.md",
    "## Command issuance application-port enforcement",
    "## Command lifecycle application-port enforcement",
)
replace_once(
    "docs/architecture/invariant-enforcement.md",
    "The existing admin `issue_command` capability now has one bounded clean-dependency slice:",
    "The existing command issue, poll and acknowledgement capabilities now have bounded clean-dependency slices:",
)
replace_once(
    "docs/architecture/invariant-enforcement.md",
    "This evidence applies only to command issuance. Registration, heartbeat, public probe, command polling and acknowledgement remain transitional and keep `ARCH-004` and `ARCH-005` at `partially_enforced`.",
    "Command polling validates queue ownership and returns a typed pending-or-empty outcome without transport logic reaching into the queue. Successful acknowledgement removes the command and updates the device projection in one fsynced candidate before publishing either in memory. Negative acknowledgement preserves the pending command and the existing `{ \\\"accepted\\\": true }` compatibility shape.\n\nRegistration, heartbeat and public probe remain transitional and keep `ARCH-004` and `ARCH-005` at `partially_enforced`.",
)

(ROOT / "docs/architecture/command-delivery-application-port.md").write_text(
    """# Command delivery application ports

Status: production migration slice  
Scope: existing device command polling and acknowledgement routes

## Contract

`mobile-proxy-application` owns transport-independent ports for polling the oldest pending command for one device, acknowledging successful execution, and reporting a retryable negative acknowledgement without deleting the command. Axum authenticates the request, converts path and JSON values to typed inputs, invokes one port and maps typed outcomes. The application crate has no runtime, filesystem, process, network or framework dependency.

## Compatibility

The existing HTTP surface is unchanged:

- `GET /api/v1/devices/{id}/commands/next` returns either the command object or JSON `null`;
- successful and negative acknowledgements return `{ "accepted": true }`;
- a repeated successful acknowledgement for a command that is no longer pending returns `{ "accepted": false }`;
- device and admin bearer-token separation remains unchanged.

## Persistence ordering

Successful acknowledgement clones the bounded command and device state, validates the queue key and command identity, removes the pending command, clears the device recovery intent, fsyncs and atomically renames the complete JSON candidate, and only then publishes the candidate in memory. A failed write returns `state_persistence_failed` and leaves the in-memory command pending. Negative acknowledgement does not mutate durable state and remains safe for repeated delivery.

## Explicitly deferred

SQLite transactions, durable acknowledgement history, claim leases, attempt counters, domain events, audit, outbox, per-device cryptographic identity and deadline expiry remain later bounded slices. Registration, heartbeat and public-probe handlers remain transitional.
""",
    encoding="utf-8",
)
