from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COMPONENT_CONTRACT = ROOT / "contracts/operations/phone-production-release-components-v1.json"
REALIZATION_CONTRACT = ROOT / "contracts/operations/phone-production-runtime-realization-v1.json"


class PhoneRuntimeRealizationTests(unittest.TestCase):
    def load(self):
        components = json.loads(COMPONENT_CONTRACT.read_text(encoding="utf-8"))
        realization = json.loads(REALIZATION_CONTRACT.read_text(encoding="utf-8"))
        return components, realization

    def test_realization_contract_is_bound_as_phone_component(self) -> None:
        components, realization = self.load()
        pointer = components["realization_contract"]
        self.assertEqual(pointer["component_name"], "runtime-realization-contract")
        self.assertEqual(pointer["source"], "contracts/operations/phone-production-runtime-realization-v1.json")
        self.assertEqual(pointer["archive_path"], "realization/phone-production-runtime-realization-v1.json")
        records = {item["name"]: item for item in components["components"]}
        bound = records[pointer["component_name"]]
        self.assertEqual(bound["kind"], "runtime-realization-contract")
        self.assertEqual(bound["source"], pointer["source"])
        self.assertEqual(bound["archive_path"], pointer["archive_path"])
        self.assertFalse(bound["executable"])
        self.assertEqual(realization["target"], "phone-production")
        self.assertEqual(realization["status"], "protected")

    def test_every_component_has_exactly_one_non_ambiguous_disposition(self) -> None:
        components, realization = self.load()
        names = {item["name"] for item in components["components"]}
        dispositions = realization["component_dispositions"]
        self.assertEqual(set(dispositions), names)
        allowed = {"live-copy", "render-input", "identity-only"}
        for name, rule in dispositions.items():
            with self.subTest(name=name):
                disposition = rule["disposition"]
                self.assertIn(disposition, allowed)
                if disposition == "live-copy":
                    self.assertEqual(set(rule), {"disposition", "release_path"})
                    self.assertTrue(rule["release_path"])
                    self.assertFalse(rule["release_path"].startswith("/"))
                    self.assertNotIn("..", Path(rule["release_path"]).parts)
                elif disposition == "render-input":
                    self.assertIn("render_role", rule)
                    self.assertNotIn("release_path", rule)
                else:
                    self.assertEqual(name, "runtime-realization-contract")
                    self.assertEqual(rule["identity_role"], "product-owned-runtime-realization-contract")
                    self.assertNotIn("release_path", rule)

    def test_live_paths_preserve_accepted_release_layout_without_filename_inference(self) -> None:
        _, realization = self.load()
        dispositions = realization["component_dispositions"]
        live = {
            name: rule["release_path"]
            for name, rule in dispositions.items()
            if rule["disposition"] == "live-copy"
        }
        self.assertEqual(
            live,
            {
                "runtime-supervisor": "bin/runtime-supervisor",
                "host-daemon": "bin/host-daemon",
                "sing-box": "bin/sing-box",
                "magisk-module-prop": "module.prop",
                "magisk-service": "service.sh",
            },
        )
        self.assertEqual(realization["activation_entrypoint"], "service.sh")
        self.assertTrue(realization["boundaries"]["controller_must_not_infer_release_paths_from_archive_filenames"])
        self.assertEqual(realization["absolute_device_root_owner"], "deployment-controller")

    def test_render_inputs_and_derived_outputs_are_explicit(self) -> None:
        _, realization = self.load()
        dispositions = realization["component_dispositions"]
        render_inputs = {
            name for name, rule in dispositions.items() if rule["disposition"] == "render-input"
        }
        self.assertEqual(
            render_inputs,
            {
                "profile-a1-by",
                "profile-default",
                "profile-mts-by",
                "app-wireguard-template",
                "host-daemon-template",
                "sing-box-template",
            },
        )
        derived = {item["name"]: item for item in realization["derived_runtime_files"]}
        self.assertTrue(derived["host-daemon-config"]["required_for_current_production"])
        self.assertTrue(derived["sing-box-config"]["required_for_current_production"])
        self.assertFalse(derived["app-wireguard-config"]["required_for_current_production"])
        self.assertEqual(derived["host-daemon-config"]["release_path"], "config/host-daemon.json")
        self.assertEqual(derived["sing-box-config"]["release_path"], "config/sing-box.json")
        self.assertEqual(derived["app-wireguard-config"]["release_path"], "config/app-wireguard.conf")
        for item in derived.values():
            for component in item["product_component_inputs"]:
                self.assertIn(component, render_inputs)
            self.assertTrue(item["secret_values_must_not_enter_product_release"])
            self.assertTrue(item["normative_implementation"].startswith("apps/operator-cli/src/provision.rs"))

    def test_required_runnable_layout_is_complete_and_supplemental_files_are_classified(self) -> None:
        _, realization = self.load()
        self.assertEqual(
            set(realization["required_live_release_paths"]),
            {
                "service.sh",
                "module.prop",
                "bin/runtime-supervisor",
                "bin/host-daemon",
                "bin/sing-box",
                "config/host-daemon.json",
                "config/sing-box.json",
            },
        )
        supplemental = {item["release_path"]: item for item in realization["legacy_supplemental_files"]}
        self.assertEqual(set(supplemental), {"bin/curl", "release-metadata.json", "integrity-manifest.json"})
        self.assertTrue(all(item["runtime_required"] is False for item in supplemental.values()))
        self.assertFalse(realization["boundaries"]["product_release_contains_secret_values"])
        self.assertTrue(realization["boundaries"]["controller_owns_atomic_activation_and_process_order"])

    def test_phone_realization_contract_contains_no_vm_or_server_material(self) -> None:
        components, realization = self.load()
        serialized = json.dumps({"components": components, "realization": realization}, sort_keys=True)
        for forbidden in (
            "deploy/vm-runtime/",
            "services/control-plane/",
            "services/relay-gate/",
            "services/reverse-tunnel-server/",
            "linux-amd64-glibc",
        ):
            self.assertNotIn(forbidden, json.dumps(realization, sort_keys=True))
        self.assertEqual(components["third_party_runtime"]["sing-box"]["lock_target"], "android-arm")
        self.assertIn("phone-production", serialized)


if __name__ == "__main__":
    unittest.main()
