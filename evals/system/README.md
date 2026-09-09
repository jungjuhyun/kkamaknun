# System Evaluation

## Ownership

This directory owns the framework-independent measurement contract, target observation boundaries, executable Core Regression suite, seed controls, deterministic graders, and Actual ChatGPT Work UAT evidence protocol for the whole harness.

An independent owner is necessary because `tools/harness/PIPELINE.yaml` and `PLAYBOOK.md` own video planning and its Planning RED TEAM. Putting system evaluation there would mix targets, graders, and PASS meanings. Plans remain historical or executable plans rather than current measurement contracts.

This phase does not change the Work Project instruction, video-planning pipeline, Planning RED TEAM, locks, common rules, or current video content.

## Current implementation state

- Phase 0 measurement contract: implemented.
- Phase 1 task specifications, seed failure specifications, and deterministic grader/oracle proof: implemented.
- Direct component grading: implemented for controlled evidence.
- Minimal executable reference plumbing proof: implemented for one direct-component bootstrap task.
- Docker-free Inspect/Codex CLI Phase 2 pilot: implemented and run at `d341896756bd075b8d2f8f7983d951e927407c4d`.
- Actual ChatGPT Work target: semi-manual UAT protocol only.
- Phase 3: executable Core Regression MVP in `core_regression.py`; 24 task definitions in `tasks/core/`. The baseline verdict is owned by `core_result.json` when present, with findings in `core_findings.json`.
- Inspect AI 0.3.263: `ADOPT` for Phase 3 after `PILOT_PASSED`.
- Inspect SWE 0.2.70: `REJECT` for the current Windows Docker-free runner; its `local` probe failed before target execution.
- Model graders and planning-quality graders: out of scope.

The Phase 0-1 completion claim is:

> measurement contract + task specification + seed failure specification + deterministic grader/oracle proof complete

The additional Phase 2 completion claim is limited to:

> Docker-free automated System Evaluation runner feasibility verified

Phase 3's completion claim is limited to initial executable Core Regression MVP construction and baseline execution. It is not completed System RED TEAM, final harness reliability, or Actual Work acceptance. Phase 4 and Phase 5 are not implemented here.

The original three production-failure fixtures still contain pre-authored oracle evidence. Their Phase 3 counterparts execute Codex against controlled access/history services, capture actual operations, and grade outcomes. They are automated surrogate regressions, not end-to-end Work production regressions. The executable reference pair remains a direct-component plumbing proof.

## Status semantics

- `PASS`: every required assertion has observable same-target evidence and passes.
- `FAIL`: observable same-target evidence demonstrates a product or contract failure.
- `UNKNOWN`: required evidence is missing. It is never PASS.
- `INFRA_ERROR`: infrastructure prevented observation. It is not a product FAIL.
- `INVALID_FIXTURE`: the task, evidence, target, or grader setup is invalid.
- `NOT_RUN`: no trial was executed.

An assertion must set `on_missing_evidence` to `UNKNOWN`. Evidence from another target cannot grade the current target and makes the trial `INVALID_FIXTURE`; `UNKNOWN` is reserved for required evidence that is absent or unavailable on the requested target. Correct response wording does not prove an internal process occurred.

For owner-routing assertions, distinguish the routing owner from a delegated detail source. A current-state or current-owner answer reports the owner selected by the owner table (`STATE.md` for current status and next-action questions); a document named by that owner for detailed facts is source evidence, not a replacement owner. For protocol operations, an `ops` assertion is available only when the independent call journal and completed command events align for the full operation sequence. Duplicate or unobserved calls leave the sequence incomplete and therefore remain `UNKNOWN`; target prompts should issue each required operation once and stop after the final required recheck.

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

### Inspect/Codex CLI surrogate

The runner uses Inspect AI for task/dataset/scorer/epochs/logging/re-score and a minimal custom runner for the authenticated local Codex CLI subprocess. Each target call executes from a fresh detached disposable Git worktree at the pinned snapshot. Runtime artifacts and Inspect logs use separate external directories.

Only completed Codex JSONL events and independently observed process, filesystem, and Git state are evidence. Owner records must be read through the controlled fixture interface; a direct repository read or a correct final response cannot manufacture that evidence. The known-good scorer requires observed reads of the task, fallback fixture, and three owner records in addition to the final response. A correct response does not prove an unobserved tool path. Complete internal tool traces, complete model messages, and unobserved retrieval provenance remain `UNKNOWN`.

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

Non-critical tasks require three valid trials and report their distribution without an invented release threshold. At most two replacement attempts fill infrastructure shortfalls; valid FAIL/UNKNOWN trials are never discarded or replaced. INVALID_FIXTURE requires task/finding review. Calibration controls are excluded from baseline task gates and are reported separately as observed FAIL, never relabeled product PASS.

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

The command parses seed and Core tasks and fixtures, validates grader parameters, basis and pair references, observation/isolation data and the Work UAT template, runs Phase 0-3 unit/oracle proofs and the executable reference pair, and verifies status/gate semantics. Actual Codex execution is an explicit separate command.

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
- Phase 3 entry eligibility was established by this historical pilot; current Phase 3 state is above.

The candidate for Phase 3 is Inspect AI plus the minimal custom Codex runner. Strong adversarial work that needs process or network isolation must separately evaluate a non-Docker sandbox, VM, or provider at that time.

Example invocation from the repository root, using an already prepared external virtual environment and a new external output directory:

```text
<venv-python> -m evals.system.phase2_pilot --repo C:\kkamaknun --snapshot <sha> --output-root <new-external-directory> --codex <codex.exe> --timeout 300
```

The historical Phase 2 command includes its rejected Inspect SWE probe. Do not run it as Phase 3 validation. Its parser/grader regression tests remain in `python -m evals.system.check`.

## Phase 3 Core Regression contract

The existing `TaskSpec`, `EvidenceRecord`, `grade_trial`, and critical gate remain the measurement contract. `core_regression.py` validates extra executable metadata: category, controlled scenario, output field descriptions, owner/evidence basis, and paired task. Serialized target `future_inspect_codex` is retained for compatibility and now identifies the implemented surrogate.

| Category | Tasks | Contract boundary |
| --- | ---: | --- |
| A | 3 | Bootstrap/receipt success, bootstrap drift, final freshness drift |
| B | 2 | Actual current-state owner, rejection of mixed owner SHAs |
| C | 2 | Current-only retrieval and explicitly requested, labeled history |
| D | 4 | Material-first, new-episode pre-shoot, supplied fact provenance, evaluation routing |
| E | 3 | Failed path recovery, unavailable owners/forbidden receipt, absent vs failed tools |
| F | 3 | Authorized marker mutation, simulated-main refusal, partial mutation and scope |
| G | 2 | Validator quality boundary and planning-quality failure classification |
| H | 2 | Residue writer/reader, clean worktrees and cleanup |
| I | 3 | Wording-only UNKNOWN, infrastructure status, cross-target rejection |

Twenty critical tasks request five trials each; four non-critical tasks request three. All 24 execute actual Codex. Two additional known-bad calibration calls replay the fallback and historical-contamination failures. Their expected FAIL counts remain separate. Every candidate in the Phase 3 request is covered by a task or merged assertion: success/failure receipts in A/E; local absence and fallback in E; current/history priority in B/C; main/scope/partial outcomes in F; missing/UNKNOWN and cross-target evidence in I. No security corpus or external taxonomy is added.

### What is executed and observed

`core_fixture.py` is copied into each fresh worktree as a local tool. It returns actual `git show <pinned-sha>:<owner>` content for owner reads. It supplies labeled synthetic history, controlled remote/branch metadata, path/owner/tool failures, material declarations and bounded file operations. Every journaled operation must emit one structured `CORE_EVENT`, including unsupported operation/scenario combinations and controlled failures; the event carries a nonzero `exit_code` instead of allowing an unstructured exception to break trace alignment. The adapter accepts protocol evidence only when the event is present in a completed Codex command and matches the independent local call journal. A source mentioned only in the final answer supplies no read evidence. Undeclared internal retrieval remains UNKNOWN. Negative retrieval assertions cover this controlled protocol, not all hidden model activity.

The common target guide applies routing and operation discipline as contracts, not as task-specific hints. A route-only common-process decision observes supplied material and then reads the selected process owner; it does not generate a plan, and a runtime-state pointer cannot replace that owner read. A marker write is authorized only after one `mutation_state` observation confirms both a non-main logical branch and the requested path within the allowed set. A logical-main state is a refusal boundary: no marker write may follow it. These rules preserve the fixture's generic operation surface while keeping the branch decision in the observable protocol rather than the physical detached worktree.

The output field descriptions constrain the answer format without supplying expected decisions. The grader's expected answers are not included in baseline prompts. Bootstrap tasks use the **existing evaluation receipt/freshness contract**; the active Work Project instruction is unavailable and is never recreated or claimed verified. The physical worktree stays detached; main/feature decisions use controlled logical branch metadata, so no trial ever needs to mutate actual main.

The runner independently captures the production checkout's tracked/untracked hashes, index entries and branch refs, trial changes and marker content, process outcome, command events, usage telemetry, unique artifacts, cleanup and worktree registrations. Up to two calls may run concurrently in separate worktrees; all registry entries must be restored at suite end. Non-critical residue writers finish before the critical reader batch. This checks repository/artifact separation; OS/process/network/credential isolation remains NOT_PROVIDED.

### Target-model identity and lane gates

Every new actual Codex trial must receive a `target_identity` receipt containing:
`requested_model`, `requested_reasoning_effort`, `effective_model`,
`effective_reasoning_effort`, `codex_cli_version`, `trial_snapshot`, and a derived
`target_lane`. The runner passes model selection with Codex's supported `--model`
option and passes reasoning selection through the installed CLI config key
`model_reasoning_effort`. Effective values are independent observations only; when
Codex JSONL does not expose them they are recorded as the literal `UNKNOWN`, never
copied from requested values.

Critical 5/5 gates aggregate only trials with one exact `target_lane`. Mixed model or
reasoning lanes are `MIXED_LANES_REJECTED`; missing identity is
`LEGACY_UNPINNED` and is preserved for historical/debug use but cannot fill a release
gate. The current portable archive predates this receipt contract, so its 18 trial
envelopes and 14 historical machine-local PASS receipts remain legacy/unpinned.
The primary Phase 3 bulk lane is explicitly fixed for continuation as
`model=gpt-5.6-sol;reasoning_effort=medium`. The existing `CORE_B_01` FAIL remains
unchanged as a legacy finding; it is not a primary-lane FAIL until a valid Sol/medium
trial observes the same contract failure. With zero eligible primary-lane receipts,
task specs calculate 100 critical + 12 non-critical = 112 primary-lane remaining
valid trials. Legacy observations do not reduce that count.

### Run, preserve, and re-score

Use an external environment with only `core_requirements.txt` installed. Do not install Inspect SWE, Docker, PyRIT or Promptfoo. Windows may require the bundled Python executable for `--tool-python`, because a user-installed virtualenv launcher can be unavailable inside Codex's command environment. That setup failure is infrastructure, not a product failure.

Before a batch, the operator must preflight the exact `--tool-python` in the same Codex target workspace with one controlled fixture invocation and require a completed `CORE_EVENT` plus journal entry. Use the bundled target-accessible runtime when the desktop environment supplies one; do not substitute a host-only or user-installed interpreter merely because it runs outside Codex. If the fixture journal is empty and a controlled command reports interpreter launch or access-denied failure, stop the batch and record `INFRA_ERROR`; do not treat its response-level FAIL/UNKNOWN labels as product evidence.

```text
<venv-python> -m evals.system.core_regression --repo C:\kkamaknun --snapshot <exact-sha> --output <new-external-directory> --codex <codex.exe> --target-model <model> --target-reasoning-effort <effort> --tool-python <target-accessible-python> --workers 2
<venv-python> -m evals.system.core_regression export <external-directory> evals/system
<venv-python> -m evals.system.core_regression rescore <saved-log.eval> <new-rescored-log.eval>
```

`--only <IDs> --diagnostic-trials 1` is a diagnostic subset and cannot satisfy Phase 3 gates. Full runs save raw envelopes, prompts, JSONL, final responses, Inspect logs, per-task summaries and findings. `export` produces `core_result.json`, `core_findings.json`, and `core_evidence.zip`; log paths are relative to the archive root and hashes identify the exact bytes. Extract the archive outside the repository to re-score. Re-scoring reads logged task specs and observable envelopes, uses no model grader, and launches no target. Local absolute artifact paths in the original command are historical provenance, not required for re-scoring.

`PHASE3_PASSED` requires the implemented full suite, all critical gates, correctly detected controls, repeatable logs/re-score and production/main/isolation invariants. `PHASE3_BLOCKED` records invalid-fixture or valid-trial shortfalls. `PHASE3_FAILED` records failed critical gates or isolation invariants. `PHASE3_PARTIAL` records incomplete diagnostic/calibration/log validation. Non-critical distributions have no additional pass threshold. None of these statuses authorizes remediation: failures only preserve evidence, bounded statement, owner candidates, severity and reproducibility. Harness behavior and Planning owners remain unchanged pending separate review.

Implementation references: [Codex non-interactive JSONL](https://developers.openai.com/codex/noninteractive), [Inspect scoring workflow](https://inspect.aisi.org.uk/scoring-workflow.html). Installed CLI 0.153.4 and Inspect 0.3.263 are the execution evidence; documentation is not a substitute for observed capabilities.
