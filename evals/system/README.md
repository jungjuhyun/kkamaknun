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
- Docker-free Inspect/Codex CLI Phase 2 pilot: implemented and run at `d341896756bd075b8d2f8f7983d951e927407c4d`.
- Actual ChatGPT Work target: semi-manual UAT protocol only.
- Inspect AI 0.3.263: `ADOPT` as the Phase 3 runner candidate after `PILOT_PASSED`.
- Inspect SWE 0.2.70: `REJECT` for the current Windows Docker-free runner; its `local` probe failed before target execution.
- Model graders and planning-quality graders: out of scope.

The exact completion claim for this phase is:

> measurement contract + task specification + seed failure specification + deterministic grader/oracle proof complete

The additional Phase 2 completion claim is limited to:

> Docker-free automated System Evaluation runner feasibility verified

It is not a completed System RED TEAM and does not enter Phase 3.

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

### Inspect/Codex CLI Phase 2 pilot

The candidate runner uses Inspect AI for task/dataset/scorer/epochs/logging/re-score and a minimal custom runner for the authenticated local Codex CLI subprocess. Each target call executes from a fresh detached disposable Git worktree at the pinned snapshot. Runtime artifacts and Inspect logs use separate external directories.

Only completed Codex JSONL events and independently observed process, filesystem, and Git state are evidence. The known-good scorer requires observed reads of the task, fallback fixture, and three owner records in addition to the final response. A correct response does not prove an unobserved tool path. Complete internal tool traces, complete model messages, and unobserved retrieval provenance remain `UNKNOWN`.

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

`isolation_profiles.json` defines expectations and required probes. The Phase 2 profile is `disposable_worktree`. It offers repository working-tree state separation and trial artifact separation only. It does not provide OS process, host filesystem, network, credential, evaluator-process, or model-provider isolation.

Inspect's built-in `local` environment is explicitly a local filesystem **with no sandbox**. It is never described as isolation evidence here. Docker is neither used nor required for the Phase 2 pilot. Existing container profiles remain available for other future evaluation designs but are not Phase 2 prerequisites or success criteria.

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

## Phase 2 Docker-free feasibility result

The machine-readable result is `phase2_pilot_result.json`; the repeatable runner is `phase2_pilot.py`; exact pilot-only dependency pins are in `phase2_pilot_requirements.txt`.

The pilot executed three benign task types:

1. `REG-BOOTSTRAP-FALLBACK-001` known-good behavior for five real Codex epochs: 5/5 `PASS`.
2. The same task's explicit known-bad behavior: actual Codex execution classified `FAIL`.
3. One controlled untracked-file mutation: the change appeared only in its disposable worktree and was captured before cleanup.

All seven Codex subprocesses exited zero without provider errors or timeouts. Every trial started and ended at the pinned SHA, used a unique artifact directory, left the production checkout and `main` unchanged, showed no cross-trial residue, and removed its worktree without requiring prune. Inspect wrote three eval logs and deterministic re-scoring reproduced the results without re-running the targets.

The installed Inspect SWE Codex integration was probed separately with Inspect `local`, recorded as `NO_SANDBOX`. On Windows it produced a sample-level `SandboxInjectionError` (`WinError 2`) before target execution. Installed source also uses Linux platform detection and `bash`. This rejects Inspect SWE for the current Windows Docker-free runner; it does not reject Inspect AI core or claim Inspect SWE requires Docker in every environment.

The decision is:

- Pilot: `PILOT_PASSED`.
- Inspect AI: `ADOPT` as the Phase 3 runner candidate.
- Inspect SWE: `REJECT` for this Windows Docker-free runner.
- Phase 3: eligible but not started.

The candidate for Phase 3 is Inspect AI plus the minimal custom Codex runner. Strong adversarial work that needs process or network isolation must separately evaluate a non-Docker sandbox, VM, or provider at that time.

Example invocation from the repository root, using an already prepared external virtual environment and a new external output directory:

```text
<venv-python> -m evals.system.phase2_pilot --repo C:\kkamaknun --snapshot <sha> --output-root <new-external-directory> --codex <codex.exe> --timeout 300
```
