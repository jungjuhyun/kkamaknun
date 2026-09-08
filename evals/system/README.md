# System Evaluation

## Ownership

This directory owns the framework-independent measurement contract, target observation boundaries, seed regression tasks, deterministic graders, and Actual ChatGPT Work UAT evidence protocol for the whole harness.

An independent owner is necessary because `tools/harness/PIPELINE.yaml` and `PLAYBOOK.md` own video planning and its Planning RED TEAM. Putting system evaluation there would mix targets, graders, and PASS meanings. Plans remain historical or executable plans rather than current measurement contracts.

This phase does not change the Work Project instruction, video-planning pipeline, Planning RED TEAM, locks, common rules, or current video content.

## Current implementation state

- Phase 0 measurement contract: implemented.
- Phase 1 seed fixtures and deterministic grader proof: implemented.
- Direct component target: implemented for controlled evidence.
- Future Inspect/Codex CLI target: schema only; not run.
- Actual ChatGPT Work target: semi-manual UAT protocol only.
- Inspect AI and Inspect SWE: `PREFERRED_FOR_PILOT`; not installed or adopted.
- Model graders and planning-quality graders: out of scope.

The exact completion claim for this phase is:

> framework-independent measurement contract + seed regression fixture + deterministic grader proof complete

## Status semantics

- `PASS`: every required assertion has observable same-target evidence and passes.
- `FAIL`: observable same-target evidence demonstrates a product or contract failure.
- `UNKNOWN`: required evidence is missing. It is never PASS.
- `INFRA_ERROR`: infrastructure prevented observation. It is not a product FAIL.
- `INVALID_FIXTURE`: the task, evidence, target, or grader setup is invalid.
- `NOT_RUN`: no trial was executed.

An assertion must set `on_missing_evidence` to `UNKNOWN`. Evidence from another target cannot grade the current target. Correct response wording does not prove an internal process occurred.

## Target boundaries

The machine-readable observation matrix is `observation_matrix.json`.

### Direct component

The grader may use controlled fixture inputs, structured process results, filesystem state, and git state. This is the only executable target in Phase 0-1.

### Future Inspect/Codex CLI

Only candidate evidence requirements are defined. Tool arguments, retrieval provenance, sandbox isolation, and log completeness remain unknown until the separate Phase 2 feasibility pilot.

### Actual ChatGPT Work

Only actual observable output, user-visible activity, and independently observable external state may be graded. The following are not assumed to exist:

- complete tool-call trace;
- retrieval query or result trace;
- personal-context invocation trace;
- Project instruction active-version API;
- clean-session reset API;
- connector fault injection;
- exact model or runtime pin.

If a required assertion depends on unavailable internal evidence, the assertion and trial are `UNKNOWN`. A Codex surrogate PASS never becomes a Work PASS.

## Project instruction provenance

`project_instruction.provenance` is required metadata. The content hash is optional.

- `VERIFIED`: a supported independent path confirms the active UI instruction. Requires exact text bytes, a SHA-256 content hash, and `active_ui_match=true`.
- `USER_SUPPLIED`: the hash identifies supplied text only. It is not evidence of the active UI version.
- `UNKNOWN`: no active version claim is made. An instruction content hash is forbidden.
- `NOT_APPLICABLE`: the target does not use a Work Project instruction.

A screenshot may have an `artifact_hash`; it is not an instruction `content_hash`.

## Critical gate

Critical 5/5 is an initial release gate, not proof of 100% reliability.

- Five valid trials must all PASS.
- `UNKNOWN` is a valid non-passing trial and fails the gate.
- `INFRA_ERROR`, `INVALID_FIXTURE`, and `NOT_RUN` do not count as valid trials.
- If five valid trials cannot be obtained, the gate is `BLOCKED`.
- Extra successes cannot average away a critical FAIL or UNKNOWN in the release run.

## Isolation profiles

`isolation_profiles.json` defines expectations and required probes. No Docker or Inspect execution is implemented in this phase. Docker use alone never establishes network isolation. Container, evaluator, model-provider, and out-of-sandbox custom code are separate boundaries.

## Actual Work semi-manual UAT protocol

Use `actual_work_uat_template.json` for each trial. Record:

- fresh chat and same-project status;
- known memory state;
- repo head;
- Project instruction provenance;
- contamination seed;
- final response;
- external GitHub state;
- repository mutation outcome;
- observable error or receipt;
- evaluator notes;
- isolation status and reset evidence.

Isolation status is one of:

- `CLEAN_VERIFIED`
- `CLEAN_PARTIAL`
- `CONTAMINATION_SEEDED`
- `UNKNOWN`

`CLEAN_VERIFIED` is invalid without supported reset evidence. A fresh chat alone is not sufficient.

## Seed regression tasks

- `REG-BOOTSTRAP-FALLBACK-001`: one failed GitHub path must not become GitHub-wide unavailability.
- `REG-PROVENANCE-CONTAMINATION-001`: an unrequested historical marker must not contaminate current output.
- `REG-HISTORICAL-RETRIEVAL-REQUIRED-001`: explicit historical requests must still retrieve and label history while preserving current-truth priority.

Production documents are not copied into the fixtures. The bootstrap fixture uses synthetic owner files and a synthetic immutable SHA. The historical fixture stores only the minimal marker required to reproduce the failure boundary.

## Repeatable validation

From the repository root:

```text
python -m evals.system.check
```

The command parses every task and fixture, validates observation and isolation data, validates the Work UAT template, runs deterministic grader proofs, checks PASS/FAIL/UNKNOWN/INFRA_ERROR/INVALID_FIXTURE classification, verifies critical-gate semantics, and performs cross-reference checks.

## Phase 2 boundary

Phase 2 may pilot Inspect AI and Inspect SWE only after this Phase 0-1 validation passes. The pilot must verify actual Codex CLI execution, version control, trace completeness, sandbox state, network boundaries by probe, epoch behavior, error classification, re-scoring, cost, and maintenance burden before dependency adoption.
