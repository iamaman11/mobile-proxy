import importlib.util
import json
from pathlib import Path
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "verify_item19_acceptance_lifecycle.py"
SPEC = importlib.util.spec_from_file_location("item19_acceptance_lifecycle", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
ROOT = Path(__file__).resolve().parents[2]


class Item19AcceptanceLifecycleTests(unittest.TestCase):
    SHA = "a" * 40

    def workflow_run(self, *, name, path, run_id, created_at, sha=None):
        return {
            "id": run_id,
            "run_attempt": 1,
            "name": name,
            "path": path,
            "event": "push" if name == "Quality" else "issue_comment",
            "head_branch": "main",
            "head_sha": sha or self.SHA,
            "status": "completed",
            "conclusion": "success",
            "created_at": created_at,
            "repository": {"full_name": "iamaman11/mobile-proxy"},
        }

    def quality_run(self):
        return self.workflow_run(
            name="Quality",
            path=".github/workflows/quality.yml",
            run_id=100,
            created_at="2026-08-31T10:00:00Z",
        )

    def acceptance_run(self):
        return self.workflow_run(
            name="Vultr acceptance authority",
            path=".github/workflows/acceptance-authority.yml",
            run_id=200,
            created_at="2026-08-31T10:05:00Z",
        )

    def preflight_run(self, run_id=300):
        return self.workflow_run(
            name="Vultr read-only acceptance preflight",
            path=".github/workflows/vultr-readonly-preflight.yml",
            run_id=run_id,
            created_at="2026-08-31T10:10:00Z",
        )

    def acceptance_evidence(self):
        return {
            "format_version": 1,
            "authority": "pre_release_acceptance",
            "candidate_sha": self.SHA,
            "repository": "iamaman11/mobile-proxy",
            "executor": "github-hosted",
            "acceptance_workflow": "Vultr acceptance authority",
            "acceptance_workflow_run_id": "200",
            "acceptance_workflow_run_attempt": "1",
            "command_issue": 90,
            "command_comment_id": "501",
            "candidate_quality_run_id": "100",
            "candidate_quality_run_attempt": "1",
            "candidate_evidence_artifact": f"software-release-candidate-{self.SHA}",
            "candidate_evidence_file": "release-candidate-evidence.json",
            "final_production_authority": False,
            "production_environment_authorized": False,
            "final_release_tag_created": False,
            "vultr_api_access_performed": False,
            "vm_mutation_performed": False,
            "phone_mutation_performed": False,
        }

    def preflight_evidence(self):
        return {
            "format_version": 1,
            "authority": "pre_release_acceptance_read_only",
            "candidate_sha": self.SHA,
            "repository": "iamaman11/mobile-proxy",
            "executor": "github-hosted",
            "environment": "acceptance-vultr",
            "workflow": "Vultr read-only acceptance preflight",
            "workflow_run_id": "300",
            "workflow_run_attempt": "1",
            "command_issue": 90,
            "command_comment_id": "601",
            "acceptance_authority_run_id": "200",
            "acceptance_authority_run_attempt": "1",
            "api_key_available": True,
            "ssh_private_key_available": True,
            "ssh_private_key_valid": True,
            "provider_api_method": "GET",
            "provider_api_path": "/v2/account",
            "provider_api_calls": 1,
            "account_endpoint_accessible": True,
            "account_response_body_recorded": False,
            "account_metadata_recorded": False,
            "secret_values_recorded": False,
            "secret_derived_identifiers_recorded": False,
            "vm_lifecycle_access_performed": False,
            "vm_mutation_performed": False,
            "phone_mutation_performed": False,
            "final_production_authority": False,
            "production_environment_authorized": False,
            "final_release_tag_created": False,
        }

    def test_exact_readiness_command_only(self):
        command = f"/item19-acceptance-ready {self.SHA}"
        self.assertEqual(MODULE.parse_command(command), self.SHA)
        with self.assertRaises(ValueError):
            MODULE.parse_command("/item19-acceptance-ready main")

    def test_exact_current_protected_main_is_required(self):
        MODULE.verify_main_branch(
            self.SHA,
            {"name": "main", "protected": True, "commit": {"sha": self.SHA}},
        )
        with self.assertRaises(ValueError):
            MODULE.verify_main_branch(
                self.SHA,
                {"name": "main", "protected": False, "commit": {"sha": self.SHA}},
            )

    def test_fresh_chain_remains_strict_historical_verifier_logic(self):
        MODULE.verify_fresh_chain(
            self.quality_run(),
            self.acceptance_run(),
            self.acceptance_evidence(),
            self.preflight_run(),
            "2026-08-31T10:15:00Z",
        )
        stale = self.acceptance_evidence()
        stale["candidate_quality_run_id"] = "999"
        with self.assertRaises(ValueError):
            MODULE.verify_fresh_chain(
                self.quality_run(),
                self.acceptance_run(),
                stale,
                self.preflight_run(),
                "2026-08-31T10:15:00Z",
            )

    def test_admission_evidence_remains_bounded_and_non_production(self):
        evidence = MODULE.build_admission_evidence(
            self.SHA,
            self.quality_run(),
            self.acceptance_run(),
            self.preflight_run(),
            {
                "GITHUB_REPOSITORY": "iamaman11/mobile-proxy",
                "GITHUB_RUN_ID": "700",
                "GITHUB_RUN_ATTEMPT": "1",
                "COMMAND_COMMENT_ID": "800",
            },
        )
        self.assertFalse(evidence["final_production_authority"])
        self.assertFalse(evidence["phone_mutation_authorized"])
        self.assertFalse(evidence["provider_mutation_performed_at_admission"])
        self.assertNotIn("VULTR_API_KEY", json.dumps(evidence))

    def test_retired_workflow_is_absent(self):
        self.assertFalse((ROOT / ".github/workflows/item19-acceptance-lifecycle.yml").exists())


if __name__ == "__main__":
    unittest.main()
