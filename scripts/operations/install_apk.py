from __future__ import annotations

from dataclasses import dataclass
import hmac
import os
from pathlib import Path
import re
import subprocess
import tempfile
from typing import ClassVar, Protocol, Sequence, cast

import operation_state_machine as operation
import transaction_runner as transaction


_PACKAGE = "com.example.mobileproxy"
_TYPED_ARTIFACT_REF = re.compile(r"^b3:[0-9a-f]{64}$")


class ApkExecutionFailure(RuntimeError):
    """Fail-closed error at the bounded APK physical edge."""


@dataclass(frozen=True)
class ApkInstallRequest:
    transaction_id: str
    artifact_ref: str


class ApkInstallExecutor(Protocol):
    """APK-specific physical edge supplied by the execution plane."""

    def dispatch_once(
        self,
        request: ApkInstallRequest,
    ) -> transaction.DispatchReceipt: ...

    def verify_postcondition(
        self,
        request: ApkInstallRequest,
    ) -> transaction.PostconditionProof: ...


@dataclass(frozen=True)
class CommandResult:
    stdout: str
    stderr: str = ""


class CommandEdge(Protocol):
    """One command invocation; retry policy is deliberately outside this edge."""

    def run(
        self,
        arguments: Sequence[str],
        *,
        timeout_seconds: int,
    ) -> CommandResult: ...


@dataclass(frozen=True)
class SubprocessCommandEdge:
    """Production command edge with one subprocess invocation and no retry loop."""

    def run(
        self,
        arguments: Sequence[str],
        *,
        timeout_seconds: int,
    ) -> CommandResult:
        try:
            completed = subprocess.run(
                list(arguments),
                check=True,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
            )
        except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
            raise ApkExecutionFailure("APK command edge failed") from error
        return CommandResult(completed.stdout, completed.stderr)


class ArtifactDigestEdge(Protocol):
    """Typed APK content identity edge."""

    def digest(self, path: Path) -> str: ...


@dataclass(frozen=True)
class ExternalTypedArtifactDigest:
    """Invoke the canonical typed Android artifact digest helper exactly once."""

    tool: Path
    commands: CommandEdge
    timeout_seconds: int = 120

    def digest(self, path: Path) -> str:
        tool = self.tool.resolve()
        if not tool.is_file() or not os.access(tool, os.X_OK):
            raise ApkExecutionFailure("typed Android artifact digest helper is unavailable")
        result = self.commands.run(
            (str(tool), str(path)),
            timeout_seconds=self.timeout_seconds,
        )
        value = result.stdout.strip()
        if _TYPED_ARTIFACT_REF.fullmatch(value) is None:
            raise ApkExecutionFailure("typed Android artifact digest is invalid")
        return value


def _request(value: object) -> ApkInstallRequest:
    if not isinstance(value, ApkInstallRequest):
        raise TypeError("android.apk-install.v1 requires ApkInstallRequest")
    return cast(ApkInstallRequest, value)


def _typed_artifact_ref(value: str) -> str:
    value = value.strip()
    if _TYPED_ARTIFACT_REF.fullmatch(value) is None:
        raise ApkExecutionFailure("APK artifact identity is not a typed Android digest")
    return value


def _serial(value: str) -> str:
    value = value.strip()
    if (
        not value
        or len(value) > 128
        or any(character.isspace() for character in value)
        or not all(32 < ord(character) < 127 for character in value)
    ):
        raise ApkExecutionFailure("registered production device binding is invalid")
    return value


def _installed_apk_path(output: str) -> str:
    paths = []
    for line in output.splitlines():
        value = line.strip()
        if not value:
            continue
        prefix, separator, path = value.partition(":")
        if prefix != "package" or separator != ":" or not path.startswith("/"):
            raise ApkExecutionFailure("installed APK path observation is invalid")
        paths.append(path)
    if len(paths) != 1:
        raise ApkExecutionFailure("installed APK path is unavailable or ambiguous")
    return paths[0]


def _install_reported_success(output: str) -> bool:
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    return bool(lines) and lines[-1] == "Success"


@dataclass(frozen=True)
class CanonicalApkInstallExecutor:
    """Bounded same-lineage APK install/update physical edge.

    The transaction kernel owns authority, locking, mutation-intent persistence,
    dispatch state and retries. This executor owns only exact APK content binding,
    one package install/update command, and exact installed-content observation.
    """

    serial: str
    apk_path: Path
    admitted_artifact_ref: str
    commands: CommandEdge
    digests: ArtifactDigestEdge

    def _request_identity(self, request: ApkInstallRequest) -> str:
        admitted = _typed_artifact_ref(self.admitted_artifact_ref)
        requested = _typed_artifact_ref(request.artifact_ref)
        if requested != admitted:
            raise ApkExecutionFailure("APK request differs from pre-admitted artifact identity")
        return admitted

    def _prove_local_artifact(self, expected_ref: str) -> None:
        path = self.apk_path.resolve()
        if not path.is_file() or path.stat().st_size <= 0:
            raise ApkExecutionFailure("pre-admitted APK artifact is unavailable")
        observed = _typed_artifact_ref(self.digests.digest(path))
        if not hmac.compare_digest(observed, expected_ref):
            raise ApkExecutionFailure("local APK content differs from pre-admitted identity")

    def dispatch_once(
        self,
        request: ApkInstallRequest,
    ) -> transaction.DispatchReceipt:
        request = _request(request)
        expected_ref = self._request_identity(request)
        self._prove_local_artifact(expected_ref)
        serial = _serial(self.serial)
        result = self.commands.run(
            ("adb", "-s", serial, "install", "-r", str(self.apk_path.resolve())),
            timeout_seconds=180,
        )
        if not _install_reported_success(result.stdout):
            raise ApkExecutionFailure("APK install/update did not report success")
        return transaction.DispatchReceipt(
            f"apk-install:{request.transaction_id}:{expected_ref}"
        )

    def verify_postcondition(
        self,
        request: ApkInstallRequest,
    ) -> transaction.PostconditionProof:
        request = _request(request)
        expected_ref = self._request_identity(request)
        serial = _serial(self.serial)
        try:
            path_result = self.commands.run(
                ("adb", "-s", serial, "shell", "pm", "path", _PACKAGE),
                timeout_seconds=30,
            )
            remote_path = _installed_apk_path(path_result.stdout)
            with tempfile.TemporaryDirectory(prefix="mobile-proxy-installed-apk-") as raw:
                local_path = Path(raw) / "installed-base.apk"
                self.commands.run(
                    ("adb", "-s", serial, "pull", remote_path, str(local_path)),
                    timeout_seconds=120,
                )
                if not local_path.is_file() or local_path.stat().st_size <= 0:
                    raise ApkExecutionFailure("installed APK capture is unavailable")
                observed_ref = _typed_artifact_ref(self.digests.digest(local_path))
        except ApkExecutionFailure:
            return transaction.PostconditionProof(False, "installed-apk:unobserved")

        return transaction.PostconditionProof(
            hmac.compare_digest(observed_ref, expected_ref),
            f"installed-apk:{observed_ref}",
        )


@dataclass(frozen=True)
class ApkInstallBinding:
    """The APK operation binding; transaction semantics remain in the kernel."""

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