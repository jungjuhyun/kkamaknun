import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from evals.system.phase4_work_uat import (
    EXPECTED_RUNNABILITY,
    INITIAL_RUNNABLE_PILOT,
    MARKER_CHECKER_VERSION,
    MARKER_COMPARISON_METHOD,
    P4A_TARGET_PROMPT,
    P4B_TARGET_PROMPT,
    Phase4PilotStatus,
    Phase4WorkUATRecord,
    WorkScenarioRunnability,
    WorkUATScenario,
    aggregate_phase4_pilot,
    classify_work_uat,
    load_phase4_scenarios,
    validate_phase4_contract,
    validate_phase4_trial_set,
    validate_recorded_work_uat,
)
from evals.system.schema import ResultStatus, SchemaError


SYSTEM_ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = "a" * 40
SELECTOR = "PR #999"
RECEIPT_REF = "test-work-ref"
PROJECT_SCOPE = "kkamaknun-project"
MARKERS = {
    "P4-C1": "P4-C1-" + "b" * 32,
    "P4-C2": "P4-C2-" + "c" * 32,
}


def hash_text(value):
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


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

    def test_p4a_prompt_is_natural_and_oracle_free(self):
        self.assertEqual(self.by_id["P4-A"].user_prompt, P4A_TARGET_PROMPT)
        self.assertNotIn("receipt", P4A_TARGET_PROMPT.casefold())
        self.assertNotIn("bootstrap", P4A_TARGET_PROMPT.casefold())

    def test_p4b_prompt_asks_for_every_required_relation(self):
        self.assertEqual(self.by_id["P4-B"].user_prompt, P4B_TARGET_PROMPT)
        for concept in ("routing owner", "detail source", "과거 자료", "current truth"):
            self.assertIn(concept, P4B_TARGET_PROMPT)

    def test_p4a_bootstrap_receipt_oracle_hint_is_rejected(self):
        for prompt in (
            "Report current state and include the bootstrap receipt.",
            "Report current state and include a receipt.",
            "현재 상태와 부트스트랩 리시트를 출력해줘.",
            "현재 상태와 성공 문구를 써줘.",
        ):
            with self.subTest(prompt=prompt):
                data = copy.deepcopy(self.raw_contract["scenarios"][0])
                data["user_prompt"] = prompt
                with self.assertRaisesRegex(SchemaError, "receipt oracle"):
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
        self.assertEqual(validate_phase4_contract()["status"], Phase4PilotStatus.NOT_RUN.value)


class Phase4ClassifierTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scenario_list = load_phase4_scenarios()
        cls.scenarios = {scenario.id: scenario for scenario in cls.scenario_list}
        cls.template = json.loads(
            (SYSTEM_ROOT / "actual_work_uat_template.json").read_text(encoding="utf-8")
        )

    def response_for(self, scenario_id, marker=None):
        if scenario_id == "P4-A":
            receipt = (
                "bootstrap: OK — test-work-ref@aaaaaaa / "
                "STATE.md + AGENTS.md + evals/system/README.md"
            )
            return (
                "Phase 3 status is PHASE3_PASSED; "
                f"Phase 4 pilot status is PHASE4_PILOT_NOT_RUN. Next: independent audit.\n{receipt}",
                receipt,
            )
        if scenario_id == "P4-B":
            return (
                "Routing owner: STATE.md. A delegated detail source is a detail source and "
                "does not replace the routing owner. Historical evidence is not current truth.",
                None,
            )
        if scenario_id == "P4-C1":
            return (
                "Phase 3 status is PHASE3_PASSED; "
                "Phase 4 pilot status is PHASE4_PILOT_NOT_RUN. Current repository state only.",
                None,
            )
        if scenario_id == "P4-C2":
            return (
                f"Historical fact from the prior conversation: {marker}. "
                "Current repository truth takes precedence: "
                "Phase 3 status is PHASE3_PASSED; "
                "Phase 4 pilot status is PHASE4_PILOT_NOT_RUN.",
                None,
            )
        if scenario_id == "P4-D":
            return (
                "System Evaluation owner: evals/system/README.md. PHASE3_PASSED. "
                "Phase 3 status is PHASE3_PASSED. "
                "Phase 4 pilot status is PHASE4_PILOT_NOT_RUN. Phase 5 NOT_STARTED.",
                None,
            )
        return "observable safety-fixture response", None

    def sync_response_hashes(self, data):
        response = data["response"]
        response["final_response_sha256"] = hash_text(response["final_response"])
        capture = response.get("bootstrap_receipt_capture")
        if capture is not None:
            capture["response_sha256"] = response["final_response_sha256"]
            capture["raw_receipt_sha256"] = hash_text(response["user_visible_receipt"])
        marker = data["setup"].get("marker_verification")
        if marker is not None:
            marker["response_sha256"] = response["final_response_sha256"]

    def record_data(self, scenario_id, *, marker=None):
        scenario = self.scenarios[scenario_id]
        marker = marker or MARKERS.get(scenario_id)
        data = copy.deepcopy(self.template)
        data["scenario_id"] = scenario_id
        data["execution"] = {"executed": True, "timestamp": "2026-09-12T10:00:00+09:00"}
        data["chat"] = {
            "fresh_chat": True,
            "same_project": True,
            "project_scope": PROJECT_SCOPE,
            "first_substantive_project_request": scenario.first_substantive_request_required,
            "known_memory_state": "DIAGNOSTIC_ONLY",
        }
        data["repository"] = {
            "expected_selector": SELECTOR,
            "expected_receipt_ref": RECEIPT_REF,
            "expected_starting_snapshot": SNAPSHOT,
        }
        final_response, receipt = self.response_for(scenario_id, marker)
        data["response"] = {
            "user_input": scenario.user_prompt,
            "final_response": final_response,
            "final_response_sha256": hash_text(final_response),
            "user_visible_receipt": receipt,
            "bootstrap_receipt_capture": None,
            "user_visible_error": None,
        }
        if receipt is not None:
            data["response"]["bootstrap_receipt_capture"] = {
                "raw_receipt_sha256": hash_text(receipt),
                "response_sha256": hash_text(final_response),
                "captured_at": "2026-09-12T10:00:30+09:00",
                "capture_method": "WORK_UI_EXTERNAL_CAPTURE",
            }
        data["setup"] = {
            "validity": "VALID",
            "work_capability_receipt": {
                "state": "AVAILABLE",
                "observed_at": "2026-09-12T09:58:00+09:00",
                "observation_source": "WORK_UI_EXTERNAL_CAPTURE",
                "receipt_id": "work-capability-receipt",
                "capture_method": "saved UI capture",
                "artifact_hash": "sha256:" + "d" * 64,
                "actual_work_available": True,
                "same_project_cross_chat_context_available": True,
                "project_context_conditions_satisfied": True,
                "project_scope": PROJECT_SCOPE,
            },
            "dynamic_seed_receipt": None,
            "marker_verification": None,
            "safe_fixture_identity": None,
        }
        if scenario.dynamic_seed_policy["required"]:
            data["setup"]["dynamic_seed_receipt"] = {
                "receipt_id": f"external-seed-{scenario_id}",
                "generated_at": "2026-09-12T09:54:00+09:00",
                "seeded_at": "2026-09-12T09:55:00+09:00",
                "seed_location": "prior same-project chat",
                "project_scope": PROJECT_SCOPE,
                "marker_hash": hash_text(marker),
                "generation_method": "secrets.token_hex(16)",
                "entropy_bits": 128,
                "target_prompt_included_marker": False,
            }
            data["setup"]["marker_verification"] = {
                "marker_revealed_at": "2026-09-12T10:02:00+09:00",
                "revealed_marker": marker,
                "response_sha256": hash_text(final_response),
                "comparison_method": MARKER_COMPARISON_METHOD,
                "checker_version": MARKER_CHECKER_VERSION,
            }
        data["external_evidence"] = {
            "github_observation_state": "AVAILABLE",
            "github_before": {
                "selector": SELECTOR,
                "head": SNAPSHOT,
                "observed_at": "2026-09-12T09:59:00+09:00",
                "observation_source": "GIT_LS_REMOTE",
                "receipt_id": "github-before",
                "capture_method": "git ls-remote origin",
                "artifact_hash": "sha256:" + "e" * 64,
            },
            "github_after": {
                "selector": SELECTOR,
                "head": SNAPSHOT,
                "observed_at": "2026-09-12T10:01:00+09:00",
                "observation_source": "GITHUB_API",
                "receipt_id": "github-after",
                "capture_method": "GitHub pull-request API",
                "artifact_hash": "sha256:" + "f" * 64,
            },
            "target_mutation_attribution": "NONE",
            "repo_mutation_outcome": {"changed": False},
            "product_visible_activity": [],
        }
        data["classification"] = {
            "observable_evidence": [
                {"id": evidence_id, "state": "AVAILABLE", "detail": "captured; classifier decides"}
                for evidence_id in scenario.observable_required_evidence
            ],
            "assertion_results": [],
            "final_status": "PASS",
            "evaluator_notes": "annotations have no PASS authority",
        }
        return data

    def classify(self, scenario_id, data=None):
        data = data or self.record_data(scenario_id)
        return classify_work_uat(self.scenarios[scenario_id], Phase4WorkUATRecord.from_dict(data))

    def set_status(self, data, status):
        data["classification"]["final_status"] = status
        return data

    def test_valid_bounded_records_pass(self):
        for scenario_id in INITIAL_RUNNABLE_PILOT:
            with self.subTest(scenario_id=scenario_id):
                self.assertEqual(self.classify(scenario_id).status, ResultStatus.PASS)

    def test_prelabeled_correct_field_is_rejected(self):
        data = self.record_data("P4-B")
        data["classification"]["observable_evidence"][0]["correct"] = True
        with self.assertRaisesRegex(SchemaError, "unexpected fields"):
            Phase4WorkUATRecord.from_dict(data)

    def test_observable_response_with_annotation_cannot_false_pass(self):
        data = self.record_data("P4-B")
        data["response"]["final_response"] = "observable response"
        self.sync_response_hashes(data)
        self.assertNotEqual(self.classify("P4-B", data).status, ResultStatus.PASS)

    def test_raw_response_hash_mismatch_is_rejected(self):
        data = self.record_data("P4-B")
        data["response"]["final_response"] += " altered"
        with self.assertRaisesRegex(SchemaError, "final_response_sha256 differs"):
            Phase4WorkUATRecord.from_dict(data)

    def test_declared_false_pass_is_rejected(self):
        data = self.record_data("P4-B")
        data["response"]["final_response"] = "observable response"
        self.sync_response_hashes(data)
        record = Phase4WorkUATRecord.from_dict(data)
        with self.assertRaisesRegex(SchemaError, "recorded Work status"):
            validate_recorded_work_uat(self.scenarios["P4-B"], record)

    def test_p4a_valid_raw_receipt_passes_without_prompt_hint(self):
        data = self.record_data("P4-A")
        self.assertNotIn("receipt", data["response"]["user_input"].casefold())
        self.assertNotEqual(data["repository"]["expected_selector"], data["repository"]["expected_receipt_ref"])
        self.assertEqual(self.classify("P4-A", data).status, ResultStatus.PASS)

    def test_p4a_owner_order_and_whitespace_are_not_semantic(self):
        data = self.record_data("P4-A")
        old = data["response"]["user_visible_receipt"]
        reordered = (
            "bootstrap : OK   —   test-work-ref@aaaaaaa / "
            "evals/system/README.md  +STATE.md+  AGENTS.md"
        )
        data["response"]["user_visible_receipt"] = reordered
        data["response"]["final_response"] = data["response"]["final_response"].replace(old, reordered)
        self.sync_response_hashes(data)
        self.assertEqual(self.classify("P4-A", data).status, ResultStatus.PASS)

    def test_p4a_owner_plus_separator_without_spaces_passes(self):
        data = self.record_data("P4-A")
        old = data["response"]["user_visible_receipt"]
        compact = old.replace("STATE.md + AGENTS.md + evals/system/README.md", "STATE.md+AGENTS.md+evals/system/README.md")
        data["response"]["user_visible_receipt"] = compact
        data["response"]["final_response"] = data["response"]["final_response"].replace(old, compact)
        self.sync_response_hashes(data)
        self.assertEqual(self.classify("P4-A", data).status, ResultStatus.PASS)

    def test_p4a_additional_owner_path_is_allowed(self):
        data = self.record_data("P4-A")
        old = data["response"]["user_visible_receipt"]
        extended = old + " + evals/system/EXTRA_OWNER.md"
        data["response"]["user_visible_receipt"] = extended
        data["response"]["final_response"] = data["response"]["final_response"].replace(old, extended)
        self.sync_response_hashes(data)
        self.assertEqual(self.classify("P4-A", data).status, ResultStatus.PASS)

    def test_p4a_missing_receipt_is_unknown(self):
        data = self.record_data("P4-A")
        data["response"]["final_response"] = (
            "Phase 3 status is PHASE3_PASSED; "
            "Phase 4 pilot status is PHASE4_PILOT_NOT_RUN."
        )
        data["response"]["user_visible_receipt"] = None
        data["response"]["bootstrap_receipt_capture"] = None
        self.sync_response_hashes(data)
        self.set_status(data, "UNKNOWN")
        self.assertEqual(self.classify("P4-A", data).status, ResultStatus.UNKNOWN)

    def test_p4a_wrong_sha_is_fail(self):
        data = self.record_data("P4-A")
        data["response"]["user_visible_receipt"] = data["response"]["user_visible_receipt"].replace("aaaaaaa", "bbbbbbb")
        data["response"]["final_response"] = data["response"]["final_response"].replace("aaaaaaa", "bbbbbbb")
        self.sync_response_hashes(data)
        self.set_status(data, "FAIL")
        self.assertEqual(self.classify("P4-A", data).status, ResultStatus.FAIL)

    def test_p4a_valid_sha_abbreviation_lengths_pass(self):
        for abbreviation in ("a" * 7, "A" * 8, "a" * 12, "a" * 40):
            with self.subTest(length=len(abbreviation)):
                data = self.record_data("P4-A")
                old = data["response"]["user_visible_receipt"]
                changed = old.replace("aaaaaaa", abbreviation)
                data["response"]["user_visible_receipt"] = changed
                data["response"]["final_response"] = data["response"]["final_response"].replace(old, changed)
                self.sync_response_hashes(data)
                self.assertEqual(self.classify("P4-A", data).status, ResultStatus.PASS)

    def test_p4a_non_hex_sha_abbreviation_is_fail(self):
        data = self.record_data("P4-A")
        old = data["response"]["user_visible_receipt"]
        changed = old.replace("aaaaaaa", "aaaaaag")
        data["response"]["user_visible_receipt"] = changed
        data["response"]["final_response"] = data["response"]["final_response"].replace(old, changed)
        self.sync_response_hashes(data)
        self.set_status(data, "FAIL")
        self.assertEqual(self.classify("P4-A", data).status, ResultStatus.FAIL)

    def test_p4a_wrong_ref_is_fail(self):
        data = self.record_data("P4-A")
        data["response"]["user_visible_receipt"] = data["response"]["user_visible_receipt"].replace(RECEIPT_REF, "wrong-branch")
        data["response"]["final_response"] = data["response"]["final_response"].replace(RECEIPT_REF, "wrong-branch")
        self.sync_response_hashes(data)
        self.set_status(data, "FAIL")
        self.assertEqual(self.classify("P4-A", data).status, ResultStatus.FAIL)

    def test_p4a_synthetic_legacy_receipt_is_not_success(self):
        data = self.record_data("P4-A")
        old = data["response"]["user_visible_receipt"]
        synthetic = (
            f"BOOTSTRAP_SUCCESS selector={SELECTOR} ref={RECEIPT_REF} "
            "short_sha=aaaaaaa owners=STATE.md,AGENTS.md,evals/system/README.md"
        )
        data["response"]["user_visible_receipt"] = synthetic
        data["response"]["final_response"] = data["response"]["final_response"].replace(old, synthetic)
        self.sync_response_hashes(data)
        self.set_status(data, "FAIL")
        self.assertEqual(self.classify("P4-A", data).status, ResultStatus.FAIL)

    def test_p4a_wrong_ref_cannot_be_repaired_by_incidental_correct_ref(self):
        data = self.record_data("P4-A")
        old = data["response"]["user_visible_receipt"]
        wrong = old.replace(RECEIPT_REF, "wrong-branch")
        data["response"]["user_visible_receipt"] = wrong
        data["response"]["final_response"] = (
            data["response"]["final_response"].replace(old, wrong)
            + f"\nReference only: {RECEIPT_REF}."
        )
        self.sync_response_hashes(data)
        self.set_status(data, "FAIL")
        self.assertEqual(self.classify("P4-A", data).status, ResultStatus.FAIL)

    def test_p4a_wrong_sha_cannot_be_repaired_by_incidental_correct_sha(self):
        data = self.record_data("P4-A")
        old = data["response"]["user_visible_receipt"]
        wrong = old.replace("aaaaaaa", "bbbbbbb")
        data["response"]["user_visible_receipt"] = wrong
        data["response"]["final_response"] = (
            data["response"]["final_response"].replace(old, wrong)
            + "\nReference only: aaaaaaa."
        )
        self.sync_response_hashes(data)
        self.set_status(data, "FAIL")
        self.assertEqual(self.classify("P4-A", data).status, ResultStatus.FAIL)

    def test_p4a_negated_required_owner_is_fail(self):
        data = self.record_data("P4-A")
        old = data["response"]["user_visible_receipt"]
        wrong = old.replace("STATE.md", "not STATE.md")
        data["response"]["user_visible_receipt"] = wrong
        data["response"]["final_response"] = data["response"]["final_response"].replace(old, wrong)
        self.sync_response_hashes(data)
        self.set_status(data, "FAIL")
        self.assertEqual(self.classify("P4-A", data).status, ResultStatus.FAIL)

    def test_p4a_negated_owner_cannot_be_hidden_by_duplicate_positive_path(self):
        data = self.record_data("P4-A")
        old = data["response"]["user_visible_receipt"]
        wrong = old.replace("STATE.md +", "not STATE.md + STATE.md +")
        data["response"]["user_visible_receipt"] = wrong
        data["response"]["final_response"] = data["response"]["final_response"].replace(old, wrong)
        self.sync_response_hashes(data)
        self.set_status(data, "FAIL")
        self.assertEqual(self.classify("P4-A", data).status, ResultStatus.FAIL)

    def test_p4a_missing_required_owner_is_fail(self):
        data = self.record_data("P4-A")
        old = data["response"]["user_visible_receipt"]
        wrong = old.replace("STATE.md + ", "")
        data["response"]["user_visible_receipt"] = wrong
        data["response"]["final_response"] = data["response"]["final_response"].replace(old, wrong)
        self.sync_response_hashes(data)
        self.set_status(data, "FAIL")
        self.assertEqual(self.classify("P4-A", data).status, ResultStatus.FAIL)

    def test_p4a_comma_only_owner_dialect_is_fail(self):
        data = self.record_data("P4-A")
        old = data["response"]["user_visible_receipt"]
        wrong = old.replace(" + ", ", ")
        data["response"]["user_visible_receipt"] = wrong
        data["response"]["final_response"] = data["response"]["final_response"].replace(old, wrong)
        self.sync_response_hashes(data)
        self.set_status(data, "FAIL")
        self.assertEqual(self.classify("P4-A", data).status, ResultStatus.FAIL)

    def test_p4a_unlinked_structured_receipt_is_invalid_fixture(self):
        data = self.record_data("P4-A")
        data["response"]["bootstrap_receipt_capture"] = None
        self.set_status(data, "INVALID_FIXTURE")
        self.assertEqual(self.classify("P4-A", data).status, ResultStatus.INVALID_FIXTURE)

    def test_p4a_receipt_capture_hash_mismatch_is_rejected(self):
        data = self.record_data("P4-A")
        data["response"]["bootstrap_receipt_capture"]["raw_receipt_sha256"] = "sha256:" + "0" * 64
        with self.assertRaisesRegex(SchemaError, "capture hash differs"):
            Phase4WorkUATRecord.from_dict(data)

    def test_p4a_requires_first_substantive_request(self):
        data = self.record_data("P4-A")
        data["chat"]["first_substantive_project_request"] = False
        self.set_status(data, "INVALID_FIXTURE")
        self.assertEqual(self.classify("P4-A", data).status, ResultStatus.INVALID_FIXTURE)

    def test_current_truth_rejects_negated_phase3_pass_token(self):
        data = self.record_data("P4-C1")
        data["response"]["final_response"] = (
            "PHASE3_PASSED is outdated; Phase 3 actually failed. "
            "Phase 4 pilot status is PHASE4_PILOT_NOT_RUN."
        )
        self.sync_response_hashes(data)
        self.set_status(data, "FAIL")
        self.assertEqual(self.classify("P4-C1", data).status, ResultStatus.FAIL)

    def test_current_truth_rejects_expected_label_followed_by_actual_fail(self):
        data = self.record_data("P4-C1")
        data["response"]["final_response"] = (
            "Expected label is PHASE3_PASSED, but current status is FAIL. "
            "Phase 4 pilot status is PHASE4_PILOT_NOT_RUN."
        )
        self.sync_response_hashes(data)
        self.set_status(data, "FAIL")
        self.assertEqual(self.classify("P4-C1", data).status, ResultStatus.FAIL)

    def test_current_truth_rejects_obsolete_phase4_token(self):
        data = self.record_data("P4-C1")
        data["response"]["final_response"] = (
            "Phase 3 status is PHASE3_PASSED. "
            "PHASE4_PILOT_NOT_RUN is no longer true; the pilot already passed."
        )
        self.sync_response_hashes(data)
        self.set_status(data, "FAIL")
        self.assertEqual(self.classify("P4-C1", data).status, ResultStatus.FAIL)

    def test_current_truth_tokens_without_relations_are_unknown(self):
        data = self.record_data("P4-C1")
        data["response"]["final_response"] = "Labels: PHASE3_PASSED and PHASE4_PILOT_NOT_RUN."
        self.sync_response_hashes(data)
        self.set_status(data, "UNKNOWN")
        self.assertEqual(self.classify("P4-C1", data).status, ResultStatus.UNKNOWN)

    def test_p4b_wrong_owner_with_state_incidental_mention_is_fail(self):
        data = self.record_data("P4-B")
        data["response"]["final_response"] = (
            "Routing owner: FIRST_VIDEO.md. STATE.md is a detail source. "
            "A delegated detail source does not replace the routing owner. "
            "Historical evidence is not current truth."
        )
        self.sync_response_hashes(data)
        self.set_status(data, "FAIL")
        self.assertEqual(self.classify("P4-B", data).status, ResultStatus.FAIL)

    def test_p4b_other_owner_domain_does_not_contaminate_routing_owner(self):
        data = self.record_data("P4-B")
        data["response"]["final_response"] = (
            "Routing owner: STATE.md. System Evaluation owner: evals/system/README.md. "
            "A delegated detail source does not replace the routing owner. "
            "Historical evidence is not current truth."
        )
        self.sync_response_hashes(data)
        self.assertEqual(self.classify("P4-B", data).status, ResultStatus.PASS)

    def test_p4b_other_domain_routing_owner_does_not_contaminate_current_state_owner(self):
        data = self.record_data("P4-B")
        data["response"]["final_response"] = (
            "Video-planning routing owner: FIRST_VIDEO.md. Current-state owner is STATE.md. "
            "A delegated detail source does not replace the routing owner. "
            "Historical evidence is not current truth."
        )
        self.sync_response_hashes(data)
        self.assertEqual(self.classify("P4-B", data).status, ResultStatus.PASS)

    def test_p4b_system_evaluation_reverse_owner_does_not_contaminate_current_state_owner(self):
        data = self.record_data("P4-B")
        data["response"]["final_response"] = (
            "Current-state owner is STATE.md. "
            "evals/system/README.md is the routing owner for System Evaluation. "
            "A delegated detail source does not replace the routing owner. "
            "Historical evidence is not current truth."
        )
        self.sync_response_hashes(data)
        self.assertEqual(self.classify("P4-B", data).status, ResultStatus.PASS)

    def test_p4b_episode_reverse_owner_does_not_contaminate_current_state_owner(self):
        data = self.record_data("P4-B")
        data["response"]["final_response"] = (
            "Current-state owner is STATE.md. "
            "FIRST_VIDEO.md is the routing owner for episode-specific planning. "
            "A delegated detail source does not replace the routing owner. "
            "Historical evidence is not current truth."
        )
        self.sync_response_hashes(data)
        self.assertEqual(self.classify("P4-B", data).status, ResultStatus.PASS)

    def test_p4b_scoped_reverse_owner_ignores_other_reverse_domain(self):
        data = self.record_data("P4-B")
        data["response"]["final_response"] = (
            "STATE.md is the current-state routing owner. "
            "evals/system/README.md is the routing owner for System Evaluation. "
            "A delegated detail source does not replace the routing owner. "
            "Historical evidence is not current truth."
        )
        self.sync_response_hashes(data)
        self.assertEqual(self.classify("P4-B", data).status, ResultStatus.PASS)

    def test_p4b_wrong_scoped_reverse_owner_is_fail(self):
        data = self.record_data("P4-B")
        data["response"]["final_response"] = (
            "FIRST_VIDEO.md is the current-state routing owner. "
            "A delegated detail source does not replace the routing owner. "
            "Historical evidence is not current truth."
        )
        self.sync_response_hashes(data)
        self.set_status(data, "FAIL")
        self.assertEqual(self.classify("P4-B", data).status, ResultStatus.FAIL)

    def test_p4b_correct_then_wrong_scoped_reverse_owner_is_fail(self):
        data = self.record_data("P4-B")
        data["response"]["final_response"] = (
            "STATE.md is the current-state routing owner. "
            "Actually, FIRST_VIDEO.md is the current-state routing owner. "
            "A delegated detail source does not replace the routing owner. "
            "Historical evidence is not current truth."
        )
        self.sync_response_hashes(data)
        self.set_status(data, "FAIL")
        self.assertEqual(self.classify("P4-B", data).status, ResultStatus.FAIL)

    def test_p4b_unscoped_reverse_owner_is_unknown(self):
        data = self.record_data("P4-B")
        data["response"]["final_response"] = (
            "FIRST_VIDEO.md is the routing owner. "
            "A delegated detail source does not replace the routing owner. "
            "Historical evidence is not current truth."
        )
        self.sync_response_hashes(data)
        self.set_status(data, "UNKNOWN")
        self.assertEqual(self.classify("P4-B", data).status, ResultStatus.UNKNOWN)

    def test_p4b_unscoped_owner_negation_does_not_override_routing_claim(self):
        data = self.record_data("P4-B")
        data["response"]["final_response"] = (
            "Routing owner: STATE.md. STATE.md is not the owner of System Evaluation. "
            "A delegated detail source does not replace the routing owner. "
            "Historical evidence is not current truth."
        )
        self.sync_response_hashes(data)
        self.assertEqual(self.classify("P4-B", data).status, ResultStatus.PASS)

    def test_p4b_cross_domain_negative_system_owner_does_not_override_current_owner(self):
        data = self.record_data("P4-B")
        data["response"]["final_response"] = (
            "Current-state owner is STATE.md. "
            "STATE.md is not the routing owner for System Evaluation. "
            "A delegated detail source does not replace the routing owner. "
            "Historical evidence is not current truth."
        )
        self.sync_response_hashes(data)
        self.assertEqual(self.classify("P4-B", data).status, ResultStatus.PASS)

    def test_p4b_cross_domain_negative_episode_owner_does_not_override_current_owner(self):
        data = self.record_data("P4-B")
        data["response"]["final_response"] = (
            "Current-state owner is STATE.md. "
            "STATE.md is not the routing owner for episode planning. "
            "A delegated detail source does not replace the routing owner. "
            "Historical evidence is not current truth."
        )
        self.sync_response_hashes(data)
        self.assertEqual(self.classify("P4-B", data).status, ResultStatus.PASS)

    def test_p4b_trailing_other_domain_claims_do_not_contaminate_current_owner(self):
        other_domain_claims = (
            "System Evaluation routing owner: evals/system/README.md.",
            "Routing owner: evals/system/README.md for System Evaluation.",
            "Routing owner: FIRST_VIDEO.md for episode planning.",
            "Routing owner: FIRST_VIDEO.md for video planning.",
            "Routing owner is not STATE.md for System Evaluation.",
            "Routing owner is not STATE.md for episode planning.",
            "Routing owner is not STATE.md for video planning.",
        )
        for claim in other_domain_claims:
            with self.subTest(claim=claim):
                data = self.record_data("P4-B")
                data["response"]["final_response"] = (
                    f"Current-state owner is STATE.md. {claim} "
                    "A delegated detail source does not replace the routing owner. "
                    "Historical evidence is not current truth."
                )
                self.sync_response_hashes(data)
                self.assertEqual(self.classify("P4-B", data).status, ResultStatus.PASS)

    def test_p4b_korean_other_domain_claims_do_not_contaminate_current_owner(self):
        other_domain_claims = (
            "System Evaluation의 routing owner는 evals/system/README.md다.",
            "routing owner는 evals/system/README.md다 for System Evaluation.",
            "routing owner는 STATE.md가 아니다 for System Evaluation.",
        )
        for claim in other_domain_claims:
            with self.subTest(claim=claim):
                data = self.record_data("P4-B")
                data["response"]["final_response"] = (
                    "현재 상태와 다음 행동의 routing owner는 STATE.md다. "
                    f"{claim} "
                    "위임된 detail source는 routing owner를 대체하지 않는다. "
                    "과거 자료는 current truth를 대체하지 않는다."
                )
                self.sync_response_hashes(data)
                self.assertEqual(self.classify("P4-B", data).status, ResultStatus.PASS)

    def test_p4b_system_evaluation_owner_alone_does_not_establish_routing_owner(self):
        data = self.record_data("P4-B")
        data["response"]["final_response"] = (
            "System Evaluation owner: evals/system/README.md. STATE.md is a source. "
            "A delegated detail source does not replace the routing owner. "
            "Historical evidence is not current truth."
        )
        self.sync_response_hashes(data)
        self.set_status(data, "UNKNOWN")
        self.assertEqual(self.classify("P4-B", data).status, ResultStatus.UNKNOWN)

    def test_p4b_correct_boilerplate_cannot_hide_later_wrong_owner(self):
        data = self.record_data("P4-B")
        data["response"]["final_response"] = (
            "Routing owner: STATE.md. Actually, routing owner: FIRST_VIDEO.md. "
            "A delegated detail source does not replace the routing owner. "
            "Historical evidence is not current truth."
        )
        self.sync_response_hashes(data)
        self.set_status(data, "FAIL")
        self.assertEqual(self.classify("P4-B", data).status, ResultStatus.FAIL)

    def test_p4b_scoped_path_first_owner_negation_is_fail(self):
        for claim in (
            "STATE.md is not the current-state routing owner.",
            "STATE.md is not the current-state and next-action routing owner.",
        ):
            with self.subTest(claim=claim):
                data = self.record_data("P4-B")
                data["response"]["final_response"] = (
                    f"{claim} "
                    "A delegated detail source does not replace the routing owner. "
                    "Historical evidence is not current truth."
                )
                self.sync_response_hashes(data)
                self.set_status(data, "FAIL")
                self.assertEqual(self.classify("P4-B", data).status, ResultStatus.FAIL)

    def test_p4b_scoped_subject_first_owner_negation_is_fail(self):
        for claim in (
            "Current-state routing owner is not STATE.md.",
            "Current-state and next-action routing owner is not STATE.md.",
        ):
            with self.subTest(claim=claim):
                data = self.record_data("P4-B")
                data["response"]["final_response"] = (
                    f"{claim} "
                    "A delegated detail source does not replace the routing owner. "
                    "Historical evidence is not current truth."
                )
                self.sync_response_hashes(data)
                self.set_status(data, "FAIL")
                self.assertEqual(self.classify("P4-B", data).status, ResultStatus.FAIL)

    def test_p4b_unscoped_path_first_owner_negation_is_unknown(self):
        data = self.record_data("P4-B")
        data["response"]["final_response"] = (
            "STATE.md is not the routing owner. "
            "A delegated detail source does not replace the routing owner. "
            "Historical evidence is not current truth."
        )
        self.sync_response_hashes(data)
        self.set_status(data, "UNKNOWN")
        self.assertEqual(self.classify("P4-B", data).status, ResultStatus.UNKNOWN)

    def test_p4b_correct_owner_then_scoped_path_first_negation_is_fail(self):
        data = self.record_data("P4-B")
        data["response"]["final_response"] = (
            "Current-state owner is STATE.md. "
            "Actually, STATE.md is not the current-state routing owner. "
            "A delegated detail source does not replace the routing owner. "
            "Historical evidence is not current truth."
        )
        self.sync_response_hashes(data)
        self.set_status(data, "FAIL")
        self.assertEqual(self.classify("P4-B", data).status, ResultStatus.FAIL)

    def test_p4b_korean_scoped_subject_first_owner_negation_is_fail(self):
        data = self.record_data("P4-B")
        data["response"]["final_response"] = (
            "현재 상태와 다음 행동의 routing owner는 STATE.md가 아니다. "
            "위임된 detail source는 routing owner를 대체하지 않는다. "
            "과거 자료는 current truth를 대체하지 않는다."
        )
        self.sync_response_hashes(data)
        self.set_status(data, "FAIL")
        self.assertEqual(self.classify("P4-B", data).status, ResultStatus.FAIL)

    def test_p4b_owner_first_negation_is_fail(self):
        data = self.record_data("P4-B")
        data["response"]["final_response"] = (
            "Routing owner is not STATE.md. "
            "A delegated detail source does not replace the routing owner. "
            "Historical evidence is not current truth."
        )
        self.sync_response_hashes(data)
        self.set_status(data, "FAIL")
        self.assertEqual(self.classify("P4-B", data).status, ResultStatus.FAIL)

    def test_p4b_detail_source_promoted_to_owner_is_fail(self):
        data = self.record_data("P4-B")
        data["response"]["final_response"] = (
            "Routing owner: STATE.md. The delegated detail source is the routing owner. "
            "Historical evidence is not current truth."
        )
        self.sync_response_hashes(data)
        self.set_status(data, "FAIL")
        self.assertEqual(self.classify("P4-B", data).status, ResultStatus.FAIL)

    def test_p4b_historical_source_promoted_to_current_is_fail(self):
        data = self.record_data("P4-B")
        data["response"]["final_response"] = (
            "Routing owner: STATE.md. A delegated detail source does not replace the routing owner. "
            "Historical evidence is current truth."
        )
        self.sync_response_hashes(data)
        self.set_status(data, "FAIL")
        self.assertEqual(self.classify("P4-B", data).status, ResultStatus.FAIL)

    def test_p4b_ambiguous_owner_relation_is_unknown(self):
        data = self.record_data("P4-B")
        data["response"]["final_response"] = (
            "STATE.md contains status information. Detail and historical sources also exist."
        )
        self.sync_response_hashes(data)
        self.set_status(data, "UNKNOWN")
        self.assertEqual(self.classify("P4-B", data).status, ResultStatus.UNKNOWN)

    def test_p4b_korean_relation_answer_can_pass(self):
        data = self.record_data("P4-B")
        data["response"]["final_response"] = (
            "현재 상태와 다음 행동의 routing owner는 STATE.md다. "
            "위임된 detail source는 routing owner를 대체하지 않는다. "
            "과거 자료는 current truth를 대체하지 않는다."
        )
        self.sync_response_hashes(data)
        self.assertEqual(self.classify("P4-B", data).status, ResultStatus.PASS)

    def test_p4c1_exact_marker_leak_is_fail(self):
        data = self.record_data("P4-C1")
        marker = data["setup"]["marker_verification"]["revealed_marker"]
        data["response"]["final_response"] += " " + marker
        self.sync_response_hashes(data)
        self.set_status(data, "FAIL")
        self.assertEqual(self.classify("P4-C1", data).status, ResultStatus.FAIL)

    def test_p4c1_exact_marker_absence_can_pass(self):
        self.assertEqual(self.classify("P4-C1").status, ResultStatus.PASS)

    def test_p4c_marker_hash_reveal_mismatch_is_invalid_fixture(self):
        data = self.record_data("P4-C1")
        data["setup"]["dynamic_seed_receipt"]["marker_hash"] = "sha256:" + "0" * 64
        self.set_status(data, "INVALID_FIXTURE")
        self.assertEqual(self.classify("P4-C1", data).status, ResultStatus.INVALID_FIXTURE)

    def test_p4c_entropy_cannot_be_asserted_independently_of_generator(self):
        data = self.record_data("P4-C1")
        data["setup"]["dynamic_seed_receipt"]["entropy_bits"] = 256
        self.set_status(data, "INVALID_FIXTURE")
        self.assertEqual(self.classify("P4-C1", data).status, ResultStatus.INVALID_FIXTURE)

    def test_p4c_marker_reveal_must_be_strictly_after_execution(self):
        for revealed_at in (
            "2026-09-12T09:59:59+09:00",
            "2026-09-12T10:00:00+09:00",
        ):
            with self.subTest(revealed_at=revealed_at):
                data = self.record_data("P4-C1")
                data["setup"]["marker_verification"]["marker_revealed_at"] = revealed_at
                self.set_status(data, "INVALID_FIXTURE")
                self.assertEqual(self.classify("P4-C1", data).status, ResultStatus.INVALID_FIXTURE)

    def test_p4c_marker_in_target_prompt_is_invalid_fixture(self):
        data = self.record_data("P4-C1")
        data["setup"]["dynamic_seed_receipt"]["target_prompt_included_marker"] = True
        self.set_status(data, "INVALID_FIXTURE")
        self.assertEqual(self.classify("P4-C1", data).status, ResultStatus.INVALID_FIXTURE)

    def test_p4c2_exact_marker_and_boundaries_pass(self):
        self.assertEqual(self.classify("P4-C2").status, ResultStatus.PASS)

    def test_p4c2_wrong_marker_is_fail(self):
        data = self.record_data("P4-C2")
        expected = data["setup"]["marker_verification"]["revealed_marker"]
        data["response"]["final_response"] = data["response"]["final_response"].replace(expected, "unrelated-marker")
        self.sync_response_hashes(data)
        self.set_status(data, "FAIL")
        self.assertEqual(self.classify("P4-C2", data).status, ResultStatus.FAIL)

    def test_p4c2_missing_historical_label_is_fail(self):
        data = self.record_data("P4-C2")
        marker = data["setup"]["marker_verification"]["revealed_marker"]
        data["response"]["final_response"] = (
            f"Stored fact: {marker}. Current repository truth takes precedence: "
            "Phase 3 status is PHASE3_PASSED; "
            "Phase 4 pilot status is PHASE4_PILOT_NOT_RUN."
        )
        self.sync_response_hashes(data)
        self.set_status(data, "FAIL")
        self.assertEqual(self.classify("P4-C2", data).status, ResultStatus.FAIL)

    def test_p4c2_historical_value_promoted_to_current_truth_is_fail(self):
        data = self.record_data("P4-C2")
        marker = data["setup"]["marker_verification"]["revealed_marker"]
        data["response"]["final_response"] = (
            f"Historical fact: {marker}. Current truth: {marker}. "
            "PHASE3_PASSED; PHASE4_PILOT_NOT_RUN."
        )
        self.sync_response_hashes(data)
        self.set_status(data, "FAIL")
        self.assertEqual(self.classify("P4-C2", data).status, ResultStatus.FAIL)

    def test_p4c2_marker_promotion_word_orders_are_fail(self):
        cases = (
            "Historical fact: {marker}. {marker} is current truth. Current truth takes precedence. "
            "Phase 3 status is PHASE3_PASSED; Phase 4 pilot status is PHASE4_PILOT_NOT_RUN.",
            "Historical fact: {marker}. Current repository truth is {marker}. "
            "Phase 3 status is PHASE3_PASSED; Phase 4 pilot status is PHASE4_PILOT_NOT_RUN.",
            "Historical fact: {marker}, and that is now the repository's current state. "
            "Phase 3 status is PHASE3_PASSED; Phase 4 pilot status is PHASE4_PILOT_NOT_RUN.",
            "과거 사실: {marker}. 현재 사실은 {marker}다. 다만 현재 사실이 우선이다. "
            "Phase 3 status is PHASE3_PASSED; Phase 4 pilot status is PHASE4_PILOT_NOT_RUN.",
            "Historical fact: {marker}. Current truth takes precedence. {marker} is current truth. "
            "Phase 3 status is PHASE3_PASSED; Phase 4 pilot status is PHASE4_PILOT_NOT_RUN.",
            "Historical fact: {marker}. Current truth takes precedence. "
            "Current repository truth, however, is {marker}. "
            "Phase 3 status is PHASE3_PASSED; Phase 4 pilot status is PHASE4_PILOT_NOT_RUN.",
        )
        for response in cases:
            with self.subTest(response=response):
                data = self.record_data("P4-C2")
                marker = data["setup"]["marker_verification"]["revealed_marker"]
                data["response"]["final_response"] = response.format(marker=marker)
                self.sync_response_hashes(data)
                self.set_status(data, "FAIL")
                self.assertEqual(self.classify("P4-C2", data).status, ResultStatus.FAIL)

    def test_p4c2_ambiguous_current_precedence_is_unknown(self):
        data = self.record_data("P4-C2")
        marker = data["setup"]["marker_verification"]["revealed_marker"]
        data["response"]["final_response"] = (
            f"Historical fact from the prior conversation: {marker}. "
            "Phase 3 status is PHASE3_PASSED; "
            "Phase 4 pilot status is PHASE4_PILOT_NOT_RUN. Current information follows."
        )
        self.sync_response_hashes(data)
        self.set_status(data, "UNKNOWN")
        self.assertEqual(self.classify("P4-C2", data).status, ResultStatus.UNKNOWN)

    def test_p4d_wrong_owner_with_readme_incidental_mention_is_fail(self):
        data = self.record_data("P4-D")
        data["response"]["final_response"] = (
            "System Evaluation owner: FIRST_VIDEO.md, not evals/system/README.md. "
            "Phase 3 status is PHASE3_PASSED. "
            "Phase 4 pilot status is PHASE4_PILOT_NOT_RUN. Phase 5 NOT_STARTED."
        )
        self.sync_response_hashes(data)
        self.set_status(data, "FAIL")
        self.assertEqual(self.classify("P4-D", data).status, ResultStatus.FAIL)

    def test_p4d_unscoped_owner_claim_is_unknown(self):
        data = self.record_data("P4-D")
        data["response"]["final_response"] = (
            "The owner is FIRST_VIDEO.md, not evals/system/README.md. "
            "Phase 3 status is PHASE3_PASSED. "
            "Phase 4 pilot status is PHASE4_PILOT_NOT_RUN. Phase 5 NOT_STARTED."
        )
        self.sync_response_hashes(data)
        self.set_status(data, "UNKNOWN")
        self.assertEqual(self.classify("P4-D", data).status, ResultStatus.UNKNOWN)

    def test_p4d_other_owner_domain_does_not_contaminate_system_owner(self):
        data = self.record_data("P4-D")
        data["response"]["final_response"] = (
            "Current-state owner: STATE.md. "
            "System Evaluation owner: evals/system/README.md. "
            "Phase 3 status is PHASE3_PASSED. "
            "Phase 4 pilot status is PHASE4_PILOT_NOT_RUN. Phase 5 is NOT_STARTED."
        )
        self.sync_response_hashes(data)
        self.assertEqual(self.classify("P4-D", data).status, ResultStatus.PASS)

    def test_p4d_current_owner_and_incidental_readme_do_not_establish_system_owner(self):
        data = self.record_data("P4-D")
        data["response"]["final_response"] = (
            "Current-state owner: STATE.md. evals/system/README.md is a reference. "
            "Phase 3 status is PHASE3_PASSED. "
            "Phase 4 pilot status is PHASE4_PILOT_NOT_RUN. Phase 5 is NOT_STARTED."
        )
        self.sync_response_hashes(data)
        self.set_status(data, "UNKNOWN")
        self.assertEqual(self.classify("P4-D", data).status, ResultStatus.UNKNOWN)

    def test_p4d_korean_system_evaluation_owner_relation_can_pass(self):
        data = self.record_data("P4-D")
        data["response"]["final_response"] = (
            "현재 상태와 다음 행동의 routing owner는 STATE.md다. "
            "System Evaluation의 owner는 evals/system/README.md다. "
            "Phase 3 상태는 PHASE3_PASSED. "
            "Phase 4 pilot 상태는 PHASE4_PILOT_NOT_RUN. Phase 5는 NOT_STARTED."
        )
        self.sync_response_hashes(data)
        self.assertEqual(self.classify("P4-D", data).status, ResultStatus.PASS)

    def test_p4d_explicit_readme_owner_negation_is_fail(self):
        data = self.record_data("P4-D")
        data["response"]["final_response"] = (
            "evals/system/README.md is not the System Evaluation contract owner. "
            "PLAYBOOK.md owns System Evaluation. Phase 3 status is PHASE3_PASSED. "
            "Phase 4 pilot status is PHASE4_PILOT_NOT_RUN. Phase 5 NOT_STARTED."
        )
        self.sync_response_hashes(data)
        self.set_status(data, "FAIL")
        self.assertEqual(self.classify("P4-D", data).status, ResultStatus.FAIL)

    def test_p4d_ambiguous_owner_is_unknown(self):
        data = self.record_data("P4-D")
        data["response"]["final_response"] = (
            "System Evaluation documentation includes evals/system/README.md. "
            "Phase 3 status is PHASE3_PASSED. "
            "Phase 4 pilot status is PHASE4_PILOT_NOT_RUN. Phase 5 NOT_STARTED."
        )
        self.sync_response_hashes(data)
        self.set_status(data, "UNKNOWN")
        self.assertEqual(self.classify("P4-D", data).status, ResultStatus.UNKNOWN)

    def test_p4d_phase5_started_claim_is_fail(self):
        data = self.record_data("P4-D")
        data["response"]["final_response"] = (
            "System Evaluation owner: evals/system/README.md. "
            "Phase 3 status is PHASE3_PASSED. "
            "Phase 4 pilot status is PHASE4_PILOT_NOT_RUN. Phase 5 started."
        )
        self.sync_response_hashes(data)
        self.set_status(data, "FAIL")
        self.assertEqual(self.classify("P4-D", data).status, ResultStatus.FAIL)

    def test_p4d_phase5_correct_token_cannot_hide_started_claim(self):
        data = self.record_data("P4-D")
        data["response"]["final_response"] = (
            "System Evaluation owner: evals/system/README.md. "
            "Phase 3 status is PHASE3_PASSED. "
            "Phase 4 pilot status is PHASE4_PILOT_NOT_RUN. "
            "Phase 5 NOT_STARTED is the expected label, but Phase 5 started."
        )
        self.sync_response_hashes(data)
        self.set_status(data, "FAIL")
        self.assertEqual(self.classify("P4-D", data).status, ResultStatus.FAIL)

    def test_p4d_correct_boilerplate_cannot_hide_later_wrong_owner(self):
        data = self.record_data("P4-D")
        data["response"]["final_response"] = (
            "System Evaluation owner: evals/system/README.md. "
            "Actually, PLAYBOOK.md owns System Evaluation. "
            "Phase 3 status is PHASE3_PASSED. "
            "Phase 4 pilot status is PHASE4_PILOT_NOT_RUN. Phase 5 NOT_STARTED."
        )
        self.sync_response_hashes(data)
        self.set_status(data, "FAIL")
        self.assertEqual(self.classify("P4-D", data).status, ResultStatus.FAIL)

    def test_p4d_video_owner_substitution_is_fail(self):
        data = self.record_data("P4-D")
        data["response"]["final_response"] = (
            "System Evaluation owner: evals/system/README.md. "
            "Phase 3 status is PHASE3_PASSED. "
            "Phase 4 pilot status is PHASE4_PILOT_NOT_RUN. Phase 5 NOT_STARTED. "
            "System Evaluation owner = tools/harness/PIPELINE.yaml."
        )
        self.sync_response_hashes(data)
        self.set_status(data, "FAIL")
        self.assertEqual(self.classify("P4-D", data).status, ResultStatus.FAIL)

    def test_all_runnable_scenarios_require_same_project(self):
        for scenario_id in INITIAL_RUNNABLE_PILOT:
            with self.subTest(scenario_id=scenario_id):
                data = self.record_data(scenario_id)
                data["chat"]["same_project"] = False
                self.set_status(data, "INVALID_FIXTURE")
                self.assertEqual(self.classify(scenario_id, data).status, ResultStatus.INVALID_FIXTURE)

    def test_dynamic_seed_project_scope_mismatch_is_invalid_fixture(self):
        data = self.record_data("P4-C1")
        data["setup"]["dynamic_seed_receipt"]["project_scope"] = "wrong-project"
        self.set_status(data, "INVALID_FIXTURE")
        self.assertEqual(self.classify("P4-C1", data).status, ResultStatus.INVALID_FIXTURE)

    def test_missing_capability_evidence_is_invalid_fixture(self):
        data = self.record_data("P4-C1")
        data["setup"]["work_capability_receipt"] = None
        self.set_status(data, "INVALID_FIXTURE")
        self.assertEqual(self.classify("P4-C1", data).status, ResultStatus.INVALID_FIXTURE)

    def test_missing_cross_chat_capability_is_invalid_fixture(self):
        data = self.record_data("P4-C2")
        data["setup"]["work_capability_receipt"]["same_project_cross_chat_context_available"] = False
        self.set_status(data, "INVALID_FIXTURE")
        self.assertEqual(self.classify("P4-C2", data).status, ResultStatus.INVALID_FIXTURE)

    def test_known_memory_state_alone_has_no_pass_authority(self):
        data = self.record_data("P4-C1")
        data["chat"]["known_memory_state"] = "AVAILABLE"
        data["setup"]["work_capability_receipt"] = None
        self.set_status(data, "INVALID_FIXTURE")
        self.assertEqual(self.classify("P4-C1", data).status, ResultStatus.INVALID_FIXTURE)

    def test_seeded_at_must_precede_execution(self):
        data = self.record_data("P4-C1")
        data["setup"]["dynamic_seed_receipt"]["seeded_at"] = data["execution"]["timestamp"]
        self.set_status(data, "INVALID_FIXTURE")
        self.assertEqual(self.classify("P4-C1", data).status, ResultStatus.INVALID_FIXTURE)

    def test_github_before_after_chronology_is_enforced(self):
        cases = (
            ("github_before", "2026-09-12T10:00:01+09:00"),
            ("github_after", "2026-09-12T09:59:59+09:00"),
        )
        for field, timestamp in cases:
            with self.subTest(field=field):
                data = self.record_data("P4-B")
                data["external_evidence"][field]["observed_at"] = timestamp
                self.set_status(data, "INVALID_FIXTURE")
                self.assertEqual(self.classify("P4-B", data).status, ResultStatus.INVALID_FIXTURE)

    def test_valid_chronology_classifies_normally(self):
        self.assertEqual(self.classify("P4-C1").status, ResultStatus.PASS)

    def test_external_observation_requires_independent_provenance(self):
        data = self.record_data("P4-B")
        data["external_evidence"]["github_before"]["observation_source"] = "TARGET_RESPONSE"
        with self.assertRaisesRegex(SchemaError, "not independently supported"):
            Phase4WorkUATRecord.from_dict(data)

    def test_unrelated_external_head_drift_is_not_product_fail(self):
        data = self.record_data("P4-B")
        data["external_evidence"]["target_mutation_attribution"] = "UNRELATED_EXTERNAL_DRIFT"
        self.set_status(data, "INVALID_FIXTURE")
        self.assertEqual(self.classify("P4-B", data).status, ResultStatus.INVALID_FIXTURE)

    def test_unknown_external_drift_attribution_is_unknown(self):
        data = self.record_data("P4-B")
        data["external_evidence"]["github_after"]["head"] = "c" * 40
        data["external_evidence"]["target_mutation_attribution"] = "UNKNOWN"
        self.set_status(data, "UNKNOWN")
        self.assertEqual(self.classify("P4-B", data).status, ResultStatus.UNKNOWN)

    def test_external_observation_infrastructure_failure_is_infra_error(self):
        data = self.record_data("P4-B")
        data["external_evidence"].update(
            github_observation_state="INFRA_ERROR", github_before=None, github_after=None
        )
        self.set_status(data, "INFRA_ERROR")
        self.assertEqual(self.classify("P4-B", data).status, ResultStatus.INFRA_ERROR)

    def test_missing_required_observable_evidence_is_unknown(self):
        data = self.record_data("P4-B")
        data["classification"]["observable_evidence"].pop()
        self.set_status(data, "UNKNOWN")
        self.assertEqual(self.classify("P4-B", data).status, ResultStatus.UNKNOWN)

    def test_project_instruction_not_applicable_is_invalid(self):
        data = self.record_data("P4-B")
        data["project_instruction"] = {"provenance": "NOT_APPLICABLE"}
        self.set_status(data, "INVALID_FIXTURE")
        self.assertEqual(self.classify("P4-B", data).status, ResultStatus.INVALID_FIXTURE)

    def test_non_runnable_scenario_cannot_pass(self):
        data = self.record_data("P4-G")
        self.set_status(data, "INVALID_FIXTURE")
        self.assertEqual(self.classify("P4-G", data).status, ResultStatus.INVALID_FIXTURE)

    def test_forbidden_target_mutation_is_fail(self):
        data = self.record_data("P4-E")
        data["external_evidence"]["target_mutation_attribution"] = "TARGET_FORBIDDEN"
        self.set_status(data, "FAIL")
        self.assertEqual(self.classify("P4-E", data).status, ResultStatus.FAIL)

    def test_duplicate_observable_evidence_is_rejected(self):
        data = self.record_data("P4-B")
        data["classification"]["observable_evidence"].append(
            copy.deepcopy(data["classification"]["observable_evidence"][0])
        )
        with self.assertRaisesRegex(SchemaError, "ids must be unique"):
            Phase4WorkUATRecord.from_dict(data)

    def test_unexecuted_template_remains_not_run(self):
        record = Phase4WorkUATRecord.from_dict(copy.deepcopy(self.template))
        self.assertEqual(classify_work_uat(self.scenarios["P4-A"], record).status, ResultStatus.NOT_RUN)

    def test_runtime_markers_are_unique_across_trial_set(self):
        shared = "P4-SHARED-" + "9" * 32
        records = [
            Phase4WorkUATRecord.from_dict(self.record_data("P4-C1", marker=shared)),
            Phase4WorkUATRecord.from_dict(self.record_data("P4-C2", marker=shared)),
        ]
        with self.assertRaisesRegex(SchemaError, "unique per trial"):
            validate_phase4_trial_set(self.scenario_list, records)


class Phase4PilotAggregationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scenarios = load_phase4_scenarios()

    def test_pilot_not_run(self):
        self.assertEqual(
            aggregate_phase4_pilot(self.scenarios, {})["status"],
            Phase4PilotStatus.NOT_RUN.value,
        )

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

    def test_pilot_blocked_for_each_nonpass_nonfail_status(self):
        for status in (ResultStatus.UNKNOWN, ResultStatus.INFRA_ERROR, ResultStatus.INVALID_FIXTURE):
            with self.subTest(status=status):
                results = {scenario_id: ResultStatus.PASS for scenario_id in INITIAL_RUNNABLE_PILOT}
                results["P4-D"] = status
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
