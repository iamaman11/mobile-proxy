from __future__ import annotations

import importlib.util
import subprocess
import unittest
from pathlib import Path
from unittest import mock


MODULE_PATH = Path(__file__).resolve().parents[1] / "clean_install_android_production.py"
SPEC = importlib.util.spec_from_file_location("clean_install_android_production", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class AndroidCleanInstallTests(unittest.TestCase):
    def _run(self, *, old_package_present: bool):
        install_result = mock.Mock(stdout="Success\n")
        uninstall_result = mock.Mock(stdout="Success\n")
        present_values = [old_package_present]
        if old_package_present:
            present_values.append(False)
        present_values.append(True)

        def fake_adb(_serial: str, *args: str, **_kwargs):
            if args and args[0] == "uninstall":
                return uninstall_result
            if args and args[0] == "install":
                return install_result
            raise AssertionError(f"unexpected adb call: {args}")

        with (
            mock.patch.object(MODULE, "require_canonical_sha", return_value="a" * 40),
            mock.patch.object(MODULE, "require_expected_serial", return_value="registered-device"),
            mock.patch.object(MODULE, "load_json", return_value={}),
            mock.patch.object(MODULE, "verify_release_evidence", return_value="b3:" + "1" * 64),
            mock.patch.object(MODULE, "prove_registered_device") as preflight,
            mock.patch.object(MODULE, "package_present", side_effect=present_values),
            mock.patch.object(MODULE, "adb", side_effect=fake_adb) as adb_call,
            mock.patch.object(MODULE, "package_version", return_value=(1004, "0.1.4")),
            mock.patch.object(MODULE, "verify_installed_apk_digest") as digest_verify,
        ):
            report = MODULE.clean_install(
                canonical_sha="a" * 40,
                apk=Path("candidate.apk"),
                release_evidence=Path("evidence.json"),
                digest_tool=Path("digest-tool"),
                expected_version_name="0.1.4",
                expected_version_code=1004,
            )

        return report, preflight, adb_call, digest_verify

    def test_absent_legacy_package_is_valid_clean_start(self) -> None:
        report, preflight, adb_call, digest_verify = self._run(old_package_present=False)

        self.assertTrue(report["accepted"])
        self.assertFalse(report["old_package_required"])
        self.assertFalse(report["old_package_observed"])
        self.assertFalse(report["old_package_retained"])
        self.assertFalse(report["rollback_to_old_generation_available"])
        self.assertEqual(preflight.call_count, 2)
        self.assertFalse(any(call.args[1:] and call.args[1] == "uninstall" for call in adb_call.call_args_list))
        self.assertTrue(any(call.args[1:] and call.args[1] == "install" for call in adb_call.call_args_list))
        digest_verify.assert_called_once()

    def test_present_legacy_package_is_removed_without_retention_or_version_proof(self) -> None:
        report, preflight, adb_call, _ = self._run(old_package_present=True)

        self.assertTrue(report["accepted"])
        self.assertTrue(report["old_package_observed"])
        self.assertFalse(report["old_package_retained"])
        self.assertEqual(preflight.call_count, 3)
        operations = [call.args[1] for call in adb_call.call_args_list]
        self.assertEqual(operations, ["uninstall", "install"])

    def test_new_identity_is_the_only_version_acceptance(self) -> None:
        with (
            mock.patch.object(MODULE, "require_canonical_sha", return_value="a" * 40),
            mock.patch.object(MODULE, "require_expected_serial", return_value="registered-device"),
            mock.patch.object(MODULE, "load_json", return_value={}),
            mock.patch.object(MODULE, "verify_release_evidence", return_value="b3:" + "1" * 64),
            mock.patch.object(MODULE, "prove_registered_device"),
            mock.patch.object(MODULE, "package_present", side_effect=[False, True]),
            mock.patch.object(MODULE, "adb", return_value=mock.Mock(stdout="Success\n")),
            mock.patch.object(MODULE, "package_version", return_value=(999, "wrong")),
            mock.patch.object(MODULE, "verify_installed_apk_digest"),
        ):
            with self.assertRaisesRegex(MODULE.CleanInstallFailure, "version differs"):
                MODULE.clean_install(
                    canonical_sha="a" * 40,
                    apk=Path("candidate.apk"),
                    release_evidence=Path("evidence.json"),
                    digest_tool=Path("digest-tool"),
                    expected_version_name="0.1.4",
                    expected_version_code=1004,
                )

    def test_package_probe_transport_failure_is_not_absence(self) -> None:
        with mock.patch.object(MODULE.subprocess, "run", side_effect=subprocess.TimeoutExpired(["adb"], 30)):
            with self.assertRaisesRegex(MODULE.CleanInstallFailure, "presence probe failed"):
                MODULE.package_present("registered-device")

    def test_package_probe_nonzero_exit_is_not_absence(self) -> None:
        result = mock.Mock(returncode=1, stdout="", stderr="transport error")
        with mock.patch.object(MODULE.subprocess, "run", return_value=result):
            with self.assertRaisesRegex(MODULE.CleanInstallFailure, "presence probe failed"):
                MODULE.package_present("registered-device")

    def test_package_probe_rejects_ambiguous_multiple_paths(self) -> None:
        result = mock.Mock(
            returncode=0,
            stdout="package:/data/app/base.apk\npackage:/data/app/split.apk\n",
            stderr="",
        )
        with mock.patch.object(MODULE.subprocess, "run", return_value=result):
            with self.assertRaisesRegex(MODULE.CleanInstallFailure, "probe is ambiguous"):
                MODULE.package_present("registered-device")


if __name__ == "__main__":
    unittest.main()
