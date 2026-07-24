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
    def deployment(self, owner="first_party_reverse_tunnel"):
        return {
            "format_version": 1,
            "candidate_sha": "a" * 40,
            "expected_tunnel_owner": owner,
            "device_release_entries": 10,
            "vm_release_entries": 15,
            "device_release_metadata_match": True,
            "device_deployment_match": True,
            "android_vpn_owner_match": True,
            "vm_deployment_match": True,
            "accepted": True,
        }

    def switch(self, mode):
        return {
            "format_version": 1,
            "mode": mode,
            "config_sha256": "a" * 64,
            "public_ports": [1080, 1081, 3128],
            "accepted": True,
        }

    def stage(self, stage):
        transport = {
            "online": "quic",
            "post-reboot": "quic",
            "fallback": "tls_tcp",
            "recovered": "quic",
            "post-wireguard-recovered": "quic",
        }.get(stage)
        reverse = transport is not None
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
            "device_state": {
                "node_id": "device-1",
                "serving": True,
                "availability": "available",
                "heartbeat_present": True,
                "cellular_route_ready": True,
                "proxy_bind_ready": True,
                "local_serving_ready": True,
            },
            "tunnel_owner": (
                "first_party_reverse_tunnel" if reverse else "stock_wireguard_bridge"
            ),
            "reverse_tunnel": {
                "connected": True if reverse else False,
                "active_transport": transport,
                "freshness": "fresh" if reverse else None,
            },
            "wireguard": {
                "enabled": not reverse,
                "tun0_present": True if not reverse else None,
                "handshake_recent": True if not reverse else None,
            },
            "proxy_surfaces": {name: True for name in MODULE._REQUIRED_PROXY_SURFACES},
            "accepted": True,
        }

    def test_complete_report_set_contract(self):
        MODULE.verify_deployment_report(
            self.deployment(), "a" * 40, "primary", "first_party_reverse_tunnel"
        )
        MODULE.verify_deployment_report(
            self.deployment("stock_wireguard_bridge"),
            "a" * 40,
            "wireguard",
            "stock_wireguard_bridge",
        )
        MODULE.verify_deployment_report(
            self.deployment(), "a" * 40, "final", "first_party_reverse_tunnel"
        )
        MODULE.verify_switch_report(self.switch("reverse-tunnel"), "reverse-tunnel", "primary")
        MODULE.verify_switch_report(self.switch("wireguard"), "wireguard", "wireguard")
        MODULE.verify_switch_report(self.switch("reverse-tunnel"), "reverse-tunnel", "final")
        for stage in [
            "online",
            "post-reboot",
            "fallback",
            "recovered",
            "wireguard",
            "post-wireguard-recovered",
        ]:
            MODULE.verify_stage_report(self.stage(stage), "a" * 40, stage)

    def test_wrong_sha_owner_missing_mixed_protocol_or_stale_tunnel_fails(self):
        deployment = self.deployment()
        deployment["candidate_sha"] = "b" * 40
        with self.assertRaisesRegex(MODULE.AcceptanceFailure, "SHA differs"):
            MODULE.verify_deployment_report(
                deployment, "a" * 40, "primary", "first_party_reverse_tunnel"
            )

        deployment = self.deployment("stock_wireguard_bridge")
        with self.assertRaisesRegex(MODULE.AcceptanceFailure, "tunnel owner differs"):
            MODULE.verify_deployment_report(
                deployment, "a" * 40, "primary", "first_party_reverse_tunnel"
            )

        report = self.stage("online")
        del report["proxy_surfaces"]["mixed_1080_connect"]
        with self.assertRaisesRegex(MODULE.AcceptanceFailure, "incomplete"):
            MODULE.verify_stage_report(report, "a" * 40, "online")

        report = self.stage("fallback")
        report["reverse_tunnel"]["freshness"] = "stale"
        with self.assertRaisesRegex(MODULE.AcceptanceFailure, "stale"):
            MODULE.verify_stage_report(report, "a" * 40, "fallback")

        report = self.stage("online")
        report["wireguard"]["tun0_present"] = True
        with self.assertRaisesRegex(MODULE.AcceptanceFailure, "leaves tun0 active"):
            MODULE.verify_stage_report(report, "a" * 40, "online")

    def test_wireguard_stage_requires_owner_tun_and_handshake(self):
        report = self.stage("wireguard")
        report["wireguard"]["handshake_recent"] = False
        with self.assertRaisesRegex(MODULE.AcceptanceFailure, "not recent"):
            MODULE.verify_stage_report(report, "a" * 40, "wireguard")

        report = self.stage("wireguard")
        report["reverse_tunnel"]["connected"] = True
        with self.assertRaisesRegex(MODULE.AcceptanceFailure, "remained active"):
            MODULE.verify_stage_report(report, "a" * 40, "wireguard")

    def test_switch_report_requires_exact_mode_and_ports(self):
        report = self.switch("wireguard")
        report["public_ports"] = [1080]
        with self.assertRaisesRegex(MODULE.AcceptanceFailure, "ports differ"):
            MODULE.verify_switch_report(report, "wireguard", "wireguard")


if __name__ == "__main__":
    unittest.main()
