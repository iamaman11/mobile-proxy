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
            ssh_attempts=3,
        )

    def test_modes_use_distinct_exact_upstreams(self):
        reverse = MODULE._CONFIGS["reverse-tunnel"]
        wireguard = MODULE._CONFIGS["wireguard"]
        server = MODULE._CONFIGS["server-termination"]
        optimized = MODULE._CONFIGS["optimized-hybrid"]
        for port in [14080, 14081, 14128]:
            self.assertIn(str(port), reverse)
            self.assertNotIn(str(port), wireguard)
        for port in [11080, 11081, 13128]:
            self.assertIn(str(port), wireguard)
            self.assertNotIn(str(port), reverse)
        for port in [12080, 12081, 12128]:
            self.assertIn(str(port), server)
            self.assertNotIn(str(port), reverse)
            self.assertNotIn(str(port), wireguard)
        self.assertEqual(optimized.count("proxy_pass 127.0.0.1:14080"), 3)
        self.assertNotIn("proxy_pass 127.0.0.1:14081", optimized)
        self.assertNotIn("proxy_pass 127.0.0.1:12128", optimized)
        self.assertEqual(len({reverse, wireguard, server, optimized}), 4)

    def test_server_termination_requires_both_proxy_layers(self):
        command = MODULE.remote_command("server-termination")
        self.assertIn("mobile-public-proxy.service", command)
        self.assertIn(":(443|1080|1081|3128)", command)
        self.assertIn("mobile-reverse-tunnel-server.service", command)

    def test_every_mode_preserves_pinned_tls_reverse_tunnel_ingress(self):
        for config in MODULE._CONFIGS.values():
            self.assertIn("listen 0.0.0.0:443 ssl", config)
            self.assertIn("proxy_pass 127.0.0.1:18091", config)
            self.assertIn("ssl_session_tickets off", config)

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
        self.assertIn("if sudo cmp -s", command)
        self.assertIn("verify_runtime", command)
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

    @mock.patch.object(MODULE.time, "sleep")
    @mock.patch.object(MODULE.subprocess, "run")
    def test_switch_retries_transient_ssh_failure(self, run, sleep):
        run.side_effect = [
            MODULE.subprocess.CalledProcessError(255, ["gcloud"]),
            mock.Mock(stdout=f"{MODULE._SUCCESS_MARKER}\n"),
        ]
        report = MODULE.switch(self.args("reverse-tunnel"))
        self.assertTrue(report["accepted"])
        self.assertEqual(run.call_count, 2)
        sleep.assert_called_once_with(1)


if __name__ == "__main__":
    unittest.main()
