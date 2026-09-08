import unittest

from evals.system.schema import (
    ProjectInstructionEvidence,
    SchemaError,
    TaskSpec,
    WorkUATRecord,
)


HASH = "sha256:" + "a" * 64


class TaskSchemaTests(unittest.TestCase):
    def test_missing_task_fields_are_rejected(self):
        with self.assertRaises(SchemaError):
            TaskSpec.from_dict({"id": "incomplete"})

    def test_on_missing_evidence_must_be_unknown(self):
        task = {
            "id": "X",
            "suite": "regression",
            "target": "direct_component",
            "risk_surface": ["x"],
            "criticality": "critical",
            "setup": ["x"],
            "precondition": ["x"],
            "user_input": "x",
            "expected_observable_behavior": ["x"],
            "forbidden_observable_behavior": ["x"],
            "assertions": [{
                "id": "a",
                "target": "direct_component",
                "evidence_source": "e",
                "required_for_pass": True,
                "evaluation_method": "equals",
                "on_missing_evidence": "PASS",
            }],
            "trial_count": 5,
            "isolation_profile": "controlled_mock_access",
            "required_evidence": ["e"],
            "optional_evidence": [],
            "snapshot_expectation": {},
        }
        with self.assertRaises(SchemaError):
            TaskSpec.from_dict(task)


class ProjectInstructionProvenanceTests(unittest.TestCase):
    def test_verified_requires_exact_text_hash_and_active_match(self):
        evidence = ProjectInstructionEvidence.from_dict({
            "provenance": "VERIFIED",
            "content_hash": HASH,
            "active_ui_match": True,
            "exact_text_bytes_available": True,
        })
        self.assertEqual(evidence.content_hash, HASH)

    def test_verified_without_hash_is_rejected(self):
        with self.assertRaises(SchemaError):
            ProjectInstructionEvidence.from_dict({
                "provenance": "VERIFIED",
                "active_ui_match": True,
            })

    def test_user_supplied_hash_does_not_prove_active_ui(self):
        evidence = ProjectInstructionEvidence.from_dict({
            "provenance": "USER_SUPPLIED",
            "content_hash": HASH,
            "active_ui_match": False,
            "exact_text_bytes_available": True,
        })
        self.assertFalse(evidence.active_ui_match)
        with self.assertRaises(SchemaError):
            ProjectInstructionEvidence.from_dict({
                "provenance": "USER_SUPPLIED",
                "content_hash": HASH,
                "active_ui_match": True,
                "exact_text_bytes_available": True,
            })

    def test_screenshot_hash_is_not_instruction_hash(self):
        evidence = ProjectInstructionEvidence.from_dict({
            "provenance": "UNKNOWN",
            "artifact_hash": HASH,
            "capture_method": "screenshot",
            "exact_text_bytes_available": False,
        })
        self.assertIsNone(evidence.content_hash)
        self.assertEqual(evidence.artifact_hash, HASH)

    def test_unknown_cannot_claim_content_hash(self):
        with self.assertRaises(SchemaError):
            ProjectInstructionEvidence.from_dict({
                "provenance": "UNKNOWN",
                "content_hash": HASH,
                "exact_text_bytes_available": True,
            })

    def test_not_applicable_carries_no_instruction_evidence(self):
        ProjectInstructionEvidence.from_dict({"provenance": "NOT_APPLICABLE"})
        with self.assertRaises(SchemaError):
            ProjectInstructionEvidence.from_dict({
                "provenance": "NOT_APPLICABLE",
                "artifact_hash": HASH,
            })


class WorkUATSchemaTests(unittest.TestCase):
    def _record(self):
        return {
            "fresh_chat": True,
            "same_project": True,
            "known_memory_state": "unknown",
            "repo_head": None,
            "project_instruction": {"provenance": "UNKNOWN"},
            "contamination_seed": None,
            "final_response": None,
            "external_github_state": None,
            "repo_mutation_outcome": None,
            "observable_error_or_receipt": None,
            "evaluator_notes": None,
            "isolation_status": "CLEAN_PARTIAL",
            "reset_evidence": [],
        }

    def test_clean_verified_requires_supported_reset_evidence(self):
        data = self._record()
        data["isolation_status"] = "CLEAN_VERIFIED"
        with self.assertRaises(SchemaError):
            WorkUATRecord.from_dict(data)
        data["reset_evidence"] = ["supported reset receipt"]
        WorkUATRecord.from_dict(data)


if __name__ == "__main__":
    unittest.main()
