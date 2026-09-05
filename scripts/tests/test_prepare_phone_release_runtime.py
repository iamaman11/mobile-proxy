import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "prepare_phone_release_runtime.py"
SPEC = importlib.util.spec_from_file_location("prepare_phone_release_runtime", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
ROOT = Path(__file__).resolve().parents[2]
CONTRACT = Path("contracts/operations/phone-production-release-components-v1.json")
LOCK = Path("deploy/sing-box-artifacts.lock.json")


def copy_inputs(root: Path) -> None:
    for relative in (CONTRACT, LOCK):
        source = ROOT / relative
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


class PhoneReleaseRuntimePreparationTests(unittest.TestCase):
    def test_committed_phone_build_inputs_are_exact_and_phone_only(self) -> None:
        inputs = MODULE.resolve_phone_build_inputs(ROOT, ROOT / CONTRACT)
        self.assertEqual(inputs["android_ndk_version"], "29.0.14206865")
        self.assertEqual(inputs["android_api_level"], 23)
        self.assertEqual(inputs["rust_profile"], "release")
        self.assertEqual(inputs["rust_target"], "armv7-linux-androideabi")
        self.assertEqual(inputs["sing_box"]["lock_target"], "android-arm")

    def test_vm_only_sing_box_pin_cannot_change_phone_build_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            copy_inputs(root)
            before = MODULE.resolve_phone_build_inputs(root, root / CONTRACT)
            path = root / LOCK
            lock = json.loads(path.read_text(encoding="utf-8"))
            vm = lock["artifacts"]["linux-amd64-glibc"]
            vm["size"] += 1
            vm["upstream_sha256"] = "0" * 64
            vm["content_digest"] = "b3:" + "1" * 64
            path.write_text(json.dumps(lock, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            after = MODULE.resolve_phone_build_inputs(root, root / CONTRACT)
        self.assertEqual(before, after)

    def test_phone_contract_cannot_switch_to_vm_sing_box_target(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            copy_inputs(root)
            path = root / CONTRACT
            contract = json.loads(path.read_text(encoding="utf-8"))
            contract["third_party_runtime"]["sing-box"]["lock_target"] = "linux-amd64-glibc"
            path.write_text(json.dumps(contract), encoding="utf-8")
            with self.assertRaisesRegex(
                MODULE.PhoneRuntimePreparationError,
                "must remain android-arm",
            ):
                MODULE.resolve_phone_build_inputs(root, path)

    def test_ndk_pin_is_mandatory_and_exact(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            copy_inputs(root)
            path = root / CONTRACT
            contract = json.loads(path.read_text(encoding="utf-8"))
            contract["build_toolchain"]["android_ndk_version"] = "latest"
            path.write_text(json.dumps(contract), encoding="utf-8")
            with self.assertRaisesRegex(
                MODULE.PhoneRuntimePreparationError,
                "NDK version is invalid",
            ):
                MODULE.resolve_phone_build_inputs(root, path)

    def test_release_builder_source_has_no_vm_runtime_payload_path(self) -> None:
        body = SCRIPT.read_text(encoding="utf-8")
        self.assertNotIn("deploy/vm-runtime", body)
        self.assertNotIn("linux-amd64-glibc", body)


if __name__ == "__main__":
    unittest.main()
