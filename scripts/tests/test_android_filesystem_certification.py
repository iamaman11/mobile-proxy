from __future__ import annotations

import importlib.util
import os
import sys
import unittest
from pathlib import Path
from unittest import mock


SCRIPT = Path(__file__).resolve().parents[1] / "run_android_filesystem_certification.py"
SPEC = importlib.util.spec_from_file_location("android_filesystem_certification", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class AndroidFilesystemCertificationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.environment = mock.patch.dict(
            os.environ,
            {"ANDROID_PRODUCTION_SERIAL": "registered-device"},
            clear=False,
        )
        self.environment.start()
        self.addCleanup(self.environment.stop)

        self.tooling_probe_patch = mock.patch.object(
            MODULE._TOOLING,
            "probe_scope",
            side_effect=self._default_probe_scope,
        )
        self.probe_scope = self.tooling_probe_patch.start()
        self.addCleanup(self.tooling_probe_patch.stop)

    def _inventory(self):
        return {
            "read_only_capabilities_proven": True,
            "capabilities": {
                "adb_shell": "SUPPORTED",
                "package_query": "SUPPORTED",
                "root_shell": "SUPPORTED",
                "managed_root_observe": "SUPPORTED",
                "process_observe": "SUPPORTED",
                "network_observe": "SUPPORTED",
                "free_space_observe": "SUPPORTED",
                "adb_push_pull_roundtrip": "UNKNOWN",
                "managed_root_write": "UNKNOWN",
                "managed_atomic_replace": "UNKNOWN",
                "package_install_uninstall": "UNKNOWN",
                "runtime_start_stop": "UNKNOWN",
            },
        }

    def _comparator_scope(
        self,
        selected: str = "cmp",
        state: str = MODULE.SUPPORTED,
        *,
        complete: bool = True,
    ) -> dict[str, object]:
        return {
            "probes": {},
            "selected_comparator": selected,
            "canonical_comparator_path_state": state,
            "probe_complete": complete,
        }

    def _default_probe_scope(self, _serial: str, *, root: bool):
        del root
        return self._comparator_scope()

    def test_transaction_paths_are_confined(self) -> None:
        paths = MODULE.transaction_paths("tx-123")
        self.assertEqual(paths["scratch"], "/data/local/tmp/mobile-proxy-adapter-test/tx-123")
        self.assertEqual(paths["managed"], "/data/adb/mobile-proxy-node/.adapter-test/tx-123")

        for invalid in ("", "../escape", "a/b", ".", "a b", "/absolute"):
            with self.subTest(invalid=invalid):
                with self.assertRaises(MODULE.CertificationFailure):
                    MODULE.transaction_paths(invalid)

    @mock.patch.object(MODULE, "cleanup_paths", return_value=True)
    @mock.patch.object(MODULE, "run_managed_certification")
    @mock.patch.object(MODULE, "run_scratch_certification")
    @mock.patch.object(MODULE, "verify_prestate")
    @mock.patch.object(MODULE._CAPABILITIES, "inventory")
    @mock.patch.object(MODULE._PREFLIGHT, "require_tools", return_value={"adb": True})
    @mock.patch.object(MODULE._PREFLIGHT, "prove_registered_device")
    def test_success_promotes_only_proven_filesystem_capabilities(
        self,
        prove_device,
        _tools,
        inventory,
        _prestate,
        scratch,
        managed,
        cleanup,
    ) -> None:
        inventory.return_value = self._inventory()

        report = MODULE.certify("a" * 40, "tx-success")

        self.assertTrue(report["accepted"])
        self.assertEqual(report["state"], "ACCEPTED")
        self.assertTrue(report["filesystem_mutation_capabilities_proven"])
        self.assertTrue(report["cleanup_attempted"])
        self.assertTrue(report["cleanup_verified"])
        self.assertIsNone(report["failure_substep"])
        self.assertIsNone(report["cleanup_failure_substep"])
        self.assertTrue(report["phone_mutation_performed"])
        self.assertFalse(report["raw_device_identifier_recorded"])
        self.assertEqual(prove_device.call_count, 2)
        scratch.assert_called_once()
        managed.assert_called_once()
        cleanup.assert_called_once()
        self.assertEqual(scratch.call_args.kwargs["comparator"], "cmp")
        self.assertEqual(managed.call_args.kwargs["comparator"], "cmp")
        self.assertEqual(
            report["comparator_contract"]["source"],
            "android.filesystem-tooling-compatibility.v1",
        )
        for name in (
            "adb_push_pull_roundtrip",
            "managed_root_write",
            "managed_atomic_replace",
        ):
            self.assertEqual(report["capabilities"][name], "SUPPORTED")
        self.assertEqual(report["capabilities"]["package_install_uninstall"], "UNKNOWN")
        self.assertEqual(report["capabilities"]["runtime_start_stop"], "UNKNOWN")

    @mock.patch.object(MODULE, "cleanup_paths", return_value=True)
    @mock.patch.object(MODULE, "run_managed_certification")
    @mock.patch.object(MODULE, "run_scratch_certification")
    @mock.patch.object(MODULE, "verify_prestate")
    @mock.patch.object(MODULE._CAPABILITIES, "inventory")
    @mock.patch.object(MODULE._PREFLIGHT, "require_tools", return_value={"adb": True})
    @mock.patch.object(MODULE._PREFLIGHT, "prove_registered_device")
    def test_mutation_consumes_independently_selected_comparators(
        self,
        _prove_device,
        _tools,
        inventory,
        _prestate,
        scratch,
        managed,
        _cleanup,
    ) -> None:
        inventory.return_value = self._inventory()

        def scope(_serial: str, *, root: bool):
            if root:
                return self._comparator_scope("cmp", MODULE.SUPPORTED)
            return self._comparator_scope("toybox_cmp", MODULE.SUPPORTED)

        self.probe_scope.side_effect = scope

        report = MODULE.certify("9" * 40, "tx-fallback")

        self.assertTrue(report["accepted"])
        self.assertEqual(scratch.call_args.kwargs["comparator"], "toybox_cmp")
        self.assertEqual(managed.call_args.kwargs["comparator"], "cmp")
        self.assertEqual(
            report["comparator_contract"]["scratch_selected_comparator"],
            "toybox_cmp",
        )
        self.assertEqual(
            report["comparator_contract"]["managed_selected_comparator"],
            "cmp",
        )

    @mock.patch.object(MODULE, "cleanup_paths")
    @mock.patch.object(MODULE, "run_managed_certification")
    @mock.patch.object(MODULE, "run_scratch_certification")
    @mock.patch.object(MODULE, "verify_prestate")
    @mock.patch.object(MODULE._CAPABILITIES, "inventory")
    @mock.patch.object(MODULE._PREFLIGHT, "require_tools", return_value={"adb": True})
    @mock.patch.object(MODULE._PREFLIGHT, "prove_registered_device")
    def test_unknown_comparator_refuses_before_mutation(
        self,
        prove_device,
        _tools,
        inventory,
        prestate,
        scratch,
        managed,
        cleanup,
    ) -> None:
        inventory.return_value = self._inventory()
        self.probe_scope.side_effect = [
            self._comparator_scope("UNKNOWN", MODULE.UNKNOWN, complete=False),
            self._comparator_scope("cmp", MODULE.SUPPORTED),
        ]

        report = MODULE.certify("7" * 40, "tx-unknown")

        self.assertFalse(report["accepted"])
        self.assertEqual(report["state"], "REFUSED")
        self.assertEqual(report["failure_stage"], "comparator_admission")
        self.assertFalse(report["phone_mutation_performed"])
        self.assertFalse(report["cleanup_attempted"])
        self.assertTrue(report["cleanup_verified"])
        self.assertEqual(prove_device.call_count, 1)
        prestate.assert_not_called()
        scratch.assert_not_called()
        managed.assert_not_called()
        cleanup.assert_not_called()
        self.assertEqual(
            report["comparator_contract"]["scratch_comparator_path_state"],
            MODULE.UNKNOWN,
        )

    @mock.patch.object(MODULE, "cleanup_paths")
    @mock.patch.object(MODULE, "run_managed_certification")
    @mock.patch.object(MODULE, "run_scratch_certification")
    @mock.patch.object(MODULE, "verify_prestate")
    @mock.patch.object(MODULE._CAPABILITIES, "inventory")
    @mock.patch.object(MODULE._PREFLIGHT, "require_tools", return_value={"adb": True})
    @mock.patch.object(MODULE._PREFLIGHT, "prove_registered_device")
    def test_unsupported_comparator_refuses_before_mutation(
        self,
        _prove_device,
        _tools,
        inventory,
        prestate,
        scratch,
        managed,
        cleanup,
    ) -> None:
        inventory.return_value = self._inventory()
        self.probe_scope.side_effect = [
            self._comparator_scope("NONE", MODULE.UNSUPPORTED),
            self._comparator_scope("cmp", MODULE.SUPPORTED),
        ]

        report = MODULE.certify("8" * 40, "tx-unsupported")

        self.assertFalse(report["accepted"])
        self.assertEqual(report["state"], "REFUSED")
        self.assertEqual(report["failure_stage"], "comparator_admission")
        self.assertFalse(report["phone_mutation_performed"])
        prestate.assert_not_called()
        scratch.assert_not_called()
        managed.assert_not_called()
        cleanup.assert_not_called()
        self.assertEqual(
            report["comparator_contract"]["scratch_comparator_path_state"],
            MODULE.UNSUPPORTED,
        )

    def test_verify_remote_exact_uses_selected_invocation_without_presence_branch(self) -> None:
        with mock.patch.object(MODULE, "shell", return_value="") as shell:
            MODULE._verify_remote_exact(
                "registered-device",
                "/tmp/actual",
                "/tmp/expected",
                root=False,
                comparator="toybox_cmp",
            )

        command = shell.call_args.args[1]
        self.assertIn("toybox cmp -s", command)
        self.assertNotIn("command -v", command)
        self.assertNotIn("if ", command)

    @mock.patch.object(MODULE, "cleanup_paths", return_value=True)
    @mock.patch.object(
        MODULE,
        "run_scratch_certification",
        side_effect=MODULE.CertificationFailure("simulated partial write failure"),
    )
    @mock.patch.object(MODULE, "verify_prestate")
    @mock.patch.object(MODULE._CAPABILITIES, "inventory")
    @mock.patch.object(MODULE._PREFLIGHT, "require_tools", return_value={"adb": True})
    @mock.patch.object(MODULE._PREFLIGHT, "prove_registered_device")
    def test_failed_first_mutation_recovers_but_does_not_accept(
        self, prove_device, _tools, inventory, _prestate, _scratch, cleanup
    ) -> None:
        inventory.return_value = self._inventory()

        report = MODULE.certify("b" * 40, "tx-recovered")

        self.assertFalse(report["accepted"])
        self.assertEqual(report["state"], "RECOVERED")
        self.assertEqual(report["failure_stage"], "scratch_roundtrip")
        self.assertEqual(report["failure_substep"], "scratch.enter")
        self.assertTrue(report["phone_mutation_performed"])
        self.assertTrue(report["cleanup_attempted"])
        self.assertTrue(report["cleanup_verified"])
        self.assertIsNone(report["cleanup_failure_substep"])
        self.assertFalse(report["filesystem_mutation_capabilities_proven"])
        self.assertEqual(prove_device.call_count, 2)
        cleanup.assert_called_once()

    @mock.patch.object(MODULE, "cleanup_paths", return_value=True)
    @mock.patch.object(MODULE, "run_scratch_certification")
    @mock.patch.object(MODULE, "verify_prestate")
    @mock.patch.object(MODULE._CAPABILITIES, "inventory")
    @mock.patch.object(MODULE._PREFLIGHT, "require_tools", return_value={"adb": True})
    @mock.patch.object(MODULE._PREFLIGHT, "prove_registered_device")
    def test_failure_report_identifies_exact_bounded_scratch_substep(
        self, _prove_device, _tools, inventory, _prestate, scratch, _cleanup
    ) -> None:
        inventory.return_value = self._inventory()

        def fail_scratch(
            _serial,
            _paths,
            _payloads,
            _local_root,
            *,
            comparator,
            mark_step=None,
        ):
            self.assertEqual(comparator, "cmp")
            self.assertIsNotNone(mark_step)
            mark_step("scratch.compare_original_remote")
            raise MODULE.CertificationFailure("device command returned nonzero status")

        scratch.side_effect = fail_scratch

        report = MODULE.certify("f" * 40, "tx-diagnostic")

        self.assertEqual(report["state"], "RECOVERED")
        self.assertEqual(report["failure_stage"], "scratch_roundtrip")
        self.assertEqual(report["failure_substep"], "scratch.compare_original_remote")
        self.assertEqual(report["failure"], "device command returned nonzero status")
        self.assertNotIn("registered-device", str(report))

    @mock.patch.object(MODULE, "cleanup_paths")
    @mock.patch.object(MODULE, "run_scratch_certification")
    @mock.patch.object(MODULE, "verify_prestate")
    @mock.patch.object(MODULE._CAPABILITIES, "inventory")
    @mock.patch.object(MODULE._PREFLIGHT, "require_tools", return_value={"adb": True})
    @mock.patch.object(MODULE._PREFLIGHT, "prove_registered_device")
    def test_cleanup_failure_preserves_original_failure_and_reports_cleanup_substep(
        self, _prove_device, _tools, inventory, _prestate, scratch, cleanup
    ) -> None:
        inventory.return_value = self._inventory()

        def fail_scratch(
            _serial,
            _paths,
            _payloads,
            _local_root,
            *,
            comparator,
            mark_step=None,
        ):
            self.assertEqual(comparator, "cmp")
            self.assertIsNotNone(mark_step)
            mark_step("scratch.atomic_replace")
            raise MODULE.CertificationFailure("device command returned nonzero status")

        def fail_cleanup(_serial, _paths, *, mark_step=None):
            self.assertIsNotNone(mark_step)
            mark_step("cleanup.scratch_verify_absent")
            return False

        scratch.side_effect = fail_scratch
        cleanup.side_effect = fail_cleanup

        report = MODULE.certify("c" * 40, "tx-quarantine")

        self.assertFalse(report["accepted"])
        self.assertEqual(report["state"], "QUARANTINED")
        self.assertEqual(report["failure_substep"], "scratch.atomic_replace")
        self.assertTrue(report["cleanup_attempted"])
        self.assertFalse(report["cleanup_verified"])
        self.assertEqual(report["cleanup_failure_substep"], "cleanup.scratch_verify_absent")

    @mock.patch.object(MODULE, "cleanup_paths", return_value=False)
    @mock.patch.object(
        MODULE,
        "run_scratch_certification",
        side_effect=MODULE.CertificationFailure("simulated interrupted write"),
    )
    @mock.patch.object(MODULE, "verify_prestate")
    @mock.patch.object(MODULE._CAPABILITIES, "inventory")
    @mock.patch.object(MODULE._PREFLIGHT, "require_tools", return_value={"adb": True})
    @mock.patch.object(MODULE._PREFLIGHT, "prove_registered_device")
    def test_cleanup_failure_quarantines_transaction(
        self, _prove_device, _tools, inventory, _prestate, _scratch, _cleanup
    ) -> None:
        inventory.return_value = self._inventory()

        report = MODULE.certify("1" * 40, "tx-quarantine-fallback")

        self.assertFalse(report["accepted"])
        self.assertEqual(report["state"], "QUARANTINED")
        self.assertTrue(report["cleanup_attempted"])
        self.assertFalse(report["cleanup_verified"])
        self.assertEqual(report["cleanup_failure_substep"], "cleanup.enter")

    @mock.patch.object(MODULE, "cleanup_paths")
    @mock.patch.object(MODULE, "verify_prestate")
    @mock.patch.object(MODULE._CAPABILITIES, "inventory")
    @mock.patch.object(MODULE._PREFLIGHT, "require_tools", return_value={"adb": True})
    @mock.patch.object(MODULE._PREFLIGHT, "prove_registered_device")
    def test_read_only_prerequisite_failure_refuses_before_mutation(
        self, prove_device, _tools, inventory, _prestate, cleanup
    ) -> None:
        value = self._inventory()
        value["read_only_capabilities_proven"] = False
        inventory.return_value = value

        report = MODULE.certify("d" * 40, "tx-refused")

        self.assertFalse(report["accepted"])
        self.assertEqual(report["state"], "REFUSED")
        self.assertFalse(report["phone_mutation_performed"])
        self.assertFalse(report["cleanup_attempted"])
        self.assertTrue(report["cleanup_verified"])
        self.assertIsNone(report["failure_substep"])
        self.assertIsNone(report["cleanup_failure_substep"])
        self.assertEqual(prove_device.call_count, 1)
        self.probe_scope.assert_not_called()
        cleanup.assert_not_called()

    def test_report_scope_never_contains_registered_serial(self) -> None:
        with (
            mock.patch.object(MODULE._PREFLIGHT, "require_tools", return_value={"adb": True}),
            mock.patch.object(MODULE._PREFLIGHT, "prove_registered_device"),
            mock.patch.object(MODULE._CAPABILITIES, "inventory", return_value=self._inventory()),
            mock.patch.object(MODULE, "verify_prestate"),
            mock.patch.object(MODULE, "run_scratch_certification"),
            mock.patch.object(MODULE, "run_managed_certification"),
            mock.patch.object(MODULE, "cleanup_paths", return_value=True),
        ):
            report = MODULE.certify("e" * 40, "tx-no-serial")
        self.assertNotIn("registered-device", str(report))


if __name__ == "__main__":
    unittest.main()
