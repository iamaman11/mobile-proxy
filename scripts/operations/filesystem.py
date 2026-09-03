from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import atomic_physical_contracts as atomic
import transaction_runner as transaction

from operations._atomic import CanonicalAtomicBinding, kernel_steps


@dataclass(frozen=True)
class FilesystemScratchRoundtripRequest:
    semantic_request: transaction.SemanticRequestIdentity
    scratch_ref: str
    payload_ref: str

    @property
    def mutation_subject_ref(self) -> str:
        return self.scratch_ref


@dataclass(frozen=True)
class FilesystemScratchAtomicReplaceRequest:
    semantic_request: transaction.SemanticRequestIdentity
    scratch_ref: str
    replacement_ref: str

    @property
    def mutation_subject_ref(self) -> str:
        return self.scratch_ref


@dataclass(frozen=True)
class FilesystemManagedRootWriteRequest:
    semantic_request: transaction.SemanticRequestIdentity
    managed_ref: str
    payload_ref: str

    @property
    def mutation_subject_ref(self) -> str:
        return self.managed_ref


@dataclass(frozen=True)
class FilesystemManagedAtomicReplaceRequest:
    semantic_request: transaction.SemanticRequestIdentity
    managed_ref: str
    replacement_ref: str

    @property
    def mutation_subject_ref(self) -> str:
        return self.managed_ref


@dataclass(frozen=True)
class FilesystemQuarantineCleanupRequest:
    semantic_request: transaction.SemanticRequestIdentity
    quarantine_ref: str

    @property
    def mutation_subject_ref(self) -> str:
        return self.quarantine_ref


class FilesystemEdge(Protocol):
    def scratch_roundtrip_once(
        self,
        request: FilesystemScratchRoundtripRequest,
    ) -> transaction.DispatchReceipt: ...

    def scratch_atomic_replace_once(
        self,
        request: FilesystemScratchAtomicReplaceRequest,
    ) -> transaction.DispatchReceipt: ...

    def managed_root_write_once(
        self,
        request: FilesystemManagedRootWriteRequest,
    ) -> transaction.DispatchReceipt: ...

    def managed_atomic_replace_once(
        self,
        request: FilesystemManagedAtomicReplaceRequest,
    ) -> transaction.DispatchReceipt: ...

    def quarantine_cleanup_once(
        self,
        request: FilesystemQuarantineCleanupRequest,
    ) -> transaction.DispatchReceipt: ...


class FilesystemObserverEdge(Protocol):
    def observe_scratch_roundtrip(
        self,
        request: FilesystemScratchRoundtripRequest,
    ) -> transaction.PostconditionProof: ...

    def observe_scratch_atomic_replace(
        self,
        request: FilesystemScratchAtomicReplaceRequest,
    ) -> transaction.PostconditionProof: ...

    def observe_managed_root_write(
        self,
        request: FilesystemManagedRootWriteRequest,
    ) -> transaction.PostconditionProof: ...

    def observe_managed_atomic_replace(
        self,
        request: FilesystemManagedAtomicReplaceRequest,
    ) -> transaction.PostconditionProof: ...

    def observe_quarantine_absent(
        self,
        request: FilesystemQuarantineCleanupRequest,
    ) -> transaction.PostconditionProof: ...


@dataclass(frozen=True)
class FilesystemScratchRoundtripExecutor:
    filesystem: FilesystemEdge
    observer: FilesystemObserverEdge

    def dispatch_once(
        self,
        request: FilesystemScratchRoundtripRequest,
    ) -> transaction.DispatchReceipt:
        return self.filesystem.scratch_roundtrip_once(request)

    def verify_postcondition(
        self,
        request: FilesystemScratchRoundtripRequest,
    ) -> transaction.PostconditionProof:
        return self.observer.observe_scratch_roundtrip(request)

    def observe_recovery(
        self,
        request: FilesystemScratchRoundtripRequest,
    ) -> transaction.RecoveryObservation:
        proof = self.observer.observe_scratch_roundtrip(request)
        return transaction.RecoveryObservation(
            transaction.RECOVERY_PROVEN_ABSENT
            if proof.passed
            else transaction.RECOVERY_RESIDUAL_PRESENT,
            proof.source_ref,
        )


@dataclass(frozen=True)
class FilesystemScratchAtomicReplaceExecutor:
    filesystem: FilesystemEdge
    observer: FilesystemObserverEdge

    def dispatch_once(
        self,
        request: FilesystemScratchAtomicReplaceRequest,
    ) -> transaction.DispatchReceipt:
        return self.filesystem.scratch_atomic_replace_once(request)

    def verify_postcondition(
        self,
        request: FilesystemScratchAtomicReplaceRequest,
    ) -> transaction.PostconditionProof:
        return self.observer.observe_scratch_atomic_replace(request)


@dataclass(frozen=True)
class FilesystemManagedRootWriteExecutor:
    filesystem: FilesystemEdge
    observer: FilesystemObserverEdge

    def dispatch_once(
        self,
        request: FilesystemManagedRootWriteRequest,
    ) -> transaction.DispatchReceipt:
        return self.filesystem.managed_root_write_once(request)

    def verify_postcondition(
        self,
        request: FilesystemManagedRootWriteRequest,
    ) -> transaction.PostconditionProof:
        return self.observer.observe_managed_root_write(request)


@dataclass(frozen=True)
class FilesystemManagedAtomicReplaceExecutor:
    filesystem: FilesystemEdge
    observer: FilesystemObserverEdge

    def dispatch_once(
        self,
        request: FilesystemManagedAtomicReplaceRequest,
    ) -> transaction.DispatchReceipt:
        return self.filesystem.managed_atomic_replace_once(request)

    def verify_postcondition(
        self,
        request: FilesystemManagedAtomicReplaceRequest,
    ) -> transaction.PostconditionProof:
        return self.observer.observe_managed_atomic_replace(request)


@dataclass(frozen=True)
class FilesystemQuarantineCleanupExecutor:
    filesystem: FilesystemEdge
    observer: FilesystemObserverEdge

    def dispatch_once(
        self,
        request: FilesystemQuarantineCleanupRequest,
    ) -> transaction.DispatchReceipt:
        return self.filesystem.quarantine_cleanup_once(request)

    def verify_postcondition(
        self,
        request: FilesystemQuarantineCleanupRequest,
    ) -> transaction.PostconditionProof:
        return self.observer.observe_quarantine_absent(request)


class FilesystemScratchRoundtripBinding(
    CanonicalAtomicBinding[FilesystemScratchRoundtripRequest]
):
    spec = atomic.ANDROID_FILESYSTEM_SCRATCH_ROUNDTRIP
    contract = spec.contract
    kernel_steps = kernel_steps(spec)
    request_type = FilesystemScratchRoundtripRequest


class FilesystemScratchAtomicReplaceBinding(
    CanonicalAtomicBinding[FilesystemScratchAtomicReplaceRequest]
):
    spec = atomic.ANDROID_FILESYSTEM_SCRATCH_ATOMIC_REPLACE
    contract = spec.contract
    kernel_steps = kernel_steps(spec)
    request_type = FilesystemScratchAtomicReplaceRequest


class FilesystemManagedRootWriteBinding(
    CanonicalAtomicBinding[FilesystemManagedRootWriteRequest]
):
    spec = atomic.ANDROID_FILESYSTEM_MANAGED_ROOT_WRITE
    contract = spec.contract
    kernel_steps = kernel_steps(spec)
    request_type = FilesystemManagedRootWriteRequest


class FilesystemManagedAtomicReplaceBinding(
    CanonicalAtomicBinding[FilesystemManagedAtomicReplaceRequest]
):
    spec = atomic.ANDROID_FILESYSTEM_MANAGED_ATOMIC_REPLACE
    contract = spec.contract
    kernel_steps = kernel_steps(spec)
    request_type = FilesystemManagedAtomicReplaceRequest


class FilesystemQuarantineCleanupBinding(
    CanonicalAtomicBinding[FilesystemQuarantineCleanupRequest]
):
    spec = atomic.ANDROID_FILESYSTEM_QUARANTINE_CLEANUP
    contract = spec.contract
    kernel_steps = kernel_steps(spec)
    request_type = FilesystemQuarantineCleanupRequest
