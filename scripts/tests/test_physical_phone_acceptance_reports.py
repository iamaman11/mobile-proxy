import importlib.util
import pathlib
import sys
import unittest


SCRIPTS_DIR = pathlib.Path(__file__).parents[1]
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))
MODULE_PATH = SCRIPTS_DIR / "verify_physical_phone_acceptance_reports.py"
SPEC = importlib.util.spec_from_file_location("physical_reports", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class PhysicalReportVerifierTests(unittest.TestCase):
    def deployment(self):
        return {
            "format_version": 1,
            "candidate_sha": "a" * 40,
            "device_release_entries": 10,
            "vm_release_entries": 15,
            "device_release_metadata_match": True,
            "device_deployment_match": True,
            "vm_deployment_match": True,
            "accepted": True,
        }

    def stage(self, stage):
        transport = {
            "online": "quic",
            "post-reboot": "quic",
            "fallback": "tls_tcp",
            "recovered": "quic",
        }.get(stage)
        return {
            "format_version": 1,
            "candidate_sha": "a" * 40,
            "stage": stage,
            "process_health": {
                "host_live": True,
                "host_ready": True,
                "control_plane_ready": True,
            },
            "device_inventory_present": True,
            "expected_device_present": True,
            "reverse_tunnel": {
                "connected": True if transport else None,
                "active_transport": transport,
                "freshness": "fresh" if transport else None,
            },
            "wireguard_enabled": stage == "wireguard",
            "proxy_surfaces": {name: True for name in MODULE._REQUIRED_PROXY_SURFACES},
            "accepted": True,
        }

    def test_complete_report_set_contract(self):
        MODULE.verify_deployment_report(self.deployment(), "a" * 40)
        for stage in ["online", "post-reboot", "fallback", "recovered", "wireguard"]:
            MODULE.verify_stage_report(self.stage(stage), "a" * 40, stage)

    def test_wrong_sha_missing_mixed_protocol_or_stale_tunnel_fails(self):
        deployment = self.deployment()
        deployment["candidate_sha"] = "b" * 40
        with self.assertRaisesRegex(MODULE.AcceptanceFailure, "SHA differs"):
            MODULE.verify_deployment_report(deployment, "a" * 40)

        report = self.stage("online")
        del report["proxy_surfaces"]["mixed_1080_connect"]
        with self.assertRaisesRegex(MODULE.AcceptanceFailure, "incomplete"):
            MODULE.verify_stage_report(report, "a" * 40, "online")

        report = self.stage("fallback")
        report["reverse_tunnel"]["freshness"] = "stale"
        with self.assertRaisesRegex(MODULE.AcceptanceFailure, "stale"):
            MODULE.verify_stage_report(report, "a" * 40, "fallback")

    def test_wireguard_stage_requires_enabled_rollback(self):
        report = self.stage("wireguard")
        report["wireguard_enabled"] = False
        with self.assertRaisesRegex(MODULE.AcceptanceFailure, "not enabled"):
            MODULE.verify_stage_report(report, "a" * 40, "wireguard")


if __name__ == "__main__":
    unittest.main()
