#!/usr/bin/env python3
"""Protect the accepted PRODUCT / Deployment Controller v2 foundation invariants.

This checker intentionally validates each invariant at its canonical concern owner.
It must not force the same doctrine into navigation files or resurrect a historical
execution roadmap merely to satisfy literal Markdown checks.
"""

from __future__ import annotations

from pathlib import Path


ARCHITECTURE = Path("docs/architecture/ARCHITECTURE_STANDARD.md")
BASELINE = Path("docs/PRODUCTION_BASELINE_PLAN.md")
STAGE_WORKFLOW = Path("STAGE_WORKFLOW.md")
STAGE_ROADMAP = Path("docs/PRODUCTION_STAGE_ROADMAP.md")
AUTHORITY = Path("docs/operations/project-authority.md")
GITHUB_V2 = Path("contracts/operations/github-control-plane-v2.json")

REQUIRED: dict[Path, tuple[str, ...]] = {
    ARCHITECTURE: (
        "one primary developer",
        "Parallel roadmaps, duplicated policy planes and framework layers",
        "No code for code",
        "adding a checker whose only purpose is to confirm that another checker/test exists or ran",
        "Do not introduce speculative interfaces, factories, registries, plugins or generic frameworks",
        "Protect boundaries, not bootstrap state",
    ),
    BASELINE: (
        "active static architecture/invariant baseline; not an execution roadmap",
        "Both repositories are public.",
        "Deployment admission, target mutation, durable mutation intent, exactly-once dispatch and recovery are Controller responsibilities",
        "durable mutation intent exists before destructive dispatch",
        "`UNKNOWN` continuation is read-only observation/reconciliation",
        "PRODUCT must not reintroduce a second deployment State Machine or mutation ledger.",
        "Old failed workflow runs are never rerun merely to obtain a second physical effect.",
        "combined topology passes Stage 7 end-to-end functional, recovery, bounded-load and soak acceptance",
    ),
    STAGE_WORKFLOW: (
        "A #179 checkpoint that opens a stage is continuous authority for that whole stage",
        "Physical phone state must be **observed, not guessed**.",
        "controller_capability_gap",
        "Architecture improvement is not a parallel workstream.",
    ),
    STAGE_ROADMAP: (
        "static seven-stage sequencing and scope model",
        "Stage 7 — Combined PHONE + VM operational acceptance",
    ),
    AUTHORITY: (
        "Both repositories are public; repository visibility is not the confidentiality boundary.",
        "The PRODUCT repository is the canonical source and release plane.",
        "The Deployment Controller repository is the canonical deployment-execution plane.",
        "durable mutation intent before destructive dispatch",
        "A public GitHub Deployment is not the execution ledger",
        "`RECOVERED` never retroactively converts the original deployment attempt into `ACCEPTED`.",
    ),
    GITHUB_V2: (
        '"authority": "deployment_controller"',
        '"visibility": "public"',
        '"product_source_copy": "forbidden"',
        '"product_public_self_hosted_runner": "forbidden"',
        '"controller_secret_or_raw_device_data_in_public_git_or_issue_evidence"',
        '"public_github_deployment_as_canonical_execution_ledger"',
    ),
}


def _read(root: Path, path: Path, errors: list[str]) -> str:
    try:
        return (root / path).read_text(encoding="utf-8")
    except OSError as error:
        errors.append(f"cannot read {path}: {error}")
        return ""


def check_repository(root: Path) -> list[str]:
    errors: list[str] = []
    for path, tokens in REQUIRED.items():
        body = _read(root, path, errors)
        for token in tokens:
            if token not in body:
                errors.append(f"{path} is missing controller-v2 foundation invariant {token!r}")
    return errors


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    errors = check_repository(root)
    if errors:
        print("controller-v2 foundation consistency validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print("controller-v2 foundation consistency validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
