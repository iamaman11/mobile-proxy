import json
import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
CONTRACT = ROOT / "contracts" / "operations" / "item20-acceptance-v1.json"
TOPOLOGY = ROOT / "contracts" / "operations" / "production-topology-v1.json"
WORKFLOW = ROOT / ".github" / "workflows" / "item20-session-orchestration.yml"
ENTRYPOINT = ROOT / "apps" / "operator-cli" / "src" / "bin" / "item20-session-lifecycle.rs"


class Item20SessionEntrypointTests(unittest.TestCase):
    def test_contract_records_compile_only_non_live_entrypoint(self) -> None:
        contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
        self.assertEqual(
            contract["session_entrypoint"],
            {
                "binary": "apps/operator-cli/src/bin/item20-session-lifecycle.rs",
                "current_workflow_endpoint_handoff": False,
                "current_workflow_environment": "none",
                "current_workflow_phone_execution": False,
                "current_workflow_provider_credentials": "forbidden",
                "current_workflow_provider_mutation": False,
                "endpoint_resolution_command": "not_exposed",
                "future_runtime_commands": ["open", "verify-target", "close"],
                "grants_live_authority": False,
                "lifecycle_policy_owner": "apps/operator-cli/src/item20_session_lifecycle.rs",
                "status": "protected_typed_compile_only_not_live_invoked",
                "workflow": ".github/workflows/item20-session-orchestration.yml",
                "workflow_wiring": "compile_only",
            },
        )
        self.assertFalse(contract["authorization"]["provider_mutation_authorized"])
        self.assertFalse(contract["authorization"]["phone_mutation_authorized"])
        self.assertFalse(contract["authorization"]["endpoint_handoff_authorized"])
        self.assertFalse(contract["authorization"]["live_execution_authorized"])

    def test_workflow_only_compiles_entrypoint(self) -> None:
        workflow = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn(
            "cargo check --locked -p operator-cli --bin item20-session-lifecycle",
            workflow,
        )
        self.assertIn("Typed Item 20 lifecycle entrypoint compiled: true", workflow)
        self.assertIn("Typed Item 20 lifecycle entrypoint invoked: false", workflow)
        for forbidden in (
            "acceptance-vultr",
            "production-vultr",
            "VULTR_API_KEY",
            "VULTR_SSH_PRIVATE_KEY",
            "verified_item20_endpoint",
            "item20-session-lifecycle open",
            "item20-session-lifecycle verify-target",
            "item20-session-lifecycle close",
        ):
            self.assertNotIn(forbidden, workflow)

    def test_entrypoint_reuses_typed_policy_and_emits_no_endpoint(self) -> None:
        source = ENTRYPOINT.read_text(encoding="utf-8")
        for required in (
            "DurableGitHubVmBindingStore::new_item20",
            "open_item20_session",
            "verified_item20_target",
            "close_item20_session",
            'GITHUB_REPOSITORY',
            'GITHUB_REF_PROTECTED',
            'refs/heads/main',
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
            "candidate_sha != control_plane_sha",
            "candidate_sha == control_plane_sha",
        ):
            self.assertNotIn(forbidden, source)

    def test_topology_records_entrypoint_without_live_authority(self) -> None:
        topology = json.loads(TOPOLOGY.read_text(encoding="utf-8"))
        self.assertEqual(
            topology["migration_status"]["item_20_typed_session_entrypoint"],
            "protected_typed_cli_compile_only_not_live_invoked_no_provider_or_phone_authority",
        )
        self.assertEqual(
            topology["migration_status"]["phone_mutation"],
            "item_20_blocked_by_signing_continuity_gate_issue_115",
        )
        self.assertIn("no acceptance-vultr environment", topology["execution"]["item20_non_live"])


if __name__ == "__main__":
    unittest.main()
