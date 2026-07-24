import importlib.util
import pathlib
import sys
import unittest
from argparse import Namespace
from unittest import mock


SCRIPTS_DIR = pathlib.Path(__file__).parents[1]
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))
MODULE_PATH = SCRIPTS_DIR / "activate_device_release.py"
SPEC = importlib.util.spec_from_file_location("activate_device_release", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class ActivateDeviceReleaseTests(unittest.TestCase):
    def test_activation_script_restarts_runtime_without_copying_or_rebuilding(self):
        script = MODULE.activation_script("/data/adb/mobile-proxy-node", "candidate-reverse")
        self.assertIn("pkill -f mobile-proxy-runtime-watchdog", script)
        self.assertIn("pidof runtime-supervisor host-daemon sing-box", script)
        self.assertIn("ln -sfn \"$TARGET\" \"$ROOT/current\"", script)
        self.assertIn("sh \"$ROOT/current/service.sh\"", script)
        self.assertNotIn("cp -R", script)
        self.assertNotIn("cargo", script)

    def test_release_id_is_strict(self):
        for invalid in ["", "../escape", "has space", ";reboot", "x" * 129]:
            with self.assertRaisesRegex(MODULE.AcceptanceFailure, "release ID is invalid"):
                MODULE.activation_script("/data/adb/mobile-proxy-node", invalid)

    @mock.patch.object(MODULE, "verify_candidate", return_value="a" * 40)
    @mock.patch.object(MODULE, "read_json", return_value={})
    @mock.patch.object(MODULE.subprocess, "run")
    def test_activation_requires_exact_active_symlink(self, run, _read, _verify):
        args = Namespace(
            evidence=pathlib.Path("evidence.json"),
            release_id="candidate-reverse",
            device_serial="serial",
            device_root="/data/adb/mobile-proxy-node",
        )
        run.return_value.stdout = "/data/adb/mobile-proxy-node/releases/candidate-reverse\n"
        report = MODULE.activate(args)
        self.assertTrue(report["full_runtime_restart"])
        self.assertTrue(report["accepted"])

        run.return_value.stdout = "/data/adb/mobile-proxy-node/releases/other\n"
        with self.assertRaisesRegex(MODULE.AcceptanceFailure, "differs"):
            MODULE.activate(args)


if __name__ == "__main__":
    unittest.main()
