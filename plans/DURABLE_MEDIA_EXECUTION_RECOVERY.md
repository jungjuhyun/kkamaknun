# DURABLE_MEDIA_EXECUTION_RECOVERY

Status: APPROVED_FOR_IMPLEMENTATION_AFTER_RED_TEAM
Starting snapshot: `ebde17b5f5abd6b3a1b22b7fe3186bc5442450c4` (`gpt-harness-finish-plan`)
Date: 2026-09-17 KST

## Problem and incident evidence

Cloud material migration is complete. GitHub is the code/current-truth source, and the authenticated cloud material store holds durable material bytes through the logical-artifact registry in `tools/harness/STATE.json`. The K SSD is only an optional offline backup.

The reported EP1 rough-cut failure is therefore not a missing-storage incident: the rendering environment ended unexpectedly, a final-named MP4 had no `moov` atom, and there was no manifest, validation receipt, durable progress, resume point, or cross-device recovery path. A human transported an SSD snapshot to reconstruct state. `material_store.py` currently materializes/publishes registered artifacts with local SHA/size checks, but it owns none of these execution semantics.

Current production planning is independently blocked before new rough-cut generation by direct audio/continuous-AV verification. This plan must not change the EP1 lock, source identity, or that planning gate. A recovery pilot may use immutable EP1 bytes only as a technical workload; it must never be represented as an authorized new production rough cut.

## Current architecture classification

| Classification | Evidence |
| --- | --- |
| Implemented contract | GitHub for code/current truth; authenticated cloud store for durable external bytes; logical artifact IDs in `STATE.json`; rclone transport; fully materialized local cache; K optional. |
| Validated capability | Cloud round trip, SHA verification, ffprobe/decode of primary material, published derived probe, and K-less clean-cache recovery passed in the completed cloud-migration plan. |
| Historical plan/evidence | `review_b`/`review_c`, old selections, and migration phases are not current EP1 production input. |
| Newly found gap | No run identity, immutable execution receipt, progress journal, checkpoint lifecycle, lease/stale detection, safe final publication, resume command, or cross-device run recovery. |

## Web-first research gate and comparison

Research was performed before selecting an architecture. Official source facts are external evidence, not repository current truth.

| Candidate | What it solves | Overlap with this repository | Decision |
| --- | --- | --- | --- |
| FFmpeg fragmented MP4 | Writes media as fragments; `frag_keyframe` and `empty_moov` can make a partial staging file structurally more inspectable. Segment muxer output can be read by concat demuxer. | Prevents one monolithic interrupted output from being the only progress representation. | Adapt only: independently rendered, hash-validated segments plus normal final mux. Fragmented staging is optional local diagnostics, never a committed final. |
| rclone + Drive | `copy`/`copyto`, checksums, retries, and remote partial-name behavior; Drive supports resumable uploads. | Existing transport and provider. | Adopt existing adapter; publish only immutable checkpoints and final receipts; verify after materialize. Do not reimplement Drive resumable protocol. |
| Temporal | Durable, crash-proof workflow continuation. | State history, retries, and deterministic progress concepts. | Reject now: requires service/worker/runtime administration disproportionate to one local render workflow. Adapt durable journal, idempotent unit, and explicit state ideas. |
| Prefect | Persisted task results, state transitions, retries, caching, concurrency. | Checkpoint/reuse/state model. | Reject now: orchestration service/settings add material operational surface. Adapt completed-unit reuse and explicit crashed/stale states. |
| DVC | Versioned data, reproducible stages, remote cache. | Immutable inputs and content-addressed output concepts. | Reject now: it does not provide active-run lease or media commit semantics; existing registry already provides artifact identity. Adapt input/config digest and hash-verified outputs. |

Official sources consulted: FFmpeg formats documentation; rclone `copy`, general, and Google Drive documentation; Google Drive API resumable upload guide; Temporal documentation; Prefect state/result/task documentation; DVC command reference. URLs and findings are recorded in the final implementation report, not promoted to current truth.

## Chosen architecture

Add a small standard-library Python executor, `tools/harness/durable_media.py`, rather than a workflow framework.

1. A run has a generated UUID, an immutable `input_identity` (logical source IDs plus recorded size/SHA and execution-config SHA-256), and a unique cloud prefix `runs/<run-id>/`.
2. A local run directory contains only reconstructable working bytes. Its cloud journal is a small JSON receipt published atomically as immutable generations. The latest pointer is advisory; a recovery command scans and verifies generations instead of trusting it blindly.
3. Each independent segment is an idempotent unit. It renders to a local staging name, passes ffprobe and full decode, receives SHA-256/size, and only then is published as a checkpoint under its content-verified run prefix. A completed checkpoint is reused only when input/config/unit identity and hash all match.
4. Local temporary files, FFmpeg logs, and failed partials are EPHEMERAL and are not uploaded. Hash-verified completed segments, state journals, and manifests are CHECKPOINTS. A normally muxed user-compatible MP4 plus its full decode/ffprobe/SHA manifest becomes COMMITTED only after all validation passes and the final commit marker is published.
5. Final assembly reads verified checkpoints into a staging filename, validates it fully, uploads it to a unique final object, materializes/verifies it once, then publishes the commit marker last. No final-named local or cloud media is authoritative without a matching committed manifest and marker.
6. A lease record contains holder, start/heartbeat timestamps, and generation. A live lease rejects concurrent mutation; an expired heartbeat is STALE and can be claimed only with explicit `--takeover` after recovery verification. A process killed without closing leaves the run recoverable, not committed.
7. Rollback never deletes immutable checkpoints or a previous commit. It marks the current run abandoned/failed and removes only its local EPHEMERAL directory. A prior committed artifact stays valid.

The media strategy is hybrid C/B: render independent normal-MP4 segments, validate each before checkpointing, and concat/remux to a normal compatible final MP4 via a staging path and atomic local rename. If enabled, fragmented MP4 is solely a staging diagnostic aid; it is not relied on for recovery or delivered as final output. This avoids treating a no-`moov` monolith as a usable result while keeping final compatibility.

## Owner map and instruction boundary

| Fact | Owner |
| --- | --- |
| Durable-run implementation and its unit tests | `tools/harness/durable_media.py`, `tools/harness/test_durable_media.py` |
| Existing material transfer and logical registry | `tools/harness/material_store.py`, `tools/harness/STATE.json` |
| Current project status/next action | `STATE.md` |
| General web-first system-design gate and repository execution rule | `AGENTS.md` |
| System-evaluation measurement boundaries | `evals/system/README.md` |
| This decision/provenance/execution record | this plan only |

The Project instruction is not copied or changed in this repository. It should own only an enforcement bridge: require that repository architecture/workflow/tool/recovery proposals demonstrate a current official-source search/evaluation receipt before design commitment, then defer concrete gate details to `AGENTS.md`. It must not duplicate AGENTS routing, source owners, commands, or provider details. `CLAUDE.md` remains its import-only adapter and its protected block is untouched.

## Implementation steps and gates

1. Add deterministic run schema, atomic local JSON write, config/input digests, journal generations, and lease/stale recovery. Validate with unit tests covering malformed journals, identity mismatch, duplicate run IDs, active lease, stale takeover, and crash-state recovery.
2. Add validated unit rendering/checkpoint publication/reuse and final staging/commit flow. Validate with a fake transport and real local FFmpeg fixture; confirm no `.partial`/staging file can be committed.
3. Add CLI commands (`start`, `run`, `recover`, `status`, `rollback`) and explicit artifact lifecycle output. Validate idempotent repeated recovery and cross-device materialization of a checkpoint.
4. Integrate only the necessary durable-run registry fields in `STATE.json`; do not add volatile run state to Git. Update `STATE.md` with the implemented capability without falsely advancing the blocked EP1 planning gate.
5. Refactor the relevant AGENTS design/research section as one integrated replacement after its source/owner/reference audit. It will require a web-first hard gate for architecture, workflow, tool, recovery, storage, and execution-contract changes: research current official sources; compare existing implementation and external alternatives; record Adopt/Adapt/Build decision, evidence, and rollback/validation before implementation. Routine local bug fixes and tasks with no design choice do not need artificial research.
6. Determine System Evaluation scope from its observable-evidence contract. Do not grade hidden browsing/tool calls. Add only a static regression if it can inspect required plan/source evidence and repo/external/inference separation; otherwise document no change.
7. Run the crash-injection matrix and technical EP1 workload pilot only after Steps 1-6 pass. Production rough-cut creation remains prohibited until the existing AV gate is separately cleared.

Each step requires implementation, focused tests, deterministic validation, reference scan, and an update to this plan’s execution record before the next step.

## Crash-injection and recovery matrix

| Injection | Expected durable state | Recovery assertion |
| --- | --- | --- |
| Kill during unit render | No checkpoint for that unit | Delete/ignore EPHEMERAL partial; rerender only that unit. |
| Fail during checkpoint publish | Unit remains uncommitted or verified checkpoint exists | Verify remote object/generation; reuse only verified object or rerender. |
| Kill during final mux | No commit marker | Existing checkpoints are reused; assembly reruns; partial final is never final. |
| Kill before validation | No checkpoint/commit transition | Validation reruns before any publish/commit. |
| Kill after validation before marker | Final object may exist, but is uncommitted | Recovery validates manifest/object and either completes marker or discards staging authority; never treats it as final automatically. |
| Clean cache/new device | Journal and checkpoints only | Materialize/verify journal and completed units; resume without K SSD or manual file hunting. |
| Concurrent start / stale run | Lease conflict / stale state | Active mutation rejected; stale takeover requires explicit verified recovery. |

## Rollback and completion definition

Rollback is local ephemeral cleanup plus an immutable failed/abandoned journal transition. It never overwrites source, deletes checkpoints, or modifies an earlier COMMITTED result.

Completion requires: immutable source and lock identities preserved; checkpoint reuse; corruption and partial-final rejection; cloud journal/checkpoint SHA verification; cross-device clean-cache recovery without K; final ffprobe and full decode; final SHA-256 and manifest; explicit commit marker; concurrent/stale safety; current-owner updates; tests/scans; one atomic commit and remote verification.

## Plan RED TEAM result

The plan rejects rebuilding `material_store.py`, framework adoption without need, provider-specific core semantics, Git/external-artifact mixing, and uploading all temporary bytes. Checkpoint granularity is independent segments only. Lease generations protect concurrent/stale writers. A final MP4 without manifest/marker is never authoritative. Rollback is deliberately non-destructive. The System Evaluation boundary remains observable evidence only. The remaining external blocker is existing EP1 AV gate and any unavailable cloud credentials; neither is silently bypassed.

## Execution record

- 2026-09-17: pre-flight passed at the starting snapshot; full relevant-source audit and official-source research completed.
- 2026-09-17: plan RED TEAM completed; no design flaw requires a plan rewrite before Step 1.
- 2026-09-17: Steps 1-3 implemented as `durable_media.py`; immutable self-hashed journal generations, duplicate-run/lease/stale-takeover checks, identity-bound checkpoints, remote round-trip hash verification, final manifest, and marker-last commit are covered by focused tests.
- 2026-09-17: `AGENTS.md` Step 5 integrated web-first hard gate and `STATE.json` current runtime owner update completed. No System Evaluation change: its contract cannot infer hidden browsing and a static source check would duplicate the repository instruction audit rather than measure a target.
- 2026-09-17: Existing machine-local rclone was present with an existing authenticated `kkamaknun` material remote; ambient `KKAMAKNUN_MATERIAL_REMOTE` was absent, so a process-local synthetic validation root was injected without exposing its value. The synthetic cloud pilot PASSed A–E with separate-process recovery: render interruption rerendered only the missing unit; interrupted checkpoint publish left an unreferenced object that was not reused; mux failure left no marker while checkpoints restored; pre-validation failure published neither final nor marker; and post-validation/pre-marker recovery explicitly revalidated then published the marker. Cloud checkpoint/final bytes were round-trip SHA-256 verified; a clean cache recovered without K; final ffprobe/full decode, manifest, and marker-last semantics PASSed. No EP1 production source, lock, or rough cut was used or created.
- 2026-09-17: Implementation RED TEAM reconfirmed that incomplete staging, unreferenced checkpoint uploads, and a final object without a manifest/marker have no committed authority; lease observers are read-only and stale mutation requires explicit takeover. Focused material-store + durable-media tests: 24/24 PASS.
- 2026-09-17: `python -m evals.system.check` ran 218 tests and produced 217 PASS plus one existing immutable historical-release-manifest mismatch (`test_interpretation_receipts_distinguish_status_change_and_keep_v1_importable`). It compares preserved System Evaluation release evidence and is not caused by, loosened for, or repaired by this durable-media change. The System Evaluation release remains unchanged; this is recorded as historical authentication mismatch, not a substantive durable-media regression.
