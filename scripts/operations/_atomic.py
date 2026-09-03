from __future__ import annotations

from typing import ClassVar, Generic, Protocol, TypeVar, cast

import atomic_physical_contracts as atomic
import operation_state_machine as operation
import transaction_runner as transaction


RequestT = TypeVar("RequestT")


class AtomicRequest(Protocol):
    semantic_request: transaction.SemanticRequestIdentity

    @property
    def mutation_subject_ref(self) -> str: ...


class AtomicExecutor(Protocol[RequestT]):
    def dispatch_once(self, request: RequestT) -> transaction.DispatchReceipt: ...

    def verify_postcondition(
        self,
        request: RequestT,
    ) -> transaction.PostconditionProof: ...


class AtomicRecoveryObserver(Protocol[RequestT]):
    def observe_recovery(
        self,
        request: RequestT,
    ) -> transaction.RecoveryObservation: ...


class CanonicalAtomicBinding(Generic[RequestT]):
    """Typed contract/request binding; lifecycle semantics remain in the kernel."""

    spec: ClassVar[atomic.AtomicOperationSpec]
    contract: ClassVar[operation.OperationContract]
    kernel_steps: ClassVar[transaction.KernelStepRoles]
    request_type: ClassVar[type]

    def __init__(
        self,
        executor: AtomicExecutor[RequestT],
        recovery_observer: AtomicRecoveryObserver[RequestT] | None = None,
    ) -> None:
        self.executor = executor
        self.recovery_observer = recovery_observer

    def _request(self, value: object) -> RequestT:
        if not isinstance(value, self.request_type):
            raise TypeError(
                f"{self.contract.operation_id} requires {self.request_type.__name__}"
            )
        return cast(RequestT, value)

    def semantic_request_identity(
        self,
        request: object,
    ) -> transaction.SemanticRequestIdentity:
        return cast(AtomicRequest, self._request(request)).semantic_request

    def transaction_id(self, request: object) -> str:
        typed = cast(AtomicRequest, self._request(request))
        return transaction.derive_physical_transaction_id(
            typed.semantic_request,
            self.contract.operation_id,
        )

    def mutation_subject_ref(self, request: object) -> str:
        return cast(AtomicRequest, self._request(request)).mutation_subject_ref

    def dispatch_once(self, request: object) -> transaction.DispatchReceipt:
        return self.executor.dispatch_once(self._request(request))

    def verify_postcondition(self, request: object) -> transaction.PostconditionProof:
        return self.executor.verify_postcondition(self._request(request))

    def observe_recovery(self, request: object) -> transaction.RecoveryObservation:
        """Invoke only the explicitly injected read-only recovery observer."""

        if self.recovery_observer is None:
            raise transaction.TransactionRefusal(
                "operation binding lacks explicit typed recovery observer"
            )
        return self.recovery_observer.observe_recovery(self._request(request))


def kernel_steps(spec: atomic.AtomicOperationSpec) -> transaction.KernelStepRoles:
    return transaction.KernelStepRoles(
        authority_step_id=spec.authority_step_id,
        mutation_scope_step_id=spec.mutation_scope_step_id,
        preflight_step_id=spec.preflight_step_id,
        intent_step_id=spec.intent_step_id,
        dispatch_step_id=spec.dispatch_step_id,
        postcondition_step_id=spec.postcondition_step_id,
        acceptance_step_id=spec.acceptance_step_id,
    )
