# CONTEXT / MEMORY DEEP RESEARCH — 2026-08

> 상태: **PHASE 1 RESEARCH SYNTHESIS**
> 조사 시점: 2026-08-23
> 목적: `kkamaknun` 장기 프로젝트에서 새 세션이 **현재 상태 + 장기 맥락 + 판단 원리 + 작업 절차 + 과거 증거**를 낮은 사용자 부담으로 복원하도록 하기 위해, 2024~2026 장기 컨텍스트·agent memory·filesystem memory·stale memory·procedural memory·eval 연구와 최신 OpenAI/Anthropic 실무를 교차 검토한다.
>
> 이 문서는 연구 결과다. 아직 `AGENTS.md`, `USER_CONTEXT.md`, `JUDGMENT.md` 등의 실제 구조를 변경하지 않는다. 실제 구조 결정은 Phase 2 repo audit 이후 Phase 3에서 한다.

---

# 1. 먼저 결론 — `성능이 제일 좋은 것`은 단일 제품/알고리즘이 아니다

현재 연구에는 모든 workload에서 동시에 최고인 단일 memory system이 없다.

- **LongMemEval-V2**에서는 file-based agentic retrieval인 **AgentRunbook-C 계열**이 공개 baseline 중 강한 accuracy/latency frontier를 보인다.
- **MemoryAgentBench의 precise retrieval / fact tracking**에서는 **ReFind**가 복잡한 graph/tree memory 없이 **raw chat archive + agent-controlled iterative lexical search**로 비교군 최고 mean accuracy를 보고한다.
- **MemoryAgentBench 전체 능력**에서는 **Infini Memory**가 topic-structured documents + buffer + iterative retrieval로 높은 overall score를 보고한다.
- **LoCoMo / LongMemEval-S 정적·대화 memory 계열**에서는 LycheeMemory V2, MOSAIC 등 더 높은 개별 benchmark 수치를 보고하지만, workload와 backbone이 다르고 graph/LLM construction 비용이 크다.
- **MemoryArena**에서는 기존 recall benchmark에서 강한 memory agents도 실제 multi-session agentic task에서 크게 무너진다.
- cost 연구는 **정확도와 비용을 동시에 지배하는 단일 시스템이 없고 backbone·query volume·construction policy에 따라 결과가 바뀐다**고 보고한다.

따라서 이 프로젝트가 따라야 할 기준은 `벤치마크 숫자가 제일 큰 시스템을 통째로 복제`가 아니다.

> **우리 workload와 직접 맞는 성능 좋은 구성요소만 결합하고, 현재 ChatGPT + GitHub 환경에서 구현 불가능하거나 과도한 구조는 버린다.**

현재 가장 강하게 수렴하는 실용 방향은:

```text
small bootstrap/router
→ explicit canonical current state
→ stable declarative context + procedural/judgment memory
→ agentic selective retrieval
→ raw episodic evidence preserved
→ gated/non-destructive consolidation
→ explicit stale/supersede handling
→ cold-start behavioral eval
```

이다.

---

# 2. Evidence level

이 문서에서는 근거를 다음처럼 구분한다.

- **E1 — 공식 production engineering / 실제 제품**: OpenAI, Anthropic이 실제 서비스·agent 운영에서 공개한 결과
- **E2 — 동료평가 학회 논문**: ACL / ICLR / ICML / TACL 등
- **E3 — 2026 최신 preprint + 공개 benchmark/code**: 재현 가능성이 높지만 peer review 전일 수 있음
- **E4 — 일반화 추론**: 위 자료들을 `kkamaknun` workload에 적용한 분석. 연구 결과 그 자체가 아님

숫자를 비교할 때는 **backbone, benchmark, task definition이 다르면 직접 SOTA 순위로 합치지 않는다.**

---

# 3. Evidence matrix

## 3.1 OpenAI — Harness engineering: repository as system of record

- **근거 수준:** E1
- **발표:** 2026-02-11
- **출처:** https://openai.com/index/harness-engineering/
- **실제 조건:** agent-first software product, 수개월, 약 1M LOC 규모, Codex 중심 운영

### 핵심 결과

OpenAI 팀은 큰 `AGENTS.md` 하나에 지식을 몰아넣는 방식을 실제로 시도했고 실패했다고 보고한다.

실패 이유:
- task 자체보다 instruction blob이 context를 점유
- 모든 것이 중요해져 priority가 사라짐
- monolithic manual이 빠르게 stale해짐
- ownership/freshness/cross-link 등을 기계적으로 검사하기 어려움

대신:
- repository knowledge를 **system of record**로 둠
- 짧은 `AGENTS.md`는 **table of contents / map** 역할
- 세부 지식은 structured docs로 분리
- execution plan, progress, decision log를 repo에 versioned artifact로 보존
- 필요할 때 깊게 읽는 **progressive disclosure**
- doc freshness/links를 lint/CI로 검사

### 우리 문제와 직접 연결

매우 높음. 현재 `kkamaknun`도 repo-based external memory이고 `AGENTS.md`가 bootstrap 역할을 한다.

### 적용 후보

- bootstrap = map/router
- source of truth의 owner 명시
- current/decision/evidence를 versioned docs로 유지
- 기계적으로 검사 가능한 invariant만 CI 대상으로 검토

### 그대로 일반화하면 안 되는 것

OpenAI 사례는 software/codebase workload다. 우리 프로젝트는 콘텐츠 기획 + 사용자 맥락 + 판단 이전이 핵심이므로 동일 docs hierarchy를 복제할 이유는 없다.

---

## 3.2 Anthropic — Effective context engineering

- **근거 수준:** E1
- **발표:** 2025-09-29
- **출처:** https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents

### 핵심 결과

- context는 유한한 attention resource
- 목표는 가장 작은 **high-signal context** 구성
- 모든 정보를 preload하지 않고 file path / link / lightweight identifier로 두었다가 **just-in-time retrieval**
- long-horizon 작업에서 compaction, structured note-taking, subagent 등의 context management 사용

### 우리 문제와 직접 연결

매우 높음.

### 적용 후보

- 세션 시작 시 7~8개 문서를 무조건 모두 읽는 방식은 audit 대상
- stable bootstrap + query-dependent retrieval 경계 설계

### 제한

이 글은 하나의 memory backend benchmark가 아니라 engineering guidance다. retrieval 방식 자체의 최적 알고리즘을 결정하지 않는다.

---

## 3.3 Anthropic — Effective harnesses for long-running agents

- **근거 수준:** E1
- **발표:** 2025-11-26
- **출처:** https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents

### 핵심 결과

- 장기 agent는 여러 context window/session을 건너며 작업
- 새 session은 이전 session을 직접 기억하지 못하는 문제가 있음
- progress artifact, git history, structured handoff를 통해 상태 복원
- 단순 compaction만으로 전체 장기 작업 문제가 해결되지 않음

### 우리 문제와 직접 연결

매우 높음. 사용자가 새 chat에서 이전 상태를 복원하려는 문제와 구조적으로 동일하다.

### 적용 후보

- compact current-state artifact
- git/raw history는 증거층
- 다음 세션이 재구성 가능한 상태를 남김

### 제한

주요 실험이 coding harness 중심이다.

---

## 3.4 Anthropic — Agent Skills / progressive disclosure

- **근거 수준:** E1
- **발표:** 2025-10-16
- **출처:** https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills

### 핵심 결과

Agent Skills는 3층 progressive disclosure를 사용한다.

1. startup에 `name + description` 수준의 작은 metadata
2. 관련 task일 때 `SKILL.md` 본문 로드
3. 더 깊은 reference는 필요할 때만 탐색

### 우리 문제와 직접 연결

높음. `AGENTS` → 관련 memory/policy → raw evidence의 계층적 routing 설계에 직접 참고 가능.

### 적용 후보

- 파일 역할·trigger를 짧은 routing metadata로 명시
- 세부 절차/증거는 on-demand

---

## 3.5 Anthropic — Scaling Managed Agents / Harness design

- **근거 수준:** E1
- **발표:** 2026-03~04
- **출처:**
  - https://www.anthropic.com/engineering/harness-design-long-running-apps
  - https://www.anthropic.com/engineering/managed-agents

### 핵심 결과

- harness의 각 요소는 `모델이 이것을 스스로 못 한다`라는 가정을 encode함
- 모델이 발전하면 그 가정이 stale해질 수 있음
- 더 복잡한 harness가 더 나은 결과를 낼 수 있지만 비용이 매우 커질 수 있음
- stable interface와 replaceable harness를 분리하고 주기적으로 scaffolding을 줄여야 함

### 적용 후보

- architecture를 최소화
- 새 GPT/model 출시 시 regression eval 후 필요 없는 rule/harness 제거
- 규칙의 양을 성능으로 간주하지 않음

---

## 3.6 OpenAI — Dreaming V3 / memory synthesis

- **근거 수준:** E1
- **발표:** 2026-06-04
- **출처:** https://openai.com/index/chatgpt-memory-dreaming/

### 핵심 결과

OpenAI가 memory 품질을 평가하는 세 축:

1. useful context carry-forward
2. preferences/constraints adherence
3. currentness over time

기존 saved memories의 staleness와 제한을 해결하기 위해 여러 대화에서 memory state를 **synthesize**하고 시간 변화에 따라 업데이트하는 Dreaming 기반 architecture를 확장했다.

### 우리 문제와 직접 연결

높음. 다만 ChatGPT 내부 구현은 공개되지 않아 직접 복제할 수 없음.

### 적용 후보

- memory 평가에 `continuity / constraints / freshness` 포함
- canonical state를 주기적으로 synthesize/review할 필요가 있음

### 중요한 반대 근거와 함께 사용

뒤의 `Useful Memories Become Faulty...`는 LLM continuous consolidation이 오히려 memory를 망칠 수 있다고 보고한다. 따라서 우리 repo에서 Dreaming을 흉내내 **모든 turn마다 기존 canonical memory를 LLM으로 재작성**하는 것은 근거가 없다.

---

## 3.7 LongMemEval-V2 — experienced colleague memory benchmark

- **근거 수준:** E3 (2026 최신 preprint + 공식 공개 benchmark/code)
- **발표:** 2026-05, repo 2026-08 업데이트
- **출처:**
  - https://arxiv.org/abs/2605.12493
  - https://xiaowu0162.github.io/longmemeval-v2/
  - https://github.com/xiaowu0162/LongMemEval-V2

### Benchmark

- 451 manually curated questions
- 최대 500 trajectories/haystack
- 최대 115M tokens
- web + enterprise

### 평가하는 5개 memory 능력

1. Static state recall
2. Dynamic state tracking
3. Workflow knowledge
4. Environment gotchas
5. Premise awareness

이 다섯 축은 `kkamaknun`이 새 세션에 이전하려는 능력과 거의 직접 대응한다.

### 공개 baseline 결과

| Method | Small Overall | Small latency | Medium Overall | Medium latency |
|---|---:|---:|---:|---:|
| RAG slice | 42.8 | 0.1s | 38.1 | 0.1s |
| RAG slice + notes | 51.0 | 0.2s | 45.9 | 0.3s |
| AgentRunbook-R | 58.6 | 26.9s | 57.0 | 25.8s |
| Codex | 69.9 | 177.2s | 68.7 | 185.8s |
| **AgentRunbook-C** | **74.9** | **108.3s** | **70.1** | **139.9s** |

### 의미

단일-shot RAG보다 **agent가 직접 filesystem을 탐색하고 증거를 수집하는 방식**이 이 benchmark에서는 훨씬 강함.

### 제한

이 결과는 context-gathering benchmark다. 우리 실제 기획 행동을 직접 측정하지 않는다.

---

## 3.8 AgentRunbook-C V2 — 현재 가장 직접적으로 참고할 구현

- **근거 수준:** E3, 공식 LongMemEval-V2 연구 업데이트 + 공개 code
- **업데이트:** 2026-08
- **출처:** https://xiaowu0162.github.io/longmemeval-v2/agentrunbook-c-v2/

### GPT-5.4-mini / LongMemEval-V2 Small

| System | Medium accuracy | Medium latency | Xhigh accuracy | Xhigh latency |
|---|---:|---:|---:|---:|
| Codex | 66.50 | 130.00s | 69.90 | 177.20s |
| V1 | 70.30 | 70.00s | 74.90 | 108.30s |
| **V2** | **72.73** | **56.68s** | **75.61** | 130.54s |

연구팀은 V2가 tested medium/xhigh settings에서 가장 높은 accuracy를 달성한다고 보고한다.

### V2 구조에서 중요한 것

- 모델 능력이 좋아지자 복잡한 orchestration을 **줄임**
- shell/search + file inspection 중심 lightweight controller
- 이전 query에서 얻은 **retrieval strategy만** 작은 persistent note로 보존
- 과거 strategy note는 답의 증거가 아니며 **현재 evidence로 재검증**해야 함

공개 source의 `CONSOLIDATE_STRATEGY.md`는 특히 중요한 guard를 둔다.

- 대부분 query는 strategy note를 추가하지 않는 것이 기본
- bad/over-specific note는 no note보다 나쁨
- default zero additions, 보통 최대 one strong reusable row
- 직접 증거 / premise contradiction / near-match / insufficient를 구분
- near-match를 현재 answer evidence로 승격 금지
- 이미 긴 strategy file이면 merge/prune 우선

### 우리 문제에 적용 후보

`판단/사실 memory`를 자동 학습시키기보다, 별도로 **검색 경로 / 어디를 먼저 찾아야 하는지 / 반복적인 retrieval gotcha**만 아주 작게 보존하는 패턴은 검토 가치가 높다.

### 제한

LongMemEval trajectory retrieval에 최적화된 strategy memory다. 이를 그대로 사용자 사실이나 기획 결론 저장 방식으로 사용하면 안 됨.

---

## 3.9 ReFind — raw archive + agentic lexical retrieval

- **근거 수준:** E3, 2026-08-13 매우 최신 preprint
- **출처:** https://arxiv.org/abs/2608.12888

### 구조

- raw chat archive를 **수정하지 않음**
- turn-level lexical index
- agent-controlled iterative keyword search
- session-aware rank fusion
- local context expansion
- temporal narrowing
- already-inspected session skip
- 수집 증거와 최종 answer reasoning을 분리

### 결과

MemoryAgentBench precise-retrieval/fact-tracking 약 2,800 questions, GPT-4o-mini matched backbone:

- **ReFind 58.2 mean accuracy**
- strongest compared graph/tree baseline HippoRAG2 53.2

LongMemEval-S/M with GPT-5-mini:

- **93.2 ± 3.3 / 89.3 ± 6.0**

### 우리 문제와 직접 연결

매우 높음. 사용자가 실제 과거 대화/논쟁/결정 원문을 잃지 않고 필요할 때 다시 찾아야 한다는 요구와 직접 일치.

### 적용 후보

- raw history를 과도하게 요약·변환하지 않고 first-class evidence로 보존
- current question에서 필요할 때 iterative search
- 주변 context와 시간 범위를 함께 조회
- 이미 본 기록을 반복 조회하지 않는 retrieval discipline

### 제한

아직 매우 새로운 preprint이고, 일부 comparison numbers가 prior work에서 재사용된다는 검토상 한계가 있다. 따라서 `structured memory 전체를 폐기`하는 근거로 쓰면 과잉 일반화다.

---

## 3.10 Filesystem-Based Memory for LLM Agents

- **근거 수준:** E3
- **발표:** 2026-07-29
- **출처:** https://arxiv.org/abs/2607.26637

### 핵심 결과

- filesystem memory를 조직하면 대규모 store에서 **retrieval cost를 대략 절반으로 줄이는 효과**가 안정적으로 나타남
- 그러나 organization 자체가 answer accuracy를 개선하지는 않음
- store organization은 시간이 지나며 약해질 수 있고, 강한 management agent가 아니면 구조가 붕괴
- toolset 선택도 memory shape에 큰 영향을 줌

### 적용 후보

- 현재 markdown/filesystem 방향은 타당
- hierarchy는 검색경제와 maintainability를 위한 것
- `폴더를 잘 나누면 판단력도 자동 상승` 같은 가정 금지

---

## 3.11 Useful Memories Become Faulty When Continuously Updated by LLMs

- **근거 수준:** E3
- **발표:** 2026-05
- **출처:** https://arxiv.org/abs/2605.12978

### 핵심 결과

- raw episodic traces와 consolidated abstraction은 다름
- LLM이 memory bank를 계속 rewrite/consolidate하면 utility가 처음 증가하다가 다시 하락 가능
- ground-truth solution에서 memory를 만들었는데도 GPT-5.4가 이전에 풀던 ARC-AGI 문제 중 54%를 memory와 함께 실패한 실험 보고
- episodic-only raw retention은 consolidation systems와 경쟁력 있음
- agent가 retain/delete/consolidate를 선택하게 하면 raw episode 보존을 선호했고 forced consolidation보다 성능이 좋았음

### 우리 문제에 직접 주는 원칙

> **원본 증거를 파괴적으로 덮어쓰지 않는다. consolidation은 gated하고, 실패 시 원본으로 되돌아갈 수 있어야 한다.**

### 적용 후보

- `기록/` / git history / raw transcripts를 삭제하지 않음
- canonical summary 변경은 provenance와 source를 유지
- 매 turn 자동 rewrite 금지

---

## 3.12 LycheeMemory V2 — segment-level consolidation

- **근거 수준:** E3
- **발표:** 2026-08-13
- **출처:** https://arxiv.org/abs/2608.12990

### 핵심 결과

매 turn마다 memory를 consolidate하는 eager design 대신 semantic segment 단위로 batch consolidation.

GPT-4.1-mini:
- LoCoMo **89.22%**
- LongMemEval-S **92.20%**
- A-Mem 대비 construction tokens: LoCoMo -86.0%, LME-S -75.9%

### 적용 후보

- 실제 session/작업 단위로 memory promotion을 batch 처리
- 사소한 turn마다 canonical docs 수정하지 않기

### 제한

대화 memory benchmark이며 사용자 프로젝트의 procedural judgment behavior를 직접 평가하지 않음.

---

## 3.13 Infini Memory — maintainable topic documents

- **근거 수준:** E3
- **발표:** 2026-06
- **출처:** https://arxiv.org/abs/2606.10677

### 구조

- isolated record 대신 **topic-structured text documents**
- new observation은 buffer에서 staging
- 주기적으로 coherent document에 consolidation
- query에서는 one-shot retrieval 대신 **agentic iterative inspection**

### 결과

MemoryAgentBench overall **64.7%** 보고.

### 적용 후보

- 현재 repo처럼 주제별 markdown source of truth는 합리적
- 바로 canonical에 쓰지 않고 staging/admission을 거치는 write policy 검토
- iterative retrieval

### 제한

consolidation 자체는 앞선 faulty-consolidation 연구와 긴장 관계가 있으므로, raw source를 보존하고 canonical promotion을 제한하는 방식으로만 채택해야 함.

---

## 3.14 STALE — stale memory는 retrieval과 별도 문제

- **근거 수준:** E3
- **발표:** 2026-05
- **출처:** https://arxiv.org/abs/2605.06527

### benchmark

- 400 expert-validated conflict scenarios
- 1,200 queries
- 100+ everyday topics
- up to 150K tokens

### 평가축

1. State Resolution
2. Premise Resistance
3. Implicit Policy Adaptation

### 핵심 결과

best evaluated system도 전체 **55.2%** 수준.

중요한 발견:
- 최신 evidence를 retrieval했다고 해서 stale state를 실제 행동에서 버리는 것은 아님
- user query 자체가 오래된 전제를 포함하면 모델이 그 전제를 받아들이기 쉬움

### 우리 문제와 직접 연결

매우 높음. `귀멸 후보`, 장비 상태, 기획 우선순위, 철회 결정 등 프로젝트 상태가 바뀌는 구조와 직접 일치.

### 적용 후보

- current state를 명시적으로 owner 하나에 둠
- superseded relationship 명시
- eval에 stale-premise rejection 포함

---

## 3.15 Don't Ask the LLM to Track Freshness

- **근거 수준:** E3
- **발표:** 2026-05/06
- **출처:** https://arxiv.org/abs/2606.01435

### 핵심 결과

명시적으로 `newer serial/timestamp wins`인 current-value conflict에서는 LLM에게 freshness 판단을 맡기기보다 deterministic max(serial/timestamp) aggregation이 강한 결과.

MemoryAgentBench FactConsolidation single-hop:
- deterministic recipe가 matched setup에서 +10.8 points
- GPT-4o에서는 94.8%까지 보고

하지만 LongMemEval knowledge-update check에서는 deterministic timestamp 방식이 LLM judgment보다 낮거나 비슷한 수준(57.8 vs 64.4, n=45).

### 적용 원칙

> **명시적인 버전/current state는 deterministic하게. 의미적·암시적 conflict는 LLM reasoning과 결합.**

즉 모든 memory QA를 timestamp 하나로 처리하는 것은 틀림.

---

## 3.16 ACL 2026 — How Memory Management Impacts LLM Agents

- **근거 수준:** E2, ACL 2026 Long Paper
- **출처:** https://aclanthology.org/2026.acl-long.27/

### 핵심 발견

**experience-following property**:
현재 task와 retrieved memory의 input이 비슷하면 output execution도 강하게 따라감.

이로부터 두 failure:
- **error propagation** — 잘못된 과거 경험을 따라하고 다시 memory에 넣으며 오류 증폭
- **misaligned experience replay** — 겉보기에는 비슷하지만 현재 task에 맞지 않는 과거 경험이 오히려 방해

trajectory evaluator의 feedback으로 memory addition/deletion quality를 관리하면 개선됨.

### 우리 문제에 직접 주는 원칙

- 사용자가 AI와 싸웠다는 이유만으로 그 사건을 permanent rule로 쓰지 않음
- `성공/검증된 것`만 reusable procedural/judgment memory로 승격
- retrieval similarity만으로 현재 문제에 과거 사례를 적용하지 않음

---

## 3.17 HaluMem — extraction/update 단계에서 이미 hallucination 발생

- **근거 수준:** E3 benchmark
- **발표:** 2025-11, 2026 현재 사용
- **출처:** https://arxiv.org/abs/2511.03506

### 평가 단계

1. memory extraction
2. memory update
3. memory QA

약 15k memory points, 3.5k questions, 1M+ token long dialogs.

### 핵심 결과

hallucination/error/conflict/omission은 final answer에서만 생기는 것이 아니라 **extraction/update 단계에서 생겨 누적되어 QA까지 전파**됨.

### 적용 후보

- memory write를 답변 생성보다 더 엄격하게 취급
- provenance 없는 `AI가 알아서 요약한 사실`을 canonical로 즉시 승격하지 않음

---

## 3.18 DynamicMem — long-term failure의 93% 이상이 retrieval 측

- **근거 수준:** E3
- **발표:** 2026-06
- **출처:** https://arxiv.org/abs/2606.22877

### benchmark

- 사용자당 15개월
- 평균 2.2M tokens
- 1,772 grounded events
- 16 apps
- 5 quarterly checkpoints

### 핵심 결과

- history가 길어질수록 profile reconstruction 성능 저하
- 어떤 시스템도 stable facts 유지와 changing facts replacement를 둘 다 잘하지 못함
- **93% 이상 실패가 answer writing이 아니라 retrieval된 memory에서 발생**

### 우리 문제에 적용

final response prompt를 더 정교하게 만드는 것보다 **어떤 state/evidence를 가져오는가**가 우선.

---

## 3.19 Memora / FAMA — 기억해야 할 것만큼 잊어야 할 것이 중요

- **근거 수준:** E3
- **발표:** 2026-04
- **출처:** https://arxiv.org/abs/2604.20006

### 핵심

기존 평가가 recall에 치우친 문제를 지적하고, obsolete memory 사용을 직접 벌점 주는 **Forgetting-Aware Memory Accuracy (FAMA)** 제안.

여러 memory agents가 invalid memory 재사용과 evolving memory reconciliation에서 실패.

### 적용 후보

우리 eval도 `무엇을 기억했는가`만 보지 않고 **철회/과거 상태를 사용하지 않는가**를 별도 fail condition으로 둔다.

---

## 3.20 Procedural memory — AFTER

- **근거 수준:** E3
- **발표:** 2026-06
- **출처:** https://arxiv.org/abs/2606.23127

### benchmark

- 382 realistic enterprise tasks
- 6 roles
- 22 procedural skills

### 결과

- 한 번의 refinement로 aggregate performance **+3.7 ~ +6.7 points**
- multi-model traces에서 만든 skills가 **73.1% cross-model test accuracy**
- 일부 skill은 넓게 transfer되지만 일부는 role-specific으로 전문화되어 transfer 성능이 떨어짐

### 적용 후보

`PLANNING_PROCESS` 같은 procedural memory를 facts/history와 분리 유지.

`JUDGMENT`도 반복적으로 재현돼야 하는 high-level decision skill로 볼 수 있음.

### 제한

모든 프로젝트-specific judgment가 범용 skill로 전환된다는 의미는 아님.

---

## 3.21 MemoryAgentBench — memory를 네 능력으로 분해

- **근거 수준:** E2, ICLR 2026
- **출처:** https://openreview.net/ (MemoryAgentBench) / https://github.com/HUST-AI-HYZ/MemoryAgentBench

### 평가 능력

- Accurate Retrieval
- Test-Time Learning
- Long-Range Understanding
- Conflict Resolution / Selective Forgetting

### 의미

memory 성능을 `잘 기억한다` 하나의 점수로 보면 안 됨.

---

## 3.22 MemoryArena — recall benchmark 점수가 높아도 실제 agent 행동은 실패

- **근거 수준:** E2, ICML 2026
- **출처:** https://arxiv.org/abs/2602.16313

### 핵심

- memory acquisition과 action을 multi-session으로 결합
- web navigation, preference planning, progressive search, formal reasoning 등
- LoCoMo 같은 recall benchmark에서 near-saturated인 systems도 agentic setting에서는 크게 무너짐

### 우리 문제에 직접 주는 원칙

최종 eval을:

> `현재 상태가 뭐야?`

같은 문서 recall 시험으로만 만들면 안 됨.

실제로:
- 현재 상황에서 다음 행동을 제대로 선택하는가
- stale premise를 거부하는가
- 판단 원리를 적용하는가
- 필요한 evidence를 스스로 찾는가

를 봐야 함.

---

## 3.23 Agent Memory: Characterization and System Implications

- **근거 수준:** E3
- **발표:** 2026-06
- **출처:** https://arxiv.org/abs/2606.06448

### 핵심

10개 대표 memory systems를 profiling하고 비용을:

- construction
- retrieval
- generation

으로 분리.

query volume, capability floor, freshness-latency, write/read tradeoff에 따라 최적 architecture가 달라짐.

### 우리 문제에 적용

- memory 품질만이 아니라 tool calls / latency / context tokens도 함께 평가
- `더 많은 retrieval = 더 좋은 시스템` 아님

---

## 3.24 Total Recall at What Cost?

- **근거 수준:** E3, 2026-08 매우 최신
- **출처:** https://arxiv.org/abs/2608.11879

### benchmark

Mem0 / Hindsight / Mastra Observational Memory와 rolling window / full transcript를 400 turns까지 비교, 665 LoCoMo questions.

### 핵심 결과

- memory serving cost는 conversation length만으로 설명되지 않음
- system 내부 extraction/retrieval/consolidation 정책이 비용을 크게 좌우
- full transcript보다 언제 싸지는지는 system/backbone에 따라 `초반`부터 `400턴 내에는 전혀 안 됨`까지 다양
- accuracy 21~54% 범위, **cost와 accuracy 모두를 지배하는 단일 시스템 없음**

### 적용

Phase 7에서 retrieval/tool-call overhead를 별도 지표로 측정.

---

## 3.25 MOSAIC — conflict-aware structured memory

- **근거 수준:** E3
- **발표:** 2026-05/07
- **출처:** https://arxiv.org/abs/2607.16211

### 구조

- entity-typed graph
- dual-path retrieval
- save-time conflict detection

### 보고 결과

- LoCoMo 89.35%
- HaluMem QA Medium 73.10%, Long 70.75%
- factual conflict detection 66%
- avg search latency 0.58s

### 적용 후보

`save-time conflict check` 원리는 유용.

### 현재 우리 workload에서 보류할 이유

`kkamaknun`의 현재 memory store는 작고 파일 owner를 명시적으로 만들 수 있다. 지금부터 graph DB/entity graph를 추가하면 complexity가 커지며, 이 workload에서 그 추가 비용이 상쇄된다는 근거가 아직 없다.

---

## 3.26 AgeMem — learned memory policy

- **근거 수준:** E2, ACL 2026
- **출처:** https://aclanthology.org/2026.acl-long.981/

### 핵심

LLM agent가 store/retrieve/update/summarize/discard를 직접 policy action으로 학습하도록 RL로 memory management 통합. 여러 long-horizon benchmark에서 strong baselines를 상회.

### 우리 시스템에서 제외

현재 ChatGPT/GitHub 환경에서는 model weights/RL policy를 우리가 학습시킬 수 없다.

따라서 `memory actions를 명시적으로 나눈다`는 아이디어는 참고하지만 architecture 자체는 구현 대상이 아니다.

---

# 4. 성능 지도 — 무엇이 어디에서 강했는가

직접 비교가 가능한 benchmark 안에서만 본다.

| 목적/benchmark | 강한 결과 | 핵심 구조 | 우리 적용성 |
|---|---|---|---|
| LongMemEval-V2 공식 baseline | AgentRunbook-C 74.9 Small / 70.1 Medium | file-based agentic evidence gathering | **매우 높음** |
| LME-V2 V2 update | AgentRunbook-C V2 72.73 medium, 75.61 xhigh (GPT-5.4-mini Small) | simplified controller + guarded retrieval-strategy memory | **매우 높음** |
| Raw chat precise retrieval | ReFind 58.2 MAB mean; LME-S/M 93.2/89.3 | raw logs + iterative lexical/session/time search | **매우 높음** |
| MemoryAgentBench overall | Infini Memory 64.7 | topic docs + buffer + iterative retrieval | 높음 |
| Low-construction conversation memory | LycheeMemory V2 89.22 LoCoMo / 92.20 LME-S | segment batching + typed records | 중간~높음 |
| Conflict-aware graph memory | MOSAIC 89.35 LoCoMo; HaluMem QA 73.10/70.75 | graph + save-time conflict detection | 원리 높음, 전체 구조 낮음 |
| Learned policy | AgeMem | RL-trained memory action policy | 현재 구현 불가 |

**주의:** 이 표의 행끼리는 backbone과 benchmark가 다르므로 숫자로 우열을 직접 비교하지 않는다.

---

# 5. 서로 충돌하는 연구와 해석

## 충돌 A — `잘 정리된 memory` vs `raw archive 그대로`

- Infini / Lychee / MOSAIC: 구조화·consolidation이 강한 benchmark 성능
- ReFind: raw log를 변형하지 않고 agentic search만으로 structured memory와 경쟁/상회
- Filesystem study: 조직화는 retrieval cost를 줄이지만 accuracy 자체를 자동 개선하지 않음

### 해석

둘 중 하나를 고를 필요가 없다.

> **canonical high-signal state는 구조화하고, raw episodic history는 그대로 보존한다.**

정확한 과거 evidence가 필요하면 raw search, 현재 상태/규칙은 canonical docs를 우선하는 hybrid가 가장 근거와 잘 맞는다.

---

## 충돌 B — `memory synthesis/consolidation` vs `continuous consolidation이 memory를 망침`

- OpenAI Dreaming / Infini / Lychee: synthesis/consolidation의 가치
- Useful Memories Become Faulty: 반복 LLM rewrite가 error를 누적시키고 성능을 떨어뜨릴 수 있음
- HaluMem: extraction/update 단계 자체가 hallucination source

### 해석

consolidation을 버리는 것이 아니라 **쓰기 정책을 제한**해야 함.

가장 안전한 형태:

```text
raw evidence (immutable)
        ↓
new observation / staging
        ↓ quality/conflict check
canonical update
        ↓
old canonical version remains recoverable in git/history
```

매 turn 강제 consolidation은 채택하지 않는다.

---

## 충돌 C — deterministic freshness vs LLM reasoning

- explicit version/current-value는 deterministic max(timestamp/version)가 강함
- broad QA/implicit conflicts에서는 deterministic freshness만으로 충분하지 않음

### 해석

- `현재 화수 후보`, `현재 우선순위`, `현재 장비 상태` 같은 explicit state → owner/version/date를 명시
- 의미적으로 한 정보가 다른 정보를 간접 무효화하는 문제 → LLM conflict reasoning + evidence lookup

---

## 충돌 D — more harness vs simpler harness

- 복잡한 harness가 frontier performance를 높인 실험 존재
- AgentRunbook-C V2 / Managed Agents는 모델 발전 후 orchestration을 줄여 더 빠르고 강하게 만든 사례

### 해석

> **현재 모델이 할 수 있는 일까지 규칙으로 강제하지 않는다.**

우리는 최소 architecture로 시작하고 actual failure가 재현될 때만 scaffolding을 추가해야 한다.

---

# 6. 현재 ChatGPT + GitHub 환경에서 구현 가능한 것 / 불가능한 것

## 구현 가능

- GitHub repo를 live source로 읽기/검색
- markdown source of truth 유지
- current state / decisions / procedures / evidence를 별도 파일로 관리
- query-dependent file retrieval
- git version history와 rollback
- explicit timestamp/version/superseded metadata
- lightweight deterministic checks/CI
- fresh session에서 repo를 읽고 behavior eval

OpenAI 공식 GitHub 연결 문서도 ChatGPT가 허용된 repository의 code/README/docs에서 live data를 가져와 분석할 수 있다고 설명한다.

출처: https://help.openai.com/ko-kr/articles/11145903-connecting-github-to-chatgpt

## 제품 memory가 보조할 수 있는 것

ChatGPT Projects는 같은 project의 chats/files를 우선 context로 참조할 수 있다.

출처: https://help.openai.com/en/articles/10169521-projects-in-chatgpt

하지만:
- project memory가 어떤 특정 과거 세부사항을 반드시 가져온다고 deterministic하게 보장할 수 없음
- memory summary가 memory 전체를 모두 보여주는 것도 아님

따라서 프로젝트 memory를 **보조 hot context**로 활용할 수는 있어도 GitHub canonical state를 대체하면 안 됨.

## 현재 구현 불가 / 불필요

- AgeMem 같은 RL-trained policy
- TMEM/δ-mem 같은 model parameter adaptation
- OpenAI Dreaming 내부 synthesis engine 복제
- large-scale graph DB를 현재 필요성 증거 없이 구축

---

# 7. `kkamaknun`에 가장 적합한 설계 원칙 후보

아래는 **E4 적용 추론**이다. Phase 2 audit 후 Phase 3에서 확정/폐기한다.

## P1 — Repo는 system of record로 유지

별도 active memory repo를 만들지 않는다.

근거:
- OpenAI harness engineering
- file-based memory 연구
- 현재 ChatGPT GitHub live access

## P2 — bootstrap은 작고 stable한 router

세션 시작에 필요한 것은 `전체 지식`이 아니라:
- 현재 project identity
- canonical current state가 어디 있는지
- 필요한 policy/procedure/evidence를 어디서 찾는지

근거:
- OpenAI map-not-manual
- Anthropic progressive disclosure/context engineering

## P3 — current state는 단일 canonical owner

mutable state를 `USER_CONTEXT`, README, plans 여러 곳에 복제하지 않는다.

근거:
- STALE
- DynamicMem
- deterministic freshness

## P4 — stable context와 current state를 분리

- 오래 유지되는 사용자/프로젝트 조건
- 지금 시점의 project state

을 다른 memory class로 취급.

## P5 — procedural / judgment memory는 사실/역사와 분리

재사용 가능한 `어떻게 판단할지`는 concise skill/policy로 유지.

근거:
- AFTER procedural memory
- LongMemEval-V2 workflow/gotcha axes

## P6 — raw evidence는 삭제/덮어쓰기 금지

`기록/`, git history, 실제 실측은 canonical summary와 별도로 남김.

근거:
- ReFind
- faulty continuous consolidation
- HaluMem

## P7 — retrieval은 agentic iterative search 우선

현재 store 규모에서 별도 vector DB/graph를 먼저 도입하지 않는다.

우선순위:
1. canonical route
2. filename/lexical search
3. surrounding context
4. date/state narrowing
5. 필요하면 추가 evidence file

근거:
- AgentRunbook-C
- ReFind
- Infini iterative retrieval

## P8 — canonical write는 admission gate를 통과

모든 대화/실패를 저장하지 않는다.

저장 후보가 되려면:
- 앞으로 재사용될 가능성
- 정확한 evidence
- existing owner와 conflict 확인
- 기존 상위 원칙으로 이미 설명되지 않는가

를 확인.

AgentRunbook-C V2의 strategy memory처럼 **default는 no write**에 가깝게 둔다.

## P9 — consolidation은 batch/gated/non-destructive

- session/meaningful milestone 단위
- source evidence 유지
- canonical owner만 update
- git에서 이전 version 복구 가능

매 turn rewrite 금지.

## P10 — stale/superseded는 적극적으로 표시

기억 성능은 `옛 것을 잘 기억하는 것`이 아니라 `옛 것을 현재처럼 쓰지 않는 것`까지 포함.

## P11 — retrieval strategy memory가 필요하면 사실 memory와 분리

예: `장비 질문이면 장비세팅부터`, `현재 상태면 진행상태 우선` 같은 **retrieval path**는 작은 strategy/router memory로 가능.

단, 과거 answer text 자체를 shortcut으로 저장하지 않는다.

## P12 — eval은 행동을 본다

최종 eval에는 최소:
- static state
- dynamic state
- workflow
- gotcha
- premise awareness
- stale state resolution
- pressure resistance
- selective retrieval
- 실제 기획 행동

이 들어가야 한다.

MemoryArena가 보여주듯 recall QA만 통과해도 실제 planning agent가 잘한다고 말할 수 없음.

## P13 — latency / context overhead를 성능에 포함

architecture가 정확해도 매 답변마다 수십 번 tool call을 요구하면 실패일 수 있음.

평가:
- tool calls
- loaded context
- response latency
- user clarification count

## P14 — 모델 업그레이드 시 harness를 다시 공격

새 모델이 동일 task를 더 적은 scaffolding으로 수행하면 규칙/절차를 제거하는 쪽이 우선.

---

# 8. 현재 기준으로 채택하지 않을 것

Phase 2 audit에서 새로운 필요가 발견되지 않는 한 다음은 채택하지 않는다.

- 별도 active `agent-memory` repository
- 모든 chat turn permanent summary
- 모든 source를 매 session preload
- knowledge graph / vector DB를 선행 구축
- 매 turn LLM consolidation
- memory를 하나의 giant markdown으로 합치기
- retrieval score만 보고 final behavior 성능이라고 간주
- user가 매 새 chat마다 handoff prompt를 복사하는 방식
- `사용자가 더 찾아보라고 했다`는 이유로 새 rule/defect를 생성

---

# 9. Research-derived target hypothesis — Phase 2 전 provisional

현재 가장 근거가 강한 target hypothesis:

```text
                 ┌─────────────────────┐
                 │ SMALL BOOTSTRAP MAP │
                 └──────────┬──────────┘
                            │
                   always current route
                            ▼
                 ┌─────────────────────┐
                 │ CANONICAL CURRENT   │
                 │ STATE               │
                 └──────────┬──────────┘
                            │ task-dependent
             ┌──────────────┴──────────────┐
             ▼                             ▼
┌────────────────────────┐      ┌────────────────────────┐
│ STABLE DECLARATIVE     │      │ PROCEDURAL / JUDGMENT │
│ USER+PROJECT CONTEXT   │      │ MEMORY                 │
└───────────┬────────────┘      └───────────┬────────────┘
            └──────────────┬────────────────┘
                           │ evidence needed
                           ▼
                ┌───────────────────────┐
                │ RAW EPISODIC /       │
                │ DECISION / EVIDENCE  │
                │ + GIT HISTORY        │
                └───────────────────────┘
```

Retrieval policy provisional:

```text
read minimal router/current state
→ classify task
→ load only relevant durable memory
→ if claim/history needs support: iterative search raw evidence/history
→ resolve current vs stale
→ answer / act
```

Write policy provisional:

```text
new information
→ does it change current state?
   → update canonical owner, preserve previous version
→ is it stable long-term context?
   → quality/admission check then promote
→ is it reusable procedure/judgment?
   → only after evidence/validation and generalization check
→ otherwise
   → leave in raw history / do not promote
```

이 가설은 **Phase 2의 실제 repo audit에서 변경될 수 있다.**

---

# 10. P1 Exit Gate 평가

## Gate 1 — 서로 다른 3개 이상 연구/실무 계열에서 수렴하는가?

**PASS**

독립적으로 수렴:
- OpenAI production harness + Dreaming
- Anthropic context/harness/skills/evals
- LongMemEval-V2 / AgentRunbook
- ACL memory management
- ReFind / Infini / filesystem memory
- STALE / DynamicMem / Memora

## Gate 2 — 특정 vendor 한 글에 의존하는가?

**PASS**

OpenAI/Anthropic뿐 아니라 peer-reviewed ACL/ICLR/ICML + 다수 independent 2026 preprint를 교차함.

## Gate 3 — 2026 결과가 2024~2025 foundational 결과를 어떻게 수정했는가?

**PASS**

2024~2025의 핵심은 `긴 context에서 retrieval degradation → external memory / retrieval 필요`였다.

2026은 이를 더 구체화함:
- 단순 external memory만으로 부족
- stale resolution / selective forgetting 필요
- continuous consolidation 자체가 위험할 수 있음
- filesystem organization은 cost를 줄여도 accuracy를 자동 개선하지 않음
- raw archive agentic retrieval이 structured memory와 경쟁 가능
- 실제 agent behavior는 recall benchmark보다 훨씬 어렵고 별도 eval 필요
- 모델이 좋아질수록 harness는 더 단순해질 수 있음

## Gate 4 — 다른 workload의 benchmark를 그대로 일반화했는가?

**PASS**

각 연구마다 적용 범위를 별도 기록했으며, graph/RL/parametric architecture는 현재 workload에 직접 복제하지 않도록 제외/보류함.

## Gate 5 — 연구 결과와 AI 적용 추론을 구분했는가?

**PASS**

Evidence matrix는 E1~E3, `kkamaknun` 적용 원칙은 E4로 분리함.

---

# 11. Phase 1 최종 판정

**P1 = PASS**

현재 연구로 확정할 수 있는 것은 특정 memory 제품 하나가 아니라 다음 설계 방향이다.

> **작은 bootstrap + explicit canonical current state + stable declarative memory + procedural/judgment memory + raw evidence preservation + agentic iterative retrieval + guarded/non-destructive writes + explicit stale/supersede + behavioral cold-start eval**

다음 단계는 이 구조를 바로 구현하는 것이 아니다.

> **PHASE 2 — 현재 `kkamaknun` repo를 전수 감사하여 실제로 어디가 이 연구 원칙과 충돌하는지, 무엇은 이미 잘 되어 있는지, 무엇만 바꿔야 하는지 증거 기반으로 확인한다.**

Phase 2 audit 전에는 architecture file을 수정하지 않는다.
