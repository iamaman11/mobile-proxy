#!/usr/bin/env python3
"""Protect the accepted PRODUCT / Deployment Controller v2 foundation invariants.

This remains intentionally small. It protects the real cross-repository authority
and exactly-once safety boundary; it does not encode a Markdown roadmap, test
another checker, or keep superseded Item19/Item20 development ordering alive.
Behavioral controller semantics belong in Deployment Controller tests and
separately authorized target acceptance.
"""

from __future__ import annotations

from pathlib import Path


IMPLEMENTATION = Path("IMPLEMENTATION_PLAN.md")
BASELINE = Path("docs/PRODUCTION_BASELINE_PLAN.md")
ARCHITECTURE = Path("docs/architecture/ARCHITECTURE_STANDARD.md")
AUTHORITY = Path("docs/operations/project-authority.md")
GITHUB_V2 = Path("contracts/operations/github-control-plane-v2.json")

REQUIRED: dict[Path, tuple[str, ...]] = {
    IMPLEMENTATION: (
        "PRODUCT",
        "DEPLOYMENT CONTROLLER",
        "Both repositories are public.",
        "No new framework is justified merely to reconcile old PRODUCT/controller duplication.",
        "No code for code.",
        "No verification of verification.",
        "No old failed GitHub run is manually rerun to perform a deployment.",
    ),
    BASELINE: (
        "The accepted v2 split is normative:",
        "Both repositories are public.",
        "PRODUCT work must not reintroduce a second runtime State Machine or mutation ledger.",
        "durable mutation intent exists before destructive dispatch",
        "UNKNOWN continuation is read-only observation/reconciliation",
        "No code for code. No verification of verification.",
        "Gate H — real-world acceptance",
    ),
    ARCHITECTURE: (
        "one primary developer",
        "No code for code",
        "adding a checker whose only purpose is to confirm that another checker/test exists or ran",
        "Protect boundaries, not bootstrap state",
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
