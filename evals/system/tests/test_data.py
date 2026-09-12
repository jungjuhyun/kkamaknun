import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import evals.system.check as check_module
from evals.system.check import load_tasks, validate_all_data, validate_fixture_data
from evals.system.schema import SchemaError


class DataValidationTests(unittest.TestCase):
    def test_all_tasks_fixtures_and_protocol_data(self):
        validate_all_data()

    def test_stale_marker_in_current_source_is_invalid_fixture(self):
        root = Path(__file__).resolve().parents[1]
        path = root / "fixtures" / "REG-PROVENANCE-CONTAMINATION-001.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        invalid = copy.deepcopy(data)
        invalid["fake_environment"]["current_owner"]["text"] = "シ·ツ·ソ·ン"
        with self.assertRaises(SchemaError):
            validate_fixture_data(invalid, "in-memory-invalid-fixture", load_tasks())

    def test_task_load_rejects_malformed_grader_parameters(self):
        root = Path(__file__).resolve().parents[1]
        source = root / "tasks" / "REG-BOOTSTRAP-FALLBACK-001.json"
        task = json.loads(source.read_text(encoding="utf-8"))
        task["assertions"][1]["parameters"] = {}
        with tempfile.TemporaryDirectory() as directory:
            system_root = Path(directory)
            (system_root / "tasks").mkdir()
            (system_root / "tasks" / source.name).write_text(
                json.dumps(task), encoding="utf-8"
            )
            with patch.object(check_module, "SYSTEM_ROOT", system_root):
                with self.assertRaises(SchemaError):
                    check_module.load_tasks()


if __name__ == "__main__":
    unittest.main()
