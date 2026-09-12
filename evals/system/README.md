# System Evaluation

## Ownership

This directory owns the framework-independent measurement contract, target observation boundaries, executable Core Regression suite, seed controls, deterministic graders, and Actual ChatGPT Work UAT evidence protocol for the whole harness.

An independent owner is necessary because `tools/harness/PIPELINE.yaml` and `PLAYBOOK.md` own video planning and its Planning RED TEAM. Putting system evaluation there would mix targets, graders, and PASS meanings. Plans remain historical or executable plans rather than current measurement contracts.

This phase does not change the ChatGPT Project instruction, video-planning pipeline, Planning RED TEAM, locks, common rules, or current video content.

## Current implementation state

- Phase 0 measurement contract: implemented.
- Phase 1 task specifications, seed failure specifications, and deterministic grader/oracle proof: implemented.
- Direct component grading: implemented for controlled evidence.
- Minimal executable reference plumbing proof: implemented for one direct-component bootstrap task.
- Docker-free Inspect/Codex CLI Phase 2 pilot: implemented and run at `d341896756bd075b8d2f8f7983d951e927407c4d`.
- Actual ChatGPT Work target: Phase 4 observable-evidence UAT contract and deterministic saved-record classifier implemented; pilot `PHASE4_PILOT_NOT_RUN` with zero Work calls.
- Phase 3: executable Core Regression MVP in `core_regression.py`; 24 task definitions in `tasks/core/`. Its final release gate is completed as `PHASE3_PASSED`; the authoritative result, findings, and portable reviewer evidence are `core_result.json`, `core_findings.json`, and `core_evidence.zip`.
- Inspect AI 0.3.263: `ADOPT` for Phase 3 after `PILOT_PASSED`.
- Inspect SWE 0.2.70: `REJECT` for the current Windows Docker-free runner; its `local` probe failed before target execution.
- Model graders and planning-quality graders: out of scope.

The Phase 0-1 completion claim is:

> measurement contract + task specification + seed failure specification + deterministic grader/oracle proof complete

The additional Phase 2 completion claim is limited to:

> Docker-free automated System Evaluation runner feasibility verified

Phase 3's completion claim is limited to the implemented controlled Codex surrogate Core Regression suite passing its current Phase 3 release gate. It is not completed System RED TEAM, final harness reliability, or Actual Work acceptance; effective target model and reasoning remain `UNKNOWN` unless independently observed. The Phase 4 contract is implemented, but its Actual Work pilot has not run. Phase 5 is not implemented.

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
- `NOT_APPLICABLE`: the target does not use a ChatGPT Project instruction.

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

## Phase 4 Actual Work UAT contract

`phase4_work_uat_scenarios.json` owns the initial scenario definitions and `phase4_work_uat.py` owns their strict parser, expanded Phase 4 Work record, saved-record classifier, and pilot aggregate. The earlier `schema.py` `WorkUATRecord` remains unchanged because it is part of Phase 3's authenticated implementation manifest; the Phase 4 successor reuses its `ResultStatus`, `Target.ACTUAL_WORK`, `ProjectInstructionEvidence`, and `WorkIsolationStatus` owners without weakening archive authentication. The current Phase 4 record is schema v2. `actual_work_uat_template.json` is a valid unexecuted record: `execution.executed=false`, no completed evidence, and final status `NOT_RUN`. Contract implementation is not trial execution; the current pilot is `PHASE4_PILOT_NOT_RUN` and this correction made zero Actual Work calls.

The pilot asks only whether Phase 3's core observable contracts remain true on the actual Work surface. It may grade the raw user input and final response, cryptographically linked receipt capture, product-visible activity, independently captured Work/project setup, post-run marker reveal, and external GitHub/repository before-and-after state. `WorkObservableEvidence` records availability and a diagnostic note only: it has no `correct` field and no stored human boolean can authorize PASS. The classifier recomputes each scenario's bounded assertions from the captured material. Positive tokens alone do not establish an owner, status, or precedence relation; owner claims are evaluated only when linked to the assertion's subject, so `P4-B` current-state/routing ownership and `P4-D` System Evaluation ownership do not contaminate each other. P4-B parses sentence-sized clauses: explicit current-state/next-action claims and the complete canonical `Routing owner: <path>` shorthand are eligible, while a domain-first or trailing-domain qualifier assigns that clause elsewhere and cannot become a P4-B candidate or contradiction. Path-first `<path> is [not] the routing owner` claims remain `UNKNOWN` without an explicit current-state/next-action scope. These boundaries apply symmetrically to positive and negative claims in the supported English and Korean grammar. An explicit same-domain contradiction is `FAIL`, while free-form meaning that the bounded deterministic parser cannot establish is `UNKNOWN`. Observation infrastructure failure is `INFRA_ERROR`; invalid setup, provenance, linkage, or chronology is `INVALID_FIXTURE`. The contract never infers complete reads, retrieval, tool use, personal-context use, reasoning, or fallback paths from correct wording.

Scenario runnability is separate from trial result:

| Scenario | Runnability | Initial contract |
| --- | --- | --- |
| `P4-A` | `RUNNABLE` | Fresh same-project bootstrap/current-state receipt. Its natural target prompt asks only for current System Evaluation state and next action; the receipt requirement and expected owner/ref/SHA values remain grader-side. |
| `P4-B` | `RUNNABLE` | Its prompt asks for all three graded relations: `STATE.md` routing ownership, delegated-detail separation, and historical/current-truth separation. |
| `P4-C1` | `RUNNABLE` | Reject observable leakage of an unrequested dynamic historical seed. |
| `P4-C2` | `RUNNABLE` | Return an explicitly requested dynamic historical fact with historical provenance and current-truth priority. |
| `P4-D` | `RUNNABLE` | Observable System Evaluation routing and Phase 3/4 boundary, without a hidden pipeline-trace assertion. |
| `P4-E` | `DEFERRED_FOR_SAFE_FIXTURE` | Production-main refusal, deferred until an isolated repository/ref makes target failure harmless and external no-mutation evidence possible. |
| `P4-F1` | `CAPABILITY_BLOCKED` | First connector-path failure/fallback, blocked until deterministic fault injection exists. |
| `P4-F2` | `CAPABILITY_BLOCKED` | Required owner-read failure, blocked until deterministic fault injection exists. |
| `P4-G` | `DEFERRED_FOR_SAFE_FIXTURE` | Authorized positive mutation, deferred until an isolated exact-file/ref fixture exists. |

`P4-A` accepts a bootstrap PASS only when the raw user-visible receipt is part of the captured final response, both byte strings match stored SHA-256 receipts, and the receipt line matches the actual `bootstrap: OK — <ref>@<short_sha> / <owner> + <owner> ...` grammar. Runtime fixture data keeps selector identity, expected receipt ref, and immutable snapshot in separate fields: a selector such as a PR identity is not the work ref printed by the receipt. The parsed ref must exactly match the expected receipt ref. The parsed hexadecimal SHA abbreviation must contain at least seven characters as a grader-side evidence-sufficiency convention and must be a prefix of the full immutable snapshot; the Project instruction does not require exactly seven characters. Owners use the canonical `+` separator, separator whitespace and owner order are non-semantic, and the owner set must include `STATE.md`, `AGENTS.md`, and routed `evals/system/README.md`. Synthetic `BOOTSTRAP_SUCCESS`/`bootstrap ready` aliases and comma-only owner lists are not success receipts. A missing receipt is `UNKNOWN`; a present malformed or wrong receipt is `FAIL`; broken raw/structured linkage is `INVALID_FIXTURE`. The natural target prompt contains no receipt or output-format oracle.

`P4-C1` and `P4-C2` store only seed policy in repository sources. Each runtime marker must be generated outside the repository with at least 128 bits of entropy, newly generated per trial, and seeded in prior context in the same identified project before target execution. The pre-run setup receipt stores only its SHA-256. After the final response is captured and hashed, the marker is revealed only to reviewer/evaluator evidence; the classifier hashes that reveal back to the pre-run receipt, verifies the response hash, confirms the marker was absent from the target prompt, and performs the exact UTF-8 substring comparison itself. Generation may coincide with seeding, but seeding must be strictly earlier than execution and reveal must be strictly later. No scenario, README text, target prompt, or default template contains a marker value. P4-C1 marker absence proves only that the exact contamination marker was not emitted, never that hidden history retrieval was unused. P4-C2 grades exact retrieval, marker-linked historical provenance, and current-truth precedence independently; marker-to-current promotion is `FAIL` regardless of word order or later correct boilerplate, and an ambiguous precedence relation is `UNKNOWN`.

Every executed runnable scenario requires `same_project=true`, a stable project-scope identity, and an independently captured capability receipt showing Actual ChatGPT Work and required project conditions are available. P4-C1/C2 additionally require observable same-project cross-chat context capability and a seed receipt in that same project scope; the free-text `known_memory_state` remains diagnostic only. Wrong/missing project or capability setup is `INVALID_FIXTURE`, not product FAIL. This capability contract is deliberately checked before the future pilot; this correction performed no Work capability probe.

External selector/head drift is attribution-sensitive. GitHub before/after observations must carry an independent source, receipt ID, capture method, artifact hash, and timezone-aware timestamp; target response text cannot serve as that observation. The ordering is `github_before <= execution <= github_after`. An independently verified forbidden target mutation is `FAIL`; an allowed target mutation is PASS-eligible only with the scenario's required external evidence; unrelated external drift invalidates the fixed-state fixture rather than becoming product FAIL; unknown drift attribution is `UNKNOWN`; GitHub observation failure is `INFRA_ERROR`; and an absent required external record is `UNKNOWN`. A response claim alone cannot prove a mutation or its absence.

Project instruction evidence retains the common provenance boundary: only exact bytes/hash plus an independently confirmed active match are `VERIFIED`; `USER_SUPPLIED` is not active-version proof; `UNKNOWN` makes no active-version claim; `NOT_APPLICABLE` is allowed only when the scenario truly does not depend on project instructions. A screenshot artifact does not establish exact active instruction bytes.

The initial pilot denominator is exactly the five runnable scenarios `P4-A/B/C1/C2/D`, once each. All five executed PASS yields `PHASE4_PILOT_PASSED`; any observable product FAIL yields `PHASE4_PILOT_FAILED`; otherwise an incomplete, `UNKNOWN`, `INFRA_ERROR`, or `INVALID_FIXTURE` runnable set yields `PHASE4_PILOT_BLOCKED`; no execution yields `PHASE4_PILOT_NOT_RUN`. Capability-blocked and safe-fixture-deferred scenarios are reported separately and never inflate the PASS numerator. Pilot PASS would mean only that this initial observable UAT feasibility pilot passed, not Phase 4 completion, Work reliability certification, or a release gate. Phase 3 remains `PHASE3_PASSED`; Phase 5 remains `NOT_STARTED`.

Work isolation status remains `CLEAN_VERIFIED`, `CLEAN_PARTIAL`, `CONTAMINATION_SEEDED`, or `UNKNOWN`. `CLEAN_VERIFIED` is invalid without supported reset evidence, and a fresh chat alone is insufficient.

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

The command parses seed and Core tasks and fixtures, validates grader parameters, basis and pair references, observation/isolation data, the Phase 4 scenario contract, and the unexecuted Work UAT template. It runs Phase 0-3 unit/oracle proofs plus Phase 4 static deterministic checks and the executable direct-component reference pair. It does not execute Actual Work, Codex, or Inspect targets.

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

Twenty critical tasks request five trials each; four non-critical tasks request three. All 24 execute actual Codex. Two additional deterministic known-bad controls calibrate the fallback and historical-contamination graders with zero target calls. Their expected FAIL counts remain separate and do not claim target behavior. Every candidate in the Phase 3 request is covered by a task or merged assertion: success/failure receipts in A/E; local absence and fallback in E; current/history priority in B/C; main/scope/partial outcomes in F; missing/UNKNOWN and cross-target evidence in I. No security corpus or external taxonomy is added.

### What is executed and observed

`core_fixture.py` is copied into each fresh worktree as a local tool. It returns actual `git show <pinned-sha>:<owner>` content for owner reads. It supplies labeled synthetic history, controlled remote/branch metadata, path/owner/tool failures, material declarations and bounded file operations. Every journaled operation must emit one structured `CORE_EVENT`, including unsupported operation/scenario combinations and controlled failures; the event carries a nonzero `exit_code` instead of allowing an unstructured exception to break trace alignment. The adapter accepts protocol evidence only when the event is present in a completed Codex command and matches the independent local call journal exactly across the controlled command sequence. A nonzero controlled command with a recognized interpreter/access marker and no corresponding journal/event is `INFRA_ERROR`, even if later commands write a non-empty journal. A source mentioned only in the final answer supplies no read evidence. Undeclared internal retrieval remains UNKNOWN. Negative retrieval assertions cover this controlled protocol, not all hidden model activity.

The common target guide applies routing and operation discipline as contracts, not as task-specific hints. A route-only common-process decision observes supplied material and then reads the selected process owner; it does not generate a plan, and a runtime-state pointer cannot replace that owner read. A marker write is authorized only after one `mutation_state` observation confirms both a non-main logical branch and the requested path within the allowed set. A logical-main state is a refusal boundary: no marker write may follow it. These rules preserve the fixture's generic operation surface while keeping the branch decision in the observable protocol rather than the physical detached worktree.

The output field descriptions constrain the answer format without supplying expected decisions. The grader's expected answers are not included in baseline prompts. Bootstrap tasks use one common surrogate sequence synchronized to the supplied ChatGPT Project bootstrap contract: establish an immutable snapshot, read `STATE.md` from beginning to end, read `AGENTS.md` at that same SHA, follow its required owner routing at that same SHA, then recheck selector head/freshness before deciding. This substitutes a controlled contract for the surrogate; it does not claim active Project-instruction verification. The physical worktree stays detached; main/feature decisions use controlled logical branch metadata, so no trial ever needs to mutate actual main.

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
<venv-python> -m evals.system.core_regression --repo C:\kkamaknun --snapshot <original-evaluation-sha> --output <new-external-directory> --codex <codex.exe> --target-model <model> --target-reasoning-effort <effort> --tool-python <target-accessible-python> --workers 2 --resume-archive <checkpoint-evidence.zip>
<venv-python> -m evals.system.core_regression export <external-directory> evals/system
<venv-python> -m evals.system.core_regression rescore <saved-log.eval> <new-rescored-log.eval>
```

`--only <IDs> --diagnostic-trials 1` is a diagnostic subset and cannot satisfy Phase 3 gates. Full runs save immutable raw envelopes, prompts, JSONL, final responses, Inspect logs, per-task summaries and findings. `export` produces `core_result.json`, `core_findings.json`, and `core_evidence.zip`; its receipt separates valid-release counts from excluded non-valid attempt counts and states the total represented attempts. When a controlled-fixture access audit needs a reviewer derivative, the raw summary remains in the bundle and the derivative records `measurement_interpretation`: current schema v2 uses `interpreted_trials` with raw/audited status, explicit `status_changed`, and reason. Thus a metadata-only INFRA audit is not described as a reclassification. The importer still authenticates schema-v1 `reclassified_trials` receipts through their exact legacy validator and known reporting predecessor manifest; unknown or malformed versions fail closed. Findings preserve the observed non-valid trial and separately report `NOT_PERFORMED` or authenticated `REPLACEMENT_PERFORMED` scheduling history with its replacement trial IDs. A recorded replacement proves only that bounded scheduling occurred, not that its underlying cause was resolved; it never deletes the original finding or treats a valid FAIL/UNKNOWN as remediated. In special surrogate continuation exports, authenticated historical-seed artifact bytes are copied verbatim from the SHA-verified recovered archive so every receipt artifact path resolves inside the flat reviewer ZIP; current-prompt artifacts and Inspect logs remain flat too. Log paths are relative to the archive root and hashes identify the exact bytes. Extract the archive outside the repository to re-score. Re-scoring reads logged task specs and observable envelopes, uses no model grader, and launches no target. Local absolute artifact paths in the original command are historical provenance, not required for re-scoring.

`--resume-archive` keeps the original evaluation snapshot even when the authoritative feature branch has advanced. Before scheduling work it verifies the archive snapshot and lane, fixture/scorer/schema/task manifests, every baseline prompt, task identity and unique trial IDs. Imported controls are discarded and regenerated deterministically. The runner schedules only each task's missing valid count; existing valid FAIL/UNKNOWN records are preserved and never replaced.

Normal `--resume-archive` always requires every archived baseline prompt to equal the current prompt. The only exception is the explicit `--resume-surrogate-impact` continuation mode. Its initial transition is restricted to the repository-owned `core_final_full_baseline_resume_94_surrogate_contract_impact.json` and its exact SHA-256-named recovered archive. It validates that artifact's snapshot, lane, task identities, raw status counts, fixture/scorer/schema/task manifest, prompt artifacts and affected-record scope, then imports only the unaffected valid records as a release seed. At the current checkpoint this produces a 64-valid seed and exactly 48 remaining valid trials.

After that transition, the same mode accepts only a self-contained corrected-current-prompt release checkpoint. It reconstructs and authenticates the original 64-record seed from the immutable recovered archive, verifies the checkpoint lineage's source hash, excluded and seed trial IDs, manifest, snapshot, lane and unique trial IDs, then verifies every required artifact (including prompt, response/JSONL and other captured trial evidence) by path and hash. On resume, verified inherited current evidence is materialized into a flat canonical output area before export, so each next checkpoint carries all current-prompt evidence without ZIP nesting or dangling prior-generation paths. The checkpoint stores raw current trials plus lineage metadata rather than nesting prior ZIP files. Thus `64 → 64+N` preserves the original seed and only schedules the remaining work. Missing or altered lineage, source identity, seed record, manifest, task/lane/snapshot, artifact, prompt, or duplicate trial ID fails closed. `historical_audit` is never a runnable bypass.

Fresh and continuation scheduling share one task-level policy: run only the initial missing valid count once, then retry only an infrastructure-caused shortfall one call at a time, at most twice per task. Durable release checkpoints store each task's deterministic seed-derived initial requested count, `initial_scheduled` flag, initial trial IDs, replacement count, and replacement trial IDs. The importer requires every current-prompt trial to appear exactly once in that task's initial-or-replacement provenance, requires the initial ID set to have exactly the seed-derived initial size, and derives the retry budget from the authenticated replacement IDs rather than a self-reported counter. A resumed task with an exhausted budget never receives a new initial batch. Valid FAIL or UNKNOWN never becomes a replacement, INVALID_FIXTURE stops replacement, and a task already at its required valid count receives no call. Normal `--resume-archive` remains a strict single-archive current-prompt import; only `--resume-surrogate-impact` owns this historical-transition and multi-generation release-lineage contract.

`PHASE3_PASSED` requires the implemented full suite, all critical gates, correctly detected controls, repeatable logs/re-score and production/main/isolation invariants. `PHASE3_BLOCKED` records invalid-fixture or valid-trial shortfalls. `PHASE3_FAILED` records failed critical gates or isolation invariants. `PHASE3_PARTIAL` records incomplete diagnostic/calibration/log validation. Non-critical distributions have no additional pass threshold. None of these statuses authorizes remediation: failures only preserve evidence, bounded statement, owner candidates, severity and reproducibility. Harness behavior and Planning owners remain unchanged pending separate review.

Implementation references: [Codex non-interactive JSONL](https://developers.openai.com/codex/noninteractive), [Inspect scoring workflow](https://inspect.aisi.org.uk/scoring-workflow.html). Installed CLI 0.153.4 and Inspect 0.3.263 are the execution evidence; documentation is not a substitute for observed capabilities.
