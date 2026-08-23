import importlib.util
import pathlib
import subprocess
import unittest
from argparse import Namespace
from unittest import mock


MODULE_PATH = pathlib.Path(__file__).parents[1] / "compare_proxy_topologies.py"
SPEC = importlib.util.spec_from_file_location("compare_proxy_topologies", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class CompareProxyTopologiesTests(unittest.TestCase):
    def test_probe_keeps_credentials_out_of_child_process_arguments(self):
        completed = subprocess.CompletedProcess([], 0, stdout="203.0.113.7\n", stderr="")
        with mock.patch.object(MODULE.subprocess, "run", return_value=completed) as run:
            result = MODULE.run_probe(
                "http://proxy.example:1080",
                'user:password-with-"-quote',
                "https://api.ipify.org",
                10,
            )

        command = run.call_args.args[0]
        self.assertNotIn('user:password-with-"-quote', command)
        self.assertIn("--config", command)
        self.assertIn('proxy-user = "user:password-with-\\"-quote"', run.call_args.kwargs["input"])
        self.assertTrue(result["ok"])

    def test_inventory_compares_candidate_and_restorable_default(self):
        self.assertEqual(
            MODULE.MODES,
            ("reverse-tunnel", "server-termination", "optimized-hybrid"),
        )
        self.assertEqual(MODULE.PRODUCTION_MODE, "optimized-hybrid")

    @mock.patch.object(MODULE.subprocess, "run")
    def test_probe_keeps_credentials_out_of_result(self, run):
        run.return_value = mock.Mock(returncode=0, stdout="192.0.2.1\n")
        result = MODULE.run_probe(
            "http://127.0.0.1:3128", "secret-user:secret-password", "https://probe", 5
        )
        self.assertTrue(result["ok"])
        self.assertNotIn("secret", str(result))
        self.assertNotIn("secret-user:secret-password", run.call_args.args[0])
        self.assertIn("secret-user:secret-password", run.call_args.kwargs["input"])

    def test_summary_is_bounded_and_ignores_failed_latency(self):
        report = MODULE.summarize([
            {"ok": True, "duration_ms": 10, "public_ip": "192.0.2.1"},
            {"ok": False, "duration_ms": 999, "public_ip": None, "exit_code": 28},
            {"ok": True, "duration_ms": 20, "public_ip": "192.0.2.1"},
        ])
        self.assertEqual(report["successes"], 2)
        self.assertEqual(report["median_ms"], 15)
        self.assertEqual(report["max_ms"], 20)
        self.assertEqual(report["failure_exit_codes"], {"28": 1})

    def test_switch_command_does_not_accept_proxy_credentials(self):
        args = Namespace(
            project="project", zone="zone", instance="instance", ssh_user="user", ssh_key="key"
        )
        command = MODULE.switch_command(args, "reverse-tunnel", pathlib.Path("report.json"))
        self.assertNotIn("password", " ".join(command).lower())


if __name__ == "__main__":
    unittest.main()
