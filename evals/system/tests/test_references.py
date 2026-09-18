import json
from pathlib import Path
import unittest


SYSTEM_ROOT = Path(__file__).resolve().parents[1]


class ReferenceTests(unittest.TestCase):
    def test_seed_task_and_fixture_names_match(self):
        tasks = {path.stem for path in (SYSTEM_ROOT / "tasks").glob("*.json")}
        fixtures = {path.stem for path in (SYSTEM_ROOT / "fixtures").glob("*.json")}
        self.assertEqual(tasks, fixtures)
        self.assertEqual(tasks, {
            "REG-BOOTSTRAP-FALLBACK-001",
            "REG-PROVENANCE-CONTAMINATION-001",
            "REG-HISTORICAL-RETRIEVAL-REQUIRED-001",
        })

    def test_no_forbidden_framework_imports(self):
        forbidden = ("inspect_ai", "inspect_swe", "pyrit", "promptfoo")
        for path in SYSTEM_ROOT.rglob("*.py"):
            text = path.read_text(encoding="utf-8").lower()
            for name in forbidden:
                if name == "inspect_ai" and path.name in {"phase2_pilot.py", "core_regression.py"}:
                    continue
                if name == "inspect_swe" and path.name == "phase2_pilot.py":
                    continue  # Historical Phase 2 probe only; never invoked by Phase 3.
                self.assertNotIn(f"import {name}", text, path.as_posix())
                self.assertNotIn(f"from {name}", text, path.as_posix())

    def test_observation_matrix_marks_phase3_and_phase4_contract_boundaries(self):
        data = json.loads((SYSTEM_ROOT / "observation_matrix.json").read_text(encoding="utf-8"))
        statuses = {item["target"]: item["implementation_status"] for item in data["targets"]}
        self.assertEqual(statuses["future_inspect_codex"], "CORE_REGRESSION_IMPLEMENTED_PHASE_3")
        self.assertEqual(
            statuses["actual_work"],
            "PHASE4_UAT_CONTRACT_IMPLEMENTED_PILOT_NOT_RUN",
        )


if __name__ == "__main__":
    unittest.main()
