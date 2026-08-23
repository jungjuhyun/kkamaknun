# CONTEXT / MEMORY REPOSITORY AUDIT

> 상태: **PHASE 2 AUDIT COMPLETE**
> 작성일: 2026-08-23
> 감사 기준 head: `d887f92165654fc0c464154feb6352d5e11ba01e`
> 상위 계획: `CONTEXT_MEMORY_REFACTOR_PLAN.md`
> 연구 기준: `기록/CONTEXT_MEMORY_RESEARCH_2026-08.md`
>
> 목적: 현재 `kkamaknun` 저장소가 새 세션에 **현재 상태 + 장기 맥락 + 판단 기준 + 작업 절차 + 과거 근거**를 넘기는 방식에서 실제로 어디가 잘 되어 있고, 어디가 중복·stale·over-preload·ownership 혼합을 일으키는지 확인한다.
>
> 이 문서는 **진단 결과**다. 아직 목표 아키텍처나 실제 수정안을 확정하지 않는다. 실제 구조 수정은 Phase 3 설계/RED TEAM과 Phase 4 rollback 확보 뒤에만 한다.

---

## 1. 감사 방법과 최신 근거

### 1.1 저장소 감사 범위

다음을 직접 확인했다.

- repository root 및 memory/process 관련 파일 구조
- `AGENTS.md`
- `CLAUDE.md` + immutable 보호 workflow
- `PROJECT_RULES.md`
- `PLANNING_PROCESS.md`
- `JUDGMENT.md`
- `USER_CONTEXT.md`
- `진행상태.md`
- `DECISIONS.md`
- `README.md`
- `첫콘텐츠_계획.md`
- `장비세팅.md`
- `계획.md`
- `기록/` 전체 항목과 역할
- `실측/` 전체 항목과 역할
- `도구/` 전체 항목과 역할
- memory/process 구조가 만들어지고 변경된 최근 git history

`실측/`와 `도구/`는 현재 boot memory가 아니라 cold evidence / operational tools이므로, memory architecture 감사에서는 **각 파일의 존재·역할·현재 라우팅 상태**를 중심으로 확인했다. 콘텐츠 내용 자체의 시장·코드 정확성 재감사는 이번 Phase 2 범위가 아니다.

### 1.2 Phase 2 시작 시 추가 확인한 최신 연구

Phase 1을 닫은 뒤에도 단계 시작 시 최신 검색을 다시 실시했다. 새로 나온 근거 중 Phase 3 설계에 직접 영향을 줄 수 있는 것은 다음이다.

#### StateMemBench / StateMem — 2026-08-20

- Xinyi Fan et al., **Can Agent Memory Systems Track Evolving State?**
- https://arxiv.org/abs/2608.19652
- 핵심: 장기 memory의 중요한 실패는 과거 사실을 못 찾는 것만이 아니라 **현재값 대신 superseded value를 다시 사용하는 것**이다.
- StateMem은 supersession과 relational dependency를 명시적으로 추적한다.
- 같은 backbone 대비 current-state accuracy를 1.8배, 비교된 strongest memory system 대비 1.6배 개선했다고 보고한다.
- 기존 여섯 memory/retrieval backend 위에 lightweight state-first wrapper를 얹었을 때 +32~+67pt 향상을 보고하며, length/cost-matched control에서도 +15~+32pt가 state structure 자체에 귀속됐다.

**우리 감사에 주는 의미:** `현재 상태가 어디에 있는가`, `무엇이 무엇을 대체했는가`, `과거 확정이 아직 살아 있는가`를 명시적으로 볼 필요가 있다.

#### OpenAI Agents SDK memory — 현재 공식 문서

- https://openai.github.io/openai-agents-python/sandbox/memory/
- memory read는 **progressive disclosure**를 사용한다.
- startup에는 작은 `memory_summary.md`만 주고, 필요할 때 `MEMORY.md`를 검색한 뒤, 더 자세한 정보가 필요할 때만 `rollout_summaries/`를 연다.
- memory가 stale할 수 있으므로 현재 환경을 우선하도록 지시하고, stale memory를 발견하면 갱신할 수 있다.
- memory write도 raw conversation → extraction → consolidation의 다단계로 나눈다.

**우리 감사에 주는 의미:** 현재 `AGENTS.md`의 고정 7문서 preload와 비교해야 한다. 또 raw history와 distilled memory의 역할을 분리해야 한다.

#### TANGLE — 2026-08-14

- Lu Yang et al., **When Personal Memory Has No Single Answer**
- https://arxiv.org/abs/2608.13921
- 모든 충돌이 supersession으로 해결되는 것은 아니다.
- 맥락·시간·출처 권위가 부족하면 conflict가 실제로 underdetermined일 수 있으며, 한쪽을 current truth로 강제하면 잘못된 확신이 된다.

**우리 감사에 주는 의미:** Phase 3에서 `current state`는 명확한 수정/철회 관계에는 강하게 적용하되, 맥락 의존 선호나 애매한 충돌까지 억지로 단일 값으로 만들면 안 된다.

---

# 2. 현재 구조 한눈에 보기

현재 구조는 이미 다음 요소를 갖고 있다.

```text
AGENTS.md                 startup / routing + 일부 policy
CLAUDE.md                 vendored common behavior
PROJECT_RULES.md           project failure-prevention policy
PLANNING_PROCESS.md        procedural memory
JUDGMENT.md                judgment criteria + accumulated reasons/cases
USER_CONTEXT.md            user/project context + 현재 state 일부
진행상태.md                current-state handoff
DECISIONS.md               chronological decisions/history
README.md                  overview + current state + boot instructions mirror
첫콘텐츠_계획.md            first-content domain plan/state
장비세팅.md                 gear plan/state + filming protocol 일부
계획.md                     historical legacy plan
기록/                       raw/synthesized historical records + research
실측/                       raw evidence
도구/                       operational scripts
Git history                temporal raw evidence / change history
```

**중요한 판단:** 저장소를 외부 memory substrate로 쓰는 발상 자체가 문제는 아니다. 오히려 Phase 1 연구와 잘 맞는다. 현재 문제는 **정보 소유권과 읽기 경로가 겹친 것**이다.

---

# 3. 파일별 감사

## 3.1 `AGENTS.md`

### 현재 역할

- BOOTSTRAP / ROUTER
- 문서 우선순위
- 주요 기획 self-review 연결
- 종료 시 write routing

### 잘 된 점

- raw `기록/`, `실측/`, `계획.md`를 필요할 때만 보도록 이미 구분한다.
- current state는 `진행상태.md`와 `DECISIONS.md`를 우선한다고 적어 historical volume에 끌려가지 않게 한다.
- 파일별 역할을 명시해 최소한의 routing 개념은 이미 있다.

### 실제 문제

**A1 — startup fixed preload가 크다.**

현재는 모든 project work 시작 전에 다음 7개를 순서대로 **반드시 전부 읽는다.**

`CLAUDE → PROJECT_RULES → PLANNING_PROCESS → JUDGMENT → USER_CONTEXT → 진행상태 → DECISIONS`

그 뒤 첫 콘텐츠면 `첫콘텐츠_계획`, 장비면 `장비세팅`까지 더 읽는다.

이는 Phase 1에서 확인한 OpenAI/Anthropic의 `small high-signal startup → 필요할 때 progressive disclosure` 방향과 충돌한다. 특히 단순 번역·장비 한 항목·짧은 전술 질문에도 긴 JUDGMENT/DECISIONS/PLANNING_PROCESS를 모두 읽는 구조다.

**A2 — router와 policy가 부분적으로 섞여 있다.**

AGENTS는 어디를 읽을지 정하는 map 역할 외에, major-plan 제출 규칙, 판단 보존 규칙, write policy 일부도 직접 가진다. 당장 치명적이지 않지만 Phase 3에서 owner를 명확히 할 필요가 있다.

### Phase 3 후보 판정

- **KEEP + REFACTOR 후보**
- 없애는 것이 아니라 **작은 entry map/router**로 만드는 방향을 우선 검토한다.
- 실제 최소 bootstrap 세트는 Phase 3에서 확정한다.

---

## 3.2 `CLAUDE.md` + immutable CI

### 현재 역할

- 공통 상위 행동 guideline
- immutable vendor block

### 잘 된 점

- immutable 범위가 명시돼 있다.
- `.github/workflows/protect-karpathy-claude.yml`에서 hash로 변경을 감지한다.
- project-specific instruction을 별도 파일로 분리했다.

### 실제 문제

이번 감사에서 **immutable block 자체를 context-memory defect로 볼 근거는 없다.**

다만 이 문서는 coding-oriented general guideline이므로 프로젝트 memory architecture의 system-of-record로 확장해서는 안 된다.

### Phase 3 후보 판정

- **KEEP / immutable block 수정 금지**
- Phase 3에서도 구조 문제 해결 대상으로 삼지 않는다.

---

## 3.3 `PROJECT_RULES.md`

### 의도된 역할

- durable project invariant / failure-prevention policy

### 실제 들어 있는 정보

1. durable evidence/judgment rules
2. universal web-search requirement
3. answer/decision behavior
4. major planning self-review routing
5. **보류 중인 반복듣기 포맷의 구현 규칙**
6. session-start routing
7. **현재 첫 콘텐츠 전용 규칙**

### 잘 된 점

- 사용자 압박을 근거로 취급하지 않는 규칙은 일반화된 failure-prevention invariant로 적절하다.
- 확인하지 않은 파일/기능을 봤다고 말하지 않는 규칙도 durable invariant다.
- 세부 planning stages를 여기 복제하지 않고 `PLANNING_PROCESS.md`로 위임하도록 이미 정리했다.

### 실제 문제

**P1 — invariant file에 domain-specific mutable rules가 들어 있다.**

`기존 반복듣기 포맷 — 검색·매칭 규칙`과 `현재 첫 콘텐츠 관련 규칙`은 프로젝트 전체에서 항상 필요한 invariant가 아니다.

특히 첫 콘텐츠의 작품 후보, 진단 방식, 후속편 구조 같은 내용은 바뀔 수 있고 `첫콘텐츠_계획.md` 및 `진행상태.md`에도 존재한다.

**P2 — startup routing도 AGENTS와 겹친다.**

세션 시작 절이 다시 `AGENTS.md`의 읽기 흐름을 설명한다.

### Phase 3 후보 판정

- **KEEP + SCOPE REDUCTION 후보**
- durable failure-prevention invariant만 남기는 방향을 우선 검토한다.
- domain rule은 domain owner로 이동/참조하는 것이 유력하지만 Phase 3에서 확정한다.

---

## 3.4 `PLANNING_PROCESS.md`

### 현재 역할

- PROCEDURAL MEMORY
- major planning workflow

### 잘 된 점

- `어떻게 기획할지`와 `무엇이 좋은 기획인지`를 개념적으로 분리한다.
- create → attack → repair → re-attack 과정이 짧아졌고, 무한 검토 금지까지 포함한다.
- write target mapping이 있어 세션 종료 시 정보를 어디에 남길지 기준을 준다.
- evidence grade와 maintenance principle이 있다.
- 단일 실패마다 새 규칙을 추가하지 말라는 maintenance 원칙은 AgentRunbook-C V2의 strict strategy-note admission과 방향이 같다.

### 실제 문제

**PP1 — 일부 judgment/evidence principles가 `PROJECT_RULES`와 겹친다.**

`근거보다 강하게 결론내리지 않는다`, `원하는 결론에 맞춰 검증하지 않는다` 같은 원칙은 planning process 내부에서 필요한 판정 logic이지만, 일부는 general evidence policy와 의미가 겹친다.

이것은 현재 즉시 제거해야 할 defect라고 단정할 정도는 아니다. Phase 3에서 다음 기준으로 owner를 정해야 한다.

- 모든 작업에 적용되는 invariant → PROJECT_RULES
- major planning 판정 단계에서만 필요한 procedure → PLANNING_PROCESS
- 콘텐츠가 강한 이유/평가 가치 → JUDGMENT

### Phase 3 후보 판정

- **KEEP / 핵심 구조 보존 가능성이 높음**
- 정확한 중복만 정리하고, 새 layer를 추가할 근거는 현재 없다.

---

## 3.5 `JUDGMENT.md`

### 의도된 역할

- durable judgment criteria / reusable reasoning

### 실제 들어 있는 정보

- 최상위 사업 목적
- 주인공 포지션
- 질문/결과 중심 콘텐츠 원칙
- **첫 콘텐츠 이중 구조**
- **첫 콘텐츠 재미 발생 위치**
- **첫 콘텐츠 촬영/진단 방식**
- **첫 콘텐츠 후속 엔진**
- 반복 패턴 대응
- 축적된 판단 이유와 사례

### 잘 된 점

- 결론만이 아니라 `왜`를 보존하려는 방향은 procedural/judgment memory 연구와 맞는다.
- 사업 목적, 결과 내구성, 제작 통제, 학습자/실험자 포지션 등은 장기 재사용 가치가 높다.
- 특정 판단의 이유를 설명하는 examples는 fresh model이 decision boundary를 복원하는 데 가치가 있다.

### 실제 문제

**J1 — durable judgment와 current first-content design이 섞여 있다.**

예를 들어 `첫 콘텐츠의 이중 구조`, `소리를 따라 말하기`, `진단 순서`, `후속 콘텐츠 엔진`, `반복 공개 방식`은 첫 영상/현재 시리즈에 강하게 묶여 있다. 같은 내용이 `첫콘텐츠_계획.md`, `진행상태.md`, `DECISIONS.md`에도 있다.

그 결과:

- unrelated task에서도 JUDGMENT를 preload하면 첫 콘텐츠 세부가 context를 차지한다.
- first-content design이 바뀌면 JUDGMENT까지 동기화해야 한다.
- historical case와 reusable principle의 경계가 약해진다.

**J2 — case를 principle로 승격하는 admission gate가 문서 구조상 명확하지 않다.**

PLANNING_PROCESS maintenance에는 `단일 사례마다 규칙을 늘리지 말라`가 있지만, JUDGMENT 자체에는 `이 판단은 reusable principle인가 / current case인가 / superseded case인가`를 구조적으로 표시하는 최소 schema가 약하다.

### Phase 3 후보 판정

- **KEEP + DISTILLATION 후보**
- durable judgment principle을 중심으로 유지하고, project-specific 사례는 reference/case로 분리하거나 domain 문서에 남기는 방향을 검토한다.
- 새로운 거대 taxonomy는 만들지 않는다.

---

## 3.6 `USER_CONTEXT.md`

### 의도된 역할

- STABLE USER / PROJECT CONTEXT

### 실제 들어 있는 정보

초반에는 장기 맥락이 잘 들어 있다.

- 사업 목표
- 일본어 배경
- 협업 방식
- 제작/콘텐츠 성향

하지만 후반에는 다음 mutable state가 들어 있다.

- 현재 첫 콘텐츠 방향
- 귀멸의 칼날 유력 후보
- 현재 촬영 protocol
- 현재 얼굴 공개 방향
- 현재 화면 구성
- OBS track 방향
- 현재 스탠드/볼헤드 후보
- 현재 반복듣기 포맷 우선순위

### 실제 문제

**U1 — stable context와 mutable state가 명백히 혼합돼 있다.**

이것은 이번 감사에서 가장 확실한 ownership defect 중 하나다.

동일한 first-content / gear state가 `진행상태`, `첫콘텐츠_계획`, `장비세팅`, `README`, `DECISIONS`에도 있다.

### Phase 3 후보 판정

- **KEEP + MUTABLE STATE REMOVAL 후보**
- 장기적으로 잘 변하지 않는 사용자/프로젝트 정보만 남기는 방향이 강하게 유력하다.

---

## 3.7 `진행상태.md`

### 의도된 역할

- CURRENT CANONICAL STATE / handoff

### 잘 된 점

- 지금 하는 일, next action, first-content current decisions를 한눈에 볼 수 있다.
- 과거 archive를 현재로 오인하지 않도록 현재 우선순위를 명시한다.

### 실제 문제

**S1 — 이번 refactor 자체가 시작되면서 이미 current-state divergence가 발생했다.**

`진행상태.md`는 여전히:

- `기획 판단 체계 자체를 계속 손보는 단계는 종료했다`
- `최우선은 첫 콘텐츠 실제 촬영·편집`
- 다음 행동은 OBS test → 촬영 진행

이라고 한다.

하지만 현재 실제 실행은 `CONTEXT_MEMORY_REFACTOR_PLAN.md`에 의해 **PHASE 2 memory architecture audit** 상태다.

즉 현재 repo에는 동시에:

```text
진행상태.md
→ 시스템 작업 종료 / 촬영 단계

CONTEXT_MEMORY_REFACTOR_PLAN.md
→ memory refactor EXECUTING PHASE 2
```

라는 서로 다른 current state가 존재한다.

이것은 이론적인 stale-risk가 아니라 **현재 실제로 발생한 state-tracking failure**다.

StateMemBench의 최신 결과가 지적하는 `current state vs superseded state` 문제와 직접 연결된다.

**S2 — current state file이 domain details를 너무 많이 복제한다.**

filming protocol, diagnosis categories, editing tactics, equipment details가 domain files에도 거의 같은 형태로 있다. current state의 목적이 `지금 어디까지 / 다음에 무엇`이라면 세부 recipe 전체를 다시 보유할 필요가 있는지 Phase 3에서 검토해야 한다.

### Phase 3 후보 판정

- **KEEP / canonical-current 역할을 더 강하게 만들 후보**
- task-local execution plan이 활성화됐을 때 current state가 그것을 가리키도록 하는 state-first flow가 필요하다.
- 구체적 schema는 Phase 3에서 확정한다.

---

## 3.8 `DECISIONS.md`

### 현재 역할

- DECISION HISTORY
- 일부 current-status lookup

### 잘 된 점

- `확정 / 현재 우선 / 유력 후보 / 보류 / 철회`를 표시한다.
- 날짜순으로 변화 이유를 추적할 수 있다.
- mask→face, HelloTalk→anime 등 실제 decision history가 보존돼 있다.

### 실제 문제

**D1 — 명시적 supersession link가 없다.**

같은 주제가 바뀔 때 예전 row가 `철회`로 바뀌는 경우도 있지만, 모든 후속 refactor가 old decision의 status를 다시 써주지는 않는다.

구체적인 사례:

- `DECISIONS.md`에는 2026-08-23 기획 공정의 주요 공격 기준을 `클릭 / 시청 지속 / 사건 밀도 / ... / 근거 수준`의 **14개 축**으로 `확정` 기록한 항목이 남아 있다.
- 현재 `PLANNING_PROCESS.md`는 그 뒤 refactor되어 **5개 bundle**로 통합됐다.

역사적으로 14축 기록이 남는 것은 정상이다. 문제는 그 항목 자체가 `SUPERSEDED`나 `대체됨: ...` 없이 여전히 `확정`으로 보인다는 것이다.

새 세션이 DECISIONS를 current authority로 읽으면 둘 중 어느 것이 현재인지 chronology와 다른 문서까지 해석해야 한다.

**D2 — decision history와 current state가 일부 겹친다.**

`현재 우선` 항목이 계속 쌓이면 DECISIONS가 history이면서 동시에 current-state registry 역할을 하게 된다. 명확한 current owner가 약해진다.

### Phase 3 후보 판정

- **KEEP + EXPLICIT SUPERSESSION 후보**
- stable decision ID / superseded-by 같은 최소 관계가 필요한지 검토한다.
- full database나 복잡한 graph는 현재 근거상 필요 없다.

---

## 3.9 `README.md`

### 의도된 역할

- 사람/에이전트가 repository를 이해하는 overview

### 실제 들어 있는 정보

- 프로젝트 설명
- 현재 첫 콘텐츠 질문/포맷
- 현재 process
- 새 session boot order
- 파일 역할 table
- current filming/gear state

### 실제 문제

**R1 — README가 operational state mirror가 되어 있다.**

현재 상태와 boot order가 `진행상태.md`, `AGENTS.md`와 다시 복제된다.

이 구조는 한 번의 변경에 README도 같이 갱신해야 하므로 stale mirror가 되기 쉽다.

### Phase 3 후보 판정

- **KEEP + STATIC OVERVIEW 후보**
- 프로젝트 개요와 canonical pointers 중심으로 줄이고, current details를 mirror하지 않는 방향을 검토한다.

---

## 3.10 `첫콘텐츠_계획.md`

### 현재 역할

- FIRST-CONTENT DOMAIN PLAN / detailed working memory

### 잘 된 점

- 첫 영상에서 실제로 필요한 protocol, diagnosis, editing logic, current candidate를 한 domain file에 모아두고 있다.
- 파일 머리에 상태와 마지막 갱신일이 있다.
- 사용자 보고와 AI 직접 확인 여부를 구분한다.

### 실제 문제

파일 자체보다 **다른 core memory 파일들이 이 내용을 복제**하는 것이 문제다.

이 파일은 상세 domain owner로 남을 가치가 높다. 다만 Phase 3에서 current state와 stable design의 경계를 정할 때 `진행상태`가 이 파일의 상세를 다시 복사하지 않고 pointer로 연결할 수 있는지 검토한다.

### Phase 3 후보 판정

- **KEEP 가능성 높음**

---

## 3.11 `장비세팅.md`

### 현재 역할

- GEAR DOMAIN PLAN / current gear state

### 잘 된 점

- OBS tracks, camera, stand, lighting, recording format 등 장비 세부가 모여 있다.
- 본촬영 전 verification checklist가 있어 execution evidence와 잘 연결된다.

### 실제 문제

**G1 — gear file이 first-content filming protocol을 다시 소유한다.**

문서 첫 부분에:

- 자막 OFF
- SPACE
- 일본어 소리 재현
- pilot correction

등 비장비 protocol이 반복된다.

이는 `첫콘텐츠_계획`, `진행상태`, `USER_CONTEXT`의 내용과 중복이다.

**G2 — gear current state도 여러 파일에 복제된다.**

OBS 3 tracks, webcam 유지, stand/ballhead 후보 등이 `USER_CONTEXT`, `진행상태`, `README`, `DECISIONS`에도 있다.

### Phase 3 후보 판정

- **KEEP + SCOPE CLEANUP 후보**
- 장비 자체의 detailed owner로 좁히는 방향을 검토한다.

---

## 3.12 `계획.md`

### 현재 역할

- ARCHIVE / historical design

### 잘 된 점

문서 맨 위에 이미 명확히:

- `2026-08-20 이전 설계 기록`
- `상태: 과거 설계 / 현재 우선순위 아님`
- current priority는 `진행상태.md`와 `DECISIONS.md`
- 과거의 `주력` 문구는 현재 지시가 아님

이라고 표시돼 있다.

이는 stale memory 방지 관점에서 **좋은 archival pattern**이다.

### Phase 3 후보 판정

- **KEEP / 소급 rewrite 금지**

---

## 3.13 `기록/`

현재 확인된 항목:

- `2026-08-20_밤_답변정리.md`
- `2026-08-21_GPT_동기화.md`
- `CONTEXT_MEMORY_RESEARCH_2026-08.md`
- 이번 audit 문서

### 잘 된 점

과거 기록들은 `현재 상태 판단은 진행상태/DECISIONS 우선`처럼 archive 성격을 명시한다.

예를 들어 2026-08-21 기록에는 현재와 반대인 `얼굴 공개를 원하지 않는다 / mask test` 상태가 남아 있지만, 이것은 당시 history이며 현재로 읽지 말라는 header가 있다.

이는 raw episodic evidence를 삭제하지 않고 보존하되 현재 state와 구분한다는 Phase 1 원칙과 잘 맞는다.

### 위험

archive의 내부 문장은 stale할 수 있으므로 **retrieval 결과를 current truth로 바로 쓰면 안 된다.** agent가 archive status + 날짜 + current state를 같이 확인해야 한다.

### Phase 3 후보 판정

- **KEEP AS COLD MEMORY**
- 모든 record를 startup preload하지 않는다.

---

## 3.14 `실측/`

현재 디렉터리는 시장, 작품, 자막창고, 재료량, 경쟁채널 등 직접 수집한 raw evidence를 보존한다.

### 잘 된 점

- boot memory와 분리돼 있다.
- `AGENTS.md`도 필요할 때만 조회하도록 한다.
- 현재 main first-content와 관련 없는 오래된 반복듣기 실측이 많아도 그것이 current priority로 자동 승격되지 않게 이미 문서 경계가 있다.

### Phase 3 후보 판정

- **KEEP AS RAW EVIDENCE / ON-DEMAND RETRIEVAL**
- 지금 단계에서 vector DB/graph DB로 옮겨야 한다는 증거 없음.

---

## 3.15 `도구/`

현재 Python utilities는 자막/표현/유튜브 실적 등 실제 작업을 위한 operational tool이다.

### 판정

- **MEMORY LAYER 아님**
- 현재 context-memory refactor에서 구조 변경할 이유 없음.
- 필요 작업에서만 route하면 된다.

---

## 3.16 Git history

### 현재 역할

- 시간순 raw change evidence
- 과거 판단과 수정 과정의 최종 원본

### 관찰

최근 history에는:

- planning process 생성
- judgment framework 생성
- transfer test에서 발견한 판단 오류 수정
- process refactor
- stale docs cleanup
- universal web-search rule
- 현재 context-memory research plan

이 짧은 기간에 빠른 state transition이 많이 있다.

### 판정

- **valuable cold evidence**
- 하지만 current state substitute로 사용하면 안 된다.
- 명시적 current owner를 먼저 보고, 이유/원본 추적이 필요할 때 git history를 조회하는 것이 맞다.

---

# 4. 중복 지도 — 현재 가장 큰 구조 문제

아래는 같은 계열 정보가 여러 owner에 복제된 실제 예다.

| 정보 | 현재 나타나는 주요 위치 |
|---|---|
| 첫 콘텐츠 목적/훅 | USER_CONTEXT / 진행상태 / JUDGMENT / README / 첫콘텐츠_계획 / DECISIONS / PROJECT_RULES 일부 |
| 촬영 protocol | USER_CONTEXT / 진행상태 / JUDGMENT / 첫콘텐츠_계획 / 장비세팅 / README / DECISIONS |
| `말하기 전에 SPACE` 보정 | 진행상태 / 첫콘텐츠_계획 / 장비세팅 / README / DECISIONS |
| 얼굴 공개/화면 방향 | USER_CONTEXT / 진행상태 / 장비세팅 / README / DECISIONS |
| OBS 3-track/gear 상태 | USER_CONTEXT / 진행상태 / 장비세팅 / README / DECISIONS |
| planning process | AGENTS / PROJECT_RULES / PLANNING_PROCESS / README / DECISIONS / 진행상태 일부 |
| 판단 이유 | PROJECT_RULES / PLANNING_PROCESS / JUDGMENT / DECISIONS 일부 |
| current priority | USER_CONTEXT / 진행상태 / README / DECISIONS + 현재는 REFACTOR_PLAN까지 |

이 표는 `복제가 많으니 무조건 하나만 남긴다`는 결론이 아니다.

- **canonical owner**는 하나가 필요하다.
- 다른 문서에는 필요한 경우 `pointer / 짧은 summary`가 있을 수 있다.
- 그러나 지금은 같은 mutable 문장을 여러 곳에서 독립적으로 관리하고 있어 owner가 불명확하다.

---

# 5. 실제로 이미 발생한 stale / supersession 사례

## 사례 1 — 현재 작업 자체의 충돌

`진행상태.md`:

> 시스템/판단 체계 작업 종료 → 촬영으로 이동

현재 `CONTEXT_MEMORY_REFACTOR_PLAN.md`:

> context-memory refactor EXECUTING PHASE 2

**판정:** 실제 current-state conflict. Phase 3에서 해결해야 한다.

## 사례 2 — planning attack axes

historical `DECISIONS.md`:

> 14개 주요 공격 기준을 `확정`

current `PLANNING_PROCESS.md`:

> refactor 후 5개 bundle

**판정:** 역사 자체는 보존 가치가 있으나 old `확정`이 명시적으로 superseded되지 않아 read-time ambiguity가 있다.

## 사례 3 — 얼굴 비공개 과거 기록

`기록/2026-08-21_GPT_동기화.md`에는 face-hidden/mask state가 있고, 현재 state/decisions에는 face-visible로 변경된 기록이 있다.

**판정:** archive header가 있어 현재는 비교적 안전하다. 이것은 **좋은 raw-history preservation 사례**다. 다만 retrieval agent가 archive를 현재 truth로 쓰지 않는 guard는 필요하다.

---

# 6. 연구 failure mode와 현재 repo의 실제 대응 관계

| 연구 failure mode | 현재 repo 상태 |
|---|---|
| long-context / over-preload | **실제 위험 있음** — startup 7 core docs + domain docs |
| current vs superseded state | **실제 failure 관찰됨** — 진행상태 vs active refactor plan |
| stale memory | **부분 방어됨** — archive banners는 좋지만 core mutable duplication 존재 |
| conflict resolution | **부분 방어됨** — 철회 status는 있으나 explicit supersession relation이 불완전 |
| procedural memory | **강점** — PLANNING_PROCESS가 이미 있음 |
| judgment transfer | **강점 + 혼합 문제** — JUDGMENT가 존재하나 first-content detail이 섞임 |
| raw evidence preservation | **강점** — 기록/실측/git history 보존 |
| retrieval strategy | **부분 구현** — AGENTS의 on-demand rule은 있으나 core는 fixed preload |
| write quality | **부분 구현** — maintenance rules 있음, 하지만 여러 canonical mirror 업데이트 필요 |
| user burden | **방향은 좋음** — repo self-bootstrap 목표. 다만 현재 구조는 문서 동기화 burden이 시스템 측에 큼 |

---

# 7. 고치지 말아야 할 것 / 과잉 리팩터링 방지

이번 전수 감사에서 다음은 **현재 근거만으로 defect라고 볼 수 없다.**

1. repository 자체를 memory substrate로 쓰는 것
2. `CLAUDE.md` immutable block
3. raw `기록/`과 `실측/`을 보존하는 것
4. `계획.md`를 historical archive로 남기는 것
5. `PLANNING_PROCESS.md`라는 별도 procedural-memory 문서가 존재하는 것
6. `JUDGMENT.md`라는 judgment-memory 계층 자체가 존재하는 것
7. Git history를 cold evidence로 유지하는 것
8. 현재 규모에서 vector DB / graph DB가 없는 것
9. 별도 active repository를 만들지 않는 것

즉 Phase 3의 목표는 `새 memory 제품을 더 얹기`보다 **이미 있는 파일의 ownership과 routing을 단순화하는 것**이 먼저다.

---

# 8. Phase 3로 넘길 실제 설계 요구사항

아래는 audit에서 실제로 나온 요구사항이며 아직 구현안은 아니다.

1. **current state는 명확한 canonical owner 하나가 있어야 한다.**
2. task-local active plan이 생기면 canonical current state가 그것을 가리키거나 상태를 갱신해야 한다.
3. superseded decision은 chronology 추론에만 맡기지 않고 최소한의 explicit relation을 검토해야 한다.
4. `AGENTS` startup은 fixed full preload가 아니라 small boot + query-dependent retrieval을 우선 설계한다.
5. `USER_CONTEXT`에서 mutable project state를 분리한다.
6. `PROJECT_RULES`에서 parked-format/current-video implementation detail을 분리한다.
7. `JUDGMENT`는 reusable principle과 current case/detail의 경계를 강화한다.
8. README는 current state/boot sequence의 독립 mirror가 되지 않도록 한다.
9. first-content/gear domain files는 자기 domain의 detailed owner 역할을 하고 다른 domain protocol을 복제하지 않게 한다.
10. raw history/evidence는 보존하고, retrieval 시 archive/current authority를 구분한다.
11. clear supersession과 genuinely underdetermined conflict를 구분한다. 모든 conflict를 억지로 하나의 current value로 만들지 않는다.
12. 구조를 줄이는 것이 목표이지 새 schema/file 수를 늘리는 것이 목표가 아니다.

---

# 9. Phase 2 Exit Gate P2

### 1. repository root와 memory 관련 파일을 전수 확인했는가?

**YES.**

root, core memory/process documents, current domain docs, records/evidence/tool directories, immutable protection, recent memory/process git history를 확인했다.

### 2. `전부`, `N개`, `유일` 같은 폐쇄형 표현을 실제 확인 없이 사용했는가?

**NO.**

확인 범위와 content-audit 범위를 구분했다. 특히 `실측/`와 `도구/`는 memory architecture상 역할/라우팅 감사를 했으며 개별 시장 데이터나 Python 코드의 정확성 재감사는 이번 범위가 아님을 명시했다.

### 3. 문제를 만들어내기 위해 억지 defect를 추가했는가?

**NO.**

실제 중복, 실제 current-state conflict, 실제 superseded ambiguity, 실제 fixed preload에 한정했다. `CLAUDE`, archive raw evidence, tools, vector DB 부재 등은 근거 없는 defect로 만들지 않았다.

### 4. 연구 failure mode와 repo의 실제 문제가 연결되는가?

**YES.**

특히:

- over-preload ↔ AGENTS fixed seven-document startup
- state tracking ↔ 진행상태 vs active refactor plan conflict
- supersession ↔ DECISIONS old `확정` vs refactored process
- stale/write quality ↔ mutable facts copied across many files
- progressive disclosure ↔ raw evidence는 이미 cold, core documents는 아직 fixed preload

으로 직접 대응한다.

## 최종 판정

**Exit Gate P2: PASS.**

다음 단계는 **PHASE 3 — Phase 1 연구 + 이 audit만을 근거로 target architecture를 설계하고 RED TEAM하는 것**이다.

아직 기존 memory/process architecture 파일은 수정하지 않았다.
