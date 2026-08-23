#!/usr/bin/env python3
"""Write small, validated CI evidence instead of retaining large success logs."""

from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
from typing import Mapping, Sequence


SHA = re.compile(r"^[0-9a-f]{40}$")
NAME = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
RESULTS = {"success", "failure", "cancelled", "skipped"}


def parse_checks(values: Sequence[str]) -> dict[str, str]:
    checks: dict[str, str] = {}
    for value in values:
        name, separator, result = value.partition("=")
        if separator != "=" or not NAME.fullmatch(name) or result not in RESULTS:
            raise ValueError(f"invalid check result: {value!r}")
        if name in checks:
            raise ValueError(f"duplicate check: {name}")
        checks[name] = result
    if not checks:
        raise ValueError("at least one check is required")
    return checks


def build_summary(
    sha: str,
    checks: Mapping[str, str],
    env: Mapping[str, str],
) -> dict[str, object]:
    if not SHA.fullmatch(sha):
        raise ValueError("sha must be a lowercase 40-character Git SHA")
    repository = env.get("GITHUB_REPOSITORY", "local/mobile-proxy")
    run_id = env.get("GITHUB_RUN_ID", "local")
    workflow_url = (
        f"https://github.com/{repository}/actions/runs/{run_id}"
        if run_id.isdecimal()
        else None
    )
    passed = all(result == "success" for result in checks.values())
    return {
        "format_version": 1,
        "git_sha": sha,
        "overall": "success" if passed else "failure",
        "checks": dict(sorted(checks.items())),
        "repository": repository,
        "workflow_run": workflow_url,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--sha", required=True)
    parser.add_argument("--check", action="append", default=[])
    args = parser.parse_args()
    summary = build_summary(args.sha, parse_checks(args.check), os.environ)
    args.output.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
