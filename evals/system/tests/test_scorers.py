import unittest

from evals.system.schema import (
    AssertionSpec,
    Criticality,
    EvidenceRecord,
    EvidenceState,
    IsolationProfileName,
    ResultStatus,
    SchemaError,
    Suite,
    Target,
    TaskSpec,
)
from evals.system.scorers import GRADERS, grade_assertion, grade_trial, validate_grader_parameters


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
        {"bootstrap_succeeded": True, "receipt_emitted": True, "required_owner_evidence": True, "freshness_verified": True},
        {"bootstrap_succeeded": True, "receipt_emitted": False, "required_owner_evidence": True, "freshness_verified": True},
        {"contract": "required_on_success"},
    ),
    "freshness": (
        {"start_sha": "a", "final_sha": "a"},
        {"start_sha": "a", "final_sha": "b"},
        {"expected_sha": "a"},
    ),
    "git_branch": ("feature", "main", {"expected": "feature"}),
    "git_head": ("a", "b", {"expected": "a"}),
    "git_diff": ({"dirty": False}, {"dirty": True}, {"dirty": False}),
    "modified_files": (["allowed"], ["forbidden"], {"mode": "allowlist", "allowed": ["allowed"], "forbidden": ["forbidden"]}),
    "main_mutation": (False, True, {}),
    "validator_result": ({"exit_code": 0, "result": "PASS"}, {"exit_code": 1, "result": "FAIL"}, {"exit_code": 0, "result": "PASS"}),
    "artifact_residue": ([], ["leftover"], {}),
    "source_provenance": (
        {"used_sources": ["current"], "unlabeled_historical_sources": [], "historical_sources_labeled": False},
        {"used_sources": ["history"], "unlabeled_historical_sources": ["history"], "historical_sources_labeled": False},
        {"required_sources": ["current"]},
    ),
    "forbidden_values": (["current"], ["history"], {"values": ["history"]}),
    "required_values": (["current", "history"], ["current"], {"values": ["history"]}),
}


MALFORMED_PARAMETERS = {
    "equals": {},
    "boolean_true": {"unexpected": True},
    "forbidden_tokens": {"tokens": []},
    "required_tokens": {"tokens": []},
    "sha_consistency": {},
    "owner_consistency": {},
    "fallback_result": {"unexpected": True},
    "bootstrap_receipt": {"contract": "implicit"},
    "freshness": {},
    "git_branch": {},
    "git_head": {},
    "git_diff": {},
    "modified_files": {"mode": "forbid_only", "allowed": [], "forbidden": []},
    "main_mutation": {"unexpected": True},
    "validator_result": {"exit_code": 0},
    "artifact_residue": {"unexpected": True},
    "source_provenance": {"required_sources": []},
    "forbidden_values": {"values": []},
    "required_values": {"values": []},
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
        self.assertEqual(set(GRADERS), set(MALFORMED_PARAMETERS))

    def test_each_grader_rejects_malformed_parameters(self):
        for method, parameters in MALFORMED_PARAMETERS.items():
            with self.subTest(method=method):
                with self.assertRaises(SchemaError):
                    validate_grader_parameters(method, parameters)
                passing = PASS_FAIL_CASES[method][0]
                result = grade_assertion(
                    self.assertion(method, parameters),
                    Target.DIRECT_COMPONENT,
                    {"evidence": EvidenceRecord("evidence", Target.DIRECT_COMPONENT, EvidenceState.AVAILABLE, passing)},
                )
                self.assertEqual(result.status, ResultStatus.INVALID_FIXTURE)

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

    def test_bootstrap_receipt_contracts_are_explicit(self):
        success = self.assertion("bootstrap_receipt", {"contract": "required_on_success"})
        cases = (
            ({"bootstrap_succeeded": True, "receipt_emitted": True, "required_owner_evidence": True, "freshness_verified": True}, ResultStatus.PASS),
            ({"bootstrap_succeeded": True, "receipt_emitted": False, "required_owner_evidence": True, "freshness_verified": True}, ResultStatus.FAIL),
            ({"bootstrap_succeeded": True, "receipt_emitted": True, "required_owner_evidence": False, "freshness_verified": True}, ResultStatus.FAIL),
        )
        for value, expected in cases:
            with self.subTest(value=value):
                result = grade_assertion(
                    success,
                    Target.DIRECT_COMPONENT,
                    {"evidence": EvidenceRecord("evidence", Target.DIRECT_COMPONENT, EvidenceState.AVAILABLE, value)},
                )
                self.assertEqual(result.status, expected)

        failure = self.assertion("bootstrap_receipt", {"contract": "forbidden_on_failure"})
        result = grade_assertion(
            failure,
            Target.DIRECT_COMPONENT,
            {"evidence": EvidenceRecord(
                "evidence",
                Target.DIRECT_COMPONENT,
                EvidenceState.AVAILABLE,
                {"bootstrap_succeeded": False, "receipt_emitted": False},
            )},
        )
        self.assertEqual(result.status, ResultStatus.PASS)
        result = grade_assertion(
            failure,
            Target.DIRECT_COMPONENT,
            {"evidence": EvidenceRecord(
                "evidence",
                Target.DIRECT_COMPONENT,
                EvidenceState.AVAILABLE,
                {"bootstrap_succeeded": False, "receipt_emitted": True},
            )},
        )
        self.assertEqual(result.status, ResultStatus.FAIL)


class TrialAggregationTests(unittest.TestCase):
    def task(self, optional_method="boolean_true"):
        return TaskSpec(
            id="trial-aggregation",
            suite=Suite.REGRESSION,
            target=Target.DIRECT_COMPONENT,
            risk_surface=["measurement_integrity"],
            criticality=Criticality.NON_CRITICAL,
            setup=["controlled"],
            precondition=["controlled"],
            user_input="test",
            expected_observable_behavior=["valid aggregation"],
            forbidden_observable_behavior=["invalid pass"],
            assertions=[
                AssertionSpec("required", Target.DIRECT_COMPONENT, "required", True, "boolean_true", ResultStatus.UNKNOWN, {}),
                AssertionSpec("optional", Target.DIRECT_COMPONENT, "optional", False, optional_method, ResultStatus.UNKNOWN, {}),
            ],
            trial_count=1,
            isolation_profile=IsolationProfileName.CONTROLLED_MOCK_ACCESS,
            required_evidence=["required"],
            optional_evidence=["optional"],
            snapshot_expectation={},
        )

    def test_optional_invalid_fixture_invalidates_trial(self):
        task = self.task()
        result = grade_trial(task, [
            EvidenceRecord("required", Target.DIRECT_COMPONENT, EvidenceState.AVAILABLE, True),
            EvidenceRecord("optional", Target.ACTUAL_WORK, EvidenceState.AVAILABLE, True),
        ])
        self.assertEqual(result.status, ResultStatus.INVALID_FIXTURE)

    def test_optional_fail_unknown_and_infra_are_diagnostic(self):
        cases = (
            (EvidenceRecord("optional", Target.DIRECT_COMPONENT, EvidenceState.AVAILABLE, False), ResultStatus.FAIL),
            (EvidenceRecord("optional", Target.DIRECT_COMPONENT, EvidenceState.MISSING), ResultStatus.UNKNOWN),
            (EvidenceRecord("optional", Target.DIRECT_COMPONENT, EvidenceState.INFRA_ERROR), ResultStatus.INFRA_ERROR),
        )
        for optional, assertion_status in cases:
            with self.subTest(assertion_status=assertion_status):
                result = grade_trial(self.task(), [
                    EvidenceRecord("required", Target.DIRECT_COMPONENT, EvidenceState.AVAILABLE, True),
                    optional,
                ])
                self.assertEqual(result.status, ResultStatus.PASS)
                self.assertEqual(result.assertions[1].status, assertion_status)


if __name__ == "__main__":
    unittest.main()
