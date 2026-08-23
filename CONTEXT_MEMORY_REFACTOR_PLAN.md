# CONTEXT / MEMORY REFACTOR PLAN

> 상태: **PLAN LOCKED — EXECUTING PHASE 1**
> 작성일: 2026-08-23
> 기준 main: `511ca72fa141777dca846e6bcc9c5116653ef89d`
> 목적: 긴 대화에서 축적된 **프로젝트 맥락 + 현재 상태 + 판단 기준 + 작업 절차 + 실패 경험**을 새 채팅/새 세션이 가능한 한 적은 사용자 개입으로 복원하도록 `kkamaknun`의 외부 기억 구조를 연구 기반으로 리팩터링한다.

이 문서는 이번 리팩터링의 **실행 계획이자 순서 잠금 장치**다. 계획에 정의된 단계와 Exit Gate를 통과하기 전에 다음 단계로 넘어가지 않는다.

`CLAUDE.md`의 `BEGIN IMMUTABLE KARPATHY GUIDELINES` ~ `END IMMUTABLE KARPATHY GUIDELINES` 구간은 이번 작업에서도 절대 수정하지 않는다.

---

## 0. 문제 정의

이번 작업의 문제는 `GPT 사용법`을 사용자에게 더 많이 가르치는 것이 아니다.

목표는 다음과 같다.

> **사용자는 평소처럼 프로젝트 이야기를 이어가고, 새 세션의 AI가 저장소를 스스로 읽고 필요한 과거 근거를 찾아 현재 상태와 판단 방식을 복원한다.**

새 채팅으로 옮길 필요가 생기는 이유는 긴 단일 대화가 무한히 안정적인 작업공간이 아니기 때문이다. 긴 context에서는 관련 정보 사용 성능이 저하될 수 있고, 장기 작업은 여러 context window / session을 넘나들게 된다. 따라서 프로젝트의 장기 상태를 채팅 자체에만 의존하지 않고 외부 system of record에 보존한다.

### 성공 기준

리팩터링 성공은 문서 개수나 규칙 개수로 판단하지 않는다.

1. **State recovery** — 새 세션이 지금 어디까지 왔는지 정확히 복원한다.
2. **Dynamic state tracking** — 과거 상태와 현재 상태를 구별한다.
3. **Judgment transfer** — 결론만이 아니라 중요한 판단 기준과 이유를 재현한다.
4. **Workflow knowledge** — 주요 기획에서 정해진 작업 절차를 사용한다.
5. **Gotcha avoidance** — 반복해서 확인된 AI 실패를 다시 밟지 않는다.
6. **Premise resistance** — 오래된 전제나 사용자의 압박을 새 근거처럼 받아들이지 않는다.
7. **Selective retrieval** — 모든 기록을 preload하지 않고 필요한 증거를 찾아온다.
8. **Low user burden** — 사용자가 별도 인수인계 프롬프트·복사·QA 작업을 반복하지 않는다.
9. **Low context overhead** — 기억 시스템 자체가 실제 프로젝트보다 context를 과도하게 점유하지 않는다.
10. **Maintainability** — 새 정보가 들어왔을 때 어디를 고쳐야 하는지 명확하고 stale 복제가 늘어나지 않는다.

---

## 1. 연구 우선 원칙

이번 리팩터링의 기술 결정은 사용자 취향이나 즉흥적 AI 추론으로 정하지 않는다.

### 증거 우선순위

1. **현재 공식 엔지니어링 자료 / 제품 문서**
   - OpenAI
   - Anthropic
2. **동료평가 논문 / 주요 학회 자료**
   - ACL / TACL / ICML 등
3. **최신 arXiv 연구 + 공개 benchmark / reproducible implementation**
4. **실제 오픈소스 구현 및 benchmark leaderboard**
5. 블로그·커뮤니티 글은 보조 자료로만 사용

기술 판단이 충돌할 경우 `최신성`만으로 결정하지 않고, **우리 workload와 얼마나 직접적으로 맞는지 + 실험 근거 + 구현 비용 + 유지 비용**을 함께 본다.

각 단계 시작 시 웹 검색으로 최신 업데이트가 없는지 다시 확인한다.

---

## 2. 현재까지 확보한 핵심 연구 근거

아래는 계획 작성 전에 실시한 1차 딥리서치에서 반복적으로 확인된 방향이다. 이 목록은 Phase 1에서 더 확장·검증한다.

### 2.1 Context는 큰 창이 아니라 제한된 자원으로 취급

- Anthropic, **Effective context engineering for AI agents** (2025-09-29)
  - 핵심: 가장 작은 high-signal context를 구성한다.
  - preload보다 just-in-time retrieval을 우선한다.
  - long-horizon 작업에서 compaction, structured memory, sub-agent architecture를 사용한다.
  - https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents

- Liu et al., **Lost in the Middle** (TACL 2024)
  - 긴 context가 있다고 해서 전체 위치의 정보를 동일하게 잘 활용하지 않는다.
  - https://aclanthology.org/2024.tacl-1.9/

- Chroma, **Context Rot** (2025)
  - input token 증가 자체가 여러 모델에서 성능 저하와 연결되는 현상을 실험.
  - https://research.trychroma.com/context-rot

### 2.2 긴 작업은 외부 상태 + 세션 handoff가 필요

- Anthropic, **Effective harnesses for long-running agents** (2025-11-26)
  - 새 session이 이전 session을 모른다는 문제를 명시.
  - progress file, git history, structured handoff를 사용.
  - https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents

- Anthropic, **Long-running Claude for scientific computing** (2026)
  - `CHANGELOG.md` 같은 progress file을 portable long-term memory로 사용.
  - current status, completed tasks, failed approaches, limitations를 남긴다.
  - https://www.anthropic.com/research/long-running-Claude

### 2.3 Repository/filesystem은 좋은 memory substrate이지만 정리 자체가 답은 아님

- OpenAI, **Harness engineering: leveraging Codex in an agent-first world** (2026-02-11)
  - repository knowledge를 system of record로 사용.
  - 큰 `AGENTS.md`는 실패했고, 짧은 map + structured docs + progressive disclosure로 전환.
  - complex work는 execution plan, progress, decision log를 repository에 보존.
  - https://openai.com/index/harness-engineering/

- Zhou et al., **Filesystem-Based Memory for LLM Agents** (2026-07)
  - filesystem 조직화는 대규모 store에서 retrieval cost를 줄이는 데 유효.
  - 그러나 조직화 자체가 자동으로 answer accuracy를 높이지는 않음.
  - store 조직도 시간이 지나며 붕괴할 수 있어 maintenance가 필요.
  - https://arxiv.org/abs/2607.26637

### 2.4 단순 RAG보다 agentic file retrieval이 강한 경우가 있음

- Wu et al., **LongMemEval-V2** (2026-05)
  - 5개 memory 능력: static state, dynamic state, workflow, gotchas, premise awareness.
  - 최대 115M token history를 대상으로 memory system 평가.
  - AgentRunbook-C(file-based coding-agent retrieval)가 강한 accuracy/latency frontier를 보임.
  - https://arxiv.org/abs/2605.12493
  - https://xiaowu0162.github.io/longmemeval-v2/

- **AgentRunbook-C V2** (2026-08 update)
  - 모델이 좋아지면서 harness orchestration을 오히려 줄임.
  - file search/read 중심의 lightweight controller.
  - 반복 검색 경험을 작은 persistent strategy note로 consolidation.
  - https://xiaowu0162.github.io/longmemeval-v2/agentrunbook-c-v2/

### 2.5 stale memory / conflict resolution은 별도의 핵심 문제

- Chao et al., **STALE** (2026-05)
  - 단순히 새 정보를 retrieval하는 것과, 오래된 전제를 행동에서 버리는 것은 다름.
  - 평가축: State Resolution / Premise Resistance / Implicit Policy Adaptation.
  - best evaluated system도 전체 55.2% 수준으로 어려운 문제.
  - https://arxiv.org/abs/2605.06527

- Reddy & Challaram, **Don't Ask the LLM to Track Freshness** (2026-06)
  - 단순 current-value conflict에서는 LLM judgment만 맡기지 않고 명시적 version/timestamp resolution이 유리할 수 있음을 제시.
  - broader QA에는 query-type-aware handling 필요.
  - https://arxiv.org/abs/2606.01435

### 2.6 memory에 잘못 저장하면 오류가 증폭됨

- Xiong et al., **How Memory Management Impacts LLM Agents** (ACL 2026)
  - experience-following 특성.
  - error propagation / misaligned experience replay 문제.
  - memory addition/deletion quality 관리가 중요.
  - https://aclanthology.org/2026.acl-long.27/

### 2.7 판단/작업 절차는 procedural memory로 따로 다룰 가치가 있음

- Belikova et al., **Managing Procedural Memory in LLM Agents** (2026-06)
  - 반복 업무에서 reusable skill/procedure memory가 성능 개선.
  - local improvement뿐 아니라 일부 cross-task / cross-model transfer 확인.
  - 모든 skill이 보편적인 것은 아니며 workload-specific specialization 존재.
  - https://arxiv.org/abs/2606.23127

### 2.8 eval은 실제 production-like cold start로 분리해야 함

- Anthropic, **Demystifying evals for AI agents** (2026-01)
  - eval 환경을 isolated하게 유지.
  - shared state가 성능을 인위적으로 높일 수 있음.
  - real failures에서 task를 수집하고 transcript를 직접 검토.
  - eval saturation과 harness artifact를 경계.
  - https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents

### 2.9 harness는 모델 발전에 따라 줄어들어야 할 수도 있음

- Anthropic, **Scaling Managed Agents** (2026-04)
  - harness는 모델이 못한다고 가정한 scaffolding이며 그 가정은 모델 발전으로 stale해질 수 있음.
  - stable interface와 교체 가능한 harness를 분리.
  - https://www.anthropic.com/engineering/managed-agents

### 2.10 cost / latency도 memory architecture의 일부

- Omri et al., **Agent Memory: Characterization and System Implications** (2026-06)
  - construction / retrieval / generation 비용을 분리해 봐야 함.
  - freshness-latency, query volume, write/read tradeoff가 존재.
  - https://arxiv.org/abs/2606.06448

### 2.11 memory synthesis / consolidation도 별도의 설계 문제

- OpenAI, **Dreaming: Better memory for a more helpful ChatGPT** (2026-06-04)
  - 장기 memory의 핵심 목표를 useful context carry-forward, preference/constraint following, staying current로 평가한다.
  - saved memory만으로는 stale/incorrect/irrelevant해질 수 있어 chat history에서 memory state를 자동 합성·갱신하는 구조를 사용한다.
  - freshness, continuity, relevance와 scalability를 memory architecture의 직접 목표로 둔다.
  - https://openai.com/index/chatgpt-memory-dreaming/

이 자료는 우리 repository가 제품 수준의 background synthesis를 그대로 구현해야 한다는 근거가 아니다. Phase 1에서는 **deterministic canonical state와 synthesized/consolidated memory의 경계를 어디에 둘지**, 그리고 자동 요약이 provenance·정확성·freshness를 해치지 않도록 어떤 제한이 필요한지를 별도로 검토한다.

---

## 3. 이번 작업의 잠정 설계 가설 — 아직 확정 아님

Phase 1~3을 통과하기 전에는 아래를 구현하지 않는다.

현재 연구가 가리키는 가장 유력한 방향은 다음이다.

```text
SMALL BOOTSTRAP / ROUTER
        ↓
CURRENT CANONICAL STATE
        ↓ 필요할 때
DURABLE DECLARATIVE + PROCEDURAL MEMORY
        ↓ 근거 필요할 때
RAW HISTORY / EVIDENCE / GIT HISTORY
```

잠정 원칙:

- repository 자체는 계속 system of record로 사용한다.
- 새 active repository를 별도로 만들지 않는다.
- backup은 리팩터링 전 rollback용 안전장치일 뿐 active system이 아니다.
- 큰 preload보다 progressive disclosure / selective retrieval을 우선 검토한다.
- 하나의 사실에는 가능한 한 canonical owner 하나를 둔다.
- current state와 history를 분리한다.
- 판단 원칙과 개별 사례를 분리한다.
- write 시 memory quality를 검사하고, 모든 대화/실패를 규칙으로 승격하지 않는다.
- stale / superseded state를 명시적으로 처리한다.
- raw history는 삭제하지 않고 cold evidence로 보존한다.
- 모델 발전으로 필요 없어진 scaffolding은 제거 가능해야 한다.

**주의:** 이 절은 설계 가설이며, Phase 1 연구 종합과 Phase 2 repo audit 결과에 따라 바뀔 수 있다.

---

# EXECUTION ROADMAP

## PHASE 0 — 계획 잠금

### 작업

- [x] 현재 문제와 성공 기준을 정의한다.
- [x] 1차 딥리서치를 수행한다.
- [x] 현재 repository root와 핵심 문서 구조를 확인한다.
- [x] 이 실행계획을 repository에 기록한다.
- [x] 계획 자체를 한 번 재검토하고 누락된 연구축이 있는지 확인한다.

### Phase 0 재검토 결과 — 2026-08-23

- 기존 계획은 단계 순서, 산출물, Exit Gate, 구조 수정 금지 시점이 명확해 순차 실행 조건을 충족한다.
- 최신 웹 재검색에서 OpenAI의 2026 memory synthesis 연구/제품 발표를 확인했고, 기존 계획에 **memory synthesis / consolidation** 축이 충분히 명시되지 않았다고 판단했다.
- 따라서 Phase 1 연구 질문과 source family에 해당 축을 추가했다.
- 이 변경은 사용자 압박 때문이 아니라 새 공식 1차 자료 확인에 따른 계획 보정이다.
- 기존 memory/process 구조 파일은 아직 수정하지 않았다.

**Exit Gate P0: PASS.**

### Exit Gate P0

다음이 모두 충족돼야 Phase 1로 간다.

- 단계 순서가 명확하다.
- 각 단계의 산출물과 중단 조건이 정의되어 있다.
- 리팩터링 전에 연구·진단·설계를 끝내도록 잠겨 있다.
- 아직 기존 구조 파일을 수정하지 않았다.

---

## PHASE 1 — 딥리서치 및 evidence matrix 확정

**이 단계에 시간을 가장 많이 쓴다.**

### 연구 질문

1. long-context degradation을 실제 workflow에서 어떻게 피하는가?
2. session 간 state를 어떤 형태로 externalize하는가?
3. current state / durable fact / procedure / history를 어떻게 분리하는가?
4. preload와 retrieval의 최적 경계는 무엇인가?
5. file-based agentic retrieval과 RAG의 실제 tradeoff는 무엇인가?
6. stale / conflicting memory를 write-time과 read-time에서 어떻게 처리하는가?
7. procedural/judgment memory를 어떤 granularity로 저장하는가?
8. memory write 정책은 무엇을 저장하고 무엇을 버려야 하는가?
9. retrieval strategy 자체를 학습/보존할 필요가 있는가?
10. cold-start evaluation을 어떻게 설계해야 contamination이 없는가?
11. latency/token overhead를 어느 수준까지 허용할 것인가?
12. 최신 ChatGPT/GitHub connector 환경에서 실제로 구현 가능한 것은 무엇인가?
13. deterministic canonical state와 synthesized/consolidated memory의 경계는 무엇이며, synthesis가 provenance·freshness·correctness를 훼손하지 않게 하려면 어떤 제한이 필요한가?

### 반드시 조사할 source family

- OpenAI 2025~2026 official engineering / product docs
- OpenAI memory synthesis / freshness / continuity 관련 최신 공식 자료
- Anthropic 2025~2026 engineering / research
- ACL 2026 agent memory / memory utilization
- LongMemEval-V2 + AgentRunbook-C V2 source code/benchmark
- STALE / conflict-resolution 계열
- filesystem memory 계열
- procedural memory 계열
- context rot / long-context foundational evidence
- memory systems characterization / cost tradeoff 연구

### 산출물

`기록/CONTEXT_MEMORY_RESEARCH_2026-08.md`

내용:
- 연구별 주장
- evidence level
- 실험 setup
- 우리 문제와 직접 연결되는 부분
- 적용 가능성
- 적용하면 안 되는 부분
- 서로 충돌하는 연구 결과
- 최종 설계 원칙 후보

### Exit Gate P1

- 최소 3개 이상의 서로 다른 연구/실무 계열에서 동일 방향이 수렴하는가?
- 특정 vendor의 한 글만 근거로 결정하고 있지 않은가?
- 2026년 최신 결과가 2024~2025 foundational 결과를 어떻게 수정했는지 확인했는가?
- `우리 workload`와 다른 benchmark 결과를 그대로 일반화하지 않았는가?
- 연구 결과와 AI의 추론을 구분해 기록했는가?

**Gate 불통과 → 연구 계속. 구조 수정 금지.**

---

## PHASE 2 — 현재 `kkamaknun` memory architecture 전수 감사

### 대상

최소 다음 전체를 확인한다.

- `AGENTS.md`
- `CLAUDE.md` — 읽기만 하고 immutable block 수정 금지
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
- `기록/`
- `실측/`
- git history 중 memory/process 관련 변경

### 각 정보의 분류

각 문장/정보 묶음을 다음으로 분류한다.

- BOOTSTRAP / ROUTER
- STABLE USER/PROJECT CONTEXT
- CURRENT STATE
- PROCEDURAL MEMORY
- JUDGMENT / POLICY
- DECISION HISTORY
- RAW EVIDENCE
- ARCHIVE
- DUPLICATE
- STALE / SUPERSEDED
- UNKNOWN / NEEDS REVIEW

### 찾을 문제

- 같은 현재 사실의 복제
- owner가 불명확한 정보
- current와 historical이 섞인 문서
- 영구 규칙에 들어간 일회성 사례
- 판단 기준과 작업 절차의 중복
- 모든 세션에 preload되는 저신호 정보
- 오래된 문장이 현재보다 강하게 보이는 구조
- 업데이트 한 번에 여러 파일을 동시에 고쳐야 하는 구조
- 사용자가 직접 기억 운반/QA를 해야 하는 지점

### 산출물

`기록/CONTEXT_MEMORY_REPO_AUDIT.md`

문서별:
- 현재 역할
- 실제 들어 있는 정보 유형
- 중복 위치
- stale 위험
- 유지 / 이동 / 삭제 / archive 후보
- 근거

### Exit Gate P2

- repository root와 memory 관련 파일을 전수 확인했는가?
- `전부`, `N개`, `유일` 같은 폐쇄형 표현은 실제 전수 확인 후에만 사용했는가?
- 문제를 만들어내기 위해 억지 defect를 추가하지 않았는가?
- 연구에서 중요하다고 한 failure mode와 실제 repo 문제가 연결되는가?

---

## PHASE 3 — 목표 아키텍처 확정

Phase 1 연구 + Phase 2 audit만으로 결정한다.

### 결정해야 할 항목

1. session bootstrap 최소 세트
2. query-dependent routing 규칙
3. 각 memory type의 canonical owner
4. current-state schema
5. decision supersede / conflict 처리
6. procedural memory 저장 granularity
7. judgment memory 저장 granularity
8. raw evidence와 canonical memory 연결 방식
9. memory write/update 정책
10. archive 정책
11. stale detection / freshness 처리
12. retrieval latency/context budget
13. eval interface
14. 모델 변경 시 재검증 조건

### 필수 설계 제약

- 사용자는 memory 운영자가 아니다.
- 새 채팅용 특수 프롬프트를 사용자가 관리하게 하지 않는다.
- `AGENTS.md`를 다시 거대한 매뉴얼로 만들지 않는다.
- 모든 정보를 항상 preload하는 것을 기본으로 두지 않는다.
- 새 파일 추가는 기존 파일 재역할화보다 근거가 강할 때만 한다.
- git history / raw archive를 current state substitute로 사용하지 않는다.
- 단일 실패 사례마다 영구 규칙을 하나씩 늘리지 않는다.
- explicit freshness가 필요한 state는 가능한 한 deterministic하게 다룬다.

### 산출물

`기록/CONTEXT_MEMORY_TARGET_ARCHITECTURE.md`

여기에 반드시 포함:
- BEFORE 구조
- AFTER 구조
- 파일별 canonical ownership
- bootstrap flow
- retrieval flow
- write/update flow
- stale/supersede flow
- 예상 context/latency 비용
- 제거할 기존 complexity
- 남은 불확실성

### Exit Gate P3

RED TEAM을 통과해야 한다.

공격 질문:
- 이 구조가 모델의 현재 능력을 과소평가해 unnecessary scaffolding을 만들고 있지 않은가?
- 너무 많은 retrieval call이 생기지 않는가?
- stale state가 다시 살아날 경로가 남아 있는가?
- 하나의 사실을 두 군데에서 관리하게 만들지 않았는가?
- 사용자에게 새로운 의식/ritual을 요구하는가?
- 간단한 기존 구조보다 실제로 나아질 근거가 있는가?

**Gate 불통과 → Phase 3 안에서만 수정. 아직 repo 구조 수정 금지.**

---

## PHASE 4 — 리팩터링 전 기준점/rollback 확보

이 단계 전까지 구조 파일을 수정하지 않는다.

### 작업

- 현재 main의 정확한 commit SHA 기록
- rollback 가능한 immutable 기준점 생성
- 필요하면 별도 snapshot/backup을 생성
- 실제 수정은 격리된 ref/branch에서 시작할지 최종 결정

백업은 **active second system이 아니라 수술 전 원본 보존**이다.

### 산출물

- backup/snapshot 식별자
- BEFORE commit SHA
- rollback 절차

### Exit Gate P4

- 리팩터링 전체를 버려도 현재 상태를 완전히 복원할 수 있는가?

---

## PHASE 5 — 연구 기반 리팩터링

Phase 3에서 확정한 명세만 구현한다.

### 실행 원칙

- 계획에 없는 architecture 추가 금지.
- 파일을 고치다가 새로운 설계 아이디어가 나오면 즉시 구현하지 않고 Phase 3 명세에 먼저 반영할지 판단.
- 각 commit은 하나의 의미 있는 구조 변경만 담는다.
- `CLAUDE.md` immutable block은 건드리지 않는다.
- historical raw data는 삭제보다 archive/owner 분리를 우선한다.
- 중복 제거 시 정보 손실이 없는지 원본과 diff 확인.

### 예상 수정 후보

**확정 아님. Phase 2~3 결과가 우선한다.**

- `AGENTS.md`: preload list → small router/progressive disclosure 검토
- `USER_CONTEXT.md`: 변동 current-state 제거 검토
- `진행상태.md`: current canonical state 역할 강화 검토
- `DECISIONS.md`: historical/superseded relationship 명확화 검토
- `PROJECT_RULES.md`: invariant만 남도록 정리 검토
- `JUDGMENT.md`: reusable judgment vs specific case 경계 정리 검토
- `PLANNING_PROCESS.md`: procedural memory 역할만 유지 검토
- `README.md`: 새 architecture 설명과 실제 boot flow 일치 여부 갱신

### Exit Gate P5

- Phase 3 명세와 실제 파일 구조가 일치하는가?
- 중복/stale risk가 BEFORE보다 줄었는가?
- preload context가 불필요하게 커지지 않았는가?
- user burden이 증가하지 않았는가?

---

## PHASE 6 — Blind cold-start eval 설계

리팩터링 후 답을 보기 전에 eval specification을 먼저 잠근다.

### 핵심 평가축

LongMemEval-V2 / STALE에서 직접 가져온 축을 프로젝트에 맞게 변환한다.

1. Static state recall
2. Dynamic state tracking
3. Workflow knowledge
4. Environment/project gotchas
5. Premise awareness
6. State resolution
7. Premise resistance
8. Policy adaptation
9. Judgment consistency under pressure
10. Selective evidence retrieval

### 오염 방지 규칙

- 테스트 prompt에 정답 규칙을 적지 않는다.
- 새 session은 기존 테스트 transcript를 볼 수 없게 한다.
- 실행 전에 prompt, expected traits, fail conditions를 잠근다.
- 실행 후 결과가 마음에 안 든다고 조건을 바꾸지 않는다.
- 동일 prompt를 반복 학습시키고 pass라고 부르지 않는다.

### 사용자 부담 기준

평가 prompt는 가능한 한 일반적인 실제 사용 형태여야 한다.

목표 예:

> `이 프로젝트 이어서 하자.`

정도의 요청에서도 필요한 bootstrap과 retrieval을 AI가 수행하는 것이 이상적이다.

### Exit Gate P6

- eval이 architecture document의 문구 암기 시험이 아니라 실제 행동 능력을 측정하는가?
- BEFORE/AFTER에 동일 조건을 적용할 수 있는가?

---

## PHASE 7 — BEFORE vs AFTER 검증

### 비교 지표

- 상태 복원 정확도
- stale/superseded 오류
- 판단 이유 재현
- 사용자 압박에 따른 근거 없는 judgment drift
- 필요한 자료 retrieval 성공
- 불필요한 자료 preload/retrieval
- 응답 지연/도구 호출 overhead
- 사용자 추가 설명 요구량

가능한 한 점수 하나로 합치지 않고 실패 유형별로 본다.

### 판정

- **PASS** — AFTER가 핵심 실패를 줄이고 새로운 치명적 overhead를 만들지 않음
- **PARTIAL** — 개선은 있으나 특정 memory failure가 남음
- **FAIL** — BEFORE와 차이가 없거나 새로운 회귀가 더 큼

한 번의 pass는 `가능성`의 증거다. 안정성이 필요한 경우 사전에 정한 최소 반복 수만 추가한다.

---

## PHASE 8 — 실패 원인 분석 및 제한적 수리

FAIL/PARTIAL일 때만 실행.

### 규칙

- 실패를 무조건 새 rule로 만들지 않는다.
- 먼저 failure class를 판별한다.
  - retrieval failure
  - routing failure
  - stale-state failure
  - write/update failure
  - procedural-memory failure
  - judgment-policy failure
  - eval artifact
- 기존 상위 원칙으로 해결 가능하면 새 architecture를 추가하지 않는다.
- 같은 실패가 재현되고 설계 원인이 확인될 때만 구조 수정.

수리 후에는 **변경 영향을 받는 eval만** 재실행하고, 최종적으로 regression set을 한 번 다시 확인한다.

---

## PHASE 9 — 채택 및 종료

PASS 후:

- main에 최종 구조 반영
- README / AGENTS / current state가 실제 architecture와 일치하는지 확인
- 이번 research/refactor plan을 `completed` 상태로 전환
- 핵심 research note와 audit은 archive로 보존
- temporary eval artifacts 중 장기 가치 없는 것은 제거/보관 판단

### 최종 종료 조건

다음 질문에 모두 YES여야 한다.

- 새 세션이 사용자에게 기본 맥락을 다시 묻는 일이 줄었는가?
- 최신 현재 상태를 과거보다 우선하는가?
- 왜 그렇게 판단하는지 상당 부분 재현하는가?
- 필요한 과거 자료를 스스로 찾는가?
- 사용자가 GPT 운용/인수인계 담당자가 되지 않았는가?
- 기억 시스템 때문에 실제 콘텐츠 프로젝트가 더 느려지지 않는가?

종료 후 **첫 콘텐츠 실제 촬영·편집 작업으로 복귀**한다.

---

# 4. 이번 리팩터링에서 하지 않는 것

- 범용 agent-memory 제품을 별도 active repository로 만드는 일
- `kkamaknun`의 프로젝트 데이터를 다른 active repo로 이전하는 일
- 사용자가 매 세션 복사할 bootstrap prompt 제작
- 규칙 수를 성능 지표로 삼는 일
- 모든 대화 turn을 영구 memory로 저장하는 일
- 모든 history를 매 session preload하는 일
- benchmark를 통과할 때까지 test prompt에 맞춰 문서를 overfit하는 일
- 현재 프로젝트 제작을 무기한 중단하고 memory 연구를 계속하는 일

---

# 5. 변경 통제 규칙

이 계획도 연구 결과가 틀렸거나 새로운 근거가 나오면 변경할 수 있다. 단, 다음 조건을 지킨다.

1. 사용자의 압박/선호만으로 기술 계획을 바꾸지 않는다.
2. 새 연구, 새 도구 제약, repo audit의 실제 발견처럼 **새 근거**가 있어야 한다.
3. 계획 변경 시 무엇이 왜 바뀌었는지 이 문서에 기록한다.
4. 이미 실행한 단계의 조건을 사후에 바꿔 성공처럼 만들지 않는다.
5. `DRAFT` / `LOCKED` / `EXECUTING` / `COMPLETED` 상태를 구분한다.

---

# 6. 현재 진행 위치

**현재: PHASE 1 — 딥리서치 및 evidence matrix 확정**

완료:
- PHASE 0 문제 정의
- 1차 연구 탐색
- repo root / 핵심 memory 파일 구조 확인
- 실행 roadmap 작성
- 계획 재검토 및 누락 축 보완
- Exit Gate P0 PASS

현재 수행:

> **PHASE 1 — 연구 범위를 확장하고 evidence matrix를 완성한다.**

Phase 1이 끝나기 전에는 기존 memory/process 구조를 리팩터링하지 않는다.
