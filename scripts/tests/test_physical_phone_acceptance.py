import importlib.util
import pathlib
import unittest
from unittest import mock


MODULE_PATH = pathlib.Path(__file__).parents[1] / "run_physical_phone_acceptance.py"
SPEC = importlib.util.spec_from_file_location("physical_phone_acceptance", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class PhysicalPhoneAcceptanceTests(unittest.TestCase):
    def evidence(self):
        return {
            "format_version": 2,
            "repository": "iamaman11/mobile-proxy",
            "workflow": "Software Release Candidate",
            "candidate_sha": "a" * 40,
            "primary_runtime": "first_party_reverse_tunnel",
            "primary_runtime_requires_android_vpn": False,
            "rollback_runtime": "stock_wireguard_bridge",
            "software_10_of_10_ready": True,
            "physical_phone_acceptance_required": True,
            "baseline_complete": False,
            "accepted_checks": sorted(MODULE._REQUIRED_SOFTWARE_CHECKS),
        }

    @mock.patch.object(MODULE, "git_output")
    def test_candidate_must_match_a_clean_checkout(self, git_output):
        git_output.side_effect = ["a" * 40, ""]
        self.assertEqual(MODULE.verify_candidate(self.evidence()), "a" * 40)

        git_output.side_effect = ["b" * 40]
        with self.assertRaisesRegex(MODULE.AcceptanceFailure, "differs"):
            MODULE.verify_candidate(self.evidence())

    @mock.patch.object(MODULE, "curl_proxy")
    def test_proxy_sequence_covers_all_authenticated_protocols(self, curl_proxy):
        result = MODULE.prove_proxy_surfaces(
            "proxy.example",
            "http://probe.example/",
            "https://probe.example/",
            "user:password",
        )
        self.assertEqual(curl_proxy.call_count, 6)
        for call in curl_proxy.call_args_list:
            self.assertEqual(call.args[1], "user:password")
            self.assertNotIn("--proxy-user", call.args[0])
        self.assertEqual(
            result,
            {
                "mixed_1080_socks5": True,
                "mixed_1080_http": True,
                "mixed_1080_connect": True,
                "socks5_1081": True,
                "http_3128": True,
                "http_connect_3128": True,
            },
        )

    @mock.patch.object(MODULE.subprocess, "run")
    def test_curl_uses_stdin_credentials_and_disables_no_proxy(self, run):
        MODULE.curl_proxy(["--proxy", "http://proxy.example:3128", "https://probe/"], "u:p")
        command = run.call_args.args[0]
        self.assertNotIn("u:p", command)
        self.assertIn("--noproxy", command)
        self.assertIn("--config", command)
        self.assertIn('proxy-user = "u:p"', run.call_args.kwargs["input"])
        self.assertEqual(run.call_args.kwargs["env"]["NO_PROXY"], "")
        self.assertEqual(run.call_args.kwargs["env"]["no_proxy"], "")

    def test_incomplete_invalid_wrong_runtime_or_wrong_source_evidence_fails_closed(self):
        evidence = self.evidence()
        evidence["software_10_of_10_ready"] = False
        with self.assertRaisesRegex(MODULE.AcceptanceFailure, "not 10/10-ready"):
            MODULE.verify_candidate(evidence)

        evidence = self.evidence()
        evidence["candidate_sha"] = "not-a-sha"
        with self.assertRaisesRegex(MODULE.AcceptanceFailure, "invalid SHA"):
            MODULE.verify_candidate(evidence)

        evidence = self.evidence()
        evidence["repository"] = "someone/else"
        with self.assertRaisesRegex(MODULE.AcceptanceFailure, "repository differs"):
            MODULE.verify_candidate(evidence)

        evidence = self.evidence()
        evidence["primary_runtime_requires_android_vpn"] = True
        with self.assertRaisesRegex(MODULE.AcceptanceFailure, "incorrectly requires"):
            MODULE.verify_candidate(evidence)

        evidence = self.evidence()
        evidence["baseline_complete"] = True
        with self.assertRaisesRegex(MODULE.AcceptanceFailure, "falsely declares"):
            MODULE.verify_candidate(evidence)

        evidence = self.evidence()
        evidence["accepted_checks"].remove("quic_recovery")
        with self.assertRaisesRegex(MODULE.AcceptanceFailure, "missing required"):
            MODULE.verify_candidate(evidence)

        evidence = self.evidence()
        evidence["accepted_checks"].append(evidence["accepted_checks"][0])
        with self.assertRaisesRegex(MODULE.AcceptanceFailure, "duplicate"):
            MODULE.verify_candidate(evidence)

    def test_non_object_health_response_is_rejected_cleanly(self):
        with self.assertRaisesRegex(MODULE.AcceptanceFailure, "response is invalid"):
            MODULE.require_object([], "host readiness")

    @mock.patch.dict("os.environ", {"PROXY_PASSWORD": "secret-value"}, clear=True)
    def test_secret_validation_does_not_echo_secret(self):
        self.assertEqual(MODULE._required_environment("PROXY_PASSWORD"), "secret-value")
        with self.assertRaisesRegex(MODULE.AcceptanceFailure, "MISSING") as caught:
            MODULE._required_environment("MISSING")
        self.assertNotIn("secret-value", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
