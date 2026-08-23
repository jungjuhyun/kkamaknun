# CONTEXT / MEMORY REFACTOR PLAN

> 상태: **PHASE 7 ACTIVE — FRESH-SESSION BEHAVIORAL VALIDATION**
> 작성일: 2026-08-23
> 역할: context/memory refactor의 task-local execution state owner
> project-level current state는 `진행상태.md`가 소유한다.

`CLAUDE.md`의 immutable Karpathy block은 절대 수정하지 않는다.

---

## 1. 목표

repo 접근이 가능한 새 세션이 사용자에게 별도 인수인계 작업을 요구하지 않고:

```text
small bootstrap/router
→ current canonical state
→ task-dependent procedure/judgment/domain memory
→ 필요할 때 history/evidence retrieval
```

순으로 현재 상태와 판단을 복원하게 한다.

---

## 2. 완료된 단계

- **P0 계획 잠금 — PASS**
- **P1 딥리서치 — PASS** → `기록/CONTEXT_MEMORY_RESEARCH_2026-08.md`
- **P2 repository audit — PASS** → `기록/CONTEXT_MEMORY_REPO_AUDIT.md`
- **P3 target architecture + RED TEAM — PASS** → `기록/CONTEXT_MEMORY_TARGET_ARCHITECTURE.md`
- **P4 rollback baseline — PASS** → `기록/CONTEXT_MEMORY_ROLLBACK.md`
- **P5 implementation — PASS**
- **P6 blind eval specification — PASS** → `기록/CONTEXT_MEMORY_EVAL_SPEC.md`
- **P7 static/structural verification — PASS**

BEFORE baseline:
`4f632705702d192a0eb188ace4d8fcee11d1d178`

backup branch:
`backup/pre-context-memory-refactor-20260823`

---

## 3. Phase 5에서 실제로 바뀐 구조

- `AGENTS.md` — fixed 7-document preload → small progressive-disclosure router
- `PROJECT_RULES.md` — durable invariant 중심
- `USER_CONTEXT.md` — mutable first-content/gear/current state 제거
- `진행상태.md` — project-level current-state canonical owner
- `JUDGMENT.md` — reusable judgment principle 중심으로 distill
- `DECISIONS.md` — historical transition log로 명확화 + known supersession 표시
- `README.md` — current-state mirror 제거, static repository map
- `장비세팅.md` — first-content protocol 복제를 줄이고 gear domain owner로 정리

의도적으로 유지:
- `CLAUDE.md` unchanged
- `PLANNING_PROCESS.md` unchanged
- `첫콘텐츠_계획.md` detailed domain owner 유지
- `계획.md`, 기존 `기록/`, `실측/`, `도구/`, git history 보존

새 DB, graph, 별도 active memory repository, background consolidator는 추가하지 않았다.

---

# 4. PHASE 7 — fresh-session behavioral validation

## 4.1 정적 검증

**PASS**

확인된 것:
- fixed full preload 제거
- project current state와 task-local phase owner 분리
- stable context / mutable state / history ownership 분리
- known supersession ambiguity 보정
- raw evidence/history 보존
- rollback baseline 보존

## 4.2 왜 지금 behavioral test를 해야 하는가

구조가 맞아 보여도 실제 fresh session이:
- 현재 상태를 복원하지 못하거나
- 과거 상태를 current로 오인하거나
- 필요한 domain/procedure/history를 찾지 못하거나
- 사용자에게 기본 맥락을 다시 요구한다면

이번 refactor의 실제 목적을 달성한 것이 아니다.

따라서 **behavioral validation이 끝나기 전에 production 복귀를 완료 처리하지 않는다.**

## 4.3 테스트 순서

### STEP 7A — natural fresh-session test

실제 평소 사용 형태에 가까운 새 채팅에서 최소한의 요청만 준다.

권장 첫 prompt:

> `까막눈 프로젝트 이어서 하자. 지금 어디까지 왔고 다음에 뭘 해야 하는지 확인해줘.`

이 prompt에는 정답, 문서 경로, 판단 규칙, expected behavior를 넣지 않는다.

관찰:
- repo/current state를 스스로 확인하는가
- memory refactor를 아직 active production work로 오인하지 않는가
- 첫 콘텐츠 제작 복귀 지점을 정확히 찾는가
- 근거 없이 과거 상태를 current로 사용하지 않는가
- 사용자에게 이미 repo에 있는 기본 설명을 다시 요구하지 않는가

### STEP 7B — isolation test (필요할 때만)

Natural fresh-session pass가 프로젝트/채팅 memory의 도움인지 repo architecture 덕분인지 구분할 필요가 있을 때만 수행한다.

공식 ChatGPT Temporary Chat은 개인화를 위한 기존 memory/이전 대화를 사용하지 않는다. Temporary Chat에서 GitHub 접근이 실제로 제공되는 환경이라면 repo-only에 가까운 검증에 사용할 수 있다.

Temporary Chat에서 GitHub 접근이 제공되지 않으면 그 환경 제약을 기록하고, 억지로 PASS/FAIL을 만들지 않는다.

## 4.4 판정

- **PASS** — fresh session이 현재 상태·필요 자료·다음 행동을 스스로 복원하고 stale premise를 사용하지 않음
- **PARTIAL** — 핵심 상태는 복원하지만 routing/judgment/history 중 일부가 약함
- **FAIL** — current state를 틀리게 잡거나 사용자에게 기본 인수인계를 다시 요구하거나 stale history를 current로 사용

실패 시 바로 새 layer를 추가하지 않고 failure class를 먼저 분류한다.

---

# 5. PHASE 8 — 제한적 수리

Phase 7에서 실제 failure가 확인될 때만 진입한다.

failure class:
- routing failure
- current-state failure
- stale/supersession failure
- domain retrieval failure
- procedure/judgment retrieval failure
- unsupported-claim failure
- eval contamination/artifact

기존 owner/routing 수정으로 해결되면 새 architecture를 만들지 않는다.

---

# 6. PHASE 9 — 종료 및 production 복귀

Phase 7 behavioral validation이 PASS하면:
- 이 plan을 `COMPLETED`로 전환
- `진행상태.md`에서 memory validation을 active work에서 제거
- 첫 콘텐츠 제작을 현재 active work로 전환

그 전에는 GitHub 문서 리팩터링이 **구조적으로 완료됐지만 실제 동작 검증 전**으로 취급한다.
