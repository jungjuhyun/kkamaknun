# AGENTS.md — 까막눈 repository 운영 규칙

이 파일은 저장소 안에서 작업할 때 적용되는 공통 운영 규칙과 source owner routing을 정의한다. 저장소의 현재 사실은 이 파일이 아니라 각 owner 문서에 둔다.

## 1. 범위와 상위 계층

- ChatGPT Work Project instruction은 저장소 식별과 session-level ref/bootstrap/freshness 결정, GitHub 접근 실패 처리, 최소 UI/project-level 규칙을 소유한다.
- 이 파일은 ref를 선택하거나 bootstrap·freshness 절차를 정의하지 않고, 특정 PR·feature branch·selector 구현을 영구적으로 기록하지 않는다. repository 작업은 상위 계층이 확정한 snapshot에서만 시작한다.
- Claude는 CLAUDE.md를 통해 이 파일을 adapter로 읽는다. CLAUDE.md의 protected Karpathy block은 변경하지 않는다.
- 이 저장소의 운영 규칙을 프로젝트 instruction, Claude adapter, hook, 계획서에 복제해 여러 owner를 만들지 않는다.

## 2. Source owner

| 책임 | owner | 범위 |
|---|---|---|
| 저장소 운영 원칙·routing·변경 절차 | root AGENTS.md | 저장소 전체 |
| subtree 개발 규칙 | 해당 경로의 scoped AGENTS.md | 그 subtree와 하위 경로 |
| 사람이 읽는 현재 상태·다음 행동 | STATE.md | 현재 프로젝트 상태 |
| runtime 현재 실행 상태 | tools/harness/STATE.json | 현재 공정·편·lock·입력 경로 |
| 공통 영상 기획 process | tools/harness/PIPELINE.yaml | 모든 영상 기획 공정 |
| 공통 deterministic 규칙 | tools/harness/COMMON_RULES.json | 모든 편에 공통인 기계 검사 |
| 편별 deterministic lock | STATE.json이 가리키는 lock 파일 | 해당 편의 사실·잠금·금지 문구 |
| 첫 콘텐츠의 세부 사실·기획 기준 | FIRST_VIDEO.md | 1화 |
| 장기 판단 원칙 | PLAYBOOK.md | 반복 적용할 기획·운영 원칙 |
| 안정적 프로젝트 배경 | PROJECT_CONTEXT.md | 채널·프로젝트의 지속적 맥락 |
| 사용자 적합성 정보 | USER_PROFILE.md | 실제 판단을 바꾸는 안정적 특성 |
| 외부 근거·보조 자료 | references/ | current truth를 대체하지 않는 source |
| 실행 계획·과거 기록 | plans/ | 현재 상태의 owner가 아님 |
| Claude 세션 context 주입 | tools/harness/hook_session_start.py | STATE.md 주입만 담당 |
| 명령 deterministic guard | tools/harness/hook_guard.py | 위험한 main/backup git 명령 차단 |
| Claude adapter | CLAUDE.md | protected block + AGENTS.md import만 담당 |

같은 사실을 여러 owner에 복제하지 않는다. 기록을 남길 필요가 있으면 사실의 종류에 맞는 owner 하나를 먼저 정한다.

## 3. Bootstrap 이후의 읽기 순서와 retrieval

상위 Work Project instruction이 snapshot을 확정한 뒤 저장소 의존 작업은 다음 순서로 읽는다.

1. STATE.md
2. root AGENTS.md
3. 현재 요청에 필요한 owner 문서
4. 기획 결과물을 요청한 경우 tools/harness/STATE.json → 그 파일이 지정한 PIPELINE.yaml → 현재_lock 파일

모든 문서를 일괄 preload하지 않는다. 현재 요청과 무관한 계획서, history, backup branch, 폐기 문서는 기본 retrieval 대상이 아니다.

- repo에 접근할 수 없으면 current state를 기억이나 이전 채팅으로 복원했다고 말하지 않는다.
- repo와 memory, 이전 대화, 모델의 추측이 충돌하면 current snapshot의 owner를 따른다.
- 과거 기록이 필요한 경우에도 먼저 현재 owner를 확인하고, 과거 자료는 역사적 근거로만 표시한다.
- 현재 사실, 사용자 제공 사실, 외부 조사 결과, 가정·시뮬레이션을 문장과 자료에서 구분한다.

## 4. 요청별 routing

- 현재 상태·다음 행동·진행 요약: STATE.md를 기준으로 답한다.
- 첫 콘텐츠의 각·장면·구조·패키징: FIRST_VIDEO.md를 읽는다.
- 큰 기획 판단·반복 원칙: PLAYBOOK.md를 읽고, 안정적 배경이 판단을 바꾸면 PROJECT_CONTEXT.md를 추가한다.
- 사용자 적합성이 선택을 바꾸는 경우에만 USER_PROFILE.md를 추가한다.
- 외부 근거가 필요한 경우 관련 references와 최신 원출처를 구분해 확인한다.
- 실제 영상의 아이디어·각·구조·패키징을 요청받으면 video_planning 공정을 실행한다.

영상 기획 routing은 다음을 고정한다.

1. tools/harness/STATE.json에서 현재 공정, 현재 편, 현재_lock, 입력 경로와 계획 단계를 확인한다.
2. STATE.json이 지정한 PIPELINE.yaml의 순서와 통과 조건을 따른다.
3. STATE.json의 현재_lock 경로를 사용한다. EP1_LOCK.json 등 특정 편의 lock을 추측하거나 하드코딩하지 않는다.
4. 실제 촬영물·실험 결과·관찰 기록이 있으면 material_first를 사용한다.
5. material_first에서는 실제 footage와 material에서 사건·반응·변화를 먼저 찾고, 촬영 전의 예상이나 가상 원안이 이를 덮어쓰지 않게 한다.
6. pipeline을 건너뛰고 바로 각·구조·패키징을 작성하지 않는다.

하네스 구현·감사·instruction source 수정 요청은 영상 기획 결과물 요청이 아니므로 video_planning pipeline을 실행하지 않는다. tools/scene_collector 아래 작업은 해당 scoped AGENTS.md를 함께 따른다.

## 5. 사실·외부 조사·도구 선택

- 실제 footage/material이 사전 기획이나 예상보다 우선한다. 실제 결과가 예상과 다르면 실제 재료 안에서 다시 기획한다.
- 확보하지 못한 자료, 확인하지 않은 장면, 검증하지 않은 인과·수치·관계·대사를 사실처럼 쓰지 않는다.
- 행별 대조 자료나 일부 관찰을 전체 작품·전체 자막·일반 능력으로 확대하지 않는다.
- 외부 사실·최신 정보·가격·규칙·기술 상태·성과 수치가 판단에 영향을 주면 웹에서 현재 원출처를 확인한다. 검색하지 않은 외부 사실을 확인한 것처럼 보고하지 않는다.
- 외부 자료를 사용할 때 저장소 current truth, 사용자가 제공한 source, 외부 조사와 AI의 추론을 분리한다.
- 새 도구·서비스·구현을 선택할 때는 다음 순서를 기본으로 한다.

Search → Evaluate → Adopt/Buy → Adapt → Build last

이미 있는 도구나 현재 구조로 목적을 달성할 수 있는지 먼저 확인하고, 새 framework·agent·규칙·문서 계층을 실패 근거 없이 추가하지 않는다.

## 6. 영상 기획 품질과 validator의 경계

- A/B→C는 큰 기획 뼈대이며 경쟁 사례 분석을 대체하지 않는다.
- material_first에서는 실제 사건·반응·시청각 신호에서 A+B가 특별해지는 장면을 찾은 뒤 콘텐츠 각과 구조를 만든다.
- 촬영 전 가정과 실제 결과를 섞지 않는다. 2차·3차 시청이나 재촬영은 1차 시청인 것처럼 재배열하지 않는다.
- deterministic validator는 current truth·lock·자료 경계·명백한 금지 문구만 검사한다.
- validator의 PASS는 기획 재미, 시청 지속, 콘텐츠 각, RED TEAM 통과나 최종 품질을 뜻하지 않는다.
- RED TEAM은 살아남은 안의 명백한 약점을 공격하는 절차이지 좋은 기획 인증서가 아니다.
- 공정과 current truth를 지켰는데 영상이 약하면 planning_quality_failure로 분리해 판단한다. 실패했다고 자동으로 harness layer를 추가하지 않는다.
- 실제 기획의 최종 품질 판정은 사용자에게 남긴다. AI는 근거, deterministic 결과, 남은 불확실성을 정확히 보고한다.

## 7. Owner별 변경 원칙

- 현재 프로젝트 상태와 다음 행동이 바뀌면 STATE.md를 갱신한다.
- 첫 콘텐츠의 세부 사실·구조·잠금 전제가 바뀌면 FIRST_VIDEO.md와 필요한 lock의 책임을 확인한 뒤 해당 owner만 갱신한다.
- runtime 실행 상태가 바뀌면 tools/harness/STATE.json을 갱신한다.
- 공통 영상 공정이 바뀌면 PIPELINE.yaml을 갱신하고 특정 편 전용 규칙을 공정에 섞지 않는다.
- 오래 유지될 판단 원칙은 PLAYBOOK.md에 둔다.
- 새 문서는 기존 owner로 명확히 해결할 수 없을 때만 만든다.
- 새 파일 이름은 영문·숫자·밑줄만 사용한다.
- 일회성 대화·가상 수치·실패 사례를 자동으로 지속 지식으로 승격하지 않는다.
- instruction, prompt, config, workflow를 바꿀 때는 부분 문구를 덧붙이지 않는다. 관련 source와 참조 관계를 먼저 전수 조사하고, owner·중복·충돌·stale 규칙을 정리한 뒤 통합 교체하고 검증한다.

## 8. Repository mutation procedure

repo 변경이 승인된 경우 AI가 가능한 수정을 직접 수행한다. 사용자에게 파일 복사·수동 편집·삭제·커밋을 넘기지 않는다.

변경 순서는 다음과 같다.

1. 현재 snapshot의 관련 source, 참조, owner와 변경 범위를 확인한다.
2. 변경 직전에 처음 확정한 snapshot SHA와 현재 작업 ref의 head SHA가 같은지 확인한다.
3. head가 바뀌었으면 새 snapshot에서 audit와 diff를 다시 계산한다. 승인 범위 안의 변경이면 재승인을 요구하지 않고 최신 상태에서 계속한다. 범위가 확장되면 중단하고 보고한다.
4. 승인된 범위 안에서 AI가 직접 수정·삭제한다. 사용하지 않는 stale instruction/bootstrap 파일은 실제 dependency가 없을 때만 제거한다.
5. JSON/YAML/Python과 관련 validator·hook·테스트를 실행해 검증한다.
6. 가능한 경우 관련 변경을 하나의 atomic commit으로 만든다. 파일마다 별도 commit을 만들지 않는다.
7. main에 직접 commit하거나 push하지 않는다. 작업 ref를 확인하고 그 ref에만 commit/update한다. 현재 feature branch 이름을 문서에 영구 하드코딩하지 않는다.
8. atomic single commit을 보장할 수 없으면 write를 시작하지 않고 제한을 보고한다.
9. commit 후 remote/ref를 다시 확인해 실제 post-commit SHA와 변경 파일을 검증한다.

instruction source를 수정할 때는 관련 source 전체 확인 → owner 판정 → 중복·충돌·stale 제거 → 통합 교체 → parse/test/reference scan의 순서를 지킨다.

