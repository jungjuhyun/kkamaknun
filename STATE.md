# STATE.md — 현재 상태

기준 시각: 2026-09-14 KST

## 현재 상태

클린시트 메모리/컨텍스트 구조의 **프로젝트 콜드스타트 검증 통과** 이후 메모리/컨텍스트 시스템 작업은 종료했다.

최근 대화에서 확정된 채널 정체성·기획 원칙·사용자 적합성 중 장기적으로 필요한 내용은 각 owner 문서에 반영했다.

## 기획자 공정 검증 상태

- **Creator Discovery는 현재 충분한 수준으로 종료**한다. 실제 판단에 필요한 새 정보가 생기지 않는 한 광범위한 인터뷰를 다시 시작하지 않는다.
- 광범위한 AI/OSS 기획 공정 조사도 현재 POC를 돌리기에 충분한 수준까지 했다. 주요 참고로 `ericrisco/rsc-harness`의 `youtube-ideation`, `sharbelxyz/nova-youtube-agent`, LLM-assisted ideation review 등을 검토했다. 실제 구현에 다시 쓸 때는 최신 상태를 웹에서 재확인한다.
- **POC1 통과** — 과거 카타카나 원재료를 가지고 수동 재현/보정 기획을 했고, 사용자가 통과 판정함.
- **POC2 진행 중** — 실제 정답이 미리 없는 촬영물을 대상으로 검증한다.
- POC2는 `2-A Material Logging`과 `2-B Planning`으로 나눠 본다. 2-A에서 1차 촬영물 재관찰과 사건 후보 판정까지 진행됐고, 2-B는 2026-09-02 가상 완성본 실험이 사용자 품질 판정에서 FAIL했다.
- **기획자/Planner 구현은 POC2-B가 실제 1화 재료로 다시 통과하기 전에는 고정하지 않는다.** 현재는 `plans/GPT_HARNESS_FINISH_AND_EP1_VALIDATION.md`의 단계별 교정·실전 검증 계획을 따른다.

## 기획 공정·하네스 현재 상태

2026-09-02의 **1화 촬영 전 가상 완성본 POC는 종료**됐다.

- 사용자 품질 판정: 패키징 **FAIL**, 본편 구조 **FAIL**.
- 판정 근거 owner: `plans/EP1_PLANNING_RELIABILITY_POC.md`.
- 이 실패 뒤 **새 가상 완성본을 또 만들지 않는다**고 결정했다.
- 이후 1차 약 82분 촬영본을 재관찰했고, 후보 9개 중 실제 사건 7개를 사용자 판정으로 확인했다. 따라서 `82분 1차 촬영본 재관찰`은 더 이상 다음 할 일이 아니다.
- 현재 1화 기획의 올바른 출발점은 **실제 촬영물·사건·반응 → A+B가 특별해지고 C가 생기는 장면 → 콘텐츠 각 → 구성**이다.

2026-09-04부터 `plans/GPT_HARNESS_FINISH_AND_EP1_VALIDATION.md`를 현재 하네스 교정·1화 실전 검증 계획으로 사용한다.

**현재 실행 위치:** **REVIEW_B planning_quality_failure 종료 → material-first source reconstruction·repair·독립 evidence audit 통과 — body-first 재설계 준비**.
**다음 실행:** **독립 감사를 통과한 current evidence layer에서 scene candidate를 다시 경쟁해 final select와 콘텐츠 각을 확정하고, 본편 구조를 먼저 설계한 뒤 Cold open을 경쟁시킨다.**

사용자의 실제 REVIEW_B 시청 결과를 근거로 Step 5를 공식 FAIL로 닫았다. 핵심 원인은 chronology만 대략 보존하고 narrative continuity를 보존하지 못한 것, 청해 증거를 작품의 핵심 사건·감정·payoff보다 우선한 것, listening과 reaction을 작품 감상 흐름 안에서 결합하지 못한 것, Cold open/body의 `사메노 마진/상어 마인` 및 `漢字読めないの？` 단순 반복, historical large-v3 결과에 과도하게 의존한 것이다. 레제의 최종 선택·죽음·덴지가 모른 채 기다리는 결말 인과가 끊긴 것은 planning_quality_failure의 핵심 evidence다.

기존 REVIEW_B를 고치거나 그 기반으로 REVIEW_C를 만들지 않는다. 2026-09-13의 34 candidates / 15 selects는 `materials/ep1_main/PLANNING_RESULTS.md`에 historical evidence로 보존하지만 authoritative select set이 아니다. A/B/C와 primary material, 내부 provenance 사실은 변경하지 않았다.

recovery 실행에서는 stream 2 desktop과 stream 3 mic 전체 `01:45:25`를 별도 재전사하고, source narrative / desktop dialogue·audio / user mic raw / visual·nonverbal reaction 네 layer를 복원했다. 25개 narrative beat map, 633행 synchronized timeline, 30개 새 scene candidate pool을 생성했다. current external evidence 위치는 `K:\kkamaknun\transcription\`이다. final select, body 구조, Cold open, REVIEW_C는 아직 확정·렌더하지 않았다.

repair 뒤 새 Codex 세션에서 primary MP4와 raw desktop/mic을 기준으로 reconstructed evidence를 read-only 독립 재감사했고 **`EVIDENCE_GATE_PASS`**를 확인했다. `予定/여정?` 사건 분리, N09/N10 narrative boundary, N25 captured ending, P29 reaction을 실제 source에서 재확인했으며, JSONL/CSV 633행 대응·TC 순서·25 narrative beats·30 scene candidates·stale regression scan에서 planning-critical blocker가 남지 않았다. post-credit의 파워 카페 장면은 current primary recording 범위 밖이고 사용자 reaction도 없는 구간이므로 이번 captured-material evidence의 blocker로 취급하지 않는다. 이 PASS는 **evidence source fidelity gate 통과**이며 final select·body 구조·Cold open·REVIEW_C의 품질 PASS나 최종 Step 5 PASS를 뜻하지 않는다.

현재 code와 current truth는 GitHub와 각 PC의 local Git repository에서 관리한다. 집과 회사의 canonical local working repository는 모두 `C:\kkamaknun`이며 branch·commit을 GitHub로 동기화한다. 이동식 SSD `K:`는 repository 실행 위치가 아니라 대용량 external material 운반용이며, current media·evidence·review artifact는 각각 `K:\kkamaknun\source`, `K:\kkamaknun\transcription`, `K:\kkamaknun\review`에 둔다. `K:\kkamaknun\repo`는 2026-09-13 이전 과정에서 만든 historical/transport copy이므로 canonical repository나 현재 실행 경로로 사용하지 않는다. external artifact는 local repository 안으로 복사하거나 Git에 add·commit하지 않는다.

`tools/harness/PIPELINE.yaml`의 material_first 공정은 외부 source narrative가 있으면 네 layer와 synchronized evidence timeline이 준비되기 전 후보 경쟁으로 넘어가지 않도록 통합 수정했다. 작품 서사는 골격, listening은 소재·발견, reaction은 재미·인물성으로 다룬다. chronology integrity와 narrative continuity를 분리하고, 본편을 먼저 설계한 뒤 Cold open을 경쟁시키며, MUST_KEEP 누락·climax/resolution/emotional closure 삭제·진단표 배열·Cold open 단순 중복을 pre-render hard gate에서 막는다.

`AGENTS.md`의 기획 라우팅은 실제 기획 요청을 `tools/harness/STATE.json` → 현재 `PIPELINE.yaml` → 현재 lock 순으로 연결한다. 현재 편은 `EP1`, lock은 `tools/harness/EP1_LOCK.json`, 입력 경로는 `material_first`다. `check_draft.py`는 이 lock을 `STATE.json`에서 선택하며 **current truth·잠금·자료 경계의 deterministic 오류만 검사**한다. PASS는 기획 품질 인증이 아니다.


## 과거 실행 기록 — current instruction 아님

아래 2026-09-04~2026-09-13의 가설·보정·REVIEW_B 이전 기록은 역사적 근거다. 현재 실행은 위 recovery 상태와 상세 owner를 따른다.

2026-09-04 추가 엑셀 확인: 이번에 사용자가 수정한 새 source는 **`해석표` 시트 하나**다. 기존 판정 열은 보존하고 `평가 대상 / 이해 결과 / 포착 방식 / 오류·병목 / 세부 근거`로 1차 정규화했다. 청해 대상으로 분류된 68행의 작업 집계는 `정확 15 / 요지 이해 34 / 부분 이해 13 / 오해 2 / 미이해 4`이며 **객관 점수가 아니라 기획용 분류**다. 행별 일본어 대조 원문은 사용할 수 있지만 영화 전체 자막 완전 확보로 일반화하지 않는다.


아래 Step 4-B~4-E 기록은 **본 촬영 전체 로깅 전 테스트 재료 기반 가설의 이력**이다. 현재 장면·핵심 역할·payoff·패키징 판정은 위 2026-09-13 결과와 상세 owner를 따른다.

Step 4-B 경쟁 영상 해부 완료. 가장 가까운 구조 참고는 Matt vs Japan의 `illiterate boy speaks perfect Japanese`로, **읽기 약점/듣기 강점의 모순을 제목과 첫 장면에서 먼저 증명**한다. 30일 일본어 challenge 계열에서는 `최종 실제 시험`, `중간 progress/실전 사건`, `결과 대기 갱신`이 반복적으로 보였다. 반대로 step/tips 중심 정보형은 현재 1화가 피해야 할 `진단·설명 목록` 구조의 대비 사례로 둔다. 상세 source와 적용 원리는 `FIRST_VIDEO.md`의 Step 4-B 절이 owner다.

Step 4-C 후보 경쟁 완료. 메인 각은 **`오래 취미로 본 애니가 남긴 비대칭 귀`**로 선택했다. 여기서 `20년`은 작품 수나 덕후성의 크기가 아니라 취미 시청 기간을 뜻한다. 사용자는 여러 작품을 폭넓게 많이 본 타입이 아니라 좋아하는 작품을 오래 보고 반복해서 보는 시청자에 가깝다.

Step 4-D 구조·payoff·패키징 완료. 본편은 `정확히 이해 → 소리만 포착 → 유사음 오매칭 → 귀/문자 비대칭 → 실제 작품 웃음·몰입`으로 발견 기능을 바꾸며 진행한다. payoff는 점수가 아니라 `오랜 취미 시청이 남긴 비대칭적인 청해 형태`다. 현재 패키징은 하나를 미리 버리지 않고 2개 후보를 Step 4-E로 넘긴다. A는 `일본어 제대로 안 배우고 20년 넘게 애니 본 사람, 자막을 꺼봤습니다` / `뜻은 아는데 일본어는 모름?`, B는 `일본어 안 배웠는데 청해는 중급? 20년 넘게 애니 본 결과` / `청해는 중급?` 계열이다. `중급`은 확정 결론이 아니라 질문형 훅으로만 사용한다. `뜻은 아는데 일본어는 모르는 귀`는 가장 강한 중간 발견으로 흡수하고, 수영장 웃음·관계 반응·전투 몰입·성우 발화를 재미로 자발적으로 따라 하는 행동은 사용자 캐릭터를 살리는 실제 사건으로 사용한다. `성우를 따라 해서 청해가 늘었다`는 인과관계는 주장하지 않는다. 상세 후보/탈락 이유는 `FIRST_VIDEO.md` Step 4-C가 owner다.

Step 4-E는 사용자 사전 검수에서 **타임라인 무결성 결함**이 발견돼 한 번 재개방 후 보정했다.

추가로 사용자 사전 검수에서 **Cold open 선정 기준 오류**가 발견돼 Step 4-E를 다시 재개방했다.

사용자 지적에 따라 원인을 EP1 한 편의 Cold open 문제로만 보지 않는다. **윤성원 PD 강의를 EP1 참고자료로만 사용한 것이 공정 결함**이었다. 이미 전사 기반으로 채택된 `A/B→C / 보는 사람 / 콘텐츠 각·핵심 장면 / 실제 푸티지 재기획 / 시청각 판단 / 예상 댓글·공유 문구 / 바이럴 재가공 단위 / 시청자 모드 편집 검수`를 공통 `PIPELINE.yaml`과 `PLAYBOOK.md`의 해당 단계에 통합한다. 새 강의 전사도 반복 적용 가치가 있으면 개별 영상 패치가 아니라 기존 공정 단계에 매핑한다. `결과/발견을 많이 공개하면 안 된다`는 식의 잘못된 제한을 사용했고, 설명이 있어야 의미가 생기는 `지누키?`를 Cold open 핵심으로 올린 것은 planning-quality failure로 기록한다. 수정 원칙은 `결과/payoff 일부 공개 허용 / 제목·썸네일 promise 즉시 확인 / 독립 장면 강도 / 공개 뒤 남는 미해결 질문 / 사실 경계`다. 패키지 A와 B는 promise가 다르므로 Cold open도 별도로 경쟁시킨다. 최종 원칙은 `Cold open만 순서 예외 / 본편은 1차 시청 실제 시간 순서 유지 / 구간 생략은 가능하지만 남긴 사건 순서 뒤집기 금지 / 2·3차 촬영 여부는 내부 provenance에 보존하되 viewer-facing 표시는 강제하지 않음 / 최초가 아닌 장면을 최초라고 명시적으로 주장하지 않음`이다. `정확 이해 → 소리만 포착 → 오매칭 → 문자 비대칭`은 편집 챕터가 아니라 시간순 사건을 해석하는 기능 태그로만 사용한다. 패키지 A는 제작 기본안, 패키지 B는 `중급권`에 대한 제한적 직접 답을 포함할 때만 사용하는 유지 후보다. 보정 후 deterministic validator를 다시 실행해 **PASS**를 확인했다. 이 과거 검수 뒤 현재 Step 5는 아래의 review rough cut 시청 테스트 구조로 교체됐다.

Step 5는 문서만 보고 사용자가 전문 기획 판정을 하지 않는다. AI/harness가 구조표와 실제 장면 근거로 전문 판정한 뒤 selected footage로 review rough cut을 만들고, 사용자는 실제 영상을 일반 시청자로 보며 체감 관측을 남긴다. AI가 그 관측을 구조 문제로 해석하고 PASS/FAIL 권고를 정리하며, 최종 제작 진행 여부는 사용자가 확정한다. 세부 계약 owner는 `tools/harness/PIPELINE.yaml`이다.

보정된 공정 재실행 결과:
- 기존 `비대칭 귀`는 콘텐츠 각이 아니라 **최종 해석/payoff**로 재배치했다.
- 새 viewer-facing 콘텐츠 각은 **`일본어 글은 아직 잘 못 읽는데 ‘漢字読めないの？’는 알아듣고 ‘나랑 똑같네’라고 반응하는 사람`**이다.
- 핵심 장면은 약 32분대 `漢字読めないの？ → 나랑 똑같네 / 한자 못읽는다`로 선택했다.
- **한자 장면은 실제 증거로 유지하되**, viewer-facing 요약은 `한자`보다 넓은 **일본어 읽기 전반의 약점**으로 표현한다. `전혀 못 읽음`은 과장이므로 `글은 잘 못 읽음/읽기는 약함`으로 제한한다.
- `次が最後 → 다음이 최고`는 독립 공유성이 강해 **공유 단위/Cold open 보조 후보**로 재배치했다.
- `지누키?`는 본편의 소리-의미 분리 증거로 유지하고 Cold open 핵심에서는 제외한다.
- 패키지 A는 `일본어 제대로 안 배우고 20년 넘게 애니 본 사람, 자막을 꺼봤습니다` / `글은 잘 못 읽는데 들림?`으로 갱신한다.
- 본편은 Cold open을 제외하고 1차 시청 실제 타임라인을 유지한다.

Step 4는 양이 크므로 실행 배치만 나눈다(새 공정 추가가 아님): **4-A 재료 복원 → 4-B 경쟁 영상 조사·해부 → 4-C 콘텐츠 각 후보 생성·경쟁 → 4-D 본편 구조·payoff·패키징 → 4-E deterministic 검증 + RED TEAM + 최종 제출**.

4-A에서 복원한 1화 기준:
- A/B/C는 `FIRST_VIDEO.md` 현재 확정을 유지한다.
- 1차 촬영물은 약 82분 25초이며, `materials/ep1_take1/후보표.md`의 사용자 판정에서 **사건 7개 / 사건 아님 2개**가 확정돼 있다.
- 확정 사건은 카타카나 읽기, 마키마 영화 데이트 반응, 수영장 장면의 가장 큰 웃음, 레제의 민간 데빌헌터 역습 장면, 다른 좋아하는 사람 질문 반응, 빔 구출 장면의 어처구니없는 웃음, 덴지·레제 악마화 대치 이후 몰입 구간이다.
- 1차 촬영은 **정밀 객관 점수용 최종 진단이 아니라 1차 관찰 자료**다. 체감 약 70%는 사용자 주관값이며 임의의 `애니 청해 XX점`을 만들지 않는다.
- 현재 질적 관찰은 **내용은 따라가도 실제 일본어 표현의 정확한 형태를 잡지 못하는 경우가 많고, 귀로 아는 소리·의미와 문자·한자 표기 사이 격차가 있다**는 것이다.


## 1화 전 청해 베이스라인

1화 전 사전 검증에서 **처음 접한 명료한 일본어 1인 팟캐스트의 실제 검증 구간은 세부 의미 재구성 약 80%대**로 확인됐다.
담화의 흐름과 핵심 의미 이해는 강했고, 정확한 시간 표현·어휘 의미·일부 의미 방향에서는 실제 오류가 있었다.
이 결과는 해당 팟캐스트의 검증된 구간에 한정하며, 전체 일본어·애니·JLPT 수준으로 일반화하지 않는다.

따라서 현재 전제는 `청해가 읽기·쓰기·문법·한자보다 상대적으로 강하다` 수준을 넘어서 **특정 명료한 1인 발화에서는 실제로 높은 이해가 확인됐지만, 애니 조건의 정밀한 객관 점수는 아직 확정하지 않는다**이다.

상세 검증 조건·점수·해석 제한은 `FIRST_VIDEO.md`가 owner다.

## 현재 첫 콘텐츠 실제 소스

2026-09-07 사용자 확인 결과로 본 촬영 primary material을 확정했다. 정확한 원본 경로·스트림 명세·검사 근거와 편집 준비 workflow는 `FIRST_VIDEO.md`의 `1화 본 촬영 — 단일 MP4·오디오 3스트림 확정` 및 다음 절이 owner다.

- 단일 MP4의 영상 1스트림과 역할이 확인된 오디오 3스트림을 사용한다. 기존 여러 영상 동기화·별도 master 생성은 현재 선행 작업이 아니다.
- 과거 드라이브의 손상본 조사와 파일 이동 대기는 현재 본 촬영의 상태를 나타내지 않는다.
- 기존 약 82분 테스트 촬영은 보조·비교 자료다. 테스트 촬영 기반 러프 구조표는 current 입력으로 쓰지 않고, 2026-09-13 본 촬영 장면·타임코드와 AI 전문 판정을 반영한 REVIEW_B를 Step 5 시청 테스트에 사용한다.
- 2026-09-13 원본을 직접 읽어 스트림·러닝타임을 재확인하고 전체 material-first 분석을 완료했다.

## 1차 애니 진단·2차 진단 방향

1차 레제편 촬영은 정밀 진단이 아니라 1차 관찰 단계로 종결했고, 2차 진단은 멀티트랙 분리 녹화로 진행한다. 판정 내용과 확인 항목은 `FIRST_VIDEO.md`가 owner다.

## 사용자 실사용 검수(UAT) — 구조 문제 발견, 개발 재개

실제 사용자가 직접 사용해 본 결과, 자동시험으로는 드러나지 않던 **작업 흐름 자체의 설계 문제**가 확인됐다.

발견된 핵심 문제:
- AI 후보 생성과 **선택하지 않은 후보 전부**의 Nadeshiko 검색이 한 번에 묶여 있고, 검색 결과가 있는 표현만 보인다.
- 검색 응답·장면 원본·URL·캐시가 DB에 영구 저장되고, 시작 시 지난 검색이 자동 복원된다.
- 장면 수만큼 영상 플레이어가 동시에 생성·로딩된다.
- 실제 작업 결과(판정·번역·메모)가 검색 저장 구조에 종속돼 있다.

이에 따라 **재작업 계획을 승인하고 개발을 재개**했다. 승인된 계약의 핵심:
- 한국어 의미 → **저장 표현이 있으면 AI 미호출**, 없으면 AI가 자연스러운 표현을 폭넓게(최대 20, 억지로 채우지 않음) 생성해 **표현 자산으로 저장**(meanings ↔ meaning_expressions(의미별 뜻/말투) ↔ expressions). [표현 더 찾기]는 기존 표현을 전달해 중복 없는 추가분만 저장.
- **사용자가 선택한 의미→표현 관계 1개만** Nadeshiko(활성 작품)+로컬 자막 검색. 검색 결과·문맥 응답은 캐시/저장하지 않는다(세션 한정).
- 로컬 자막 결과는 이번 범위에서 **참고 검색 결과**(존재 확인)로만 표시 — 영상 로딩·판정·저장·내보내기 대상 아님.
- 장면 목록은 텍스트로, **영상 플레이어는 1개**만 두고 선택한 장면만 로딩.
- 문맥/번역은 장면 단위 명시 요청 시에만 실행하고 **번역 결과만 작업물로 저장**.
- **실제 작업한 장면만** `work_scenes`(관계 기준, URL 미저장)에 저장. 내보내기는 기존 MP4 재사용, 없으면 `get_segment`로 현재 URL 재조회.
- DB는 v4로 마이그레이션: 실 SSD DB **사본 리허설 통과 후에만** 실 DB 실행, 구조 변경 전 자동 백업 유지, 선호 작품·로컬 자막·기존 표현·의미 연결·판정·번역·메모 보존, 캐시·검색 이력 폐기.
- 설정 `candidate_count`는 의미가 달라졌으므로 값을 승계하지 않고 `expression_generation_limit`(기본 20)으로 대체한다.

**완료 조건은 자동시험이 아니라 사용자 직접 실사용 검수 통과다.** 현재는 미완료 보존 상태이며, 다시 요청하면 `SCENE_COLLECTOR_PLAN.md` 25절의 승인된 재작업 계약에서 이어간다.

## 윤성원 PD 강의자료·2화 아이디어 작업 상태

- 2026-09-04 추가 전사: 9-1 `0에서 100만까지 바이럴 되는 과정` 확인 완료.
- 9-1에서 새로 반영할 핵심은 `최초 노출`보다 현재 1화 기획에 직접적인 **바이럴 재가공 단위**다. 커뮤니티·SNS에서 영상 전체가 아니라 특정 표정·대사·캡처 몇 장이 독립 콘텐츠처럼 퍼질 수 있으므로, `커뮤니티 제목 / 예상 댓글 / 캡처·짤 독립성`을 콘텐츠 각·패키징 점검에 추가한다.
- 이 기준은 Cold open과 분리한다. 가장 공유하기 좋은 장면이 반드시 가장 좋은 Cold open은 아니다.


- 사용자 제공 윤성원 PD **강의자료 전체 정독을 완료**했다. 이 자료는 강의 전사가 아니므로 실제 강의 발언을 확정하는 근거로 사용하지 않는다.
- 강의자료의 슬라이드·기획안·사례·제작 참고 내용은 `references/YOON_SUNGWON_LECTURE_MATERIALS.md`에 **보조 reference**로 분리했다.
- 윤성원 PD의 실제 방법론 판단은 계속 **강의 전사를 1차 근거**로 한다. 사용자가 한 편씩 전사를 진행하면 해당 강의자료와 대조해 `references/YOON_SUNGWON_CONTENT_ESSENCE.md`를 갱신한다.
- 현재 2화 방법론 탐색에서는 **전사가 확인된 5-2를 중심 근거로 사용하고 강의자료는 사례적 참고로만 사용**해 방법론 아이디어 **34개**를 생성했다.
- 34개 후보는 확정 기획이 아니며 `IDEATION.md`에 작업 중 아이디어 뱅크로 보존했다.
- 이 작업에서 남은 것은 아이디어 재생성이 아니라 **34개 후보의 1차 선별**이다(보존, 현재 작업 아님). 선별 후 살아남은 후보만 C·예상 댓글·공유 문구 검증으로 넘긴다.
- `PLAYBOOK.md`는 이번 강의자료 정독만을 근거로 수정하지 않았다.

## System Evaluation 측정 상태

Phase 0~1 measurement contract와 deterministic oracle proof, Docker-free Phase 2 feasibility pilot, 그리고 executable Core Regression Phase 3 release measurement를 완료했다. 독립 contract owner는 `evals/system/README.md`이며 영상 기획 `PIPELINE.yaml`의 Planning RED TEAM과 분리한다.

- Phase 3 authoritative status: `PHASE3_PASSED`.
- Evaluation snapshot: `476bc226433efc95c0b546948c2c7160ff97616c`.
- Requested release lane: `gpt-5.6-sol / medium`; effective model/reasoning observations are `UNKNOWN / UNKNOWN`.
- Valid release result: `112/112` — `PASS 112 / FAIL 0 / UNKNOWN 0`, remaining valid trials `0`; 20 critical tasks are all `PASS`.
- Excluded non-valid attempts: `INFRA_ERROR 1 / INVALID_FIXTURE 0`; represented actual target attempts are `113`. The preserved infrastructure attempt is `CORE_A_01_baseline_1_8be1291f`; `CORE_A_01_baseline_1_855a5e53` is replacement #1 and the fifth valid PASS for `CORE_A_01`.
- Historical continuation remains authenticated: 64 historical seed trials, 30 excluded historical valid trials, and recovered source archive SHA-256 `38d12583294a12829874602c703d90bd78a0616ef57fb97d14c2ec4fbab28858`.
- Authoritative publication: `evals/system/core_result.json`, `evals/system/core_findings.json`, and self-contained portable reviewer evidence `evals/system/core_evidence.zip` (SHA-256 `769d83acfb39d5a78b1b22492929e416e323a62d860f0faf3e18cc2340519b2c`). The reviewer package was independently approved twice as `APPROVE_NEXT_STEP`.
- The PASS scope is the implemented controlled Codex surrogate Core Regression suite only. It is not Actual ChatGPT Work acceptance, video-planning quality certification, full reliability/security proof, or Phase 4/5 completion. Actual ChatGPT Work UAT remains separate.
- Historical failed/blocked baselines, targeted regressions, surrogate-contract correction, permission investigation, and export remediation remain preserved in their durable result/evidence/history records; they are not the current Phase 3 state.
- Phase 4 Actual Work UAT의 보존 evidence를 corrected deterministic classifier로 offline 재분류했다. 결과는 `P4-A UNKNOWN / P4-B PASS / P4-C1 PASS / P4-C2 PASS / P4-D PASS`, corrected aggregate는 `PHASE4_PILOT_BLOCKED` (`4/5 PASS`)다. P4-A는 queued expiry로 final response가 없어 current contract상 `VALID_UNKNOWN / INFRA_OR_UNOBSERVABLE`을 유지한다. Actual Work를 재실행하거나 evidence를 보충하지 않았다.
- 과거 보존 aggregate `PHASE4_PILOT_FAILED`와 `P4-C2/D FAIL`은 Markdown·한국어 관계 문법, `Phase 4:` status 표현, 문장 간 historical provenance, contract/classifier correction과 pilot completion의 구분을 놓친 measurement/classifier defect의 historical 결과다. confirmed Actual Work semantic product failure 또는 evidence/capture defect로 해석하지 않는다. classifier는 immutable repository snapshot truth와 이후 external pilot measurement state를 별도 clock으로 취급하며, snapshot의 `PHASE4_PILOT_NOT_RUN / Work call 0회`를 실행 중 의미론적 실패로 소급하지 않는다.
- Phase 4 initial Actual Work pilot 종료 판단: 사용자가 P4-A의 보존 `UNKNOWN`을 수용하고 replacement 없이 pilot을 종료하기로 승인했다. corrected aggregate는 `PHASE4_PILOT_BLOCKED` (`4/5 PASS`)로 보존하며, confirmed Actual Work semantic product failure는 없다. Phase 5는 `NOT_STARTED`다. System Evaluation 추가 실행 없이 video-planning의 기존 다음 행동으로 복귀한다.

## 운영 원칙

현재 상태 질문은 이 파일을 기준으로 답한다. 다음 할 일은 위 POC 절 한 곳에만 적는다.
장면 수집기 실제 구현을 시작할 때는 `SCENE_COLLECTOR_PLAN.md`를 실행 계획으로 읽는다.

