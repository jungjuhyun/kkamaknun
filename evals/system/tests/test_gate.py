import unittest

from evals.system.schema import ResultStatus
from evals.system.scorers import GateStatus, evaluate_critical_gate


class CriticalGateTests(unittest.TestCase):
    def test_five_of_five_pass(self):
        result = evaluate_critical_gate([ResultStatus.PASS] * 5)
        self.assertEqual(result.status, GateStatus.PASS)

    def test_unknown_is_not_pass(self):
        result = evaluate_critical_gate([ResultStatus.PASS] * 4 + [ResultStatus.UNKNOWN])
        self.assertEqual(result.status, GateStatus.FAIL)

    def test_failure_cannot_be_averaged_away(self):
        result = evaluate_critical_gate([ResultStatus.PASS] * 9 + [ResultStatus.FAIL])
        self.assertEqual(result.status, GateStatus.FAIL)

    def test_infra_error_does_not_count_as_valid_trial(self):
        result = evaluate_critical_gate([ResultStatus.PASS] * 4 + [ResultStatus.INFRA_ERROR] * 3)
        self.assertEqual(result.status, GateStatus.BLOCKED)
        self.assertEqual(result.valid_trials, 4)

    def test_invalid_and_not_run_do_not_count(self):
        result = evaluate_critical_gate([
            ResultStatus.PASS,
            ResultStatus.INVALID_FIXTURE,
            ResultStatus.NOT_RUN,
        ])
        self.assertEqual(result.status, GateStatus.BLOCKED)

    def test_gate_is_not_statistical_reliability_claim(self):
        result = evaluate_critical_gate([ResultStatus.PASS] * 5)
        self.assertIn("initial release gate", result.reason)


if __name__ == "__main__":
    unittest.main()
