from __future__ import annotations

from operations import filesystem, install_apk, package, runtime


CANONICAL_BINDING_TYPES = {
    "android.apk-install.v1": install_apk.ApkInstallBinding,
    "android.package-remove.v1": package.PackageRemoveBinding,
    "android.runtime-stop.v1": runtime.RuntimeStopBinding,
    "android.runtime-remove.v1": runtime.RuntimeRemoveBinding,
    "android.runtime-materialize.v1": runtime.RuntimeMaterializeBinding,
    "android.runtime-start.v1": runtime.RuntimeStartBinding,
    "android.runtime-binary-replace.v1": runtime.RuntimeBinaryReplaceBinding,
    "android.filesystem-scratch-roundtrip.v1": filesystem.FilesystemScratchRoundtripBinding,
    "android.filesystem-scratch-atomic-replace.v1": filesystem.FilesystemScratchAtomicReplaceBinding,
    "android.filesystem-managed-root-write.v1": filesystem.FilesystemManagedRootWriteBinding,
    "android.filesystem-managed-atomic-replace.v1": filesystem.FilesystemManagedAtomicReplaceBinding,
    "android.filesystem-quarantine-cleanup-atomic.v1": filesystem.FilesystemQuarantineCleanupBinding,
}

CANONICAL_EXECUTOR_TYPES = {
    "android.apk-install.v1": install_apk.CanonicalApkInstallExecutor,
    "android.package-remove.v1": package.PackageRemoveExecutor,
    "android.runtime-stop.v1": runtime.RuntimeStopExecutor,
    "android.runtime-remove.v1": runtime.RuntimeRemoveExecutor,
    "android.runtime-materialize.v1": runtime.RuntimeMaterializeExecutor,
    "android.runtime-start.v1": runtime.RuntimeStartExecutor,
    "android.runtime-binary-replace.v1": runtime.RuntimeBinaryReplaceExecutor,
    "android.filesystem-scratch-roundtrip.v1": filesystem.FilesystemScratchRoundtripExecutor,
    "android.filesystem-scratch-atomic-replace.v1": filesystem.FilesystemScratchAtomicReplaceExecutor,
    "android.filesystem-managed-root-write.v1": filesystem.FilesystemManagedRootWriteExecutor,
    "android.filesystem-managed-atomic-replace.v1": filesystem.FilesystemManagedAtomicReplaceExecutor,
    "android.filesystem-quarantine-cleanup-atomic.v1": filesystem.FilesystemQuarantineCleanupExecutor,
}
