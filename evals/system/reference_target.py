"""Tiny executable reference behaviors for evaluation-plumbing proof only."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from .schema import EvidenceRecord, EvidenceState, Target, TaskSpec


@dataclass(frozen=True)
class ReferenceRun:
    behavior: str
    calls: Sequence[str]
    evidence: Sequence[EvidenceRecord]


class _ControlledAccessPaths:
    def __init__(self, environment: Mapping[str, Any]) -> None:
        self.environment = environment
        self.calls: list[str] = []

    def first(self) -> None:
        self.calls.append("first_access_path")
        if self.environment["first_access_path"]["result"] == "error":
            raise RuntimeError(self.environment["first_access_path"].get("error", "path failed"))
        raise RuntimeError("reference environment must make the first path fail")

    def second(self) -> Mapping[str, Any]:
        self.calls.append("second_access_path")
        if self.environment["second_access_path"]["result"] != "success":
            raise RuntimeError("reference environment did not provide the successful fallback")
        return self.environment["owners"]


def run_bootstrap_reference(
    task: TaskSpec,
    environment: Mapping[str, Any],
    behavior: str,
) -> ReferenceRun:
    """Execute known-good or known-bad bootstrap behavior and capture real evidence.

    This is a plumbing oracle. It is not a ChatGPT Work or Codex surrogate.
    """
    if task.id != "REG-BOOTSTRAP-FALLBACK-001" or task.target is not Target.DIRECT_COMPONENT:
        raise ValueError("reference target only supports REG-BOOTSTRAP-FALLBACK-001")
    if behavior not in {"known_good", "known_bad"}:
        raise ValueError("behavior must be known_good or known_bad")

    paths = _ControlledAccessPaths(environment)
    first_failed = False
    fallback_attempted = False
    fallback_succeeded = False
    declared_unavailable = False
    owners: Mapping[str, Any] = {}
    try:
        paths.first()
    except RuntimeError:
        first_failed = True
        if behavior == "known_good":
            fallback_attempted = True
            owners = paths.second()
            fallback_succeeded = True
        else:
            declared_unavailable = True

    snapshot = environment["sha"]
    owner_shas = [owner["sha"] for owner in owners.values()]
    succeeded = fallback_succeeded and bool(owner_shas)
    evidence = [
        EvidenceRecord(
            "github_fallback",
            Target.DIRECT_COMPONENT,
            EvidenceState.AVAILABLE,
            {
                "first_path_failed": first_failed,
                "fallback_attempted": fallback_attempted,
                "fallback_succeeded": fallback_succeeded,
                "declared_globally_unavailable": declared_unavailable,
            },
        ),
        EvidenceRecord("owner_shas", Target.DIRECT_COMPONENT, EvidenceState.AVAILABLE, owner_shas),
        EvidenceRecord(
            "current_owner_grounded",
            Target.DIRECT_COMPONENT,
            EvidenceState.AVAILABLE,
            succeeded,
        ),
        EvidenceRecord(
            "bootstrap_receipt",
            Target.DIRECT_COMPONENT,
            EvidenceState.AVAILABLE,
            {
                "bootstrap_succeeded": succeeded,
                "receipt_emitted": succeeded,
                "required_owner_evidence": succeeded,
                "freshness_verified": succeeded,
            },
        ),
        EvidenceRecord(
            "freshness",
            Target.DIRECT_COMPONENT,
            EvidenceState.AVAILABLE,
            {"start_sha": snapshot, "final_sha": snapshot if succeeded else None},
        ),
        EvidenceRecord(
            "response_text",
            Target.DIRECT_COMPONENT,
            EvidenceState.AVAILABLE,
            "current owner outcome" if succeeded else "GitHub unavailable",
        ),
    ]
    return ReferenceRun(behavior, tuple(paths.calls), tuple(evidence))
