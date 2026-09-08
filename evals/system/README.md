# System Evaluation

## Ownership

This directory owns the framework-independent measurement contract, target observation boundaries, seed regression tasks, deterministic graders, and Actual ChatGPT Work UAT evidence protocol for the whole harness.

An independent owner is necessary because `tools/harness/PIPELINE.yaml` and `PLAYBOOK.md` own video planning and its Planning RED TEAM. Putting system evaluation there would mix targets, graders, and PASS meanings. Plans remain historical or executable plans rather than current measurement contracts.

This phase does not change the Work Project instruction, video-planning pipeline, Planning RED TEAM, locks, common rules, or current video content.

## Current implementation state

- Phase 0 measurement contract: implemented.
- Phase 1 task specifications, seed failure specifications, and deterministic grader/oracle proof: implemented.
- Direct component grading: implemented for controlled evidence.
- Minimal executable reference plumbing proof: implemented for one direct-component bootstrap task.
- Future Inspect/Codex CLI target: schema only; not run.
- Actual ChatGPT Work target: semi-manual UAT protocol only.
- Inspect AI and Inspect SWE: `PREFERRED_FOR_PILOT`; not installed or adopted.
- Model graders and planning-quality graders: out of scope.

The exact completion claim for this phase is:

> measurement contract + task specification + seed failure specification + deterministic grader/oracle proof complete

The production-failure fixtures contain pre-authored oracle evidence. They are not yet end-to-end production regressions because they do not execute an actual Work or Codex target and capture its behavior. The executable reference pair proves only that the local task → controlled behavior → evidence capture → grader plumbing distinguishes known-good from known-bad behavior.

## Status semantics

- `PASS`: every required assertion has observable same-target evidence and passes.
- `FAIL`: observable same-target evidence demonstrates a product or contract failure.
- `UNKNOWN`: required evidence is missing. It is never PASS.
- `INFRA_ERROR`: infrastructure prevented observation. It is not a product FAIL.
- `INVALID_FIXTURE`: the task, evidence, target, or grader setup is invalid.
- `NOT_RUN`: no trial was executed.

An assertion must set `on_missing_evidence` to `UNKNOWN`. Evidence from another target cannot grade the current target. Correct response wording does not prove an internal process occurred.

Fixture validity is trial-wide. Any assertion with `INVALID_FIXTURE`, including an optional diagnostic assertion, makes the trial `INVALID_FIXTURE`. Optional `FAIL`, `UNKNOWN`, and `INFRA_ERROR` remain diagnostic and do not change a trial whose required assertions all PASS. Required assertion status keeps the product/observation semantics above.

## Deterministic grader parameter contracts

Every registered grader has required keys, allowed keys, and value-shape validation. Task loading rejects missing, empty, unexpected, ambiguous, or ill-typed parameters as a schema error; runtime grading also converts malformed wiring to `INVALID_FIXTURE` rather than PASS or product FAIL.

- token and value graders require non-empty explicit lists;
- snapshot, branch, and head graders require explicit expected values;
- freshness requires `expected_sha`;
- source provenance requires non-empty `required_sources`;
- validator result requires both expected exit code and result;
- git diff requires an explicit dirty-state boolean;
- modified files requires `mode`, `allowed`, and `forbidden`. `allowlist` rejects every path outside `allowed`; `forbid_only` requires `allowed=[]`, a non-empty forbidden list, and permits other paths;
- bootstrap receipt requires `required_on_success` or `forbidden_on_failure`.

For `required_on_success`, PASS requires `bootstrap_succeeded=true`, a receipt, required owner evidence, and verified final freshness. For `forbidden_on_failure`, PASS requires `bootstrap_succeeded=false` and no receipt. Failure behavior is never inferred from receipt absence; it must select the explicit failure contract.

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

## Seed failure specifications

- `REG-BOOTSTRAP-FALLBACK-001`: one failed GitHub path must not become GitHub-wide unavailability.
- `REG-PROVENANCE-CONTAMINATION-001`: an unrequested historical marker must not contaminate current output.
- `REG-HISTORICAL-RETRIEVAL-REQUIRED-001`: explicit historical requests must still retrieve and label history while preserving current-truth priority.

Production documents are not copied into the fixtures. The bootstrap fixture uses synthetic owner files and a synthetic immutable SHA. The historical fixture stores only the minimal marker required to reproduce the failure boundary.

These three task/fixture pairs prove deterministic oracles against known evidence. They do not yet prove that an executable Work/Codex target produces the required evidence.

## Executable reference plumbing proof

`reference_target.py` runs known-good and known-bad bootstrap behaviors against the same `REG-BOOTSTRAP-FALLBACK-001` task and controlled environment. The behaviors actually invoke a failing first access path; only the known-good behavior invokes the successful fallback. Both runs capture evidence and are graded through the normal trial path, producing PASS and FAIL respectively.

This is not an agent framework and is not a proxy for ChatGPT Work, Codex CLI, model behavior, connector behavior, or real GitHub reliability. It proves only the framework-independent evaluation plumbing before a Phase 2 runner pilot.

## Repeatable validation

From the repository root:

```text
python -m evals.system.check
```

The command parses every task and fixture, validates every grader parameter contract, validates observation and isolation data, validates the Work UAT template, runs deterministic grader/oracle proofs and the executable reference pair, checks PASS/FAIL/UNKNOWN/INFRA_ERROR/INVALID_FIXTURE classification, verifies critical-gate semantics, and performs cross-reference checks.

## Phase 2 boundary

Phase 2 may pilot Inspect AI and Inspect SWE only after this Phase 0-1 validation and the framework-independent reference plumbing proof pass. The pilot must verify actual Codex CLI execution, version control, trace completeness, sandbox state, network boundaries by probe, epoch behavior, error classification, re-scoring, cost, and maintenance burden before dependency adoption.
