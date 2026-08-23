# CONTEXT / MEMORY REFACTOR PLAN

> 상태: **PLAN LOCKED — EXECUTING PHASE 7**
> 작성일: 2026-08-23
> 역할: context/memory refactor의 **task-local execution state canonical owner**
> project-level current state는 `진행상태.md`가 소유한다.

`CLAUDE.md`의 immutable Karpathy block은 절대 수정하지 않는다.

---

## 목표

repo 접근이 가능한 새 세션이 사용자에게 별도 인수인계 작업을 요구하지 않고:

```text
small bootstrap/router
→ current canonical state
→ task-dependent procedure/judgment/domain memory
→ 필요할 때 history/evidence retrieval
```

순으로 현재 상태와 판단을 복원하게 한다.

---

## 완료된 gate

### P0 — 계획 잠금: PASS

문제·성공 기준·단계·중단 조건을 정의했다.

### P1 — 딥리서치: PASS

`기록/CONTEXT_MEMORY_RESEARCH_2026-08.md`

핵심 수렴:

> small bootstrap + explicit current state + stable context + procedural/judgment memory + raw evidence preservation + agentic retrieval + guarded writes + stale/supersede handling + behavioral eval

### P2 — repository audit: PASS

`기록/CONTEXT_MEMORY_REPO_AUDIT.md`

실제 defect:
- fixed core-doc preload
- mutable current-state duplication
- `진행상태` vs active plan current-state conflict
- historical `확정`의 supersession ambiguity

### P3 — target architecture + RED TEAM: PASS

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

### P4 — rollback baseline: PASS

`기록/CONTEXT_MEMORY_ROLLBACK.md`

BEFORE commit:
`4f632705702d192a0eb188ace4d8fcee11d1d178`

backup branch:
`backup/pre-context-memory-refactor-20260823`

### P5 — implementation: PASS

실제 반영:
- `AGENTS.md` — fixed 7-doc preload → small progressive-disclosure router
- `PROJECT_RULES.md` — durable invariant 중심
- `USER_CONTEXT.md` — mutable first-content/gear/current state 제거
- `진행상태.md` — project current-state owner + active-plan pointer
- `JUDGMENT.md` — reusable principle로 distill
- `DECISIONS.md` — historical log 명확화 + known supersession 표시
- `README.md` — current-state mirror 제거
- `장비세팅.md` — gear domain owner로 scope 정리
- 이 plan 자체도 완료 연구 설명의 반복을 제거하고 task-local state 중심으로 compact

유지:
- `CLAUDE.md` unchanged
- `PLANNING_PROCESS.md` unchanged
- `첫콘텐츠_계획.md` detailed domain owner 유지
- `계획.md`, 기존 `기록/`, `실측/`, `도구/`, git history 보존

BEFORE→P5 compare에서 `CLAUDE.md`는 changed-file 목록에 없었고, target에 없는 DB/graph/new active memory layer를 추가하지 않았다.

판정:
- target architecture와 실제 역할 일치 → YES
- current-state conflict 구조적 제거 → YES
- default preload 감소 구조 → YES
- raw history/evidence 보존 → YES
- user ritual 추가 → NO

### P6 — blind eval specification: PASS

`기록/CONTEXT_MEMORY_EVAL_SPEC.md`

10개 locked case와 expected traits/fail conditions를 실행 전에 고정했다.
평가축은 state recovery, stale rejection, workflow/judgment, selective retrieval, pressure resistance, user burden, overhead다.

---

# 현재: PHASE 7 — BEFORE vs AFTER behavioral validation

## 비교 대상

BEFORE:
`4f632705702d192a0eb188ace4d8fcee11d1d178`

AFTER:
Phase 7 실행 시점 main head

## 동일 조건 원칙

가능한 한:
- 같은 model/config
- 같은 GitHub 접근
- 같은 사용자 prompt
- 같은 tool availability

를 사용한다.

fresh evaluator에게 `기록/CONTEXT_MEMORY_EVAL_SPEC.md`, target architecture, 과거 eval transcript를 보여주지 않는다.

## 평가할 것

- state recovery
- old/current 구분
- stale premise rejection
- judgment consistency under pressure
- 필요한 procedure/domain/history retrieval
- unsupported claim 방지
- 불필요한 preload/retrieval
- 사용자 추가 설명 요구량

## 중요한 도구 한계

현재 이 세션의 도구는 **독립된 fresh ChatGPT session을 자동 생성하는 기능을 제공하지 않는다.**
따라서 같은 세션 안에서 blind cold-start를 흉내내고 PASS라고 선언하지 않는다.

Phase 7은 다음을 분리한다.

1. 지금 가능한 **static/structural BEFORE vs AFTER verification**
2. 실제 repo 접근 가능한 **natural fresh session에서의 behavioral result**

사용자에게 eval 운영 ritual을 새로 요구하지 않는다.

## Phase 7 판정

- **PASS** — 핵심 stale/current/retrieval 실패 감소 + 치명적 새 overhead 없음
- **PARTIAL** — 구조 개선은 확인되나 isolated behavioral evidence가 아직 부족
- **FAIL** — 구조 회귀 또는 실제 behavior 악화

근거보다 강하게 결론내리지 않는다.

---

## PHASE 8 — 제한적 수리

PARTIAL/FAIL에서 실제 failure class가 확인될 때만 실행한다.
새 rule/layer 추가가 기본값이 아니다.

---

## PHASE 9 — 종료

behavioral evidence가 충분해 PASS하면:
- 이 plan을 `COMPLETED`로 전환
- `진행상태.md` active-plan pointer 제거
- 첫 콘텐츠 실제 촬영·편집으로 복귀

한 번의 clean run은 가능성의 증거이지 무조건적인 안정성 증명으로 과장하지 않는다.
