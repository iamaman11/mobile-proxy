from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "control_state_machine.py"
SPEC = importlib.util.spec_from_file_location("control_state_machine", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


F = MODULE.Fact


class ControlStateMachineTests(unittest.TestCase):
    def test_real_preflight_shape_stops_at_source_fetch_without_inventing_phone_failure(self) -> None:
        facts = [
            F("run", "job_status", "completed"),
            F("run", "job_conclusion", "failure"),
            F("run", "runner_assigned", True),
            F("runner", "transport_tls_failure_recent", True),
            F("run", "source_fetch_result", "transport_failure"),
            F("run", "source_fetch_failed", True),
            F("run", "mutation_performed", False),
        ]

        state = MODULE.derive_snapshot(facts)

        self.assertEqual(state["command_job"], "JOB_FAILED")
        self.assertEqual(state["transport"], "TRANSPORT_DEGRADED")
        self.assertEqual(state["source_fetch"], "SOURCE_FETCH_FAILED_TRANSPORT")
        self.assertEqual(state["phone_access"], "PHONE_ACCESS_UNOBSERVED")
        self.assertEqual(state["failure_stage"], "SOURCE_FETCH")
        self.assertFalse(state["mutation_performed"])

    def test_skipped_job_never_becomes_runner_failure(self) -> None:
        facts = [
            F("run", "job_status", "completed"),
            F("run", "job_conclusion", "skipped"),
        ]

        state = MODULE.derive_snapshot(facts)

        self.assertEqual(state["command_job"], "JOB_SKIPPED")
        self.assertEqual(state["runner"], "RUNNER_UNKNOWN")
        self.assertEqual(state["phone_access"], "PHONE_ACCESS_UNOBSERVED")

    def test_queued_unassigned_is_distinct_from_offline_runner(self) -> None:
        facts = [
            F("run", "job_status", "queued"),
            F("run", "runner_assigned", False),
        ]

        state = MODULE.derive_snapshot(facts)

        self.assertEqual(state["command_job"], "JOB_QUEUED_UNASSIGNED")
        self.assertEqual(state["runner"], "RUNNER_UNKNOWN")

    def test_online_idle_runner_can_have_degraded_transport(self) -> None:
        facts = [
            F("runner", "runner_registered", True),
            F("runner", "runner_labels_match", True),
            F("runner", "runner_online", True),
            F("runner", "runner_busy", False),
            F("runner", "transport_tls_failure_recent", True),
        ]

        state = MODULE.derive_snapshot(facts)

        self.assertEqual(state["runner"], "RUNNER_ONLINE_IDLE")
        self.assertEqual(state["transport"], "TRANSPORT_DEGRADED")

    def test_phone_access_requires_every_identity_and_shell_fact(self) -> None:
        facts = [
            F("phone", "adb_tool_available", True),
            F("phone", "adb_inventory_valid", True),
            F("phone", "adb_device_count", 1),
            F("phone", "registered_device_match", True),
            F("phone", "registered_device_inventory_state", "device"),
            F("phone", "adb_get_state", "device"),
            F("phone", "adb_shell_probe", True),
        ]

        state = MODULE.derive_snapshot(facts)

        self.assertEqual(state["phone_access"], "PHONE_ACCESS_PROVEN")

    def test_missing_shell_fact_keeps_phone_access_unobserved(self) -> None:
        facts = [
            F("phone", "adb_tool_available", True),
            F("phone", "adb_inventory_valid", True),
            F("phone", "adb_device_count", 1),
            F("phone", "registered_device_match", True),
            F("phone", "registered_device_inventory_state", "device"),
            F("phone", "adb_get_state", "device"),
        ]

        state = MODULE.derive_snapshot(facts)

        self.assertEqual(state["phone_access"], "PHONE_ACCESS_UNOBSERVED")

    def test_package_health_does_not_participate_in_phone_access(self) -> None:
        facts = [
            F("phone", "package_present", True),
            F("phone", "runtime_healthy", True),
            F("phone", "proxy_ports_ready", True),
        ]

        state = MODULE.derive_snapshot(facts)

        self.assertEqual(state["phone_access"], "PHONE_ACCESS_UNOBSERVED")

    def test_conflicting_device_identity_fails_closed(self) -> None:
        facts = [
            F("phone", "adb_tool_available", True),
            F("phone", "adb_inventory_valid", True),
            F("phone", "adb_device_count", 1),
            F("phone", "registered_device_match", True),
            F("phone", "registered_device_match", False),
        ]

        state = MODULE.derive_snapshot(facts)

        self.assertEqual(state["phone_access"], "PHONE_ACCESS_CONFLICT")

    def test_stale_access_fact_cannot_be_reused(self) -> None:
        facts = [
            F("phone", "adb_tool_available", True, lifecycle="STALE"),
            F("phone", "adb_inventory_valid", True),
            F("phone", "adb_device_count", 1),
            F("phone", "registered_device_match", True),
            F("phone", "registered_device_inventory_state", "device"),
            F("phone", "adb_get_state", "device"),
            F("phone", "adb_shell_probe", True),
        ]

        state = MODULE.derive_snapshot(facts)

        self.assertEqual(state["phone_access"], "PHONE_ACCESS_UNOBSERVED")


if __name__ == "__main__":
    unittest.main()
