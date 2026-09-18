# GPT 하네스 마무리 + EP1 실전 검증 계획

기준일: 2026-09-17

상태: **ACTIVE** — 기존 harness architecture와 두 입력 분기를 유지한 ownership/content cleanup은 구현 대상에 반영했다. EP1 narrative pilot UAT에서 narrative direction 개선과 함께 Opening / Viewer Question 및 일부 boundary failure가 확인돼 material-first/external-narrative baseline의 final acceptance는 아직 남아 있다.

현재 상태와 다음 행동: `STATE.md`

공통 executable process: `tools/harness/PIPELINE.yaml`

EP1 current planning/evidence: `materials/ep1_main/PLANNING_RESULTS.md`

## 1. 목적과 lifecycle 판정

이 계획은 새 harness를 설계하는 문서가 아니라, 기존 video-planning harness를 실제 EP1 material로 끝까지 검증해 reusable baseline의 acceptance scope를 판정하는 active implementation plan이다.

과거 단계가 완료·실패·대체됐다는 사실만으로 계획 전체가 종료되지는 않는다. repository에는 이 계획을 대체하거나 종료한다는 evidence가 없고 `STATE.json`의 current-plan pointer도 이 계획을 가리킨다. 따라서 pointer를 유지하고 완료·실패한 단계는 historical evidence로 구분한다.

## 2. 완료 ownership

서로 다른 완료를 섞지 않는다.

1. 한 편의 video planning 완료 조건은 `PIPELINE.yaml`의 per-video pass condition이 소유한다.
2. harness implementation을 reusable baseline으로 acceptance하는 조건은 이 계획이 소유한다.
3. 현재 충족 정도와 immediate next action은 `STATE.md`가 소유한다.

EP1 한 편의 성공만으로 pre_shoot branch나 entire two-branch harness가 live-validated됐다고 주장하지 않는다. latest pilot의 Opening/boundary failure 때문에 material_first/external-narrative baseline도 아직 final PASS가 아니다.

## 3. Harness acceptance criteria

- current truth, deterministic lock, actual material identity, internal provenance와 artifact registry가 보존된다.
- `material_first`와 `pre_shoot` 분기 및 기존 stage topology가 유지된다.
- common executable rules는 `PIPELINE.yaml`, long-lived judgment는 `PLAYBOOK.md`, repository routing은 `AGENTS.md`에만 둔다.
- deterministic validator는 A/B/C/package lock과 명백한 forbidden claim만 검사하고 subjective planning quality를 인증하지 않는다.
- external-narrative material-first 경로가 source narrative와 실제 footage를 바탕으로 Opening, Viewer Question, body, boundary, payoff와 user-viewed rough-cut UAT를 통과한다.
- pre_shoot의 live validation 여부와 남은 scope를 별도로 기록하고, 실행하지 않은 검증을 PASS로 확대하지 않는다.

## 4. Current evidence boundary

현재 재사용하는 검증된 입력:

- `ep1.primary_recording` immutable identity와 stream facts
- full-original rescan 65 candidates
- durable direct mixed-audio AV 42/42 checkpoint
- `ep1.review_step10`의 historical planning-quality failure evidence
- `ep1.review_pilot_narrative_v1` technical receipt와 최신 user-view UAT

현재 재사용하지 않는 planning lock:

- 과거 34/15 select, reconstruction 30 candidates, REVIEW_B/REVIEW_C body와 Cold open
- superseded 32 RETAIN / 52 ranges / prior Step 9 PASS
- F003/F007 등 과거 evidence montage를 대체 Opening으로 자동 승격하는 선택

full rescan과 direct-AV evidence는 새 evidence가 요구하지 않는 한 반복하지 않는다.

## 5. Latest UAT와 남은 acceptance path

USER_FACT와 AI interpretation의 상세 owner는 `materials/ep1_main/PLANNING_RESULTS.md`다. 현재 결론은 narrative-first 방향은 개선됐지만 F002 complete event만으로 계속 볼 이유가 생기지 않았고 일부 assembled boundary도 너무 이르거나 어색했다는 것이다.

남은 실행 순서:

> Opening / Viewer Question 재경쟁 → affected boundary 재검토 → 실패 가설 하나를 검증하는 smallest-sufficient pilot → 사용자 UAT → full body relock → Cold open 경쟁 → AI quality gate → full rough cut → 사용자 UAT → EP1 production decision → harness acceptance scope 판정

대체 Opening, full body, Cold open 또는 final PASS를 이 계획에서 미리 확정하지 않는다.

## 6. Owner 반영

- `AGENTS.md`: repository routing, owner boundary, retrieval, deterministic-vs-quality boundary, mutation safety
- `PLAYBOOK.md`: long-lived planning judgment principles
- `tools/harness/PIPELINE.yaml`: common executable branches, stages, gates and per-video completion
- `STATE.md`: current focus, latest USER_FACT/AI interpretation, blocker and next action
- `tools/harness/STATE.json`: runtime route/stage and external artifact registry
- `FIRST_VIDEO.md`: EP1 semantic facts, A/B/C, packaging and content constraints
- `materials/ep1_main/PLANNING_RESULTS.md`: current planning, detailed evidence, application trace, UAT and superseded planning
- `tools/harness/EP1_LOCK.json`: deterministic EP1 projection only

`COMMON_RULES.json`과 `check_draft.py`는 subjective quality를 검사하지 않는다. System Evaluation과 media implementation은 이 계획의 video-planning quality evaluator가 아니며 이번 cleanup에서 변경하지 않는다.

## 7. Web-first design gate receipt

**Search:** current owner·consumer·tests를 먼저 조사한 뒤 YouTube 공식 creator guidance, JSON Schema 공식 문서, Python 공식 `unittest` 문서를 확인했다.

**Evaluate:**

- YouTube는 intro가 title/thumbnail expectation을 충족하고 관심을 유지하는지 보라고 하며, storytelling으로 anticipation·curiosity를 유지하라고 설명한다. 보편적인 최적 영상 길이도 없다고 명시한다. 따라서 complete event나 fixed pilot duration은 Opening 성공의 대리 지표가 될 수 없다.
- JSON Schema는 structure·constraints·types의 declarative validation을 위한 도구다. 현재 문제는 새 runtime schema가 아니라 owner/content drift와 subjective planning gate의 내용 결함이므로 새 schema framework는 중복과 migration cost만 늘린다.
- Python test case는 입력에 대한 특정 response를 검증하는 단위다. 따라서 exact Korean prose보다 YAML topology와 validator behavior를 regression boundary로 둔다.

공식 source:

- https://support.google.com/youtube/answer/9314415?hl=en
- https://support.google.com/youtube/answer/16559650?hl=en
- https://support.google.com/youtube/answer/16559651?hl=en
- https://json-schema.org/docs
- https://docs.python.org/3/library/unittest.html

**Adopt/Adapt:** 기존 owner 구조, pipeline topology, JSON runtime registry, validator와 tests를 유지하고 content/ownership만 정리한다.

**Build last:** 새 framework·owner·schema·Opening subsystem 없이 existing pipeline의 Opening/Viewer Question, boundary, repetition, UAT recovery 문구와 구조 regression만 최소 보강한다.

## 8. RED TEAM과 rollback boundary

RED TEAM 판정: **PASS for owner-local cleanup.** 확인된 failure는 기존 owner와 pipeline content 안에서 해결 가능하며 새 architecture가 필요한 concrete blocker는 없다.

- artifact registry 손실 위험: logical ID/object_key/size/sha256/publish를 이전 snapshot과 비교한다.
- common process가 semantic owner에 다시 복제될 위험: repository-wide reference/duplicate scan을 실행한다.
- current/history 혼재 위험: `STATE.md`, `STATE.json`, `EP1_LOCK.json`에서 historical prose와 mutable planning state를 제거하고 detailed history는 `PLANNING_RESULTS.md`에 보존한다.
- pre_shoot 또는 stage topology regression 위험: YAML parse와 structure test로 두 branch와 1~10 stage order를 검증한다.
- validator가 quality를 인증하는 regression 위험: positive/negative behavior test와 explicit out-of-scope test를 유지한다.

문제가 생기면 새 layer를 추가하지 않고 이 commit을 revert할 수 있는 owner-local 변경으로 유지한다.

## 9. Historical execution provenance

- 2026-09-02 pre-shoot 가상 완성본 POC는 packaging/body 구조 FAIL로 종료했다.
- 2026-09-04 actual-material routing, candidate competition과 deterministic/quality 책임 분리를 구현했다.
- REVIEW_B는 narrative continuity·핵심 사건·payoff 실패, REVIEW_C는 scene-selection·within-scene compression·story-context allocation failure로 거절됐다.
- source reconstruction과 independent evidence audit 뒤 full-original rescan 65 candidates, direct AV 42/42 durable checkpoint를 완료했다.
- `ep1.review_step10` UAT 뒤 narrative-first spine과 application trace를 통합하고 `ep1.review_pilot_narrative_v1`을 만들었다.
- 최신 pilot UAT는 narrative direction 개선을 확인했지만 Opening / Viewer Question과 affected boundary를 다시 열었다.

세부 receipt와 superseded boundary는 `materials/ep1_main/PLANNING_RESULTS.md`가 보존한다.

## 10. Validation과 commit

JSON/YAML parse, Python compile, deterministic validator, material-store/durable-media regression, artifact registry preservation, pipeline topology/branch/gate checks, current/history separation scan, stale-reference scan, media/eval unchanged 확인, `git diff --check`와 changed-file/full-diff review를 모두 통과한 뒤 feature branch에 atomic single commit으로 push한다.
