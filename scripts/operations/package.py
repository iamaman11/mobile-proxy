from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import atomic_physical_contracts as atomic
import transaction_runner as transaction

from operations._atomic import CanonicalAtomicBinding, kernel_steps


@dataclass(frozen=True)
class PackageRemoveRequest:
    semantic_request: transaction.SemanticRequestIdentity
    package_name: str

    @property
    def mutation_subject_ref(self) -> str:
        return f"package/{self.package_name}"


class PackageCommandEdge(Protocol):
    def remove_package_once(
        self,
        request: PackageRemoveRequest,
    ) -> transaction.DispatchReceipt: ...


class PackageAbsentObserverEdge(Protocol):
    def observe_package_absent(
        self,
        request: PackageRemoveRequest,
    ) -> transaction.PostconditionProof: ...


@dataclass(frozen=True)
class PackageRemoveExecutor:
    commands: PackageCommandEdge
    observer: PackageAbsentObserverEdge

    def dispatch_once(
        self,
        request: PackageRemoveRequest,
    ) -> transaction.DispatchReceipt:
        return self.commands.remove_package_once(request)

    def verify_postcondition(
        self,
        request: PackageRemoveRequest,
    ) -> transaction.PostconditionProof:
        return self.observer.observe_package_absent(request)


class PackageRemoveBinding(CanonicalAtomicBinding[PackageRemoveRequest]):
    spec = atomic.ANDROID_PACKAGE_REMOVE
    contract = spec.contract
    kernel_steps = kernel_steps(spec)
    request_type = PackageRemoveRequest
