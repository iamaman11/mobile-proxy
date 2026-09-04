#!/usr/bin/env python3
"""Cross-document fitness gate for the controller-v2 production architecture."""

from __future__ import annotations

import json
from pathlib import Path

HISTORICAL_ITEM19_SHA = "d151dbdd156279e32a5361d304c90f996bd2d565"

TEN_PLAN = Path("TEN_OUT_OF_TEN_VALIDATION_PLAN.md")
README = Path("README.md")
RUNTIME = Path("RUNTIME_LAYOUT.md")
PROJECT_DOC = Path("docs/operations/project-authority.md")
PHONE_DOC = Path("docs/operations/phone-gitops-runtime.md")
RELEASE_DOC = Path("docs/operations/final-release-authority-order.md")
ITEM19_CLOSEOUT = Path("docs/operations/item19-provider-proof-closeout.md")
PROJECT = Path("contracts/operations/project-authority-v2.json")
TOPOLOGY = Path("contracts/operations/production-topology-v2.json")
GITHUB = Path("contracts/operations/github-control-plane-v2.json")
RELEASE_AUTHORITY = Path("contracts/operations/product-release-authority-v2.json")
RELEASE_TAG = Path(".github/workflows/release-tag.yml")
RELEASE = Path(".github/workflows/release.yml")

ACTIVE_NO_V1_AUTHORITY = (
    PROJECT_DOC,
    PHONE_DOC,
    RELEASE_DOC,
    PROJECT,
    TOPOLOGY,
    GITHUB,
    RELEASE_AUTHORITY,
    RELEASE_TAG,
    RELEASE,
)

STALE_ACTIVE_TOKENS = (
    "contracts/operations/final-release-authority-v1.json",
    "private repository/runner remain execution-only",
    "private phone repository/runner remain execution-only",
    "private `mobile-proxy-production` repository remains execution-only",
    "final tag remains forbidden until Item 20",
    "Only after Item 20 physical acceptance",
    "completed Item 20 + final_accepted_candidate_sha",
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
            errors.append(f"{path} is missing controller-v2 invariant {token!r}")


def check_repository(root: Path) -> list[str]:
    errors: list[str] = []
    text = {
        path: _read(root, path, errors)
        for path in (
            TEN_PLAN,
            README,
            RUNTIME,
            PROJECT_DOC,
            PHONE_DOC,
            RELEASE_DOC,
            ITEM19_CLOSEOUT,
            RELEASE_TAG,
            RELEASE,
        )
    }
    project = _load(root, PROJECT, errors)
    topology = _load(root, TOPOLOGY, errors)
    github = _load(root, GITHUB, errors)
    release_authority = _load(root, RELEASE_AUTHORITY, errors)

    # The active authority model is PRODUCT public + Deployment Controller private.
    public = project.get("public_product_authority")
    private = project.get("private_deployment_authority")
    if not isinstance(public, dict) or public.get("repository") != "iamaman11/mobile-proxy":
        errors.append("project v2 does not bind public PRODUCT authority")
    if not isinstance(private, dict) or private.get("repository") != "iamaman11/mobile-proxy-production" or private.get("authority") != "deployment_controller":
        errors.append("project v2 does not bind private Deployment Controller authority")
    runtime_identity = project.get("runtime_identity")
    if not isinstance(runtime_identity, dict) or runtime_identity.get("identity") != "product_release_plus_controller_revision":
        errors.append("runtime identity is not Product Release + controller revision")

    # Product Release must exist before target deployment/physical acceptance.
    release_link = topology.get("release_link")
    if not isinstance(release_link, dict) or release_link.get("product_release_must_exist_before_deployment_admission") is not True or release_link.get("physical_acceptance_before_product_release") is not False:
        errors.append("topology does not enforce Product Release before deployment")
    targets = topology.get("targets")
    vm = targets.get("vm-production") if isinstance(targets, dict) else None
    if not isinstance(vm, dict) or vm.get("destructive_dispatch") != "forbidden_until_proven" or vm.get("reuses_same_controller_kernel") is not True:
        errors.append("VM target is not fail-closed on the shared controller kernel")

    # Transaction semantics are stable across target adapters.
    execution = topology.get("execution_rules")
    if not isinstance(execution, dict) or any(
        execution.get(key) != value
        for key, value in {
            "mutation_intent_before_destructive_dispatch": True,
            "blind_retry_after_dispatch_boundary": False,
            "independent_postcondition_observation": True,
            "unknown_continuation": "read_only_recovery_only",
            "recovered_retroactively_equals_original_success": False,
            "duplicate_semantic_request_second_mutation": "forbidden",
            "recovery_mode_reconciled_after_target_lock": True,
        }.items()
    ):
        errors.append("controller transaction/recovery semantics differ from accepted v2 model")

    # GitHub separates public product publication from private runtime authority.
    if github.get("project_authority_contract") != str(PROJECT):
        errors.append("GitHub v2 contract does not bind project authority v2")
    if github.get("production_topology_contract") != str(TOPOLOGY):
        errors.append("GitHub v2 contract does not bind production topology v2")
    if github.get("product_release_contract") != str(RELEASE_AUTHORITY):
        errors.append("GitHub v2 contract does not bind Product Release v2")
    controller = github.get("private_deployment_controller")
    if not isinstance(controller, dict) or controller.get("authority") != "deployment_controller" or controller.get("command") != "/deploy <target> <vX.Y.Z>":
        errors.append("GitHub v2 contract does not preserve private deployment ingress")

    # Product Release v2 uses an exact annotated tag, signed Android product and typed digest set.
    if release_authority.get("contract_version") != 2:
        errors.append("Product Release authority version differs")
    assets = release_authority.get("required_release_assets")
    expected_assets = [
        "mobile-proxy-linux-x86_64-vMAJOR.MINOR.PATCH.tar.gz",
        "mobile-proxy-android-vMAJOR.MINOR.PATCH.apk",
        "release-manifest.json",
        "provenance.json",
        "artifact-digests.json",
    ]
    if assets != expected_assets:
        errors.append("Product Release exact asset set differs")
    manifest = release_authority.get("manifest")
    if not isinstance(manifest, dict) or manifest.get("content_digest_domain") != "mobile-proxy/product-release-asset/v2" or manifest.get("content_digest_algorithm") != "blake3-256":
        errors.append("Product Release typed digest identity differs")

    _require(
        text[RELEASE_TAG],
        RELEASE_TAG,
        (
            "target SHA does not equal exact protected main",
            "exact protected main has no eligible successful Quality push",
            'test "$(git rev-parse origin/main)" = "$TARGET_SHA"',
            "git tag -a",
            "Physical acceptance required before product tag: false",
            "Phone access performed: false",
            "Deployment performed: false",
        ),
        errors,
    )
    for token in ("ITEM20_ISSUE", "PHONE_SIGNING_ISSUE", "final_accepted_candidate_sha"):
        if token in text[RELEASE_TAG]:
            errors.append(f"release-tag workflow still carries old physical-before-product authority {token!r}")

    _require(
        text[RELEASE],
        RELEASE,
        (
            'tag_sha=$(git rev-list -n 1 "$VERIFIED_TAG")',
            'test "$tag_sha" = "$VERIFIED_SHA"',
            "environment: product-release",
            "scripts/build_signed_android_release.py",
            "scripts/create_release_bundle_v2.py",
            "artifact-digests.json",
            "cmp -s --",
            "gh release verify",
            "GitHub Release immutable: true",
            "Phone access performed: false",
            "Deployment performed: false",
        ),
        errors,
    )

    # Active docs must say release -> deployment, not Item20 -> release.
    _require(
        text[RELEASE_DOC],
        RELEASE_DOC,
        (
            "A Product Release is an **input to deployment**, not an output of prior physical phone acceptance.",
            "only now may private /deploy <target> <tag> consume that Product Release",
            "product_release + exact controller_revision",
            "artifact-digests.json",
            "exact bytes",
        ),
        errors,
    )
    _require(
        text[PROJECT_DOC],
        PROJECT_DOC,
        (
            "One product, two authoritative planes",
            "The private repository is the canonical deployment-execution controller.",
            "runtime_deployment_identity",
            "A Product Release is an input to deployment.",
            "public GitHub Deployment is not the execution ledger",
        ),
        errors,
    )
    _require(
        text[PHONE_DOC],
        PHONE_DOC,
        (
            "private repository is therefore **not** merely a thin execution satellite",
            "/deploy phone-production <vX.Y.Z>",
            "mutation intent exists durably before destructive dispatch",
            "no blind retry occurs after the destructive dispatch boundary",
            "RECOVERED` never retroactively converts the original deployment into `ACCEPTED",
            "re-observe only required dependencies",
        ),
        errors,
    )

    # Android remains an auxiliary product component when topology consumes its capability.
    for path in (TEN_PLAN, RUNTIME, PHONE_DOC):
        body = text[path]
        if "not the primary reverse-tunnel owner" not in body:
            errors.append(f"{path} lost Android auxiliary-role invariant")
    _require(
        text[README],
        README,
        ("first_party_android_egress", "Network.bindSocket()", "app-owned WireGuard compatibility path"),
        errors,
    )

    # Historical Item 19 proof remains historical evidence, not active runtime authority.
    if HISTORICAL_ITEM19_SHA not in text[ITEM19_CLOSEOUT]:
        errors.append("historical Item 19 closeout lost its immutable proof SHA")

    for path in ACTIVE_NO_V1_AUTHORITY:
        body = _read(root, path, errors)
        for token in STALE_ACTIVE_TOKENS:
            if token in body:
                errors.append(f"{path} contains superseded active authority wording {token!r}")

    return errors


def main() -> int:
    errors = check_repository(Path(__file__).resolve().parents[1])
    if errors:
        print("10/10 controller-v2 architecture consistency validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print("10/10 controller-v2 architecture consistency validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
