import importlib.util
import json
from pathlib import Path
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "verify_vultr_readonly_preflight.py"
SPEC = importlib.util.spec_from_file_location("vultr_readonly_preflight", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
ROOT = Path(__file__).resolve().parents[2]


class VultrReadonlyPreflightTests(unittest.TestCase):
    def acceptance_run(self, sha="a" * 40, run_id=123):
        return {
            "id": run_id,
            "run_attempt": 1,
            "name": "Vultr acceptance authority",
            "path": ".github/workflows/acceptance-authority.yml",
            "event": "issue_comment",
            "head_branch": "main",
            "head_sha": sha,
            "status": "completed",
            "conclusion": "success",
            "repository": {"full_name": "iamaman11/mobile-proxy"},
        }

    def acceptance_evidence(self, sha="a" * 40, run_id=123):
        return {
            "format_version": 1,
            "authority": "pre_release_acceptance",
            "candidate_sha": sha,
            "repository": "iamaman11/mobile-proxy",
            "executor": "github-hosted",
            "acceptance_workflow": "Vultr acceptance authority",
            "acceptance_workflow_run_id": str(run_id),
            "acceptance_workflow_run_attempt": "1",
            "command_issue": 90,
            "command_comment_id": "456",
            "candidate_quality_run_id": "789",
            "candidate_quality_run_attempt": "1",
            "candidate_evidence_artifact": f"software-release-candidate-{sha}",
            "candidate_evidence_file": "release-candidate-evidence.json",
            "final_production_authority": False,
            "production_environment_authorized": False,
            "final_release_tag_created": False,
            "vultr_api_access_performed": False,
            "vm_mutation_performed": False,
            "phone_mutation_performed": False,
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

    def test_exact_command_only(self):
        sha = "a" * 40
        self.assertEqual(MODULE.parse_command(f"/vultr-readonly-preflight {sha}"), sha)
        for value in (
            "/vultr-readonly-preflight main",
            "/vultr-readonly-preflight latest",
            "/vultr-readonly-preflight feature/test",
            "/vultr-readonly-preflight " + "a" * 12,
            "/vultr-readonly-preflight " + "A" * 40,
            f"/vultr-readonly-preflight {sha} extra",
        ):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    MODULE.parse_command(value)

    def test_selects_latest_exact_successful_acceptance_run(self):
        sha = "a" * 40
        older = self.acceptance_run(sha, 100)
        newer = self.acceptance_run(sha, 200)
        wrong_sha = self.acceptance_run("b" * 40, 300)
        failed = self.acceptance_run(sha, 400)
        failed["conclusion"] = "failure"
        selected = MODULE.select_acceptance_run(
            sha, {"workflow_runs": [older, wrong_sha, failed, newer]}
        )
        self.assertEqual(selected["id"], 200)

    def test_missing_or_noncanonical_acceptance_run_fails_closed(self):
        sha = "a" * 40
        with self.assertRaisesRegex(ValueError, "no successful"):
            MODULE.select_acceptance_run(sha, {"workflow_runs": []})
        wrong = self.acceptance_run(sha, 123)
        wrong["repository"] = {"full_name": "other/repo"}
        with self.assertRaisesRegex(ValueError, "no successful"):
            MODULE.select_acceptance_run(sha, {"workflow_runs": [wrong]})

    def test_acceptance_evidence_must_match_candidate_and_run(self):
        sha = "a" * 40
        run = self.acceptance_run(sha, 123)
        MODULE.verify_acceptance_evidence(sha, run, self.acceptance_evidence(sha, 123))
        mismatched = self.acceptance_evidence(sha, 123)
        mismatched["candidate_sha"] = "b" * 40
        with self.assertRaisesRegex(ValueError, "does not match"):
            MODULE.verify_acceptance_evidence(sha, run, mismatched)
        elevated = self.acceptance_evidence(sha, 123)
        elevated["final_production_authority"] = True
        with self.assertRaisesRegex(ValueError, "does not match"):
            MODULE.verify_acceptance_evidence(sha, run, elevated)

    def test_bounded_evidence_is_read_only_and_non_secret(self):
        evidence = MODULE.build_preflight_evidence("a" * 40, self.environment())
        self.assertEqual(evidence["authority"], "pre_release_acceptance_read_only")
        self.assertEqual(evidence["environment"], "acceptance-vultr")
        self.assertEqual(evidence["provider_api_method"], "GET")
        self.assertEqual(evidence["provider_api_path"], "/v2/account")
        self.assertEqual(evidence["provider_api_calls"], 1)
        self.assertTrue(evidence["account_endpoint_accessible"])
        self.assertFalse(evidence["account_response_body_recorded"])
        self.assertFalse(evidence["account_metadata_recorded"])
        self.assertFalse(evidence["secret_values_recorded"])
        self.assertFalse(evidence["secret_derived_identifiers_recorded"])
        self.assertFalse(evidence["vm_lifecycle_access_performed"])
        self.assertFalse(evidence["vm_mutation_performed"])
        self.assertFalse(evidence["phone_mutation_performed"])
        self.assertFalse(evidence["final_production_authority"])
        self.assertNotIn("VULTR_API_KEY", json.dumps(evidence))
        self.assertNotIn("VULTR_SSH_PRIVATE_KEY", json.dumps(evidence))

    def test_contract_and_workflow_lock_read_only_authority_separation(self):
        contract = json.loads(
            (ROOT / "contracts/operations/vultr-readonly-preflight-v1.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(contract["execution"]["environment"], "acceptance-vultr")
        self.assertEqual(
            contract["authority_separation"]["production_environment_name"],
            "production-vultr",
        )
        self.assertTrue(contract["authority_separation"]["environments_must_differ"])
        self.assertFalse(contract["authority_separation"]["final_production_authority"])
        self.assertEqual(contract["provider_probe"]["method"], "GET")
        self.assertEqual(contract["provider_probe"]["url"], "https://api.vultr.com/v2/account")
        self.assertEqual(contract["provider_probe"]["allowed_api_calls"], 1)
        self.assertEqual(contract["provider_probe"]["vm_lifecycle"], "forbidden")
        self.assertEqual(contract["provider_probe"]["provider_mutation"], "forbidden")

        workflow = (ROOT / ".github/workflows/vultr-readonly-preflight.yml").read_text(
            encoding="utf-8"
        )
        for required in (
            "runs-on: ubuntu-latest",
            "environment: acceptance-vultr",
            "--request GET",
            "--output /dev/null",
            "https://api.vultr.com/v2/account",
            "vultr-acceptance-authority-",
            "verify_vultr_readonly_preflight.py",
        ):
            self.assertIn(required, workflow)
        for forbidden in (
            "environment: production-vultr",
            "/v2/instances",
            "/v2/snapshots",
            "--request POST",
            "--request PUT",
            "--request PATCH",
            "--request DELETE",
            "runs-on: self-hosted",
            "adb ",
            "gcloud",
        ):
            self.assertNotIn(forbidden, workflow)


if __name__ == "__main__":
    unittest.main()
