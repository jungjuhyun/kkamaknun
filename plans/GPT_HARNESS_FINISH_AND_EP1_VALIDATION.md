# GPT 하네스 마무리 + EP1 실전 검증·recovery 계획

기준일: 2026-09-14

상태: 진행 중 — REVIEW_B planning_quality_failure 종료, source reconstruction evidence 생성 완료, 독립 감사 대기

현재 상태 owner: `STATE.md`

공통 process owner: `tools/harness/PIPELINE.yaml`

## 1. 목적과 완료 기준

목적은 하네스 계층을 늘리는 것이 아니라, 실제 material에서 작품 감상과 청해·reaction을 함께 살리는 기획을 반복 가능하게 만드는 것이다.

최종 성공 조건은 다음 세 가지다.

1. current truth, lock, 실제 material, 내부 provenance가 보존된다.
2. 외부 source narrative가 있는 material-first 영상은 source reconstruction을 거쳐 narrative continuity와 핵심 사건 coverage를 보존한다.
3. AI/harness의 pre-render 품질 gate와 실제 review rough cut 시청 테스트 뒤 사용자가 제작 진행을 결정할 수 있다.

REVIEW_B는 2번을 충족하지 못해 **planning_quality_failure**다. 이번 recovery는 evidence layer까지 재구축하고, final select·body·Cold open·REVIEW_C는 다음 독립 감사 뒤로 남긴다.

## 2. 고정 범위

다음은 재설계하지 않는다.

- A: 20년 이상 취미로 애니를 봐왔지만 일본어를 제대로 공부해본 적은 없는 사람
- B: `체인소 맨: 레제편`을 한국어 자막 없이 보고, 자기 귀에 실제로 무엇이 남아 있는지 확인한다.
- C: 20년 동안 좋아한 시간이 사람한테 이렇게 남을 수도 있구나. 신기하다.
- primary material과 stream 2 desktop / stream 3 mic 사실
- 재확인·재시청·재촬영의 내부 provenance와 최초성 경계
- viewer-facing 영상에 provenance overlay를 자동 노출하지 않는 원칙

기존 34 candidates / 15 selects는 삭제하지 않지만 historical evidence다. REVIEW_B를 수정하거나 그 select로 REVIEW_C를 만들지 않는다.

## 3. REVIEW_B 공식 FAIL

사용자의 실제 시청 결과를 다음 구조 문제로 해석한다.

| 실패 | 구조 원인 |
|---|---|
| chronology는 대략 맞지만 장면이 이어지지 않음 | chronology integrity를 narrative continuity로 오인 |
| 레제의 죽음과 결말 payoff가 약함 | 청해 증거 점수가 source narrative MUST_KEEP보다 우선 |
| 청해 사례와 reaction이 따로 놈 | 핵심 일본어 한 문장을 scene 단위로 사용 |
| `사메노 마진`, `漢字読めないの？` 반복 | Cold open을 body 전 설계하고 semantic reuse 검사를 하지 않음 |
| 핵심 구간 판단 불안정 | 제한적 large-v3 전사와 후보 중심 검증에 과의존 |

이 FAIL은 A/B/C가 틀렸다는 뜻이 아니다. **작품 서사 = 골격 / listening = 소재·발견 / reaction = 재미·인물성**이라는 책임 배치가 공정에 없었던 것이 root cause다.

## 4. 공통 material-first recovery 공정

외부 원작·경기·공연·사건처럼 자체 서사가 있는 경우 후보 경쟁 전에 네 layer를 독립 복원한다.

1. Layer A — source narrative
2. Layer B — desktop dialogue/audio
3. Layer C — user mic raw
4. Layer D — visual/nonverbal reaction

Layer A는 source TC별 사건, 관계·감정 변화, 앞뒤 의존 정보, narrative function과 `MUST_KEEP / BRIDGE / OPTIONAL`을 기록한다. 중요도는 청해와 독립 판정한다. Layer B/C는 absolute TC, overlap, uncertainty, raw/interpretation 분리를 지킨다. Layer D는 transcript로 추정하지 않고 영상 evidence로 확인한다.

네 layer를 synchronized evidence timeline으로 정렬하기 전에는 최종 scene 후보 경쟁으로 넘어가지 않는다.

## 5. Scene unit과 본편 구조

scene 기본 단위는 가능한 범위의 다음 묶음이다.

> source setup → 작품 대사/사건 → 사용자의 이해·오해 → 실제 reaction → 작품의 결과/다음 상태

역할은 `ANCHOR / STORY_REACTION / STORY_LISTENING / BRIDGE / EVIDENCE / CHARACTER`로 구분한다. EVIDENCE/CHARACTER만으로 본편 spine을 만들지 않는다.

본편을 Cold open보다 먼저 설계한다. chronology integrity는 남긴 사건 순서 보존이고, narrative continuity는 컷 사이 상황·관계·질문·감정·인과 보존이다. 모든 큰 cut boundary에서 다음을 확인한다.

- 현재 작품 상황을 이해할 수 있는가
- 앞 scene의 어떤 상태를 이어받는가
- 생략 뒤에도 다음 scene의 의미가 남는가
- reaction의 원인이 보이는가
- 분석 태그 때문에 장면이 억지로 들어오지 않았는가

## 6. Cold open과 pre-render gate

본편 완성 뒤 Cold open을 다시 경쟁시킨다. teaser의 body scene이 본편에 재등장하면 더 큰 맥락, 원인/결과, 새 정보, 새 감정, payoff, 의미 재해석 중 하나 이상이 추가돼야 한다.

다음 중 하나라도 FAIL이면 render하지 않는다.

- MUST_KEEP 누락
- climax/resolution/emotional closure의 근거 없는 삭제
- narrative continuity 단절 또는 reaction 원인 절단
- 청해 사례 세 개 이상 연속 나열
- 작품 감상보다 analysis tag가 편집 순서를 지배
- Cold open/body 단순 중복
- 동일 listening/reaction 기능 반복
- scene context 절단으로 원본 의미 변경
- A/B→C 증명 때문에 작품 감상 자체 붕괴

AI/harness가 이 gate를 책임지며 사용자에게 전문 판정을 넘기지 않는다.

## 7. EP1 transcription 실행

primary material 전체 `01:45:25`를 처리한다.

- desktop: stream 2, 일본어 원문 우선, 작품명·고유명사 context, absolute TC, 40초 core + 양쪽 5초 overlap
- mic: stream 3, Korean/Japanese code-switch, verbatim 우선, 오청·오발음 교정 금지
- primary local ASR: `Qwen/Qwen3-ASR-1.7B` + `Qwen/Qwen3-ForcedAligner-0.6B`
- secondary: `faster-whisper large-v3`를 핵심·불확실 구간 독립 대조에만 사용
- historical large-v3: reference only

OpenAI transcription API는 credential 값을 읽거나 노출하지 않고 실제 사용 가능성만 확인한다. 사용할 수 없으면 mini·낮은 모델로 몰래 fallback하지 않는다. local 대안의 품질이 planning truth를 지탱하지 못하면 중단한다.

## 8. Narrative reconstruction 범위

합법적으로 접근 가능한 공식 작품 소개·신뢰 가능한 상세 줄거리를 실제 desktop audio와 화면에 대조한다. 자막·대본 원문 전체를 repository에 복제하지 않는다.

특히 다음 구간을 독립 QA한다.

- 초반 setup과 마키마 관계 기준
- 레제와 만남·관계 진전·학교/수영장
- 정체/위협 전환과 53:00~58:10
- 전투 시작·동료 개입·전투 climax
- 95:10~98:07 해변 관계 회수
- 레제의 배경과 최종 선택
- 레제 죽음
- 100:12~105:18 결말

후반은 `전투 재기·climax → 해변 대화 → 레제의 배경 → 귀환 선택 → 죽음 → 덴지가 모른 채 기다리는 결말`의 인과를 하나의 회수 사슬로 본다.

## 9. 이번 실행 artifact와 중지점

이동식 SSD의 portable external material 영역인 `K:\kkamaknun\transcription\`에 다음을 둔다. Git working repository는 집과 회사 모두 `C:\kkamaknun`이며 GitHub로 동기화한다. `K:\kkamaknun\repo`는 historical/transport copy로만 보존하고 current 실행 경로로 사용하지 않는다. 2026-09-14 최초 생성 위치 `C:\kkamaknun_transcription\` 및 그 C: artifact 원본은 historical provenance로만 보존하고 current 실행 입력으로 사용하지 않는다.

- `EP1_DESKTOP_JA_FULL.jsonl`
- `EP1_MIC_RAW_FULL.jsonl`
- `EP1_SYNC_TIMELINE.jsonl`
- `EP1_SYNC_TIMELINE.csv`
- `EP1_NARRATIVE_MAP.md`
- `EP1_TRANSCRIPTION_QA.md`
- `EP1_NEW_SCENE_POOL.md`

이번 실행은 source audit, workflow refactor, 전체 전사, narrative map, synchronized evidence timeline, 새 scene pool에서 멈춘다. final select, body, Cold open, REVIEW_C는 만들지 않는다.

## 10. Owner 반영

- `AGENTS.md`: routing과 source reconstruction 진입 원칙
- `PLAYBOOK.md`: 장기 반복 원칙
- `tools/harness/PIPELINE.yaml`: 공통 material-first 단계·scene unit·continuity·render gate
- `FIRST_VIDEO.md`: EP1 stream/외부 source 경계/recovery 실행 계약
- `materials/ep1_main/PLANNING_RESULTS.md`: REVIEW_B FAIL evidence, 과거 34/15 격리, 새 evidence 연결
- `STATE.md` / `tools/harness/STATE.json`: 사람이 읽는 현재 상태와 runtime 다음 행동
- `tools/harness/EP1_LOCK.json`: A/B/C와 primary material truth의 최소 잠금
- 이 계획서: historical run과 current recovery를 한 실행 계획으로 통합

`COMMON_RULES.json`과 deterministic validator는 재미·continuity를 문자열 규칙으로 인증하지 않는다. 관련 regression test는 pipeline 계약의 누락만 검사한다.

## 11. Validation과 commit

repository 변경은 feature branch에 atomic single commit으로 남긴다.

- JSON parse
- YAML parse
- Python compile/test
- deterministic validator regression
- current truth / lock 일치
- stale reference scan
- `git diff --check`
- commit 후 remote/ref/SHA/changed files 재확인

원본 media, 분리 audio, 전사·frame·timeline 임시 artifact는 commit하지 않는다.

## 12. Historical record — current procedure 아님

- 2026-09-02 촬영 전 가상 완성본 POC는 패키징/본편 구조 FAIL로 종료했다.
- 2026-09-04 actual-material 분기, 후보 경쟁, deterministic validator/RED TEAM 책임 분리를 구현했다.
- 윤성원 PD 방법론을 A/B→C, 핵심 장면, 시청각 판단, 공유 단위, Cold open, 시청자 모드 검수에 연결했다.
- 2026-09-13 primary 전체에서 34 candidates와 15 selects를 만들고 REVIEW_A/B를 렌더했다.
- provenance overlay를 viewer-facing에서 제거하는 결정은 유지한다.
- REVIEW_B 실제 시청에서 작품 핵심 사건·감정·payoff와 narrative continuity가 무너진 사실이 드러나 현재 recovery를 시작했다.

이 기록의 당시 promise proof, payoff 1순위, Cold open, select 판정은 재현용 history이며 current instruction이 아니다.
