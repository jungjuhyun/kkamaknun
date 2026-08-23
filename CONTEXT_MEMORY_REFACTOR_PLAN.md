# CONTEXT / MEMORY REFACTOR PLAN

> 상태: **PHASE 8 — SECOND LIMITED REPAIR APPLIED / NATURAL FRESH-SESSION REGRESSION REQUIRED**
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
- **P6 blind eval specification — PASS**
- **P7 static/structural verification — PASS**

BEFORE baseline:
`4f632705702d192a0eb188ace4d8fcee11d1d178`

backup branch:
`backup/pre-context-memory-refactor-20260823`

blind eval specification 보존 branch:
`eval/context-memory-spec-20260824`

---

## 3. 구현된 architecture

- `AGENTS.md` — small progressive-disclosure router
- `진행상태.md` — project current-state canonical owner
- active execution plan — task-local phase owner
- `USER_CONTEXT.md` — stable context
- `PROJECT_RULES.md` — durable invariant
- `PLANNING_PROCESS.md` — reusable planning procedure
- `JUDGMENT.md` — reusable judgment principle
- domain docs — domain detail
- `DECISIONS.md`, `기록/`, `실측/`, `계획.md`, git history — history/evidence

새 DB, graph, 별도 active memory repository, background consolidator는 추가하지 않았다.

---

# 4. Behavioral validation results

## STEP 7A — natural fresh-session

**FAIL**

실패:
- current-state miss
- blind eval 가상 데이터의 실제 사실화
- 불필요한 카타카나 history leakage
- canonical owner 미확인 수치/사건 서술

### Repair 1

1. blind eval spec을 `main`에서 제거하고 eval branch에만 보존
2. continuation/current-state 요청에서 `진행상태.md` → active plan 우선
3. 둘로 충분하면 history/archive retrieval 금지
4. 평가용·가상·예시 데이터를 canonical fact로 승격 금지
5. current-state 답변에서 오래된 history 자동 서론 금지

## STEP 8A — Temporary Chat isolation

**INVALID / UNTESTABLE for repo architecture**

Temporary Chat 답변 자체는 품질상 실패했다.
- 오래된 `シ・ツ・ソ・ン` 기획을 current first content처럼 서술
- current canonical repo에서 확인되지 않은 구체 사항을 사실처럼 제시
- 현재 first-content domain owner와 충돌

하지만 답변 스스로 GitHub repository를 직접 찾지 못했다고 밝혔다.
따라서 이 run은 테스트의 필수 전제인 **repo access available**을 충족하지 못했다.

이 run이 추가로 드러낸 실패:

> repo 확인 실패 후 과거 ChatGPT memory/기타 context로 project state를 채우고도 복원한 것처럼 말하는 fallback.

### Repair 2

`AGENTS.md`와 `PROJECT_RULES.md`를 수정했다.

- canonical repo를 `jungjuhyun/kkamaknun`, default branch를 `main`으로 명시
- project continuation/current-state 요청에서는 repo verification을 답변보다 먼저 수행
- ChatGPT personalization memory / 과거 채팅 기억은 project current truth의 canonical source가 아님을 명시
- repo 접근 실패 시 current state를 복원했다고 말하지 않음
- repo 접근 실패 시 과거 memory로 빈칸을 채우지 않음
- repo 미검증이면 `repo 확인 불가 / 현재 상태 검증 불가`로 중단

새 layer/DB는 추가하지 않았다.

---

# 5. 현재 next step — STEP 8B

## Natural fresh-session regression

수리된 `main`에서 일반 새 채팅을 다시 연다.

동일 prompt:

> `까막눈 프로젝트 이어서 하자. 지금 어디까지 왔고 다음에 뭘 해야 하는지 확인해줘.`

유효한 run 조건:
- GitHub repository 접근이 실제로 가능
- prompt에 정답/문서 경로/expected behavior를 추가하지 않음

PASS 기준:
- 실제 repo 접근을 수행
- `진행상태.md`와 active plan으로 현재 단계 복원
- behavioral regression이 현재 작업임을 인식
- production은 validation 이후 복귀점으로 구분
- 오래된 카타카나 history를 현재 상태로 부활시키지 않음
- canonical owner에 없는 숫자/사건을 창작하지 않음
- 사용자에게 repo에 있는 기본 맥락을 다시 설명하라고 요구하지 않음

### 결과 해석

- **PASS** → Phase 9 종료
- **FAIL + repo access 확인** → failure class만 최소 수리
- **GitHub access 없음** → tool availability 문제로 분리; architecture PASS/FAIL을 억지로 판정하지 않음

---

# 6. PHASE 9 — 종료 및 production 복귀

유효한 repo-access fresh-session behavioral run이 PASS하면:
- 이 plan을 `COMPLETED`로 전환
- `진행상태.md`에서 memory validation을 active work에서 제거
- 첫 콘텐츠 제작을 current active work로 전환

그 전에는 production으로 넘어가지 않는다.
