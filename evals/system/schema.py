"""Strict, dependency-free schemas for system evaluation data."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import re
from typing import Any, Mapping, Sequence


class SchemaError(ValueError):
    """Raised when evaluation input is structurally invalid."""


class Suite(str, Enum):
    REGRESSION = "regression"
    CAPABILITY = "capability"
    ADVERSARIAL = "adversarial"
    FIELD = "field"


class Target(str, Enum):
    DIRECT_COMPONENT = "direct_component"
    FUTURE_INSPECT_CODEX = "future_inspect_codex"
    ACTUAL_WORK = "actual_work"


class Criticality(str, Enum):
    CRITICAL = "critical"
    NON_CRITICAL = "non_critical"


class ResultStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"
    INFRA_ERROR = "INFRA_ERROR"
    INVALID_FIXTURE = "INVALID_FIXTURE"
    NOT_RUN = "NOT_RUN"


class TargetIdentityStatus(str, Enum):
    """Whether a trial's target identity is independently pinned."""

    PINNED = "PINNED"
    REQUESTED_ONLY = "REQUESTED_ONLY"
    LEGACY_UNPINNED = "LEGACY_UNPINNED"


class EvidenceState(str, Enum):
    AVAILABLE = "AVAILABLE"
    MISSING = "MISSING"
    INFRA_ERROR = "INFRA_ERROR"
    INVALID = "INVALID"


@dataclass(frozen=True)
class TargetIdentity:
    """Machine-readable target configuration attached to every new Codex trial.

    Requested values come from the runner invocation. Effective values are only
    populated when an independent Codex event exposes them; otherwise they are
    the literal ``UNKNOWN`` and never inferred from the request.
    """

    requested_model: str
    requested_reasoning_effort: str
    effective_model: str
    effective_reasoning_effort: str
    codex_cli_version: str
    trial_snapshot: str
    target_lane: str
    identity_status: TargetIdentityStatus

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "TargetIdentity":
        required = {
            "requested_model",
            "requested_reasoning_effort",
            "effective_model",
            "effective_reasoning_effort",
            "codex_cli_version",
            "trial_snapshot",
            "target_lane",
            "identity_status",
        }
        _require_fields(data, required, "target identity")
        values = {name: data[name] for name in required}
        for name in required - {"identity_status"}:
            if not isinstance(values[name], str) or not values[name].strip():
                raise SchemaError(f"target identity {name} must be a non-empty string")
        if values["effective_model"] != "UNKNOWN" and values["effective_reasoning_effort"] == "UNKNOWN":
            raise SchemaError("effective model and reasoning effort must be observed together")
        if values["effective_model"] == "UNKNOWN" and values["effective_reasoning_effort"] != "UNKNOWN":
            raise SchemaError("effective model and reasoning effort must be observed together")
        if not re.fullmatch(r"[0-9a-f]{40}", values["trial_snapshot"]):
            raise SchemaError("target identity trial_snapshot must be a 40-character SHA")
        expected_lane = f"model={values['requested_model']};reasoning_effort={values['requested_reasoning_effort']}"
        if values["target_lane"] != expected_lane:
            raise SchemaError("target_lane must be derived from requested model and reasoning effort")
        status = TargetIdentityStatus(values["identity_status"])
        effective_known = values["effective_model"] != "UNKNOWN"
        if status is TargetIdentityStatus.PINNED and not effective_known:
            raise SchemaError("PINNED target identity requires independently observed effective values")
        if status is TargetIdentityStatus.REQUESTED_ONLY and effective_known:
            raise SchemaError("REQUESTED_ONLY target identity cannot carry effective values")
        if status is TargetIdentityStatus.LEGACY_UNPINNED:
            raise SchemaError("legacy target identity must be represented by a missing identity, not a trial record")
        return cls(
            requested_model=values["requested_model"],
            requested_reasoning_effort=values["requested_reasoning_effort"],
            effective_model=values["effective_model"],
            effective_reasoning_effort=values["effective_reasoning_effort"],
            codex_cli_version=values["codex_cli_version"],
            trial_snapshot=values["trial_snapshot"],
            target_lane=values["target_lane"],
            identity_status=status,
        )


class InstructionProvenance(str, Enum):
    VERIFIED = "VERIFIED"
    USER_SUPPLIED = "USER_SUPPLIED"
    UNKNOWN = "UNKNOWN"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class WorkIsolationStatus(str, Enum):
    CLEAN_VERIFIED = "CLEAN_VERIFIED"
    CLEAN_PARTIAL = "CLEAN_PARTIAL"
    CONTAMINATION_SEEDED = "CONTAMINATION_SEEDED"
    UNKNOWN = "UNKNOWN"


class IsolationProfileName(str, Enum):
    OFFLINE_CONTAINER = "offline_container"
    INTERNAL_SERVICES_ONLY = "internal_services_only"
    CONTROLLED_MOCK_ACCESS = "controlled_mock_access"
    PROVIDER_REQUIRED = "provider_required"
    LIVE_EXTERNAL = "live_external"
    DISPOSABLE_WORKTREE = "disposable_worktree"


TASK_REQUIRED_FIELDS = {
    "id",
    "suite",
    "target",
    "risk_surface",
    "criticality",
    "setup",
    "precondition",
    "user_input",
    "expected_observable_behavior",
    "forbidden_observable_behavior",
    "assertions",
    "trial_count",
    "isolation_profile",
    "required_evidence",
    "optional_evidence",
    "snapshot_expectation",
}

ASSERTION_REQUIRED_FIELDS = {
    "id",
    "target",
    "evidence_source",
    "required_for_pass",
    "evaluation_method",
    "on_missing_evidence",
}

HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


def _require_fields(data: Mapping[str, Any], required: set[str], label: str) -> None:
    missing = sorted(required - set(data))
    if missing:
        raise SchemaError(f"{label} missing required fields: {', '.join(missing)}")


def _nonempty_strings(value: Any, label: str) -> list[str]:
    if not isinstance(value, list) or not value or not all(
        isinstance(item, str) and item.strip() for item in value
    ):
        raise SchemaError(f"{label} must be a non-empty list of strings")
    return list(value)


@dataclass(frozen=True)
class AssertionSpec:
    id: str
    target: Target
    evidence_source: str
    required_for_pass: bool
    evaluation_method: str
    on_missing_evidence: ResultStatus
    parameters: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "AssertionSpec":
        _require_fields(data, ASSERTION_REQUIRED_FIELDS, "assertion")
        if data["on_missing_evidence"] != ResultStatus.UNKNOWN.value:
            raise SchemaError("on_missing_evidence must be UNKNOWN")
        if not isinstance(data["required_for_pass"], bool):
            raise SchemaError("required_for_pass must be boolean")
        for name in ("id", "evidence_source", "evaluation_method"):
            if not isinstance(data[name], str) or not data[name].strip():
                raise SchemaError(f"assertion {name} must be a non-empty string")
        parameters = data.get("parameters", {})
        if not isinstance(parameters, Mapping):
            raise SchemaError("assertion parameters must be an object")
        return cls(
            id=data["id"],
            target=Target(data["target"]),
            evidence_source=data["evidence_source"],
            required_for_pass=data["required_for_pass"],
            evaluation_method=data["evaluation_method"],
            on_missing_evidence=ResultStatus.UNKNOWN,
            parameters=dict(parameters),
        )


@dataclass(frozen=True)
class TaskSpec:
    id: str
    suite: Suite
    target: Target
    risk_surface: Sequence[str]
    criticality: Criticality
    setup: Sequence[str]
    precondition: Sequence[str]
    user_input: str
    expected_observable_behavior: Sequence[str]
    forbidden_observable_behavior: Sequence[str]
    assertions: Sequence[AssertionSpec]
    trial_count: int
    isolation_profile: IsolationProfileName
    required_evidence: Sequence[str]
    optional_evidence: Sequence[str]
    snapshot_expectation: Mapping[str, Any]

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "TaskSpec":
        _require_fields(data, TASK_REQUIRED_FIELDS, "task")
        if not isinstance(data["id"], str) or not data["id"].strip():
            raise SchemaError("task id must be a non-empty string")
        if not isinstance(data["user_input"], str) or not data["user_input"].strip():
            raise SchemaError("user_input must be a non-empty string")
        if not isinstance(data["trial_count"], int) or data["trial_count"] <= 0:
            raise SchemaError("trial_count must be a positive integer")
        if not isinstance(data["assertions"], list) or not data["assertions"]:
            raise SchemaError("assertions must be a non-empty list")
        assertions = [AssertionSpec.from_dict(item) for item in data["assertions"]]
        target = Target(data["target"])
        if any(assertion.target != target for assertion in assertions):
            raise SchemaError("every assertion target must match its task target")
        assertion_ids = [assertion.id for assertion in assertions]
        if len(assertion_ids) != len(set(assertion_ids)):
            raise SchemaError("assertion ids must be unique within a task")
        snapshot = data["snapshot_expectation"]
        if not isinstance(snapshot, Mapping):
            raise SchemaError("snapshot_expectation must be an object")
        optional = data["optional_evidence"]
        if not isinstance(optional, list) or not all(isinstance(v, str) for v in optional):
            raise SchemaError("optional_evidence must be a list of strings")
        return cls(
            id=data["id"],
            suite=Suite(data["suite"]),
            target=target,
            risk_surface=_nonempty_strings(data["risk_surface"], "risk_surface"),
            criticality=Criticality(data["criticality"]),
            setup=_nonempty_strings(data["setup"], "setup"),
            precondition=_nonempty_strings(data["precondition"], "precondition"),
            user_input=data["user_input"],
            expected_observable_behavior=_nonempty_strings(
                data["expected_observable_behavior"], "expected_observable_behavior"
            ),
            forbidden_observable_behavior=_nonempty_strings(
                data["forbidden_observable_behavior"], "forbidden_observable_behavior"
            ),
            assertions=assertions,
            trial_count=data["trial_count"],
            isolation_profile=IsolationProfileName(data["isolation_profile"]),
            required_evidence=_nonempty_strings(data["required_evidence"], "required_evidence"),
            optional_evidence=list(optional),
            snapshot_expectation=dict(snapshot),
        )


@dataclass(frozen=True)
class EvidenceRecord:
    id: str
    target: Target
    state: EvidenceState
    value: Any = None
    detail: str | None = None

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "EvidenceRecord":
        _require_fields(data, {"id", "target", "state"}, "evidence")
        return cls(
            id=str(data["id"]),
            target=Target(data["target"]),
            state=EvidenceState(data["state"]),
            value=data.get("value"),
            detail=data.get("detail"),
        )


@dataclass(frozen=True)
class AssertionResult:
    assertion_id: str
    status: ResultStatus
    reason: str
    evidence_source: str


@dataclass(frozen=True)
class TrialResult:
    task_id: str
    target: Target
    status: ResultStatus
    assertions: Sequence[AssertionResult]
    evidence_ids: Sequence[str]


@dataclass(frozen=True)
class ProjectInstructionEvidence:
    provenance: InstructionProvenance
    capture_method: str | None = None
    observed_at: str | None = None
    content_hash: str | None = None
    artifact_hash: str | None = None
    active_ui_match: bool | None = None
    exact_text_bytes_available: bool = False

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ProjectInstructionEvidence":
        if "provenance" not in data:
            raise SchemaError("project_instruction provenance is required")
        item = cls(
            provenance=InstructionProvenance(data["provenance"]),
            capture_method=data.get("capture_method"),
            observed_at=data.get("observed_at"),
            content_hash=data.get("content_hash"),
            artifact_hash=data.get("artifact_hash"),
            active_ui_match=data.get("active_ui_match"),
            exact_text_bytes_available=bool(data.get("exact_text_bytes_available", False)),
        )
        item.validate()
        return item

    def validate(self) -> None:
        if self.observed_at is not None:
            validate_iso_timestamp(self.observed_at)
        for name, value in (("content_hash", self.content_hash), ("artifact_hash", self.artifact_hash)):
            if value is not None and not HASH_RE.fullmatch(value):
                raise SchemaError(f"{name} must use sha256:<64 lowercase hex>")
        if self.content_hash and not self.exact_text_bytes_available:
            raise SchemaError("content_hash requires exact instruction text bytes")
        if self.exact_text_bytes_available and not self.content_hash:
            raise SchemaError("exact instruction text bytes require content_hash")
        if self.provenance is InstructionProvenance.VERIFIED:
            if self.active_ui_match is not True or not self.content_hash:
                raise SchemaError("VERIFIED requires active_ui_match=true and content_hash")
        elif self.active_ui_match is True:
            raise SchemaError("only VERIFIED provenance may assert active_ui_match=true")
        if self.provenance is InstructionProvenance.UNKNOWN and self.content_hash:
            raise SchemaError("UNKNOWN provenance cannot claim instruction content_hash")
        if self.provenance is InstructionProvenance.NOT_APPLICABLE:
            if any((self.capture_method, self.observed_at, self.content_hash, self.artifact_hash)):
                raise SchemaError("NOT_APPLICABLE cannot carry instruction evidence")
            if self.active_ui_match is not None or self.exact_text_bytes_available:
                raise SchemaError("NOT_APPLICABLE cannot claim UI or text evidence")


@dataclass(frozen=True)
class IsolationProfile:
    name: IsolationProfileName
    filesystem_isolation_expectation: str
    process_isolation_expectation: str
    network_expectation: str
    evaluator_network_expectation: str
    provider_network_expectation: str
    custom_tool_scorer_boundary: str
    required_probe: Sequence[str]

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "IsolationProfile":
        fields = {
            "name",
            "filesystem_isolation_expectation",
            "process_isolation_expectation",
            "network_expectation",
            "evaluator_network_expectation",
            "provider_network_expectation",
            "custom_tool_scorer_boundary",
            "required_probe",
        }
        _require_fields(data, fields, "isolation profile")
        for name in fields - {"name", "required_probe"}:
            if not isinstance(data[name], str) or not data[name].strip():
                raise SchemaError(f"{name} must be a non-empty string")
        return cls(
            name=IsolationProfileName(data["name"]),
            filesystem_isolation_expectation=data["filesystem_isolation_expectation"],
            process_isolation_expectation=data["process_isolation_expectation"],
            network_expectation=data["network_expectation"],
            evaluator_network_expectation=data["evaluator_network_expectation"],
            provider_network_expectation=data["provider_network_expectation"],
            custom_tool_scorer_boundary=data["custom_tool_scorer_boundary"],
            required_probe=_nonempty_strings(data["required_probe"], "required_probe"),
        )


@dataclass(frozen=True)
class WorkUATRecord:
    fresh_chat: bool | None
    same_project: bool | None
    known_memory_state: str
    repo_head: str | None
    project_instruction: ProjectInstructionEvidence
    contamination_seed: str | None
    final_response: str | None
    external_github_state: Mapping[str, Any] | None
    repo_mutation_outcome: Mapping[str, Any] | None
    observable_error_or_receipt: str | None
    evaluator_notes: str | None
    isolation_status: WorkIsolationStatus
    reset_evidence: Sequence[str]

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "WorkUATRecord":
        required = {
            "fresh_chat",
            "same_project",
            "known_memory_state",
            "repo_head",
            "project_instruction",
            "contamination_seed",
            "final_response",
            "external_github_state",
            "repo_mutation_outcome",
            "observable_error_or_receipt",
            "evaluator_notes",
            "isolation_status",
            "reset_evidence",
        }
        _require_fields(data, required, "Work UAT record")
        reset = data["reset_evidence"]
        if not isinstance(reset, list) or not all(isinstance(v, str) for v in reset):
            raise SchemaError("reset_evidence must be a list of strings")
        status = WorkIsolationStatus(data["isolation_status"])
        if status is WorkIsolationStatus.CLEAN_VERIFIED and not reset:
            raise SchemaError("CLEAN_VERIFIED requires supported reset evidence")
        for name in ("fresh_chat", "same_project"):
            if data[name] is not None and not isinstance(data[name], bool):
                raise SchemaError(f"{name} must be boolean or null")
        if not isinstance(data["known_memory_state"], str):
            raise SchemaError("known_memory_state must be a string")
        return cls(
            fresh_chat=data["fresh_chat"],
            same_project=data["same_project"],
            known_memory_state=data["known_memory_state"],
            repo_head=data["repo_head"],
            project_instruction=ProjectInstructionEvidence.from_dict(data["project_instruction"]),
            contamination_seed=data["contamination_seed"],
            final_response=data["final_response"],
            external_github_state=data["external_github_state"],
            repo_mutation_outcome=data["repo_mutation_outcome"],
            observable_error_or_receipt=data["observable_error_or_receipt"],
            evaluator_notes=data["evaluator_notes"],
            isolation_status=status,
            reset_evidence=list(reset),
        )


def validate_iso_timestamp(value: str) -> None:
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise SchemaError("observed_at must be an ISO-8601 timestamp") from exc
