import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "check_state_ownership.py"
SPEC = importlib.util.spec_from_file_location("state_ownership", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
REPO_ROOT = Path(__file__).resolve().parents[2]
CONTRACT_PATH = REPO_ROOT / MODULE.CONTRACT_PATH


class StateOwnershipTests(unittest.TestCase):
    def load_contract(self):
        return json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))

    def validate_changed(self, change):
        contract = self.load_contract()
        change(contract)
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "state-ownership.json"
            path.write_text(json.dumps(contract), encoding="utf-8")
            return MODULE.validate_repository(REPO_ROOT, path)

    def test_repository_contract_passes(self):
        self.assertEqual(MODULE.validate_repository(REPO_ROOT), [])

    def test_duplicate_resource_owner_is_rejected(self):
        def change(contract):
            resource = contract["state_groups"][0]["resources"][0]
            contract["state_groups"][1]["resources"].append(resource)

        errors = self.validate_changed(change)
        self.assertTrue(any("has multiple owners" in error for error in errors))

    def test_unknown_authority_module_is_rejected(self):
        def change(contract):
            contract["state_groups"][0]["authority_module"] = "services/unknown-owner"

        errors = self.validate_changed(change)
        self.assertTrue(any("unknown authority module" in error for error in errors))

    def test_writer_outside_authority_is_rejected(self):
        def change(contract):
            contract["state_groups"][1]["writer_paths"] = [
                "services/control-plane/src/state.rs"
            ]

        errors = self.validate_changed(change)
        self.assertTrue(any("writer path escapes authority module" in error for error in errors))

    def test_durable_state_without_persistence_owner_is_rejected(self):
        def change(contract):
            contract["state_groups"][0]["persistence_owner_module"] = None

        errors = self.validate_changed(change)
        self.assertTrue(any("durable state requires a known persistence owner" in error for error in errors))

    def test_ephemeral_state_cannot_have_persistence_writer(self):
        def change(contract):
            group = contract["state_groups"][1]
            group["persistence_owner_module"] = "crates/reverse-tunnel"
            group["persistence_writer_paths"] = ["crates/reverse-tunnel/src/state.rs"]

        errors = self.validate_changed(change)
        self.assertTrue(any("ephemeral state must not name a persistence owner" in error for error in errors))
        self.assertTrue(any("ephemeral state must not have persistence writer paths" in error for error in errors))

    def test_non_fail_closed_policy_is_rejected(self):
        def change(contract):
            contract["policies"]["duplicate_resource_owner"] = "allow"

        errors = self.validate_changed(change)
        self.assertTrue(any("policies must remain fail-closed" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
