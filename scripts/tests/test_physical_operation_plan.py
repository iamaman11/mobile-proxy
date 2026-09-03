from __future__ import annotations

from pathlib import Path
import sys
import unittest


SCRIPT_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import atomic_physical_contracts as ATOMIC
import operation_state_machine as OP
import physical_operation_plan as PLAN
import transaction_runner as KERNEL


class PhysicalOperationPlanTests(unittest.TestCase):
    def test_all_atomic_specs_have_one_destructive_dispatch_and_domains(self) -> None:
        for spec in ATOMIC.ATOMIC_OPERATION_SPECS:
            with self.subTest(operation=spec.contract.operation_id):
                self.assertEqual(ATOMIC.validate_atomic_spec(spec), ())
                self.assertEqual(
                    ATOMIC.primary_destructive_steps(spec.contract),
                    (spec.dispatch_step_id,),
                )
                self.assertTrue(spec.contract.affected_physical_domains)
                self.assertFalse(spec.contract.retryable)
                self.assertFalse(spec.contract.rollback_to_legacy_allowed)

    def test_clean_install_is_six_ordered_atomic_subtransactions(self) -> None:
        plan = PLAN.CURRENT_SOURCE_CLEAN_INSTALL_PLAN
        self.assertEqual(PLAN.validate_plan(plan), ())
        self.assertEqual(
            tuple((step.step_id, step.operation_id) for step in plan.steps),
            (
                ("stop_runtime", "android.runtime-stop.v1"),
                ("remove_runtime", "android.runtime-remove.v1"),
                ("remove_package", "android.package-remove.v1"),
                ("install_package", "android.apk-install.v1"),
                ("materialize_runtime", "android.runtime-materialize.v1"),
                ("start_runtime", "android.runtime-start.v1"),
            ),
        )
        self.assertEqual(
            plan.steps[-1].requires_accepted_steps,
            (
                "stop_runtime",
                "remove_runtime",
                "remove_package",
                "install_package",
                "materialize_runtime",
            ),
        )

    def test_filesystem_certification_legacy_effects_are_decomposed(self) -> None:
        plan = PLAN.FILESYSTEM_CERTIFICATION_PLAN
        self.assertEqual(PLAN.validate_plan(plan), ())
        self.assertEqual(
            tuple(step.step_id for step in plan.steps),
            (
                "scratch_roundtrip",
                "scratch_atomic_replace",
                "managed_root_write",
                "managed_atomic_replace",
            ),
        )
        self.assertGreater(
            len(ATOMIC.primary_destructive_steps(OP.ANDROID_FILESYSTEM_CERTIFICATION)),
            1,
        )

    def test_runtime_binary_repair_separates_replace_stop_and_start(self) -> None:
        plan = PLAN.RUNTIME_BINARY_REPAIR_PLAN
        self.assertEqual(PLAN.validate_plan(plan), ())
        self.assertEqual(
            tuple((step.step_id, step.operation_id) for step in plan.steps),
            (
                ("replace_runtime_binaries", "android.runtime-binary-replace.v1"),
                ("stop_runtime", "android.runtime-stop.v1"),
                ("start_runtime", "android.runtime-start.v1"),
            ),
        )
        replace = ATOMIC.atomic_operation_spec("android.runtime-binary-replace.v1")
        self.assertEqual(
            replace.contract.affected_physical_domains,
            ("filesystem", "runtime"),
        )
        self.assertNotIn("process", replace.contract.affected_physical_domains)

    def test_legacy_clean_install_contract_is_not_atomic(self) -> None:
        destructive = ATOMIC.primary_destructive_steps(
            OP.ANDROID_CURRENT_SOURCE_CLEAN_INSTALL
        )
        self.assertEqual(
            destructive,
            (
                "stop_owned_runtime",
                "remove_owned_runtime",
                "uninstall_legacy_apk",
                "install_new_apk",
                "materialize_runtime",
                "start_runtime",
            ),
        )

    def test_kernel_refuses_multi_destructive_binding_before_any_port_call(self) -> None:
        contract = OP.OperationContract(
            operation_id="android.invalid-composite-binding.v1",
            target="android-production",
            steps=(
                OP.StepContract("authority", "VERIFY", "SOURCE_AUTHORITY"),
                OP.StepContract("lock", "VERIFY", "MUTATION_LOCK"),
                OP.StepContract(
                    "preflight",
                    "VERIFY",
                    "MUTATION_BOUNDARY",
                    mutation_boundary=True,
                ),
                OP.StepContract("intent", "VERIFY", "MUTATION_BOUNDARY"),
                OP.StepContract("effect_one", "MUTATE", "MUTATION_EXECUTION", destructive=True),
                OP.StepContract("effect_two", "MUTATE", "MUTATION_EXECUTION", destructive=True),
                OP.StepContract("verify", "VERIFY", "POSTCONDITION"),
                OP.StepContract("accept", "ACCEPT", "POSTCONDITION", acceptance=True),
            ),
            fact_requirements=(
                OP.FactRequirement(
                    "phone",
                    "registered_phone_access_proven",
                    OP.SAME_TRANSACTION,
                    ("target", "observer", "transaction"),
                ),
            ),
            affected_physical_domains=("runtime",),
            retryable=False,
        )

        class Binding:
            kernel_steps = KERNEL.KernelStepRoles(
                authority_step_id="authority",
                mutation_scope_step_id="lock",
                preflight_step_id="preflight",
                intent_step_id="intent",
                dispatch_step_id="effect_one",
                postcondition_step_id="verify",
                acceptance_step_id="accept",
            )

            def __init__(self) -> None:
                self.contract = contract
                self.request_interpreted = False

            def transaction_id(self, request):
                self.request_interpreted = True
                raise AssertionError("binding request must not be interpreted")

            def mutation_subject_ref(self, request):
                raise AssertionError("mutation subject must not be resolved")

            def dispatch_once(self, request):
                raise AssertionError("physical dispatch must not be reached")

            def verify_postcondition(self, request):
                raise AssertionError("postcondition must not be reached")

        class Ports:
            def __getattribute__(self, name):
                if name.startswith("__"):
                    return object.__getattribute__(self, name)
                raise AssertionError(f"port call must not be reached: {name}")

        binding = Binding()
        with self.assertRaisesRegex(
            KERNEL.TransactionRefusal,
            "exactly one primary destructive dispatch step",
        ):
            KERNEL.TransactionRunner().run(
                object(),
                ports=Ports(),
                binding=binding,
            )
        self.assertFalse(binding.request_interpreted)

    def test_plan_only_advances_after_accepted_prefix(self) -> None:
        plan = PLAN.RUNTIME_RECONSTRUCTION_PLAN
        first = PLAN.classify_plan_progress(plan, {})
        self.assertEqual(first.action, PLAN.PLAN_RUN)
        self.assertEqual(first.step_id, "stop_runtime")

        second = PLAN.classify_plan_progress(
            plan,
            {"stop_runtime": PLAN.ACCEPTED},
        )
        self.assertEqual(second.action, PLAN.PLAN_RUN)
        self.assertEqual(second.step_id, "materialize_runtime")

    def test_unknown_refused_and_quarantined_stop_composite_plan(self) -> None:
        plan = PLAN.RUNTIME_RECONSTRUCTION_PLAN
        for terminal in (PLAN.UNKNOWN, PLAN.REFUSED, PLAN.QUARANTINED):
            with self.subTest(terminal=terminal):
                decision = PLAN.classify_plan_progress(
                    plan,
                    {"stop_runtime": terminal},
                )
                self.assertEqual(decision.action, PLAN.PLAN_STOP)
                self.assertEqual(decision.step_id, "stop_runtime")
                self.assertIn(terminal, decision.reason)

    def test_already_satisfied_skip_is_explicit_and_bounded(self) -> None:
        plan = PLAN.CURRENT_SOURCE_CLEAN_INSTALL_PLAN
        decision = PLAN.classify_plan_progress(
            plan,
            {},
            satisfied_steps=frozenset({"stop_runtime"}),
        )
        self.assertEqual(decision.action, PLAN.PLAN_RUN)
        self.assertEqual(decision.step_id, "remove_runtime")

        with self.assertRaisesRegex(PLAN.PlanValidationError, "not authorized"):
            PLAN.classify_plan_progress(
                plan,
                {
                    "stop_runtime": PLAN.ACCEPTED,
                    "remove_runtime": PLAN.ACCEPTED,
                    "remove_package": PLAN.ACCEPTED,
                },
                satisfied_steps=frozenset({"install_package"}),
            )

    def test_out_of_order_terminal_evidence_fails_closed(self) -> None:
        with self.assertRaisesRegex(
            PLAN.PlanValidationError,
            "later step evidence exists",
        ):
            PLAN.classify_plan_progress(
                PLAN.RUNTIME_RECONSTRUCTION_PLAN,
                {"materialize_runtime": PLAN.ACCEPTED},
            )

    def test_machine_readable_plan_exposes_domains_freshness_and_postconditions(self) -> None:
        payload = PLAN.machine_readable_plan(PLAN.RUNTIME_RECONSTRUCTION_PLAN)
        self.assertEqual(payload["schema"], "atomic-physical-mutation-plan.v1")
        self.assertEqual(
            payload["stop_terminals"],
            ["QUARANTINED", "REFUSED", "UNKNOWN"],
        )
        materialize = payload["steps"][1]
        self.assertEqual(materialize["operation_id"], "android.runtime-materialize.v1")
        self.assertEqual(
            materialize["affected_physical_domains"],
            ["filesystem", "runtime"],
        )
        self.assertEqual(
            materialize["postcondition_step_id"],
            "verify_runtime_materialized",
        )
        freshness = {item["freshness"] for item in materialize["fact_requirements"]}
        self.assertEqual(
            freshness,
            {OP.CAUSAL_REUSE_ALLOWED, OP.SAME_TRANSACTION},
        )

    def test_exact_private_mutator_snapshot_is_fully_classified(self) -> None:
        self.assertEqual(PLAN.validate_private_mutator_inventory(), ())
        self.assertEqual(
            PLAN.PRIVATE_EXECUTION_SHA,
            "4842a6455c44e8f549fd5ea37c2fa28349fc72bb",
        )
        self.assertEqual(
            {item.workflow for item in PLAN.PRIVATE_MUTATOR_INVENTORY},
            {
                "android-signing-migration.yml",
                "phone-clean-install.yml",
                "phone-filesystem-certification.yml",
                "phone-filesystem-quarantine-cleanup.yml",
                "phone-runtime-recovery.yml",
                "phone-runtime-binary-repair.yml",
                "runtime-reconstruction-execution.yml",
            },
        )
        dispositions = {
            item.workflow: item.disposition
            for item in PLAN.PRIVATE_MUTATOR_INVENTORY
        }
        self.assertEqual(dispositions["android-signing-migration.yml"], "hard_blocked")
        self.assertEqual(dispositions["phone-runtime-recovery.yml"], "hard_blocked")
        self.assertEqual(dispositions["phone-clean-install.yml"], "composite")
        self.assertEqual(dispositions["phone-runtime-binary-repair.yml"], "composite")
        self.assertEqual(
            dispositions["runtime-reconstruction-execution.yml"],
            "composite",
        )


if __name__ == "__main__":
    unittest.main()
