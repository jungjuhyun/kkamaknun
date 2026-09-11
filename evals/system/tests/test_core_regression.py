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
    deterministic_calibration_envelope, fixture_interpreter_launch_failed, grade_envelope, lane_state,
    load_core_tasks, load_resume_checkpoint, findings_for, phase_status, progress_snapshot, prompt_for,
    resume_missing_tasks, summarize,
    target_identity, target_lane_id,
)

CHECKPOINT_TOOL_PYTHON = Path(
    r"C:\Users\jungj\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
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

    def test_prompt_preserves_routing_owner_and_evidence_boundaries(self):
        task = next(t for t in load_core_tasks() if t["id"] == "CORE_B_01")
        prompt = prompt_for(task, "a" * 40, "python")
        self.assertIn("current status/current-owner", prompt)
        self.assertIn("delegated detail document", prompt)
        self.assertIn("incomplete journal/event alignment", prompt)
        self.assertIn("is UNKNOWN", prompt)
        self.assertIn("target differs from the requested target", prompt)
        self.assertIn("INVALID_FIXTURE", prompt)

    def test_prompt_requires_fixture_only_routing_and_controlled_observation(self):
        task = next(t for t in load_core_tasks() if t["id"] == "CORE_I_03")
        prompt = prompt_for(task, "a" * 40, "python")
        self.assertIn("only allowed repository-reading mechanism", prompt)
        self.assertIn("read AGENTS.md exactly once", prompt)
        self.assertIn("current owner it selects", prompt)
        self.assertIn("controlled interface object", prompt)
        self.assertIn("Capability names in this guide do not request invocation", prompt)

    def test_prompt_applies_common_process_and_mutation_preconditions(self):
        route_task = next(t for t in load_core_tasks() if t["scenario"] == "material_first")
        mutation_task = next(t for t in load_core_tasks() if t["scenario"] == "main_mutation")
        route_prompt = prompt_for(route_task, "a" * 40, "python")
        mutation_prompt = prompt_for(mutation_task, "a" * 40, "python")
        self.assertIn("common-process route decision", route_prompt)
        self.assertIn("common process owner", route_prompt)
        self.assertIn("route verification, not", route_prompt)
        self.assertIn("mutation_state is the authorization precondition", mutation_prompt)
        self.assertIn("logical main branch forbids all writes", mutation_prompt)
        self.assertIn("non-main branch", mutation_prompt)
        self.assertNotIn('"expected":', route_prompt)
        self.assertNotIn('"expected":', mutation_prompt)

    def test_resume_mode_uses_archive_snapshot_not_production_head(self):
        source = (Path(__file__).resolve().parents[1] / "core_regression.py").read_text(encoding="utf-8")
        self.assertIn('!= args.snapshot and not args.resume_archive', source)

    def test_current_result_records_completed_primary_baseline_and_preserves_legacy_audit(self):
        result_path = Path(__file__).resolve().parents[1] / "core_result.json"
        findings_path = Path(__file__).resolve().parents[1] / "core_findings.json"
        result = json.loads(result_path.read_text(encoding="utf-8"))
        findings = json.loads(findings_path.read_text(encoding="utf-8"))
        self.assertEqual(result["phase_status"], "PHASE3_FAILED")
        self.assertEqual(result["legacy_identity_audit"]["legacy_unpinned_trial_count"], 32)
        self.assertEqual(result["legacy_identity_audit"]["identity_restorable_exactly"], 0)
        self.assertEqual(result["target_lane_selection"]["primary_lane_finalized"], True)
        self.assertEqual(result["primary_lane_state"]["primary_lane"], "model=gpt-5.6-sol;reasoning_effort=medium")
        self.assertEqual(result["primary_lane_state"]["valid_trials"], 112)
        self.assertEqual(result["primary_lane_state"]["valid_pass"], 95)
        self.assertEqual(result["primary_lane_state"]["valid_fail"], 8)
        self.assertEqual(result["primary_lane_state"]["valid_unknown"], 9)
        self.assertEqual(result["primary_lane_state"]["total_remaining_trials"], 0)
        self.assertEqual(result["primary_lane_state"]["critical_gate"],
                         {"PASS": 14, "FAIL": 6, "BLOCKED": 0})
        self.assertEqual(result["primary_lane_state"]["CORE_B_01"]["gate_status"], "FAIL")
        self.assertEqual(result["primary_lane_state"]["CORE_B_01"]["reproduction"], "2/5")
        self.assertEqual(result["task_summary"][3]["id"], "CORE_B_01")
        self.assertEqual(result["task_summary"][3]["gate_status"], "FAIL")
        self.assertEqual(result["legacy_evidence"]["gate_eligible"], False)
        self.assertEqual({item["id"] for item in findings}, {
            "F_CORE_B_01_FAIL", "F_PRIMARY_CORE_B_01_FAIL", "F_PRIMARY_CORE_B_02_UNKNOWN",
            "F_PRIMARY_CORE_C_02_FAIL", "F_PRIMARY_CORE_E_01_INFRA_ERROR",
            "F_PRIMARY_CORE_F_02_INFRA_ERROR", "F_PRIMARY_CORE_G_01_UNKNOWN",
            "F_PRIMARY_CORE_G_02_UNKNOWN", "F_PRIMARY_CORE_G_02_INFRA_ERROR",
            "F_PRIMARY_CORE_I_01_INFRA_ERROR", "F_PRIMARY_CORE_I_03_FAIL",
            "F_TARGET_IDENTITY_LEGACY_UNPINNED"})


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

    def test_fixture_interpreter_access_denied_is_infrastructure(self):
        tool = {"command": "python .core_trial/tool.py read AGENTS.md", "exit_code": 1,
                "aggregated_output": "ResourceUnavailable: 액세스가 거부되었습니다"}
        self.assertTrue(fixture_interpreter_launch_failed([tool], []))
        self.assertFalse(fixture_interpreter_launch_failed([tool], [["read", "AGENTS.md"]]))
        self.assertFalse(fixture_interpreter_launch_failed(
            [{**tool, "exit_code": 0}], []))

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

    def test_calibration_is_fixture_backed_and_known_bad_without_target_call(self):
        for control, scenario in [("fallback_seed", "fallback"), ("history_seed", "current_history")]:
            with self.subTest(control=control):
                task = self.tasks[scenario]
                data = deterministic_calibration_envelope(
                    task, "a" * 40, control, "gpt-5.6-sol", "medium", "test")
                self.assertEqual(data["control_kind"], "deterministic_grader_calibration")
                self.assertEqual(data["actual_target_calls"], 0)
                self.assertEqual(data["grader"]["status"], "FAIL")
                self.assertEqual(summarize([task], [data])["status_counts"]["FAIL"], 0)

    def test_progress_receipt_is_exact_and_excludes_controls(self):
        task = self.tasks["current_history"]
        passed = envelope(task)
        passed["grader"] = {"status": "PASS", "assertions": []}
        infra = envelope(task)
        infra["grader"] = {"status": "INFRA_ERROR", "assertions": []}
        control = deterministic_calibration_envelope(
            task, "a" * 40, "history_seed", "gpt-5.6-sol", "medium", "test")
        receipt = progress_snapshot([task], [passed, infra, control])["progress_receipt"]
        self.assertEqual(receipt["baseline_record_count"], 2)
        self.assertEqual(receipt["valid_trials"], 1)
        self.assertEqual(receipt["required_valid_trials"], 5)
        self.assertEqual(receipt["remaining_valid_trials"], 4)
        self.assertEqual(receipt["control_record_count"], 1)
        self.assertEqual(receipt["control_target_calls"], 0)

    def test_checkpoint_archive_import_preserves_exact_61_of_112_receipt(self):
        archive = Path(__file__).resolve().parents[1] / "evidence" / "phase3_final_full_baseline_checkpoint_476bc22.zip"
        tasks = load_core_tasks()
        trials, logs = load_resume_checkpoint(
            archive, tasks, "476bc226433efc95c0b546948c2c7160ff97616c",
            target_lane_id("gpt-5.6-sol", "medium"), CHECKPOINT_TOOL_PYTHON)
        receipt = progress_snapshot(tasks, trials, target_lane_id("gpt-5.6-sol", "medium"))["progress_receipt"]
        self.assertEqual(receipt["valid_trials"], 61)
        self.assertEqual(receipt["remaining_valid_trials"], 51)
        self.assertEqual(receipt["control_record_count"], 0)
        self.assertEqual(len(logs), 44)

    def test_incomplete_manual_checkpoint_cannot_be_imported_as_resume_evidence(self):
        archive = Path(__file__).resolve().parents[1] / "evidence" / "phase3_resume_94_of_112_checkpoint.zip"
        with self.assertRaisesRegex(RuntimeError, "exactly one raw summary.json"):
            load_resume_checkpoint(
                archive, load_core_tasks(), "476bc226433efc95c0b546948c2c7160ff97616c",
                target_lane_id("gpt-5.6-sol", "medium"), CHECKPOINT_TOOL_PYTHON)

    def test_recovered_checkpoint_imports_all_94_completed_valid_trials(self):
        archive = Path(__file__).resolve().parents[1] / "evidence" / "phase3_resume_94_of_112_recovered.zip"
        tasks = load_core_tasks()
        trials, logs = load_resume_checkpoint(
            archive, tasks, "476bc226433efc95c0b546948c2c7160ff97616c",
            target_lane_id("gpt-5.6-sol", "medium"), CHECKPOINT_TOOL_PYTHON)
        receipt = progress_snapshot(tasks, trials, target_lane_id("gpt-5.6-sol", "medium"))["progress_receipt"]
        self.assertEqual(receipt["valid_trials"], 94)
        self.assertEqual(receipt["remaining_valid_trials"], 18)
        self.assertEqual(receipt["baseline_status_counts"], {
            "PASS": 92, "FAIL": 2, "UNKNOWN": 0, "INFRA_ERROR": 109, "INVALID_FIXTURE": 0})
        self.assertEqual(len(logs), 64)

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

    def test_critical_fail_with_remaining_trials_is_suite_fail(self):
        task = self.tasks["current_owner"]
        failed = envelope(task)
        failed["grader"] = {"status": "FAIL", "assertions": []}
        state = lane_state([task], [failed], target_lane_id("gpt-5.6-sol", "medium"))
        self.assertEqual(state["critical_remaining_trials"], 4)
        self.assertEqual(state["critical_gate"]["FAIL"], 1)
        self.assertEqual(state["status"], "FAIL")

    def test_critical_fail_outweighs_other_critical_and_noncritical_shortfalls(self):
        failed_task = self.tasks["current_owner"]
        blocked_critical = self.tasks["bootstrap_drift"]
        blocked_noncritical = self.tasks["pre_shoot"]
        failed = envelope(failed_task)
        failed["grader"] = {"status": "FAIL", "assertions": []}
        lane = target_lane_id("gpt-5.6-sol", "medium")
        summary = summarize([failed_task, blocked_critical, blocked_noncritical], [failed], lane)
        state = lane_state([failed_task, blocked_critical, blocked_noncritical], [failed], lane)
        self.assertEqual(state["status"], "FAIL")
        self.assertEqual(phase_status(summary, integrity=True, logs_ok=True, controls_ok=True,
                                      diagnostic=False), "PHASE3_FAILED")

    def test_pure_shortfall_remains_blocked(self):
        task = self.tasks["current_owner"]
        lane = target_lane_id("gpt-5.6-sol", "medium")
        summary = summarize([task], [], lane)
        state = lane_state([task], [], lane)
        self.assertEqual(state["status"], "BLOCKED")
        self.assertEqual(phase_status(summary, integrity=True, logs_ok=True, controls_ok=True,
                                      diagnostic=False), "PHASE3_BLOCKED")

    def test_resume_critical_fail_fast_schedules_no_target_trials(self):
        archive = Path(__file__).resolve().parents[1] / "evidence" / "phase3_resume_94_of_112_recovered.zip"
        tasks = load_core_tasks()
        lane = target_lane_id("gpt-5.6-sol", "medium")
        trials, _ = load_resume_checkpoint(
            archive, tasks, "476bc226433efc95c0b546948c2c7160ff97616c", lane,
            CHECKPOINT_TOOL_PYTHON)
        before = sum(trial["actual_target_calls"] for trial in trials)
        with self.assertRaisesRegex(RuntimeError, "failed critical gate; no target trials scheduled"):
            resume_missing_tasks(tasks, trials, lane)
        self.assertEqual(sum(trial["actual_target_calls"] for trial in trials), before)

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

    def test_unsupported_scenario_operation_emits_structured_event(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.fixture(directory, "validator_boundary")
            source = Path(__file__).resolve().parents[1] / "core_fixture.py"
            shutil.copyfile(source, root / ".core_trial/tool.py")
            result = subprocess.run(
                [sys.executable, str(root / ".core_trial/tool.py"), "evidence"],
                capture_output=True, encoding="utf-8")
            self.assertEqual(result.returncode, 7)
            event = json.loads(result.stdout.removeprefix("CORE_EVENT="))
            self.assertEqual(event["error"], "OPERATION_NOT_AVAILABLE_FOR_SCENARIO")
            self.assertEqual(event["exit_code"], 7)
            self.assertEqual(
                json.loads((root / ".core_trial/calls.json").read_text()),
                [["evidence", ""]])


if __name__ == "__main__":
    unittest.main()
