#!/usr/bin/env python3
"""Validate the normative invariant enforcement audit fail-closed."""

from __future__ import annotations

import argparse
from datetime import date, timedelta
import hashlib
import json
from pathlib import Path
import re
import sys

MATRIX_PATH = Path("contracts/governance/invariant-enforcement.json")
DOCUMENT_PATH = Path("docs/architecture/invariant-enforcement.md")
ALLOWED_STATUSES = {
    "enforced",
    "partially_enforced",
    "review_only",
    "planned",
    "not_applicable_yet",
}
REQUIRED_SOURCE_IDS = {"U", "A1", "A2", "F", "D", "C"}
REQUIRED_COLUMNS = [
    "id",
    "source",
    "anchor",
    "scope",
    "status",
    "owner",
    "enforcement",
    "ci",
    "planned_slice",
    "activation_condition",
    "evidence_note",
    "expires_on",
]
EXPECTED_INVARIANT_IDS = {
    "PLATFORM-001",
    "COMPAT-001",
    "COMPAT-002",
    "COMPAT-003",
    "COMPAT-004",
    "COMPAT-005",
    "COMPAT-006",
    "COMPAT-007",
    "ARCH-001",
    "ARCH-002",
    "ARCH-003",
    "ARCH-004",
    "ARCH-005",
    "ARCH-006",
    "ARCH-007",
    "ARCH-008",
    "PERSIST-001",
    "PERSIST-002",
    "PERSIST-003",
    "PERSIST-004",
    "CONTRACT-001",
    "CONTRACT-002",
    "CONTRACT-003",
    "CONTRACT-004",
    "DIGEST-001",
    "DIGEST-002",
    "DIGEST-003",
    "DIGEST-004",
    "DIGEST-005",
    "DIGEST-006",
    "DIGEST-007",
    "DIGEST-008",
    "DIGEST-009",
    "DIGEST-010",
    "FOUND-001",
    "FOUND-002",
    "FOUND-003",
    "FOUND-004",
    "FOUND-005",
    "FOUND-006",
    "FOUND-007",
    "TUNNEL-001",
    "TUNNEL-002",
    "TUNNEL-003",
    "TUNNEL-004",
    "TUNNEL-005",
    "TUNNEL-006",
    "TUNNEL-007",
    "TUNNEL-008",
    "TUNNEL-009",
    "SEC-001",
    "SEC-002",
    "SEC-003",
    "SEC-004",
    "SEC-005",
    "OPS-001",
    "OPS-002",
    "OPS-003",
    "OPS-004",
    "UPGRADE-001",
    "UPGRADE-002",
    "UPGRADE-003",
    "UPGRADE-004",
    "DELIVERY-001",
    "DELIVERY-002",
    "DELIVERY-003",
    "DELIVERY-004",
}


def git_blob_sha(data: bytes) -> str:
    header = f"blob {len(data)}\0".encode()
    return hashlib.sha1(header + data, usedforsecurity=False).hexdigest()


def _load_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def _row_to_dict(columns: list[str], row: object, index: int, errors: list[str]) -> dict[str, object]:
    if not isinstance(row, list):
        errors.append(f"invariant row {index} must be an array")
        return {}
    if len(row) != len(columns):
        errors.append(
            f"invariant row {index} has {len(row)} values; expected {len(columns)}"
        )
        return {}
    return dict(zip(columns, row, strict=True))


def validate_repository(root: Path, matrix_path: Path | None = None) -> list[str]:
    root = root.resolve()
    matrix_file = matrix_path or root / MATRIX_PATH
    errors: list[str] = []
    if not matrix_file.is_file():
        return [f"missing invariant matrix: {matrix_file}"]
    try:
        matrix = _load_json(matrix_file)
    except (OSError, json.JSONDecodeError) as exc:
        return [f"cannot parse invariant matrix: {exc}"]
    if not isinstance(matrix, dict):
        return ["invariant matrix root must be an object"]

    if matrix.get("schema_version") != 1:
        errors.append("schema_version must be 1")
    if matrix.get("status") != "normative":
        errors.append("matrix status must be normative")
    baseline = matrix.get("baseline_main_sha")
    if not isinstance(baseline, str) or re.fullmatch(r"[0-9a-f]{40}", baseline) is None:
        errors.append("baseline_main_sha must be a lowercase 40-hex commit SHA")

    raw_columns = matrix.get("columns")
    if raw_columns != REQUIRED_COLUMNS:
        errors.append("matrix columns do not match the required schema")
        columns = REQUIRED_COLUMNS
    else:
        columns = raw_columns

    source_map = matrix.get("sources")
    if not isinstance(source_map, dict):
        errors.append("sources must be an object")
        source_map = {}
    source_ids = set(source_map)
    if source_ids != REQUIRED_SOURCE_IDS:
        errors.append(
            f"source IDs differ: missing={sorted(REQUIRED_SOURCE_IDS - source_ids)} "
            f"extra={sorted(source_ids - REQUIRED_SOURCE_IDS)}"
        )
    for source_id, source in source_map.items():
        if not isinstance(source, dict):
            errors.append(f"source {source_id} must be an object")
            continue
        relative = source.get("path")
        expected_sha = source.get("blob_sha")
        if not isinstance(relative, str) or not relative:
            errors.append(f"source {source_id} has no path")
            continue
        path = root / relative
        if not path.is_file():
            errors.append(f"source {source_id} path does not exist: {relative}")
            continue
        actual_sha = git_blob_sha(path.read_bytes())
        if actual_sha != expected_sha:
            errors.append(
                f"source {source_id} changed without invariant re-audit: "
                f"expected {expected_sha}, got {actual_sha}"
            )

    workflow_map = matrix.get("workflows")
    if not isinstance(workflow_map, dict) or not workflow_map:
        errors.append("workflows must be a non-empty object")
        workflow_map = {}
    for workflow_id, workflow in workflow_map.items():
        if not isinstance(workflow, dict):
            errors.append(f"workflow {workflow_id} must be an object")
            continue
        relative = workflow.get("path")
        step = workflow.get("step")
        if not isinstance(relative, str) or not isinstance(step, str):
            errors.append(f"workflow {workflow_id} requires path and step")
            continue
        path = root / relative
        if not path.is_file():
            errors.append(f"workflow path does not exist: {relative}")
        elif step not in path.read_text(encoding="utf-8"):
            errors.append(f"workflow {workflow_id} step does not exist: {step}")

    required_ids = matrix.get("required_invariant_ids")
    if not isinstance(required_ids, list) or any(not isinstance(item, str) for item in required_ids):
        errors.append("required_invariant_ids must be a string array")
        required_id_set: set[str] = set()
    else:
        required_id_set = set(required_ids)
        if len(required_id_set) != len(required_ids):
            errors.append("required_invariant_ids contains duplicates")
    if required_id_set != EXPECTED_INVARIANT_IDS:
        errors.append(
            f"required invariant catalog differs: missing={sorted(EXPECTED_INVARIANT_IDS - required_id_set)} "
            f"extra={sorted(required_id_set - EXPECTED_INVARIANT_IDS)}"
        )

    rows = matrix.get("invariants")
    if not isinstance(rows, list):
        errors.append("invariants must be an array")
        rows = []
    seen: set[str] = set()
    for index, raw_row in enumerate(rows):
        invariant = _row_to_dict(columns, raw_row, index, errors)
        if not invariant:
            continue
        invariant_id = invariant.get("id")
        if not isinstance(invariant_id, str) or not invariant_id:
            errors.append(f"invariant row {index} has no ID")
            continue
        if invariant_id in seen:
            errors.append(f"duplicate invariant ID: {invariant_id}")
        seen.add(invariant_id)
        for field in ("source", "anchor", "scope", "status", "owner"):
            if not isinstance(invariant.get(field), str) or not invariant[field]:
                errors.append(f"{invariant_id}: {field} must be non-empty")
        source_id = invariant.get("source")
        if source_id not in source_map:
            errors.append(f"{invariant_id}: unknown source {source_id!r}")
        status = invariant.get("status")
        if status not in ALLOWED_STATUSES:
            errors.append(f"{invariant_id}: unsupported status {status!r}")
            continue
        enforcement = invariant.get("enforcement")
        ci = invariant.get("ci")
        planned_slice = invariant.get("planned_slice")
        activation = invariant.get("activation_condition")
        evidence_note = invariant.get("evidence_note")
        expires_on = invariant.get("expires_on")
        if not isinstance(enforcement, list) or any(not isinstance(item, str) for item in enforcement):
            errors.append(f"{invariant_id}: enforcement must be a string array")
            enforcement = []
        if not isinstance(ci, list) or any(not isinstance(item, str) for item in ci):
            errors.append(f"{invariant_id}: ci must be a string array")
            ci = []
        if status == "enforced" and (not enforcement or not ci):
            errors.append(f"{invariant_id}: enforced requires evidence paths and CI references")
        if status == "partially_enforced" and (
            not enforcement or not ci or not isinstance(planned_slice, str) or not planned_slice
        ):
            errors.append(
                f"{invariant_id}: partially_enforced requires evidence, CI and planned_slice"
            )
        if status == "planned" and (not isinstance(planned_slice, str) or not planned_slice):
            errors.append(f"{invariant_id}: planned requires planned_slice")
        if status == "not_applicable_yet" and (
            not isinstance(planned_slice, str)
            or not planned_slice
            or not isinstance(activation, str)
            or not activation
        ):
            errors.append(
                f"{invariant_id}: not_applicable_yet requires planned_slice and activation_condition"
            )
        if status == "review_only":
            if not all(isinstance(value, str) and value for value in (planned_slice, evidence_note, expires_on)):
                errors.append(
                    f"{invariant_id}: review_only requires planned_slice, evidence_note and expires_on"
                )
            else:
                try:
                    expiry = date.fromisoformat(expires_on)
                    revision = date.fromisoformat(str(matrix.get("audit_revision")))
                    if expiry <= revision or expiry > revision + timedelta(days=180):
                        errors.append(
                            f"{invariant_id}: review_only expiry must be within 180 days after audit"
                        )
                except ValueError:
                    errors.append(f"{invariant_id}: invalid review_only date")
        for relative in enforcement:
            if not (root / relative).exists():
                errors.append(f"{invariant_id}: enforcement path does not exist: {relative}")
        for workflow_id in ci:
            if workflow_id not in workflow_map:
                errors.append(f"{invariant_id}: unknown CI reference {workflow_id}")

    if seen != EXPECTED_INVARIANT_IDS:
        errors.append(
            f"invariant rows differ: missing={sorted(EXPECTED_INVARIANT_IDS - seen)} "
            f"extra={sorted(seen - EXPECTED_INVARIANT_IDS)}"
        )

    controls = matrix.get("external_controls")
    if not isinstance(controls, list) or not controls:
        errors.append("external_controls must explicitly record repository-host controls")
    else:
        control_ids: set[str] = set()
        for control in controls:
            if not isinstance(control, dict):
                errors.append("external control must be an object")
                continue
            control_id = control.get("id")
            if not isinstance(control_id, str) or not control_id:
                errors.append("external control has no ID")
                continue
            if control_id in control_ids:
                errors.append(f"duplicate external control ID: {control_id}")
            control_ids.add(control_id)
            if control.get("status") not in ALLOWED_STATUSES:
                errors.append(f"{control_id}: unsupported external control status")
            for field in ("scope", "owner", "planned_slice", "evidence_note"):
                if not isinstance(control.get(field), str) or not control[field]:
                    errors.append(f"{control_id}: {field} must be non-empty")

    document = root / DOCUMENT_PATH
    if not document.is_file():
        errors.append(f"missing explanatory document: {DOCUMENT_PATH}")
    else:
        body = document.read_text(encoding="utf-8")
        for required_text in ("enforced", "partially_enforced", "review_only", "planned", "not_applicable_yet", "GITHUB-001"):
            if required_text not in body:
                errors.append(f"explanatory document omits {required_text}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
    )
    args = parser.parse_args()
    errors = validate_repository(args.repo_root)
    if errors:
        print("invariant enforcement validation failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print("invariant enforcement validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
