import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class ProductionRunnerLauncherTests(unittest.TestCase):
    def test_proxy_selection_is_dynamic_bounded_and_optional(self) -> None:
        launcher = (ROOT / "scripts/run-production-runner").read_text(encoding="utf-8")

        unset_at = launcher.index("unset ALL_PROXY")
        gateway_at = launcher.index("ip route show default")
        probe_at = launcher.index("timeout 2 bash")
        exec_at = launcher.index("exec ./run.sh")

        self.assertLess(unset_at, gateway_at)
        self.assertLess(gateway_at, probe_at)
        self.assertLess(probe_at, exec_at)
        self.assertIn('HTTP_PROXY="http://$proxy_host:17890"', launcher)
        self.assertIn('HTTPS_PROXY="$HTTP_PROXY"', launcher)
        self.assertNotIn("172.26.", launcher)


if __name__ == "__main__":
    unittest.main()
