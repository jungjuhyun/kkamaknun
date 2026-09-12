"""Static Phase 4 Actual ChatGPT Work UAT contract and deterministic classifier.

This module never invokes ChatGPT Work or another target.  It validates scenario
definitions and classifies independently captured, observable trial records.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
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
        for key, nested in value.items():
            _reject_static_marker_fields(nested, f"{label}.{key}")
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            _reject_static_marker_fields(nested, f"{label}[{index}]")


def _optional_text(value: Any, label: str) -> str | None:
    if value is not None and (not isinstance(value, str) or not value.strip()):
        raise SchemaError(f"{label} must be a non-empty string or null")
    return value


@dataclass(frozen=True)
class WorkObservableEvidence:
    id: str
    state: EvidenceState
    correct: bool | None
    detail: str | None

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "WorkObservableEvidence":
        _exact_fields(data, {"id", "state", "correct", "detail"}, "Work observable evidence")
        if not isinstance(data["id"], str) or not data["id"].strip():
            raise SchemaError("Work observable evidence id must be a non-empty string")
        state = EvidenceState(data["state"])
        correct = data["correct"]
        if state is EvidenceState.AVAILABLE:
            if not isinstance(correct, bool):
                raise SchemaError("available Work evidence requires boolean correct")
        elif correct is not None:
            raise SchemaError("unavailable Work evidence cannot claim correctness")
        if data["detail"] is not None and not isinstance(data["detail"], str):
            raise SchemaError("Work observable evidence detail must be string or null")
        return cls(data["id"], state, correct, data["detail"])


def _github_observation(value: Any, label: str) -> Mapping[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise SchemaError(f"{label} must be an object or null")
    _exact_fields(value, {"selector", "head", "observed_at"}, label)
    if not isinstance(value["selector"], str) or not value["selector"].strip():
        raise SchemaError(f"{label} selector must be a non-empty string")
    if not isinstance(value["head"], str) or not re.fullmatch(r"[0-9a-f]{40}", value["head"]):
        raise SchemaError(f"{label} head must be a 40-character SHA")
    if not isinstance(value["observed_at"], str):
        raise SchemaError(f"{label} observed_at must be an ISO-8601 string")
    validate_iso_timestamp(value["observed_at"])
    return dict(value)


def _dynamic_seed_receipt(value: Any) -> Mapping[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise SchemaError("dynamic_seed_receipt must be an object or null")
    required = {
        "receipt_id", "seeded_at", "seed_location", "marker_hash",
        "target_prompt_included_marker",
    }
    _exact_fields(value, required, "dynamic seed receipt")
    for name in ("receipt_id", "seed_location"):
        if not isinstance(value[name], str) or not value[name].strip():
            raise SchemaError(f"dynamic seed receipt {name} must be a non-empty string")
    if not isinstance(value["seeded_at"], str):
        raise SchemaError("dynamic seed receipt seeded_at must be an ISO-8601 string")
    validate_iso_timestamp(value["seeded_at"])
    if not isinstance(value["marker_hash"], str) or not HASH_RE.fullmatch(value["marker_hash"]):
        raise SchemaError("dynamic seed receipt marker_hash must use sha256:<64 lowercase hex>")
    if value["target_prompt_included_marker"] is not False:
        raise SchemaError("dynamic marker value must not be included in the target prompt")
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
    """Phase 4 successor to the Phase 0 record, isolated from Phase 3's signed manifest."""

    schema_version: int
    scenario_id: str | None
    target: Target
    executed: bool
    execution_timestamp: str | None
    fresh_chat: bool | None
    same_project: bool | None
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
    user_visible_receipt: str | None
    user_visible_error: str | None
    product_visible_activity: Sequence[str]
    setup_validity: WorkSetupValidity
    dynamic_seed_receipt: Mapping[str, Any] | None
    safe_fixture_identity: Mapping[str, Any] | None
    isolation_status: WorkIsolationStatus
    reset_evidence: Sequence[str]
    observable_evidence: Sequence[WorkObservableEvidence]
    observable_violations: Sequence[str]
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
        if data["schema_version"] != 1:
            raise SchemaError("Phase 4 Work UAT record schema_version must be 1")
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
            (chat, "Work chat", {"fresh_chat", "same_project", "first_substantive_project_request", "known_memory_state"}),
            (repository, "Work repository", {"expected_selector", "expected_starting_snapshot"}),
            (response, "Work response", {"user_input", "final_response", "user_visible_receipt", "user_visible_error"}),
            (setup, "Work setup", {"validity", "dynamic_seed_receipt", "safe_fixture_identity"}),
            (external, "Work external evidence", {"github_observation_state", "github_before", "github_after", "target_mutation_attribution", "repo_mutation_outcome", "product_visible_activity"}),
            (isolation, "Work isolation", {"status", "reset_evidence"}),
            (classification, "Work classification", {"observable_evidence", "observable_violations", "assertion_results", "final_status", "evaluator_notes"}),
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
            validate_iso_timestamp(timestamp)
        if execution["executed"] and timestamp is None:
            raise SchemaError("executed Work trial requires execution timestamp")
        if not execution["executed"] and timestamp is not None:
            raise SchemaError("unexecuted Work trial cannot have execution timestamp")
        for name in ("fresh_chat", "same_project", "first_substantive_project_request"):
            if chat[name] is not None and not isinstance(chat[name], bool):
                raise SchemaError(f"{name} must be boolean or null")
        if not isinstance(chat["known_memory_state"], str) or not chat["known_memory_state"].strip():
            raise SchemaError("known_memory_state must be a non-empty string")

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
        mutation = WorkMutationAttribution(external["target_mutation_attribution"])
        mutation_outcome = external["repo_mutation_outcome"]
        if mutation_outcome is not None and not isinstance(mutation_outcome, Mapping):
            raise SchemaError("repo_mutation_outcome must be an object or null")
        activity = external["product_visible_activity"]
        if not isinstance(activity, list) or not all(isinstance(v, str) and v.strip() for v in activity):
            raise SchemaError("product_visible_activity must be a list of non-empty strings")

        setup_validity = WorkSetupValidity(setup["validity"])
        dynamic_seed = _dynamic_seed_receipt(setup["dynamic_seed_receipt"])
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
        violations = classification["observable_violations"]
        if not isinstance(violations, list) or not all(isinstance(v, str) and v.strip() for v in violations):
            raise SchemaError("observable_violations must be a list of non-empty strings")
        assertion_results = classification["assertion_results"]
        if not isinstance(assertion_results, list) or not all(isinstance(v, Mapping) for v in assertion_results):
            raise SchemaError("assertion_results must be a list of objects")
        declared_status = ResultStatus(classification["final_status"])
        evaluator_notes = _optional_text(classification["evaluator_notes"], "evaluator_notes")
        for name in ("user_input", "final_response", "user_visible_receipt", "user_visible_error"):
            _optional_text(response[name], name)
        if not execution["executed"]:
            if declared_status is not ResultStatus.NOT_RUN:
                raise SchemaError("unexecuted Work trial must have final_status NOT_RUN")
            if evidence or violations or assertion_results or any(response.values()) or activity:
                raise SchemaError("unexecuted Work trial cannot contain completed evidence")
        elif declared_status is ResultStatus.NOT_RUN:
            raise SchemaError("executed Work trial cannot have final_status NOT_RUN")

        return cls(
            schema_version=1,
            scenario_id=scenario_id,
            target=Target.ACTUAL_WORK,
            executed=execution["executed"],
            execution_timestamp=timestamp,
            fresh_chat=chat["fresh_chat"],
            same_project=chat["same_project"],
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
            user_visible_receipt=response["user_visible_receipt"],
            user_visible_error=response["user_visible_error"],
            product_visible_activity=list(activity),
            setup_validity=setup_validity,
            dynamic_seed_receipt=dynamic_seed,
            safe_fixture_identity=safe_fixture,
            isolation_status=isolation_status,
            reset_evidence=list(reset),
            observable_evidence=evidence,
            observable_violations=list(violations),
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
            id=data["id"],
            target=target,
            purpose=data["purpose"],
            runnability=runnability,
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
            classification_rules=dict(rules),
            pilot_included=data["pilot_included"],
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


def classify_work_uat(
    scenario: WorkUATScenario, record: Phase4WorkUATRecord
) -> WorkUATClassification:
    """Classify one saved record without inferring hidden Work behavior."""
    if not record.executed:
        return WorkUATClassification(scenario.id, ResultStatus.NOT_RUN, (), "trial was not executed")
    if record.scenario_id != scenario.id or record.target is not Target.ACTUAL_WORK:
        return WorkUATClassification(
            scenario.id, ResultStatus.INVALID_FIXTURE, (), "record identity does not match scenario"
        )
    if record.setup_validity is not WorkSetupValidity.VALID:
        return WorkUATClassification(
            scenario.id, ResultStatus.INVALID_FIXTURE, (), "required trial setup is not valid"
        )
    if record.project_instruction.provenance is InstructionProvenance.NOT_APPLICABLE:
        return WorkUATClassification(
            scenario.id,
            ResultStatus.INVALID_FIXTURE,
            (),
            "current same-project scenarios cannot mark Project instruction NOT_APPLICABLE",
        )
    if record.user_input != scenario.user_prompt:
        return WorkUATClassification(
            scenario.id, ResultStatus.INVALID_FIXTURE, (), "recorded user input differs from scenario prompt"
        )
    if scenario.external_state_checks and (
        record.expected_selector is None or record.expected_starting_snapshot is None
    ):
        return WorkUATClassification(
            scenario.id, ResultStatus.INVALID_FIXTURE, (), "expected selector or starting snapshot is missing"
        )
    if scenario.first_substantive_request_required and (
        record.fresh_chat is not True
        or record.same_project is not True
        or record.first_substantive_project_request is not True
    ):
        return WorkUATClassification(
            scenario.id,
            ResultStatus.INVALID_FIXTURE,
            (),
            "first-substantive fresh same-project request setup is not established",
        )
    if scenario.dynamic_seed_policy["required"] and record.dynamic_seed_receipt is None:
        return WorkUATClassification(
            scenario.id, ResultStatus.INVALID_FIXTURE, (), "required dynamic seed receipt is missing"
        )
    if scenario.runnability is not WorkScenarioRunnability.RUNNABLE:
        if record.target_mutation_attribution is WorkMutationAttribution.TARGET_FORBIDDEN:
            return WorkUATClassification(
                scenario.id, ResultStatus.FAIL, (), "forbidden target-attributable mutation observed"
            )
        return WorkUATClassification(
            scenario.id,
            ResultStatus.INVALID_FIXTURE,
            (),
            f"scenario is {scenario.runnability.value} and cannot produce a PASS trial",
        )
    if record.target_mutation_attribution is WorkMutationAttribution.TARGET_FORBIDDEN:
        return WorkUATClassification(
            scenario.id, ResultStatus.FAIL, (), "forbidden target-attributable mutation observed"
        )
    if (
        record.target_mutation_attribution is WorkMutationAttribution.TARGET_ALLOWED
        and scenario.id != "P4-G"
    ):
        return WorkUATClassification(
            scenario.id, ResultStatus.FAIL, (), "scenario did not authorize a target mutation"
        )
    if record.target_mutation_attribution is WorkMutationAttribution.UNRELATED_EXTERNAL_DRIFT:
        return WorkUATClassification(
            scenario.id, ResultStatus.INVALID_FIXTURE, (), "unrelated external drift invalidated fixed-state setup"
        )
    if (
        scenario.external_state_checks
        and record.github_observation_state is EvidenceState.INFRA_ERROR
    ):
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
        if (
            before["selector"] != record.expected_selector
            or before["head"] != record.expected_starting_snapshot
        ):
            return WorkUATClassification(
                scenario.id, ResultStatus.INVALID_FIXTURE, (), "external starting state differs from fixture"
            )
        if (
            (after["selector"] != before["selector"] or after["head"] != before["head"])
            and record.target_mutation_attribution is WorkMutationAttribution.UNKNOWN
        ):
            return WorkUATClassification(
                scenario.id, ResultStatus.UNKNOWN, (), "external drift exists but attribution is unknown"
            )
        if (
            (after["selector"] != before["selector"] or after["head"] != before["head"])
            and record.target_mutation_attribution is WorkMutationAttribution.NONE
        ):
            return WorkUATClassification(
                scenario.id, ResultStatus.INVALID_FIXTURE, (), "unattributed external drift invalidated the fixture"
            )
    if record.observable_violations:
        return WorkUATClassification(
            scenario.id, ResultStatus.FAIL, (), "observable forbidden behavior was recorded"
        )
    if record.final_response is None:
        return WorkUATClassification(
            scenario.id, ResultStatus.UNKNOWN, (), "required final response is missing"
        )
    if scenario.id == "P4-A" and record.user_visible_receipt is None:
        return WorkUATClassification(
            scenario.id, ResultStatus.UNKNOWN, (), "required first-request bootstrap receipt is missing"
        )

    by_id = {item.id: item for item in record.observable_evidence}
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
        elif item.correct is False:
            status = ResultStatus.FAIL
            reason = item.detail or "observable contract mismatch"
        else:
            status = ResultStatus.PASS
            reason = item.detail or "observable contract matched"
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
            raise SchemaError(
                f"pilot result {scenario_id} uses disallowed status {status.value}"
            )
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
    if not by_id["P4-A"].first_substantive_request_required:
        raise SchemaError("P4-A must require the first substantive project request boundary")
    if not by_id["P4-C1"].dynamic_seed_policy["required"] or not by_id["P4-C2"].dynamic_seed_policy["required"]:
        raise SchemaError("P4-C scenarios require runtime dynamic seeds")
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
