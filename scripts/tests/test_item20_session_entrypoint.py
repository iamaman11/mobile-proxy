import json
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
CONTRACT = ROOT / "contracts" / "operations" / "item20-acceptance-v1.json"
ENTRYPOINT = ROOT / "apps" / "operator-cli" / "src" / "bin" / "item20-session-lifecycle.rs"
WORKFLOW = ROOT / ".github" / "workflows" / "item20-session-orchestration.yml"
RETIREMENT = ROOT / "contracts" / "operations" / "historical-public-acceptance-retirement-v1.json"


class Item20SessionEntrypointTests(unittest.TestCase):
    def test_historical_contract_snapshot_remains_non_live(self) -> None:
        contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
        self.assertFalse(contract["authorization"]["provider_mutation_authorized"])
        self.assertFalse(contract["authorization"]["phone_mutation_authorized"])
        self.assertFalse(contract["authorization"]["endpoint_handoff_authorized"])
        self.assertFalse(contract["authorization"]["live_execution_authorized"])
        self.assertEqual(
            contract["session_entrypoint"]["binary"],
            "apps/operator-cli/src/bin/item20-session-lifecycle.rs",
        )

    def test_retired_workflow_is_absent(self) -> None:
        self.assertFalse(WORKFLOW.exists())
        retirement = json.loads(RETIREMENT.read_text(encoding="utf-8"))
        self.assertIn(str(WORKFLOW.relative_to(ROOT)), retirement["retired_workflows"])

    def test_entrypoint_reuses_typed_policy_and_emits_no_endpoint(self) -> None:
        source = ENTRYPOINT.read_text(encoding="utf-8")
        for required in (
            "DurableGitHubVmBindingStore::new_item20",
            "open_item20_session",
            "verified_item20_target",
            "close_item20_session",
            'GITHUB_REPOSITORY',
            'GITHUB_REF_PROTECTED',
            'provider_identifier_recorded: false',
            'transport_endpoint_recorded: false',
            'endpoint_handoff_authorized: false',
            'phone_mutation_performed: false',
        ):
            self.assertIn(required, source)
        for forbidden in (
            "verified_item20_endpoint",
            "instance_ipv4",
            "production-vultr",
            "LifecycleScope::Production",
            'Command::new("ssh")',
            'Command::new("adb")',
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
