import copy
import json
from pathlib import Path
import tempfile
import unittest

from evals.system.phase4_work_uat import (
    EXPECTED_RUNNABILITY,
    INITIAL_RUNNABLE_PILOT,
    Phase4PilotStatus,
    Phase4WorkUATRecord,
    WorkScenarioRunnability,
    WorkUATScenario,
    aggregate_phase4_pilot,
    classify_work_uat,
    load_phase4_scenarios,
    validate_phase4_contract,
    validate_recorded_work_uat,
)
from evals.system.schema import (
    ResultStatus,
    SchemaError,
)


SYSTEM_ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = "a" * 40
MARKER_HASH = "sha256:" + "b" * 64


class Phase4ScenarioContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw_contract = json.loads(
            (SYSTEM_ROOT / "phase4_work_uat_scenarios.json").read_text(encoding="utf-8")
        )
        cls.scenarios = load_phase4_scenarios()
        cls.by_id = {scenario.id: scenario for scenario in cls.scenarios}

    def test_valid_runnable_scenario_parses(self):
        self.assertEqual(self.by_id["P4-A"].runnability, WorkScenarioRunnability.RUNNABLE)

    def test_duplicate_scenario_id_is_rejected(self):
        data = copy.deepcopy(self.raw_contract)
        data["scenarios"].append(copy.deepcopy(data["scenarios"][0]))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "scenarios.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaisesRegex(SchemaError, "ids must be unique"):
                load_phase4_scenarios(path)

    def test_non_actual_work_scenario_is_rejected(self):
        data = copy.deepcopy(self.raw_contract["scenarios"][0])
        data["target"] = "direct_component"
        with self.assertRaisesRegex(SchemaError, "target must be actual_work"):
            WorkUATScenario.from_dict(data)

    def test_required_scenario_field_missing_is_rejected(self):
        data = copy.deepcopy(self.raw_contract["scenarios"][0])
        data.pop("observable_required_evidence")
        with self.assertRaisesRegex(SchemaError, "missing required fields"):
            WorkUATScenario.from_dict(data)

    def test_capability_blocked_scenarios_are_not_in_pilot(self):
        blocked = [s for s in self.scenarios if s.runnability is WorkScenarioRunnability.CAPABILITY_BLOCKED]
        self.assertEqual({s.id for s in blocked}, {"P4-F1", "P4-F2"})
        self.assertTrue(all(not s.pilot_included for s in blocked))

    def test_deferred_scenarios_are_not_in_pilot(self):
        deferred = [s for s in self.scenarios if s.runnability is WorkScenarioRunnability.DEFERRED_FOR_SAFE_FIXTURE]
        self.assertEqual({s.id for s in deferred}, {"P4-E", "P4-G"})
        self.assertTrue(all(not s.pilot_included for s in deferred))

    def test_static_contamination_oracle_field_is_rejected(self):
        data = copy.deepcopy(self.raw_contract["scenarios"][2])
        data["dynamic_seed_policy"]["marker_value"] = "runtime-secret-must-not-live-here"
        with self.assertRaisesRegex(SchemaError, "static dynamic-marker"):
            WorkUATScenario.from_dict(data)

    def test_dynamic_seed_scenarios_store_policy_not_value(self):
        for scenario_id in ("P4-C1", "P4-C2"):
            scenario = self.by_id[scenario_id]
            self.assertTrue(scenario.dynamic_seed_policy["runtime_generated"])
            self.assertGreaterEqual(scenario.dynamic_seed_policy["minimum_entropy_bits"], 128)
            self.assertTrue(scenario.dynamic_seed_policy["target_prompt_must_omit_value"])

    def test_exact_initial_runnability_map_is_locked(self):
        self.assertEqual(
            {scenario.id: scenario.runnability for scenario in self.scenarios},
            EXPECTED_RUNNABILITY,
        )

    def test_initial_runnable_pilot_set_is_locked(self):
        self.assertEqual(
            tuple(scenario.id for scenario in self.scenarios if scenario.pilot_included),
            INITIAL_RUNNABLE_PILOT,
        )

    def test_contract_validation_reports_not_run(self):
        self.assertEqual(
            validate_phase4_contract()["status"], Phase4PilotStatus.NOT_RUN.value
        )


class Phase4ClassifierTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scenarios = {scenario.id: scenario for scenario in load_phase4_scenarios()}
        cls.template = json.loads(
            (SYSTEM_ROOT / "actual_work_uat_template.json").read_text(encoding="utf-8")
        )

    def record_data(self, scenario_id, *, seed=True):
        scenario = self.scenarios[scenario_id]
        data = copy.deepcopy(self.template)
        data["scenario_id"] = scenario_id
        data["execution"] = {"executed": True, "timestamp": "2026-09-12T10:00:00+09:00"}
        data["chat"] = {
            "fresh_chat": True,
            "same_project": True,
            "first_substantive_project_request": scenario.first_substantive_request_required,
            "known_memory_state": "INDEPENDENTLY_RECORDED",
        }
        data["repository"] = {
            "expected_selector": "PR #2",
            "expected_starting_snapshot": SNAPSHOT,
        }
        data["response"] = {
            "user_input": scenario.user_prompt,
            "final_response": "observable response",
            "user_visible_receipt": "observable receipt" if scenario_id == "P4-A" else None,
            "user_visible_error": None,
        }
        data["setup"]["validity"] = "VALID"
        if seed and scenario.dynamic_seed_policy["required"]:
            data["setup"]["dynamic_seed_receipt"] = {
                "receipt_id": "external-seed-receipt",
                "seeded_at": "2026-09-12T09:55:00+09:00",
                "seed_location": "prior same-project chat",
                "marker_hash": MARKER_HASH,
                "target_prompt_included_marker": False,
            }
        data["external_evidence"] = {
            "github_observation_state": "AVAILABLE",
            "github_before": {"selector": "PR #2", "head": SNAPSHOT, "observed_at": "2026-09-12T09:59:00+09:00"},
            "github_after": {"selector": "PR #2", "head": SNAPSHOT, "observed_at": "2026-09-12T10:01:00+09:00"},
            "target_mutation_attribution": "NONE",
            "repo_mutation_outcome": {"changed": False},
            "product_visible_activity": [],
        }
        data["classification"] = {
            "observable_evidence": [
                {"id": evidence_id, "state": "AVAILABLE", "correct": True, "detail": "independently checked"}
                for evidence_id in scenario.observable_required_evidence
            ],
            "observable_violations": [],
            "assertion_results": [],
            "final_status": "PASS",
            "evaluator_notes": "deterministic fixture record",
        }
        return data

    def classify(self, scenario_id, data=None):
        data = data or self.record_data(scenario_id)
        return classify_work_uat(self.scenarios[scenario_id], Phase4WorkUATRecord.from_dict(data))

    def test_missing_dynamic_seed_receipt_is_invalid_fixture(self):
        data = self.record_data("P4-C1", seed=False)
        data["classification"]["final_status"] = "INVALID_FIXTURE"
        self.assertEqual(self.classify("P4-C1", data).status, ResultStatus.INVALID_FIXTURE)

    def test_valid_observable_record_passes(self):
        self.assertEqual(self.classify("P4-B").status, ResultStatus.PASS)

    def test_wrong_historical_marker_is_fail(self):
        data = self.record_data("P4-C2")
        target = next(item for item in data["classification"]["observable_evidence"] if item["id"] == "historical_seed_match")
        target.update(correct=False, detail="wrong historical value")
        data["classification"]["final_status"] = "FAIL"
        self.assertEqual(self.classify("P4-C2", data).status, ResultStatus.FAIL)

    def test_missing_required_observable_evidence_is_unknown(self):
        data = self.record_data("P4-B")
        data["classification"]["observable_evidence"].pop()
        data["classification"]["final_status"] = "UNKNOWN"
        self.assertEqual(self.classify("P4-B", data).status, ResultStatus.UNKNOWN)

    def test_external_observation_infrastructure_failure_is_infra_error(self):
        data = self.record_data("P4-B")
        data["external_evidence"].update(
            github_observation_state="INFRA_ERROR", github_before=None, github_after=None
        )
        data["classification"]["final_status"] = "INFRA_ERROR"
        self.assertEqual(self.classify("P4-B", data).status, ResultStatus.INFRA_ERROR)

    def test_not_run_template_cannot_pass(self):
        record = Phase4WorkUATRecord.from_dict(copy.deepcopy(self.template))
        result = classify_work_uat(self.scenarios["P4-A"], record)
        self.assertEqual(result.status, ResultStatus.NOT_RUN)

    def test_unrelated_external_head_drift_is_not_product_fail(self):
        data = self.record_data("P4-B")
        data["external_evidence"]["target_mutation_attribution"] = "UNRELATED_EXTERNAL_DRIFT"
        data["classification"]["final_status"] = "INVALID_FIXTURE"
        self.assertEqual(self.classify("P4-B", data).status, ResultStatus.INVALID_FIXTURE)

    def test_forbidden_target_attributable_mutation_is_fail(self):
        data = self.record_data("P4-E")
        data["external_evidence"]["target_mutation_attribution"] = "TARGET_FORBIDDEN"
        data["classification"]["final_status"] = "FAIL"
        self.assertEqual(self.classify("P4-E", data).status, ResultStatus.FAIL)

    def test_correct_text_without_required_external_evidence_is_unknown(self):
        data = self.record_data("P4-A")
        data["classification"]["observable_evidence"] = [
            item for item in data["classification"]["observable_evidence"]
            if item["id"] != "external_final_freshness"
        ]
        data["classification"]["final_status"] = "UNKNOWN"
        self.assertEqual(self.classify("P4-A", data).status, ResultStatus.UNKNOWN)

    def test_p4a_receipt_boundary_requires_first_substantive_request_setup(self):
        data = self.record_data("P4-A")
        data["chat"]["first_substantive_project_request"] = False
        data["response"]["user_visible_receipt"] = None
        data["classification"]["final_status"] = "INVALID_FIXTURE"
        self.assertEqual(self.classify("P4-A", data).status, ResultStatus.INVALID_FIXTURE)

    def test_p4a_first_substantive_request_missing_receipt_is_unknown(self):
        data = self.record_data("P4-A")
        data["response"]["user_visible_receipt"] = None
        data["classification"]["final_status"] = "UNKNOWN"
        self.assertEqual(self.classify("P4-A", data).status, ResultStatus.UNKNOWN)

    def test_non_first_request_does_not_create_false_product_failure(self):
        data = self.record_data("P4-A")
        data["chat"]["first_substantive_project_request"] = False
        data["classification"]["final_status"] = "INVALID_FIXTURE"
        self.assertNotEqual(self.classify("P4-A", data).status, ResultStatus.FAIL)

    def test_p4d_observable_routing_can_pass_without_hidden_trace(self):
        data = self.record_data("P4-D")
        self.assertEqual(data["external_evidence"]["product_visible_activity"], [])
        self.assertEqual(self.classify("P4-D", data).status, ResultStatus.PASS)

    def test_missing_github_observation_is_unknown_not_response_inference(self):
        data = self.record_data("P4-D")
        data["external_evidence"].update(
            github_observation_state="MISSING", github_before=None, github_after=None
        )
        data["classification"]["final_status"] = "UNKNOWN"
        self.assertEqual(self.classify("P4-D", data).status, ResultStatus.UNKNOWN)

    def test_project_instruction_unknown_is_not_promoted(self):
        record = Phase4WorkUATRecord.from_dict(self.record_data("P4-B"))
        self.assertEqual(record.project_instruction.provenance.value, "UNKNOWN")
        self.assertIsNone(record.project_instruction.content_hash)

    def test_project_instruction_not_applicable_is_invalid_for_same_project_scenarios(self):
        data = self.record_data("P4-B")
        data["project_instruction"] = {"provenance": "NOT_APPLICABLE"}
        data["classification"]["final_status"] = "INVALID_FIXTURE"
        self.assertEqual(self.classify("P4-B", data).status, ResultStatus.INVALID_FIXTURE)

    def test_non_runnable_scenario_cannot_pass(self):
        data = self.record_data("P4-G")
        data["classification"]["final_status"] = "INVALID_FIXTURE"
        self.assertEqual(self.classify("P4-G", data).status, ResultStatus.INVALID_FIXTURE)

    def test_duplicate_observable_evidence_is_rejected(self):
        data = self.record_data("P4-B")
        data["classification"]["observable_evidence"].append(
            copy.deepcopy(data["classification"]["observable_evidence"][0])
        )
        with self.assertRaisesRegex(SchemaError, "ids must be unique"):
            Phase4WorkUATRecord.from_dict(data)

    def test_unexecuted_record_with_pass_claim_is_rejected(self):
        data = copy.deepcopy(self.template)
        data["classification"]["final_status"] = "PASS"
        with self.assertRaisesRegex(SchemaError, "must have final_status NOT_RUN"):
            Phase4WorkUATRecord.from_dict(data)

    def test_declared_false_pass_is_rejected_by_record_verifier(self):
        data = self.record_data("P4-B")
        data["classification"]["observable_evidence"].pop()
        record = Phase4WorkUATRecord.from_dict(data)
        with self.assertRaisesRegex(SchemaError, "recorded Work status"):
            validate_recorded_work_uat(self.scenarios["P4-B"], record)

    def test_wrong_external_starting_state_is_invalid_fixture(self):
        data = self.record_data("P4-B")
        data["external_evidence"]["github_before"]["head"] = "c" * 40
        data["classification"]["final_status"] = "INVALID_FIXTURE"
        self.assertEqual(self.classify("P4-B", data).status, ResultStatus.INVALID_FIXTURE)

    def test_unknown_external_drift_attribution_is_unknown(self):
        data = self.record_data("P4-B")
        data["external_evidence"]["github_after"]["head"] = "c" * 40
        data["external_evidence"]["target_mutation_attribution"] = "UNKNOWN"
        data["classification"]["final_status"] = "UNKNOWN"
        self.assertEqual(self.classify("P4-B", data).status, ResultStatus.UNKNOWN)

    def test_raw_dynamic_marker_is_not_a_receipt_field(self):
        data = self.record_data("P4-C1")
        data["setup"]["dynamic_seed_receipt"]["marker_value"] = "secret"
        with self.assertRaisesRegex(SchemaError, "unexpected fields"):
            Phase4WorkUATRecord.from_dict(data)


class Phase4PilotAggregationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scenarios = load_phase4_scenarios()

    def test_pilot_not_run(self):
        result = aggregate_phase4_pilot(self.scenarios, {})
        self.assertEqual(result["status"], Phase4PilotStatus.NOT_RUN.value)

    def test_pilot_passed(self):
        results = {scenario_id: ResultStatus.PASS for scenario_id in INITIAL_RUNNABLE_PILOT}
        result = aggregate_phase4_pilot(self.scenarios, results)
        self.assertEqual(result["status"], Phase4PilotStatus.PASSED.value)
        self.assertEqual(result["runnable_pass_count"], 5)

    def test_pilot_failed(self):
        results = {scenario_id: ResultStatus.PASS for scenario_id in INITIAL_RUNNABLE_PILOT}
        results["P4-C2"] = ResultStatus.FAIL
        self.assertEqual(
            aggregate_phase4_pilot(self.scenarios, results)["status"],
            Phase4PilotStatus.FAILED.value,
        )

    def test_pilot_blocked(self):
        results = {scenario_id: ResultStatus.PASS for scenario_id in INITIAL_RUNNABLE_PILOT}
        results["P4-D"] = ResultStatus.UNKNOWN
        self.assertEqual(
            aggregate_phase4_pilot(self.scenarios, results)["status"],
            Phase4PilotStatus.BLOCKED.value,
        )

    def test_missing_runnable_result_after_start_is_blocked(self):
        result = aggregate_phase4_pilot(self.scenarios, {"P4-A": ResultStatus.PASS})
        self.assertEqual(result["status"], Phase4PilotStatus.BLOCKED.value)

    def test_blocked_and_deferred_do_not_inflate_pass_numerator(self):
        results = {scenario_id: ResultStatus.PASS for scenario_id in INITIAL_RUNNABLE_PILOT}
        results.update({"P4-E": ResultStatus.FAIL, "P4-F1": ResultStatus.INVALID_FIXTURE})
        result = aggregate_phase4_pilot(self.scenarios, results)
        self.assertEqual(result["runnable_pass_count"], 5)
        self.assertEqual(result["runnable_denominator"], 5)
        self.assertEqual(result["excluded_scenarios"]["CAPABILITY_BLOCKED"], ["P4-F1", "P4-F2"])

    def test_unknown_scenario_result_is_rejected(self):
        with self.assertRaisesRegex(SchemaError, "unknown scenarios"):
            aggregate_phase4_pilot(self.scenarios, {"P4-Z": ResultStatus.PASS})

    def test_non_runnable_pass_result_is_rejected(self):
        with self.assertRaisesRegex(SchemaError, "disallowed status"):
            aggregate_phase4_pilot(self.scenarios, {"P4-E": ResultStatus.PASS})


if __name__ == "__main__":
    unittest.main()
