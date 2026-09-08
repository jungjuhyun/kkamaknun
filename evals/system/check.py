"""One-shot Phase 0-1 validation command."""

from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest

from .schema import (
    EvidenceRecord,
    IsolationProfile,
    IsolationProfileName,
    ResultStatus,
    SchemaError,
    Target,
    TaskSpec,
    WorkUATRecord,
)
from .scorers import GRADERS, grade_trial


SYSTEM_ROOT = Path(__file__).resolve().parent


def load_json(path: Path):
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_tasks() -> dict[str, TaskSpec]:
    tasks: dict[str, TaskSpec] = {}
    for path in sorted((SYSTEM_ROOT / "tasks").glob("*.json")):
        task = TaskSpec.from_dict(load_json(path))
        if task.id in tasks:
            raise SchemaError(f"duplicate task id: {task.id}")
        if path.stem != task.id:
            raise SchemaError(f"task filename must match id: {path.name}")
        unknown_graders = sorted(
            {a.evaluation_method for a in task.assertions if a.evaluation_method not in GRADERS}
        )
        if unknown_graders:
            raise SchemaError(f"task {task.id} uses unknown graders: {unknown_graders}")
        required_sources = {
            assertion.evidence_source for assertion in task.assertions if assertion.required_for_pass
        }
        if required_sources != set(task.required_evidence):
            raise SchemaError(
                f"task {task.id} required_evidence must exactly match required assertion sources"
            )
        if set(task.required_evidence) & set(task.optional_evidence):
            raise SchemaError(f"task {task.id} evidence cannot be both required and optional")
        tasks[task.id] = task
    if not tasks:
        raise SchemaError("no task definitions found")
    return tasks


def validate_fake_environment(task_id: str, environment: object) -> None:
    if not isinstance(environment, dict):
        raise SchemaError("fake_environment must be an object")
    if task_id == "REG-BOOTSTRAP-FALLBACK-001":
        if environment.get("local_checkout_present") is not False:
            raise SchemaError("bootstrap fixture must start without a local checkout")
        if environment.get("first_access_path", {}).get("result") != "error":
            raise SchemaError("bootstrap fixture first access path must fail")
        if environment.get("second_access_path", {}).get("result") != "success":
            raise SchemaError("bootstrap fixture second access path must succeed")
        expected_sha = environment.get("sha")
        owner_shas = {owner.get("sha") for owner in environment.get("owners", {}).values()}
        if not expected_sha or owner_shas != {expected_sha}:
            raise SchemaError("bootstrap fixture owners must share the fixed fixture SHA")
    elif task_id == "REG-PROVENANCE-CONTAMINATION-001":
        marker = "シ·ツ·ソ·ン"
        current_text = environment.get("current_owner", {}).get("text", "")
        historical_text = environment.get("historical_context", {}).get("text", "")
        if marker in current_text or marker not in historical_text:
            raise SchemaError("contamination fixture marker must exist only in historical context")
    elif task_id == "REG-HISTORICAL-RETRIEVAL-REQUIRED-001":
        current = environment.get("current_owner", {})
        historical = environment.get("historical_context", {})
        if current.get("source_class") != "current_owner":
            raise SchemaError("paired fixture current source is mislabeled")
        if historical.get("source_class") != "historical_context":
            raise SchemaError("paired fixture historical source is mislabeled")
        if current.get("text") == historical.get("text"):
            raise SchemaError("paired fixture current and historical content must differ")


def validate_fixture_data(data: dict, label: str, tasks: dict[str, TaskSpec]) -> None:
    required = {"fixture_id", "task_id", "target", "fake_environment", "cases"}
    missing = required - set(data)
    if missing:
        raise SchemaError(f"{label} missing fields: {sorted(missing)}")
    if data["task_id"] not in tasks:
        raise SchemaError(f"fixture references unknown task: {data['task_id']}")
    task = tasks[data["task_id"]]
    if Target(data["target"]) != task.target:
        raise SchemaError(f"fixture target does not match task: {label}")
    validate_fake_environment(data["task_id"], data["fake_environment"])
    cases = data["cases"]
    if not isinstance(cases, list) or not cases:
        raise SchemaError(f"fixture cases must be non-empty: {label}")
    case_ids = set()
    statuses = set()
    for case in cases:
        if not {"id", "expected_status", "evidence"} <= set(case):
            raise SchemaError(f"fixture case is incomplete: {label}")
        if case["id"] in case_ids:
            raise SchemaError(f"duplicate fixture case: {case['id']}")
        case_ids.add(case["id"])
        expected = ResultStatus(case["expected_status"])
        evidence = [EvidenceRecord.from_dict(item) for item in case["evidence"]]
        result = grade_trial(task, evidence)
        if result.status is not expected:
            raise SchemaError(
                f"{label}:{case['id']} expected {expected.value}, got {result.status.value}"
            )
        statuses.add(expected)
    required_proofs = {
        ResultStatus.PASS,
        ResultStatus.FAIL,
        ResultStatus.UNKNOWN,
        ResultStatus.INFRA_ERROR,
        ResultStatus.INVALID_FIXTURE,
    }
    if not required_proofs <= statuses:
        missing_statuses = sorted(status.value for status in required_proofs - statuses)
        raise SchemaError(f"{label} missing proof cases: {missing_statuses}")


def validate_fixture(path: Path, tasks: dict[str, TaskSpec]) -> None:
    data = load_json(path)
    if path.stem != data.get("task_id"):
        raise SchemaError(f"fixture filename must match task_id: {path.name}")
    validate_fixture_data(data, path.name, tasks)


def validate_observation_matrix() -> None:
    data = load_json(SYSTEM_ROOT / "observation_matrix.json")
    targets = data.get("targets")
    if not isinstance(targets, list):
        raise SchemaError("observation matrix targets must be a list")
    seen = {Target(item["target"]) for item in targets}
    if seen != set(Target):
        raise SchemaError("observation matrix must define each target exactly once")
    for item in targets:
        for field in (
            "observable_evidence",
            "non_observable_evidence",
            "deterministic_grader",
            "state_outcome_grader",
            "trace_dependency",
            "missing_evidence",
            "pass_condition",
            "unknown_condition",
            "infra_error_condition",
        ):
            if field not in item:
                raise SchemaError(f"observation matrix missing {field}")
        if item["missing_evidence"] != ResultStatus.UNKNOWN.value:
            raise SchemaError("every target must classify missing evidence as UNKNOWN")


def validate_isolation_profiles() -> None:
    data = load_json(SYSTEM_ROOT / "isolation_profiles.json")
    profiles = [IsolationProfile.from_dict(item) for item in data.get("profiles", [])]
    if len(profiles) != len(IsolationProfileName) or {profile.name for profile in profiles} != set(IsolationProfileName):
        raise SchemaError("isolation profiles must define every profile exactly once")


def validate_uat_template() -> None:
    WorkUATRecord.from_dict(load_json(SYSTEM_ROOT / "actual_work_uat_template.json"))


def validate_all_data() -> None:
    tasks = load_tasks()
    fixture_paths = sorted((SYSTEM_ROOT / "fixtures").glob("*.json"))
    if {path.stem for path in fixture_paths} != set(tasks):
        raise SchemaError("every seed task must have exactly one same-named fixture")
    for path in fixture_paths:
        validate_fixture(path, tasks)
    validate_observation_matrix()
    validate_isolation_profiles()
    validate_uat_template()


def main() -> int:
    try:
        validate_all_data()
    except (SchemaError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"DATA VALIDATION FAILED: {exc}", file=sys.stderr)
        return 1
    suite = unittest.defaultTestLoader.discover(str(SYSTEM_ROOT / "tests"))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        return 1
    print("Phase 0-1 system evaluation checks: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
