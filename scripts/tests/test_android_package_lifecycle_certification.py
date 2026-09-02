from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from unittest import mock


SCRIPT = Path(__file__).resolve().parents[1] / "run_android_package_lifecycle_certification.py"
SPEC = importlib.util.spec_from_file_location("android_package_lifecycle_certification", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class AndroidPackageLifecycleCertificationTests(unittest.TestCase):
    def _inventory(self):
        return {
            "read_only_capabilities_proven": True,
            "capabilities": {
                "adb_shell": "SUPPORTED",
                "package_query": "SUPPORTED",
                "root_shell": "SUPPORTED",
            },
        }

    def _certify(self):
        return MODULE.certify(
            canonical_sha="a" * 40,
            apk=Path("candidate.apk"),
            release_evidence=Path("release-evidence.json"),
            digest_tool=Path("android-artifact-digest"),
            expected_version_name="0.1.4",
            expected_version_code=1004,
        )

    @mock.patch.object(MODULE, "_recover_to_candidate_or_absent")
    @mock.patch.object(MODULE, "_install_and_verify_candidate")
    @mock.patch.object(MODULE, "_uninstall_and_verify_absent")
    @mock.patch.object(MODULE._CAPABILITIES, "inventory")
    @mock.patch.object(MODULE._CLEAN, "package_present")
    @mock.patch.object(MODULE._CLEAN, "prove_registered_device")
    @mock.patch.object(MODULE._CLEAN, "verify_release_evidence", return_value="b3:" + "1" * 64)
    @mock.patch.object(MODULE._CLEAN, "load_json", return_value={})
    @mock.patch.object(MODULE._CLEAN, "require_expected_serial", return_value="registered-device")
    def test_full_install_uninstall_reinstall_cycle_is_accepted(
        self,
        _serial,
        _load,
        _evidence,
        prove_device,
        package_present,
        inventory,
        uninstall,
        install,
        recover,
    ) -> None:
        inventory.return_value = self._inventory()
        package_present.side_effect = [True, False, False]

        report = self._certify()

        self.assertTrue(report["accepted"])
        self.assertEqual(report["state"], "ACCEPTED")
        self.assertTrue(report["initial_absence_verified"])
        self.assertTrue(report["first_install_verified"])
        self.assertTrue(report["candidate_uninstall_verified"])
        self.assertTrue(report["reinstall_verified"])
        self.assertTrue(report["package_install_uninstall_proven"])
        self.assertEqual(prove_device.call_count, 5)
        self.assertEqual(uninstall.call_count, 2)
        self.assertEqual(install.call_count, 2)
        recover.assert_not_called()

    @mock.patch.object(MODULE, "_recover_to_candidate_or_absent", return_value=(True, "candidate_installed"))
    @mock.patch.object(
        MODULE,
        "_install_and_verify_candidate",
        side_effect=MODULE._CLEAN.CleanInstallFailure("simulated install failure"),
    )
    @mock.patch.object(MODULE, "_uninstall_and_verify_absent")
    @mock.patch.object(MODULE._CAPABILITIES, "inventory")
    @mock.patch.object(MODULE._CLEAN, "package_present", side_effect=[True, False])
    @mock.patch.object(MODULE._CLEAN, "prove_registered_device")
    @mock.patch.object(MODULE._CLEAN, "verify_release_evidence", return_value="b3:" + "2" * 64)
    @mock.patch.object(MODULE._CLEAN, "load_json", return_value={})
    @mock.patch.object(MODULE._CLEAN, "require_expected_serial", return_value="registered-device")
    def test_failure_after_destructive_boundary_recovers_but_never_accepts(
        self,
        _serial,
        _load,
        _evidence,
        _prove_device,
        _package_present,
        inventory,
        _uninstall,
        _install,
        recover,
    ) -> None:
        inventory.return_value = self._inventory()

        report = self._certify()

        self.assertFalse(report["accepted"])
        self.assertEqual(report["state"], "RECOVERED")
        self.assertEqual(report["failure_stage"], "install_candidate_first")
        self.assertEqual(report["recovery_baseline"], "candidate_installed")
        self.assertTrue(report["recovery_verified"])
        self.assertTrue(report["phone_mutation_performed"])
        recover.assert_called_once()

    @mock.patch.object(MODULE, "_recover_to_candidate_or_absent", return_value=(False, "unproven"))
    @mock.patch.object(
        MODULE,
        "_install_and_verify_candidate",
        side_effect=MODULE._CLEAN.CleanInstallFailure("simulated install failure"),
    )
    @mock.patch.object(MODULE, "_uninstall_and_verify_absent")
    @mock.patch.object(MODULE._CAPABILITIES, "inventory")
    @mock.patch.object(MODULE._CLEAN, "package_present", side_effect=[True, False])
    @mock.patch.object(MODULE._CLEAN, "prove_registered_device")
    @mock.patch.object(MODULE._CLEAN, "verify_release_evidence", return_value="b3:" + "3" * 64)
    @mock.patch.object(MODULE._CLEAN, "load_json", return_value={})
    @mock.patch.object(MODULE._CLEAN, "require_expected_serial", return_value="registered-device")
    def test_unprovable_recovery_quarantines_package_state(
        self,
        _serial,
        _load,
        _evidence,
        _prove_device,
        _package_present,
        inventory,
        _uninstall,
        _install,
        _recover,
    ) -> None:
        inventory.return_value = self._inventory()

        report = self._certify()

        self.assertFalse(report["accepted"])
        self.assertEqual(report["state"], "QUARANTINED")
        self.assertFalse(report["recovery_verified"])
        self.assertEqual(report["recovery_baseline"], "unproven")

    @mock.patch.object(MODULE, "_recover_to_candidate_or_absent")
    @mock.patch.object(MODULE._CLEAN, "verify_release_evidence")
    @mock.patch.object(MODULE._CLEAN, "load_json", return_value={})
    @mock.patch.object(MODULE._CLEAN, "require_expected_serial", return_value="registered-device")
    def test_artifact_failure_refuses_before_phone_mutation(
        self,
        _serial,
        _load,
        verify_evidence,
        recover,
    ) -> None:
        verify_evidence.side_effect = MODULE._CLEAN.CleanInstallFailure("candidate evidence differs")

        report = self._certify()

        self.assertFalse(report["accepted"])
        self.assertEqual(report["state"], "REFUSED")
        self.assertFalse(report["phone_mutation_performed"])
        self.assertEqual(report["recovery_baseline"], "unchanged")
        recover.assert_not_called()

    @mock.patch.object(MODULE._CLEAN, "package_present", return_value=True)
    @mock.patch.object(MODULE._CLEAN, "verify_installed_apk_digest")
    @mock.patch.object(MODULE._CLEAN, "package_version", return_value=(1004, "0.1.4"))
    def test_candidate_verification_requires_version_and_exact_artifact(
        self, _version, digest, _present
    ) -> None:
        MODULE._verify_candidate_installed(
            "registered-device",
            expected_digest="b3:" + "4" * 64,
            digest_tool=Path("android-artifact-digest"),
            expected_version_name="0.1.4",
            expected_version_code=1004,
        )
        digest.assert_called_once_with(
            "registered-device",
            "b3:" + "4" * 64,
            Path("android-artifact-digest"),
        )


if __name__ == "__main__":
    unittest.main()
