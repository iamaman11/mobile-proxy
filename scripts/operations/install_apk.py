from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar, Protocol, cast

import operation_state_machine as operation
import transaction_runner as transaction


@dataclass(frozen=True)
class ApkInstallRequest:
    transaction_id: str
    artifact_ref: str


class ApkInstallExecutor(Protocol):
    """APK-specific physical edge supplied by a later execution-plane integration."""

    def dispatch_once(
        self,
        request: ApkInstallRequest,
    ) -> transaction.DispatchReceipt: ...

    def verify_postcondition(
        self,
        request: ApkInstallRequest,
    ) -> transaction.PostconditionProof: ...


def _request(value: object) -> ApkInstallRequest:
    if not isinstance(value, ApkInstallRequest):
        raise TypeError("android.apk-install.v1 requires ApkInstallRequest")
    return cast(ApkInstallRequest, value)


@dataclass(frozen=True)
class ApkInstallBinding:
    """The only Stage C.0d operation binding; contains no ADB/device command."""

    executor: ApkInstallExecutor

    contract: ClassVar[operation.OperationContract] = operation.ANDROID_APK_INSTALL
    dispatch_step_id: ClassVar[str] = "install_apk"
    postcondition_step_id: ClassVar[str] = "verify_installed_apk"
    acceptance_step_id: ClassVar[str] = "accept"

    def transaction_id(self, request: object) -> str:
        return _request(request).transaction_id

    def mutation_subject_ref(self, request: object) -> str:
        return _request(request).artifact_ref

    def dispatch_once(self, request: object) -> transaction.DispatchReceipt:
        return self.executor.dispatch_once(_request(request))

    def verify_postcondition(self, request: object) -> transaction.PostconditionProof:
        return self.executor.verify_postcondition(_request(request))
