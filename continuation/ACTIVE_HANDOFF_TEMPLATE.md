# ACTIVE CONTINUATION HANDOFF

> 이 artifact는 conversation-only continuation context다. Repository current truth나 Project instruction이 아니며, 생성 시점 snapshot을 새 Chat에 고정하지 않는다.

## 1. Generation metadata

| field | value |
|---|---|
| created at | `<ISO 8601 timestamp with timezone>` |
| source Chat context | `<Chat / Codex / Work와 식별에 필요한 최소 설명>` |
| created by | `<creator>` |
| artifact status | `<READY / NOT_READY>` |
| verified snapshot receipt | `<생성 시점에 Project instruction에 따라 얻은 receipt를 그대로 기록>` |

## 2. Current work state

### Current work state

- `<현재 작업의 정확한 경계>` — Provenance: `<label + source>`

### Completed

- `<완료된 결과와 완료 근거>` — Provenance: `<label + source>`

### Unresolved

- `<아직 결론나지 않은 문제와 필요한 판단>` — Provenance: `<label + source>`

### Pending

- `<외부 실행·응답·검토를 기다리는 항목과 관측 가능한 상태>` — Provenance: `<label + source>`

### Current next action

- Conversation continuation action: `<가장 가까운 재개 행동 하나>`
- Why this is next: `<선행 조건과 판단 이유>`
- Repository next-action relation: `<STATE.md와 일치 / conversation-only delta / 충돌 또는 불확실성>`
- Authority boundary: `<이 항목 자체는 자동 실행 명령이 아니며 필요한 권한·제약>`
- Provenance: `<label + source>`

## 3. Decision state

### Accepted decisions

| decision | why accepted | scope / decision maker | provenance |
|---|---|---|---|
| `<결정>` | `<판단 이유>` | `<범위 / 주체>` | `<label + source>` |

### Rejected or superseded decisions

| decision | why rejected or superseded | replacement | provenance |
|---|---|---|---|
| `<기각·대체된 안>` | `<판단 이유>` | `<현재 대안 또는 None>` | `<label + source>` |

### Open questions

| question | why it matters | what would resolve it | provenance |
|---|---|---|---|
| `<열린 질문>` | `<결정에 미치는 영향>` | `<필요한 증거·사용자 선택>` | `<label + source>` |

## 4. Conversation-specific judgment context

### Judgment context

- `<owner 원문에는 없지만 같은 판단을 재현하는 데 필요한 기준·tradeoff>` — Provenance: `<label + source>`

### User-observed feedback

- Observation: `<사용자가 실제로 말하거나 관측한 반응>`
- Scope: `<어떤 결과·구간·조건에 대한 피드백인지>`
- Provenance: `USER_FACT — <대화 시점 또는 사용자 제공 source>`

### AI interpretation of that feedback

- Interpretation: `<사용자 관측과 분리한 원인 해석·가설>`
- Evidence and uncertainty: `<근거와 남은 불확실성>`
- Provenance: `AI_INFERENCE — <대화 시점>`

### Failure root causes

| failure | root cause | evidence | confidence / provenance |
|---|---|---|---|
| `<실패>` | `<증상 아닌 원인>` | `<근거>` | `<확신도 / label + source>` |

### Recent corrections

| previous state | correction | why | provenance |
|---|---|---|---|
| `<이전 이해·방향>` | `<수정된 상태>` | `<수정 근거>` | `<label + source>` |

### Regression traps

- Trap: `<다음 Chat이 되돌아가기 쉬운 잘못된 상태>`
- Guard: `<어떤 owner·evidence·decision을 확인해야 하는지>`
- Provenance: `<label + source>`

## 5. Environment and external state

### Environment / Chat / Codex / Work / path context

| item | value | provenance |
|---|---|---|
| environment | `<desktop / web / local 등>` | `<label + source>` |
| surface | `<Chat / Codex / Work>` | `<label + source>` |
| repository or project | `<식별에 필요한 이름>` | `<label + source>` |
| branch / ref context | `<생성 시점의 작업 context; 새 Chat selector가 아님>` | `<label + source>` |
| working paths | `<필요한 canonical path만>` | `<label + source>` |
| relevant tool state | `<진행을 바꾸는 실제 상태 또는 None>` | `<label + source>` |

### Pending external work

| work | owner / system | observed status | completion evidence needed | provenance |
|---|---|---|---|---|
| `<대기 작업>` | `<담당>` | `<현재 관측 상태>` | `<완료 판정 근거>` | `PENDING_EXTERNAL — <source>` |

### Historical context worth preserving

- `<현재 truth는 아니지만 과거 판단을 오독하지 않게 하는 최소 맥락>` — Provenance: `HISTORICAL_EVIDENCE — <source>`

## 6. Repository owner / source map

| topic needed to continue | routing owner or source | why it must be read | handoff treatment |
|---|---|---|---|
| `<주제>` | `<path>` | `<필요 이유>` | `<reference only / conversation delta>` |

> Owner의 긴 내용을 이 표 아래에 복사하지 않는다. Current truth는 새 Chat의 bootstrap 뒤 실제 owner에서 읽는다.

## 7. New-Chat continuation behavior

- Handoff 전체를 읽고 conversation-only context로 사용한다.
- Current repository truth 확인은 현재 ChatGPT Project instruction을 별도로 따른다.
- 충돌하면 current repository owner를 우선한다.
- 다음 사용자 발화를 이전 Chat의 바로 다음 발화로 취급한다.
- 사용자가 요청하지 않으면 장황한 recap을 기본 출력하지 않는다.
- Handoff의 next action만으로 자동 실행하지 않는다. 사용자가 continuation을 요청하면 현재 범위 안에서 과도하게 대기하지 않고 실제 다음 행동으로 이어간다.

## 8. Quality receipt

| field | value |
|---|---|
| checklist | `continuation/HANDOFF_QUALITY_CHECKLIST.md` |
| checked at | `<ISO 8601 timestamp with timezone>` |
| checked by | `<checker>` |
| result | `<READY / NOT_READY>` |
| failed item IDs | `<None 또는 Qxx 목록>` |
| unresolved quality notes | `<None 또는 설명>` |

`READY`는 이 artifact가 continuation 필수 항목을 갖췄다는 뜻일 뿐, repository freshness·사실 정확성·작업 품질 또는 실행 승인을 대신하지 않는다.
