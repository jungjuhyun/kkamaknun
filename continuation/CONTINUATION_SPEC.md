# CONTINUATION_SPEC.md — active continuation 생성 계약

## 1. Ownership과 범위

이 문서는 **한 Chat의 conversation-only decision state와 작업 연속성을 다른 Chat으로 전달하는 active continuation artifact 생성 계약**의 owner다.

이 계약이 소유하는 것은 handoff에 남길 대화 전용 상태, provenance, 필수 항목, 생성·검수 방식과 새 Chat의 진입 행동뿐이다. 다음 책임은 소유하지 않는다.

- repository selector, bootstrap, immutable snapshot, same-chat freshness, GitHub 접근·실패 처리, bootstrap receipt는 ChatGPT Project instruction만 소유한다.
- repository 운영 원칙과 source routing은 root `AGENTS.md`가 소유한다.
- repository의 current project state와 project-level next action은 `STATE.md`, runtime state는 `tools/harness/STATE.json`, 세부 current truth는 각 owner가 소유한다.
- 장기 영상 기획 판단 원칙은 `PLAYBOOK.md`, material-first/pre-shoot 분기와 source reconstruction·후보 경쟁·boundary·Opening·UAT recovery를 포함한 공통 executable process는 `tools/harness/PIPELINE.yaml`이 소유한다.
- 특정 작업의 계획·과거 handoff·평가 checkpoint는 그 문서가 명시한 한정된 범위의 기록이며 이 계약을 대체하지 않는다.

current repository truth 확인은 현재 ChatGPT Project instruction을 따른다. 이 문서는 그 절차나 receipt 형식을 복제하지 않는다.

## 2. Active continuation의 정의

Active continuation은 생성 시점에 아직 repository owner로 완전히 흡수되지 않은 **대화 전용 판단 상태와 작업 경계**를 다음 Chat이 이어받도록 만든 point-in-time transfer artifact다.

단순 요약은 있었던 일을 압축한다. Active continuation은 다음 행동을 같은 판단 상태에서 재개할 수 있도록 아래를 함께 보존한다.

- 무엇이 완료·미해결·대기 중인지
- 현재 next action과 그것이 다음인 이유
- 채택·기각·대체된 결정과 판단 근거
- 사용자 관측과 AI 해석의 구분
- 실패 원인, 최근 correction, 다시 빠지기 쉬운 regression trap
- 외부 작업과 불확실성의 실제 상태
- 각 사실과 판단의 source provenance

Active continuation은 current truth owner, 장기 지식 저장소, Project instruction, 실행 계획 승인서 또는 자동 실행 명령이 아니다.

## 3. Repository truth와 handoff의 관계

1. 생성 시점에는 현재 Project instruction이 확정한 repository snapshot에서 필요한 owner를 실제로 읽고, 그 결과를 `verified snapshot receipt`로 연결한다.
2. handoff의 repository 관련 내용은 **그 생성 시점에 확인한 상태의 색인**이다. 새 Chat의 current repository truth는 별도 bootstrap 뒤 current owner에서 다시 얻는다.
3. handoff와 current owner가 충돌하면 current owner가 우선한다. handoff의 대화 전용 맥락은 current owner와 충돌하지 않는 범위에서 사용한다.
4. repository에 속하는 장기 결정이나 current state가 승인된 mutation으로 이미 owner에 반영됐다면 handoff에는 긴 내용을 복사하지 않고 owner 경로와 필요한 이유만 적는다.
5. 아직 owner에 반영되지 않은 대화 결정이나 Chat-level 재개 행동은 `CONVERSATION_DECISION`으로 표시한다. 그것만으로 repository current truth, project-level next action 또는 repository mutation 권한이 생기지 않는다.
6. 생성 시점 snapshot SHA나 receipt는 provenance이지 새 Chat을 그 snapshot에 고정하는 selector가 아니다.

## 4. Source provenance

handoff의 사실·판단·상태에는 다음 label 중 하나를 붙인다. 서로 다른 source를 한 항목에 섞지 말고 필요하면 행을 나눈다.

| label | 의미 |
|---|---|
| `REPO_CURRENT` | 생성 시점 verified snapshot의 실제 owner에서 읽은 사실. owner 경로를 함께 적는다. |
| `USER_FACT` | 사용자가 직접 제공하거나 관측한 사실. AI 해석과 분리한다. |
| `CONVERSATION_DECISION` | 현재 Chat에서 채택됐지만 repository owner 자체는 아닌 결정 상태. 결정 주체와 범위를 적는다. |
| `HISTORICAL_EVIDENCE` | 과거 기록·이전 결과. current truth로 승격하지 않는다. |
| `EXTERNAL_RESEARCH` | 외부 source에서 확인한 정보. source와 확인 시각을 적는다. |
| `AI_INFERENCE` | AI의 해석·가설·권고. 근거와 불확실성을 적는다. |
| `PENDING_EXTERNAL` | 실행·응답·렌더·검토 등 외부 결과를 기다리는 상태. 완료로 쓰지 않는다. |

사용자 실제 피드백은 `USER_FACT`, 그 피드백의 원인 해석은 별도 `AI_INFERENCE` 항목으로 기록한다. 직접 확인되지 않은 repository 사실을 memory, 이전 대화 또는 handoff 문장으로 메우지 않는다.

## 5. Artifact 생성 계약

`ACTIVE_HANDOFF_TEMPLATE.md`를 복제해 하나의 self-contained Markdown artifact를 만든다. 생성 파일명은 영문·숫자·밑줄만 사용하고, 예시는 `ACTIVE_CONTINUATION_YYYYMMDD_HHMMSS.md`다. 생성 artifact를 repository에 저장·commit하는 것은 별도 요청이 있을 때만 한다. 저장 위치와 무관하게 artifact는 current truth owner가 아니다.

생성 순서는 다음과 같다.

1. current repository truth를 현재 Project instruction에 따라 확인한다.
2. root `AGENTS.md`의 routing으로 현재 작업에 필요한 owner를 실제로 읽는다.
3. repository owner에 이미 있는 긴 내용은 복사하지 않고 owner/source map으로 연결한다.
4. 대화에만 있는 decision state, 이유, 사용자 피드백, correction, unresolved state와 regression trap을 추출한다.
5. completed, unresolved, pending을 분리하고 pending 결과를 완료로 쓰지 않는다.
6. 모든 필수 section을 채운다. 해당 없음은 비워 두지 말고 `None — <이유>`로 적는다.
7. credential, token, secret, private key, session cookie와 불필요한 개인정보를 제거한다. secret의 존재가 작업에 중요하면 값 대신 보관 위치 또는 재인증 필요 여부만 적는다.
8. `HANDOFF_QUALITY_CHECKLIST.md`를 실행하고 결과를 artifact의 `quality receipt`에 기록한다. 필수 항목 하나라도 실패하면 `NOT_READY`이며 새 Chat용 완성 artifact로 표시하지 않는다.

생성 시점의 실제 상태만 기록한다. 긴 transcript, owner 원문, raw tool log 또는 외부 문서를 보존 수단처럼 통째로 붙이지 않는다. 판단 복원에 필요한 최소 근거와 source pointer를 남긴다.

## 6. Next action과 continuation 동작

handoff의 `current next action`은 현재 Chat에서 가장 가까운 재개 지점과 이유를 전달하는 conversation-level 상태다. Repository의 project-level next action을 주장할 때는 `STATE.md`를 source로 가리킨다. 어느 경우든 handoff 항목 자체는 명령, 권한, 승인 또는 background execution 요청이 아니다. 새 Chat은 handoff를 읽었다는 이유만으로 tool call, write, push, 외부 메시지 또는 pending 작업을 실행하지 않는다.

반대로 사용자가 bootstrap이 끝난 새 Chat에서 `이어서 진행하자`, `계속해`, `다음 단계 해줘`처럼 명시적으로 continuation을 요청하면, current owner와 충돌하지 않는 범위의 `current next action`을 실제 다음 행동으로 취급해 진행한다. recap 승인이나 이미 해결된 질문을 다시 요구하며 과도하게 대기하지 않는다. 다만 다음 행동이 현재 요청 범위를 넘어 새 권한·외부 조정·중대한 선택을 필요로 하거나 handoff와 current owner가 충돌하면 그 지점만 짧게 보고하고 필요한 입력을 받는다.

## 7. 새 Chat에서의 적용

1. `CONTINUATION_LOADER.md`의 짧은 진입문과 생성된 handoff를 함께 제공한다.
2. 새 Chat은 handoff 전체를 읽되, current repository는 현재 Project instruction으로 별도 bootstrap한다.
3. current owner와 handoff가 충돌하면 current owner를 따르고 차이를 작업 판단에 반영한다.
4. conversation-only context에는 handoff를 사용하고, 다음 사용자 발화를 이전 Chat의 바로 다음 발화로 취급한다.
5. 사용자가 요청하지 않으면 handoff의 장황한 recap을 기본 출력하지 않는다.

## 8. Framework 구성

- `CONTINUATION_SPEC.md`: authoritative 생성·적용 계약
- `ACTIVE_HANDOFF_TEMPLATE.md`: 매 transfer마다 채우는 artifact 양식
- `HANDOFF_QUALITY_CHECKLIST.md`: 완성 전 품질 gate와 receipt 기준
- `CONTINUATION_LOADER.md`: 새 Chat에 넣는 최소 진입문
