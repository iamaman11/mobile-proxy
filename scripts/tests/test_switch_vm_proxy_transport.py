import importlib.util
import pathlib
import unittest
from argparse import Namespace
from unittest import mock


MODULE_PATH = pathlib.Path(__file__).parents[1] / "switch_vm_proxy_transport.py"
SPEC = importlib.util.spec_from_file_location("switch_vm_proxy_transport", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class VmProxyTransportSwitchTests(unittest.TestCase):
    def args(self, mode):
        return Namespace(
            mode=mode,
            project="project",
            zone="zone",
            instance="instance",
            ssh_user="operator",
            ssh_key="/tmp/key",
        )

    def test_modes_use_distinct_exact_upstreams(self):
        reverse = MODULE._CONFIGS["reverse-tunnel"]
        wireguard = MODULE._CONFIGS["wireguard"]
        for port in [14080, 14081, 14128]:
            self.assertIn(str(port), reverse)
            self.assertNotIn(str(port), wireguard)
        for port in [11080, 11081, 13128]:
            self.assertIn(str(port), wireguard)
            self.assertNotIn(str(port), reverse)
        self.assertNotEqual(reverse, wireguard)

    def test_remote_command_is_atomic_exact_and_reversible_on_any_failure(self):
        command = MODULE.remote_command("wireguard")
        self.assertIn(".candidate.$", command)
        self.assertIn(".expected.$", command)
        self.assertIn(".backup.$", command)
        self.assertIn("COMMITTED=0", command)
        self.assertIn("trap cleanup EXIT", command)
        self.assertIn('sudo cp "$CONFIG" "$BACKUP"', command)
        self.assertIn('sudo cp "$BACKUP" "$CONFIG"', command)
        self.assertIn("sudo nginx -t", command)
        self.assertIn("systemctl reload nginx", command)
        self.assertIn("wg-quick@wg0.service", command)
        self.assertIn("mobile-public-proxy.service", command)
        self.assertIn('sudo cmp -s -- "$CONFIG" "$EXPECTED"', command)
        self.assertNotIn("sha256", command.lower())
        self.assertIn("COMMITTED=1", command)

    @mock.patch.object(MODULE.subprocess, "run")
    def test_switch_requires_exact_remote_marker(self, run):
        run.return_value.stdout = f"active\n{MODULE._SUCCESS_MARKER}\n"
        report = MODULE.switch(self.args("reverse-tunnel"))
        self.assertTrue(report["accepted"])
        self.assertTrue(report["exact_config_match"])
        self.assertEqual(report["config_contract"], "mobile-public-proxy/v1")
        self.assertNotIn("config_sha256", report)

        run.return_value.stdout = "active\n"
        with self.assertRaisesRegex(MODULE.SwitchFailure, "byte-for-byte"):
            MODULE.switch(self.args("reverse-tunnel"))

    def test_exact_marker_parser_is_strict(self):
        self.assertTrue(MODULE.exact_match_returned("active\nexact-config-match\n"))
        self.assertFalse(MODULE.exact_match_returned("active\nexact-config-match-extra\n"))


if __name__ == "__main__":
    unittest.main()
