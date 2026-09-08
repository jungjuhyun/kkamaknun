import json
from pathlib import Path
import unittest

from evals.system.check import load_tasks
from evals.system.reference_target import run_bootstrap_reference
from evals.system.schema import ResultStatus
from evals.system.scorers import grade_trial


SYSTEM_ROOT = Path(__file__).resolve().parents[1]


class ExecutableReferenceTargetTests(unittest.TestCase):
    def test_same_task_distinguishes_executed_good_and_bad_behavior(self):
        task = load_tasks()["REG-BOOTSTRAP-FALLBACK-001"]
        fixture = json.loads(
            (SYSTEM_ROOT / "fixtures" / "REG-BOOTSTRAP-FALLBACK-001.json").read_text(
                encoding="utf-8"
            )
        )
        environment = fixture["fake_environment"]

        good = run_bootstrap_reference(task, environment, "known_good")
        bad = run_bootstrap_reference(task, environment, "known_bad")

        self.assertEqual(good.calls, ("first_access_path", "second_access_path"))
        self.assertEqual(bad.calls, ("first_access_path",))
        self.assertEqual(grade_trial(task, good.evidence).status, ResultStatus.PASS)
        self.assertEqual(grade_trial(task, bad.evidence).status, ResultStatus.FAIL)


if __name__ == "__main__":
    unittest.main()
