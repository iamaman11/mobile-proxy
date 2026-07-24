import importlib.util
import pathlib
import unittest


MODULE_PATH = pathlib.Path(__file__).parents[1] / "write_release_candidate_evidence.py"
SPEC = importlib.util.spec_from_file_location("release_candidate_evidence", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class ReleaseCandidateEvidenceTests(unittest.TestCase):
    def environment(self):
        return {
            "CANDIDATE_SHA": "a" * 40,
            "GITHUB_REPOSITORY": "iamaman11/mobile-proxy",
            "GITHUB_EVENT_NAME": "pull_request",
            "GITHUB_WORKFLOW": "Software Release Candidate",
            "GITHUB_RUN_ID": "123456",
            "GITHUB_RUN_ATTEMPT": "1",
        }

    def test_evidence_is_bounded_and_bound_to_checked_out_sha(self):
        evidence = MODULE.build_evidence(self.environment(), "a" * 40)
        self.assertEqual(evidence["candidate_sha"], "a" * 40)
        self.assertTrue(evidence["software_complete"])
        self.assertTrue(evidence["physical_phone_acceptance_required"])
        self.assertIn("quic_forced_fallback", evidence["accepted_checks"])
        self.assertIn("sqlite_clean_environment_restore", evidence["accepted_checks"])
        self.assertNotIn("secret", str(evidence).lower())

    def test_mismatched_checkout_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "does not match"):
            MODULE.build_evidence(self.environment(), "b" * 40)

    def test_unaccepted_event_or_unbounded_workflow_is_rejected(self):
        environment = self.environment()
        environment["GITHUB_EVENT_NAME"] = "schedule"
        with self.assertRaisesRegex(ValueError, "not accepted"):
            MODULE.build_evidence(environment, "a" * 40)

        environment = self.environment()
        environment["GITHUB_WORKFLOW"] = "x" * 129
        with self.assertRaisesRegex(ValueError, "GITHUB_WORKFLOW"):
            MODULE.build_evidence(environment, "a" * 40)


if __name__ == "__main__":
    unittest.main()
