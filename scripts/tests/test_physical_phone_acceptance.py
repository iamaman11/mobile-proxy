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
            "candidate_sha": "a" * 40,
            "software_complete": True,
            "physical_phone_acceptance_required": True,
        }

    @mock.patch.object(MODULE, "git_output")
    def test_candidate_must_match_a_clean_checkout(self, git_output):
        git_output.side_effect = ["a" * 40, ""]
        self.assertEqual(MODULE.verify_candidate(self.evidence()), "a" * 40)

        git_output.side_effect = ["b" * 40]
        with self.assertRaisesRegex(MODULE.AcceptanceFailure, "differs"):
            MODULE.verify_candidate(self.evidence())

    @mock.patch.object(MODULE, "curl_proxy")
    def test_proxy_sequence_covers_all_protected_surfaces(self, curl_proxy):
        result = MODULE.prove_proxy_surfaces(
            "proxy.example",
            "http://probe.example/",
            "https://probe.example/",
        )
        self.assertEqual(curl_proxy.call_count, 4)
        self.assertEqual(
            result,
            {
                "mixed_1080": True,
                "socks5_1081": True,
                "http_3128": True,
                "http_connect_3128": True,
            },
        )

    def test_incomplete_or_invalid_evidence_fails_closed(self):
        evidence = self.evidence()
        evidence["software_complete"] = False
        with self.assertRaisesRegex(MODULE.AcceptanceFailure, "not complete"):
            MODULE.verify_candidate(evidence)

        evidence = self.evidence()
        evidence["candidate_sha"] = "not-a-sha"
        with self.assertRaisesRegex(MODULE.AcceptanceFailure, "invalid SHA"):
            MODULE.verify_candidate(evidence)


if __name__ == "__main__":
    unittest.main()
