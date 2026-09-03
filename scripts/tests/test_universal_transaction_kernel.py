from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import sys
import unittest


SCRIPT_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import control_state_machine as CONTROL
import operation_state_machine as OP
import transaction_runner as KERNEL


TX = "generic-runtime-tx-1"

GENERIC_CONTRACT = OP.OperationContract(
    operation_id="android.runtime-reconcile.v1",
    target="android-production",
    steps=(
        OP.StepContract("authority", "VERIFY", "SOURCE_AUTHORITY"),
        OP.StepContract("global_lock", "VERIFY", "MUTATION_LOCK"),
        OP.StepContract(
            "causal_preflight",
            "VERIFY",
            "MUTATION_BOUNDARY",
            mutation_boundary=True,
        ),
        OP.StepContract("intent", "VERIFY", "MUTATION_BOUNDARY"),
        OP.StepContract(
            "reconcile_runtime",
            "MUTATE",
            "MUTATION_EXECUTION",
            destructive=True,
        ),
        OP.StepContract("verify_runtime", "VERIFY", "POSTCONDITION"),
        OP.StepContract("accept_runtime", "ACCEPT", "POSTCONDITION", acceptance=True),
    ),
    recovery_steps=(
        OP.StepContract(
            "recovery_observe_runtime",
            "OBSERVE",
            "RECOVERY",
            acceptance=True,
        ),
    ),
    fact_requirements=(
        OP.FactRequirement(
            "runtime",
            "materialization_ready",
            OP.CAUSAL_REUSE_ALLOWED,
            ("target", "observer", "domain"),
        ),
        OP.FactRequirement(
            "phone",
            "registered_phone_access_proven",
            OP.SAME_TRANSACTION,
            ("target", "observer", "transaction"),
        ),
    ),
    affected_physical_domains=("runtime", "provider"),
    retryable=False,
    rollback_to_legacy_allowed=False,
)

GENERIC_ROLES = KERNEL.KernelStepRoles(
    authority_step_id="authority",
    mutation_scope_step_id="global_lock",
    preflight_step_id="causal_preflight",
    intent_step_id="intent",
    dispatch_step_id="reconcile_runtime",
    postcondition_step_id="verify_runtime",
    acceptance_step_id="accept_runtime",
)


def runtime_fact(*, generation: str = "runtime-generation-7") -> KERNEL.BoundaryProof:
    fact = CONTROL.ObservedFact(
        subject="runtime",
        predicate="materialization_ready",
        value=True,
        target="android-production",
        observation_ref="runtime-observation-1",
        source_ref="canonical-source-provenance-1",
        dependencies=(
            CONTROL.FactDependency(
                "target/android-production",
                "target-binding-generation-7",
            ),
            CONTROL.FactDependency(
                "observer/runtime-materialization",
                "android.runtime-materialization-observer.v1",
            ),
            CONTROL.FactDependency(
                "domain/runtime",
                generation,
            ),
        ),
    )
    return KERNEL.BoundaryProof(
        fact=fact,
        current_context={
            "target/android-production": "target-binding-generation-7",
            "observer/runtime-materialization": "android.runtime-materialization-observer.v1",
            "domain/runtime": "runtime-generation-7",
            "source/public-main": "different-unrelated-git-sha",
        },
    )


def phone_fact(transaction_id: str = TX) -> KERNEL.BoundaryProof:
    fact = CONTROL.ObservedFact(
        subject="phone",
        predicate="registered_phone_access_proven",
        value=True,
        target="android-production",
        observation_ref="phone-boundary-observation-1",
        source_ref="canonical-source-provenance-1",
        dependencies=(
            CONTROL.FactDependency(
                "target/android-production",
                "target-binding-generation-7",
            ),
            CONTROL.FactDependency(
                "observer/phone-access",
                "android.phone-access-observer.v2",
            ),
            CONTROL.FactDependency(
                f"transaction/{transaction_id}",
                transaction_id,
            ),
        ),
    )
    return KERNEL.BoundaryProof(
        fact=fact,
        current_context={
            "target/android-production": "target-binding-generation-7",
            "observer/phone-access": "android.phone-access-observer.v2",
            f"transaction/{transaction_id}": transaction_id,
        },
    )


class GenericPorts:
    def __init__(self, *, runtime_generation: str = "runtime-generation-7") -> None:
        self.runtime_generation = runtime_generation
        self.events: list[str] = []
        self.intents: list[KERNEL.MutationIntent] = []
        self.terminals: list[KERNEL.TerminalRecord] = []

    def resolve_authority(self, request, contract):
        self.events.append("authority")
        return KERNEL.AuthorityProof(True, "authority-proof-1")

    @contextmanager
    def acquire_mutation_scope(self, target, transaction_id):
        self.events.append("global_lock")
        try:
            yield "production-phone-global-mutation:lease-1"
        finally:
            self.events.append("global_lock_release")

    def prove_same_transaction_boundary(self, contract, transaction_id):
        raise AssertionError("multi-fact operation must use prove_preflight_requirements")

    def prove_preflight_requirements(self, contract, transaction_id):
        self.events.append("preflight")
        return (
            runtime_fact(generation=self.runtime_generation),
            phone_fact(transaction_id),
        )

    def persist_mutation_intent(self, intent):
        self.events.append("intent")
        self.intents.append(intent)
        return "durable-intent-1"

    def persist_terminal(self, record):
        self.events.append("terminal")
        self.terminals.append(record)
        return "terminal-record-1"


class GenericBinding:
    contract = GENERIC_CONTRACT
    kernel_steps = GENERIC_ROLES

    def __init__(self) -> None:
        self.dispatch_calls = 0

    def transaction_id(self, request):
        return TX

    def mutation_subject_ref(self, request):
        return "runtime/desired-generation-8"

    def dispatch_once(self, request):
        self.dispatch_calls += 1
        return KERNEL.DispatchReceipt("runtime-dispatch-receipt-1")

    def verify_postcondition(self, request):
        return KERNEL.PostconditionProof(True, "runtime-postcondition-1")


class UniversalPhysicalTransactionKernelTests(unittest.TestCase):
    def test_semantic_request_identity_matches_private_router_contract(self) -> None:
        artifact = "b3:" + ("a" * 64)
        identity = KERNEL.build_semantic_request_identity(
            operation="android.apk-install.v1",
            arguments=(artifact,),
            authority_cursor="issue179-comment-5529791292",
        )
        self.assertEqual(
            identity.desired_generation,
            "gen-sha256:fe41ff66efff18c005734997b011f906d337b3c8f487f5a277c1a4522d0c31fb",
        )
        self.assertEqual(
            identity.request_id,
            "req-sha256:1c5e47745e42d9d5247e07ae3b9a980944297be69d103cc0d7bc182e0316195d",
        )
        self.assertEqual(
            KERNEL.derive_physical_transaction_id(
                identity,
                "android.apk-install.v1",
            ),
            "tx-sha256:20687b8375dea3be604b032384da3af4dd771f062013f90362ec6ed4a6163a84",
        )

    def test_generic_multi_domain_operation_uses_one_kernel_and_targeted_generations(self) -> None:
        ports = GenericPorts()
        binding = GenericBinding()
        result = KERNEL.TransactionRunner().run(
            object(),
            ports=ports,
            binding=binding,
        )

        self.assertEqual(result.lifecycle_state, KERNEL.TERMINAL_ACCEPTED)
        self.assertEqual(result.derived["state"], "ACCEPTED")
        self.assertEqual(binding.dispatch_calls, 1)
        self.assertEqual(
            ports.events,
            [
                "authority",
                "global_lock",
                "preflight",
                "intent",
                "terminal",
                "global_lock_release",
            ],
        )
        self.assertEqual(len(ports.intents), 1)
        self.assertEqual(
            ports.intents[0].affected_domain_generations,
            {
                "domain/runtime": TX,
                "domain/provider": TX,
            },
        )
        self.assertEqual(
            ports.intents[0].preflight_observation_refs,
            (
                "runtime-observation-1",
                "phone-boundary-observation-1",
            ),
        )
        self.assertEqual(ports.terminals[0].lifecycle_state, KERNEL.TERMINAL_ACCEPTED)

    def test_changed_declared_domain_generation_blocks_before_intent_and_dispatch(self) -> None:
        ports = GenericPorts(runtime_generation="old-runtime-generation")
        binding = GenericBinding()

        with self.assertRaisesRegex(KERNEL.TransactionRefusal, "not CURRENT"):
            KERNEL.TransactionRunner().run(
                object(),
                ports=ports,
                binding=binding,
            )

        self.assertEqual(binding.dispatch_calls, 0)
        self.assertEqual(ports.intents, [])
        self.assertEqual(
            ports.events,
            [
                "authority",
                "global_lock",
                "preflight",
                "global_lock_release",
            ],
        )


if __name__ == "__main__":
    unittest.main()
