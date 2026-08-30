import importlib.util
import pathlib
import unittest


MODULE_PATH = pathlib.Path(__file__).parents[1] / "verify_acceptance_candidate.py"
SPEC = importlib.util.spec_from_file_location("acceptance_candidate", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class AcceptanceCandidateTests(unittest.TestCase):
    def candidate_sha(self):
        return "a" * 40

    def quality_run(self, **overrides):
        run = {
            "id": 123456,
            "run_attempt": 1,
            "name": "Quality",
            "path": ".github/workflows/quality.yml",
            "event": "push",
            "head_branch": "main",
            "head_sha": self.candidate_sha(),
            "status": "completed",
            "conclusion": "success",
            "repository": {"full_name": "iamaman11/mobile-proxy"},
        }
        run.update(overrides)
        return run

    def candidate_evidence(self, **overrides):
        evidence = {
            "format_version": 2,
            "candidate_sha": self.candidate_sha(),
            "repository": "iamaman11/mobile-proxy",
            "workflow": "Quality",
            "workflow_run_id": "123456",
            "workflow_run_attempt": "1",
            "workflow_event": "push",
            "workflow_url": "https://github.com/iamaman11/mobile-proxy/actions/runs/123456",
            "git_worktree_clean": True,
            "software_10_of_10_ready": True,
            "physical_phone_acceptance_required": True,
            "baseline_complete": False,
            "accepted_checks": ["workspace_tests"],
        }
        evidence.update(overrides)
        return evidence

    def environment(self):
        return {
            "GITHUB_REPOSITORY": "iamaman11/mobile-proxy",
            "GITHUB_WORKFLOW": "Vultr acceptance authority",
            "GITHUB_RUN_ID": "789012",
            "GITHUB_RUN_ATTEMPT": "1",
            "COMMAND_COMMENT_ID": "345678",
        }

    def test_exact_command_accepts_only_full_candidate_sha(self):
        sha = self.candidate_sha()
        self.assertEqual(MODULE.parse_command(f"/accept-candidate {sha}"), sha)
        self.assertEqual(MODULE.parse_command(f"/accept-candidate {sha}\n"), sha)

    def test_mutable_approximate_and_malformed_identities_fail_closed(self):
        rejected = [
            "/accept-candidate main",
            "/accept-candidate latest",
            "/accept-candidate feature/item16",
            "/accept-candidate abcdef1",
            "/accept-candidate " + "A" * 40,
            "/accept-candidate " + "a" * 39,
            "/accept-candidate " + "a" * 41,
            "/accept-candidate " + "a" * 40 + " extra",
            " /accept-candidate " + "a" * 40,
            "/accept-candidate " + "a" * 40 + "\nextra",
        ]
        for body in rejected:
            with self.subTest(body=body):
                with self.assertRaises(ValueError):
                    MODULE.parse_command(body)

    def test_selects_exact_successful_main_push_quality_run(self):
        selected = MODULE.select_quality_run(
            self.candidate_sha(), {"workflow_runs": [self.quality_run()]}
        )
        self.assertEqual(selected["id"], 123456)

    def test_unknown_sha_and_wrong_quality_evidence_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "exactly one"):
            MODULE.select_quality_run(self.candidate_sha(), {"workflow_runs": []})

        wrong_event = self.quality_run(event="pull_request")
        with self.assertRaisesRegex(ValueError, "exactly one"):
            MODULE.select_quality_run(
                self.candidate_sha(), {"workflow_runs": [wrong_event]}
            )

        wrong_sha = self.quality_run(head_sha="b" * 40)
        with self.assertRaisesRegex(ValueError, "exactly one"):
            MODULE.select_quality_run(
                self.candidate_sha(), {"workflow_runs": [wrong_sha]}
            )

    def test_ambiguous_quality_runs_fail_closed(self):
        duplicate = self.quality_run(id=654321)
        with self.assertRaisesRegex(ValueError, "exactly one"):
            MODULE.select_quality_run(
                self.candidate_sha(),
                {"workflow_runs": [self.quality_run(), duplicate]},
            )

    def test_matching_release_candidate_evidence_is_accepted(self):
        MODULE.verify_candidate_evidence(
            self.candidate_sha(), self.quality_run(), self.candidate_evidence()
        )

    def test_missing_or_mismatched_candidate_evidence_fails_closed(self):
        for evidence in [
            {},
            self.candidate_evidence(candidate_sha="b" * 40),
            self.candidate_evidence(workflow_run_id="999999"),
            self.candidate_evidence(workflow_event="workflow_dispatch"),
            self.candidate_evidence(software_10_of_10_ready=False),
            self.candidate_evidence(accepted_checks=[]),
        ]:
            with self.subTest(evidence=evidence):
                with self.assertRaises(ValueError):
                    MODULE.verify_candidate_evidence(
                        self.candidate_sha(), self.quality_run(), evidence
                    )

    def test_acceptance_evidence_is_bounded_and_not_production_authority(self):
        evidence = MODULE.build_acceptance_evidence(
            self.candidate_sha(),
            self.quality_run(),
            "f" * 64,
            self.environment(),
        )
        self.assertEqual(evidence["authority"], "pre_release_acceptance")
        self.assertEqual(evidence["candidate_sha"], self.candidate_sha())
        self.assertEqual(evidence["executor"], "github-hosted")
        self.assertFalse(evidence["final_production_authority"])
        self.assertFalse(evidence["production_environment_authorized"])
        self.assertFalse(evidence["final_release_tag_created"])
        self.assertFalse(evidence["vultr_api_access_performed"])
        self.assertFalse(evidence["vm_mutation_performed"])
        self.assertFalse(evidence["phone_mutation_performed"])
        self.assertNotIn("VULTR_API_KEY", str(evidence))
        self.assertNotIn("VULTR_SSH_PRIVATE_KEY", str(evidence))


if __name__ == "__main__":
    unittest.main()
