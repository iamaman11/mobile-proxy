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
        self.assertNotEqual(
            MODULE.config_digest("reverse-tunnel"),
            MODULE.config_digest("wireguard"),
        )

    def test_remote_command_is_atomic_validated_and_reversible_on_failure(self):
        command = MODULE.remote_command("wireguard")
        self.assertIn(".candidate.$", command)
        self.assertIn(".backup.$", command)
        self.assertIn("sudo cp \"$CONFIG\" \"$BACKUP\"", command)
        self.assertIn("if ! sudo nginx -t", command)
        self.assertIn("sudo cp \"$BACKUP\" \"$CONFIG\"", command)
        self.assertIn("systemctl reload nginx", command)
        self.assertIn("wg-quick@wg0.service", command)
        self.assertIn("mobile-public-proxy.service", command)
        self.assertIn("sha256sum", command)

    @mock.patch.object(MODULE.subprocess, "run")
    def test_switch_requires_exact_remote_config_digest(self, run):
        expected = MODULE.config_digest("reverse-tunnel")
        run.return_value.stdout = f"active\n{expected}  {MODULE._REMOTE_CONFIG}\n"
        report = MODULE.switch(self.args("reverse-tunnel"))
        self.assertTrue(report["accepted"])
        self.assertEqual(report["config_sha256"], expected)
        self.assertNotIn(expected, run.call_args.args[0])

        run.return_value.stdout = f"{'0' * 64}  {MODULE._REMOTE_CONFIG}\n"
        with self.assertRaisesRegex(MODULE.SwitchFailure, "differs"):
            MODULE.switch(self.args("reverse-tunnel"))

    def test_invalid_digest_output_fails_closed(self):
        with self.assertRaisesRegex(MODULE.SwitchFailure, "invalid"):
            MODULE.parse_remote_digest("active\nnot-a-digest file\n")


if __name__ == "__main__":
    unittest.main()
