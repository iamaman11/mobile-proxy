from __future__ import annotations

from dataclasses import dataclass

import operation_state_machine as operation


@dataclass(frozen=True)
class AtomicOperationSpec:
    """Canonical metadata for one kernel-bound physical mutation.

    The operation contract remains the reducer source of truth. This companion
    metadata only identifies the seven universal kernel roles for the contract.
    """

    contract: operation.OperationContract
    authority_step_id: str
    mutation_scope_step_id: str
    preflight_step_id: str
    intent_step_id: str
    dispatch_step_id: str
    postcondition_step_id: str
    acceptance_step_id: str


_PHONE_ACCESS_FACT = operation.FactRequirement(
    "phone",
    "registered_phone_access_proven",
    operation.SAME_TRANSACTION,
    ("target", "observer", "transaction"),
)

_FILESYSTEM_MUTATION_CAPABILITY_FACT = operation.FactRequirement(
    "filesystem",
    "mutation_capability_proven",
    operation.CAUSAL_REUSE_ALLOWED,
    ("target", "observer"),
)

_FILESYSTEM_QUARANTINE_ADMISSION_FACT = operation.FactRequirement(
    "filesystem-quarantine",
    "cleanup_admissible",
    operation.CAUSAL_REUSE_ALLOWED,
    ("target", "observer", "domain"),
)

_RUNTIME_MATERIALIZATION_INPUT_FACT = operation.FactRequirement(
    "runtime-materialization",
    "source_bound_inputs_ready",
    operation.CAUSAL_REUSE_ALLOWED,
    ("target", "observer", "source"),
)

_RUNTIME_BINARY_BUNDLE_FACT = operation.FactRequirement(
    "runtime-binaries",
    "source_bound_bundle_ready",
    operation.CAUSAL_REUSE_ALLOWED,
    ("target", "observer", "source"),
)

_RUNTIME_MATERIALIZED_FACT = operation.FactRequirement(
    "runtime",
    "materialized",
    operation.CAUSAL_REUSE_ALLOWED,
    ("target", "observer", "domain"),
)


def _atomic_contract(
    *,
    operation_id: str,
    dispatch_step_id: str,
    postcondition_step_id: str,
    affected_domains: tuple[str, ...],
    extra_facts: tuple[operation.FactRequirement, ...] = (),
) -> AtomicOperationSpec:
    contract = operation.OperationContract(
        operation_id=operation_id,
        target="android-production",
        steps=(
            operation.StepContract("resolve_authority", "VERIFY", "SOURCE_AUTHORITY"),
            operation.StepContract("mutation_scope", "VERIFY", "MUTATION_LOCK"),
            operation.StepContract(
                "phone_access_boundary",
                "VERIFY",
                "MUTATION_BOUNDARY",
                mutation_boundary=True,
            ),
            operation.StepContract("mutation_intent", "VERIFY", "MUTATION_BOUNDARY"),
            operation.StepContract(
                dispatch_step_id,
                "MUTATE",
                "MUTATION_EXECUTION",
                destructive=True,
            ),
            operation.StepContract(postcondition_step_id, "VERIFY", "POSTCONDITION"),
            operation.StepContract("accept", "ACCEPT", "POSTCONDITION", acceptance=True),
        ),
        recovery_steps=(
            operation.StepContract(
                "recovery_observe",
                "OBSERVE",
                "RECOVERY",
                acceptance=True,
            ),
        ),
        fact_requirements=(*extra_facts, _PHONE_ACCESS_FACT),
        affected_physical_domains=affected_domains,
        retryable=False,
        rollback_to_legacy_allowed=False,
    )
    return AtomicOperationSpec(
        contract=contract,
        authority_step_id="resolve_authority",
        mutation_scope_step_id="mutation_scope",
        preflight_step_id="phone_access_boundary",
        intent_step_id="mutation_intent",
        dispatch_step_id=dispatch_step_id,
        postcondition_step_id=postcondition_step_id,
        acceptance_step_id="accept",
    )


def _existing_apk_install() -> AtomicOperationSpec:
    return AtomicOperationSpec(
        contract=operation.ANDROID_APK_INSTALL,
        authority_step_id="resolve_authority",
        mutation_scope_step_id="mutation_scope",
        preflight_step_id="phone_access_boundary",
        intent_step_id="mutation_intent",
        dispatch_step_id="install_apk",
        postcondition_step_id="verify_installed_apk",
        acceptance_step_id="accept",
    )


ANDROID_APK_INSTALL = _existing_apk_install()

ANDROID_PACKAGE_REMOVE = _atomic_contract(
    operation_id="android.package-remove.v1",
    dispatch_step_id="remove_package",
    postcondition_step_id="verify_package_absent",
    affected_domains=("package",),
)

ANDROID_RUNTIME_STOP = _atomic_contract(
    operation_id="android.runtime-stop.v1",
    dispatch_step_id="stop_runtime",
    postcondition_step_id="verify_runtime_stopped",
    affected_domains=("process",),
)

ANDROID_RUNTIME_REMOVE = _atomic_contract(
    operation_id="android.runtime-remove.v1",
    dispatch_step_id="remove_runtime",
    postcondition_step_id="verify_runtime_absent",
    affected_domains=("filesystem", "runtime", "process"),
)

ANDROID_RUNTIME_MATERIALIZE = _atomic_contract(
    operation_id="android.runtime-materialize.v1",
    dispatch_step_id="materialize_runtime",
    postcondition_step_id="verify_runtime_materialized",
    affected_domains=("filesystem", "runtime"),
    extra_facts=(_RUNTIME_MATERIALIZATION_INPUT_FACT,),
)

ANDROID_RUNTIME_START = _atomic_contract(
    operation_id="android.runtime-start.v1",
    dispatch_step_id="start_runtime",
    postcondition_step_id="verify_runtime_local_health",
    affected_domains=("process",),
    extra_facts=(_RUNTIME_MATERIALIZED_FACT,),
)

ANDROID_RUNTIME_BINARY_REPAIR = _atomic_contract(
    operation_id="android.runtime-binary-repair.v1",
    dispatch_step_id="repair_runtime_binaries",
    postcondition_step_id="verify_runtime_binaries",
    affected_domains=("filesystem", "runtime", "process"),
    extra_facts=(_RUNTIME_BINARY_BUNDLE_FACT,),
)

ANDROID_FILESYSTEM_SCRATCH_ROUNDTRIP = _atomic_contract(
    operation_id="android.filesystem-scratch-roundtrip.v1",
    dispatch_step_id="scratch_roundtrip",
    postcondition_step_id="verify_scratch_roundtrip",
    affected_domains=("filesystem",),
    extra_facts=(_FILESYSTEM_MUTATION_CAPABILITY_FACT,),
)

ANDROID_FILESYSTEM_SCRATCH_ATOMIC_REPLACE = _atomic_contract(
    operation_id="android.filesystem-scratch-atomic-replace.v1",
    dispatch_step_id="scratch_atomic_replace",
    postcondition_step_id="verify_scratch_atomic_replace",
    affected_domains=("filesystem",),
    extra_facts=(_FILESYSTEM_MUTATION_CAPABILITY_FACT,),
)

ANDROID_FILESYSTEM_MANAGED_ROOT_WRITE = _atomic_contract(
    operation_id="android.filesystem-managed-root-write.v1",
    dispatch_step_id="managed_root_write",
    postcondition_step_id="verify_managed_root_write",
    affected_domains=("filesystem",),
    extra_facts=(_FILESYSTEM_MUTATION_CAPABILITY_FACT,),
)

ANDROID_FILESYSTEM_MANAGED_ATOMIC_REPLACE = _atomic_contract(
    operation_id="android.filesystem-managed-atomic-replace.v1",
    dispatch_step_id="managed_atomic_replace",
    postcondition_step_id="verify_managed_atomic_replace",
    affected_domains=("filesystem",),
    extra_facts=(_FILESYSTEM_MUTATION_CAPABILITY_FACT,),
)

ANDROID_FILESYSTEM_QUARANTINE_CLEANUP = _atomic_contract(
    operation_id="android.filesystem-quarantine-cleanup-atomic.v1",
    dispatch_step_id="cleanup_quarantine",
    postcondition_step_id="verify_quarantine_absent",
    affected_domains=("filesystem",),
    extra_facts=(_FILESYSTEM_QUARANTINE_ADMISSION_FACT,),
)


ATOMIC_OPERATION_SPECS = (
    ANDROID_APK_INSTALL,
    ANDROID_PACKAGE_REMOVE,
    ANDROID_RUNTIME_STOP,
    ANDROID_RUNTIME_REMOVE,
    ANDROID_RUNTIME_MATERIALIZE,
    ANDROID_RUNTIME_START,
    ANDROID_RUNTIME_BINARY_REPAIR,
    ANDROID_FILESYSTEM_SCRATCH_ROUNDTRIP,
    ANDROID_FILESYSTEM_SCRATCH_ATOMIC_REPLACE,
    ANDROID_FILESYSTEM_MANAGED_ROOT_WRITE,
    ANDROID_FILESYSTEM_MANAGED_ATOMIC_REPLACE,
    ANDROID_FILESYSTEM_QUARANTINE_CLEANUP,
)

_ATOMIC_BY_ID = {item.contract.operation_id: item for item in ATOMIC_OPERATION_SPECS}


def atomic_operation_spec(operation_id: str) -> AtomicOperationSpec:
    try:
        return _ATOMIC_BY_ID[operation_id]
    except KeyError as error:
        raise ValueError(f"unknown atomic physical operation: {operation_id}") from error


def primary_destructive_steps(
    contract: operation.OperationContract,
) -> tuple[str, ...]:
    return tuple(step.step_id for step in contract.steps if step.destructive)


def validate_atomic_spec(spec: AtomicOperationSpec) -> tuple[str, ...]:
    """Return fail-closed validation errors for one atomic operation spec."""

    contract = spec.contract
    ids = operation.expected_step_ids(contract)
    roles = (
        spec.authority_step_id,
        spec.mutation_scope_step_id,
        spec.preflight_step_id,
        spec.intent_step_id,
        spec.dispatch_step_id,
        spec.postcondition_step_id,
        spec.acceptance_step_id,
    )
    errors: list[str] = []
    if ids != roles:
        errors.append("atomic operation roles differ from ordered primary contract")
    if primary_destructive_steps(contract) != (spec.dispatch_step_id,):
        errors.append("atomic operation must have exactly one primary destructive dispatch")
    if not contract.fact_requirements:
        errors.append("atomic operation must declare causal preflight requirements")
    if not contract.affected_physical_domains:
        errors.append("atomic operation must declare affected physical domains")
    if contract.retryable:
        errors.append("atomic physical operation cannot be blindly retryable")
    if contract.rollback_to_legacy_allowed:
        errors.append("atomic physical operation cannot allow legacy rollback")
    return tuple(errors)
