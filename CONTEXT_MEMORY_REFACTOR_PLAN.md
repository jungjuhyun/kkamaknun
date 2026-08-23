# CONTEXT / MEMORY REFACTOR PLAN

> 상태: **PHASE 7 PARTIAL — STRUCTURAL PASS / BEHAVIORAL VALIDATION PENDING**
> 작성일: 2026-08-23
> 역할: context/memory refactor의 task-local 기록. **현재 active production plan은 아님.**
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
- 이 plan 자체 — 완료 연구의 장문 복제를 제거하고 실행 상태 중심으로 축약

의도적으로 유지:
- `CLAUDE.md` unchanged
- `PLANNING_PROCESS.md` unchanged
- `첫콘텐츠_계획.md` detailed domain owner 유지
- `계획.md`, 기존 `기록/`, `실측/`, `도구/`, git history 보존

새 DB, graph, 별도 active memory repository, background consolidator는 추가하지 않았다.

---

# 4. PHASE 7 — 현재 판정

## 4.1 Static / structural verification

**PASS**

확인된 것:

1. BEFORE의 `AGENTS.md`는 project work마다 `CLAUDE / PROJECT_RULES / PLANNING_PROCESS / JUDGMENT / USER_CONTEXT / 진행상태 / DECISIONS`를 고정 preload하도록 요구했다.
2. AFTER의 `AGENTS.md`는 request classification 뒤 current/planning/domain/history/evidence 문서를 필요할 때만 읽도록 바뀌었다.
3. BEFORE에서 실제로 존재했던 `진행상태 = 시스템 작업 종료 / 촬영 단계`와 `active refactor plan = memory 작업 진행` 충돌은 제거했다.
4. current project state와 task-local phase ownership을 분리했다.
5. mutable first-content/gear state를 stable core memory에서 제거하고 domain owner로 돌렸다.
6. `DECISIONS.md`의 old 14-axis `확정`과 fixed-preload history에 명시적 `대체됨` 관계를 추가했다.
7. baseline→현재 compare에서 `CLAUDE.md`, `PLANNING_PROCESS.md`, `첫콘텐츠_계획.md`는 refactor 대상이 아니었고 raw archive/evidence도 보존됐다.
8. rollback baseline과 backup branch가 남아 있다.

### 정적 context-size 방향

BEFORE에서 `AGENTS.md`가 강제하던 startup 문서 중 `진행상태.md`를 제외하고도 알려진 파일 크기 합계가 53,825 bytes였다. 실제 mandatory boot는 여기에 `진행상태.md`까지 더해졌다.

AFTER의 기본 router/common-project-policy 세트(`AGENTS + CLAUDE + PROJECT_RULES`)는 13,226 bytes이며, current/planning/domain/history 문서는 request에 따라 추가한다.

이것은 **file-size 기준의 구조적 비교**일 뿐 token/latency 성능 측정으로 과장하지 않는다.

## 4.2 Behavioral blind cold-start verification

**PENDING**

현재 이 세션의 도구에는 독립된 fresh ChatGPT session을 자동 생성해 동일 model/config/tool 조건으로 BEFORE/AFTER를 blind 실행하는 기능이 없다.

따라서:
- 같은 세션에서 cold-start를 흉내내고 PASS라고 선언하지 않는다.
- 사용자를 수동 eval 운영자로 만들지 않는다.
- `기록/CONTEXT_MEMORY_EVAL_SPEC.md`의 locked cases는 향후 실제 fresh-session evidence를 평가할 기준으로 보존한다.

## 4.3 Phase 7 최종 판정

**PARTIAL — structural improvement verified, behavioral evidence pending.**

이 PARTIAL은 현재 architecture failure가 관찰됐다는 뜻이 아니다.
**검증 환경이 isolated behavioral evidence를 제공하지 못한다는 한계**다.

---

# 5. Phase 8 처리

**진입하지 않는다.**

이유:
- 실제 behavioral failure가 아직 관찰되지 않았다.
- tool limitation을 architecture defect로 바꿔 새 rule/layer를 만드는 것은 근거가 없다.
- 새 실패가 확인되기 전에는 추가 memory architecture 수정 금지.

향후 natural fresh session에서 실제 routing/stale/judgment failure가 확인될 때만 해당 failure class를 분석하고 제한적으로 수리한다.

---

# 6. Production 복귀 결정

memory refactor가 실제 콘텐츠 제작을 계속 막는 것은 목표 위반이다.

따라서 현재 구조는 **provisionally adopted** 상태로 사용하고, behavioral validation은 실제 fresh-session 기회에서 비용 없이 축적한다.

사용자에게:
- 새 채팅 생성 의무
- bootstrap prompt 복사
- context-transfer block 운반
- 10개 eval case 수동 실행/채점

을 요구하지 않는다.

현재 project-level active work는 다시 **첫 콘텐츠 촬영·편집**으로 돌린다. `진행상태.md`가 현재 복귀 지점을 소유한다.

---

# 7. 종료 조건

이 refactor를 `COMPLETED`로 올리는 조건은 실제 repo 접근 가능한 fresh session에서 최소한 다음이 확인되는 것이다.

- current state를 stale history보다 우선
- 필요한 domain/procedure를 스스로 retrieval
- 사용자의 오래된 premise나 압박에 근거 없이 끌려가지 않음
- repo에 있는 기본 맥락을 사용자에게 다시 요구하지 않음

한 번의 clean run은 가능성의 증거이지 무조건적인 안정성 증명으로 과장하지 않는다.

그 전까지 상태는:

> **STRUCTURAL PASS / BEHAVIORAL VALIDATION PENDING — NO FURTHER ARCHITECTURE WORK WITHOUT REAL FAILURE**
