# CONTEXT / MEMORY REFACTOR PLAN

> 상태: **PHASE 8 — LIMITED REPAIR APPLIED / FRESH-SESSION RETEST REQUIRED**
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

# 4. PHASE 7 — natural fresh-session 결과

## STEP 7A 결과: **FAIL**

실제 새 채팅에 다음 최소 prompt만 전달했다.

> `까막눈 프로젝트 이어서 하자. 지금 어디까지 왔고 다음에 뭘 해야 하는지 확인해줘.`

관찰된 실패:

1. **current-state failure**
   - canonical `진행상태.md`는 fresh-session behavioral validation이 현재 활성 작업이라고 명시했지만,
   - fresh answer는 프로젝트가 이미 첫 콘텐츠 편집 단계로 복귀한 것처럼 답했다.

2. **eval contamination**
   - fresh answer가 `35분 촬영 / 강한 장면 8개 / 14분 vs 8분`을 실제 최근 프로젝트 상태처럼 서술했다.
   - 이 수치는 blind eval spec의 가상 CASE J 입력과 일치한다.
   - 평가 명세를 fresh agent에게 보여주지 않는다고 적어놓고 같은 default branch의 `기록/`에 두었던 것이 구조적 실수였다.

3. **irrelevant historical leakage**
   - 현재 상태 확인 요청인데 오래된 카타카나 첫 콘텐츠 맥락을 서론에 꺼냈다.
   - 현재 answer에는 필요 없는 history였다.

4. **unsupported/current-owner 미확인 정보**
   - `20분 시험 / 강한 사건 약 5개`, `후속 테스트 12개 중 8개`, `단어 공부 후 향상` 등 현재 canonical owner에서 확인되지 않은 내용을 실제 진행 사실처럼 서술했다.
   - natural fresh chat은 ChatGPT personalization memory / past-chat context의 영향을 받을 수 있으므로 repo 오염과 제품 memory 오염을 분리해 재검증해야 한다.

판정 failure class:
- routing failure
- current-state failure
- eval contamination/artifact
- unsupported-claim failure
- external personalization contamination 가능성

---

# 5. PHASE 8 — 제한적 수리

실제 failure가 확인됐으므로 최소 수정만 수행한다.

## 적용한 수정

### A. eval spec을 default branch에서 제거

- blind eval spec은 `eval/context-memory-spec-20260824` branch에 보존한다.
- default `main`에서는 `기록/CONTEXT_MEMORY_EVAL_SPEC.md`를 제거했다.
- 평가용 가상 수치가 production memory retrieval에 섞이지 않게 한다.

### B. `AGENTS.md` current-state routing 강화

continuation/current-state 요청에서는:

1. `진행상태.md`
2. 활성 execution plan

을 먼저 확인하고, 이 둘로 답이 충분하면 history/DECISIONS/archive를 읽지 않는다.

추가 guard:
- 평가용·가상·예시·테스트 시나리오를 project fact로 승격 금지
- current-state 답변에서 오래된 project history를 자동 서론으로 꺼내지 않음
- historical detail은 사용자가 묻거나 현재 판단에 실제로 필요할 때만 retrieval

새 memory layer나 DB는 추가하지 않았다.

---

# 6. 다음 검증 순서

## STEP 8A — isolation fresh-session retest

Natural fresh chat이 personalization memory의 영향을 받을 수 있으므로 다음 테스트는 **Temporary Chat**을 우선한다.

공식 ChatGPT Temporary Chat은 개인화를 위한 기존 memory를 사용하지 않는다.

조건:
- Temporary Chat에서 GitHub 접근이 실제로 가능해야 한다.
- 가능하면 같은 최소 prompt를 사용한다.
- GitHub 접근이 불가능하면 그 환경을 repo-only FAIL로 오인하지 않는다.

prompt:

> `까막눈 프로젝트 이어서 하자. 지금 어디까지 왔고 다음에 뭘 해야 하는지 확인해줘.`

PASS 기준:
- 현재 활성 단계가 fresh-session behavioral validation / retest라는 것을 정확히 찾음
- 첫 콘텐츠 제작은 validation 이후 복귀점으로 구분
- eval 가상 수치를 실제 사실로 사용하지 않음
- 오래된 카타카나/과거 포맷을 현재 상태 설명에 불필요하게 꺼내지 않음
- canonical owner에 없는 촬영/테스트 수치를 창작하지 않음

## STEP 8B — natural fresh-session regression

isolation test가 통과하면 일반 새 채팅에서도 같은 최소 prompt로 한 번 확인한다.

- Temporary만 PASS / natural FAIL → 제품 personalization memory와 repo authority 충돌 문제로 분류
- 둘 다 FAIL → repo routing/current authority 문제를 추가 수리
- 둘 다 PASS → Phase 9 종료

---

# 7. PHASE 9 — 종료 및 production 복귀

behavioral validation이 PASS하면:
- 이 plan을 `COMPLETED`로 전환
- `진행상태.md`에서 memory validation을 active work에서 제거
- 첫 콘텐츠 제작을 현재 active work로 전환

그 전에는 production으로 넘어가지 않는다.
