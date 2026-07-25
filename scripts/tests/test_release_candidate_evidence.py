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

    def test_evidence_is_bounded_native_and_bound_to_checked_out_sha(self):
        evidence = MODULE.build_evidence(self.environment(), "a" * 40, True)
        self.assertEqual(evidence["format_version"], 2)
        self.assertEqual(evidence["candidate_sha"], "a" * 40)
        self.assertTrue(evidence["git_worktree_clean"])
        self.assertEqual(evidence["primary_runtime"], "first_party_reverse_tunnel")
        self.assertFalse(evidence["primary_runtime_requires_android_vpn"])
        self.assertEqual(evidence["rollback_runtime"], "stock_wireguard_bridge")
        self.assertTrue(evidence["software_10_of_10_ready"])
        self.assertTrue(evidence["physical_phone_acceptance_required"])
        self.assertFalse(evidence["baseline_complete"])
        for check in [
            "native_reverse_tunnel_default",
            "multi_language_digest_policy",
            "typed_blake3_release_integrity",
            "exact_device_deployment_bytes",
            "rustsec_advisory_audit",
            "dependency_license_bans_sources",
            "android_unit_tests",
            "android_lint",
            "android_debug_build",
            "quic_forced_fallback",
            "sqlite_clean_environment_restore",
        ]:
            self.assertIn(check, evidence["accepted_checks"])
        self.assertNotIn("secret", str(evidence).lower())

    def test_mismatched_checkout_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "does not match"):
            MODULE.build_evidence(self.environment(), "b" * 40, True)

    def test_dirty_checkout_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "not clean"):
            MODULE.build_evidence(self.environment(), "a" * 40, False)

    def test_unaccepted_event_or_unbounded_workflow_is_rejected(self):
        environment = self.environment()
        environment["GITHUB_EVENT_NAME"] = "schedule"
        with self.assertRaisesRegex(ValueError, "not accepted"):
            MODULE.build_evidence(environment, "a" * 40, True)

        environment = self.environment()
        environment["GITHUB_WORKFLOW"] = "x" * 129
        with self.assertRaisesRegex(ValueError, "GITHUB_WORKFLOW"):
            MODULE.build_evidence(environment, "a" * 40, True)

    def test_sha_and_repository_identifiers_are_strict(self):
        environment = self.environment()
        environment["CANDIDATE_SHA"] = "A" * 40
        with self.assertRaisesRegex(ValueError, "lowercase"):
            MODULE.build_evidence(environment, "A" * 40, True)

        environment = self.environment()
        environment["GITHUB_REPOSITORY"] = "invalid repository"
        with self.assertRaisesRegex(ValueError, "invalid"):
            MODULE.build_evidence(environment, "a" * 40, True)


if __name__ == "__main__":
    unittest.main()
