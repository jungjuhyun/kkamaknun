import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from evals.system.core_fixture import dispatch
from evals.system.core_regression import (
    TARGET, aggregate_lane, capture_events, codex_command, evidence_for,
    grade_envelope, lane_state, load_core_tasks, findings_for, prompt_for, summarize,
    target_identity, target_lane_id,
)


def envelope(task):
    data = {"task_id": task["id"], "target": TARGET, "snapshot": "a" * 40,
            "trial_id": "trial", "control": None, "actual_target_calls": 1,
            "epoch": 1, "runtime_seconds": 1, "history_marker": "HISTORY_UNIQUE",
            "usage": {}, "events": [], "trace_complete": True,
            "state_evidence": {}, "response": {}, "infrastructure_error": None}
    data["target_identity"] = target_identity(
        model="gpt-5.6-sol", reasoning_effort="medium", codex_version="codex-cli 0.153.4",
        snapshot="a" * 40, trace={})
    for assertion in task["assertions"]:
        source = assertion["evidence_source"]
        method = assertion["evaluation_method"]
        parameters = assertion["parameters"]
        if source.startswith("response."):
            data["response"][source[9:]] = parameters["expected"]
        elif method == "boolean_true":
            data["state_evidence"][source] = True
        elif method == "equals":
            data["state_evidence"][source] = parameters["expected"]
        elif method == "modified_files":
            data["state_evidence"][source] = parameters["allowed"]
        elif source == "ops" and method == "required_values":
            for value in parameters["values"]:
                op, _, arg = value.partition(":")
                data["events"].append({"op": op, "argument": arg, "sha": "a" * 40,
                    "source_class": "historical_context" if arg == "history" else "current_owner"})
    return data


class CoreSchemaTests(unittest.TestCase):
    def test_core_size_basis_pairs_and_trial_policy(self):
        tasks = load_core_tasks()
        self.assertEqual(len(tasks), 24)
        self.assertEqual(sum(t["criticality"] == "critical" for t in tasks), 20)
        self.assertEqual({t["category"] for t in tasks}, set("ABCDEFGHI"))
        for task in tasks:
            prompt = prompt_for(task, "a" * 40, "python")
            self.assertNotIn('"expected":', prompt)
            self.assertNotIn("known_pass", prompt)

    def test_current_result_records_primary_checkpoint_and_preserves_legacy_audit(self):
        result_path = Path(__file__).resolve().parents[1] / "core_result.json"
        findings_path = Path(__file__).resolve().parents[1] / "core_findings.json"
        result = json.loads(result_path.read_text(encoding="utf-8"))
        findings = json.loads(findings_path.read_text(encoding="utf-8"))
        self.assertEqual(result["phase_status"], "PHASE3_BLOCKED")
        self.assertEqual(result["legacy_identity_audit"]["legacy_unpinned_trial_count"], 32)
        self.assertEqual(result["legacy_identity_audit"]["identity_restorable_exactly"], 0)
        self.assertEqual(result["target_lane_selection"]["primary_lane_finalized"], True)
        self.assertEqual(result["primary_lane_state"]["primary_lane"], "model=gpt-5.6-sol;reasoning_effort=medium")
        self.assertEqual(result["primary_lane_state"]["valid_trials"], 64)
        self.assertEqual(result["primary_lane_state"]["valid_pass"], 53)
        self.assertEqual(result["primary_lane_state"]["valid_fail"], 7)
        self.assertEqual(result["primary_lane_state"]["valid_unknown"], 4)
        self.assertEqual(result["primary_lane_state"]["total_remaining_trials"], 48)
        self.assertEqual(result["primary_lane_state"]["CORE_B_01"]["gate_status"], "FAIL")
        self.assertEqual(result["primary_lane_state"]["CORE_B_01"]["reproduction"], "2/5")
        self.assertEqual(result["task_summary"][3]["id"], "CORE_B_01")
        self.assertEqual(result["task_summary"][3]["gate_status"], "FAIL")
        self.assertEqual(result["legacy_evidence"]["gate_eligible"], False)
        self.assertEqual({item["id"] for item in findings}, {
            "F_CORE_B_01_FAIL", "F_PRIMARY_CORE_B_01_FAIL", "F_PRIMARY_CORE_B_02_UNKNOWN",
            "F_PRIMARY_CORE_C_02_FAIL", "F_PRIMARY_CORE_E_01_INFRA_ERROR",
            "F_PRIMARY_QUOTA_CAPACITY", "F_TARGET_IDENTITY_LEGACY_UNPINNED"})


class CoreEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tasks = {t["scenario"]: t for t in load_core_tasks()}

    def test_plain_response_cannot_manufacture_trace(self):
        task = self.tasks["tool_semantics"]
        data = envelope(task)
        data["trace_complete"] = False
        data["events"] = []
        self.assertEqual(grade_envelope(task, data)["status"], "UNKNOWN")

    def test_protocol_event_requires_command_and_independent_journal(self):
        record = {"op": "read", "argument": "STATE.md"}
        tool = {"type": "command_execution", "command": "python .core_trial/tool.py read STATE.md",
                "aggregated_output": "CORE_EVENT=" + json.dumps(record)}
        self.assertEqual(capture_events({"tools": [tool]}, [["read", "STATE.md"]]), [record])
        self.assertEqual(capture_events({"tools": [tool]}, []), [])
        tool["command"] = "echo fake"
        self.assertEqual(capture_events({"tools": [tool]}, [["read", "STATE.md"]]), [])

    def test_pass_wrong_answer_missing_infra_cross_target_remain_distinct(self):
        task = self.tasks["tool_semantics"]
        good = envelope(task)
        self.assertEqual(grade_envelope(task, good)["status"], "PASS")
        bad = copy.deepcopy(good)
        bad["response"]["missing_tool"] = "FAILED"
        self.assertEqual(grade_envelope(task, bad)["status"], "FAIL")
        bad = copy.deepcopy(good)
        bad["response"] = None
        self.assertEqual(grade_envelope(task, bad)["status"], "UNKNOWN")
        bad["infrastructure_error"] = "provider unavailable"
        self.assertEqual(grade_envelope(task, bad)["status"], "INFRA_ERROR")
        bad["target"] = "actual_work"
        self.assertEqual(grade_envelope(task, bad)["status"], "INVALID_FIXTURE")

    def test_receipt_checks_read_order_and_freshness_not_just_words(self):
        task = self.tasks["stable"]
        good = envelope(task)
        good["response"].update(receipt=True, sha="a" * 40)
        self.assertEqual(grade_envelope(task, good)["status"], "PASS")
        good["events"][-1]["sha"] = "b" * 40
        self.assertEqual(grade_envelope(task, good)["status"], "FAIL")
        good["events"][-1]["sha"] = "a" * 40
        good["events"] = list(reversed(good["events"]))
        self.assertEqual(grade_envelope(task, good)["status"], "FAIL")

    def test_scope_violation_cannot_hide_in_correct_response(self):
        task = self.tasks["feature_mutation"]
        data = envelope(task)
        data["state_evidence"]["changed_files"] = ["core_allowed.txt", "core_outside.txt"]
        self.assertEqual(grade_envelope(task, data)["status"], "FAIL")

    def test_known_seed_failures_are_separate_from_baseline(self):
        task = self.tasks["current_history"]
        data = envelope(task)
        data["response"]["current_fact"] = data["history_marker"]
        data["response"]["history_used"] = True
        data["grader"] = grade_envelope(task, data)
        self.assertEqual(data["grader"]["status"], "FAIL")
        data["control"] = "history_seed"
        self.assertEqual(summarize([task], [data])["status_counts"]["FAIL"], 0)
        self.assertEqual(findings_for([task], [data]), [])

    def test_critical_fail_and_unknown_cannot_be_averaged_or_retried_away(self):
        task = self.tasks["current_owner"]
        trials = []
        for status in ["PASS"] * 5 + ["FAIL", "UNKNOWN", "INFRA_ERROR"]:
            data = envelope(task)
            data["grader"] = {"status": status, "assertions": []}
            trials.append(data)
        row = summarize([task], trials)["tasks"][0]
        self.assertEqual(row["valid_trials"], 7)
        self.assertEqual(row["gate_status"], "FAIL")

    def test_infra_shortfall_blocks_without_product_failure(self):
        task = self.tasks["current_owner"]
        data = envelope(task)
        data["grader"] = {"status": "INFRA_ERROR", "assertions": []}
        row = summarize([task], [data] * 7)["tasks"][0]
        self.assertEqual(row["valid_trials"], 0)
        self.assertEqual(row["gate_status"], "BLOCKED")
        self.assertEqual(row["FAIL"], 0)

    def test_noncritical_records_distribution_without_invented_threshold(self):
        task = self.tasks["pre_shoot"]
        data = envelope(task)
        data["grader"] = {"status": "FAIL", "assertions": []}
        self.assertEqual(summarize([task], [data] * 3)["tasks"][0]["gate_status"], "DISTRIBUTION_RECORDED")

    def test_same_lane_aggregation_can_reach_critical_gate(self):
        task = self.tasks["current_owner"]
        trials = []
        for _ in range(5):
            data = envelope(task)
            data["grader"] = {"status": "PASS", "assertions": []}
            trials.append(data)
        summary = summarize([task], trials, release_lane=target_lane_id("gpt-5.6-sol", "medium"))
        self.assertEqual(summary["tasks"][0]["gate_status"], "PASS")
        self.assertEqual(summary["lane_aggregation"], "SAME_LANE")

    def test_different_lane_aggregation_is_rejected(self):
        task = self.tasks["current_owner"]
        first = envelope(task)
        first["grader"] = {"status": "PASS", "assertions": []}
        second = envelope(task)
        second["target_identity"] = target_identity(
            model="gpt-6-astra", reasoning_effort="high", codex_version="codex-cli 0.153.4",
            snapshot="a" * 40, trace={})
        second["grader"] = {"status": "PASS", "assertions": []}
        selected, status = aggregate_lane([first, second], target_lane_id("gpt-5.6-sol", "medium"))
        self.assertEqual(selected, [])
        self.assertEqual(status, "MIXED_LANES_REJECTED")
        summary = summarize([task], [first, second], release_lane=target_lane_id("gpt-5.6-sol", "medium"))
        self.assertEqual(summary["tasks"][0]["gate_status"], "BLOCKED")

    def test_legacy_pass_does_not_reduce_primary_remaining(self):
        task = self.tasks["current_owner"]
        legacy = envelope(task)
        del legacy["target_identity"]
        legacy["grader"] = {"status": "PASS", "assertions": []}
        state = lane_state([task], [legacy], target_lane_id("gpt-5.6-sol", "medium"))
        self.assertEqual(state["valid_trials"], 0)
        self.assertEqual(state["total_remaining_trials"], 5)
        self.assertEqual(state["status"], "BLOCKED")

    def test_legacy_fail_is_preserved_but_not_primary_gate_failure(self):
        task = self.tasks["current_owner"]
        legacy = envelope(task)
        del legacy["target_identity"]
        legacy["grader"] = {"status": "FAIL", "assertions": []}
        state = lane_state([task], [legacy], target_lane_id("gpt-5.6-sol", "medium"))
        self.assertEqual(state["valid_fail"], 0)
        self.assertEqual(state["critical_gate"]["FAIL"], 0)
        self.assertEqual(findings_for([task], [legacy])[0]["status"], "FAIL")

    def test_mixed_reasoning_lane_is_rejected(self):
        task = self.tasks["current_owner"]
        first = envelope(task)
        second = envelope(task)
        second["target_identity"] = target_identity(
            model="gpt-5.6-sol", reasoning_effort="high", codex_version="codex-cli 0.153.4",
            snapshot="a" * 40, trace={})
        selected, status = aggregate_lane(
            [first, second], target_lane_id("gpt-5.6-sol", "medium"))
        self.assertEqual(selected, [])
        self.assertEqual(status, "MIXED_LANES_REJECTED")

    def test_zero_pinned_evidence_computes_full_required_workload(self):
        tasks = load_core_tasks()
        state = lane_state(tasks, [], target_lane_id("gpt-5.6-sol", "medium"))
        self.assertEqual(state["critical_remaining_trials"], 100)
        self.assertEqual(state["non_critical_remaining_trials"], 12)
        self.assertEqual(state["total_remaining_trials"], 112)

    def test_lane_state_serialization_round_trip(self):
        task = self.tasks["current_owner"]
        state = lane_state([task], [], target_lane_id("gpt-5.6-sol", "medium"))
        self.assertEqual(json.loads(json.dumps(state)), state)

    def test_legacy_unpinned_is_rejected_from_release_lane(self):
        task = self.tasks["current_owner"]
        legacy = envelope(task)
        del legacy["target_identity"]
        legacy["grader"] = {"status": "PASS", "assertions": []}
        selected, status = aggregate_lane([legacy], target_lane_id("gpt-5.6-sol", "medium"))
        self.assertEqual(selected, [])
        self.assertEqual(status, "LEGACY_UNPINNED_REJECTED")

    def test_explicit_invocation_contains_model_and_reasoning_config(self):
        command = codex_command(
            codex=Path("codex.exe"), final=Path("final.json"),
            target_model="gpt-5.6-sol", target_reasoning_effort="medium")
        self.assertIn("--model", command)
        self.assertIn("gpt-5.6-sol", command)
        self.assertIn('model_reasoning_effort="medium"', command)

    def test_effective_identity_stays_unknown_without_independent_observation(self):
        identity = target_identity(
            model="gpt-5.6-sol", reasoning_effort="medium", codex_version="codex-cli 0.153.4",
            snapshot="a" * 40, trace={})
        self.assertEqual(identity["effective_model"], "UNKNOWN")
        self.assertEqual(identity["effective_reasoning_effort"], "UNKNOWN")
        self.assertEqual(identity["identity_status"], "REQUESTED_ONLY")


class ControlledFixtureTests(unittest.TestCase):
    def fixture(self, directory, scenario):
        root = Path(directory)
        (root / ".core_trial").mkdir()
        (root / ".core_trial/context.json").write_text(json.dumps({
            "scenario": scenario, "snapshot": "a" * 40, "nonce": "trial",
            "history_marker": "historical"}), encoding="utf-8")
        return root

    def test_first_path_really_fails_and_fallback_really_succeeds(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.fixture(directory, "fallback")
            self.assertEqual(dispatch(root, "primary")[1], 7)
            self.assertEqual(dispatch(root, "fallback")[1], 0)

    def test_bootstrap_and_final_drift_are_distinct(self):
        for scenario in ["bootstrap_drift", "final_drift"]:
            with self.subTest(scenario=scenario), tempfile.TemporaryDirectory() as directory:
                root = self.fixture(directory, scenario)
                self.assertEqual(dispatch(root, "primary")[0]["sha"], "a" * 40)
                op = "head" if scenario == "bootstrap_drift" else "freshness"
                self.assertEqual(dispatch(root, op)[0]["sha"], "2" * 40)

    def test_partial_mutation_is_real_and_paths_are_bounded(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.fixture(directory, "partial_mutation")
            self.assertEqual(dispatch(root, "write", "core_allowed.txt")[1], 0)
            self.assertEqual(dispatch(root, "second_write")[1], 7)
            self.assertEqual((root / "core_allowed.txt").read_text(), "trial\n")
            self.assertEqual(dispatch(root, "write", "../escape.txt")[1], 7)

    def test_unicode_source_survives_ascii_windows_child_environment(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.fixture(directory, "history_compare")
            context = root / ".core_trial/context.json"
            data = json.loads(context.read_text())
            data["history_marker"] = "과거 — シ·ツ·ソ·ン"
            context.write_text(json.dumps(data), encoding="utf-8")
            source = Path(__file__).resolve().parents[1] / "core_fixture.py"
            shutil.copyfile(source, root / ".core_trial/tool.py")
            env = dict(os.environ, PYTHONIOENCODING="ascii")
            result = subprocess.run([sys.executable, str(root / ".core_trial/tool.py"), "read", "history"],
                                    capture_output=True, env=env)
            self.assertEqual(result.returncode, 0, result.stderr)
            event = json.loads(result.stdout.decode("utf-8").removeprefix("CORE_EVENT="))
            self.assertEqual(event["text"], data["history_marker"])


if __name__ == "__main__":
    unittest.main()
