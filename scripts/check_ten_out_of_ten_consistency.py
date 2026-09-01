#!/usr/bin/env python3
"""Cross-document architecture fitness gate for the project 10/10 acceptance model."""

from __future__ import annotations

import json
from pathlib import Path


HISTORICAL_ITEM19_SHA = "d151dbdd156279e32a5361d304c90f996bd2d565"
STALE_FUTURE_SHA = "778c9a6260f58ede0f5a337c5107bc96b022373c"

TEN_PLAN = Path("TEN_OUT_OF_TEN_VALIDATION_PLAN.md")
README = Path("README.md")
RUNTIME = Path("RUNTIME_LAYOUT.md")
BASELINE = Path("docs/PRODUCTION_BASELINE_PLAN.md")
FUTURE = Path("docs/FUTURE_PLATFORM_ARCHITECTURE_ROADMAP.md")
PROJECT_AUTHORITY = Path("docs/operations/project-authority.md")
PHONE = Path("docs/operations/phone-gitops-runtime.md")
RELEASE_ORDER = Path("docs/operations/final-release-authority-order.md")
ITEM19_CLOSEOUT = Path("docs/operations/item19-provider-proof-closeout.md")
ITEM20 = Path("contracts/operations/item20-acceptance-v1.json")
READINESS = Path("contracts/operations/item20-admission-readiness-v1.json")
HANDOFF = Path("contracts/operations/item20-private-handoff-v1.json")
RELEASE_AUTHORITY = Path("contracts/operations/final-release-authority-v1.json")
TOPOLOGY = Path("contracts/operations/production-topology-v1.json")
RELEASE_TAG = Path(".github/workflows/release-tag.yml")
RELEASE = Path(".github/workflows/release.yml")
READINESS_WORKFLOW = Path(".github/workflows/item20-admission-readiness.yml")

RETIRED_TWO_SHA_TOKENS = (
    "candidate_must_match_item19_closeout",
    "exact_immutable_item19_proven_sha",
    "immutable_item19_proven",
    "candidate_control_plane_separation_required",
    "candidate_control_plane_value_inequality_required",
    "control_plane_may_advance_without_redefining_candidate",
    "final_release_control_plane_sha",
)

NORMATIVE_NO_RETIRED = (
    ITEM20,
    READINESS,
    HANDOFF,
    RELEASE_AUTHORITY,
    RELEASE_TAG,
    READINESS_WORKFLOW,
    RELEASE_ORDER,
    PROJECT_AUTHORITY,
    RUNTIME,
    BASELINE,
)


def _read(root: Path, path: Path, errors: list[str]) -> str:
    try:
        return (root / path).read_text(encoding="utf-8")
    except OSError as error:
        errors.append(f"cannot read {path}: {error}")
        return ""


def _load(root: Path, path: Path, errors: list[str]) -> dict[str, object]:
    body = _read(root, path, errors)
    if not body:
        return {}
    try:
        value = json.loads(body)
    except json.JSONDecodeError as error:
        errors.append(f"cannot parse {path}: {error}")
        return {}
    if not isinstance(value, dict):
        errors.append(f"{path} root must be an object")
        return {}
    return value


def _require(body: str, path: Path, tokens: tuple[str, ...], errors: list[str]) -> None:
    for token in tokens:
        if token not in body:
            errors.append(f"{path} is missing 10/10 invariant {token!r}")


def check_repository(root: Path) -> list[str]:
    errors: list[str] = []
    text = {
        path: _read(root, path, errors)
        for path in (
            TEN_PLAN,
            README,
            RUNTIME,
            BASELINE,
            FUTURE,
            PROJECT_AUTHORITY,
            PHONE,
            RELEASE_ORDER,
            ITEM19_CLOSEOUT,
            RELEASE_TAG,
            RELEASE,
            READINESS_WORKFLOW,
        )
    }
    item20 = _load(root, ITEM20, errors)
    readiness = _load(root, READINESS, errors)
    handoff = _load(root, HANDOFF, errors)
    release_authority = _load(root, RELEASE_AUTHORITY, errors)
    topology = _load(root, TOPOLOGY, errors)

    # Release identity: one accepted software SHA from Item 20 through publication.
    identity = item20.get("identity")
    expected_identity = {
        "candidate_sha": "exact_current_protected_main_revision_selected_for_10_of_10_window",
        "control_plane_sha": "same_exact_current_protected_main_revision",
        "exact_equality_required": True,
        "final_release_tag_target": "candidate_sha",
        "source_freeze_after_selection": True,
    }
    if identity != expected_identity:
        errors.append("Item 20 identity is not the protected one-SHA acceptance model")

    admission = item20.get("admission")
    if not isinstance(admission, dict) or any(
        admission.get(key) is not True
        for key in (
            "candidate_must_equal_control_plane_sha",
            "candidate_must_be_exact_current_protected_main",
            "control_plane_must_be_exact_current_protected_main",
            "fresh_candidate_evidence_required",
            "fresh_exact_candidate_provider_proof_required_before_live_window",
            "source_freeze_after_candidate_evidence",
        )
    ):
        errors.append("Item 20 admission does not fail closed on exact protected-main single-SHA identity")

    readiness_wiring = readiness.get("candidate_evidence_workflow")
    if not isinstance(readiness_wiring, dict) or any(
        readiness_wiring.get(key) != value
        for key, value in {
            "candidate_sha": "same_exact_current_protected_main_as_control_plane",
            "candidate_control_plane_exact_equality_required": True,
            "control_plane_sha": "exact_current_protected_main",
        }.items()
    ):
        errors.append("Item 20 readiness contract does not bind candidate and control plane to one protected-main SHA")

    handoff_identity = handoff.get("identity")
    if not isinstance(handoff_identity, dict) or handoff_identity.get("exact_equality_required") is not True:
        errors.append("Item 20 private handoff does not require exact candidate/control-plane equality")

    preconditions = release_authority.get("preconditions")
    if not isinstance(preconditions, dict) or any(
        preconditions.get(key) != value
        for key, value in {
            "item20_release_sha_marker": "final_accepted_candidate_sha",
            "protected_main_sha": "must_equal_exact_accepted_candidate_sha",
            "source_sha_of_published_artifacts": "must_equal_final_tag_target_sha",
        }.items()
    ):
        errors.append("final release authority is not bound to accepted candidate == protected main == published source")

    release_link = topology.get("release_link")
    if not isinstance(release_link, dict) or release_link.get(
        "accepted_candidate_equals_protected_main_equals_final_tag_target_equals_published_source_sha"
    ) is not True:
        errors.append("production topology does not preserve one final release source SHA")

    _require(
        text[TEN_PLAN],
        TEN_PLAN,
        (
            "candidate_sha\n  == control_plane_sha",
            "final_accepted_candidate_sha",
            "source SHA recorded for published artifacts",
            "If protected `main` advances after admission, the acceptance window is stale.",
        ),
        errors,
    )
    _require(
        text[RELEASE_ORDER],
        RELEASE_ORDER,
        (
            "accepted candidate SHA == exact protected `main` SHA == final tag target SHA == source SHA of published artifacts",
            "final_accepted_candidate_sha",
        ),
        errors,
    )
    _require(
        text[RELEASE_TAG],
        RELEASE_TAG,
        (
            "final_accepted_candidate_sha",
            "protected main advanced or differs from the accepted candidate; acceptance is stale",
            'test "$(git rev-parse origin/main)" = "$TARGET_SHA"',
        ),
        errors,
    )
    _require(
        text[RELEASE],
        RELEASE,
        (
            'tag_sha=$(git rev-list -n 1 "$VERIFIED_TAG")',
            'test "$tag_sha" = "$VERIFIED_SHA"',
            '"git_sha": sha',
        ),
        errors,
    )

    # Android role: auxiliary when used, never primary reverse-tunnel owner and never globally absent.
    for path in (TEN_PLAN, RUNTIME, PHONE):
        _require(
            text[path],
            path,
            ("not the primary reverse-tunnel owner", "managed production auxiliary component"),
            errors,
        )
    if "The optional Android app is not installed by the production stack" in text[TEN_PLAN]:
        errors.append("10/10 plan still claims the production APK is globally never installed")
    _require(
        text[README],
        README,
        ("first_party_android_egress", "Network.bindSocket()", "app-owned WireGuard compatibility path"),
        errors,
    )

    # Trust zones: public canonical authority, private execution transport only.
    _require(
        text[PROJECT_AUTHORITY],
        PROJECT_AUTHORITY,
        (
            "only canonical repository for project information",
            "execution satellite",
            "thin caller",
            "must not independently define architecture, roadmap, release policy",
        ),
        errors,
    )
    control_planes = topology.get("control_planes")
    private_phone = control_planes.get("phone") if isinstance(control_planes, dict) else None
    if not isinstance(private_phone, dict) or private_phone.get("authority") != "execution_only":
        errors.append("production topology private phone repository is not execution-only")
    forbidden_responsibilities = private_phone.get("forbidden_responsibilities") if isinstance(private_phone, dict) else None
    if not isinstance(forbidden_responsibilities, list) or not {
        "project_source_of_truth",
        "release_policy",
        "acceptance_policy",
    }.issubset(set(forbidden_responsibilities)):
        errors.append("production topology does not forbid private-repository policy authority")

    # Roadmap: Production Baseline active, future roadmap explicitly non-operational.
    _require(
        text[BASELINE],
        BASELINE,
        (
            "sole canonical implementation roadmap for current development",
            "Item 20 is the first unfinished delivery item",
            "Item 20 remains blocked by the signing-continuity gate",
        ),
        errors,
    )
    if "for the same immutable candidate SHA" in text[BASELINE]:
        errors.append("Production Baseline still implies Item 20 reuses the historical Item 19 candidate SHA")
    _require(
        text[FUTURE],
        FUTURE,
        (
            "FUTURE / POST-BASELINE RECOMMENDATIONS ONLY",
            "sole active implementation roadmap is `docs/PRODUCTION_BASELINE_PLAN.md`",
            "Resolve the exact current protected `main` revision at execution time",
        ),
        errors,
    )
    if STALE_FUTURE_SHA in text[FUTURE] or "The runtime candidate prepared for the first real-phone acceptance remains" in text[FUTURE]:
        errors.append("future roadmap contains stale operational candidate state")

    # Historical evidence is preserved only as history, never as hardcoded active Item 20/release authority.
    if HISTORICAL_ITEM19_SHA not in text[ITEM19_CLOSEOUT]:
        errors.append("historical Item 19 closeout lost its immutable candidate SHA")
    historical = item20.get("historical_item19_proof")
    if not isinstance(historical, dict) or historical.get("candidate_sha") != HISTORICAL_ITEM19_SHA or historical.get("role") != (
        "historical_provider_lifecycle_proof_only_not_item20_final_candidate"
    ):
        errors.append("Item 20 contract does not preserve Item 19 SHA strictly as historical-only evidence")
    if isinstance(identity, dict) and identity.get("candidate_sha") == HISTORICAL_ITEM19_SHA:
        errors.append("historical Item 19 SHA is hardcoded as the active Item 20 candidate")
    for path in (READINESS, RELEASE_AUTHORITY, RELEASE_TAG, READINESS_WORKFLOW):
        if HISTORICAL_ITEM19_SHA in _read(root, path, errors):
            errors.append(f"{path} hardcodes historical Item 19 SHA in active authority")

    # Retired two-SHA semantics are forbidden on normative active surfaces.
    for path in NORMATIVE_NO_RETIRED:
        body = _read(root, path, errors)
        for token in RETIRED_TWO_SHA_TOKENS:
            if token in body:
                errors.append(f"{path} contains retired two-SHA semantic {token!r}")
    return errors


def main() -> int:
    errors = check_repository(Path(__file__).resolve().parents[1])
    if errors:
        print("10/10 architecture consistency validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print("10/10 architecture consistency validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
