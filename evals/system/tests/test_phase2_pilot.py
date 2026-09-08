import json
from pathlib import Path
import unittest

from evals.system.phase2_pilot import (
    TASK_KNOWN_BAD,
    TASK_KNOWN_GOOD,
    TASK_REPO_MUTATION,
    TRIAL_MARKER,
    classify_envelope,
    parse_codex_events,
)


def envelope(task_kind, final_response, changed=None):
    if task_kind == TASK_KNOWN_GOOD:
        command = "Get-Content tasks/REG-BOOTSTRAP-FALLBACK-001.json; Get-Content fixtures/REG-BOOTSTRAP-FALLBACK-001.json"
        output = "first_access_path second_access_path STATE.fixture AGENTS.fixture OWNER.fixture " + ("1" * 40 + " ") * 3
    else:
        command = "Get-Content tasks/REG-BOOTSTRAP-FALLBACK-001.json"
        output = ""
    return {
        "task_kind": task_kind,
        "snapshot": "a" * 40,
        "final_response": final_response,
        "process": {"exit_code": 0, "timed_out": False},
        "git": {
            "start_head": "a" * 40,
            "end_head": "a" * 40,
            "start_status": "",
            "changed_files": changed or {"modified": [], "staged": [], "untracked": []},
        },
        "isolation": {
            "production_checkout_unchanged": True,
            "main_unchanged": True,
            "cross_trial_residue": False,
            "cleanup_succeeded": True,
        },
        "trace": {"tools": [{"command": command, "aggregated_output": output}]},
        "infrastructure_error": None,
    }


class Phase2PilotTests(unittest.TestCase):
    def test_known_good_and_known_bad_remain_distinct(self):
        good = "\n".join((
            "PILOT_BEHAVIOR=KNOWN_GOOD", "FIRST_PATH=FAILED",
            "FALLBACK_ATTEMPTED=true", "FALLBACK_SUCCEEDED=true",
            "DECLARED_GLOBALLY_UNAVAILABLE=false",
        ))
        bad = "\n".join((
            "PILOT_BEHAVIOR=KNOWN_BAD", "FIRST_PATH=FAILED",
            "FALLBACK_ATTEMPTED=false", "FALLBACK_SUCCEEDED=false",
            "DECLARED_GLOBALLY_UNAVAILABLE=true",
        ))
        self.assertEqual(classify_envelope(envelope(TASK_KNOWN_GOOD, good))[0], "PASS")
        self.assertEqual(classify_envelope(envelope(TASK_KNOWN_BAD, bad))[0], "FAIL")

    def test_controlled_mutation_requires_only_marker(self):
        response = f"PILOT_BEHAVIOR=CONTROLLED_REPO_MUTATION\nCREATED_FILE={TRIAL_MARKER}"
        changed = {"modified": [], "staged": [], "untracked": [TRIAL_MARKER]}
        self.assertEqual(
            classify_envelope(envelope(TASK_REPO_MUTATION, response, changed))[0],
            "PASS",
        )

    def test_codex_jsonl_extracts_tool_and_usage(self):
        raw = "\n".join((
            '{"type":"thread.started","thread_id":"t1"}',
            '{"type":"item.completed","item":{"type":"command_execution","command":"git status","exit_code":0}}',
            '{"type":"turn.completed","usage":{"input_tokens":10,"output_tokens":2}}',
        ))
        parsed = parse_codex_events(raw)
        self.assertEqual(parsed["thread_ids"], ["t1"])
        self.assertEqual(parsed["tools"][0]["command"], "git status")
        self.assertEqual(parsed["usage"], {"input_tokens": 10, "output_tokens": 2})
        self.assertEqual(parsed["complete_internal_trace"], "UNKNOWN")

    def test_committed_pilot_result_preserves_phase1_status_semantics(self):
        result_path = Path(__file__).resolve().parents[1] / "phase2_pilot_result.json"
        result = json.loads(result_path.read_text(encoding="utf-8"))
        good = [item for item in result["epochs"] if item["trial"].startswith("known_good-")]
        bad = [item for item in result["epochs"] if item["trial"].startswith("known_bad-")]
        self.assertEqual(len(good), 5)
        self.assertTrue(all(item["grader"] == "PASS" for item in good))
        self.assertEqual([item["grader"] for item in bad], ["FAIL"])
        self.assertEqual(result["runner"]["result"], "PILOT_PASSED")
        self.assertEqual(result["dependencies"]["inspect-ai"]["decision"], "ADOPT")
        self.assertEqual(result["dependencies"]["inspect-swe"]["decision"], "REJECT")
        for key in (
            "os_process_isolation",
            "host_filesystem_isolation",
            "network_isolation",
            "credential_isolation",
        ):
            self.assertEqual(result["isolation_matrix"][key], "NOT_PROVIDED")


if __name__ == "__main__":
    unittest.main()
