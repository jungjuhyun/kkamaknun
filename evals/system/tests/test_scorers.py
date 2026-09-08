import unittest

from evals.system.schema import (
    AssertionSpec,
    EvidenceRecord,
    EvidenceState,
    ResultStatus,
    Target,
)
from evals.system.scorers import GRADERS, grade_assertion


PASS_FAIL_CASES = {
    "equals": ("x", "y", {"expected": "x"}),
    "boolean_true": (True, False, {}),
    "forbidden_tokens": ("clean", "contains stale", {"tokens": ["stale"]}),
    "required_tokens": ("has marker", "empty", {"tokens": ["marker"]}),
    "sha_consistency": (["a", "a"], ["a", "b"], {"expected": "a"}),
    "owner_consistency": (["a", "a"], ["a", "b"], {"expected": "a"}),
    "fallback_result": (
        {"first_path_failed": True, "fallback_attempted": True, "fallback_succeeded": True, "declared_globally_unavailable": False},
        {"first_path_failed": True, "fallback_attempted": False, "fallback_succeeded": False, "declared_globally_unavailable": True},
        {},
    ),
    "bootstrap_receipt": (
        {"receipt_emitted": True, "required_owner_evidence": True, "freshness_verified": True},
        {"receipt_emitted": True, "required_owner_evidence": False, "freshness_verified": False},
        {},
    ),
    "freshness": (
        {"start_sha": "a", "final_sha": "a"},
        {"start_sha": "a", "final_sha": "b"},
        {"expected_sha": "a"},
    ),
    "git_branch": ("feature", "main", {"expected": "feature"}),
    "git_head": ("a", "b", {"expected": "a"}),
    "git_diff": ({"dirty": False}, {"dirty": True}, {"dirty": False}),
    "modified_files": (["allowed"], ["forbidden"], {"allowed": ["allowed"], "forbidden": ["forbidden"]}),
    "main_mutation": (False, True, {}),
    "validator_result": ({"exit_code": 0, "result": "PASS"}, {"exit_code": 1, "result": "FAIL"}, {}),
    "artifact_residue": ([], ["leftover"], {}),
    "source_provenance": (
        {"used_sources": ["current"], "unlabeled_historical_sources": [], "historical_sources_labeled": False},
        {"used_sources": ["history"], "unlabeled_historical_sources": ["history"], "historical_sources_labeled": False},
        {"required_sources": ["current"]},
    ),
    "forbidden_values": (["current"], ["history"], {"values": ["history"]}),
    "required_values": (["current", "history"], ["current"], {"values": ["history"]}),
}


class DeterministicScorerTests(unittest.TestCase):
    def assertion(self, method, parameters):
        return AssertionSpec(
            id=f"assert-{method}",
            target=Target.DIRECT_COMPONENT,
            evidence_source="evidence",
            required_for_pass=True,
            evaluation_method=method,
            on_missing_evidence=ResultStatus.UNKNOWN,
            parameters=parameters,
        )

    def test_every_registered_grader_has_proof_inputs(self):
        self.assertEqual(set(GRADERS), set(PASS_FAIL_CASES))

    def test_each_grader_distinguishes_pass_and_fail(self):
        for method, (passing, failing, parameters) in PASS_FAIL_CASES.items():
            with self.subTest(method=method, case="pass"):
                result = grade_assertion(
                    self.assertion(method, parameters),
                    Target.DIRECT_COMPONENT,
                    {"evidence": EvidenceRecord("evidence", Target.DIRECT_COMPONENT, EvidenceState.AVAILABLE, passing)},
                )
                self.assertEqual(result.status, ResultStatus.PASS)
            with self.subTest(method=method, case="fail"):
                result = grade_assertion(
                    self.assertion(method, parameters),
                    Target.DIRECT_COMPONENT,
                    {"evidence": EvidenceRecord("evidence", Target.DIRECT_COMPONENT, EvidenceState.AVAILABLE, failing)},
                )
                self.assertEqual(result.status, ResultStatus.FAIL)

    def test_each_grader_maps_missing_to_unknown(self):
        for method, (_, _, parameters) in PASS_FAIL_CASES.items():
            with self.subTest(method=method):
                result = grade_assertion(
                    self.assertion(method, parameters), Target.DIRECT_COMPONENT, {}
                )
                self.assertEqual(result.status, ResultStatus.UNKNOWN)

    def test_each_grader_rejects_cross_target_evidence(self):
        for method, (passing, _, parameters) in PASS_FAIL_CASES.items():
            with self.subTest(method=method):
                result = grade_assertion(
                    self.assertion(method, parameters),
                    Target.DIRECT_COMPONENT,
                    {"evidence": EvidenceRecord("evidence", Target.ACTUAL_WORK, EvidenceState.AVAILABLE, passing)},
                )
                self.assertEqual(result.status, ResultStatus.INVALID_FIXTURE)

    def test_each_grader_keeps_infra_error_separate(self):
        for method, (_, _, parameters) in PASS_FAIL_CASES.items():
            with self.subTest(method=method):
                result = grade_assertion(
                    self.assertion(method, parameters),
                    Target.DIRECT_COMPONENT,
                    {"evidence": EvidenceRecord("evidence", Target.DIRECT_COMPONENT, EvidenceState.INFRA_ERROR)},
                )
                self.assertEqual(result.status, ResultStatus.INFRA_ERROR)

    def test_correct_response_does_not_prove_internal_process(self):
        assertion = AssertionSpec(
            id="tool-used",
            target=Target.ACTUAL_WORK,
            evidence_source="tool_trace",
            required_for_pass=True,
            evaluation_method="required_values",
            on_missing_evidence=ResultStatus.UNKNOWN,
            parameters={"values": ["github"]},
        )
        evidence = {
            "response_text": EvidenceRecord(
                "response_text", Target.ACTUAL_WORK, EvidenceState.AVAILABLE, "GitHub checked"
            )
        }
        result = grade_assertion(assertion, Target.ACTUAL_WORK, evidence)
        self.assertEqual(result.status, ResultStatus.UNKNOWN)


if __name__ == "__main__":
    unittest.main()
