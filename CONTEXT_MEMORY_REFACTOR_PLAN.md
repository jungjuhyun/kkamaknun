# CONTEXT / MEMORY REFACTOR PLAN

> 상태: **PLAN LOCKED — EXECUTING PHASE 5**
> 작성일: 2026-08-23
> 역할: 현재 context/memory refactor의 **task-local execution state canonical owner**
> project-level current state는 `진행상태.md`가 소유한다.

이 파일은 이제 완료된 연구 설명을 반복하지 않고 **현재 실행 상태와 남은 gate**만 유지한다.
원래의 상세 계획은 git history와 Phase 4 rollback baseline에 보존돼 있다.

`CLAUDE.md`의 `BEGIN IMMUTABLE KARPATHY GUIDELINES` ~ `END IMMUTABLE KARPATHY GUIDELINES` 구간은 절대 수정하지 않는다.

---

## 1. 목표

사용자는 별도 인수인계 프롬프트·context transfer block·평가 운영을 반복하지 않는다.

repo 접근이 가능한 새 세션의 AI가:

```text
small bootstrap/router
→ current canonical state
→ task-dependent procedural/judgment/domain memory
→ 필요할 때 history/evidence retrieval
```

순으로 스스로 상태와 판단을 복원하는 구조를 만든다.

성공 기준:
- current vs stale state를 구분
- 결론뿐 아니라 필요한 판단 기준 재현
- 필요 문서만 selective retrieval
- raw history/evidence 보존
- 사용자 운영 부담 감소
- memory system 자체의 context/latency overhead 통제

---

## 2. 완료된 단계

### PHASE 0 — 계획 잠금

**PASS**

문제·성공 기준·단계·중단 조건을 정의했다.

### PHASE 1 — 딥리서치

**PASS**

산출물:

`기록/CONTEXT_MEMORY_RESEARCH_2026-08.md`

수렴한 방향:

> small bootstrap + explicit current state + stable declarative context + procedural/judgment memory + raw evidence preservation + agentic retrieval + guarded writes + stale/supersede handling + behavioral eval

### PHASE 2 — repository audit

**PASS**

산출물:

`기록/CONTEXT_MEMORY_REPO_AUDIT.md`

실제 확인된 핵심 defect:
- fixed core-doc preload
- mutable current-state duplication
- `진행상태`와 active refactor plan의 실제 current-state conflict
- historical `확정`의 supersession ambiguity

### PHASE 3 — target architecture + RED TEAM

**PASS**

산출물:

`기록/CONTEXT_MEMORY_TARGET_ARCHITECTURE.md`

확정:
- 새 DB / 새 active memory repo 없음
- `AGENTS` = small router
- `진행상태` = project current owner
- active plan = task-local phase owner
- `USER_CONTEXT` = stable context
- `PROJECT_RULES` = durable invariant
- `PLANNING_PROCESS` = procedure
- `JUDGMENT` = reusable judgment
- domain docs = domain detail
- `DECISIONS`/기록/실측/git = history/evidence

### PHASE 4 — rollback 기준점

**PASS**

산출물:

`기록/CONTEXT_MEMORY_ROLLBACK.md`

BEFORE commit:

`4f632705702d192a0eb188ace4d8fcee11d1d178`

backup branch:

`backup/pre-context-memory-refactor-20260823`

---

# 3. PHASE 5 — 연구 기반 리팩터링

**현재 단계. Phase 3 명세 밖의 architecture는 추가하지 않는다.**

## 완료

- [x] `AGENTS.md` — fixed preload → small progressive-disclosure router
- [x] `PROJECT_RULES.md` — durable invariant 중심으로 scope 축소
- [x] `USER_CONTEXT.md` — mutable first-content/gear/current state 제거
- [x] `진행상태.md` — project current-state owner + active-plan pointer 구조
- [x] `JUDGMENT.md` — current first-content detail을 제거하고 reusable principle로 distill
- [x] `DECISIONS.md` — history 비권위화 + known supersession 명시
- [x] `README.md` — operational current-state mirror 제거, static map으로 축소
- [x] `장비세팅.md` — first-content protocol 복제를 줄이고 gear owner로 scope 정리

## 유지 — 수정 근거 없음

- [x] `CLAUDE.md` immutable block — 수정 안 함
- [x] `PLANNING_PROCESS.md` — audit에서 별도 procedure layer 자체는 강점으로 판정; 현재 core flow 재설계 안 함
- [x] `첫콘텐츠_계획.md` — first-content detailed owner로 유지
- [x] `계획.md`, 기존 `기록/`, `실측/`, `도구/`, git history — raw/archive/evidence로 보존

## Phase 5 종료 전 검증

- [ ] core 문서의 역할이 target architecture와 일치하는지 다시 읽는다.
- [ ] first-content/gear/current mutable fact가 불필요하게 core memory 여러 곳에 남았는지 검색한다.
- [ ] old fixed-preload instruction이 남아 있는지 검색한다.
- [ ] `DECISIONS` old `확정`이 current procedure와 충돌하는 known 사례가 정리됐는지 확인한다.
- [ ] `CLAUDE.md` immutable block이 baseline과 동일한지 확인한다.

### Exit Gate P5

- target architecture와 실제 구조가 일치하는가?
- 중복/stale risk가 BEFORE보다 줄었는가?
- default preload가 줄었는가?
- user burden이 증가하지 않았는가?
- raw evidence/history를 잃지 않았는가?

PASS 전에는 Phase 6으로 가지 않는다.

---

# 4. PHASE 6 — Blind cold-start eval specification

Phase 5 PASS 후 **실행 결과를 보기 전에 평가 명세부터 잠근다.**

평가축:
1. Static state recall
2. Dynamic state tracking
3. Workflow knowledge
4. Project gotchas
5. Premise awareness
6. State resolution
7. Premise resistance
8. Judgment consistency under pressure
9. Selective evidence retrieval
10. User clarification burden / tool-call overhead

오염 방지:
- test prompt에 정답 규칙을 쓰지 않는다.
- expected traits / fail condition을 실행 전에 잠근다.
- 결과가 마음에 안 든다고 조건을 바꾸지 않는다.
- recall만이 아니라 실제 next-action/decision behavior를 본다.

사용자가 테스트 운영자가 되지 않게 가능한 범위에서 AI/tool side가 평가를 준비한다.

---

# 5. PHASE 7 — BEFORE vs AFTER

동일 조건에서 비교:
- state recovery
- stale/superseded 오류
- judgment reason reproduction
- pressure-driven drift
- retrieval success
- unnecessary preload/retrieval
- response/tool overhead
- 추가 사용자 설명 요구량

판정:
- **PASS** — 핵심 실패 감소 + 치명적 새 overhead 없음
- **PARTIAL** — 개선 있으나 특정 failure 남음
- **FAIL** — 의미 있는 개선 없음 또는 새 회귀가 더 큼

한 번의 pass를 안정성 전체 증명으로 과장하지 않는다.

---

# 6. PHASE 8 — 제한적 수리

PARTIAL/FAIL일 때만.

먼저 failure class를 나눈다.
- routing/retrieval
- stale-state resolution
- write/update
- procedural memory
- judgment policy
- eval artifact

기존 상위 원칙으로 해결 가능하면 새 layer/rule을 추가하지 않는다.
같은 실패가 재현되고 구조 원인이 확인될 때만 수정한다.

---

# 7. PHASE 9 — 채택 및 종료

PASS 후:
- core docs와 실제 architecture 일치 최종 확인
- 이 plan을 `COMPLETED`로 전환
- 임시 eval artifact 정리
- `진행상태.md`의 active-plan pointer 제거
- project current priority를 첫 콘텐츠 실제 촬영·편집으로 복귀

최종 종료 조건:
- 새 세션이 기본 맥락을 다시 묻는 일이 줄었는가
- current state가 stale history보다 우선하는가
- 필요한 판단 이유를 상당 부분 재현하는가
- 필요한 근거를 스스로 찾는가
- 사용자가 GPT 인수인계 운영자가 되지 않았는가
- memory system이 실제 콘텐츠 제작을 계속 늦추지 않는가
