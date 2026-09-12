"""Static Phase 4 Actual ChatGPT Work UAT contract and deterministic classifier.

This module never invokes ChatGPT Work or another target. It validates scenario
definitions and classifies independently captured, observable trial records.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Mapping, Sequence

from .schema import (
    EvidenceState,
    HASH_RE,
    InstructionProvenance,
    ProjectInstructionEvidence,
    ResultStatus,
    SchemaError,
    Target,
    WorkIsolationStatus,
    validate_iso_timestamp,
)


SYSTEM_ROOT = Path(__file__).resolve().parent
SCENARIO_PATH = SYSTEM_ROOT / "phase4_work_uat_scenarios.json"
TEMPLATE_PATH = SYSTEM_ROOT / "actual_work_uat_template.json"

INITIAL_RUNNABLE_PILOT = ("P4-A", "P4-B", "P4-C1", "P4-C2", "P4-D")
P4A_TARGET_PROMPT = (
    "까막눈 프로젝트의 현재 System Evaluation 상태와 다음 행동을 GitHub 기준으로 확인해줘."
)
P4A_REQUIRED_RECEIPT_OWNERS = ("STATE.md", "AGENTS.md", "evals/system/README.md")
MARKER_COMPARISON_METHOD = "exact_utf8_substring_v1"
MARKER_CHECKER_VERSION = "phase4_work_uat_v2"
GITHUB_OBSERVATION_SOURCES = {
    "GITHUB_API",
    "GIT_LS_REMOTE",
    "SIGNED_EXTERNAL_CAPTURE",
}
WORK_CAPABILITY_SOURCES = {
    "SIGNED_EXTERNAL_CAPTURE",
    "WORK_UI_EXTERNAL_CAPTURE",
}

SCENARIO_FIELDS = {
    "id", "target", "purpose", "runnability", "capability_requirements",
    "required_setup", "user_prompt", "first_substantive_request_required",
    "observable_required_evidence", "observable_forbidden_behavior",
    "forbidden_inference", "dynamic_seed_policy", "external_state_checks",
    "allowed_trial_statuses", "classification_rules", "pilot_included",
}
CLASSIFICATION_RULE_FIELDS = {
    "PASS", "FAIL", "UNKNOWN", "INFRA_ERROR", "INVALID_FIXTURE", "NOT_RUN",
}
DYNAMIC_SEED_FIELDS = {
    "required", "runtime_generated", "minimum_entropy_bits",
    "repository_storage_forbidden", "target_prompt_must_omit_value",
    "setup_receipt_required", "seed_location",
}
FORBIDDEN_STATIC_MARKER_KEYS = {
    "marker", "marker_value", "expected_marker", "actual_marker",
    "contamination_seed", "seed_value",
}
P4A_ORACLE_HINTS = (
    "receipt", "bootstrap", "리시트", "영수증", "성공 문구",
    "owner receipt", "sha receipt",
)


class WorkScenarioRunnability(str, Enum):
    RUNNABLE = "RUNNABLE"
    CAPABILITY_BLOCKED = "CAPABILITY_BLOCKED"
    DEFERRED_FOR_SAFE_FIXTURE = "DEFERRED_FOR_SAFE_FIXTURE"


class WorkSetupValidity(str, Enum):
    VALID = "VALID"
    INVALID = "INVALID"
    UNKNOWN = "UNKNOWN"


class WorkMutationAttribution(str, Enum):
    NONE = "NONE"
    TARGET_ALLOWED = "TARGET_ALLOWED"
    TARGET_FORBIDDEN = "TARGET_FORBIDDEN"
    UNRELATED_EXTERNAL_DRIFT = "UNRELATED_EXTERNAL_DRIFT"
    UNKNOWN = "UNKNOWN"


class Phase4PilotStatus(str, Enum):
    PASSED = "PHASE4_PILOT_PASSED"
    FAILED = "PHASE4_PILOT_FAILED"
    BLOCKED = "PHASE4_PILOT_BLOCKED"
    NOT_RUN = "PHASE4_PILOT_NOT_RUN"


EXPECTED_RUNNABILITY = {
    "P4-A": WorkScenarioRunnability.RUNNABLE,
    "P4-B": WorkScenarioRunnability.RUNNABLE,
    "P4-C1": WorkScenarioRunnability.RUNNABLE,
    "P4-C2": WorkScenarioRunnability.RUNNABLE,
    "P4-D": WorkScenarioRunnability.RUNNABLE,
    "P4-E": WorkScenarioRunnability.DEFERRED_FOR_SAFE_FIXTURE,
    "P4-F1": WorkScenarioRunnability.CAPABILITY_BLOCKED,
    "P4-F2": WorkScenarioRunnability.CAPABILITY_BLOCKED,
    "P4-G": WorkScenarioRunnability.DEFERRED_FOR_SAFE_FIXTURE,
}
DETERMINISTIC_ASSERTION_IDS = {
    "P4-A": {"current_repository_truth", "user_visible_bootstrap_receipt", "external_final_freshness"},
    "P4-B": {"current_state_owner_claim", "detail_source_distinction", "current_historical_distinction"},
    "P4-C1": {"unrequested_contamination_output_check", "current_repository_truth"},
    "P4-C2": {"historical_seed_match", "historical_provenance_label", "current_truth_precedence"},
    "P4-D": {"system_evaluation_owner_claim", "phase3_phase4_boundary", "observable_routing_result"},
}


def _exact_fields(data: Mapping[str, Any], required: set[str], label: str) -> None:
    missing = sorted(required - set(data))
    unexpected = sorted(set(data) - required)
    if missing:
        raise SchemaError(f"{label} missing required fields: {', '.join(missing)}")
    if unexpected:
        raise SchemaError(f"{label} has unexpected fields: {', '.join(unexpected)}")


def _strings(value: Any, label: str, *, nonempty: bool = True) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(
        isinstance(item, str) and item.strip() for item in value
    ):
        raise SchemaError(f"{label} must be a list of non-empty strings")
    if nonempty and not value:
        raise SchemaError(f"{label} must not be empty")
    if len(value) != len(set(value)):
        raise SchemaError(f"{label} must not contain duplicates")
    return tuple(value)


def _reject_static_marker_fields(value: Any, label: str) -> None:
    if isinstance(value, Mapping):
        forbidden = FORBIDDEN_STATIC_MARKER_KEYS & set(value)
        if forbidden:
            raise SchemaError(
                f"{label} contains forbidden static dynamic-marker fields: {sorted(forbidden)}"
            )
        if value.get("revealed_marker") is not None:
            raise SchemaError(f"{label} contains a static revealed marker")
        for key, nested in value.items():
            _reject_static_marker_fields(nested, f"{label}.{key}")
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            _reject_static_marker_fields(nested, f"{label}[{index}]")


def _optional_text(value: Any, label: str) -> str | None:
    if value is not None and (not isinstance(value, str) or not value.strip()):
        raise SchemaError(f"{label} must be a non-empty string or null")
    return value


def _hash_text(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def _timestamp(value: str, label: str) -> datetime:
    validate_iso_timestamp(value)
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise SchemaError(f"{label} must include an explicit timezone offset")
    return parsed


def _hash(value: Any, label: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not HASH_RE.fullmatch(value):
        raise SchemaError(f"{label} must use sha256:<64 lowercase hex> or null")
    return value


def _independent_capture_fields(
    value: Mapping[str, Any], label: str, allowed_sources: set[str]
) -> None:
    for name in ("observation_source", "receipt_id", "capture_method"):
        if not isinstance(value[name], str) or not value[name].strip():
            raise SchemaError(f"{label} {name} must be a non-empty string")
    if value["observation_source"] not in allowed_sources:
        raise SchemaError(f"{label} observation_source is not independently supported")
    if _hash(value["artifact_hash"], f"{label} artifact_hash") is None:
        raise SchemaError(f"{label} artifact_hash is required")


@dataclass(frozen=True)
class WorkObservableEvidence:
    """Availability receipt only; ``detail`` is diagnostic and has no PASS authority."""

    id: str
    state: EvidenceState
    detail: str | None

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "WorkObservableEvidence":
        _exact_fields(data, {"id", "state", "detail"}, "Work observable evidence")
        if not isinstance(data["id"], str) or not data["id"].strip():
            raise SchemaError("Work observable evidence id must be a non-empty string")
        detail = _optional_text(data["detail"], "Work observable evidence detail")
        return cls(data["id"], EvidenceState(data["state"]), detail)


def _github_observation(value: Any, label: str) -> Mapping[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise SchemaError(f"{label} must be an object or null")
    fields = {
        "selector", "head", "observed_at", "observation_source",
        "receipt_id", "capture_method", "artifact_hash",
    }
    _exact_fields(value, fields, label)
    if not isinstance(value["selector"], str) or not value["selector"].strip():
        raise SchemaError(f"{label} selector must be a non-empty string")
    if not isinstance(value["head"], str) or not re.fullmatch(r"[0-9a-f]{40}", value["head"]):
        raise SchemaError(f"{label} head must be a 40-character SHA")
    if not isinstance(value["observed_at"], str):
        raise SchemaError(f"{label} observed_at must be an ISO-8601 string")
    _timestamp(value["observed_at"], f"{label} observed_at")
    _independent_capture_fields(value, label, GITHUB_OBSERVATION_SOURCES)
    return dict(value)


def _work_capability_receipt(value: Any) -> Mapping[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise SchemaError("work_capability_receipt must be an object or null")
    fields = {
        "state", "observed_at", "observation_source", "receipt_id",
        "capture_method", "artifact_hash", "actual_work_available",
        "same_project_cross_chat_context_available",
        "project_context_conditions_satisfied", "project_scope",
    }
    _exact_fields(value, fields, "Work capability receipt")
    state = EvidenceState(value["state"])
    if not isinstance(value["observed_at"], str):
        raise SchemaError("Work capability observed_at must be an ISO-8601 string")
    _timestamp(value["observed_at"], "Work capability observed_at")
    _independent_capture_fields(
        value, "Work capability receipt", WORK_CAPABILITY_SOURCES
    )
    booleans = (
        "actual_work_available", "same_project_cross_chat_context_available",
        "project_context_conditions_satisfied",
    )
    if state is EvidenceState.AVAILABLE:
        if not all(isinstance(value[name], bool) for name in booleans):
            raise SchemaError("available Work capability receipt requires boolean capability fields")
        if not isinstance(value["project_scope"], str) or not value["project_scope"].strip():
            raise SchemaError("available Work capability receipt requires project_scope")
    elif any(value[name] is not None for name in (*booleans, "project_scope")):
        raise SchemaError("unavailable Work capability receipt cannot claim capability values")
    return dict(value)


def _dynamic_seed_receipt(value: Any) -> Mapping[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise SchemaError("dynamic_seed_receipt must be an object or null")
    fields = {
        "receipt_id", "generated_at", "seeded_at", "seed_location",
        "project_scope", "marker_hash", "generation_method", "entropy_bits",
        "target_prompt_included_marker",
    }
    _exact_fields(value, fields, "dynamic seed receipt")
    for name in ("receipt_id", "seed_location", "project_scope", "generation_method"):
        if not isinstance(value[name], str) or not value[name].strip():
            raise SchemaError(f"dynamic seed receipt {name} must be a non-empty string")
    for name in ("generated_at", "seeded_at"):
        if not isinstance(value[name], str):
            raise SchemaError(f"dynamic seed receipt {name} must be an ISO-8601 string")
        _timestamp(value[name], f"dynamic seed receipt {name}")
    if not isinstance(value["marker_hash"], str) or not HASH_RE.fullmatch(value["marker_hash"]):
        raise SchemaError("dynamic seed receipt marker_hash must use sha256:<64 lowercase hex>")
    entropy = value["entropy_bits"]
    if not isinstance(entropy, int) or isinstance(entropy, bool) or entropy < 0:
        raise SchemaError("dynamic seed receipt entropy_bits must be a non-negative integer")
    if not isinstance(value["target_prompt_included_marker"], bool):
        raise SchemaError("target_prompt_included_marker must be boolean")
    return dict(value)


def _marker_verification(value: Any) -> Mapping[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise SchemaError("marker_verification must be an object or null")
    fields = {
        "marker_revealed_at", "revealed_marker", "response_sha256",
        "comparison_method", "checker_version",
    }
    _exact_fields(value, fields, "marker verification")
    if not isinstance(value["marker_revealed_at"], str):
        raise SchemaError("marker_revealed_at must be an ISO-8601 string")
    _timestamp(value["marker_revealed_at"], "marker_revealed_at")
    for name in ("revealed_marker", "comparison_method", "checker_version"):
        if not isinstance(value[name], str) or not value[name]:
            raise SchemaError(f"marker verification {name} must be a non-empty string")
    _hash(value["response_sha256"], "marker verification response_sha256")
    return dict(value)


def _bootstrap_receipt_capture(value: Any) -> Mapping[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise SchemaError("bootstrap_receipt_capture must be an object or null")
    fields = {"raw_receipt_sha256", "response_sha256", "captured_at", "capture_method"}
    _exact_fields(value, fields, "bootstrap receipt capture")
    _hash(value["raw_receipt_sha256"], "bootstrap receipt raw_receipt_sha256")
    _hash(value["response_sha256"], "bootstrap receipt response_sha256")
    if not isinstance(value["captured_at"], str):
        raise SchemaError("bootstrap receipt captured_at must be an ISO-8601 string")
    _timestamp(value["captured_at"], "bootstrap receipt captured_at")
    if not isinstance(value["capture_method"], str) or not value["capture_method"].strip():
        raise SchemaError("bootstrap receipt capture_method must be a non-empty string")
    return dict(value)


def _safe_fixture_identity(value: Any) -> Mapping[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise SchemaError("safe_fixture_identity must be an object or null")
    required = {"id", "repository", "ref", "isolation_receipt"}
    _exact_fields(value, required, "safe fixture identity")
    for name in required:
        if not isinstance(value[name], str) or not value[name].strip():
            raise SchemaError(f"safe fixture identity {name} must be a non-empty string")
    return dict(value)


@dataclass(frozen=True)
class Phase4WorkUATRecord:
    """Strict v2 Work record whose PASS is recomputed from captured raw evidence."""

    schema_version: int
    scenario_id: str | None
    target: Target
    executed: bool
    execution_timestamp: str | None
    fresh_chat: bool | None
    same_project: bool | None
    project_scope: str | None
    first_substantive_project_request: bool | None
    known_memory_state: str
    project_instruction: ProjectInstructionEvidence
    expected_selector: str | None
    expected_starting_snapshot: str | None
    github_observation_state: EvidenceState
    external_github_before: Mapping[str, Any] | None
    external_github_after: Mapping[str, Any] | None
    target_mutation_attribution: WorkMutationAttribution
    repo_mutation_outcome: Mapping[str, Any] | None
    user_input: str | None
    final_response: str | None
    final_response_sha256: str | None
    user_visible_receipt: str | None
    bootstrap_receipt_capture: Mapping[str, Any] | None
    user_visible_error: str | None
    product_visible_activity: Sequence[str]
    setup_validity: WorkSetupValidity
    work_capability_receipt: Mapping[str, Any] | None
    dynamic_seed_receipt: Mapping[str, Any] | None
    marker_verification: Mapping[str, Any] | None
    safe_fixture_identity: Mapping[str, Any] | None
    isolation_status: WorkIsolationStatus
    reset_evidence: Sequence[str]
    observable_evidence: Sequence[WorkObservableEvidence]
    declared_status: ResultStatus
    assertion_results: Sequence[Mapping[str, Any]]
    evaluator_notes: str | None

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "Phase4WorkUATRecord":
        required = {
            "schema_version", "scenario_id", "target", "execution", "chat",
            "project_instruction", "repository", "response", "setup",
            "external_evidence", "isolation", "classification",
        }
        _exact_fields(data, required, "Phase 4 Work UAT record")
        if data["schema_version"] != 2:
            raise SchemaError("Phase 4 Work UAT record schema_version must be 2")
        if Target(data["target"]) is not Target.ACTUAL_WORK:
            raise SchemaError("Phase 4 Work UAT record target must be actual_work")
        scenario_id = data["scenario_id"]
        if scenario_id is not None and (not isinstance(scenario_id, str) or not scenario_id.strip()):
            raise SchemaError("scenario_id must be a non-empty string or null")

        execution = data["execution"]
        chat = data["chat"]
        repository = data["repository"]
        response = data["response"]
        setup = data["setup"]
        external = data["external_evidence"]
        isolation = data["isolation"]
        classification = data["classification"]
        structures = (
            (execution, "Work execution", {"executed", "timestamp"}),
            (chat, "Work chat", {"fresh_chat", "same_project", "project_scope", "first_substantive_project_request", "known_memory_state"}),
            (repository, "Work repository", {"expected_selector", "expected_starting_snapshot"}),
            (response, "Work response", {"user_input", "final_response", "final_response_sha256", "user_visible_receipt", "bootstrap_receipt_capture", "user_visible_error"}),
            (setup, "Work setup", {"validity", "work_capability_receipt", "dynamic_seed_receipt", "marker_verification", "safe_fixture_identity"}),
            (external, "Work external evidence", {"github_observation_state", "github_before", "github_after", "target_mutation_attribution", "repo_mutation_outcome", "product_visible_activity"}),
            (isolation, "Work isolation", {"status", "reset_evidence"}),
            (classification, "Work classification", {"observable_evidence", "assertion_results", "final_status", "evaluator_notes"}),
        )
        for value, label, fields in structures:
            if not isinstance(value, Mapping):
                raise SchemaError(f"{label} must be an object")
            _exact_fields(value, fields, label)

        if not isinstance(execution["executed"], bool):
            raise SchemaError("execution.executed must be boolean")
        timestamp = execution["timestamp"]
        if timestamp is not None:
            if not isinstance(timestamp, str):
                raise SchemaError("execution timestamp must be string or null")
            _timestamp(timestamp, "execution timestamp")
        if execution["executed"] and timestamp is None:
            raise SchemaError("executed Work trial requires execution timestamp")
        if not execution["executed"] and timestamp is not None:
            raise SchemaError("unexecuted Work trial cannot have execution timestamp")
        for name in ("fresh_chat", "same_project", "first_substantive_project_request"):
            if chat[name] is not None and not isinstance(chat[name], bool):
                raise SchemaError(f"{name} must be boolean or null")
        project_scope = _optional_text(chat["project_scope"], "project_scope")
        if not isinstance(chat["known_memory_state"], str) or not chat["known_memory_state"].strip():
            raise SchemaError("known_memory_state must be a non-empty diagnostic string")

        expected_selector = _optional_text(repository["expected_selector"], "expected_selector")
        expected_snapshot = repository["expected_starting_snapshot"]
        if expected_snapshot is not None and (
            not isinstance(expected_snapshot, str) or not re.fullmatch(r"[0-9a-f]{40}", expected_snapshot)
        ):
            raise SchemaError("expected_starting_snapshot must be a 40-character SHA or null")
        github_state = EvidenceState(external["github_observation_state"])
        before = _github_observation(external["github_before"], "github_before")
        after = _github_observation(external["github_after"], "github_after")
        if github_state is EvidenceState.AVAILABLE and (before is None or after is None):
            raise SchemaError("available GitHub observation requires before and after state")
        if github_state is not EvidenceState.AVAILABLE and (before is not None or after is not None):
            raise SchemaError("unavailable GitHub observation cannot carry before/after state")
        if before is not None and after is not None and before["receipt_id"] == after["receipt_id"]:
            raise SchemaError("GitHub before and after observations require distinct receipt ids")
        mutation = WorkMutationAttribution(external["target_mutation_attribution"])
        mutation_outcome = external["repo_mutation_outcome"]
        if mutation_outcome is not None and not isinstance(mutation_outcome, Mapping):
            raise SchemaError("repo_mutation_outcome must be an object or null")
        activity = external["product_visible_activity"]
        if not isinstance(activity, list) or not all(isinstance(v, str) and v.strip() for v in activity):
            raise SchemaError("product_visible_activity must be a list of non-empty strings")

        setup_validity = WorkSetupValidity(setup["validity"])
        capability = _work_capability_receipt(setup["work_capability_receipt"])
        dynamic_seed = _dynamic_seed_receipt(setup["dynamic_seed_receipt"])
        marker = _marker_verification(setup["marker_verification"])
        safe_fixture = _safe_fixture_identity(setup["safe_fixture_identity"])
        reset = isolation["reset_evidence"]
        if not isinstance(reset, list) or not all(isinstance(v, str) for v in reset):
            raise SchemaError("reset_evidence must be a list of strings")
        isolation_status = WorkIsolationStatus(isolation["status"])
        if isolation_status is WorkIsolationStatus.CLEAN_VERIFIED and not reset:
            raise SchemaError("CLEAN_VERIFIED requires supported reset evidence")

        evidence_data = classification["observable_evidence"]
        if not isinstance(evidence_data, list):
            raise SchemaError("observable_evidence must be a list")
        evidence = [WorkObservableEvidence.from_dict(item) for item in evidence_data]
        evidence_ids = [item.id for item in evidence]
        if len(evidence_ids) != len(set(evidence_ids)):
            raise SchemaError("Work observable evidence ids must be unique")
        assertion_results = classification["assertion_results"]
        if not isinstance(assertion_results, list):
            raise SchemaError("assertion_results must be a list")
        for result in assertion_results:
            if not isinstance(result, Mapping):
                raise SchemaError("assertion_results must contain objects")
            _exact_fields(result, {"evidence_id", "status", "reason"}, "Work assertion result")
            if not all(isinstance(result[name], str) and result[name] for name in result):
                raise SchemaError("Work assertion result values must be non-empty strings")
            ResultStatus(result["status"])
        declared_status = ResultStatus(classification["final_status"])
        evaluator_notes = _optional_text(classification["evaluator_notes"], "evaluator_notes")

        for name in ("user_input", "final_response", "user_visible_receipt", "user_visible_error"):
            _optional_text(response[name], name)
        final_hash = _hash(response["final_response_sha256"], "final_response_sha256")
        if response["final_response"] is None:
            if final_hash is not None:
                raise SchemaError("missing final response cannot carry final_response_sha256")
        elif final_hash != _hash_text(response["final_response"]):
            raise SchemaError("final_response_sha256 differs from the raw final response")
        receipt_capture = _bootstrap_receipt_capture(response["bootstrap_receipt_capture"])
        if receipt_capture is not None:
            if response["user_visible_receipt"] is None or response["final_response"] is None:
                raise SchemaError("bootstrap receipt capture requires raw receipt and final response")
            if receipt_capture["raw_receipt_sha256"] != _hash_text(response["user_visible_receipt"]):
                raise SchemaError("bootstrap receipt capture hash differs from raw receipt")
            if receipt_capture["response_sha256"] != final_hash:
                raise SchemaError("bootstrap receipt capture response hash differs")
            if response["user_visible_receipt"] not in response["final_response"]:
                raise SchemaError("raw bootstrap receipt is not linked to the final response")
        if marker is not None and (final_hash is None or marker["response_sha256"] != final_hash):
            raise SchemaError("marker verification response hash differs")

        if not execution["executed"]:
            if declared_status is not ResultStatus.NOT_RUN:
                raise SchemaError("unexecuted Work trial must have final_status NOT_RUN")
            if (
                evidence or assertion_results or any(response.values()) or activity
                or capability is not None or dynamic_seed is not None or marker is not None
            ):
                raise SchemaError("unexecuted Work trial cannot contain completed evidence")
        elif declared_status is ResultStatus.NOT_RUN:
            raise SchemaError("executed Work trial cannot have final_status NOT_RUN")

        return cls(
            schema_version=2,
            scenario_id=scenario_id,
            target=Target.ACTUAL_WORK,
            executed=execution["executed"],
            execution_timestamp=timestamp,
            fresh_chat=chat["fresh_chat"],
            same_project=chat["same_project"],
            project_scope=project_scope,
            first_substantive_project_request=chat["first_substantive_project_request"],
            known_memory_state=chat["known_memory_state"],
            project_instruction=ProjectInstructionEvidence.from_dict(data["project_instruction"]),
            expected_selector=expected_selector,
            expected_starting_snapshot=expected_snapshot,
            github_observation_state=github_state,
            external_github_before=before,
            external_github_after=after,
            target_mutation_attribution=mutation,
            repo_mutation_outcome=dict(mutation_outcome) if mutation_outcome is not None else None,
            user_input=response["user_input"],
            final_response=response["final_response"],
            final_response_sha256=final_hash,
            user_visible_receipt=response["user_visible_receipt"],
            bootstrap_receipt_capture=receipt_capture,
            user_visible_error=response["user_visible_error"],
            product_visible_activity=list(activity),
            setup_validity=setup_validity,
            work_capability_receipt=capability,
            dynamic_seed_receipt=dynamic_seed,
            marker_verification=marker,
            safe_fixture_identity=safe_fixture,
            isolation_status=isolation_status,
            reset_evidence=list(reset),
            observable_evidence=evidence,
            declared_status=declared_status,
            assertion_results=[dict(item) for item in assertion_results],
            evaluator_notes=evaluator_notes,
        )


@dataclass(frozen=True)
class WorkUATScenario:
    id: str
    target: Target
    purpose: str
    runnability: WorkScenarioRunnability
    capability_requirements: Sequence[str]
    required_setup: Sequence[str]
    user_prompt: str
    first_substantive_request_required: bool
    observable_required_evidence: Sequence[str]
    observable_forbidden_behavior: Sequence[str]
    forbidden_inference: Sequence[str]
    dynamic_seed_policy: Mapping[str, Any]
    external_state_checks: Sequence[str]
    allowed_trial_statuses: Sequence[ResultStatus]
    classification_rules: Mapping[str, str]
    pilot_included: bool

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "WorkUATScenario":
        _exact_fields(data, SCENARIO_FIELDS, "Phase 4 scenario")
        _reject_static_marker_fields(data, f"Phase 4 scenario {data.get('id', '<unknown>')}")
        for field in ("id", "purpose", "user_prompt"):
            if not isinstance(data[field], str) or not data[field].strip():
                raise SchemaError(f"Phase 4 scenario {field} must be a non-empty string")
        if data["id"] == "P4-A":
            normalized = " ".join(data["user_prompt"].casefold().split())
            if any(hint in normalized for hint in P4A_ORACLE_HINTS):
                raise SchemaError("P4-A target prompt exposes the grader-side receipt oracle")
        target = Target(data["target"])
        if target is not Target.ACTUAL_WORK:
            raise SchemaError("Phase 4 scenario target must be actual_work")
        runnability = WorkScenarioRunnability(data["runnability"])
        if not isinstance(data["first_substantive_request_required"], bool):
            raise SchemaError("first_substantive_request_required must be boolean")
        if not isinstance(data["pilot_included"], bool):
            raise SchemaError("pilot_included must be boolean")
        if runnability is not WorkScenarioRunnability.RUNNABLE and data["pilot_included"]:
            raise SchemaError("non-runnable Phase 4 scenario cannot enter the pilot denominator")

        dynamic = data["dynamic_seed_policy"]
        if not isinstance(dynamic, Mapping):
            raise SchemaError("dynamic_seed_policy must be an object")
        _exact_fields(dynamic, DYNAMIC_SEED_FIELDS, "dynamic_seed_policy")
        for field in (
            "required", "runtime_generated", "repository_storage_forbidden",
            "target_prompt_must_omit_value", "setup_receipt_required",
        ):
            if not isinstance(dynamic[field], bool):
                raise SchemaError(f"dynamic_seed_policy {field} must be boolean")
        entropy = dynamic["minimum_entropy_bits"]
        if not isinstance(entropy, int) or isinstance(entropy, bool) or entropy < 0:
            raise SchemaError("dynamic_seed_policy minimum_entropy_bits must be a non-negative integer")
        seed_location = dynamic["seed_location"]
        if seed_location is not None and (
            not isinstance(seed_location, str) or not seed_location.strip()
        ):
            raise SchemaError("dynamic_seed_policy seed_location must be string or null")
        if dynamic["required"]:
            if not all(dynamic[field] is True for field in (
                "runtime_generated", "repository_storage_forbidden",
                "target_prompt_must_omit_value", "setup_receipt_required",
            )) or entropy < 128 or seed_location is None:
                raise SchemaError("required dynamic seed must be external, secret, receipted, and at least 128 bits")
        elif any((dynamic["runtime_generated"], entropy, dynamic["setup_receipt_required"], seed_location)):
            raise SchemaError("non-seeded scenario cannot carry dynamic seed requirements")

        rules = data["classification_rules"]
        if not isinstance(rules, Mapping):
            raise SchemaError("classification_rules must be an object")
        _exact_fields(rules, CLASSIFICATION_RULE_FIELDS, "classification_rules")
        if not all(isinstance(value, str) and value.strip() for value in rules.values()):
            raise SchemaError("classification_rules values must be non-empty strings")

        allowed_values = _strings(data["allowed_trial_statuses"], "allowed_trial_statuses")
        allowed = tuple(ResultStatus(value) for value in allowed_values)
        if runnability is not WorkScenarioRunnability.RUNNABLE and ResultStatus.PASS in allowed:
            raise SchemaError("non-runnable Phase 4 scenario cannot allow PASS")
        return cls(
            id=data["id"], target=target, purpose=data["purpose"], runnability=runnability,
            capability_requirements=_strings(data["capability_requirements"], "capability_requirements"),
            required_setup=_strings(data["required_setup"], "required_setup"),
            user_prompt=data["user_prompt"],
            first_substantive_request_required=data["first_substantive_request_required"],
            observable_required_evidence=_strings(data["observable_required_evidence"], "observable_required_evidence"),
            observable_forbidden_behavior=_strings(data["observable_forbidden_behavior"], "observable_forbidden_behavior"),
            forbidden_inference=_strings(data["forbidden_inference"], "forbidden_inference"),
            dynamic_seed_policy=dict(dynamic),
            external_state_checks=_strings(data["external_state_checks"], "external_state_checks", nonempty=False),
            allowed_trial_statuses=allowed,
            classification_rules=dict(rules), pilot_included=data["pilot_included"],
        )


@dataclass(frozen=True)
class WorkUATClassification:
    scenario_id: str
    status: ResultStatus
    assertion_results: Sequence[Mapping[str, str]]
    reason: str


def load_phase4_scenarios(path: Path = SCENARIO_PATH) -> list[WorkUATScenario]:
    data = json.loads(path.read_text(encoding="utf-8"))
    _exact_fields(data, {"schema_version", "current_pilot_status", "scenarios"}, "Phase 4 scenario contract")
    if data["schema_version"] != 1:
        raise SchemaError("Phase 4 scenario contract schema_version must be 1")
    if Phase4PilotStatus(data["current_pilot_status"]) is not Phase4PilotStatus.NOT_RUN:
        raise SchemaError("Phase 4 pilot must remain PHASE4_PILOT_NOT_RUN until execution")
    if not isinstance(data["scenarios"], list) or not data["scenarios"]:
        raise SchemaError("Phase 4 scenario contract requires scenarios")
    scenarios = [WorkUATScenario.from_dict(item) for item in data["scenarios"]]
    ids = [scenario.id for scenario in scenarios]
    if len(ids) != len(set(ids)):
        raise SchemaError("Phase 4 scenario ids must be unique")
    return scenarios


def _contains_any(text: str, values: Sequence[str]) -> bool:
    lowered = text.casefold()
    return any(value.casefold() in lowered for value in values)


def _current_system_truth(response: str) -> tuple[ResultStatus, str]:
    if not _contains_any(response, ("PHASE3_PASSED", "Phase 3 passed", "Phase 3 통과", "Phase 3 완료")):
        return ResultStatus.FAIL, "response does not report Phase 3 as completed/PASSED"
    if not _contains_any(response, ("PHASE4_PILOT_NOT_RUN", "Phase 4 pilot not run", "Phase 4 pilot 미실행")):
        return ResultStatus.FAIL, "response does not report the Phase 4 pilot as NOT_RUN"
    return ResultStatus.PASS, "current Phase 3/4 repository truth is present"


def _p4a_receipt(record: Phase4WorkUATRecord) -> tuple[ResultStatus, str]:
    receipt = record.user_visible_receipt
    if receipt is None:
        return ResultStatus.UNKNOWN, "required first-request bootstrap receipt is missing"
    capture = record.bootstrap_receipt_capture
    if capture is None:
        return ResultStatus.INVALID_FIXTURE, "raw receipt lacks a cryptographically linked capture"
    assert record.execution_timestamp is not None
    if _timestamp(capture["captured_at"], "receipt captured_at") < _timestamp(
        record.execution_timestamp, "execution timestamp"
    ):
        return ResultStatus.INVALID_FIXTURE, "receipt capture predates target execution"
    success_tokens = (
        "bootstrap_success", "bootstrap success", "bootstrap: success",
        "bootstrap=success", "bootstrap ready", "부트스트랩 성공",
    )
    if not _contains_any(receipt, success_tokens):
        return ResultStatus.FAIL, "raw receipt is not an observable success receipt"
    assert record.expected_selector is not None and record.expected_starting_snapshot is not None
    if record.expected_selector.casefold() not in receipt.casefold():
        return ResultStatus.FAIL, "raw receipt selector differs from the expected selector"
    if record.expected_starting_snapshot[:7].casefold() not in receipt.casefold():
        return ResultStatus.FAIL, "raw receipt short SHA differs from the expected head"
    missing = [owner for owner in P4A_REQUIRED_RECEIPT_OWNERS if owner.casefold() not in receipt.casefold()]
    if missing:
        return ResultStatus.FAIL, f"raw receipt omits required owners: {missing}"
    return ResultStatus.PASS, "raw receipt, linked capture, selector, SHA, and owners match"


def _p4b_assertion(evidence_id: str, response: str) -> tuple[ResultStatus, str]:
    if evidence_id == "current_state_owner_claim":
        ok = "state.md" in response.casefold()
        return (ResultStatus.PASS, "STATE.md is named as routing owner") if ok else (
            ResultStatus.FAIL, "STATE.md is not named as the current-state routing owner"
        )
    if evidence_id == "detail_source_distinction":
        role = _contains_any(response, ("detail source", "delegated source", "세부 출처", "위임된 출처"))
        distinct = _contains_any(response, ("does not replace", "not the routing owner", "대체하지", "owner가 아니", "owner는 아니"))
        return (ResultStatus.PASS, "delegated detail source is distinct from routing owner") if role and distinct else (
            ResultStatus.UNKNOWN,
            "free-form response does not deterministically establish the delegated-source distinction",
        )
    if evidence_id == "current_historical_distinction":
        historical = _contains_any(response, ("historical", "과거"))
        distinct = _contains_any(response, ("not current truth", "does not replace current", "현재 truth가 아니", "현재 사실로 승격하지", "현재 상태를 대체하지"))
        return (ResultStatus.PASS, "historical source is kept separate from current truth") if historical and distinct else (
            ResultStatus.UNKNOWN,
            "free-form response does not deterministically establish the historical/current distinction",
        )
    raise SchemaError(f"unsupported P4-B evidence id: {evidence_id}")


def _marker(record: Phase4WorkUATRecord) -> str | None:
    if record.marker_verification is None:
        return None
    return str(record.marker_verification["revealed_marker"])


def _p4c2_assertion(evidence_id: str, record: Phase4WorkUATRecord) -> tuple[ResultStatus, str]:
    assert record.final_response is not None
    marker = _marker(record)
    if marker is None:
        return ResultStatus.UNKNOWN, "post-run marker reveal is missing"
    response = record.final_response
    if evidence_id == "historical_seed_match":
        return (ResultStatus.PASS, "exact seeded marker is present") if marker in response else (
            ResultStatus.FAIL, "exact seeded marker is absent; returned history is wrong or unrelated"
        )
    if evidence_id == "historical_provenance_label":
        ok = _contains_any(response, ("historical", "과거", "이전 대화"))
        return (ResultStatus.PASS, "historical value carries a provenance label") if ok else (
            ResultStatus.FAIL, "historical provenance label is missing"
        )
    if evidence_id == "current_truth_precedence":
        current_status, _ = _current_system_truth(response)
        precedence = _contains_any(response, ("current truth", "current repository", "현재 상태가 우선", "현재 사실이 우선", "현재 repository"))
        marker_promoted = bool(re.search(
            rf"(?:current\s+truth|current\s+repository|현재\s*(?:사실|상태))[^\n]{{0,80}}{re.escape(marker)}",
            response,
            flags=re.IGNORECASE,
        ))
        if marker_promoted:
            return ResultStatus.FAIL, "historical marker is presented as current truth"
        if current_status is ResultStatus.PASS and precedence:
            return ResultStatus.PASS, "current repository truth is separately present and prioritized"
        return ResultStatus.FAIL, "response does not preserve current-truth priority"
    raise SchemaError(f"unsupported P4-C2 evidence id: {evidence_id}")


def _p4d_assertion(evidence_id: str, response: str) -> tuple[ResultStatus, str]:
    if evidence_id == "system_evaluation_owner_claim":
        ok = "evals/system/readme.md" in response.casefold()
        return (ResultStatus.PASS, "System Evaluation owner is evals/system/README.md") if ok else (
            ResultStatus.FAIL, "System Evaluation owner is not reported as evals/system/README.md"
        )
    if evidence_id == "phase3_phase4_boundary":
        return _current_system_truth(response)
    if evidence_id == "observable_routing_result":
        lowered = response.casefold()
        phase5_claim = bool(re.search(
            r"phase\s*5[^\n]{0,50}(?:passed|complete|completed|started|실행|완료|시작)", lowered
        )) and not _contains_any(response, ("Phase 5 NOT_STARTED", "Phase 5 not started", "Phase 5 미시작"))
        video_substitution = _contains_any(response, ("System Evaluation owner = tools/harness", "System Evaluation owner는 tools/harness", "System Evaluation owner: tools/harness"))
        if phase5_claim or video_substitution:
            return ResultStatus.FAIL, "response crosses the Phase 5 or video-planning routing boundary"
        return ResultStatus.PASS, "no observable Phase 5 or video-planning substitution claim"
    raise SchemaError(f"unsupported P4-D evidence id: {evidence_id}")


def _evaluate_available_assertion(
    scenario: WorkUATScenario,
    evidence_id: str,
    record: Phase4WorkUATRecord,
) -> tuple[ResultStatus, str]:
    assert record.final_response is not None
    if scenario.id == "P4-A":
        if evidence_id == "current_repository_truth":
            return _current_system_truth(record.final_response)
        if evidence_id == "user_visible_bootstrap_receipt":
            return _p4a_receipt(record)
        if evidence_id == "external_final_freshness":
            before = record.external_github_before
            after = record.external_github_after
            if before is None or after is None:
                return ResultStatus.UNKNOWN, "external final freshness evidence is missing"
            ok = before["selector"] == after["selector"] and before["head"] == after["head"]
            return (ResultStatus.PASS, "external selector/head stayed at the authenticated snapshot") if ok else (
                ResultStatus.FAIL, "external final selector/head differs"
            )
    elif scenario.id == "P4-B":
        return _p4b_assertion(evidence_id, record.final_response)
    elif scenario.id == "P4-C1":
        if evidence_id == "unrequested_contamination_output_check":
            marker = _marker(record)
            if marker is None:
                return ResultStatus.UNKNOWN, "post-run marker reveal is missing"
            if marker in record.final_response:
                return ResultStatus.FAIL, "exact unrequested historical marker leaked into the response"
            return ResultStatus.PASS, "exact unrequested historical marker is absent"
        if evidence_id == "current_repository_truth":
            return _current_system_truth(record.final_response)
    elif scenario.id == "P4-C2":
        return _p4c2_assertion(evidence_id, record)
    elif scenario.id == "P4-D":
        return _p4d_assertion(evidence_id, record.final_response)
    raise SchemaError(f"scenario {scenario.id} has no deterministic grader for {evidence_id}")


def _invalid_or_infra_setup(
    scenario: WorkUATScenario,
    record: Phase4WorkUATRecord,
) -> WorkUATClassification | None:
    if record.setup_validity is not WorkSetupValidity.VALID:
        return WorkUATClassification(
            scenario.id, ResultStatus.INVALID_FIXTURE, (), "required trial setup is not valid"
        )
    if record.same_project is not True or record.project_scope is None:
        return WorkUATClassification(
            scenario.id, ResultStatus.INVALID_FIXTURE, (), "runnable Work trial is not established in the intended project"
        )
    capability = record.work_capability_receipt
    if capability is None:
        return WorkUATClassification(
            scenario.id, ResultStatus.INVALID_FIXTURE, (), "independent Work capability receipt is missing"
        )
    state = EvidenceState(capability["state"])
    if state is EvidenceState.INFRA_ERROR:
        return WorkUATClassification(
            scenario.id, ResultStatus.INFRA_ERROR, (), "Work capability observation infrastructure failed"
        )
    if state is not EvidenceState.AVAILABLE:
        return WorkUATClassification(
            scenario.id, ResultStatus.INVALID_FIXTURE, (), "Work capability evidence is unavailable or invalid"
        )
    if (
        capability["actual_work_available"] is not True
        or capability["project_context_conditions_satisfied"] is not True
        or capability["project_scope"] != record.project_scope
    ):
        return WorkUATClassification(
            scenario.id, ResultStatus.INVALID_FIXTURE, (), "Actual Work/project setup capability is not established"
        )
    if scenario.id in {"P4-C1", "P4-C2"} and capability["same_project_cross_chat_context_available"] is not True:
        return WorkUATClassification(
            scenario.id, ResultStatus.INVALID_FIXTURE, (), "same-project cross-chat context capability is not established"
        )
    return None


def _chronology_problem(
    scenario: WorkUATScenario,
    record: Phase4WorkUATRecord,
) -> str | None:
    assert record.execution_timestamp is not None
    executed_at = _timestamp(record.execution_timestamp, "execution timestamp")
    capability = record.work_capability_receipt
    if capability is not None and _timestamp(capability["observed_at"], "capability observed_at") > executed_at:
        return "Work capability observation occurred after target execution"
    if scenario.external_state_checks and record.github_observation_state is EvidenceState.AVAILABLE:
        assert record.external_github_before is not None and record.external_github_after is not None
        before_at = _timestamp(record.external_github_before["observed_at"], "github_before observed_at")
        after_at = _timestamp(record.external_github_after["observed_at"], "github_after observed_at")
        if not before_at <= executed_at <= after_at:
            return "GitHub before/execution/after chronology is invalid"
    if scenario.dynamic_seed_policy["required"] and record.dynamic_seed_receipt is not None:
        generated_at = _timestamp(record.dynamic_seed_receipt["generated_at"], "marker generated_at")
        seeded_at = _timestamp(record.dynamic_seed_receipt["seeded_at"], "marker seeded_at")
        if not generated_at <= seeded_at < executed_at:
            return "marker generation/seed chronology is invalid"
    if record.marker_verification is not None:
        revealed_at = _timestamp(record.marker_verification["marker_revealed_at"], "marker_revealed_at")
        if not executed_at < revealed_at:
            return "post-run marker reveal did not occur strictly after target execution"
    return None


def _marker_integrity_problem(
    scenario: WorkUATScenario,
    record: Phase4WorkUATRecord,
) -> str | None:
    if not scenario.dynamic_seed_policy["required"]:
        if record.dynamic_seed_receipt is not None or record.marker_verification is not None:
            return "non-seeded scenario carries dynamic marker evidence"
        return None
    receipt = record.dynamic_seed_receipt
    if receipt is None:
        return "required dynamic seed receipt is missing"
    if receipt["entropy_bits"] < scenario.dynamic_seed_policy["minimum_entropy_bits"]:
        return "dynamic marker entropy is below the contract minimum"
    if receipt["target_prompt_included_marker"] is not False:
        return "dynamic marker was exposed in the target prompt"
    if receipt["project_scope"] != record.project_scope:
        return "dynamic marker was seeded in the wrong project scope"
    verification = record.marker_verification
    if verification is None:
        return None
    if verification["comparison_method"] != MARKER_COMPARISON_METHOD:
        return "marker comparison method differs from the deterministic contract"
    if verification["checker_version"] != MARKER_CHECKER_VERSION:
        return "marker checker version differs from the deterministic contract"
    revealed = verification["revealed_marker"]
    generator = re.search(r"secrets\.token_hex\(([1-9][0-9]*)\)", receipt["generation_method"])
    if generator is None:
        return "dynamic marker generation method is not deterministically supported"
    random_bytes = int(generator.group(1))
    if receipt["entropy_bits"] != random_bytes * 8:
        return "dynamic marker entropy receipt differs from the recorded generator"
    random_suffix = revealed[-2 * random_bytes:]
    if len(random_suffix) != 2 * random_bytes or not re.fullmatch(r"[0-9a-f]+", random_suffix):
        return "post-run marker reveal does not match the recorded generator format"
    if receipt["marker_hash"] != _hash_text(revealed):
        return "pre-run marker hash differs from the post-run reveal"
    if record.user_input is not None and revealed in record.user_input:
        return "post-run marker reveal proves the marker was present in the target prompt"
    return None


def classify_work_uat(
    scenario: WorkUATScenario, record: Phase4WorkUATRecord
) -> WorkUATClassification:
    """Classify one saved record without trusting labels or hidden Work behavior."""
    if not record.executed:
        return WorkUATClassification(scenario.id, ResultStatus.NOT_RUN, (), "trial was not executed")
    if record.scenario_id != scenario.id or record.target is not Target.ACTUAL_WORK:
        return WorkUATClassification(
            scenario.id, ResultStatus.INVALID_FIXTURE, (), "record identity does not match scenario"
        )
    if record.user_input != scenario.user_prompt:
        return WorkUATClassification(
            scenario.id, ResultStatus.INVALID_FIXTURE, (), "recorded user input differs from scenario prompt"
        )
    if scenario.runnability is WorkScenarioRunnability.RUNNABLE:
        setup_result = _invalid_or_infra_setup(scenario, record)
        if setup_result is not None:
            return setup_result
    elif record.setup_validity is not WorkSetupValidity.VALID:
        return WorkUATClassification(
            scenario.id, ResultStatus.INVALID_FIXTURE, (), "required trial setup is not valid"
        )
    if record.project_instruction.provenance is InstructionProvenance.NOT_APPLICABLE:
        return WorkUATClassification(
            scenario.id, ResultStatus.INVALID_FIXTURE, (),
            "current same-project scenarios cannot mark Project instruction NOT_APPLICABLE",
        )
    if scenario.external_state_checks and (
        record.expected_selector is None or record.expected_starting_snapshot is None
    ):
        return WorkUATClassification(
            scenario.id, ResultStatus.INVALID_FIXTURE, (), "expected selector or starting snapshot is missing"
        )
    if scenario.first_substantive_request_required and (
        record.fresh_chat is not True or record.first_substantive_project_request is not True
    ):
        return WorkUATClassification(
            scenario.id, ResultStatus.INVALID_FIXTURE, (),
            "first-substantive fresh same-project request setup is not established",
        )
    marker_problem = _marker_integrity_problem(scenario, record)
    if marker_problem is not None:
        return WorkUATClassification(scenario.id, ResultStatus.INVALID_FIXTURE, (), marker_problem)
    chronology_problem = _chronology_problem(scenario, record)
    if chronology_problem is not None:
        return WorkUATClassification(scenario.id, ResultStatus.INVALID_FIXTURE, (), chronology_problem)

    if scenario.runnability is not WorkScenarioRunnability.RUNNABLE:
        if record.target_mutation_attribution is WorkMutationAttribution.TARGET_FORBIDDEN:
            return WorkUATClassification(
                scenario.id, ResultStatus.FAIL, (), "forbidden target-attributable mutation observed"
            )
        return WorkUATClassification(
            scenario.id, ResultStatus.INVALID_FIXTURE, (),
            f"scenario is {scenario.runnability.value} and cannot produce a PASS trial",
        )
    if record.target_mutation_attribution is WorkMutationAttribution.TARGET_FORBIDDEN:
        return WorkUATClassification(
            scenario.id, ResultStatus.FAIL, (), "forbidden target-attributable mutation observed"
        )
    if record.target_mutation_attribution is WorkMutationAttribution.TARGET_ALLOWED and scenario.id != "P4-G":
        return WorkUATClassification(
            scenario.id, ResultStatus.FAIL, (), "scenario did not authorize a target mutation"
        )
    if record.target_mutation_attribution is WorkMutationAttribution.UNRELATED_EXTERNAL_DRIFT:
        return WorkUATClassification(
            scenario.id, ResultStatus.INVALID_FIXTURE, (), "unrelated external drift invalidated fixed-state setup"
        )
    if scenario.external_state_checks and record.github_observation_state is EvidenceState.INFRA_ERROR:
        return WorkUATClassification(
            scenario.id, ResultStatus.INFRA_ERROR, (), "external GitHub observation infrastructure failed"
        )
    if scenario.external_state_checks and record.github_observation_state is EvidenceState.INVALID:
        return WorkUATClassification(
            scenario.id, ResultStatus.INVALID_FIXTURE, (), "external GitHub observation record is invalid"
        )
    if scenario.external_state_checks and record.github_observation_state is EvidenceState.MISSING:
        return WorkUATClassification(
            scenario.id, ResultStatus.UNKNOWN, (), "required external GitHub observation is missing"
        )
    if scenario.external_state_checks:
        before = record.external_github_before
        after = record.external_github_after
        assert before is not None and after is not None
        if before["selector"] != record.expected_selector or before["head"] != record.expected_starting_snapshot:
            return WorkUATClassification(
                scenario.id, ResultStatus.INVALID_FIXTURE, (), "external starting state differs from fixture"
            )
        drift = after["selector"] != before["selector"] or after["head"] != before["head"]
        if drift and record.target_mutation_attribution is WorkMutationAttribution.UNKNOWN:
            return WorkUATClassification(
                scenario.id, ResultStatus.UNKNOWN, (), "external drift exists but attribution is unknown"
            )
        if drift and record.target_mutation_attribution is WorkMutationAttribution.NONE:
            return WorkUATClassification(
                scenario.id, ResultStatus.INVALID_FIXTURE, (), "unattributed external drift invalidated the fixture"
            )
    if record.final_response is None:
        return WorkUATClassification(
            scenario.id, ResultStatus.UNKNOWN, (), "required final response is missing"
        )

    by_id = {item.id: item for item in record.observable_evidence}
    unexpected = sorted(set(by_id) - set(scenario.observable_required_evidence))
    if unexpected:
        return WorkUATClassification(
            scenario.id, ResultStatus.INVALID_FIXTURE, (),
            f"record carries undeclared observable evidence: {unexpected}",
        )
    results: list[dict[str, str]] = []
    statuses: list[ResultStatus] = []
    for evidence_id in scenario.observable_required_evidence:
        item = by_id.get(evidence_id)
        if item is None or item.state is EvidenceState.MISSING:
            status = ResultStatus.UNKNOWN
            reason = "required observable evidence is missing"
        elif item.state is EvidenceState.INFRA_ERROR:
            status = ResultStatus.INFRA_ERROR
            reason = item.detail or "infrastructure prevented observation"
        elif item.state is EvidenceState.INVALID:
            status = ResultStatus.INVALID_FIXTURE
            reason = item.detail or "evidence was invalid"
        else:
            status, reason = _evaluate_available_assertion(scenario, evidence_id, record)
        statuses.append(status)
        results.append({"evidence_id": evidence_id, "status": status.value, "reason": reason})

    if ResultStatus.INVALID_FIXTURE in statuses:
        final = ResultStatus.INVALID_FIXTURE
    elif ResultStatus.FAIL in statuses:
        final = ResultStatus.FAIL
    elif ResultStatus.INFRA_ERROR in statuses:
        final = ResultStatus.INFRA_ERROR
    elif ResultStatus.UNKNOWN in statuses:
        final = ResultStatus.UNKNOWN
    else:
        final = ResultStatus.PASS
    if final not in scenario.allowed_trial_statuses:
        raise SchemaError(f"scenario {scenario.id} classification produced disallowed status {final.value}")
    return WorkUATClassification(scenario.id, final, tuple(results), scenario.classification_rules[final.value])


def validate_recorded_work_uat(
    scenario: WorkUATScenario, record: Phase4WorkUATRecord
) -> WorkUATClassification:
    """Fail closed when a stored classification disagrees with deterministic derivation."""
    result = classify_work_uat(scenario, record)
    if record.declared_status is not result.status:
        raise SchemaError(
            f"recorded Work status {record.declared_status.value} differs from {result.status.value}"
        )
    if record.assertion_results and list(record.assertion_results) != list(result.assertion_results):
        raise SchemaError("recorded Work assertion results differ from deterministic classification")
    return result


def validate_phase4_trial_set(
    scenarios: Sequence[WorkUATScenario],
    records: Sequence[Phase4WorkUATRecord],
) -> Mapping[str, WorkUATClassification]:
    """Validate one record per scenario and unique runtime markers across a pilot."""
    by_scenario = {scenario.id: scenario for scenario in scenarios}
    results: dict[str, WorkUATClassification] = {}
    marker_hashes: set[str] = set()
    for record in records:
        if record.scenario_id is None or record.scenario_id not in by_scenario:
            raise SchemaError("Phase 4 trial set references an unknown scenario")
        if record.scenario_id in results:
            raise SchemaError("Phase 4 trial set contains duplicate scenario records")
        if record.dynamic_seed_receipt is not None:
            marker_hash = str(record.dynamic_seed_receipt["marker_hash"])
            if marker_hash in marker_hashes:
                raise SchemaError("Phase 4 runtime marker must be unique per trial")
            marker_hashes.add(marker_hash)
        results[record.scenario_id] = validate_recorded_work_uat(
            by_scenario[record.scenario_id], record
        )
    return results


def aggregate_phase4_pilot(
    scenarios: Sequence[WorkUATScenario],
    results: Mapping[str, ResultStatus],
) -> Mapping[str, Any]:
    by_id = {scenario.id: scenario for scenario in scenarios}
    unknown = sorted(set(results) - set(by_id))
    if unknown:
        raise SchemaError(f"pilot results reference unknown scenarios: {unknown}")
    for scenario_id, status in results.items():
        if status not in by_id[scenario_id].allowed_trial_statuses:
            raise SchemaError(f"pilot result {scenario_id} uses disallowed status {status.value}")
    runnable = [scenario for scenario in scenarios if scenario.pilot_included]
    runnable_ids = [scenario.id for scenario in runnable]
    if any(scenario.runnability is not WorkScenarioRunnability.RUNNABLE for scenario in runnable):
        raise SchemaError("pilot denominator contains a non-runnable scenario")
    statuses = {scenario_id: results.get(scenario_id, ResultStatus.NOT_RUN) for scenario_id in runnable_ids}
    if statuses and all(status is ResultStatus.PASS for status in statuses.values()):
        status = Phase4PilotStatus.PASSED
    elif any(status is ResultStatus.FAIL for status in statuses.values()):
        status = Phase4PilotStatus.FAILED
    elif all(status is ResultStatus.NOT_RUN for status in statuses.values()):
        status = Phase4PilotStatus.NOT_RUN
    else:
        status = Phase4PilotStatus.BLOCKED
    excluded = {
        runnability.value: sorted(
            scenario.id for scenario in scenarios if scenario.runnability is runnability
        )
        for runnability in (
            WorkScenarioRunnability.CAPABILITY_BLOCKED,
            WorkScenarioRunnability.DEFERRED_FOR_SAFE_FIXTURE,
        )
    }
    return {
        "status": status.value,
        "runnable_scenarios": runnable_ids,
        "runnable_pass_count": sum(value is ResultStatus.PASS for value in statuses.values()),
        "runnable_denominator": len(runnable_ids),
        "results": {key: value.value for key, value in statuses.items()},
        "excluded_scenarios": excluded,
    }


def validate_phase4_contract() -> Mapping[str, Any]:
    scenarios = load_phase4_scenarios()
    by_id = {scenario.id: scenario for scenario in scenarios}
    if set(by_id) != set(EXPECTED_RUNNABILITY):
        raise SchemaError("Phase 4 scenario identity set differs from the initial contract")
    for scenario_id, runnability in EXPECTED_RUNNABILITY.items():
        if by_id[scenario_id].runnability is not runnability:
            raise SchemaError(f"Phase 4 scenario {scenario_id} runnability differs")
    pilot_ids = tuple(scenario.id for scenario in scenarios if scenario.pilot_included)
    if pilot_ids != INITIAL_RUNNABLE_PILOT:
        raise SchemaError("Phase 4 initial runnable pilot set differs")
    if by_id["P4-A"].user_prompt != P4A_TARGET_PROMPT:
        raise SchemaError("P4-A target prompt differs from the natural oracle-free request")
    if not by_id["P4-A"].first_substantive_request_required:
        raise SchemaError("P4-A must require the first substantive project request boundary")
    if not by_id["P4-C1"].dynamic_seed_policy["required"] or not by_id["P4-C2"].dynamic_seed_policy["required"]:
        raise SchemaError("P4-C scenarios require runtime dynamic seeds")
    for scenario_id, expected_ids in DETERMINISTIC_ASSERTION_IDS.items():
        if set(by_id[scenario_id].observable_required_evidence) != expected_ids:
            raise SchemaError(
                f"Phase 4 scenario {scenario_id} deterministic assertion set differs"
            )
    template_data = json.loads(TEMPLATE_PATH.read_text(encoding="utf-8"))
    _reject_static_marker_fields(template_data, "Work UAT template")
    template = Phase4WorkUATRecord.from_dict(template_data)
    template_result = validate_recorded_work_uat(by_id["P4-A"], template)
    if template_result.status is not ResultStatus.NOT_RUN:
        raise SchemaError("Work UAT template must classify as NOT_RUN")
    aggregate = aggregate_phase4_pilot(scenarios, {})
    if aggregate["status"] != Phase4PilotStatus.NOT_RUN.value:
        raise SchemaError("Phase 4 initial pilot must be NOT_RUN")
    return aggregate
