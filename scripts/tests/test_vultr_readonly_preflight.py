import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "verify_vultr_readonly_preflight.py"
POLICY_SCRIPT = ROOT / "scripts" / "check_vultr_readonly_preflight_policy.py"

SPEC = importlib.util.spec_from_file_location("vultr_readonly_preflight", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

POLICY_SPEC = importlib.util.spec_from_file_location("vultr_readonly_policy", POLICY_SCRIPT)
assert POLICY_SPEC is not None and POLICY_SPEC.loader is not None
POLICY = importlib.util.module_from_spec(POLICY_SPEC)
POLICY_SPEC.loader.exec_module(POLICY)


class VultrReadonlyPreflightTests(unittest.TestCase):
    candidate_sha = "a" * 40
    control_plane_sha = "c" * 40

    def acceptance_artifact(self, *, candidate_sha=None, control_plane_sha=None, artifact_id=500, run_id=123):
        candidate = candidate_sha or self.candidate_sha
        control = control_plane_sha or self.control_plane_sha
        return {
            "id": artifact_id,
            "name": f"vultr-acceptance-authority-{candidate}",
            "size_in_bytes": 321,
            "expired": False,
            "digest": "sha256:" + "d" * 64,
            "created_at": "2026-08-31T12:00:00Z",
            "workflow_run": {"id": run_id, "head_branch": "main", "head_sha": control},
        }

    def environment(self):
        return {
            "GITHUB_REPOSITORY": "iamaman11/mobile-proxy",
            "GITHUB_WORKFLOW": "Vultr read-only acceptance preflight",
            "GITHUB_RUN_ID": "1001",
            "GITHUB_RUN_ATTEMPT": "1",
            "COMMAND_COMMENT_ID": "2002",
            "ACCEPTANCE_AUTHORITY_RUN_ID": "3003",
            "ACCEPTANCE_AUTHORITY_RUN_ATTEMPT": "1",
        }

    def test_exact_command_parser_is_retained(self):
        sha = self.candidate_sha
        self.assertEqual(MODULE.parse_command(f"/vultr-readonly-preflight {sha}"), sha)
        for value in ("/vultr-readonly-preflight main", "/vultr-readonly-preflight " + "a" * 12):
            with self.assertRaises(ValueError):
                MODULE.parse_command(value)

    def test_artifact_selector_remains_exact_and_fail_closed(self):
        selected = MODULE.select_acceptance_artifact(
            self.candidate_sha,
            self.control_plane_sha,
            {"artifacts": [self.acceptance_artifact()]},
        )
        self.assertEqual(selected["id"], 500)
        wrong = self.acceptance_artifact(control_plane_sha="e" * 40)
        with self.assertRaises(ValueError):
            MODULE.select_acceptance_artifact(
                self.candidate_sha, self.control_plane_sha, {"artifacts": [wrong]}
            )

    def test_historical_evidence_builder_remains_bounded(self):
        evidence = MODULE.build_preflight_evidence(self.candidate_sha, self.environment())
        self.assertEqual(evidence["provider_api_method"], "GET")
        self.assertEqual(evidence["provider_api_path"], "/v2/account")
        self.assertFalse(evidence["vm_mutation_performed"])
        self.assertFalse(evidence["phone_mutation_performed"])
        self.assertFalse(evidence["final_production_authority"])
        self.assertNotIn("VULTR_API_KEY", json.dumps(evidence))

    def test_retirement_policy_passes_and_workflow_is_absent(self):
        self.assertEqual(POLICY.check_repository(ROOT), [])
        self.assertFalse((ROOT / ".github/workflows/vultr-readonly-preflight.yml").exists())
        contract = json.loads(
            (ROOT / "contracts/operations/vultr-readonly-preflight-v1.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(contract["provider_probe"]["method"], "GET")
        self.assertEqual(contract["provider_probe"]["url"], "https://api.vultr.com/v2/account")
        self.assertFalse(contract["authority_separation"]["final_production_authority"])


if __name__ == "__main__":
    unittest.main()
