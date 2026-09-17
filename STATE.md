# STATE.md — 현재 상태

기준 시각: 2026-09-17 KST

## Active focus

현재 active plan은 `plans/GPT_HARNESS_FINISH_AND_EP1_VALIDATION.md`다. video-planning harness의 기존 두 입력 분기와 stage topology는 유지한다. EP1 material-first/external-narrative 검증은 아직 final PASS가 아니며, pre_shoot branch와 전체 two-branch harness가 live-validated됐다고 주장하지 않는다.

현재 runtime route는 `tools/harness/STATE.json`의 `video_planning / EP1 / material_first / tools/harness/EP1_LOCK.json`이다.

## 최신 pilot UAT

**USER_FACT**

- 사용자가 `ep1.review_pilot_narrative_v1`을 실제 시청했다.
- narrative direction은 이전보다 개선됐다.
- 일부 scene boundary는 여전히 너무 이르거나 어색했다.
- 현재 Opening은 계속 볼 이유를 충분히 만들지 못했다.
- F002의 가타카나 읽기 complete event만으로는 `그래서 왜 계속 봐야 하지?`가 해결되지 않았다.

**AI interpretation**

- Opening / Viewer Question gate는 FAIL이며 재경쟁이 필요하다.
- pilot에서 드러난 affected boundary validation만 재개방한다.
- narrative-first 방향은 유지하되 대체 Opening, F003/F007 등 과거 evidence montage 재승격, full body relock, Cold open, Step 9와 final planning PASS는 아직 확정하지 않는다.

## Validated input headline

- primary material: `ep1.primary_recording`; single MP4, duration `6325.0625s`, desktop stream 2, mic stream 3.
- full-original rescan 65 candidates와 direct mixed-audio AV 42/42 durable checkpoint는 완료됐으며 새 evidence가 요구하지 않는 한 반복하지 않는다.
- `ep1.review_step10`은 historical `planning_quality_failure`라 다시 시청시키지 않는다.
- `ep1.review_pilot_narrative_v1`은 ffprobe/full decode/durable publish/clean materialize hash를 통과했지만, technical PASS는 Opening·boundary quality PASS가 아니다.
- 상세 candidate/spine/application trace/UAT와 historical evidence는 `materials/ep1_main/PLANNING_RESULTS.md`가 소유한다.

## Current blocker와 immediate next action

현재 blocker는 title/thumbnail promise 또는 즉시 볼 가치를 실제 footage로 드러내면서도 이후 결과·변화·관계·원인에 대한 미해결 Viewer Question을 남기는 Opening이 아직 검증되지 않았고, pilot의 일부 assembled boundary도 자연스럽지 않다는 점이다.

다음 실행:

> Opening / Viewer Question 재경쟁 → affected boundary만 재검토 → 실패 가설 하나를 검증하는 smallest-sufficient pilot → 사용자 UAT → full body relock → Cold open 경쟁 → AI quality gate → full rough cut → 사용자 UAT → EP1 production decision → harness acceptance scope 판정

새 evidence가 요구하지 않는 한 65개 candidate 전체 rescan이나 42개 direct-AV evidence 전체 재구축을 반복하지 않는다.

## Owner pointers

- common executable planning process: `tools/harness/PIPELINE.yaml`
- EP1 semantic facts·A/B/C·packaging·content constraints: `FIRST_VIDEO.md`
- EP1 current planning/evidence/UAT/superseded planning: `materials/ep1_main/PLANNING_RESULTS.md`
- runtime route·stage·artifact registry: `tools/harness/STATE.json`
- deterministic EP1 projection: `tools/harness/EP1_LOCK.json`
- long-lived judgment principles: `PLAYBOOK.md`
- current harness implementation/acceptance plan: `plans/GPT_HARNESS_FINISH_AND_EP1_VALIDATION.md`

## Other workstreams

- Cloud material migration과 durable-media synthetic qualification은 완료 상태다. GitHub가 code/current-truth source이고 K SSD는 optional offline backup이다. 구현·history는 `plans/CLOUD_MATERIAL_STORAGE_MIGRATION.md`, `plans/DURABLE_MEDIA_EXECUTION_RECOVERY.md`, `tools/harness/durable_media.py`를 따른다.
- Scene collector 재작업은 UAT 미완료 보존 상태다. 다시 요청할 때 `SCENE_COLLECTOR_PLAN.md`와 scoped `tools/scene_collector/AGENTS.md`를 따른다.
- System Evaluation은 독립 owner `evals/system/README.md`를 따른다. Phase 3는 `PHASE3_PASSED`, initial Phase 4 Actual Work pilot은 `PHASE4_PILOT_BLOCKED` (`4/5 PASS`, P4-A `UNKNOWN`), Phase 5는 `NOT_STARTED`다. 이번 video-planning cleanup은 그 구현·artifact를 변경하지 않는다.

현재 상태 질문은 이 파일을 기준으로 답하고, 상세 사실은 위 owner로 이동해 확인한다.
