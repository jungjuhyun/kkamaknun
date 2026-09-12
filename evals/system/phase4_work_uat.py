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
P4B_TARGET_PROMPT = (
    "까막눈 저장소의 현재 상태와 다음 행동의 routing owner가 무엇인지, "
    "그 owner가 위임한 detail source와 과거 자료를 current truth와 어떻게 구분해야 하는지 설명해줘."
)
P4A_REQUIRED_RECEIPT_OWNERS = ("STATE.md", "AGENTS.md", "evals/system/README.md")
P4A_MINIMUM_SHA_PREFIX_LENGTH = 7
P4A_RECEIPT_RE = re.compile(
    rf"^bootstrap\s*:\s*OK\s+—\s+(?P<ref>[^@\s]+)@(?P<sha>[0-9a-f]{{{P4A_MINIMUM_SHA_PREFIX_LENGTH},40}})\s+/\s+(?P<owners>[^\r\n]+)$",
    flags=re.IGNORECASE,
)
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
    expected_receipt_ref: str | None
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
            (repository, "Work repository", {"expected_selector", "expected_receipt_ref", "expected_starting_snapshot"}),
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
        expected_receipt_ref = _optional_text(
            repository["expected_receipt_ref"], "expected_receipt_ref"
        )
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
            expected_receipt_ref=expected_receipt_ref,
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


def _matches(text: str, patterns: Sequence[str]) -> bool:
    return any(re.search(pattern, text, flags=re.IGNORECASE | re.DOTALL) for pattern in patterns)


def _bounded_relation(
    response: str,
    *,
    positive: Sequence[str],
    contradiction: Sequence[str],
    positive_reason: str,
    contradiction_reason: str,
    unknown_reason: str,
) -> tuple[ResultStatus, str]:
    """Return a bounded relation result; a contradiction always outranks boilerplate."""
    if _matches(response, contradiction):
        return ResultStatus.FAIL, contradiction_reason
    if _matches(response, positive):
        return ResultStatus.PASS, positive_reason
    return ResultStatus.UNKNOWN, unknown_reason


def _phase3_current_relation(response: str) -> tuple[ResultStatus, str]:
    return _bounded_relation(
        response,
        positive=(
            r"\bphase\s*3(?:\s+(?:current\s+)?status)?\s*(?:is|=|:)\s*(?:phase3_passed|passed|completed)\b",
            r"\bphase\s*3\s+(?:has\s+)?(?:passed|completed)\b",
            r"phase\s*3(?:의)?\s*(?:현재\s*)?(?:상태)?\s*(?:는|은|=|:)\s*(?:phase3_passed|통과|완료)",
        ),
        contradiction=(
            r"\bphase3_passed\b.{0,100}\b(?:outdated|obsolete|no\s+longer\s+true|incorrect|not\s+(?:the\s+)?current)\b",
            r"\bphase3_passed\b.{0,120}\b(?:current|actual)\s+status\b.{0,40}\b(?:fail|failed|failure)\b",
            r"\bphase\s*3\b.{0,80}\b(?:actually|currently|current\s+status|status\s+is)?\s*(?:failed|fail|not\s+passed|incomplete|not\s+complete)\b",
            r"phase\s*3.{0,80}(?:실패|미완료|통과하지\s*않|완료되지\s*않)",
        ),
        positive_reason="Phase 3 is explicitly reported as current PASSED/completed state",
        contradiction_reason="response explicitly contradicts the current Phase 3 PASS state",
        unknown_reason="response does not deterministically state the current Phase 3 status",
    )


def _phase4_current_relation(response: str) -> tuple[ResultStatus, str]:
    return _bounded_relation(
        response,
        positive=(
            r"\bphase\s*4\s+pilot(?:\s+(?:current\s+)?status)?\s*(?:is|=|:)\s*(?:phase4_pilot_not_run|not[_\s-]*run)\b",
            r"\bphase\s*4\s+pilot\s+(?:has\s+)?not\s+(?:been\s+)?run\b",
            r"\bphase\s*4\s+pilot\s+remains\s+(?:phase4_pilot_not_run|not[_\s-]*run)\b",
            r"phase\s*4\s*pilot(?:의)?\s*(?:현재\s*)?(?:상태)?\s*(?:는|은|=|:)\s*(?:phase4_pilot_not_run|미실행|실행되지\s*않)",
        ),
        contradiction=(
            r"\bphase4_pilot_not_run\b.{0,100}\b(?:outdated|obsolete|no\s+longer\s+true|incorrect)\b",
            r"\bphase\s*4\s+pilot\b.{0,80}\b(?:already\s+)?(?:passed|completed|started|has\s+run|was\s+run)\b",
            r"\b(?:the\s+)?pilot\b.{0,50}\balready\s+(?:passed|ran|completed|started)\b",
            r"phase\s*4\s*pilot.{0,80}(?:이미\s*)?(?:통과|완료|시작|실행됨|실행했다)",
        ),
        positive_reason="Phase 4 pilot is explicitly reported as current NOT_RUN state",
        contradiction_reason="response explicitly contradicts the current Phase 4 NOT_RUN state",
        unknown_reason="response does not deterministically state the current Phase 4 pilot status",
    )


def _current_system_truth(response: str) -> tuple[ResultStatus, str]:
    phase3, phase3_reason = _phase3_current_relation(response)
    phase4, phase4_reason = _phase4_current_relation(response)
    if ResultStatus.FAIL in (phase3, phase4):
        return ResultStatus.FAIL, "; ".join(
            reason for status, reason in ((phase3, phase3_reason), (phase4, phase4_reason))
            if status is ResultStatus.FAIL
        )
    if ResultStatus.UNKNOWN in (phase3, phase4):
        return ResultStatus.UNKNOWN, "; ".join(
            reason for status, reason in ((phase3, phase3_reason), (phase4, phase4_reason))
            if status is ResultStatus.UNKNOWN
        )
    return ResultStatus.PASS, "current Phase 3 PASSED and Phase 4 pilot NOT_RUN relations are explicit"


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
    parsed = P4A_RECEIPT_RE.fullmatch(receipt.strip())
    if parsed is None:
        return ResultStatus.FAIL, "raw receipt does not match the actual bootstrap: OK ref@sha / owner + owner grammar"
    assert record.expected_receipt_ref is not None and record.expected_starting_snapshot is not None
    if parsed.group("ref") != record.expected_receipt_ref:
        return ResultStatus.FAIL, "raw receipt ref differs from the expected work ref"
    receipt_sha = parsed.group("sha").casefold()
    if not record.expected_starting_snapshot.casefold().startswith(receipt_sha):
        return ResultStatus.FAIL, "raw receipt SHA abbreviation is not a prefix of the expected head"
    owner_values = [value.strip() for value in re.split(r"\s*\+\s*", parsed.group("owners"))]
    if not owner_values or any(not value for value in owner_values):
        return ResultStatus.FAIL, "raw receipt owner list has a malformed + separator"
    if any(not re.fullmatch(r"[A-Za-z0-9_./-]+\.md", value) for value in owner_values):
        return ResultStatus.FAIL, "raw receipt owner list is not a set of actual owner paths"
    owners = {value.casefold() for value in owner_values}
    missing = [owner for owner in P4A_REQUIRED_RECEIPT_OWNERS if owner.casefold() not in owners]
    if missing:
        return ResultStatus.FAIL, f"raw receipt omits required owners: {missing}"
    return ResultStatus.PASS, "actual raw receipt grammar, linked capture, ref, SHA, and owners match"


def _owner_relation(
    response: str, *, expected_owner: str, relation: str
) -> tuple[ResultStatus, str]:
    expected = expected_owner.casefold()
    path = r"[a-z0-9_./-]+\.md"
    clause_start = r"(?:^|[.!?;]\s+|\n\s*)"
    if relation == "routing":
        claim_patterns = (
            rf"{clause_start}(?:actually,\s*)?routing\s+owner\s*(?:is|=|:)\s*(?P<path>{path})",
            rf"current[-\s]+state(?:\s+and\s+next[-\s]+action)?\s+(?:routing\s+)?owner\s*(?:is|=|:)\s*(?P<path>{path})",
            rf"{clause_start}(?:actually,\s*)?routing\s+owner(?:는|은)\s*(?P<path>{path})",
            rf"현재\s*상태와\s*다음\s*행동의\s*routing\s+owner(?:는|은)\s*(?P<path>{path})",
            rf"(?P<path>{path})\s+(?:is|=)\s+(?:the\s+)?current[-\s]+state(?:\s+and\s+next[-\s]+action)?\s+routing\s+owner",
            rf"(?P<path>{path})(?:가|이|는|은)\s*현재\s*상태와\s*다음\s*행동의\s*routing\s+owner",
        )
        negative = (
            rf"{re.escape(expected)}\s+(?:is|=)?\s*not\s+(?:the\s+)?current[-\s]+state(?:\s+and\s+next[-\s]+action)?\s+routing\s+owner",
            rf"(?:{clause_start}(?:actually,\s*)?routing\s+owner|current[-\s]+state(?:\s+and\s+next[-\s]+action)?\s+(?:routing\s+)?owner)\s*(?:is|=|:)\s*not\s+{re.escape(expected)}\b",
            rf"{re.escape(expected)}(?:가|이|는|은)\s*현재\s*상태와\s*다음\s*행동의\s*routing\s+owner(?:가|이)?\s*아니",
            rf"현재\s*상태와\s*다음\s*행동의\s*routing\s+owner(?:는|은)\s*{re.escape(expected)}(?:가|이)?\s*아니",
        )
        label = "current-state routing owner"
    elif relation == "system_evaluation":
        claim_patterns = (
            rf"system\s+evaluation(?:'s)?\s+(?:contract\s+)?owner\s*(?:is|=|:)\s*(?P<path>{path})",
            rf"system\s+evaluation\s+is\s+owned\s+by\s+(?P<path>{path})",
            rf"(?P<path>{path})\s+owns\s+system\s+evaluation",
            rf"system\s+evaluation(?:의)?\s*(?:contract\s+)?owner(?:는|은|=|:)\s*(?P<path>{path})",
        )
        negative = (
            rf"{re.escape(expected)}\s+(?:is|=)?\s*not\s+(?:the\s+)?system\s+evaluation(?:\s+contract)?\s+owner",
            rf"system\s+evaluation(?:'s)?\s+(?:contract\s+)?owner\s*(?:is|=|:)\s*not\s+{re.escape(expected)}\b",
            rf"system\s+evaluation\s+is\s+not\s+owned\s+by\s+{re.escape(expected)}\b",
            rf"{re.escape(expected)}(?:가|이|는|은).{{0,30}}system\s+evaluation.{{0,20}}owner(?:가|이)?\s*아니",
        )
        label = "System Evaluation contract owner"
    else:
        raise SchemaError(f"unsupported owner relation: {relation}")
    if _matches(response, negative):
        return ResultStatus.FAIL, f"response explicitly denies {expected_owner} as {label}"
    claims: list[str] = []
    for pattern in claim_patterns:
        claims.extend(match.group("path").casefold() for match in re.finditer(pattern, response, re.IGNORECASE))
    if any(value != expected for value in claims):
        return ResultStatus.FAIL, f"response assigns {label} to a different source"
    if expected in claims:
        return ResultStatus.PASS, f"response explicitly assigns {label} to {expected_owner}"
    return ResultStatus.UNKNOWN, f"response does not deterministically establish {label}"


def _p4b_assertion(evidence_id: str, response: str) -> tuple[ResultStatus, str]:
    if evidence_id == "current_state_owner_claim":
        return _owner_relation(response, expected_owner="STATE.md", relation="routing")
    if evidence_id == "detail_source_distinction":
        return _bounded_relation(
            response,
            positive=(
                r"(?:delegated\s+)?detail\s+source.{0,80}(?:does\s+not\s+replace|is\s+not)\s+(?:the\s+)?(?:routing\s+)?owner",
                r"(?:위임된\s*)?(?:detail\s+source|세부\s*출처).{0,80}(?:routing\s+owner|owner).{0,20}(?:대체하지\s*않|아니)",
            ),
            contradiction=(
                r"(?:delegated\s+)?detail\s+source.{0,80}(?:replaces|becomes)\s+(?:the\s+)?(?:routing\s+)?owner",
                r"(?:delegated\s+)?detail\s+source\s+is\s+(?!not\b)(?:the\s+)?(?:routing\s+)?owner",
                r"(?:위임된\s*)?(?:detail\s+source|세부\s*출처).{0,80}(?:routing\s+owner|owner)(?:다|이다|로\s*승격)",
            ),
            positive_reason="delegated detail source is explicitly kept distinct from routing owner",
            contradiction_reason="response promotes a delegated detail source to routing owner",
            unknown_reason="response does not deterministically establish the delegated-source distinction",
        )
    if evidence_id == "current_historical_distinction":
        return _bounded_relation(
            response,
            positive=(
                r"historical\s+(?:source|evidence|material).{0,80}(?:does\s+not\s+replace|is\s+not)\s+(?:the\s+)?current\s+truth",
                r"과거\s*(?:자료|근거|출처).{0,80}(?:current\s+truth|현재\s*(?:사실|상태)).{0,20}(?:대체하지\s*않|아니)",
            ),
            contradiction=(
                r"historical\s+(?:source|evidence|material).{0,80}(?:replaces|becomes|is)\s+(?:the\s+)?current\s+truth",
                r"과거\s*(?:자료|근거|출처).{0,80}(?:current\s+truth|현재\s*(?:사실|상태))(?:다|이다|로\s*승격)",
            ),
            positive_reason="historical source is explicitly kept separate from current truth",
            contradiction_reason="response promotes historical material to current truth",
            unknown_reason="response does not deterministically establish the historical/current distinction",
        )
    raise SchemaError(f"unsupported P4-B evidence id: {evidence_id}")


def _marker(record: Phase4WorkUATRecord) -> str | None:
    if record.marker_verification is None:
        return None
    return str(record.marker_verification["revealed_marker"])


def _marker_is_promoted_to_current(response: str, marker: str) -> bool:
    marker_pattern = re.escape(marker)
    current = r"(?:current\s+(?:repository\s+)?(?:truth|state)|repository's\s+current\s+state|현재\s*(?:repository\s*)?(?:사실|상태))"
    return _matches(
        response,
        (
            rf"{current}\s*(?:is|=|:)\s*{marker_pattern}(?=$|[\s.,;])",
            rf"{current}\s*,?\s*(?:however|actually|now)\s*,?\s*(?:is|=|:)\s*{marker_pattern}(?=$|[\s.,;])",
            rf"{marker_pattern}\s*(?:is|=|is\s+now|has\s+become)\s+(?:the\s+)?{current}",
            rf"{marker_pattern}\s*,?\s*(?:however|actually|now)\s*,?\s*(?:is|=)\s+(?:the\s+)?{current}",
            rf"{marker_pattern}.{{0,80}}\b(?:that|it)\s+(?:is\s+now|is|has\s+become)\s+(?:the\s+)?{current}",
            rf"{marker_pattern}.{{0,100}}\b(?:that|it)\s+is\s+now\s+(?:the\s+)?repository's\s+current\s+state",
            rf"{current}(?:은|는|이|가|:)\s*{marker_pattern}(?:이다|다|임)?",
            rf"{marker_pattern}(?:이|가|은|는)?\s*{current}(?:이다|다|임)",
        ),
    )


def _marker_historical_relation(response: str, marker: str) -> tuple[ResultStatus, str]:
    marker_pattern = re.escape(marker)
    if _matches(
        response,
        (
            rf"(?:historical\s+(?:fact|value)|fact\s+from\s+(?:the\s+)?(?:prior|earlier)\s+(?:conversation|chat)|이전\s+대화(?:의|에서)?\s*(?:사실|값)|과거\s*(?:사실|값))(?:은|는)?\s*(?:is|was|=|:)?\s*{marker_pattern}",
            rf"{marker_pattern}\s*(?:is|was|=|:)\s*(?:a\s+)?historical\s+(?:fact|value)",
            rf"{marker_pattern}(?:은|는|이|가)?\s*(?:이전\s+대화의|과거의?)\s*(?:사실|값)(?:이다|다|임)",
        ),
    ):
        return ResultStatus.PASS, "exact marker is explicitly labeled as historical evidence"
    return ResultStatus.FAIL, "exact marker lacks a deterministic historical provenance relation"


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
        return _marker_historical_relation(response, marker)
    if evidence_id == "current_truth_precedence":
        if _marker_is_promoted_to_current(response, marker):
            return ResultStatus.FAIL, "historical marker is explicitly promoted to current truth"
        current_status, _ = _current_system_truth(response)
        if current_status is ResultStatus.FAIL:
            return ResultStatus.FAIL, "response contradicts the current repository status"
        if current_status is ResultStatus.UNKNOWN:
            return ResultStatus.UNKNOWN, "current repository status relation is ambiguous"
        precedence = _matches(
            response,
            (
                r"current\s+(?:repository\s+)?truth.{0,50}(?:takes|has)\s+precedence",
                r"current\s+(?:repository\s+)?truth.{0,50}(?:is|remains)\s+(?:separate\s+and\s+)?authoritative",
                r"(?:현재\s*(?:repository\s*)?(?:사실|상태)).{0,50}(?:우선|기준|authoritative)",
            ),
        )
        if precedence:
            return ResultStatus.PASS, "current repository truth is separately present and prioritized"
        return ResultStatus.UNKNOWN, "response does not deterministically establish current-truth precedence"
    raise SchemaError(f"unsupported P4-C2 evidence id: {evidence_id}")


def _p4d_assertion(evidence_id: str, response: str) -> tuple[ResultStatus, str]:
    if evidence_id == "system_evaluation_owner_claim":
        return _owner_relation(
            response,
            expected_owner="evals/system/README.md",
            relation="system_evaluation",
        )
    if evidence_id == "phase3_phase4_boundary":
        return _current_system_truth(response)
    if evidence_id == "observable_routing_result":
        lowered = response.casefold()
        phase5_claim = _matches(
            lowered,
            (
                r"\bphase\s*5\b[^\n]{0,50}\b(?:passed|complete|completed|started)\b",
                r"\bphase5_not_started\b[^\n]{0,60}\b(?:outdated|obsolete|no\s+longer\s+true|incorrect)\b",
                r"phase\s*5[^\n]{0,50}(?:실행됨|실행했다|완료됨|완료했다|시작됨|시작했다)",
            ),
        )
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
    if scenario.id == "P4-A" and record.expected_receipt_ref is None:
        return WorkUATClassification(
            scenario.id, ResultStatus.INVALID_FIXTURE, (), "expected receipt ref is missing"
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
    if by_id["P4-B"].user_prompt != P4B_TARGET_PROMPT:
        raise SchemaError("P4-B target prompt does not ask for every required relation")
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
