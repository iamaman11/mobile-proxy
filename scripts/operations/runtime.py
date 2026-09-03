from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import atomic_physical_contracts as atomic
import transaction_runner as transaction

from operations._atomic import CanonicalAtomicBinding, kernel_steps


@dataclass(frozen=True)
class RuntimeStopRequest:
    semantic_request: transaction.SemanticRequestIdentity
    runtime_ref: str

    @property
    def mutation_subject_ref(self) -> str:
        return self.runtime_ref


@dataclass(frozen=True)
class RuntimeRemoveRequest:
    semantic_request: transaction.SemanticRequestIdentity
    runtime_root_ref: str

    @property
    def mutation_subject_ref(self) -> str:
        return self.runtime_root_ref


@dataclass(frozen=True)
class RuntimeMaterializeRequest:
    semantic_request: transaction.SemanticRequestIdentity
    release_ref: str
    artifact_ref: str

    @property
    def mutation_subject_ref(self) -> str:
        return self.release_ref


@dataclass(frozen=True)
class RuntimeStartRequest:
    semantic_request: transaction.SemanticRequestIdentity
    release_ref: str

    @property
    def mutation_subject_ref(self) -> str:
        return self.release_ref


@dataclass(frozen=True)
class RuntimeBinaryReplaceRequest:
    semantic_request: transaction.SemanticRequestIdentity
    runtime_ref: str
    artifact_ref: str

    @property
    def mutation_subject_ref(self) -> str:
        return self.runtime_ref


class RuntimeCommandEdge(Protocol):
    def stop_once(self, request: RuntimeStopRequest) -> transaction.DispatchReceipt: ...

    def remove_once(self, request: RuntimeRemoveRequest) -> transaction.DispatchReceipt: ...

    def start_once(self, request: RuntimeStartRequest) -> transaction.DispatchReceipt: ...


class RuntimeArtifactEdge(Protocol):
    def materialize_once(
        self,
        request: RuntimeMaterializeRequest,
    ) -> transaction.DispatchReceipt: ...

    def replace_binaries_once(
        self,
        request: RuntimeBinaryReplaceRequest,
    ) -> transaction.DispatchReceipt: ...


class RuntimeObserverEdge(Protocol):
    def observe_stopped(
        self,
        request: RuntimeStopRequest,
    ) -> transaction.PostconditionProof: ...

    def observe_absent(
        self,
        request: RuntimeRemoveRequest,
    ) -> transaction.PostconditionProof: ...

    def observe_materialized(
        self,
        request: RuntimeMaterializeRequest,
    ) -> transaction.PostconditionProof: ...

    def observe_local_health(
        self,
        request: RuntimeStartRequest,
    ) -> transaction.PostconditionProof: ...

    def observe_binary_digests(
        self,
        request: RuntimeBinaryReplaceRequest,
    ) -> transaction.PostconditionProof: ...


@dataclass(frozen=True)
class RuntimeStopExecutor:
    commands: RuntimeCommandEdge
    observer: RuntimeObserverEdge

    def dispatch_once(self, request: RuntimeStopRequest) -> transaction.DispatchReceipt:
        return self.commands.stop_once(request)

    def verify_postcondition(
        self,
        request: RuntimeStopRequest,
    ) -> transaction.PostconditionProof:
        return self.observer.observe_stopped(request)


@dataclass(frozen=True)
class RuntimeRemoveExecutor:
    commands: RuntimeCommandEdge
    observer: RuntimeObserverEdge

    def dispatch_once(self, request: RuntimeRemoveRequest) -> transaction.DispatchReceipt:
        return self.commands.remove_once(request)

    def verify_postcondition(
        self,
        request: RuntimeRemoveRequest,
    ) -> transaction.PostconditionProof:
        return self.observer.observe_absent(request)


@dataclass(frozen=True)
class RuntimeMaterializeExecutor:
    artifacts: RuntimeArtifactEdge
    observer: RuntimeObserverEdge

    def dispatch_once(
        self,
        request: RuntimeMaterializeRequest,
    ) -> transaction.DispatchReceipt:
        return self.artifacts.materialize_once(request)

    def verify_postcondition(
        self,
        request: RuntimeMaterializeRequest,
    ) -> transaction.PostconditionProof:
        return self.observer.observe_materialized(request)


@dataclass(frozen=True)
class RuntimeStartExecutor:
    commands: RuntimeCommandEdge
    observer: RuntimeObserverEdge

    def dispatch_once(self, request: RuntimeStartRequest) -> transaction.DispatchReceipt:
        return self.commands.start_once(request)

    def verify_postcondition(
        self,
        request: RuntimeStartRequest,
    ) -> transaction.PostconditionProof:
        return self.observer.observe_local_health(request)


@dataclass(frozen=True)
class RuntimeBinaryReplaceExecutor:
    artifacts: RuntimeArtifactEdge
    observer: RuntimeObserverEdge

    def dispatch_once(
        self,
        request: RuntimeBinaryReplaceRequest,
    ) -> transaction.DispatchReceipt:
        return self.artifacts.replace_binaries_once(request)

    def verify_postcondition(
        self,
        request: RuntimeBinaryReplaceRequest,
    ) -> transaction.PostconditionProof:
        return self.observer.observe_binary_digests(request)


class RuntimeStopBinding(CanonicalAtomicBinding[RuntimeStopRequest]):
    spec = atomic.ANDROID_RUNTIME_STOP
    contract = spec.contract
    kernel_steps = kernel_steps(spec)
    request_type = RuntimeStopRequest


class RuntimeRemoveBinding(CanonicalAtomicBinding[RuntimeRemoveRequest]):
    spec = atomic.ANDROID_RUNTIME_REMOVE
    contract = spec.contract
    kernel_steps = kernel_steps(spec)
    request_type = RuntimeRemoveRequest


class RuntimeMaterializeBinding(CanonicalAtomicBinding[RuntimeMaterializeRequest]):
    spec = atomic.ANDROID_RUNTIME_MATERIALIZE
    contract = spec.contract
    kernel_steps = kernel_steps(spec)
    request_type = RuntimeMaterializeRequest


class RuntimeStartBinding(CanonicalAtomicBinding[RuntimeStartRequest]):
    spec = atomic.ANDROID_RUNTIME_START
    contract = spec.contract
    kernel_steps = kernel_steps(spec)
    request_type = RuntimeStartRequest


class RuntimeBinaryReplaceBinding(CanonicalAtomicBinding[RuntimeBinaryReplaceRequest]):
    spec = atomic.ANDROID_RUNTIME_BINARY_REPLACE
    contract = spec.contract
    kernel_steps = kernel_steps(spec)
    request_type = RuntimeBinaryReplaceRequest
