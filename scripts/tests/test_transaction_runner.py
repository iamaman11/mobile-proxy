from __future__ import annotations

from contextlib import contextmanager
import json
from pathlib import Path
import sys
import unittest


SCRIPT_DIR = Path(__file__).resolve().parents[1]
ROOT = SCRIPT_DIR.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import control_state_machine as CONTROL
import operation_state_machine as OP
from operations import install_apk as APK
import transaction_runner as RUNNER


TX = "apk-install-tx-1"


def boundary_proof(
    transaction_id: str = TX,
    *,
    persisted: bool = True,
    current_transaction: str | None = None,
) -> RUNNER.BoundaryProof:
    fact = CONTROL.ObservedFact(
        subject="phone",
        predicate="registered_phone_access_proven",
        value=True,
        target="android-production",
        observation_ref="boundary-observation-1",
        source_ref="canonical-source-1",
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
        persisted=persisted,
    )
    context = {
        "target/android-production": "target-binding-generation-7",
        "observer/phone-access": "android.phone-access-observer.v2",
        f"transaction/{transaction_id}": current_transaction or transaction_id,
    }
    return RUNNER.BoundaryProof(fact=fact, current_context=context)


class FakePorts:
    def __init__(
        self,
        *,
        authorized: bool = True,
        boundary: RUNNER.BoundaryProof | None = None,
    ) -> None:
        self.authorized = authorized
        self.boundary = boundary or boundary_proof()
        self.events: list[str] = []
        self.intents: list[RUNNER.MutationIntent] = []
        self.terminals: list[RUNNER.TerminalRecord] = []

    def resolve_authority(self, request, contract):
        self.events.append("authority")
        return RUNNER.AuthorityProof(self.authorized, "authority-proof-1")

    @contextmanager
    def acquire_mutation_scope(self, target, transaction_id):
        self.events.append(f"scope:{target}")
        try:
            yield "mutation-scope-lease-1"
        finally:
            self.events.append("scope_release")

    def prove_same_transaction_boundary(self, contract, transaction_id):
        self.events.append("boundary")
        return self.boundary

    def persist_mutation_intent(self, intent):
        self.events.append("intent")
        self.intents.append(intent)
        return "durable-intent-1"

    def persist_terminal(self, record):
        self.events.append("terminal")
        self.terminals.append(record)
        return "terminal-record-1"


class FakeExecutor:
    def __init__(
        self,
        *,
        unknown: bool = False,
        postcondition_passed: bool = True,
    ) -> None:
        self.unknown = unknown
        self.postcondition_passed = postcondition_passed
        self.calls = 0
        self.events: list[str] | None = None

    def dispatch_once(self, request):
        self.calls += 1
        if self.events is not None:
            self.events.append("dispatch")
        if self.unknown:
            raise RUNNER.DispatchOutcomeUnknown("result channel lost")
        return RUNNER.DispatchReceipt("adapter-result-1")

    def verify_postcondition(self, request):
        if self.events is not None:
            self.events.append("verify")
        return RUNNER.PostconditionProof(
            self.postcondition_passed,
            "postcondition-1",
        )


class TransactionRunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.runner = RUNNER.TransactionRunner()
        self.request = APK.ApkInstallRequest(TX, "artifact/candidate-apk-1")

    def binding(self, executor: FakeExecutor) -> APK.ApkInstallBinding:
        return APK.ApkInstallBinding(executor)

    def test_apk_contract_is_single_package_domain_vertical_slice(self) -> None:
        contract = OP.ANDROID_APK_INSTALL
        self.assertEqual(contract.operation_id, "android.apk-install.v1")
        self.assertEqual(contract.target, "android-production")
        self.assertEqual(contract.affected_physical_domains, ("package",))
        self.assertFalse(contract.retryable)
        self.assertFalse(contract.rollback_to_legacy_allowed)
        self.assertEqual(
            OP.expected_step_ids(contract),
            (
                "resolve_authority",
                "mutation_scope",
                "phone_access_boundary",
                "mutation_intent",
                "install_apk",
                "verify_installed_apk",
                "accept",
            ),
        )
        self.assertEqual(
            OP.recovery_step_ids(contract),
            ("recovery_inspect_package",),
        )
        self.assertIs(OP.operation_contract("android.apk-install.v1"), contract)
        self.assertEqual(
            OP.affected_domain_generation_updates(contract, TX),
            {"domain/package": TX},
        )

    def test_apk_binding_is_exactly_the_contract_edge(self) -> None:
        executor = FakeExecutor()
        binding = self.binding(executor)
        self.assertIs(binding.contract, OP.ANDROID_APK_INSTALL)
        self.assertEqual(binding.dispatch_step_id, "install_apk")
        self.assertEqual(binding.postcondition_step_id, "verify_installed_apk")
        self.assertEqual(binding.acceptance_step_id, "accept")
        self.assertEqual(binding.transaction_id(self.request), TX)
        self.assertEqual(
            binding.mutation_subject_ref(self.request),
            "artifact/candidate-apk-1",
        )

    def test_success_path_enforces_transaction_order_and_persists_terminal_last(self) -> None:
        ports = FakePorts()
        executor = FakeExecutor()
        executor.events = ports.events

        result = self.runner.run(
            self.request,
            ports=ports,
            binding=self.binding(executor),
        )

        self.assertEqual(result.derived["state"], "ACCEPTED")
        self.assertEqual(result.terminal_ref, "terminal-record-1")
        self.assertEqual(executor.calls, 1)
        self.assertEqual(
            ports.events,
            [
                "authority",
                "scope:android-production",
                "boundary",
                "intent",
                "dispatch",
                "verify",
                "terminal",
                "scope_release",
            ],
        )
        self.assertEqual(len(ports.intents), 1)
        intent = ports.intents[0]
        self.assertEqual(intent.dispatch_step_id, "install_apk")
        self.assertEqual(
            intent.mutation_subject_ref,
            "artifact/candidate-apk-1",
        )
        self.assertEqual(intent.affected_domain_generations, {"domain/package": TX})
        self.assertEqual(len(ports.terminals), 1)
        self.assertEqual(ports.terminals[0].derived["state"], "ACCEPTED")

        statuses = [(item.step_id, item.status) for item in result.evidence]
        self.assertLess(
            statuses.index(("mutation_intent", OP.PASSED)),
            statuses.index(("install_apk", OP.DISPATCHED)),
        )
        self.assertLess(
            statuses.index(("install_apk", OP.DISPATCHED)),
            statuses.index(("install_apk", OP.PASSED)),
        )
        self.assertLess(
            statuses.index(("verify_installed_apk", OP.PASSED)),
            statuses.index(("accept", OP.PASSED)),
        )

    def test_lost_post_dispatch_result_is_unknown_and_not_terminalized(self) -> None:
        ports = FakePorts()
        executor = FakeExecutor(unknown=True)
        executor.events = ports.events

        result = self.runner.run(
            self.request,
            ports=ports,
            binding=self.binding(executor),
        )

        self.assertEqual(result.derived["state"], "UNKNOWN_EXECUTION_OUTCOME")
        self.assertIn("blind_retry=FORBIDDEN", result.derived["blocking_predicates"])
        self.assertEqual(result.derived["next_step"], "recovery_inspect_package")
        self.assertEqual(executor.calls, 1)
        self.assertIsNone(result.terminal_ref)
        self.assertEqual(len(ports.terminals), 0)
        self.assertNotIn("verify", ports.events)
        self.assertEqual(
            [(item.step_id, item.status) for item in result.evidence][-1],
            ("install_apk", OP.DISPATCHED),
        )

    def test_unknown_existing_trace_forbids_blind_retry_before_any_new_port_call(self) -> None:
        first_ports = FakePorts()
        first_executor = FakeExecutor(unknown=True)
        first = self.runner.run(
            self.request,
            ports=first_ports,
            binding=self.binding(first_executor),
        )

        retry_ports = FakePorts()
        retry_executor = FakeExecutor()
        with self.assertRaisesRegex(RUNNER.BlindRetryForbidden, "blind retry"):
            self.runner.run(
                self.request,
                ports=retry_ports,
                binding=self.binding(retry_executor),
                existing_evidence=first.evidence,
            )

        self.assertEqual(retry_ports.events, [])
        self.assertEqual(retry_executor.calls, 0)

    def test_same_transaction_boundary_is_required_before_intent_or_dispatch(self) -> None:
        stale = boundary_proof(current_transaction="different-transaction")
        ports = FakePorts(boundary=stale)
        executor = FakeExecutor()

        with self.assertRaisesRegex(RUNNER.TransactionRefusal, "not CURRENT"):
            self.runner.run(
                self.request,
                ports=ports,
                binding=self.binding(executor),
            )

        self.assertEqual(executor.calls, 0)
        self.assertEqual(ports.intents, [])
        self.assertEqual(
            ports.events,
            ["authority", "scope:android-production", "boundary", "scope_release"],
        )

    def test_unpersisted_boundary_is_rejected_before_mutation_intent(self) -> None:
        ports = FakePorts(boundary=boundary_proof(persisted=False))
        executor = FakeExecutor()

        with self.assertRaisesRegex(RUNNER.TransactionRefusal, "not CURRENT"):
            self.runner.run(
                self.request,
                ports=ports,
                binding=self.binding(executor),
            )

        self.assertEqual(executor.calls, 0)
        self.assertEqual(ports.intents, [])

    def test_authority_refusal_never_acquires_mutation_scope(self) -> None:
        ports = FakePorts(authorized=False)
        executor = FakeExecutor()

        result = self.runner.run(
            self.request,
            ports=ports,
            binding=self.binding(executor),
        )

        self.assertEqual(result.derived["state"], "REFUSED")
        self.assertEqual(executor.calls, 0)
        self.assertEqual(ports.events, ["authority", "terminal"])
        self.assertEqual(ports.terminals[0].derived["failure_stage"], "SOURCE_AUTHORITY")

    def test_failed_postcondition_is_known_failure_and_requires_recovery(self) -> None:
        ports = FakePorts()
        executor = FakeExecutor(postcondition_passed=False)

        result = self.runner.run(
            self.request,
            ports=ports,
            binding=self.binding(executor),
        )

        self.assertEqual(result.derived["state"], "RECOVERY_REQUIRED")
        self.assertEqual(result.derived["next_step"], "recovery_inspect_package")
        self.assertEqual(executor.calls, 1)
        self.assertEqual(len(ports.terminals), 1)
        self.assertNotIn(
            ("accept", OP.PASSED),
            [(item.step_id, item.status) for item in result.evidence],
        )

    def test_kernel_contains_no_apk_or_device_command_semantics(self) -> None:
        body = (SCRIPT_DIR / "transaction_runner.py").read_text(encoding="utf-8").lower()
        for forbidden in (
            "apk",
            "adb",
            "artifact_ref",
            "install_apk",
            "verify_apk",
        ):
            self.assertNotIn(forbidden, body)

    def test_apk_binding_is_the_only_implemented_operation_binding(self) -> None:
        operation_files = sorted(
            path.name
            for path in (SCRIPT_DIR / "operations").glob("*.py")
            if path.name != "__init__.py"
        )
        self.assertEqual(operation_files, ["install_apk.py"])

    def test_binding_rejects_wrong_request_type_before_any_executor_call(self) -> None:
        executor = FakeExecutor()
        binding = self.binding(executor)
        with self.assertRaisesRegex(TypeError, "ApkInstallRequest"):
            binding.transaction_id(object())
        self.assertEqual(executor.calls, 0)

    def test_operation_evidence_schema_registers_apk_install_contract(self) -> None:
        schema = json.loads(
            (ROOT / "docs" / "operation-state-evidence-v1.schema.json").read_text(
                encoding="utf-8"
            )
        )
        operations = schema["properties"]["operation_id"]["enum"]
        self.assertIn("android.apk-install.v1", operations)


if __name__ == "__main__":
    unittest.main()
