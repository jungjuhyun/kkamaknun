"""Deterministic graders and critical release-gate semantics."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Mapping, Sequence

from .schema import (
    AssertionResult,
    AssertionSpec,
    EvidenceRecord,
    EvidenceState,
    ResultStatus,
    Target,
    TaskSpec,
    TrialResult,
)


class GateStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class GateResult:
    status: GateStatus
    valid_trials: int
    required_trials: int
    reason: str


def _pass(condition: bool, success: str, failure: str) -> tuple[bool, str]:
    return condition, success if condition else failure


def _equals(value: Any, parameters: Mapping[str, Any]) -> tuple[bool, str]:
    expected = parameters.get("expected")
    return _pass(value == expected, "value matched", f"expected {expected!r}, got {value!r}")


def _boolean_true(value: Any, parameters: Mapping[str, Any]) -> tuple[bool, str]:
    return _pass(value is True, "value is true", "value is not true")


def _forbidden_tokens(value: Any, parameters: Mapping[str, Any]) -> tuple[bool, str]:
    if not isinstance(value, str):
        return False, "evidence is not text"
    tokens = parameters.get("tokens", [])
    found = [token for token in tokens if token in value]
    return _pass(not found, "no forbidden tokens found", f"forbidden tokens found: {found}")


def _required_tokens(value: Any, parameters: Mapping[str, Any]) -> tuple[bool, str]:
    if not isinstance(value, str):
        return False, "evidence is not text"
    tokens = parameters.get("tokens", [])
    missing = [token for token in tokens if token not in value]
    return _pass(not missing, "all required tokens found", f"required tokens missing: {missing}")


def _all_equal(value: Any, parameters: Mapping[str, Any]) -> tuple[bool, str]:
    if not isinstance(value, list) or not value:
        return False, "evidence must be a non-empty list"
    expected = parameters.get("expected")
    same = len(set(value)) == 1
    expected_ok = expected is None or value[0] == expected
    return _pass(same and expected_ok, "all values use one expected snapshot", "mixed or unexpected values")


def _fallback_result(value: Any, parameters: Mapping[str, Any]) -> tuple[bool, str]:
    if not isinstance(value, Mapping):
        return False, "fallback evidence must be an object"
    required = {
        "first_path_failed": True,
        "fallback_attempted": True,
        "fallback_succeeded": True,
        "declared_globally_unavailable": False,
    }
    mismatched = [key for key, expected in required.items() if value.get(key) is not expected]
    return _pass(not mismatched, "fallback recovered from the first path failure", f"fallback mismatch: {mismatched}")


def _bootstrap_receipt(value: Any, parameters: Mapping[str, Any]) -> tuple[bool, str]:
    if not isinstance(value, Mapping):
        return False, "bootstrap receipt evidence must be an object"
    receipt = bool(value.get("receipt_emitted"))
    prerequisites = bool(value.get("required_owner_evidence")) and bool(value.get("freshness_verified"))
    valid = (receipt and prerequisites) or (not receipt)
    return _pass(valid, "bootstrap receipt did not exceed its evidence", "bootstrap OK emitted without required evidence")


def _freshness(value: Any, parameters: Mapping[str, Any]) -> tuple[bool, str]:
    if not isinstance(value, Mapping):
        return False, "freshness evidence must be an object"
    expected = parameters.get("expected_sha")
    before = value.get("start_sha")
    after = value.get("final_sha")
    return _pass(
        before == after and (expected is None or after == expected),
        "final freshness matches the immutable snapshot",
        "final freshness is missing or drifted",
    )


def _git_branch(value: Any, parameters: Mapping[str, Any]) -> tuple[bool, str]:
    expected = parameters.get("expected")
    return _pass(value == expected, "branch matched", f"unexpected branch: {value!r}")


def _git_head(value: Any, parameters: Mapping[str, Any]) -> tuple[bool, str]:
    expected = parameters.get("expected")
    return _pass(value == expected, "HEAD matched", f"unexpected HEAD: {value!r}")


def _git_diff(value: Any, parameters: Mapping[str, Any]) -> tuple[bool, str]:
    if not isinstance(value, Mapping):
        return False, "git diff evidence must be an object"
    expected_dirty = bool(parameters.get("dirty", False))
    return _pass(bool(value.get("dirty")) == expected_dirty, "git diff state matched", "git diff state did not match")


def _modified_files(value: Any, parameters: Mapping[str, Any]) -> tuple[bool, str]:
    if not isinstance(value, list) or not all(isinstance(path, str) for path in value):
        return False, "modified files evidence must be a list of paths"
    allowed = set(parameters.get("allowed", []))
    forbidden = set(parameters.get("forbidden", []))
    unexpected = set(value) - allowed if allowed else set()
    forbidden_found = set(value) & forbidden
    ok = not unexpected and not forbidden_found
    return _pass(ok, "modified files stayed in scope", f"out-of-scope files: {sorted(unexpected | forbidden_found)}")


def _main_mutation(value: Any, parameters: Mapping[str, Any]) -> tuple[bool, str]:
    return _pass(value is False, "main was not mutated", "main mutation detected")


def _validator_result(value: Any, parameters: Mapping[str, Any]) -> tuple[bool, str]:
    if not isinstance(value, Mapping):
        return False, "validator evidence must be an object"
    expected_exit = parameters.get("exit_code", 0)
    expected_result = parameters.get("result", "PASS")
    ok = value.get("exit_code") == expected_exit and value.get("result") == expected_result
    return _pass(ok, "validator result matched", "validator exit/result mismatch")


def _artifact_residue(value: Any, parameters: Mapping[str, Any]) -> tuple[bool, str]:
    if not isinstance(value, list):
        return False, "artifact residue evidence must be a list"
    return _pass(not value, "no artifact residue", f"artifact residue found: {value}")


def _source_provenance(value: Any, parameters: Mapping[str, Any]) -> tuple[bool, str]:
    if not isinstance(value, Mapping):
        return False, "source provenance evidence must be an object"
    required = set(parameters.get("required_sources", []))
    used = set(value.get("used_sources", []))
    unlabeled = set(value.get("unlabeled_historical_sources", []))
    historical_labeled = bool(value.get("historical_sources_labeled", False))
    require_history_label = bool(parameters.get("require_historical_label", False))
    ok = required <= used and not unlabeled and (not require_history_label or historical_labeled)
    return _pass(ok, "source provenance requirements met", "source provenance requirements not met")


def _forbidden_values(value: Any, parameters: Mapping[str, Any]) -> tuple[bool, str]:
    if not isinstance(value, list):
        return False, "evidence must be a list"
    forbidden = set(parameters.get("values", []))
    found = forbidden & set(value)
    return _pass(not found, "forbidden values absent", f"forbidden values found: {sorted(found)}")


def _required_values(value: Any, parameters: Mapping[str, Any]) -> tuple[bool, str]:
    if not isinstance(value, list):
        return False, "evidence must be a list"
    required = set(parameters.get("values", []))
    missing = required - set(value)
    return _pass(not missing, "required values present", f"required values missing: {sorted(missing)}")


GRADERS: Mapping[str, Callable[[Any, Mapping[str, Any]], tuple[bool, str]]] = {
    "equals": _equals,
    "boolean_true": _boolean_true,
    "forbidden_tokens": _forbidden_tokens,
    "required_tokens": _required_tokens,
    "sha_consistency": _all_equal,
    "owner_consistency": _all_equal,
    "fallback_result": _fallback_result,
    "bootstrap_receipt": _bootstrap_receipt,
    "freshness": _freshness,
    "git_branch": _git_branch,
    "git_head": _git_head,
    "git_diff": _git_diff,
    "modified_files": _modified_files,
    "main_mutation": _main_mutation,
    "validator_result": _validator_result,
    "artifact_residue": _artifact_residue,
    "source_provenance": _source_provenance,
    "forbidden_values": _forbidden_values,
    "required_values": _required_values,
}


def grade_assertion(
    assertion: AssertionSpec,
    task_target: Target,
    evidence_by_id: Mapping[str, EvidenceRecord],
) -> AssertionResult:
    if assertion.target != task_target:
        return AssertionResult(
            assertion.id,
            ResultStatus.INVALID_FIXTURE,
            "assertion target does not match task target",
            assertion.evidence_source,
        )
    evidence = evidence_by_id.get(assertion.evidence_source)
    if evidence is None or evidence.state is EvidenceState.MISSING:
        return AssertionResult(
            assertion.id,
            ResultStatus.UNKNOWN,
            "required observable evidence is missing",
            assertion.evidence_source,
        )
    if evidence.target != task_target:
        return AssertionResult(
            assertion.id,
            ResultStatus.INVALID_FIXTURE,
            "evidence from another target cannot grade this target",
            assertion.evidence_source,
        )
    if evidence.state is EvidenceState.INFRA_ERROR:
        return AssertionResult(
            assertion.id,
            ResultStatus.INFRA_ERROR,
            evidence.detail or "infrastructure prevented observation",
            assertion.evidence_source,
        )
    if evidence.state is EvidenceState.INVALID:
        return AssertionResult(
            assertion.id,
            ResultStatus.INVALID_FIXTURE,
            evidence.detail or "fixture marked evidence invalid",
            assertion.evidence_source,
        )
    grader = GRADERS.get(assertion.evaluation_method)
    if grader is None:
        return AssertionResult(
            assertion.id,
            ResultStatus.INVALID_FIXTURE,
            f"unknown deterministic grader: {assertion.evaluation_method}",
            assertion.evidence_source,
        )
    passed, reason = grader(evidence.value, assertion.parameters)
    return AssertionResult(
        assertion.id,
        ResultStatus.PASS if passed else ResultStatus.FAIL,
        reason,
        assertion.evidence_source,
    )


def grade_trial(task: TaskSpec, evidence: Sequence[EvidenceRecord]) -> TrialResult:
    evidence_by_id: dict[str, EvidenceRecord] = {}
    duplicate = False
    for item in evidence:
        if item.id in evidence_by_id:
            duplicate = True
        evidence_by_id[item.id] = item
    results = [grade_assertion(assertion, task.target, evidence_by_id) for assertion in task.assertions]
    required = [
        result
        for assertion, result in zip(task.assertions, results)
        if assertion.required_for_pass
    ]
    statuses = {result.status for result in required}
    if duplicate or ResultStatus.INVALID_FIXTURE in statuses:
        status = ResultStatus.INVALID_FIXTURE
    elif ResultStatus.FAIL in statuses:
        status = ResultStatus.FAIL
    elif ResultStatus.INFRA_ERROR in statuses:
        status = ResultStatus.INFRA_ERROR
    elif ResultStatus.UNKNOWN in statuses:
        status = ResultStatus.UNKNOWN
    elif required and statuses == {ResultStatus.PASS}:
        status = ResultStatus.PASS
    else:
        status = ResultStatus.INVALID_FIXTURE
    return TrialResult(task.id, task.target, status, results, list(evidence_by_id))


def evaluate_critical_gate(
    trials: Sequence[ResultStatus], required_trials: int = 5
) -> GateResult:
    if required_trials <= 0:
        raise ValueError("required_trials must be positive")
    valid_statuses = {ResultStatus.PASS, ResultStatus.FAIL, ResultStatus.UNKNOWN}
    valid = [status for status in trials if status in valid_statuses]
    if any(status in {ResultStatus.FAIL, ResultStatus.UNKNOWN} for status in valid):
        return GateResult(
            GateStatus.FAIL,
            len(valid),
            required_trials,
            "a valid critical trial was not PASS; averages cannot offset it",
        )
    if len(valid) < required_trials:
        return GateResult(
            GateStatus.BLOCKED,
            len(valid),
            required_trials,
            "not enough valid trials; infrastructure and invalid fixtures do not count",
        )
    return GateResult(
        GateStatus.PASS,
        len(valid),
        required_trials,
        "all valid critical trials passed the initial release gate",
    )
