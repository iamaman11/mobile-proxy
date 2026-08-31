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
POLICY_SCRIPT = Path(__file__).resolve().parents[1] / "check_vultr_readonly_preflight_policy.py"
POLICY_SPEC = importlib.util.spec_from_file_location("vultr_readonly_policy", POLICY_SCRIPT)
assert POLICY_SPEC is not None and POLICY_SPEC.loader is not None
POLICY = importlib.util.module_from_spec(POLICY_SPEC)
POLICY_SPEC.loader.exec_module(POLICY)


class VultrReadonlyPreflightTests(unittest.TestCase):
    candidate_sha = "a" * 40
    control_plane_sha = "c" * 40

    def acceptance_run(self, control_plane_sha=None, run_id=123):
        sha = control_plane_sha or self.control_plane_sha
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

    def acceptance_artifact(
        self,
        candidate_sha=None,
        control_plane_sha=None,
        artifact_id=500,
        run_id=123,
        created_at="2026-08-31T12:00:00Z",
    ):
        candidate = candidate_sha or self.candidate_sha
        control = control_plane_sha or self.control_plane_sha
        return {
            "id": artifact_id,
            "name": f"vultr-acceptance-authority-{candidate}",
            "size_in_bytes": 321,
            "expired": False,
            "digest": "sha256:" + "d" * 64,
            "created_at": created_at,
            "workflow_run": {
                "id": run_id,
                "head_branch": "main",
                "head_sha": control,
            },
        }

    def acceptance_evidence(self, candidate_sha=None, run_id=123):
        sha = candidate_sha or self.candidate_sha
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
        sha = self.candidate_sha
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

    def test_selects_latest_candidate_artifact_on_exact_control_plane(self):
        older = self.acceptance_artifact(artifact_id=100, run_id=10, created_at="2026-08-31T10:00:00Z")
        newer = self.acceptance_artifact(artifact_id=200, run_id=20, created_at="2026-08-31T11:00:00Z")
        wrong_candidate = self.acceptance_artifact(candidate_sha="b" * 40, artifact_id=300, run_id=30)
        wrong_control = self.acceptance_artifact(control_plane_sha="e" * 40, artifact_id=400, run_id=40)
        selected = MODULE.select_acceptance_artifact(
            self.candidate_sha,
            self.control_plane_sha,
            {"artifacts": [older, wrong_candidate, wrong_control, newer]},
        )
        self.assertEqual(selected["id"], 200)
        self.assertEqual(selected["workflow_run"]["id"], 20)

    def test_selector_separates_roles_without_requiring_different_sha_values(self):
        artifact = self.acceptance_artifact(
            candidate_sha=self.candidate_sha,
            control_plane_sha=self.candidate_sha,
            artifact_id=700,
            run_id=70,
        )
        selected = MODULE.select_acceptance_artifact(
            self.candidate_sha,
            self.candidate_sha,
            {"artifacts": [artifact]},
        )
        self.assertEqual(selected["id"], 700)
        self.assertEqual(selected["workflow_run"]["head_sha"], self.candidate_sha)

    def test_missing_expired_or_invalid_digest_artifact_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "no unexpired"):
            MODULE.select_acceptance_artifact(
                self.candidate_sha, self.control_plane_sha, {"artifacts": []}
            )
        expired = self.acceptance_artifact()
        expired["expired"] = True
        with self.assertRaisesRegex(ValueError, "no unexpired"):
            MODULE.select_acceptance_artifact(
                self.candidate_sha, self.control_plane_sha, {"artifacts": [expired]}
            )
        missing_digest = self.acceptance_artifact()
        missing_digest["digest"] = None
        with self.assertRaisesRegex(ValueError, "no unexpired"):
            MODULE.select_acceptance_artifact(
                self.candidate_sha, self.control_plane_sha, {"artifacts": [missing_digest]}
            )

    def test_exact_artifact_run_must_match_current_control_plane(self):
        artifact = self.acceptance_artifact(run_id=123)
        run = self.acceptance_run(run_id=123)
        MODULE.verify_acceptance_run(self.candidate_sha, self.control_plane_sha, artifact, run)

        wrong_head = self.acceptance_run(control_plane_sha="e" * 40, run_id=123)
        with self.assertRaisesRegex(ValueError, "exact artifact/control-plane"):
            MODULE.verify_acceptance_run(
                self.candidate_sha, self.control_plane_sha, artifact, wrong_head
            )

        wrong_run = self.acceptance_run(run_id=999)
        with self.assertRaisesRegex(ValueError, "exact artifact/control-plane"):
            MODULE.verify_acceptance_run(
                self.candidate_sha, self.control_plane_sha, artifact, wrong_run
            )

    def test_acceptance_evidence_must_match_candidate_and_exact_artifact_run(self):
        artifact = self.acceptance_artifact(run_id=123)
        run = self.acceptance_run(run_id=123)
        MODULE.verify_acceptance_evidence(
            self.candidate_sha,
            self.control_plane_sha,
            artifact,
            run,
            self.acceptance_evidence(run_id=123),
        )
        mismatched = self.acceptance_evidence(run_id=123)
        mismatched["candidate_sha"] = "b" * 40
        with self.assertRaisesRegex(ValueError, "does not match"):
            MODULE.verify_acceptance_evidence(
                self.candidate_sha, self.control_plane_sha, artifact, run, mismatched
            )
        elevated = self.acceptance_evidence(run_id=123)
        elevated["final_production_authority"] = True
        with self.assertRaisesRegex(ValueError, "does not match"):
            MODULE.verify_acceptance_evidence(
                self.candidate_sha, self.control_plane_sha, artifact, run, elevated
            )

    def test_bounded_evidence_is_read_only_and_non_secret(self):
        evidence = MODULE.build_preflight_evidence(self.candidate_sha, self.environment())
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

    def test_repository_policy_passes(self):
        self.assertEqual(POLICY.check_repository(ROOT), [])

    def test_contract_and_workflow_lock_artifact_first_read_only_selection(self):
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
        selection = contract["acceptance_evidence"]["selection"]
        self.assertEqual(
            selection["strategy"],
            "candidate_specific_artifact_then_exact_control_plane_run",
        )
        self.assertEqual(selection["required_artifact_run_head_sha"], "control_plane_sha")
        self.assertEqual(selection["candidate_identity_role"], "artifact_name_and_evidence_binding")
        self.assertEqual(selection["control_plane_identity_role"], "workflow_run_head_binding")
        self.assertTrue(selection["candidate_sha_must_not_select_run_head"])
        self.assertNotIn("candidate_sha_equals_control_plane_sha", selection)
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
            "actions/artifacts?name=vultr-acceptance-authority-$CANDIDATE_SHA&per_page=100",
            "actions/runs/$run_id",
            "actions/artifacts/$ACCEPTANCE_ARTIFACT_ID/zip",
            "select-artifact",
            '--control-plane-sha "$CONTROL_PLANE_SHA"',
            "--selected-artifact selected-acceptance-artifact.json",
            "--request GET",
            "--output /dev/null",
            "https://api.vultr.com/v2/account",
            "verify_vultr_readonly_preflight.py",
        ):
            self.assertIn(required, workflow)
        for forbidden in (
            "head_sha=$CANDIDATE_SHA",
            "select-run",
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
