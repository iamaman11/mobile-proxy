from __future__ import annotations

from contextlib import contextmanager
from dataclasses import fields
from pathlib import Path
import sys
import unittest


SCRIPT_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import atomic_physical_contracts as ATOMIC
import control_state_machine as CONTROL
import transaction_runner as KERNEL
from operations import filesystem as FS
from operations import package as PACKAGE
from operations import registry as REGISTRY
from operations import runtime as RUNTIME


SEMANTIC = KERNEL.SemanticRequestIdentity(
    schema=KERNEL.SEMANTIC_REQUEST_SCHEMA,
    request_id="req-sha256:" + "a" * 64,
    operation="converge-phone",
    arguments=("production-desired-state",),
    authority_cursor="issue179-comment-5530639899",
    desired_generation="gen-sha256:" + "b" * 64,
)


def cases():
    return (
        (
            "android.package-remove.v1",
            PACKAGE.PackageRemoveRequest(SEMANTIC, "com.example.mobileproxy"),
            PACKAGE.PackageRemoveExecutor,
            PACKAGE.PackageRemoveBinding,
            "remove_package_once",
            "observe_package_absent",
        ),
        (
            "android.runtime-stop.v1",
            RUNTIME.RuntimeStopRequest(SEMANTIC, "runtime/current"),
            RUNTIME.RuntimeStopExecutor,
            RUNTIME.RuntimeStopBinding,
            "stop_once",
            "observe_stopped",
        ),
        (
            "android.runtime-remove.v1",
            RUNTIME.RuntimeRemoveRequest(SEMANTIC, "runtime/root"),
            RUNTIME.RuntimeRemoveExecutor,
            RUNTIME.RuntimeRemoveBinding,
            "remove_once",
            "observe_absent",
        ),
        (
            "android.runtime-materialize.v1",
            RUNTIME.RuntimeMaterializeRequest(
                SEMANTIC,
                "runtime/release/source-1",
                "artifact/runtime-release-1",
            ),
            RUNTIME.RuntimeMaterializeExecutor,
            RUNTIME.RuntimeMaterializeBinding,
            "materialize_once",
            "observe_materialized",
        ),
        (
            "android.runtime-start.v1",
            RUNTIME.RuntimeStartRequest(SEMANTIC, "runtime/release/source-1"),
            RUNTIME.RuntimeStartExecutor,
            RUNTIME.RuntimeStartBinding,
            "start_once",
            "observe_local_health",
        ),
        (
            "android.runtime-binary-replace.v1",
            RUNTIME.RuntimeBinaryReplaceRequest(
                SEMANTIC,
                "runtime/current/bin",
                "artifact/runtime-binaries-1",
            ),
            RUNTIME.RuntimeBinaryReplaceExecutor,
            RUNTIME.RuntimeBinaryReplaceBinding,
            "replace_binaries_once",
            "observe_binary_digests",
        ),
        (
            "android.filesystem-scratch-roundtrip.v1",
            FS.FilesystemScratchRoundtripRequest(
                SEMANTIC,
                "filesystem/scratch/tx-1",
                "payload/original-1",
            ),
            FS.FilesystemScratchRoundtripExecutor,
            FS.FilesystemScratchRoundtripBinding,
            "scratch_roundtrip_once",
            "observe_scratch_roundtrip",
        ),
        (
            "android.filesystem-scratch-atomic-replace.v1",
            FS.FilesystemScratchAtomicReplaceRequest(
                SEMANTIC,
                "filesystem/scratch/tx-1",
                "payload/replacement-1",
            ),
            FS.FilesystemScratchAtomicReplaceExecutor,
            FS.FilesystemScratchAtomicReplaceBinding,
            "scratch_atomic_replace_once",
            "observe_scratch_atomic_replace",
        ),
        (
            "android.filesystem-managed-root-write.v1",
            FS.FilesystemManagedRootWriteRequest(
                SEMANTIC,
                "filesystem/managed/tx-1",
                "payload/original-1",
            ),
            FS.FilesystemManagedRootWriteExecutor,
            FS.FilesystemManagedRootWriteBinding,
            "managed_root_write_once",
            "observe_managed_root_write",
        ),
        (
            "android.filesystem-managed-atomic-replace.v1",
            FS.FilesystemManagedAtomicReplaceRequest(
                SEMANTIC,
                "filesystem/managed/tx-1",
                "payload/replacement-1",
            ),
            FS.FilesystemManagedAtomicReplaceExecutor,
            FS.FilesystemManagedAtomicReplaceBinding,
            "managed_atomic_replace_once",
            "observe_managed_atomic_replace",
        ),
        (
            "android.filesystem-quarantine-cleanup-atomic.v1",
            FS.FilesystemQuarantineCleanupRequest(
                SEMANTIC,
                "filesystem/quarantine/tx-set-1",
            ),
            FS.FilesystemQuarantineCleanupExecutor,
            FS.FilesystemQuarantineCleanupBinding,
            "quarantine_cleanup_once",
            "observe_quarantine_absent",
        ),
    )


class RecordingDispatch:
    def __init__(self, method_name: str, *, fail: bool = False) -> None:
        self.method_name = method_name
        self.fail = fail
        self.calls: list[object] = []

    def __getattr__(self, name: str):
        if name != self.method_name:
            raise AttributeError(name)

        def invoke(request):
            self.calls.append(request)
            if self.fail:
                raise RuntimeError("ambiguous dispatch")
            return KERNEL.DispatchReceipt("physical-dispatch-receipt-1")

        return invoke


class RecordingObserver:
    def __init__(
        self,
        method_name: str,
        *,
        passed: bool = True,
        fail: bool = False,
    ) -> None:
        self.method_name = method_name
        self.passed = passed
        self.fail = fail
        self.calls: list[object] = []

    def __getattr__(self, name: str):
        if name != self.method_name:
            raise AttributeError(name)

        def invoke(request):
            self.calls.append(request)
            if self.fail:
                raise RuntimeError("postcondition unavailable")
            return KERNEL.PostconditionProof(
                self.passed,
                "postcondition-observation-1",
            )

        return invoke


class KernelPorts:
    def __init__(self) -> None:
        self.intents: list[KERNEL.MutationIntent] = []
        self.terminals: list[KERNEL.TerminalRecord] = []

    def resolve_authority(self, request, contract):
        return KERNEL.AuthorityProof(True, "authority-proof-1")

    @contextmanager
    def acquire_mutation_scope(self, target, transaction_id):
        yield "production-phone-global-mutation:lease-1"

    def prove_same_transaction_boundary(self, contract, transaction_id):
        raise AssertionError("canonical atomic contracts use proof-set admission")

    def prove_preflight_requirements(self, contract, transaction_id):
        return tuple(
            self._proof(requirement, transaction_id, index)
            for index, requirement in enumerate(contract.fact_requirements)
        )

    def _proof(self, requirement, transaction_id: str, index: int):
        dependencies = []
        current_context = {}
        for kind in requirement.required_dependency_kinds:
            if kind == "target":
                scope = "target/android-production"
                identity = "target-binding-generation-1"
            elif kind == "observer":
                scope = f"observer/test-{index}"
                identity = f"observer-generation-{index}"
            elif kind == "transaction":
                scope = f"transaction/{transaction_id}"
                identity = transaction_id
            elif kind == "domain":
                scope = f"domain/test-{index}"
                identity = f"domain-generation-{index}"
            elif kind == "source":
                scope = f"source/test-{index}"
                identity = f"source-generation-{index}"
            else:
                raise AssertionError(f"unsupported dependency kind: {kind}")
            dependencies.append(CONTROL.FactDependency(scope, identity))
            current_context[scope] = identity

        fact = CONTROL.ObservedFact(
            subject=requirement.subject,
            predicate=requirement.predicate,
            value=True,
            target="android-production",
            observation_ref=f"preflight-observation-{index}",
            source_ref="canonical-source-ref",
            dependencies=tuple(dependencies),
        )
        return KERNEL.BoundaryProof(fact, current_context)

    def persist_mutation_intent(self, intent):
        self.intents.append(intent)
        return "durable-intent-1"

    def persist_terminal(self, record):
        self.terminals.append(record)
        return "terminal-record-1"


class CanonicalAtomicExecutorTests(unittest.TestCase):
    def test_registry_covers_exact_accepted_atomic_inventory(self) -> None:
        expected = {spec.contract.operation_id for spec in ATOMIC.ATOMIC_OPERATION_SPECS}
        self.assertEqual(set(REGISTRY.CANONICAL_BINDING_TYPES), expected)
        self.assertEqual(set(REGISTRY.CANONICAL_EXECUTOR_TYPES), expected)

    def test_every_new_binding_consumes_exact_accepted_contract_and_roles(self) -> None:
        for operation_id, _, _, binding_type, _, _ in cases():
            with self.subTest(operation_id=operation_id):
                spec = ATOMIC.atomic_operation_spec(operation_id)
                self.assertIs(binding_type.contract, spec.contract)
                self.assertEqual(
                    binding_type.kernel_steps,
                    KERNEL.KernelStepRoles(
                        spec.authority_step_id,
                        spec.mutation_scope_step_id,
                        spec.preflight_step_id,
                        spec.intent_step_id,
                        spec.dispatch_step_id,
                        spec.postcondition_step_id,
                        spec.acceptance_step_id,
                    ),
                )
                self.assertEqual(ATOMIC.validate_atomic_spec(spec), ())

    def test_dispatch_and_postcondition_are_separate_injected_edges(self) -> None:
        for operation_id, request, executor_type, binding_type, dispatch_method, observer_method in cases():
            with self.subTest(operation_id=operation_id):
                dispatch = RecordingDispatch(dispatch_method)
                observer = RecordingObserver(observer_method)
                binding = binding_type(executor_type(dispatch, observer))

                receipt = binding.dispatch_once(request)
                self.assertEqual(receipt.source_ref, "physical-dispatch-receipt-1")
                self.assertEqual(dispatch.calls, [request])
                self.assertEqual(observer.calls, [])

                proof = binding.verify_postcondition(request)
                self.assertTrue(proof.passed)
                self.assertEqual(dispatch.calls, [request])
                self.assertEqual(observer.calls, [request])

    def test_transaction_identity_is_semantic_and_has_no_github_run_provenance(self) -> None:
        forbidden_fields = {
            "github_run_id",
            "github_run_attempt",
            "workflow_run_id",
            "source_comment_id",
        }
        for operation_id, request, executor_type, binding_type, dispatch_method, observer_method in cases():
            with self.subTest(operation_id=operation_id):
                binding = binding_type(
                    executor_type(
                        RecordingDispatch(dispatch_method),
                        RecordingObserver(observer_method),
                    )
                )
                expected = KERNEL.derive_physical_transaction_id(
                    SEMANTIC,
                    operation_id,
                )
                self.assertEqual(binding.transaction_id(request), expected)
                self.assertEqual(binding.transaction_id(request), expected)
                self.assertEqual(binding.semantic_request_identity(request), SEMANTIC)
                self.assertTrue(
                    forbidden_fields.isdisjoint({item.name for item in fields(request)})
                )

    def test_false_postcondition_cannot_accept_transaction(self) -> None:
        _, request, executor_type, binding_type, dispatch_method, observer_method = cases()[0]
        dispatch = RecordingDispatch(dispatch_method)
        observer = RecordingObserver(observer_method, passed=False)
        binding = binding_type(executor_type(dispatch, observer))

        result = KERNEL.TransactionRunner().run(
            request,
            ports=KernelPorts(),
            binding=binding,
        )

        self.assertNotEqual(result.lifecycle_state, KERNEL.TERMINAL_ACCEPTED)
        self.assertNotEqual(result.derived["state"], "ACCEPTED")
        self.assertEqual(len(dispatch.calls), 1)
        self.assertEqual(len(observer.calls), 1)

    def test_observer_exception_after_dispatch_is_unknown_and_blocks_blind_retry(self) -> None:
        _, request, executor_type, binding_type, dispatch_method, observer_method = cases()[1]
        dispatch = RecordingDispatch(dispatch_method)
        observer = RecordingObserver(observer_method, fail=True)
        binding = binding_type(executor_type(dispatch, observer))
        runner = KERNEL.TransactionRunner()

        result = runner.run(request, ports=KernelPorts(), binding=binding)

        self.assertEqual(result.lifecycle_state, KERNEL.TERMINAL_UNKNOWN)
        self.assertEqual(result.derived["state"], "UNKNOWN_EXECUTION_OUTCOME")
        self.assertEqual(len(dispatch.calls), 1)
        self.assertEqual(len(observer.calls), 1)

        retry_dispatch = RecordingDispatch(dispatch_method)
        retry_binding = binding_type(
            executor_type(retry_dispatch, RecordingObserver(observer_method))
        )
        with self.assertRaises(KERNEL.BlindRetryForbidden):
            runner.run(
                request,
                ports=KernelPorts(),
                binding=retry_binding,
                existing_evidence=result.evidence,
            )
        self.assertEqual(retry_dispatch.calls, [])

    def test_dispatch_ambiguity_is_unknown_without_postcondition_call(self) -> None:
        _, request, executor_type, binding_type, dispatch_method, observer_method = cases()[2]
        dispatch = RecordingDispatch(dispatch_method, fail=True)
        observer = RecordingObserver(observer_method)
        binding = binding_type(executor_type(dispatch, observer))

        result = KERNEL.TransactionRunner().run(
            request,
            ports=KernelPorts(),
            binding=binding,
        )

        self.assertEqual(result.lifecycle_state, KERNEL.TERMINAL_UNKNOWN)
        self.assertEqual(result.derived["state"], "UNKNOWN_EXECUTION_OUTCOME")
        self.assertEqual(len(dispatch.calls), 1)
        self.assertEqual(observer.calls, [])

    def test_executor_modules_do_not_own_control_plane_semantics(self) -> None:
        forbidden = (
            "resolve_authority",
            "acquire_mutation_scope",
            "persist_mutation_intent",
            "persist_terminal",
            "blindretryforbidden",
            "github_run_attempt",
            "github.com",
            "subprocess",
            "adb -s",
        )
        for relative in (
            "operations/package.py",
            "operations/runtime.py",
            "operations/filesystem.py",
        ):
            source = (SCRIPT_DIR / relative).read_text(encoding="utf-8").lower()
            with self.subTest(relative=relative):
                for token in forbidden:
                    self.assertNotIn(token.lower(), source)


if __name__ == "__main__":
    unittest.main()
