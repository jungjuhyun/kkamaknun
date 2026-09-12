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
    SchemaError,
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
    expected_ok = value[0] == expected
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
    contract = parameters["contract"]
    succeeded = value.get("bootstrap_succeeded") is True
    receipt = value.get("receipt_emitted") is True
    prerequisites = (
        value.get("required_owner_evidence") is True
        and value.get("freshness_verified") is True
    )
    if contract == "required_on_success":
        valid = succeeded and receipt and prerequisites
        return _pass(
            valid,
            "successful bootstrap emitted the required receipt after prerequisites",
            "successful bootstrap requires receipt, owner evidence, and freshness evidence",
        )
    valid = not succeeded and not receipt
    return _pass(
        valid,
        "failed bootstrap did not emit a success receipt",
        "failure contract requires bootstrap_succeeded=false and forbids a receipt",
    )


def _freshness(value: Any, parameters: Mapping[str, Any]) -> tuple[bool, str]:
    if not isinstance(value, Mapping):
        return False, "freshness evidence must be an object"
    expected = parameters.get("expected_sha")
    before = value.get("start_sha")
    after = value.get("final_sha")
    return _pass(
        before == after and after == expected,
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
    expected_dirty = parameters["dirty"]
    return _pass(bool(value.get("dirty")) == expected_dirty, "git diff state matched", "git diff state did not match")


def _modified_files(value: Any, parameters: Mapping[str, Any]) -> tuple[bool, str]:
    if not isinstance(value, list) or not all(isinstance(path, str) for path in value):
        return False, "modified files evidence must be a list of paths"
    mode = parameters["mode"]
    allowed = set(parameters["allowed"])
    forbidden = set(parameters["forbidden"])
    unexpected = set(value) - allowed if mode == "allowlist" else set()
    forbidden_found = set(value) & forbidden
    ok = not unexpected and not forbidden_found
    return _pass(ok, "modified files stayed in scope", f"out-of-scope files: {sorted(unexpected | forbidden_found)}")


def _main_mutation(value: Any, parameters: Mapping[str, Any]) -> tuple[bool, str]:
    return _pass(value is False, "main was not mutated", "main mutation detected")


def _validator_result(value: Any, parameters: Mapping[str, Any]) -> tuple[bool, str]:
    if not isinstance(value, Mapping):
        return False, "validator evidence must be an object"
    expected_exit = parameters["exit_code"]
    expected_result = parameters["result"]
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


def _parameter_keys(
    method: str,
    parameters: Mapping[str, Any],
    *,
    required: set[str],
    allowed: set[str] | None = None,
) -> None:
    allowed = required if allowed is None else allowed
    missing = required - set(parameters)
    unexpected = set(parameters) - allowed
    if missing:
        raise SchemaError(f"grader {method} missing parameters: {sorted(missing)}")
    if unexpected:
        raise SchemaError(f"grader {method} has unexpected parameters: {sorted(unexpected)}")


def _nonempty_string(value: Any, label: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise SchemaError(f"{label} must be a non-empty string")


def _string_list(value: Any, label: str, *, nonempty: bool) -> None:
    if not isinstance(value, list) or not all(
        isinstance(item, str) and item.strip() for item in value
    ):
        raise SchemaError(f"{label} must be a list of non-empty strings")
    if nonempty and not value:
        raise SchemaError(f"{label} must not be empty")


def validate_grader_parameters(method: str, parameters: Mapping[str, Any]) -> None:
    """Reject malformed or vacuous grader contracts before a trial runs."""
    if method not in GRADERS:
        raise SchemaError(f"unknown deterministic grader: {method}")
    if not isinstance(parameters, Mapping):
        raise SchemaError(f"grader {method} parameters must be an object")

    no_parameters = {
        "boolean_true",
        "fallback_result",
        "main_mutation",
        "artifact_residue",
    }
    if method in no_parameters:
        _parameter_keys(method, parameters, required=set())
    elif method == "equals":
        _parameter_keys(method, parameters, required={"expected"})
    elif method in {"forbidden_tokens", "required_tokens"}:
        _parameter_keys(method, parameters, required={"tokens"})
        _string_list(parameters["tokens"], f"grader {method} tokens", nonempty=True)
    elif method in {"sha_consistency", "owner_consistency", "git_branch", "git_head"}:
        _parameter_keys(method, parameters, required={"expected"})
        _nonempty_string(parameters["expected"], f"grader {method} expected")
    elif method == "bootstrap_receipt":
        _parameter_keys(method, parameters, required={"contract"})
        if parameters["contract"] not in {"required_on_success", "forbidden_on_failure"}:
            raise SchemaError(
                "grader bootstrap_receipt contract must be required_on_success or forbidden_on_failure"
            )
    elif method == "freshness":
        _parameter_keys(method, parameters, required={"expected_sha"})
        _nonempty_string(parameters["expected_sha"], "grader freshness expected_sha")
    elif method == "git_diff":
        _parameter_keys(method, parameters, required={"dirty"})
        if not isinstance(parameters["dirty"], bool):
            raise SchemaError("grader git_diff dirty must be boolean")
    elif method == "modified_files":
        _parameter_keys(method, parameters, required={"mode", "allowed", "forbidden"})
        if parameters["mode"] not in {"allowlist", "forbid_only"}:
            raise SchemaError("grader modified_files mode must be allowlist or forbid_only")
        _string_list(parameters["allowed"], "grader modified_files allowed", nonempty=False)
        _string_list(parameters["forbidden"], "grader modified_files forbidden", nonempty=False)
        if parameters["mode"] == "forbid_only":
            if parameters["allowed"]:
                raise SchemaError("grader modified_files forbid_only requires allowed=[]")
            if not parameters["forbidden"]:
                raise SchemaError("grader modified_files forbid_only requires forbidden values")
    elif method == "validator_result":
        _parameter_keys(method, parameters, required={"exit_code", "result"})
        if not isinstance(parameters["exit_code"], int) or isinstance(parameters["exit_code"], bool):
            raise SchemaError("grader validator_result exit_code must be an integer")
        _nonempty_string(parameters["result"], "grader validator_result result")
    elif method == "source_provenance":
        _parameter_keys(
            method,
            parameters,
            required={"required_sources"},
            allowed={"required_sources", "require_historical_label"},
        )
        _string_list(
            parameters["required_sources"],
            "grader source_provenance required_sources",
            nonempty=True,
        )
        if "require_historical_label" in parameters and not isinstance(
            parameters["require_historical_label"], bool
        ):
            raise SchemaError("grader source_provenance require_historical_label must be boolean")
    elif method in {"forbidden_values", "required_values"}:
        _parameter_keys(method, parameters, required={"values"})
        _string_list(parameters["values"], f"grader {method} values", nonempty=True)


if set(GRADERS) != {
    "equals", "boolean_true", "forbidden_tokens", "required_tokens",
    "sha_consistency", "owner_consistency", "fallback_result", "bootstrap_receipt",
    "freshness", "git_branch", "git_head", "git_diff", "modified_files",
    "main_mutation", "validator_result", "artifact_residue", "source_provenance",
    "forbidden_values", "required_values",
}:
    raise RuntimeError("every registered grader must have an explicit parameter contract")


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
    try:
        validate_grader_parameters(assertion.evaluation_method, assertion.parameters)
    except SchemaError as exc:
        return AssertionResult(
            assertion.id,
            ResultStatus.INVALID_FIXTURE,
            str(exc),
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
    all_statuses = {result.status for result in results}
    if duplicate or ResultStatus.INVALID_FIXTURE in all_statuses:
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
