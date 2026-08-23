# CONTEXT / MEMORY TARGET ARCHITECTURE

> 상태: **PHASE 3 TARGET LOCKED — RED TEAM PASS**
> 작성일: 2026-08-23
> 설계 기준: `기록/CONTEXT_MEMORY_RESEARCH_2026-08.md` + `기록/CONTEXT_MEMORY_REPO_AUDIT.md`
> 목적: 새 세션이 최소한의 startup context만 읽고도 현재 상태를 정확히 복원하고, 필요한 판단·절차·과거 근거를 스스로 찾아가며, 사용자가 별도 인수인계 작업을 하지 않게 한다.
>
> 이 문서는 **목표 구조 명세**다. 아직 기존 active memory/process 파일을 수정한 것은 아니다. 실제 구조 변경은 Phase 4 rollback 확보 뒤 Phase 5에서만 한다.

---

# 1. Phase 3 시작 시 freshness check

Phase 3 시작 직전 최신 공개 연구를 다시 확인했다.

- `StateMemBench / StateMem`(2026-08-20)은 current state와 superseded state를 명시적으로 분리하는 state-first 구조가 기존 memory backend 위에서도 큰 개선을 낼 수 있음을 보고한다.
- `Supersede`(2026-06)는 더 큰 memory 자체가 supersession 문제를 해결하지 못하며, 오래된 값을 현재값으로 쓰지 않는 능력이 별도 문제임을 보여준다.
- `A-TMA`(2026-07)는 old/current/transition fact가 같은 bank에 공존할 때 발생하는 ghost memory를 분리해 평가한다.

이 추가 검색은 Phase 1~2 방향을 뒤집는 새 반대근거를 만들지 않았다. 따라서 아래 설계는 **Phase 1 연구 + Phase 2 실제 repo audit**에서 이미 나온 요구사항을 기준으로 확정한다.

---

# 2. BEFORE — 현재 구조의 핵심 문제

현재 구조는 좋은 memory layer를 이미 갖고 있지만 ownership과 routing이 겹친다.

```text
startup
  ↓
CLAUDE
PROJECT_RULES
PLANNING_PROCESS
JUDGMENT
USER_CONTEXT
진행상태
DECISIONS
(+ 첫콘텐츠/장비 문서)
```

문제는 다음 네 가지로 압축된다.

1. **fixed preload** — task와 무관해도 core 7문서를 읽는다.
2. **mutable duplication** — 첫 콘텐츠·촬영·장비·현재 우선순위가 여러 문서에 복제된다.
3. **current-state conflict** — `진행상태.md`와 active refactor plan처럼 서로 다른 현재값이 동시에 존재할 수 있다.
4. **historical ambiguity** — `DECISIONS.md`의 과거 `확정`이 이후 refactor로 대체돼도 명시적 supersession이 약하다.

고치지 않는 것:
- repository를 memory substrate로 쓰는 것
- raw `기록/`, `실측/`, git history 보존
- `PLANNING_PROCESS.md` / `JUDGMENT.md` 계층 자체
- 별도 vector/graph DB가 없는 것
- 별도 active memory repo가 없는 것

---

# 3. AFTER — 목표 구조

새 active memory product나 새 DB를 추가하지 않는다. **기존 파일의 역할을 좁히고 읽기 경로를 바꾼다.**

```text
                 ┌───────────────────┐
                 │ AGENTS.md         │
                 │ small router/map  │
                 └─────────┬─────────┘
                           │
                minimal policy bootstrap
                           ▼
        ┌─────────────────────────────────┐
        │ CLAUDE.md + PROJECT_RULES.md    │
        │ common + durable invariants     │
        └────────────────┬────────────────┘
                         │ request-dependent
                         ▼
                ┌───────────────────┐
                │ 진행상태.md       │
                │ project current   │
                │ state + pointers  │
                └─────────┬─────────┘
                          │ active plan / domain route
        ┌─────────────────┼──────────────────────┐
        ▼                 ▼                      ▼
 active execution   stable/procedural       domain owner
 plan if present    /judgment memory        first-content / gear
        │                 │                      │
        └─────────────────┴───────────┬──────────┘
                                      │ evidence/history needed
                                      ▼
                         DECISIONS / 기록 / 실측 / git
                         historical + raw evidence
```

핵심 원칙:

> **현재값은 작은 canonical owner가 갖고, 나머지는 pointer 또는 필요 시 retrieval로 연결한다.**

---

# 4. 파일별 canonical ownership

| 파일 | AFTER 역할 | 현재값 소유 여부 | startup 기본 로드 |
|---|---|---:|---:|
| `AGENTS.md` | **BOOTSTRAP / ROUTER**. 무엇을 언제 읽는지만 안내 | 아니오 | 예 |
| `CLAUDE.md` | immutable common behavior | 아니오 | 예. harness가 이미 주입하면 중복 fetch 금지 |
| `PROJECT_RULES.md` | durable project-wide invariants / failure prevention | 아니오 | 예 |
| `진행상태.md` | **PROJECT-LEVEL CURRENT STATE**. 현재 우선순위, active work, active-plan pointer, immediate next action | **예** | 진행 중 프로젝트 질문이면 예 |
| active execution plan | 해당 작업의 phase / local execution state | **예 — task-local only** | `진행상태`가 가리킬 때만 |
| `USER_CONTEXT.md` | stable user/project declarative context만 | 장기 안정 정보만 | 필요할 때 |
| `PLANNING_PROCESS.md` | major planning procedure만 | 아니오 | major planning일 때 |
| `JUDGMENT.md` | reusable judgment principles / business-content evaluation reasons | 아니오 | 판단이 필요한 major planning일 때 |
| `첫콘텐츠_계획.md` | first-content detailed domain owner | first-content domain 안에서만 | first-content 작업일 때 |
| `장비세팅.md` | gear/recording detailed domain owner | gear domain 안에서만 | 장비 작업일 때 |
| `DECISIONS.md` | chronological decision transition/history | **현재값 owner 아님** | 과거 이유/변경 확인 때만 |
| `README.md` | static repository overview + canonical pointers | 아니오 | 필수 아님 |
| `계획.md` | historical archive | 아니오 | 필요할 때만 |
| `기록/` | raw/synthesized historical records, research | 아니오 | 필요할 때만 |
| `실측/` | raw measured evidence | 아니오 | evidence 필요할 때만 |
| git history | temporal source / rollback / provenance | 아니오 | conflict/provenance 필요할 때만 |

## 4.1 `진행상태.md`가 소유할 것

현재처럼 상세 protocol 전체를 복제하지 않는다.

최소 schema:

```text
기준 시각
프로젝트 최우선
현재 활성 작업
활성 execution plan: <path 또는 없음>
현재 blocker / unresolved
바로 다음 행동
관련 domain pointer
```

중요:
- active plan의 세부 phase 번호까지 `진행상태.md`가 독립적으로 복제하지 않는다.
- `진행상태.md`는 **활성 계획이 무엇인지**만 소유하고, 그 계획 내부 단계는 active plan이 소유한다.
- active plan이 끝나면 `진행상태.md`의 pointer를 제거하고 프로젝트 최우선을 다음 상태로 갱신한다.

이렇게 하면 현재 발생한 `진행상태 vs REFACTOR_PLAN` 충돌을 구조적으로 줄일 수 있다.

---

# 5. Bootstrap flow

사용자가 별도 bootstrap prompt를 관리하지 않는다.

## 5.1 기본 시작

```text
1. AGENTS.md 확인
2. common/project invariant 필요량만 로드
   - CLAUDE.md
   - PROJECT_RULES.md
3. 현재 요청 분류
4. 현재 프로젝트를 이어가는 요청이면 진행상태.md 확인
5. 진행상태에 active plan이 있으면 그 plan 확인
6. 요청 종류에 따라 필요한 memory만 추가 로드
```

## 5.2 query routing

### `이 프로젝트 이어서 하자`, `다음 뭐하지`, 현재 작업 질문

```text
진행상태
→ active plan이 있으면 active plan
→ 필요한 domain doc
```

### 새 콘텐츠/포맷/큰 방향 판단

```text
진행상태
→ PLANNING_PROCESS
→ JUDGMENT
→ USER_CONTEXT가 적합성 판단에 필요하면 추가
→ 해당 domain / evidence 필요 시 추가
```

### 첫 콘텐츠 세부

```text
진행상태
→ 첫콘텐츠_계획
→ 판단 문제면 PLANNING_PROCESS/JUDGMENT 추가
```

### 장비/OBS/촬영 세팅

```text
진행상태가 현재 선택 상태에 필요하면 확인
→ 장비세팅
→ 외부 최신 사실이면 웹/공식 자료
```

### `왜 이렇게 정했지?`, 과거 변경 이유

```text
현재 owner 먼저 확인
→ DECISIONS
→ 필요하면 기록/git history
```

### 실측/시장 근거가 필요한 판단

```text
현재 owner / domain owner
→ 관련 실측
→ 필요하면 web/current external evidence
```

원칙:

> **검색 결과에서 old archive 한 줄을 찾았다고 current truth로 바로 사용하지 않는다.**

---

# 6. Retrieval flow

별도 vector DB/graph DB를 도입하지 않는다.

```text
1. canonical owner를 먼저 확인
2. 질문에 필요한 정확한 file/domain을 route
3. 근거가 부족하면 repository search
4. 찾은 결과의 날짜·상태·owner를 확인
5. historical/raw 결과면 current owner와 충돌 여부 확인
6. 필요하면 주변 context / git history까지 확장
7. 충분하면 중단
```

검색 우선순위:

1. current canonical owner
2. relevant stable/procedural/domain doc
3. `DECISIONS.md`
4. `기록/` / `실측/`
5. git history

단, 사용자가 **과거 원문/실측 자체를 묻는 경우**에는 해당 raw source로 직접 간다.

---

# 7. Write / update flow

memory write는 답변보다 엄격하게 취급한다.

```text
새 정보/결정
  ↓
무슨 종류인가?
  ├─ project current state 변경 → 진행상태 owner 갱신
  ├─ active task phase 변경 → active plan만 갱신
  ├─ stable user/project context → USER_CONTEXT
  ├─ reusable invariant → PROJECT_RULES admission 후
  ├─ reusable planning procedure → PLANNING_PROCESS admission 후
  ├─ reusable judgment principle → JUDGMENT admission 후
  ├─ domain detail → 해당 domain owner
  ├─ 의미 있는 decision transition → DECISIONS history 추가
  └─ 일회성 대화/실패 → canonical write 안 함
```

## 7.1 admission rule

permanent memory로 승격하려면 최소한:

- 앞으로 다시 쓰일 가능성이 있는가
- source/evidence가 분명한가
- 현재 canonical owner가 어디인지 정해져 있는가
- 기존 상위 원칙으로 이미 설명되는가
- mutable detail을 invariant로 잘못 승격하는 것은 아닌가

를 본다.

**default는 `write하지 않음`에 가깝게 둔다.**

## 7.2 current + history 동시 변경

중요한 current-state 변경은:

- current owner에 새 값을 반영하고
- 장기적으로 의미 있는 변화일 때만 `DECISIONS`에 transition을 남긴다.

`DECISIONS`는 새 현재값의 두 번째 owner가 아니다. 사건 기록이다.

README에는 current-state 변경을 복제하지 않는다.

---

# 8. stale / supersede flow

## 8.1 명확한 supersession

예:
- mask → face-visible
- 14 attack axes → 5 bundles
- active priority A → active priority B

처리:

```text
current owner = 새 값
DECISIONS = old → new transition을 기록
old raw/archive = 삭제하지 않음
read-time = current owner 우선
```

Phase 5에서는 현재 audit에서 실제 확인된 14축→5 bundle 같은 **known ambiguous historical item**만 최소한 명시적으로 대체 표시한다. 저장소 전체 history를 새 schema로 소급 변환하지 않는다.

## 8.2 애매한 conflict

모든 충돌을 강제로 supersession 처리하지 않는다.

- 시간/맥락/출처에 따라 둘 다 맞을 수 있음
- 사용자의 선호가 상황별로 다를 수 있음
- 어떤 선택이 최종인지 실제로 확인되지 않음

이 경우:

```text
UNRESOLVED / CONTEXT-DEPENDENT
```

로 유지하고 임의로 current truth를 만들지 않는다.

## 8.3 stale archive guard

`기록/`, `계획.md`, git history는 evidence이지 current authority가 아니다.

historical source가 current owner와 다르면:
- history를 지우지 않는다.
- current query에는 current owner를 사용한다.
- 사용자가 변화 이유를 물을 때만 두 상태를 함께 설명한다.

---

# 9. 실제 Phase 5 수정 명세

Phase 5에서는 아래 범위를 넘지 않는다.

## 9.1 `AGENTS.md`

- fixed 7-document preload 제거
- small router/progressive disclosure로 변경
- current / major planning / first-content / gear / history / evidence route만 유지
- 정책 원문 복제 최소화

## 9.2 `PROJECT_RULES.md`

- durable invariant만 유지
- parked 반복듣기 구현 규칙과 current first-content implementation detail 제거/owner pointer로 교체
- session-start route 중복 제거
- universal web-search rule 등 실제 durable project rule은 이번 memory refactor 이유만으로 건드리지 않음

## 9.3 `USER_CONTEXT.md`

- first-content/gear/current candidate 같은 mutable state 제거
- 장기 사용자/프로젝트 성향과 협업 기준만 유지

## 9.4 `진행상태.md`

- project-level canonical current-state 형식으로 축약
- 현재 memory refactor를 active work로 반영
- active plan pointer = `CONTEXT_MEMORY_REFACTOR_PLAN.md`
- 상세 촬영/장비 recipe는 domain pointer로 대체

## 9.5 `JUDGMENT.md`

- 사업 목적, 클릭/시청/내구성/제작통제, 학습자·실험자 포지션, 질문/결과 중심 등 reusable principle 유지
- first-content 전용 protocol/diagnosis/reveal details는 domain owner에 이미 있는지 확인 후 제거
- 중요한 이유를 잃지 않되 current case를 permanent principle처럼 유지하지 않음

## 9.6 `PLANNING_PROCESS.md`

- procedural-memory 역할 유지
- general invariant와 겹치는 문장은 실제 중복일 때만 정리
- RED TEAM 구조 자체를 다시 재설계하지 않음

## 9.7 `DECISIONS.md`

- history 역할을 header에서 명확화: current truth는 current/domain owner를 우선
- known superseded ambiguity만 최소 수정
- 모든 과거 row에 ID/graph metadata를 소급 추가하지 않음

## 9.8 `README.md`

- static overview + canonical pointer 중심
- current filming/boot-order mirror 제거

## 9.9 `첫콘텐츠_계획.md`

- detailed first-content owner로 유지
- 다른 core files에서 세부 복제가 사라졌는지 확인
- 필요 이상의 구조 변경 없음

## 9.10 `장비세팅.md`

- gear owner로 유지
- 첫콘텐츠 촬영 protocol의 중복 부분은 pointer/짧은 전제로 축소
- gear detail 자체는 유지

## 9.11 archive/evidence/tools

- `계획.md`, 기존 `기록/`, `실측/`, `도구/`, git history는 구조 변경하지 않는다.

## 9.12 `CLAUDE.md`

- **immutable block 포함 수정하지 않는다.**

---

# 10. Expected context / latency cost

정확한 token/latency 개선율은 구현 전 숫자로 만들지 않는다. Phase 7에서 동일 조건으로 측정한다.

구조적으로 기대되는 변화:

### BEFORE

- task와 무관하게 7 core docs preload
- 첫콘텐츠/gear면 추가 문서
- mutable detail이 여러 문서에 반복돼 같은 사실을 여러 번 읽음

### AFTER

일반 project continuation:

```text
small AGENTS/router
+ durable rules
+ 진행상태
+ active plan if present
```

major planning일 때만:

```text
+ PLANNING_PROCESS
+ JUDGMENT
+ 필요하면 USER_CONTEXT/domain evidence
```

따라서 **간단한 작업은 더 적게 읽고, 복잡한 작업은 필요한 만큼만 깊게 읽는 구조**가 된다.

추가 tool call이 생기는 대신 startup preload가 줄어든다. 어느 쪽이 실제 latency/quality에 유리한지는 Phase 7에서 측정한다.

---

# 11. 제거하는 complexity

이번 구조가 **추가하는 것보다 제거하는 것**이 더 많아야 한다.

제거/축소 대상:

- startup 7문서 일괄 preload
- README의 operational current-state mirror
- USER_CONTEXT의 mutable current state
- PROJECT_RULES의 current domain implementation detail
- JUDGMENT의 first-content-specific working detail
- 장비세팅의 first-content protocol 복제
- 진행상태의 상세 domain recipe 복제
- DECISIONS를 current state owner처럼 쓰는 관행

추가하는 active system:

- **새 DB 없음**
- **새 active repo 없음**
- **새 permanent memory layer 없음**
- 기존 `진행상태`에 active-plan pointer/owner semantics를 강화하는 정도

---

# 12. RED TEAM

## 공격 1 — 너무 적게 읽어서 판단력이 떨어지지 않는가?

가능한 위험이다.

수리:
- `이어서 하자`처럼 project-state-dependent request는 반드시 `진행상태 → active plan`을 읽는다.
- major planning은 `PLANNING_PROCESS + JUDGMENT`를 route한다.
- user fit이 실제 판단에 필요할 때 `USER_CONTEXT`를 추가한다.

즉 **preload를 없애는 것이 아니라 task-dependent retrieval로 이동**한다.

판정: 수리 가능, 구조 유지.

---

## 공격 2 — tool call 수가 늘어 latency가 더 나빠질 수 있지 않은가?

그럴 수 있다. file-based agentic retrieval 연구도 accuracy와 latency tradeoff가 있다.

수리:
- canonical owner를 먼저 읽어 search fan-out을 줄인다.
- archive search는 근거가 실제로 필요할 때만 한다.
- exact budget은 구현 전에 임의로 고정하지 않고 Phase 7에서 측정한다.

판정: 남은 측정 불확실성. architecture blocker 아님.

---

## 공격 3 — `진행상태`와 active plan이 다시 두 current owner가 되는 것 아닌가?

그럴 수 있으므로 ownership을 다르게 고정한다.

- `진행상태` = **project-level active work + pointer**
- active plan = **그 작업 내부 phase/local state**

`진행상태`가 plan phase를 다시 복제하지 않는다.

판정: 해결.

---

## 공격 4 — DECISIONS의 오래된 `확정`이 여전히 검색될 수 있다.

맞다.

수리:
- DECISIONS header에서 current authority가 아님을 명시.
- read-time에 current owner를 먼저 확인.
- audit에서 실제 확인한 known superseded ambiguity만 최소 annotation.
- 모든 historical row를 새 schema로 전환하는 과잉 migration은 하지 않는다.

판정: 구조적으로 충분. 실제 eval에서 stale revival을 확인한다.

---

## 공격 5 — JUDGMENT를 줄이면 과거에 힘들게 얻은 판단 이유가 유실되지 않는가?

삭제 기준을 `첫 콘텐츠 관련이냐`로 단순 적용하면 유실될 수 있다.

수리:
- **reusable principle은 유지**한다.
- first-content-specific detail은 `첫콘텐츠_계획` 또는 DECISIONS/raw history에 실제 보존돼 있는지 확인한 뒤 중복만 제거한다.
- 정보가 한 곳에도 남지 않는다면 삭제하지 않는다.

판정: surgical migration으로 해결.

---

## 공격 6 — 새로운 schema와 metadata를 만들다가 다시 bureaucracy가 되지 않는가?

가장 큰 과잉설계 위험이다.

수리:
- 새 DB/graph/ID system 없음.
- current-state 최소 필드만 사용.
- 모든 decision에 ID를 소급 부여하지 않음.
- explicit supersession도 실제 충돌이 확인된 것과 앞으로의 의미 있는 transition에만 사용.

판정: complexity 감소가 명확함.

---

## 공격 7 — 사용자에게 새로운 의식/ritual을 요구하는가?

아니다.

사용자 입력 목표:

> `이 프로젝트 이어서 하자.`

AI가 repo 접근이 가능한 환경에서 AGENTS/current state/active plan을 스스로 읽어야 한다.

사용자가 transfer block, bootstrap prompt, 테스트 정답표를 운반하지 않는다.

판정: PASS.

---

## 공격 8 — GitHub access가 없는 새 세션에서도 자동으로 되나?

아니다. 이것은 architecture가 제거할 수 없는 제품/도구 경계다.

명시적 제한:

> **이 설계가 보장하는 자동 bootstrap 범위는 해당 session/agent가 `kkamaknun` repository를 읽을 수 있는 환경이다.**

repo access가 없으면 과거 state를 본 것처럼 추측하지 않고 접근 불가를 말해야 한다.

판정: limitation accepted. 거짓 자동화 약속을 하지 않는다.

---

## 공격 9 — 모델의 현재 능력을 과소평가해 harness를 과도하게 만드는가?

새 retrieval engine, vector DB, graph, background consolidator를 추가하지 않는다.

현재 모델이 파일을 직접 찾고 읽을 수 있다는 전제에서 **owner + route만 명확하게 만든다.**

판정: PASS.

---

# 13. 남은 불확실성

아키텍처를 막는 미해결 설계 질문은 없다. 다만 구현 후 실제로 측정해야 할 것이 있다.

1. startup context 감소가 실제 응답 latency를 얼마나 줄이는가
2. query-dependent retrieval이 필요한 file을 놓치는 빈도가 있는가
3. current/superseded conflict가 cold-start에서 실제로 줄어드는가
4. JUDGMENT distillation 후 판단 재현성이 유지되는가
5. tool access가 있는 일반 ChatGPT 새 세션에서 bootstrap이 얼마나 일관되게 실행되는가

이것들은 Phase 6~7 eval 대상이며, Phase 3에서 임의 숫자로 해결하지 않는다.

---

# 14. Exit Gate P3

### 모델 현재 능력을 과소평가해 unnecessary scaffolding을 만드는가?

**NO.** 새 memory engine/DB를 만들지 않고 기존 file ownership과 router만 단순화한다.

### retrieval call이 과도하게 늘어나는 구조인가?

**NO — 설계상 bounded.** default full preload를 줄이고 canonical owner → task-dependent file → raw evidence 순으로 확장한다. 실제 latency는 Phase 7 측정 대상이다.

### stale state가 다시 살아날 경로가 남아 있는가?

**완전히 0이라고 보장하지 않는다.** 그러나 current owner 우선, active-plan ownership 분리, history 비권위화, explicit known supersession으로 현재보다 경로를 줄인다. 남은 오류는 cold-start eval로 검증한다.

### 하나의 사실을 두 군데에서 관리하게 만드는가?

**NO.** pointer/역사 기록은 허용하지만 mutable current value의 canonical owner는 하나로 고정한다.

### 사용자에게 새로운 ritual을 요구하는가?

**NO.** 사용자는 memory 운영자가 아니다.

### 기존 구조보다 나아질 근거가 있는가?

**YES.** Phase 1의 small bootstrap/progressive disclosure/state-first/raw-evidence 원칙과 Phase 2에서 실제 확인된 over-preload, mutable duplication, current conflict, supersession ambiguity를 직접 해결한다.

## 최종 판정

**Exit Gate P3: PASS.**

다음 단계:

> **PHASE 4 — 현재 main을 정확한 rollback 기준점으로 고정한 뒤에만 Phase 5 구조 수정을 시작한다.**
