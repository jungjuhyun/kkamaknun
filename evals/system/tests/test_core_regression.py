import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zipfile

import evals.system.core_regression as core_regression
from evals.system.core_fixture import dispatch
from evals.system.core_regression import (
    TARGET, aggregate_lane, capture_events, codex_command, controlled_fixture_event_pairs, evidence_for,
    deterministic_calibration_envelope, fixture_command_infrastructure_failed, grade_envelope, lane_state,
    export_result, fixture_trace_complete, load_core_tasks, load_resume_checkpoint, load_surrogate_contract_release_seed,
    historical_seed_ids_from_provenance, materialize_inherited_current_artifacts,
    findings_for, phase_status, progress_snapshot, prompt_for,
    resume_missing_tasks, run_missing_with_bounded_infra, run_suite, summarize, validate_scheduling_ledger,
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
        self.assertIn("read STATE.md from\nbeginning to end exactly", prompt)
        self.assertIn("every additional owner the AGENTS routing requires", prompt)
        self.assertIn("controlled interface object", prompt)
        self.assertIn("Capability names in this guide do not request invocation", prompt)

    def test_common_surrogate_bootstrap_sequence_matches_project_contract(self):
        bootstrap_scenarios = ["stable", "bootstrap_drift", "final_drift", "mixed_sha", "fallback", "owner_failure"]
        tasks = {task["scenario"]: task for task in load_core_tasks()}
        sequence = [
            "establish the OPEN PR's current immutable snapshot SHA first",
            "read STATE.md from\nbeginning to end exactly",
            "read AGENTS.md exactly once",
            "every additional owner the AGENTS routing requires",
            "Recheck selector head and final freshness only after",
            "Only issue READY or any success receipt after the complete",
        ]
        for scenario in bootstrap_scenarios:
            with self.subTest(scenario=scenario):
                prompt = prompt_for(tasks[scenario], "a" * 40, "python")
                positions = [prompt.index(step) for step in sequence]
                self.assertEqual(positions, sorted(positions))
                self.assertIn("requires at that same SHA", prompt)
                self.assertIn("restart bootstrap from the new head", prompt)
                self.assertIn("fail closed with BLOCKED and no success receipt", prompt)
                self.assertNotIn("read AGENTS.md exactly once through the fixture, then read the current owner", prompt)

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

    def test_precreated_mutable_journal_accumulates_without_replacing_fixture_integrity(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fixture = root / ".core_trial"
            fixture.mkdir()
            tool_path = Path(__file__).resolve().parents[1] / "core_fixture.py"
            shutil.copyfile(tool_path, fixture / "tool.py")
            (fixture / "context.json").write_text(json.dumps({
                "scenario": "stable", "snapshot": "a" * 40, "nonce": "trial",
                "history_marker": "historical"}), encoding="utf-8")
            immutable = {name: hashlib.sha256((fixture / name).read_bytes()).hexdigest()
                         for name in ["tool.py", "context.json"]}
            (fixture / "calls.json").write_text("[]", encoding="utf-8")
            self.assertEqual(dispatch(root, "primary")[1], 0)
            self.assertEqual(dispatch(root, "head")[1], 0)
            self.assertEqual(json.loads((fixture / "calls.json").read_text()), [["primary", ""], ["head", ""]])
            self.assertEqual(immutable, {name: hashlib.sha256((fixture / name).read_bytes()).hexdigest()
                                         for name in immutable})
            (fixture / "calls.json").write_text("not-json", encoding="utf-8")
            with self.assertRaises(json.JSONDecodeError):
                dispatch(root, "freshness")

    def test_windows_journal_acl_provisioning_is_limited_to_the_mutable_journal(self):
        with tempfile.TemporaryDirectory() as directory, \
                patch("evals.system.core_regression.os.name", "nt"), \
                patch("evals.system.core_regression.subprocess.run") as run:
            journal = Path(directory) / "calls.json"
            run.return_value = SimpleNamespace(returncode=0)
            core_regression.grant_fixture_journal_write(journal)
            self.assertEqual(run.call_args.args[0],
                             ["icacls", str(journal), "/grant", "CodexSandboxUsers:(M)"])

    def test_fixture_command_access_failures_are_infrastructure(self):
        tool = {"command": "python .core_trial/tool.py read AGENTS.md", "exit_code": 1,
                "aggregated_output": "ResourceUnavailable: 액세스가 거부되었습니다"}
        self.assertTrue(fixture_command_infrastructure_failed([tool], []))
        self.assertFalse(fixture_command_infrastructure_failed([tool], [["read", "AGENTS.md"]]))
        self.assertFalse(fixture_command_infrastructure_failed(
            [{**tool, "exit_code": 0}], []))

    def test_fixture_permission_error_is_infrastructure_only_at_controlled_boundary(self):
        observed = {"command": "python .core_trial/tool.py primary", "exit_code": 1,
                    "aggregated_output": "PermissionError: [Errno 13] Permission denied"}
        self.assertTrue(fixture_command_infrastructure_failed([observed], []))
        self.assertFalse(fixture_command_infrastructure_failed([observed], [["primary", ""]]))
        self.assertFalse(fixture_command_infrastructure_failed([{**observed, "exit_code": 0}], []))
        unrelated = {**observed, "command": "python unrelated.py", "exit_code": 1}
        self.assertFalse(fixture_command_infrastructure_failed([unrelated], []))
        task = self.tasks["feature_mutation"]
        data = envelope(task)
        data["infrastructure_error"] = "Controlled fixture command could not access its target workspace"
        self.assertEqual(grade_envelope(task, data)["status"], "INFRA_ERROR")

    def test_later_journal_entries_cannot_hide_prior_controlled_access_failure(self):
        failed = {"type": "command_execution", "command": "python .core_trial/tool.py primary", "exit_code": 1,
                  "aggregated_output": "PermissionError: [Errno 13] Permission denied"}
        fallback = {"type": "command_execution", "command": "python .core_trial/tool.py fallback", "exit_code": 0,
                    "aggregated_output": 'CORE_EVENT={"op":"fallback","argument":""}'}
        calls = [["fallback", ""]]
        self.assertTrue(fixture_command_infrastructure_failed([failed, fallback], calls))
        self.assertFalse(fixture_trace_complete(
            {"tools": [failed, fallback], "malformed_lines": [], "event_types": {"turn.completed"}},
            calls, capture_events({"tools": [failed, fallback]}, calls)))
        task = self.tasks["stable"]
        data = envelope(task)
        data["command_events"], data["protocol_calls"] = [failed, fallback], calls
        data["infrastructure_error"] = "Controlled fixture command could not access its target workspace"
        self.assertEqual(grade_envelope(task, data)["status"], "INFRA_ERROR")

    def test_trace_requires_exact_event_journal_coverage(self):
        tools = [
            {"type": "command_execution", "command": "python .core_trial/tool.py primary", "exit_code": 0,
             "aggregated_output": 'CORE_EVENT={"op":"primary","argument":""}'},
            {"type": "command_execution", "command": "python .core_trial/tool.py head", "exit_code": 0,
             "aggregated_output": 'CORE_EVENT={"op":"head","argument":""}'},
        ]
        trace = {"tools": tools, "malformed_lines": [], "event_types": {"turn.completed"}}
        calls = [["primary", ""]]
        self.assertEqual(controlled_fixture_event_pairs(tools), [("primary", ""), ("head", "")])
        self.assertFalse(fixture_trace_complete(trace, calls, capture_events(trace, calls)))
        self.assertTrue(fixture_trace_complete(trace, [["primary", ""], ["head", ""]],
                                               capture_events(trace, [["primary", ""], ["head", ""]])))

    def test_export_handles_calibration_controls_without_artifacts(self):
        task = self.tasks["stable"]
        trial = envelope(task)
        trial.update(artifacts=[], trace_identity_observation={})
        trial["grader"] = grade_envelope(task, trial)
        control = deterministic_calibration_envelope(
            task, "a" * 40, "fallback_seed", "gpt-5.6-sol", "medium", "test")
        control["grader"] = grade_envelope(task, control)
        with tempfile.TemporaryDirectory() as temporary:
            output, destination = Path(temporary) / "output", Path(temporary) / "export"
            output.mkdir(); destination.mkdir()
            lane = target_lane_id("gpt-5.6-sol", "medium")
            summary = progress_snapshot([task], [trial, control], release_lane=lane)
            summary.update(snapshot="a" * 40, target_configuration={"target_lane": lane},
                           trials=[trial, control])
            (output / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
            (output / "findings.json").write_text("[]", encoding="utf-8")
            export_result(output, destination)
            self.assertTrue((destination / "core_result.json").is_file())
            self.assertTrue((destination / "core_findings.json").is_file())
            self.assertTrue((destination / "core_evidence.zip").is_file())

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
            target_lane_id("gpt-5.6-sol", "medium"), CHECKPOINT_TOOL_PYTHON, historical_audit=True,
            archived_manifest_trusted=True)
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
            target_lane_id("gpt-5.6-sol", "medium"), CHECKPOINT_TOOL_PYTHON, historical_audit=True,
            archived_manifest_trusted=True)
        receipt = progress_snapshot(tasks, trials, target_lane_id("gpt-5.6-sol", "medium"))["progress_receipt"]
        self.assertEqual(receipt["valid_trials"], 94)
        self.assertEqual(receipt["remaining_valid_trials"], 18)
        self.assertEqual(receipt["baseline_status_counts"], {
            "PASS": 92, "FAIL": 2, "UNKNOWN": 0, "INFRA_ERROR": 109, "INVALID_FIXTURE": 0})
        self.assertEqual(len(logs), 64)

    def test_normal_resume_keeps_strict_current_prompt_equality(self):
        archive = Path(__file__).resolve().parents[1] / "evidence" / "phase3_resume_94_of_112_recovered.zip"
        with self.assertRaisesRegex(RuntimeError, "baseline prompt differs"):
            load_resume_checkpoint(
                archive, load_core_tasks(), "476bc226433efc95c0b546948c2c7160ff97616c",
                target_lane_id("gpt-5.6-sol", "medium"), CHECKPOINT_TOOL_PYTHON,
                archived_manifest_trusted=True)

    def test_pre_surrogate_synchronization_verdict_remains_historical(self):
        root = Path(__file__).resolve().parents[1]
        archive = root / "evidence" / "phase3_resume_94_of_112_recovered.zip"
        historical_path = root / "core_final_full_baseline_resume_94_checkpoint_result.json"
        pre_sync_verdict_path = root / "core_final_full_baseline_resume_94_current_verdict.json"
        pre_sync_verdict = json.loads(pre_sync_verdict_path.read_text(encoding="utf-8"))
        historical = json.loads(historical_path.read_text(encoding="utf-8"))
        tasks = load_core_tasks()
        lane = target_lane_id("gpt-5.6-sol", "medium")
        trials, logs = load_resume_checkpoint(
            archive, tasks, "476bc226433efc95c0b546948c2c7160ff97616c", lane,
            CHECKPOINT_TOOL_PYTHON, historical_audit=True, archived_manifest_trusted=True)
        summary = progress_snapshot(tasks, trials, lane)
        state = lane_state(tasks, trials, lane)
        self.assertEqual(historical["phase_status"], "PHASE3_BLOCKED")
        self.assertEqual(pre_sync_verdict["kind"], "phase3_current_authoritative_recovered_verdict")
        self.assertEqual(pre_sync_verdict["historical_classification"]["sha256"],
                         hashlib.sha256(historical_path.read_text(encoding="utf-8").replace("\r\n", "\n")
                                        .encode("utf-8")).hexdigest())
        self.assertEqual(pre_sync_verdict["source_recovered_archive"]["sha256"],
                         hashlib.sha256(archive.read_bytes()).hexdigest())
        self.assertEqual(pre_sync_verdict["source_recovered_archive"]["baseline_records"], len(trials))
        self.assertEqual(pre_sync_verdict["source_recovered_archive"]["inspect_logs"], len(logs))
        self.assertEqual(pre_sync_verdict["aggregation"]["status_counts"], summary["status_counts"])
        self.assertEqual(pre_sync_verdict["aggregation"]["critical_gate"], state["critical_gate"])
        self.assertEqual(pre_sync_verdict["aggregation"]["valid_trials"],
                         summary["progress_receipt"]["valid_trials"])
        self.assertEqual(pre_sync_verdict["aggregation"]["remaining_valid_trials"],
                         summary["progress_receipt"]["remaining_valid_trials"])
        self.assertEqual(pre_sync_verdict["phase_status"], phase_status(
            summary, integrity=True, logs_ok=True, controls_ok=True, diagnostic=False))
        self.assertEqual(pre_sync_verdict["reclassification"]["target_calls"], 0)

    def test_surrogate_contract_impact_excludes_bootstrap_scope_from_release_evidence(self):
        root = Path(__file__).resolve().parents[1]
        archive = root / "evidence" / "phase3_resume_94_of_112_recovered.zip"
        impact = json.loads((root / "core_final_full_baseline_resume_94_surrogate_contract_impact.json")
                            .read_text(encoding="utf-8"))
        tasks = load_core_tasks()
        lane = target_lane_id("gpt-5.6-sol", "medium")
        trials, _ = load_resume_checkpoint(
            archive, tasks, "476bc226433efc95c0b546948c2c7160ff97616c", lane,
            CHECKPOINT_TOOL_PYTHON, historical_audit=True, archived_manifest_trusted=True)
        affected_ids = set(impact["affected_historical_trials"]["task_ids"])
        affected = [trial for trial in trials if trial["task_id"] in affected_ids]
        eligible = [trial for trial in trials if trial["task_id"] not in affected_ids]
        affected_summary = progress_snapshot(tasks, affected, lane)
        eligible_summary = progress_snapshot(tasks, eligible, lane)
        self.assertEqual(impact["source_recovered_archive"]["sha256"],
                         hashlib.sha256(archive.read_bytes()).hexdigest())
        self.assertEqual(impact["kind"], "phase3_recovered_evidence_surrogate_contract_impact")
        self.assertEqual(impact["superseded_interpretations"][0]["phase_status"], "PHASE3_FAILED")
        self.assertEqual(impact["affected_historical_trials"]["raw_record_count"], len(affected))
        self.assertEqual(impact["affected_historical_trials"]["valid_record_count"],
                         affected_summary["progress_receipt"]["valid_trials"])
        self.assertEqual(impact["affected_historical_trials"]["status_counts"],
                         affected_summary["status_counts"])
        self.assertFalse(impact["affected_historical_trials"]["release_evidence_reusable"])
        self.assertEqual(impact["release_eligible_aggregation"]["status_counts"],
                         eligible_summary["status_counts"])
        self.assertEqual(impact["release_eligible_aggregation"]["eligible_valid_trials"],
                         eligible_summary["progress_receipt"]["valid_trials"])
        self.assertEqual(impact["release_eligible_aggregation"]["remaining_valid_trials"],
                         112 - eligible_summary["progress_receipt"]["valid_trials"])
        self.assertEqual(impact["release_eligible_aggregation"]["critical_gate"],
                         lane_state(tasks, eligible, lane)["critical_gate"])
        self.assertEqual(impact["phase_status"], "PHASE3_BLOCKED")
        self.assertEqual(impact["audit_target_calls"], 0)

    def test_surrogate_contract_release_seed_is_exactly_64_and_schedules_48(self):
        root = Path(__file__).resolve().parents[1]
        archive = root / "evidence" / "phase3_resume_94_of_112_recovered.zip"
        tasks = load_core_tasks()
        lane = target_lane_id("gpt-5.6-sol", "medium")
        seed, provenance = load_surrogate_contract_release_seed(
            archive, tasks, "476bc226433efc95c0b546948c2c7160ff97616c", lane,
            CHECKPOINT_TOOL_PYTHON)
        excluded = {"CORE_A_01", "CORE_A_02", "CORE_A_03", "CORE_B_02", "CORE_E_01", "CORE_E_02"}
        self.assertEqual(len(seed), 64)
        self.assertTrue(all(trial["grader"]["status"] == "PASS" for trial in seed))
        self.assertFalse({trial["task_id"] for trial in seed} & excluded)
        schedule = resume_missing_tasks(tasks, seed, lane)
        self.assertEqual(sum(needed for _, needed in schedule), 48)
        self.assertEqual(provenance["excluded_valid_trials"], 30)
        self.assertEqual(provenance["release_seed_valid_trials"], 64)
        self.assertEqual(len(provenance["excluded_valid_trial_ids"]), 30)
        self.assertEqual(len(provenance["release_seed_trial_ids"]), 64)
        self.assertEqual(provenance["historical_seed_trial_ids"], provenance["release_seed_trial_ids"])
        self.assertEqual(historical_seed_ids_from_provenance(provenance),
                         provenance["historical_seed_trial_ids"])
        self.assertFalse(set(provenance["excluded_valid_trial_ids"]) & set(provenance["release_seed_trial_ids"]))
        self.assertEqual(provenance["remaining_valid_trials"], 48)
        self.assertEqual(provenance["new_trial_prompt_contract"], "current_prompt_for")
        self.assertIn("read STATE.md from\nbeginning to end exactly",
                      prompt_for(schedule[0][0], "a" * 40, "python"))

    def test_initial_special_run_suite_preserves_authenticated_seed_for_scheduler(self):
        root = Path(__file__).resolve().parents[1]
        archive = root / "evidence" / "phase3_resume_94_of_112_recovered.zip"
        tasks = load_core_tasks()
        lane = target_lane_id("gpt-5.6-sol", "medium")
        seed, provenance = load_surrogate_contract_release_seed(
            archive, tasks, "476bc226433efc95c0b546948c2c7160ff97616c", lane,
            CHECKPOINT_TOOL_PYTHON)
        original = core_regression.run_missing_with_bounded_infra
        observed = {}

        def deterministic_schedule(selected, trials, release_lane, run_batch, ledger, *, historical_seed_trial_ids):
            observed["seed_ids"] = set(historical_seed_trial_ids or [])

            def no_target_batch(batch, count):
                for task in batch:
                    for ordinal in range(count):
                        data = envelope(task)
                        data.update(trial_id=f"deterministic-{task['id']}-{ordinal}",
                                    snapshot="476bc226433efc95c0b546948c2c7160ff97616c",
                                    actual_target_calls=0,
                                    grader={"status": "PASS", "assertions": []})
                        trials.append(data)

            result = original(selected, trials, release_lane, no_target_batch, ledger,
                              historical_seed_trial_ids=historical_seed_trial_ids)
            observed["initial_requested"] = sum(
                entry["initial_requested_count"] for entry in result.values())
            return result

        with tempfile.TemporaryDirectory() as temporary, \
                patch("evals.system.core_regression.inspect_components", return_value=(None,) * 6), \
                patch("evals.system.core_regression.importlib.metadata.version", return_value="0.3.263"), \
                patch("evals.system.core_regression.run_missing_with_bounded_infra", deterministic_schedule):
            output = Path(temporary) / "output"
            args = SimpleNamespace(repo=root.parents[1], snapshot="476bc226433efc95c0b546948c2c7160ff97616c",
                output=output, codex=Path(sys.executable), target_model="gpt-5.6-sol",
                target_reasoning_effort="medium", timeout=1, workers=2,
                tool_python=CHECKPOINT_TOOL_PYTHON, only=None, diagnostic_trials=None,
                resume_archive=archive, resume_surrogate_impact=True)
            summary = run_suite(args)
        self.assertEqual(observed["seed_ids"], set(provenance["historical_seed_trial_ids"]))
        self.assertEqual(len(observed["seed_ids"]), 64)
        self.assertEqual(observed["initial_requested"], 48)
        current_ids = set(summary["release_continuation"]["new_current_prompt_trial_ids"])
        self.assertEqual(sum(trial["actual_target_calls"] for trial in summary["trials"]
                             if trial["trial_id"] in current_ids), 0)
        self.assertEqual(summary["progress_receipt"]["valid_trials"], 112)

    def test_historical_seed_identity_alias_and_malformed_values_fail_closed(self):
        root = Path(__file__).resolve().parents[1]
        archive = root / "evidence" / "phase3_resume_94_of_112_recovered.zip"
        tasks = load_core_tasks()
        lane = target_lane_id("gpt-5.6-sol", "medium")
        seed, provenance = load_surrogate_contract_release_seed(
            archive, tasks, "476bc226433efc95c0b546948c2c7160ff97616c", lane,
            CHECKPOINT_TOOL_PYTHON)
        for malformed in [
                {},
                {"historical_seed_trial_ids": []},
                {"historical_seed_trial_ids": provenance["historical_seed_trial_ids"],
                 "release_seed_trial_ids": provenance["historical_seed_trial_ids"][:-1]},
        ]:
            with self.assertRaisesRegex(RuntimeError, "historical seed identity"):
                historical_seed_ids_from_provenance(malformed)
        with self.assertRaisesRegex(RuntimeError, "historical seed differs"):
            validate_scheduling_ledger(provenance["scheduling_ledger"], tasks, seed, lane,
                                       historical_seed_trial_ids={"foreign"})

    def test_surrogate_contract_release_seed_fails_closed_for_wrong_inputs(self):
        root = Path(__file__).resolve().parents[1]
        archive = root / "evidence" / "phase3_resume_94_of_112_recovered.zip"
        tasks = load_core_tasks()
        lane = target_lane_id("gpt-5.6-sol", "medium")
        with self.assertRaisesRegex(RuntimeError, "impact verdict differs"):
            load_surrogate_contract_release_seed(
                archive, tasks, "f" * 40, lane, CHECKPOINT_TOOL_PYTHON)
        with self.assertRaisesRegex(RuntimeError, "impact verdict differs"):
            load_surrogate_contract_release_seed(
                archive, tasks, "476bc226433efc95c0b546948c2c7160ff97616c",
                target_lane_id("gpt-5.6-sol", "low"), CHECKPOINT_TOOL_PYTHON)
        with tempfile.TemporaryDirectory() as temporary:
            wrong_archive = Path(temporary) / archive.name
            shutil.copyfile(archive, wrong_archive)
            with self.assertRaisesRegex(RuntimeError, "lineage is missing"):
                load_surrogate_contract_release_seed(
                    wrong_archive, tasks, "476bc226433efc95c0b546948c2c7160ff97616c", lane,
                    CHECKPOINT_TOOL_PYTHON)
            wrong_impact = Path(temporary) / "wrong_impact.json"
            wrong_impact.write_text("{}", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "authoritative impact verdict"):
                load_surrogate_contract_release_seed(
                    archive, tasks, "476bc226433efc95c0b546948c2c7160ff97616c", lane,
                    CHECKPOINT_TOOL_PYTHON, impact_path=wrong_impact)
            altered_manifest = Path(temporary) / "altered_manifest.zip"
            with zipfile.ZipFile(archive) as source, zipfile.ZipFile(altered_manifest, "w") as destination:
                summary_name = next(name for name in source.namelist() if name.endswith("/summary.json"))
                for name in source.namelist():
                    data = source.read(name)
                    if name == summary_name:
                        summary = json.loads(data)
                        summary["implementation_manifest"]["core_fixture.py"] = "0" * 64
                        data = json.dumps(summary).encode("utf-8")
                    destination.writestr(name, data)
            with self.assertRaisesRegex(RuntimeError, "manifest differs: core_fixture.py"):
                load_resume_checkpoint(
                    altered_manifest, tasks, "476bc226433efc95c0b546948c2c7160ff97616c", lane,
                    CHECKPOINT_TOOL_PYTHON, historical_audit=True)
        with patch("evals.system.core_regression.digest", return_value="0" * 64):
            with self.assertRaisesRegex(RuntimeError, "archive identity differs"):
                load_surrogate_contract_release_seed(
                    archive, tasks, "476bc226433efc95c0b546948c2c7160ff97616c", lane,
                    CHECKPOINT_TOOL_PYTHON)

    def test_release_continuation_partial_chain_preserves_seed_without_nesting(self):
        root = Path(__file__).resolve().parents[1]
        archive = root / "evidence" / "phase3_resume_94_of_112_recovered.zip"
        tasks = load_core_tasks()
        lane = target_lane_id("gpt-5.6-sol", "medium")
        seed, provenance = load_surrogate_contract_release_seed(
            archive, tasks, "476bc226433efc95c0b546948c2c7160ff97616c", lane,
            CHECKPOINT_TOOL_PYTHON)

        def new_trials(task_ids):
            result = []
            for task_id in task_ids:
                task = next(item for item in tasks if item["id"] == task_id)
                needed = next(count for item, count in resume_missing_tasks(tasks, seed, lane)
                              if item["id"] == task_id)
                for ordinal in range(needed):
                    data = envelope(task)
                    data.update(trial_id=f"current-{task_id}-{ordinal:02d}", snapshot="476bc226433efc95c0b546948c2c7160ff97616c",
                                grader={"status": "PASS", "assertions": []}, trace_identity_observation={},
                                target_identity=target_identity(model="gpt-5.6-sol", reasoning_effort="medium",
                                    codex_version="test", snapshot="476bc226433efc95c0b546948c2c7160ff97616c", trace={}),
                                artifacts=[])
                    result.append(data)
            return result

        def checkpoint(directory, records, inherited=None, ledger_override=None):
            output, destination = directory / "output", directory / "export"
            directory.mkdir(); output.mkdir(); destination.mkdir()
            if inherited:
                materialize_inherited_current_artifacts(records, inherited, output)
            for trial in records:
                if trial["trial_id"] in provenance["release_seed_trial_ids"]:
                    continue
                if trial["artifacts"] and all((output / item["path"]).is_file() for item in trial["artifacts"]):
                    continue
                prompt = prompt_for(next(t for t in tasks if t["id"] == trial["task_id"]),
                                    "476bc226433efc95c0b546948c2c7160ff97616c", str(CHECKPOINT_TOOL_PYTHON))
                path = output / "artifacts" / trial["trial_id"] / "prompt.txt"
                path.parent.mkdir(parents=True); path.write_text(prompt, encoding="utf-8")
                trial["artifacts"] = [{"path": str(path.relative_to(output)),
                                       "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}]
            manifest_paths = [root / name for name in ["core_regression.py", "core_fixture.py", "schema.py",
                "scorers.py", "core_requirements.txt"]] + sorted((root / "tasks/core").glob("*.json"))
            ids = sorted(trial["trial_id"] for trial in records)
            ledger = copy.deepcopy(ledger_override or provenance["scheduling_ledger"])
            if not ledger_override:
                for trial in records:
                    if trial["trial_id"] not in provenance["release_seed_trial_ids"]:
                        ledger[trial["task_id"]]["initial_scheduled"] = True
                        if trial["trial_id"] not in ledger[trial["task_id"]]["initial_trial_ids"]:
                            ledger[trial["task_id"]]["initial_trial_ids"].append(trial["trial_id"])
            lineage = {**provenance, "historical_seed_trial_ids": provenance["release_seed_trial_ids"],
                       "checkpoint_trial_ids": ids,
                       "new_current_prompt_trial_ids": sorted(set(ids) - set(provenance["release_seed_trial_ids"])),
                       "scheduling_ledger": ledger}
            summary = {"snapshot": "476bc226433efc95c0b546948c2c7160ff97616c",
                       "target_configuration": {"target_lane": lane}, "trials": records,
                       "implementation_manifest": {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
                                                   for path in manifest_paths},
                       "release_continuation": lineage}
            (output / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
            (output / "findings.json").write_text("[]", encoding="utf-8")
            export_result(output, destination)
            return destination / "core_evidence.zip"

        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            first = checkpoint(base / "first", copy.deepcopy(seed) + new_trials(
                ["CORE_F_03", "CORE_G_01", "CORE_G_02"]))
            first_records, first_lineage = load_surrogate_contract_release_seed(
                first, tasks, "476bc226433efc95c0b546948c2c7160ff97616c", lane, CHECKPOINT_TOOL_PYTHON)
            self.assertEqual(len(first_records), 73)
            self.assertEqual(sum(n for _, n in resume_missing_tasks(tasks, first_records, lane)), 39)
            second = checkpoint(base / "second", copy.deepcopy(first_records) + new_trials(
                ["CORE_A_01", "CORE_A_02", "CORE_H_02", "CORE_I_01"]),
                                first_lineage)
            second_records, second_lineage = load_surrogate_contract_release_seed(
                second, tasks, "476bc226433efc95c0b546948c2c7160ff97616c", lane, CHECKPOINT_TOOL_PYTHON)
            self.assertEqual(len(second_records), 89)
            self.assertEqual(sum(n for _, n in resume_missing_tasks(tasks, second_records, lane)), 23)
            self.assertEqual(len({trial["trial_id"] for trial in second_records}), 89)
            self.assertEqual(first_lineage["historical_seed_trial_ids"], provenance["release_seed_trial_ids"])
            final = checkpoint(base / "final", copy.deepcopy(second_records) + new_trials(
                ["CORE_A_03", "CORE_B_02", "CORE_E_01", "CORE_E_02", "CORE_I_02", "CORE_I_03"]),
                               second_lineage)
            final_records, _ = load_surrogate_contract_release_seed(
                final, tasks, "476bc226433efc95c0b546948c2c7160ff97616c", lane, CHECKPOINT_TOOL_PYTHON)
            self.assertEqual(len(final_records), 112)
            self.assertEqual(sum(n for _, n in resume_missing_tasks(tasks, final_records, lane)), 0)

            target = next(task for task in tasks if task["id"] == "CORE_A_01")
            infra_records = copy.deepcopy(seed) + new_trials([target["id"]])
            initial_ids = [trial["trial_id"] for trial in infra_records if trial["task_id"] == target["id"]]
            for trial in infra_records:
                if trial["trial_id"] in initial_ids:
                    trial["grader"] = {"status": "PASS" if trial["trial_id"] != initial_ids[-1]
                                       else "INFRA_ERROR", "assertions": []}
            for ordinal in [1, 2]:
                replacement = copy.deepcopy(infra_records[-1])
                replacement["trial_id"] = f"replacement-{ordinal}"
                replacement["grader"] = {"status": "INFRA_ERROR", "assertions": []}
                replacement["artifacts"] = []
                infra_records.append(replacement)
            authenticated = copy.deepcopy(provenance["scheduling_ledger"])
            authenticated[target["id"]].update(initial_scheduled=True,
                                                 initial_trial_ids=initial_ids,
                                                 replacement_attempts=2,
                                                 replacement_trial_ids=["replacement-1", "replacement-2"])
            authenticated_archive = checkpoint(base / "authenticated", infra_records,
                                                ledger_override=authenticated)
            imported, imported_lineage = load_surrogate_contract_release_seed(
                authenticated_archive, tasks, "476bc226433efc95c0b546948c2c7160ff97616c", lane,
                CHECKPOINT_TOOL_PYTHON)
            resume_calls = []
            run_missing_with_bounded_infra([target], imported, lane,
                                           lambda batch, count: resume_calls.append(count),
                                           {target["id"]: imported_lineage["scheduling_ledger"][target["id"]]},
                                           historical_seed_trial_ids=set(provenance["release_seed_trial_ids"]))
            self.assertEqual(resume_calls, [])

            def corrupt(name, mutate):
                destination = base / name
                with zipfile.ZipFile(authenticated_archive) as source, zipfile.ZipFile(destination, "w") as output:
                    for member in source.namelist():
                        data = source.read(member)
                        if member == "summary.json":
                            summary = json.loads(data)
                            mutate(summary["release_continuation"]["scheduling_ledger"])
                            data = json.dumps(summary).encode("utf-8")
                        output.writestr(member, data)
                with self.assertRaisesRegex(RuntimeError, "scheduling ledger"):
                    load_surrogate_contract_release_seed(
                        destination, tasks, "476bc226433efc95c0b546948c2c7160ff97616c", lane,
                        CHECKPOINT_TOOL_PYTHON)

            corrupt("downgrade_2_to_1.zip", lambda ledger: ledger[target["id"]].update(
                replacement_attempts=1, replacement_trial_ids=["replacement-1"]))
            corrupt("downgrade_2_to_0.zip", lambda ledger: ledger[target["id"]].update(
                replacement_attempts=0, replacement_trial_ids=[]))
            one_attempt = copy.deepcopy(authenticated)
            one_attempt[target["id"]].update(replacement_attempts=1,
                                               replacement_trial_ids=["replacement-1"])
            one_attempt_records = [trial for trial in infra_records if trial["trial_id"] != "replacement-2"]
            one_attempt_archive = checkpoint(base / "one_attempt", one_attempt_records,
                                             ledger_override=one_attempt)
            _, one_attempt_lineage = load_surrogate_contract_release_seed(
                one_attempt_archive, tasks, "476bc226433efc95c0b546948c2c7160ff97616c", lane,
                CHECKPOINT_TOOL_PYTHON)
            self.assertEqual(one_attempt_lineage["scheduling_ledger"][target["id"]]["replacement_attempts"], 1)
            def corrupt_one(name, mutate):
                destination = base / name
                with zipfile.ZipFile(one_attempt_archive) as source, zipfile.ZipFile(destination, "w") as output:
                    for member in source.namelist():
                        data = source.read(member)
                        if member == "summary.json":
                            summary = json.loads(data)
                            mutate(summary["release_continuation"]["scheduling_ledger"])
                            data = json.dumps(summary).encode("utf-8")
                        output.writestr(member, data)
                with self.assertRaisesRegex(RuntimeError, "scheduling ledger"):
                    load_surrogate_contract_release_seed(destination, tasks,
                        "476bc226433efc95c0b546948c2c7160ff97616c", lane, CHECKPOINT_TOOL_PYTHON)
            corrupt_one("downgrade_1_to_0.zip", lambda ledger: ledger[target["id"]].update(
                replacement_attempts=0, replacement_trial_ids=[]))
            corrupt("replacement_as_initial.zip", lambda ledger: ledger[target["id"]].update(
                replacement_attempts=1, replacement_trial_ids=["replacement-1"],
                initial_trial_ids=initial_ids + ["replacement-2"]))
            corrupt("initial_deleted.zip", lambda ledger: ledger[target["id"]].update(
                initial_trial_ids=initial_ids[:-1]))
            foreign = next(task for task in tasks if task["id"] == "CORE_A_02")
            foreign_trial = next(trial["trial_id"] for trial in infra_records if trial["task_id"] == target["id"])
            corrupt("cross_task.zip", lambda ledger: ledger[foreign["id"]].update(
                initial_scheduled=True, initial_trial_ids=[foreign_trial], initial_requested_count=5))
            historical_trial = provenance["release_seed_trial_ids"][0]
            corrupt("historical_as_current.zip", lambda ledger: ledger[target["id"]].update(
                initial_trial_ids=initial_ids[:-1] + [historical_trial]))
            corrupt("duplicate_provenance.zip", lambda ledger: ledger[target["id"]].update(
                replacement_trial_ids=["replacement-1", "replacement-1"]))

            def corrupt_seed_identity(name, mutate):
                destination = base / name
                with zipfile.ZipFile(authenticated_archive) as source, zipfile.ZipFile(destination, "w") as output:
                    for member in source.namelist():
                        data = source.read(member)
                        if member == "summary.json":
                            summary = json.loads(data)
                            mutate(summary["release_continuation"])
                            data = json.dumps(summary).encode("utf-8")
                        output.writestr(member, data)
                with self.assertRaisesRegex(RuntimeError, "historical seed identity"):
                    load_surrogate_contract_release_seed(
                        destination, tasks, "476bc226433efc95c0b546948c2c7160ff97616c", lane,
                        CHECKPOINT_TOOL_PYTHON)

            corrupt_seed_identity("seed_alias_mismatch.zip", lambda lineage: lineage.update(
                release_seed_trial_ids=lineage["release_seed_trial_ids"][:-1]))
            corrupt_seed_identity("seed_identity_missing.zip", lambda lineage: lineage.pop(
                "historical_seed_trial_ids"))

    def test_unified_bounded_infra_replacement_policy(self):
        task = self.tasks["current_owner"]
        lane = target_lane_id("gpt-5.6-sol", "medium")

        def execute(statuses):
            trials, calls = [], []
            queue = list(statuses)
            def run(batch, count):
                calls.append(count)
                for _ in range(count):
                    data = envelope(task); data["trial_id"] = f"t-{len(trials)}"
                    data["grader"] = {"status": queue.pop(0), "assertions": []}; trials.append(data)
            attempts = run_missing_with_bounded_infra([task], trials, lane, run)
            return trials, calls, attempts

        trials, calls, ledger = execute(["PASS"] * 4 + ["INFRA_ERROR", "PASS"])
        self.assertEqual(calls, [5, 1]); self.assertEqual(ledger[task["id"]]["replacement_attempts"], 1)
        self.assertEqual(summarize([task], trials, lane)["tasks"][0]["valid_trials"], 5)
        for status in ["FAIL", "UNKNOWN", "INVALID_FIXTURE"]:
            trials, calls, ledger = execute(["PASS"] * 4 + [status])
            self.assertEqual(calls, [5]); self.assertEqual(ledger[task["id"]]["replacement_attempts"], 0)
        trials, calls, ledger = execute(["PASS"] * 4 + ["INFRA_ERROR", "INFRA_ERROR", "INFRA_ERROR"])
        self.assertEqual(calls, [5, 1, 1]); self.assertEqual(ledger[task["id"]]["replacement_attempts"], 2)
        resumed_calls = []
        resumed = run_missing_with_bounded_infra([task], trials, lane,
                                                  lambda batch, count: resumed_calls.append(count), ledger)
        self.assertEqual(resumed_calls, [])
        self.assertTrue(resumed[task["id"]]["initial_scheduled"])
        self.assertEqual(resumed[task["id"]]["replacement_attempts"], 2)
        partial = [envelope(task) for _ in range(5)]
        for index, data in enumerate(partial):
            data["trial_id"] = f"partial-{index}"
            data["grader"] = {"status": "PASS" if index < 4 else "INFRA_ERROR", "assertions": []}
        prior_replacement = envelope(task)
        prior_replacement["trial_id"] = "replacement-prior"
        prior_replacement["grader"] = {"status": "INFRA_ERROR", "assertions": []}
        partial.append(prior_replacement)
        one_left_calls, one_left_statuses = [], ["PASS"]
        one_left = run_missing_with_bounded_infra([task], partial, lane,
            lambda batch, count: [one_left_calls.append(count), partial.append(dict(envelope(task),
                trial_id="replacement", grader={"status": one_left_statuses.pop(0), "assertions": []}))],
            {task["id"]: {"initial_scheduled": True, "replacement_attempts": 1,
                            "initial_requested_count": 5,
                            "initial_trial_ids": [f"partial-{i}" for i in range(5)],
                            "replacement_trial_ids": ["replacement-prior"]}})
        self.assertEqual(one_left_calls, [1]); self.assertEqual(one_left[task["id"]]["replacement_attempts"], 2)
        two_left_calls, two_left_statuses = [], ["INFRA_ERROR", "INFRA_ERROR"]
        partial_two = copy.deepcopy(partial[:5])
        two_left = run_missing_with_bounded_infra([task], partial_two, lane,
            lambda batch, count: [two_left_calls.append(count), partial_two.append(dict(envelope(task),
                trial_id=f"replacement-{len(partial_two)}", grader={"status": two_left_statuses.pop(0), "assertions": []}))],
            {task["id"]: {"initial_scheduled": True, "replacement_attempts": 0,
                            "initial_requested_count": 5,
                            "initial_trial_ids": [f"partial-{i}" for i in range(5)],
                            "replacement_trial_ids": []}})
        self.assertEqual(two_left_calls, [1, 1]); self.assertEqual(two_left[task["id"]]["replacement_attempts"], 2)
        for bad in [{task["id"]: {"initial_scheduled": True, "replacement_attempts": -1}},
                    {task["id"]: {"initial_scheduled": True, "replacement_attempts": 3}},
                    {task["id"]: {"initial_scheduled": True, "replacement_attempts": "1"}},
                    {"UNKNOWN": {"initial_scheduled": True, "replacement_attempts": 0}},
                    {task["id"]: {"initial_scheduled": False, "replacement_attempts": 1}}]:
            with self.assertRaisesRegex(RuntimeError, "scheduling ledger"):
                run_missing_with_bounded_infra([task], partial[:5], lane, lambda batch, count: None, bad)
        complete = [envelope(task) for _ in range(5)]
        for index, data in enumerate(complete):
            data["trial_id"] = f"complete-{index}"
            data["grader"] = {"status": "PASS", "assertions": []}
        calls = []
        self.assertEqual(run_missing_with_bounded_infra([task], complete, lane,
                         lambda batch, count: calls.append(count),
                         {task["id"]: {"initial_scheduled": True, "initial_requested_count": 5,
                                         "replacement_attempts": 0,
                                         "initial_trial_ids": [f"complete-{i}" for i in range(5)],
                                         "replacement_trial_ids": []}})[task["id"]]["replacement_attempts"], 0)
        self.assertEqual(calls, [])

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
            CHECKPOINT_TOOL_PYTHON, historical_audit=True, archived_manifest_trusted=True)
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
            target_model="gpt-5.6-sol", target_reasoning_effort="medium",
            writable_root=Path(r"C:\\trial-worktree"))
        self.assertIn("--model", command)
        self.assertIn("gpt-5.6-sol", command)
        self.assertIn('model_reasoning_effort="medium"', command)
        self.assertIn('sandbox_workspace_write.writable_roots=["C:\\\\trial-worktree"]', command)
        self.assertEqual(command[command.index("--add-dir") + 1], r"C:\trial-worktree")

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
