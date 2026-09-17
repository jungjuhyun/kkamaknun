# EP1 본 촬영 material-first 결과

기준일: 2026-09-17 KST. 분석 source snapshot: `027ee9d7fa4784483ccc300bb8a7065ee455b24c`.
이 문서는 EP1 planning evidence·provenance·검증 범위의 상세 owner다. A/B/C·packaging·확정 selection/compression contract는 `FIRST_VIDEO.md`, 사람이 읽는 다음 행동은 `STATE.md`, runtime/registry는 `tools/harness/STATE.json`이 소유한다.

## Current checkpoint — contract READY, full rescan BLOCKED

`ep1.primary_recording` 전체 `00:00:00–01:45:25.063`의 desktop/mic ASR 및 source frame 탐색을 완료했다. 새 candidate universe는 빈 목록에서 생성됐고, old 34/15·reconstruction 30·REVIEW_C 17 scenes/Cold open은 seed가 아니다. REVIEW_C를 축소하는 실행이 아니다.

| 항목 | 보존한 실제 결과 / 한계 |
|---|---|
| Contract | CONTRACT_READY; 확정 원 응답과 기존 research를 cloud bundle에 보존, operative 규칙은 FIRST_VIDEO |
| Coverage | 81개 연속 범위, ledger상 TC hole 없음; TEXT+COARSE_VISUAL이며 full continuous AV coverage 아님 |
| Visual evidence | 20초 간격 317개 + detail 관측 55개, 중복 제외 366개 frame; 36 contact sheets와 11 time manifests |
| 새 후보 | 65개 = KEEP 0 + COMPETE 42 + 잠정 탈락 23 |
| DROP 집계 | 초기 non-event 등 DROP 16개 + 후보 탈락 23개 = DROP 기록 39개; 인접 합산 21 ranges |
| 후보 경쟁 | 구조·context·중복 기반 2차 경쟁은 기록됨; direct AV receipt 38/42은 대조됐으나 complete 42개 set이 아니므로 actual AV가 좌우하는 우열은 미확정 |
| Body | 39개 후보 / 17개 기능 묶음; 대체 후보 F003/F007/F017 3개 별도; NOT LOCKED |
| Runtime | 63개 raw source search windows 합계 862초(14:22). 제안 context/bridge 포함. final retained runtime 아님 |
| 미확정 | verified retained duration, 추가 context/호흡 보정, Cold open, finished total runtime 모두 미정 |
| Narrative | 필수 후반 chain의 담당 후보는 존재. 압축 후 viewer가 인과·감정을 이해하는지는 AV 미검증 |
| 제작 gate | direct AV receipt 검증 38/42, body lock false, Cold open 경쟁 NOT STARTED, rough cut 금지, AI 최종 PASS false |

**Modality blocker:** 회사 PC의 해당 Astra/Codex 세션에서 audio probe가 `audio content omitted because you do not support audio input`로 반환됐다. 직접 듣기와 연속 AV perception을 완료하지 못했으며 ASR/정지 frame을 그 대체로 인증하지 않았다. 이 관측을 모든 미래 기기·모델의 고정 능력 제한으로 확대하지 않는다. 새 기기에서도 먼저 실제 입력 perception 경로를 확인해야 한다.

## 2026-09-17 direct-AV 재개 receipt — partial, not a selection result

Web-first receipt: 현재 Google Gemini API 공식 video-understanding 문서는 `gemini-3.8-flash`의 video input을 지원하며, static mode가 frame과 audio를 함께 처리하고 agentic mode가 frame/audio/transcript를 요청에 따라 탐색한다고 명시한다. 이 작업은 short candidate clip의 reaction timing과 context boundary를 확인하는 용도이므로, completion 때는 actual `video/mp4` Files API input을 사용하고 static clip/subclip route를 기본으로 한다. transcript·still-only surrogate는 금지한다.

Current material-store contract로 `ep1.full_rescan_checkpoint`와 `ep1.primary_recording`의 registry SHA-256을 다시 검증했다. checkpoint ZIP을 disposable cache에 추출하고 `INDEX.md`를 처음부터 읽었다. primary는 5,065,619,726 bytes / SHA-256 `7847fbeebd3db7dd94141f332fd80fa11e0620ed23b58789898b6485cfefd525` / 6325.0625초, video 0·mixed 1·desktop 2·mic 3을 확인했다. K SSD는 사용하지 않았다.

Approved work path에 prior Gemini `gemini-3.8-flash` direct-MP4 records가 남아 있었다. F003/F005/F007/F010/F014/F015/F020/F023/F025/F027/F031/F032/F033/F034/F035/F036/F038/F041/F042/F043/F045/F047/F048/F049/F050/F052/F053/F054/F055/F056/F057/F058/F059/F060/F061/F062/F063/F065, 총 38개는 clip SHA-256, video+audio stream, full ffmpeg decode, non-empty Gemini raw response를 이번에 다시 대조했다. F036은 source image transition·desktop source sound·user voice와 시점 관계를 함께 기술해 direct AV route가 실제로 두 modality를 사용한 evidence다.

그러나 F002/F017/F037/F064는 source-derived MP4와 Gemini Files object ID만 남고 raw model response가 없다. 이 네 개는 current per-candidate AV record가 아니며, 특히 F017 alternate와 F002/F037/F064의 selection을 확정할 수 없다. 현재 process/user/machine에는 `GEMINI_API_KEY`, `GOOGLE_API_KEY`, `GOOGLE_GENAI_API_KEY`, gcloud auth 및 실행 가능한 기존 venv가 없어, 새로운 10–20초 capability probe와 네 response의 재실행을 수행하지 못했다. credential 값은 읽거나 기록하지 않았다.

따라서 local `AV42_RECOMPETITION`, body lock, Cold open lock, rough-cut artifacts는 incomplete evidence 위에서 생성된 machine-local 작업물일 뿐 current truth가 아니다. 32/4/6 판정·537.3초·Cold open 12.3초를 채택하지 않는다. 이번 실행에서도 rough cut을 생성하지 않았다.

재개 hard gate는 다음과 같다.

1. available credential path에서 10–20초 mixed-audio MP4를 새로 Files API video input으로 upload하고 upload file identity/state, raw response, video/audio stream, full decode 및 deterministic visible/audio event 대조를 receipt로 남긴다.
2. F002/F017/F037/F064를 동일한 direct-video route로 실행해 source range, clip hash, visual/audio events, reaction timing, context/boundary, uncertainty, retain/drop/alternate recommendation을 모두 보완한다.
3. 42개 complete per-candidate record를 material-store durable checkpoint로 보존한 뒤에만 42개 재경쟁, retained boundaries, runtime, body lock과 Cold open competition을 재개한다.

그 전에는 `FULL_RESCAN_BLOCKED`를 유지한다.

DROP도 표본 사이 강한 비언어 사건이 없다는 인증이 아니다. artifact의 '실제 사건/반응' 서술 중 ASR 기반 항목과 표본 관측을 구분하며, 청해 정확성·웃음·말투·침묵·몰입·comic timing·내부 jump cut 자연스러움은 미검증이다.

## Durable evidence와 복원 순서

Logical ID: **`ep1.full_rescan_checkpoint`**. object key: `planning/ep1/rescan/20260916/EP1_RESCAN_CHECKPOINT.zip`. registry의 size/SHA-256으로 archive 전체를 검증한다. 기존 material registry에 file artifact 하나를 추가한 이유는 candidate 표·전사 탐색 view·contact sheet가 외부 evidence이기 때문이다. Git에는 상세 media/transcript/frame을 넣지 않고 기존 owner와 registry만 유지한다. 별도 permanent owner/manifest는 만들지 않는다.

Checkpoint persistence 검증(2026-09-16): 기존 material helper로 cloud에 publish한 뒤 빈 로컬 위치에 다시 materialize해 registry size/SHA-256 일치를 확인했다. 77개 archive member의 ZIP 무결성, 36개 contact sheet decode, 상대경로 링크와 logical ID resolution, 원 후보/coverage/body/runtime JSON의 의미 동일성, 81개 연속 범위와 63개 window의 862초 합계를 재검산했다. 이는 저장·복원 검증이며 새 selection/AV 검증이 아니다. JSON/YAML/Python parse, material helper 12개 test와 deterministic validator regression 15개 및 확정 계약 검사를 통과했다. A/B/C·packaging·primary truth·공통 pipeline·EP1 lock은 변경하지 않았다.

Bundle의 `INDEX.md`가 entry point다. 다음 파일을 직접 이어 사용한다.

| 파일 | 권한과 용도 |
|---|---|
| SELECTION_COMPRESSION_CONTRACT.md, REVIEW_RESEARCH_REPORT.md | 확정 계약 원 응답과 사용했던 research; 계약 응답 말미의 no-rescan/no-commit은 당시 receipt |
| FULL_RESCAN_CANDIDATES.md/.json, candidates.json | 최종 7-field record 81행; JSON 두 사본은 같은 데이터 |
| coverage.json, DROP_RANGES.json | 전체 TC/판정 범위와 합산 DROP |
| FUNCTION_COMPETITION.md | 65개 후보 기능 경쟁과 AV 미확정 비교 |
| PROVISIONAL_BODY.md, BODY_AFTER_RED_TEAM.json | chronology 가안과 AV search windows; edit lock 아님 |
| NARRATIVE_COVERAGE_CHECK.md | 인과 담당 후보와 미검증 context |
| RUNTIME_LEDGER.md/.csv/.json | 862초 window 산술 합계; 검증 runtime 필드는 null |
| COLD_OPEN_CANDIDATES.md | body gate 미충족으로 미시작 기록 |
| RED_TEAM_CHANGES.md | 실제 반영했던 제외·축소·경계 보정 |
| FIRST_PASS_RECORDS.json, SCAN_NOTES_*, BODY_WORKING_HYPOTHESIS.json | 초기 탐색/경쟁 전 이력. 최종 후보와 BODY_AFTER_RED_TEAM보다 우선하지 않음 |
| transcript_*, coverage_*/detail_* sheets/manifests | 탐색에 사용한 ASR view와 검토한 정지 frame evidence |
| VALIDATION.json, SNAPSHOT_MATERIAL_VERIFICATION.json | 원 rescan의 검증 receipt; repo mutation/commit=false는 당시 run에 한정. checkpoint 보존 hash/제외 항목도 기록 |

집 PC에서는 fetch한 branch의 owner를 먼저 읽고 machine-local `KKAMAKNUN_MATERIAL_ROOT`, `KKAMAKNUN_MATERIAL_REMOTE` 및 필요 시 `KKAMAKNUN_RCLONE`을 기존 authenticated store에 맞게 설정한다. credential/config는 Git 밖에 둔다. repo root에서:

```text
python tools/harness/material_store.py materialize ep1.full_rescan_checkpoint
python tools/harness/material_store.py verify ep1.full_rescan_checkpoint
python tools/harness/material_store.py path ep1.full_rescan_checkpoint
```

반환된 ZIP을 같은 local cache의 작업 directory에 풀고 INDEX를 읽는다. 회사 PC 경로를 재현하지 않는다. primary는 `ep1.primary_recording`으로 resolve하고 기존 cache가 있으면 helper verify 후 재사용한다. 없으면 cloud에서 materialize한다. 크기 5,065,619,726 bytes / SHA-256 `7847fbeebd3db7dd94141f332fd80fa11e0620ed23b58789898b6485cfefd525` / duration 6325.0625초 / video 0·desktop 2·mic 3을 확인한다. K SSD는 필요 없다. 이번 persistence 작업은 primary를 새 다운로드하거나 AV 분석하지 않는다.

## AV completion — 다음 실행의 정확한 입력과 gate

1. 실제 audio + continuous AV perception이 되는 경로를 확인한다. 안 되면 `FULL_RESCAN_BLOCKED` 유지. 재생 성공이나 전사/프레임 열람만으로 gate를 통과시키지 않는다.
2. PROVISIONAL_BODY의 39개 후보 search windows를 raw context와 함께 직접 대조하고, F003/F007/F017 대체 후보를 경쟁시킨다. 65개 전체 기록과 DROP 이유를 보존해 필요 시 재개방한다. 기존 30개 pool/REVIEW_C로 universe를 교체하지 않는다.
3. 실제 사건·발화·reaction timing을 검증해 후보를 재경쟁하고 retained boundaries를 정한다. 가안 source window 자체를 보호하지 않는다. subtitle/나레이션을 가정해 context 공백을 덮지 않는다.
4. 필수 narrative 인과와 source chronology, listening/reaction/context 비용을 재확인하고 전체 retained runtime을 산출한다. 완성본 ≤15:00에는 Cold open·bridge·엔딩을 포함한다. 14:22를 이미 통과한 runtime으로 사용하지 않는다.
5. body를 lock한 뒤에만 Cold open 경쟁. 새 rough cut은 AV·selection·internal compression 및 pre-render gate를 완료한 뒤다.

특히 보존해야 할 이번 관찰/수정: F003의 인접 '괜찮'을 血抜き 오답으로 단정하지 않음; F007 source 질문 포함; F020 앞의 읽기 희망→사용자 반응을 뒤의 한자 질문 원인으로 바꾸지 않음; F023 학교 결핍 앞 경계 복원; F036 '걸렸' timing 미확정; F037 피/심장 수정·F056 비유·F060 미이해 청취 필요. B10의 별개 재기를 잇기 위해 F047 패배 창을 복원한 결과 856→862초가 됐다. 이는 새 보정 제안이 아니라 이미 반영된 RED TEAM 기록이다.

기존 `ep1.narrative_map`의 N06(27:45–31:15) 요약은 이번 29분대 source frame과 충돌했다. 새 F018 관찰은 천사악마/부상자 장면이며 map으로 미관측 사건을 추론하지 않는다. hash/parse PASS가 의미 정확성을 인증하지 않는다. 원본 카페 대기 frame 01:44:09/12는 뒤 01:44:15의 죽어가는 레제 frame보다 앞이다. 후반 인과 기능 설명을 핑계로 화면 순서를 바꾸지 않는다.

## Historical/failure evidence boundary

이하 과거 AV/A/V·audit PASS·Step 9 PASS는 각 당시 실행의 주장/receipt다. 이번 65개 후보의 직접 AV 검증으로 전이하지 않는다. REVIEW_B 및 44:43 REVIEW_C는 실패를 배우는 자료이며 새 선택의 base가 아니다. 당시 자세한 표·planned boundary는 재현용으로 보존하되 current 결과는 위 checkpoint와 별개다. A/B/C와 packaging 의미는 FIRST_VIDEO의 current 절을 따른다.

## Historical reconstruction — 당시 분석 방법

- 원본을 이동·개명·수정·재인코딩하지 않고 읽기 전용으로 검사했다.
- 직접 확인한 컨테이너 값은 영상 `2560×1440 / 48fps / H.264`, 오디오 stream 1 mixed·2 desktop·3 mic, `start_time 0`, 전체 `6325.0625초`다.
- 과거 run에서는 mic 전체 604개 초벌 발화 구간과 핵심 구간 large-v3 대조를 사용했다. 이 결과는 현재 authoritative transcript가 아니라 historical/reference다.
- recovery run은 stream 2 desktop과 stream 3 mic를 각각 전체 `01:45:25` 재전사했다. primary는 `Qwen/Qwen3-ASR-1.7B` + `Qwen/Qwen3-ForcedAligner-0.6B`, secondary는 핵심·불확실 구간의 `faster-whisper large-v3` 독립 대조다. 모든 raw ASR은 해석과 분리하고 uncertainty를 보존한다.
- 90초 간격 71개 전체 시간축 프레임과 핵심 구간 1초 간격 얼굴 프레임을 확인했다. 후보의 힘은 전사만으로 정하지 않고 표정·몸 움직임·침묵·작품 화면과의 결합을 함께 봤다.
- 전사는 탐색·대조 보조다. 아래 일본어 원문은 desktop 분리 트랙 재전사로 확인된 핵심 구간만 확정형으로 쓰며, 영화 전체 자막 확보를 뜻하지 않는다.
- 이 파일은 사용자가 음성 마커를 넣은 3번째 촬영 계획과 일치하는 형태다. 앞부분은 기존 82분 테스트 촬영에서 이미 본 동일 사건이 확인되므로 내부 로그에서 `재확인/재시청`으로 기록한다. 후반 최초 반응은 owner에 적힌 보존 방침과 기존 take1 범위 밖이라는 근거가 함께 있는 구간만 내부 분석에서 `최초 반응 후보`로 분류한다. 파일 안에 경계 선언이 없으므로 확신이 부족한 곳은 최초라고 단정하지 않는다. 이 provenance는 viewer-facing 영상 표시 의무가 아니다.
- `AV`는 분리 오디오 대조와 연속 얼굴/전체 화면 확인, `A`는 분리 오디오 대조, `V`는 연속 얼굴/전체 화면 확인을 뜻한다.
- Cold open을 제외한 본편은 1차 시청의 실제 시간 순서를 기본적으로 보존한다.

## Historical reconstruction — 당시 A/B/C 해석

- A: 20년 이상 취미로 애니를 봐왔지만 일본어를 제대로 공부해본 적은 없는 사람
- B: `체인소 맨: 레제편`을 한국어 자막 없이 보고, 자기 귀에 실제로 무엇이 남아 있는지 확인한다.
- 핵심 C: 20년 동안 좋아한 시간이 사람한테 이렇게 남을 수도 있구나. 신기하다.
- 파생 C: `나도 애니 오래 봤는데 혹시 나도 비슷한 상태인가?` / `애니만 오래 본 사람의 귀가 이렇다면 제대로 공부하면 어떻게 될까?`

실제 본 촬영은 A/B/C를 바꿀 근거를 만들지는 않았다. 다만 `읽기 약점 ↔ 듣기 강점` 한 장면보다, **정확 이해·핵심어 오해·소리 자가수정·서사 몰입이 한 사람 안에서 교차하는 누적**이 C를 더 잘 만든다.

## Historical REVIEW_B 공식 판정과 recovery evidence

REVIEW_B 공식 판정: **planning_quality_failure**

사용자의 실제 시청 관측을 AI가 구조 원인으로 해석한 결과는 다음과 같다.

1. **narrative continuity 실패:** 남긴 컷의 chronology는 대략 유지했지만 상황·관계·질문·감정·인과가 컷 사이에서 사라졌다.
2. **작품 핵심 사건 coverage 실패:** 레제의 선택, 죽음, 덴지가 모른 채 기다리는 결말까지 이어지는 후반 payoff가 보존되지 않았다.
3. **listening evidence 과최적화:** `청해 증거로 좋은 장면`이 source narrative의 MUST_KEEP보다 먼저 경쟁했다.
4. **listening/reaction 분리:** 청해 사례와 반응이 작품의 setup→사건→결과 안에서 결합되지 않고 독립 진단 사례처럼 배열됐다.
5. **Cold open/body 구조 중복:** `사메노 마진/상어 마인`, `漢字読めないの？` 비트가 본편에서 새 맥락·새 정보·새 감정 없이 다시 나왔다.
6. **transcription evidence 품질 부족:** 핵심 구간 판단이 historical large-v3와 제한적 대조에 과도하게 의존했고, source narrative 전체 복원이 없었다.

따라서 REVIEW_B를 고치거나 그 select를 이어 REVIEW_C를 만들지 않는다. 기존 34 candidates / 15 selects / REVIEW_A·B 구성은 아래 **historical evidence**로 보존하지만 새 구조의 authoritative select set이 아니다.

### Recovery source layers

- Layer A — source narrative: `ep1.narrative_map`
- Layer B — desktop dialogue/audio: `ep1.desktop_transcript`
- Layer C — user mic raw: `ep1.mic_transcript`
- Layer D — visual/nonverbal reaction: 전체 1분 frame map과 과거 AV 로그를 대조하고, transcript만으로 reaction을 확정하지 않았다.
- synchronized evidence: `ep1.sync_timeline_jsonl`, `ep1.sync_timeline_csv`
- transcription QA: `ep1.transcription_qa`
- 새 scene candidate pool: `ep1.new_scene_pool` — historical reconstruction evidence; not the seed of the 2026-09-16 65-candidate rescan.

Narrative map은 청해·reaction과 독립적으로 `MUST_KEEP / BRIDGE / OPTIONAL`을 판정한다. 특히 `도망 제안 → 거절 → 폭탄 정체 → 전투 시작 → 동료 개입 → 전투 climax → 해변 관계 회수 → 레제의 배경 → 레제의 귀환 선택 → 죽음 → 덴지의 기다림` 인과 사슬을 다시 세웠다. 레제 죽음은 고립된 충격 컷이 아니라 선택의 결과와 결말의 비극적 아이러니까지 연결해야 한다.

### Independent evidence audit — 2026-09-14

repair 작업과 분리된 새 Codex 세션에서 primary MP4와 raw desktop/mic을 다시 확인하는 read-only 독립 감사를 수행했고 최종 verdict는 **`EVIDENCE_GATE_PASS`**였다.

- `予定/여정?`: 10분대 `サメの魔人` 사건과 12분대 `予定`·`여정?` 사건이 실제 source에서 분리되어 있고 raw utterance와 interpretation 경계도 유지됨 — PASS.
- N09/N10: 덴지의 내부 선택 → 위협·역습·태풍 → 약 50:30 narrative transition → 축제·불꽃 setup 순서와 beat/candidate/sync state가 실제 source와 일치 — PASS.
- N25 captured ending: 카페의 기다림 약속, 레제의 출발 시도와 귀환 선택, 마키마·천사악마의 저지·피습, 덴지가 진실을 모른 채 기다리는 closure가 current primary recording 안에서 보존됨 — PASS.
- P29: `걸렸다` 발화와 약한 표정 변화·눈 커짐·고정 응시·작은 고개 움직임이 실제 반응 수준이며 strong laugh / `head_down`은 없음 — PASS.
- 구조·회귀: JSONL/CSV 각 633행 parse와 완전 대응, TC 순서, narrative beat 25개, scene candidate 30개, ID/stale regression scan에 planning-critical blocker 없음.
- post-credit의 파워 카페 장면은 `01:45:25`에 끝나는 current primary recording 범위 밖이고 사용자 reaction도 없는 구간이므로 captured-material evidence의 누락 결함이나 planning blocker로 취급하지 않는다.

이 PASS는 reconstructed evidence가 **body-first planning 입력으로 사용할 수 있을 정도의 source fidelity gate를 통과했다**는 뜻이다. final select, 콘텐츠 각, body 구조, Cold open, REVIEW_C의 품질이나 최종 Step 5 PASS를 뜻하지 않는다.

EP1 packaging의 semantic owner는 `FIRST_VIDEO.md`다. recovery에서 historical로 격리된 것은 REVIEW_B의 34/15 select, body, scene-specific proof/payoff sequence와 Cold open이지 current packaging promise 자체가 아니다. 이 material/evidence owner는 package를 다시 소유하지 않으며, `予定 → 여정?`를 포함한 개별 scene은 current promise를 증명·보조하는 후보이지 새 top-level 상품이 아니다.

packaging promise가 current constraint로 복원되기 전에 만들어진 별도 body-first draft는 persistent current truth나 Step 9 입력으로 채택하지 않았다. 당시 30-candidate evidence pool을 `FIRST_VIDEO.md`의 promise 아래 다시 경쟁했던 historical planning과 그 장면 범위는 아래에 기록한다. 이 파일은 evidence provenance와 planned boundary를 소유하며 packaging 의미는 계속 `FIRST_VIDEO.md`가 소유한다.

## 4. Historical reconstructed planning과 subtitle-assisted Step 9

당시 최종 verdict: **`STEP9_PASS`**. 이는 review rough cut 생성용 planning gate 통과였지만, 이후 사용자가 REVIEW_C를 시청해 quality failure로 거절했다. 아래 select/body/Cold open은 failure analysis와 provenance를 위한 기록이지 현재 selection input이 아니다.

- storytelling 방향: `선택을 따라가는 귀`. 덴지와 레제의 선택을 따라가는 작품 서사를 골격으로 두고, 정확한 일본어 형태는 놓쳐도 들은 말·화면·앞 사건을 합쳐 관계와 감정선에 도착하는 비대칭을 누적한다.
- 작품 서사 보조 primary subtitle: `ep1.source_subtitles_ko` directory의 `ChainsawMan_Movie_Reze_erai.smi`. `ChainsawMan_Movie_Reze_subsplease.smi`도 함께 확인했으며 두 파일의 줄 수와 대사 내용은 같고 빈 sync marker 하나의 시각만 1초 다르다. 한국어 자막은 작품 사건·대사 의미 확인용이며 user mic evidence를 대체하지 않는다.
- 당시 Cold open: recording TC `33:26.6~33:38.6` + `53:32.9~53:45.6`, 약 24.7초. body 재등장에는 전체 관계·원인·결과가 추가된다.
- 당시 package copy: 제목 `일본어 제대로 안 배우고 20년 넘게 애니 본 사람, 자막을 꺼봤습니다` / 썸네일 `뜻은 아는데 일본어는 모름?`. `내용은 아는데 일본어는 모름?`은 전체 영화 이해를 과장할 위험 때문에 기각했다. exact copy lock은 아니다.
- 레제 과거: `100:11.8~100:14.2`의 사용자 `하나도 못 알아듣겠다`와, `100:14.1~100:23.2`·`100:43.3~100:59.2`의 작품 자막 정보, `101:04.1~101:14.0`의 귀환 선택 bridge를 분리한다. 작품 정보는 listening success가 아니다.

### Rejected REVIEW_C final select — primary recording planned boundaries

아래 범위는 evidence/beat의 넓은 원래 범위가 아니라 review rough cut에 사용할 planned in/out이다. Cold open 뒤 S01~S17은 recording TC 오름차순이다.

| scene | planned in/out | 당시 function |
|---|---|---|
| Cold open | `33:26.6~33:38.6`; `53:32.9~53:45.6` | 글자·정확한 형태의 약점과 실제 의미 추적의 대비 |
| S01 | `05:17~05:31`; `06:41~07:08`; `09:50~10:31` | 시작 조건, 작품 진입, 첫 listening state |
| S02 | `11:31~12:05`; `12:14~12:50`; `15:47~16:42`; `20:30~21:28` | 초기 오청·부분 이해와 마키마 관계 setup |
| S03 | `22:18~23:26`; `24:20~24:34`; `25:04~25:40`; `29:45~30:12`; `30:29~31:10` | 레제 만남·카페 초대·천사 bridge |
| S04 | `31:20~31:55`; `32:24~33:50`; `34:10~35:08` | 한자 장면의 full context와 읽기/듣기 비대칭 |
| S05 | `35:20~35:55`; `36:20~37:35`; `39:40~40:20`; `41:42~41:55`; `42:45~42:59` | 관계 형성과 수영 setup·reaction |
| S06 | `45:45~47:10`; `47:20~48:20`; `48:30~50:30` | 친밀감에서 위협·내부 선택으로 전환 |
| S07 | `52:20~53:00` | 도망 제안 직전 관계 bridge |
| S08 | `53:00~54:30`; `55:10~55:50` | 도망 제안과 덴지의 거절·현재 삶 선택 |
| S09 | `55:58~56:30`; `56:40~58:10` | 배신·폭탄 정체와 전투 시작 |
| S10 | `58:10~59:30`; `60:40~61:20` | 위협 확장과 전투 진입 bridge |
| S11 | `63:18~63:36`; `65:17~65:42`; `66:16~67:05`; `69:18~69:31`; `70:19~70:38`; `71:33~72:08`; `72:20~72:53`; `73:21~73:40`; `77:02~77:34`; `78:01~78:12` | 차량 추격, 덴지의 재전투 이유, Beam 설명·협력 |
| S12 | `78:18~78:45`; `78:57~79:14`; `79:26~79:53`; `80:14~80:58`; `82:50~83:05`; `83:32~84:10`; `84:26~85:10` | 아키·천사 위기와 구조, 덴지 재진입 |
| S13 | `85:16~85:32`; `85:59~86:43`; `86:59~87:10`; `90:05~90:15`; `91:20~91:40`; `92:00~94:10`; `94:10~94:35`; `94:50~95:10` | 수영 callback, 물 전술 실행·결과, 해변 도착 |
| S14 | `95:10~95:50`; `96:04~96:25`; `96:40~97:20`; `97:27~98:10`; `98:38~99:12` | 해변 resolution, 관계 회수, 카페 약속 |
| S15 | `100:11.8~100:14.2`; `100:14.1~100:23.2`; `100:43.3~100:59.2`; `101:04.1~101:14.0` | 못 들은 레제 과거와 귀환 선택 bridge를 분리 |
| S16 | `101:25~101:50`; `102:05~102:15` | 귀환 선택에서 마키마·천사의 저지로 연결 |
| S17 | `102:15~102:38`; `102:38~103:23`; `103:23~103:50`; `103:50~104:20`; `104:20~104:45`; `104:50~105:18` | 피습·죽음과 덴지가 모른 채 기다리는 결말 |

S11~S13의 hard continuity는 `레제가 차량을 추격 → 덴지가 다시 나서는 이유 → Beam의 설명과 협력 → 아키·천사의 위기와 구조 → 덴지 재진입 → 수영 callback → 물 전술 실행·결과 → 해변 resolution`이다. TC 자체보다 이 인과를 보존하며 전투 전체를 길게 남기지 않는다.

### Step 10 review rough cut artifact

- artifact: `ep1.review_c`
- provenance: REVIEW_B를 source로 쓰지 않고 당시 planned boundaries를 primary MP4에서 직접 추출했다.
- 구성: Cold open 2구간 + 4초 context slate + chronology body 72구간.
- 실제 검사값: `44:43.021`, 1280×720 / 30fps / H.264, AAC 48kHz stereo, 파일 크기 245,559,398 bytes.
- 검증: ffprobe 정상, 영상·오디오 stream 정상, 시작·중간·끝 decode 정상, Cold open/context/N22 표시 frame 확인.
- 레제 과거 표시: `내가 실제로 들은 것`과 `작품 자막 정보 — 내가 들은 내용 아님`을 화면에서 분리했다.
- historical artifact 판정: **REVIEW_C_REJECTED**. 사용자가 시청한 scene-selection·within-scene compression·story-context allocation failure evidence다. 현재 새 rescan 상태는 이 문서 상단을 따르며 현 cut은 축소 수정의 base가 아니다.

# Historical evidence — REVIEW_B 이전 분석

아래 `장면 경쟁 기준`부터 문서 끝까지는 2026-09-13의 34 candidates / 15 selects / REVIEW_A·B를 재현하기 위한 역사 기록이다. 현재 후보·구조·품질 판정으로 실행하지 않는다. A/B/C, 실제 material 사실, provenance history 자체는 보존한다.

## H1. 당시 장면 경쟁 기준

각 후보의 `통과축`은 다음 10개 질문 번호다.

1. 없으면 A+B의 특수성이 약해지는가
2. C를 설명하지 않고 보여주는가
3. `이런 식으로 남아 있네`를 느끼게 하는가
4. 앞과 다른 새 정보·감정·질문을 만드는가
5. 사용자 캐릭터가 사는가
6. 제목·썸네일 promise를 증명·갱신하는가
7. 뒤 핵심까지 볼 이유를 만드는가
8. 같은 기능의 더 강한 장면이 없는가
9. 사실 경계를 지키면서 재미있는가
10. 짧게 떼어 공유 가능한가

`통과축`이 적어도 모든 축에서 약하다는 뜻은 아니다. 최종 유지에는 최소 하나의 고유 기능이 있어야 하며, 동일 기능의 강한 경쟁자가 있으면 보류·탈락시켰다.

## 4. 시간순 장면 로그

### 후보 핵심 사실

| ID | 원본 TC / 길이 | 실제 장면·작품 사건 | 사용자 실제 발화 / 비언어 | 포착·이해 결과 | 최초성 | 확인 | 1차 판정 |
|---|---:|---|---|---|---|---|---|
| C01 | 00:06~02:17 / 131s | 악몽·오프닝을 보며 소리와 상황을 따라감 | `무슨 말인지 몰라`, `이거 아직 꿈?`, `꿈이 아니잖아` / 고정 응시 | 일부 소리·장면 문맥, 세부 미이해 | 재확인 | A+V | 보류 — 시작은 되지만 A+B 특수성이 약함 |
| C02 | 05:17~07:10 / 113s | 타이틀 카드를 세우고 `チェンソーマン`과 화면 글자를 읽음 | `이는 어디 간 거야?`, `체인소만? 뭐야 이거?` / 입 모양 반복, 고개·시선 이동 | 문자 읽기 시도, 장음·표기 구조에서 막힘 | 재확인 | AV | 유지 — 읽기 출발점을 행동으로 증명 |
| C03 | 08:54~09:55 / 61s | 파워의 피를 빼야 한다는 대사 | `지누키?`, `괜찮다는 말인가?` 뒤 `피를 뺀다는 말인가` / 집중, 헤드폰 조정 | 소리만 포착→어휘 추측→자가수정; `血抜き` 의미에 도달 | 재확인 | AV | 유지 — 단순 실패보다 귀의 작동 과정이 보임 |
| C04 | 10:20~10:47 / 27s | 마키마가 오늘 계획을 묻는 대사 | `오늘은 어떤 느낌의 여정일까? 여정?` | 문장 틀은 잡고 `予定`를 `여정`으로 오해 | 재확인 | AV | 유지 — 짧고 명료한 핵심어 오해 |
| C05 | 11:55~13:07 / 72s | 데이트 약속·도착 시간·덴지의 경험 대화 | `몇 시에 왔어?`, `5시에 왔어`, `여성과 노는 건 처음이라서` / 짧은 놀람 | 여러 문장 의미 직접 이해; 일부 시간 세부는 흔들림 | 재확인 | AV | 유지 — 정확 이해 대표 |
| C06 | 15:18~15:25 / 7s | `次が最後` | `다음이 마지막` | 정확 이해 | 재확인 | AV | 탈락 — 과거 `다음이 최고` 오해가 본 촬영에서는 재현되지 않음 |
| C07 | 15:50~16:45 / 55s | 영화가 미묘하다는 평가와 `한 편이 인생을 바꾼다`는 대화 | `솔직히 지금까지는 미묘했다`, `한 편이 인생을 바꾼다`, `이게 그 한 편인가?` / 진지한 응시 | 긴 문장의 요지와 장면 감정 이해 | 재확인 | AV | 유지 — 성공 사례이자 작품 감상 캐릭터 |
| C08 | 17:57~20:00 / 123s | 마키마와 덴지의 관계 대화 | `마키마도구나?`, `마음이 있다고 얘기하는 건가?` / 턱 괴고 집중 | 관계 요지는 따라가나 세부 표현은 불확실 | 재확인 | A+V | 보류 — C07/C23보다 설명력이 약함 |
| C09 | 21:15~21:55 / 40s | 다른 사람과의 관계·선택 대화 | `나는 나를 좋아하는 사람이 좋다`, `확정적으로 나를 좋아하는 거잖아` / 미소 | 대사+문맥 이해와 사용자 성격이 동시 발생 | 재확인 | A+V | 유지 — 인물성 변주 |
| C10 | 22:18~22:36 / 18s | 우산 관련 대화 | `우산... 우산이었어야 된다` | 핵심 단어 포착, 문장 관계는 부분 이해 | 재확인 | A | 탈락 — 더 강한 자가수정 C03/C17 존재 |
| C11 | 26:30~26:40 / 10s | 빠른 이동 장면 | `빨라`, `나보다 빨랐다` / 순간 놀람 | 화면+짧은 발화 반응 | 재확인 | A+V | 탈락 — A+B보다 일반 리액션 |
| C12 | 27:45~29:05 / 80s | 레제의 호감 표현과 약속 | `나한테 웃어주고 만져주고 하니까`, `확정적으로 나를 좋아하는 거잖아` / 표정 이완·미소 | 관계 흐름 이해 | 재확인 | A+V | 보류 — C09와 기능 중복, 후속 맥락용 |
| C13 | 29:20~30:35 / 75s | 민간 데빌헌터와 레제의 역전 | `인간군... 민간 데빌헌터인 것 같아`, `죽여줘`, `너의 힘이면 편안하게 죽을 수 있잖아` / 눈 커짐 | 정체·위협·요지를 연속 포착 | 재확인 | A+V | 보류 — 사건은 강하지만 C23보다 A+B 압축력이 약함 |
| C14 | 31:15~31:55 / 40s | 덴지가 마음은 마키마에게 있다고 말함 | `내 마음은 마키마상 거다`, `오로지 마키마상 거다` | 핵심 의미 직접 이해 | 재확인 | A | 보류 — C09/C25의 빌드업에 필요할 때만 |
| C15 | 33:29~33:41 / 12s | `漢字読めないの？`와 덴지의 읽기 약점 | `한자 못 읽는다는 말인가 / 나도 못 읽는데` / 즉시 입꼬리 상승, 이어 웃음 | 일본어 대사 정확 이해+자기 동일시; 사용자도 일본어 글 읽기가 약함 | 재확인 | AV | 유지 — promise proof 1순위, 독립 payoff로는 아님 |
| C16 | 35:21~36:10 / 49s | 밤의 학교 탐험·두려움 대화 | `손잡아줄래`, `몸이 말을 안 듣는다고` / 고개 기울임 | 문장 요지 이해와 일부 미이해 혼재 | 재확인 | A+V | 보류 — 기능이 다른 장면보다 약함 |
| C17 | 38:00~38:12 / 12s | `冷やすか` 계열 발화 | `히야시... 차게 하자는 말이구만` | 소리 반복 후 의미 자가수정 | 재확인 | A | 유지 — C03과 짝을 이루는 짧은 변주 |
| C18 | 39:43~40:10 / 27s | 덴지가 갑자기 옷을 벗고 수영장에 들어가려 함 | `뭐야 벗고 있네, 언제 벗었어`, `안 들어갈 수가 없네` / 즉시 미소 | 화면·관계 맥락 반응 | 재확인 | AV | 유지 — 작품을 실제로 즐기는 인물 증거 |
| C19 | 40:25~42:32 / 127s | 레제가 수영을 가르치며 `모르는 것·못하는 것을 전부 알려준다`고 함 | `물이 무섭냐`, `오요기가 수영인가 보네`, `안 좋아할 수가 없다`, `전부 알려줄게`, `상징적이야` / 넓은 미소 뒤 집중 | 단어 추론+관계 의미+작품 해석 | 재확인 | AV | 유지 — 작품 몰입과 언어 이해 결합 |
| C20 | 43:20~43:55 / 35s | 나비·포식 이미지와 관계 암시 | `방금 좀 의미심장한`, `거미가 나비를 잡아먹어?` / 손을 입에 댐 | 시각 상징 해석; 청해 기여 불명 | 재확인 | AV | 보류 — 작품 몰입 보조, 청해 증거 아님 |
| C21 | 46:40~47:00 / 20s | 레제의 수상한 행동 | `가까이 오는 여자 조심해야 돼요` / 긴장된 응시 | 장면·서사 추론 | 재확인 | A+V | 보류 — 캐릭터는 살지만 C25가 더 강함 |
| C22 | 49:22~50:10 / 48s | 정체가 드러나기 전 표정·행동을 읽음 | `이거 봐도 안 깜짝아`, `얘도 체인소 심장을 노리고 왔다는 소리네`, `표정 보소` / 눈 커짐 | 화면+대사로 반전 선취 | 재확인 | A+V | 보류 — 재확인 영향이 커 독립 증거로 약함 |
| C23 | 53:00~54:28 / 88s | 레제가 덴지의 처지를 설명하고 함께 도망가자고 제안 | `16살인데 학교에도 안 가고`, `일 그만둬`, `나랑 같이 도망가자`, `행복하게 해줄게`, `지켜줄게`, `언젠간 학교로 같이 갈 수 있을 거야` / 고정 집중 | 긴 연속 대화의 핵심 관계·행동을 높은 밀도로 이해; 일부 한 문장은 `모르겠어` | 재확인 | AV | 유지 — 본 촬영 최강의 연속 청해 증거 |
| C24 | 55:19~55:49 / 30s | 덴지가 현재 삶이 재미있어졌다고 설명 | `싫어했던 선생이랑도 잘 되고`, `버디랑도 잘 되고`, `이제 좀 재밌다는 거고` | 서사 상태 변화 이해 | 재확인 | AV | 유지 — viewer question을 `실제 이야기도 따라가나`로 갱신 |
| C25 | 56:00~56:26 / 26s | 레제가 다른 좋아하는 사람이 있냐고 묻고 키스 | `알았어, 걸렸다`, `저런 질문하고 키스한다고?` / 크게 웃고 고개 숙임 | 관계 질문 정확 포착+즉시 캐릭터 반응 | 재확인 | AV | 유지 — 공유 단위·캐릭터 1순위 |
| C26 | 57:42~58:10 / 28s | 레제가 덴지의 심장을 가져가겠다고 밝힘 | `피를 마시는 건가?` 뒤 `덴지군의 심장 가져간다고 / 받아갈게`, `무서워` / 눈 커짐·몸 긴장 | 첫 추측을 정정하고 핵심 대사를 정확 포착 | 재확인 | AV | 유지 — payoff 전환·escalation |
| C27 | 59:00~60:15 / 75s | 정체 공개 뒤 공격·변신 | `와`, `아 저기 그거였어?`, `얼굴 없어졌는데?`, `빠르네` / 놀람 | 작품 반응 중심, 청해 판정은 약함 | 재확인 | A+V | 보류 — C26 뒤 짧은 브리지로만 |
| C28 | 60:42~61:30 / 48s | 본격 전투 시작 | `전투 개시`, `어둡네`, `이게 하얀? 아 몰라` / 고정 응시 | 몰입+미이해 | 재확인 | A+V | 보류 — 중간이 길어질 위험 |
| C29 | 62:40~65:00 / 140s | 전투 중 인물·계약·명령 대화 | `미래의 악마랑 계약했잖아`, `왜 네가 그런 정보를 알고 있는 거야`, `대답해` 등 | 부분·요지 이해가 반복 | 재확인 | A+V | 탈락 — 같은 리듬의 진단 사례 나열 위험 |
| C30 | 70:00~73:00 / 180s | 클라이맥스 전투 | 짧은 감탄 뒤 장시간 침묵 / 눈 고정·입 벌림·손을 입에 댐 | 언어 판정보다 작품 몰입 | 재확인 | V+A | 유지 — 8~12초 무언 몰입 비트만 사용 |
| C31 | 78:21~78:50 / 29s | 피를 받고 싸움을 이어가는 장면 | `피 받아갈게`, `보통 악마였으면 죽었을 텐데` | 대사+문맥 요지 이해 | 재확인 | A | 보류 — C23/C26보다 약함 |
| C32 | 84:01~85:08 / 67s | 눈앞에서 죽는 것은 원하지 않는다는 대화 뒤 빠른 공격 | `눈앞에서 죽는 건 원하지 않는다는 거구나`, `유도탄인가?`, `오, 하야이` / 85:02 활짝 웃음 | 감정 문장 이해+일본어 소리 자발적 모사+작품 반응 | 최초 반응 후보 | AV | 유지 — 후반 최초성·변주가 살아 있음 |
| C33 | 95:10~98:07 / 177s | 전투 후 덴지·레제의 긴 대화 | `공안에게 넘기면 까지는 알아들었는데 잘 모르겠고`, `아직도 내가 너를 진심으로 좋아한다고 생각해`, `홍조랑 다 구라라고`, `같이 안 도망가냐고`, `수영 가르쳐준 건 진짜였잖아` | 스스로 미이해 경계를 말한 뒤 여러 핵심 문장은 정확·요지 이해 | 최초 반응 후보 | AV | 유지 — 정직한 실패와 회복이 한 장면 안에 있음 |
| C34 | 100:12~105:18 / 306s | 엔딩 대화와 레제의 결말 | `하나도 못 알아듣겠다`, `여기가 레제 죽는 건가?`, `이렇게 죽는 거야?`, 마지막 `아쉽다` / 침묵·눈 고정·표정 가라앉음 | 일부 대사 미이해, 화면·서사로 결말 인지·감정 반응 | 최초 반응 후보 | A+V | 유지 — 작품 감정 payoff, 청해 성공으로 과장 금지 |

### 기획 역할·경쟁 결과

| ID | 역할 태그 | A 연결 / B 사건 / C 기여 | 시청자 질문·판단 | 공유 가능성 | 통과축 | 더 강한 경쟁자·판정 이유 |
|---|---|---|---|---|---|---|
| C01 | 소리만 포착, 작품 몰입 | 귀가 처음부터 완전한 성공은 아님 | `정말 들리는 사람인가?` | 낮음 | 4,7,9 | C03이 같은 질문을 더 선명하게 만듦 |
| C02 | promise 증명, 읽기-청해 격차, 캐릭터 | 공부하지 않은 읽기 상태를 실제 행동으로 제시 | `읽기는 이 정도인데 들으면?` | 중간 | 1,2,3,5,6,7,9 | 고유 출발점이라 유지 |
| C03 | 소리만 포착, 정확 이해, 캐릭터 | 귀에 남은 소리를 스스로 의미에 연결 | `모르다가 스스로 맞출 수도 있나?` | 중간 | 1,2,3,4,5,7,9 | C17보다 과정이 풍부해 대표 유지 |
| C04 | 오해, 공유 단위 | 익숙한 소리로 핵심어를 잘못 매칭 | `문장 틀을 알아도 단어 하나가 바꾸나?` | 높음 | 1,2,3,4,6,7,9,10 | 본 촬영의 대표 오해로 유지 |
| C05 | 정확 이해, promise 증명 | 짧은 문장 여러 개를 직접 재구성 | `생각보다 꽤 듣는데?` | 중간 | 1,2,3,4,6,7,9 | C23 전 초반 성공 증거 |
| C06 | 정확 이해 | 성공이지만 새 기능 없음 | `이건 맞았네` | 낮음 | 9 | 과거 오해 가설 보호 금지, 탈락 |
| C07 | 정확 이해, 작품 몰입, 캐릭터 | 의미 이해가 실제 영화 감상으로 연결 | `대사뿐 아니라 장면 감정도 따라가나?` | 중간 | 2,4,5,7,9 | C05와 다른 감정 기능이라 유지 |
| C08 | 부분 이해, 작품 몰입 | 관계 요지는 따라감 | `세부는 얼마나 비나?` | 낮음 | 4,7,9 | C23이 훨씬 명료해 보류 |
| C09 | 캐릭터, 작품 몰입 | 사용자 연애관이 작품 반응에서 드러남 | `이 사람은 작품을 어떻게 보나?` | 높음 | 2,4,5,7,9,10 | 짧은 인물 컷으로 유지 |
| C10 | 소리만 포착 | 단어 하나 포착 | `무엇까지 정확히 잡나?` | 낮음 | 3,9 | C03/C17에 패배 |
| C11 | 작품 몰입 | 일반 액션 반응 | 질문 갱신 없음 | 낮음 | 5,9 | A+B 기능 부재로 탈락 |
| C12 | 캐릭터, 작품 몰입 | 호감 관계를 따라감 | `레제를 얼마나 믿고 있나?` | 중간 | 4,5,7,9 | C25로 압축 가능 |
| C13 | 정확 이해, 작품 몰입 | 사건 반전을 따라감 | `액션 상황도 대사로 잡나?` | 중간 | 2,4,7,9 | 길이 대비 C23보다 약해 보류 |
| C14 | 정확 이해 | 관계 핵심을 이해 | `선택이 어디로 가나?` | 낮음 | 2,4,7,9 | C25 빌드업 필요 시만 |
| C15 | promise 증명, 정확 이해, 읽기-청해 격차, 캐릭터, 공유 단위 | 읽기는 약한 사람이 `한자 못 읽냐`는 말을 알아듣는 모순 | `글은 약한데 저 말은 바로 알아들어?` | 매우 높음 | 1,2,3,4,5,6,7,9,10 | promise proof 1위. C23보다 단독 공유성 강함 |
| C16 | 부분 이해, 작품 몰입 | 성공/실패 혼재 | `긴 장면은 어디서 비나?` | 낮음 | 4,9 | C33이 같은 기능을 더 정직하게 보여줌 |
| C17 | 소리만 포착, 정확 이해 | 소리 반복 뒤 의미 연결 | `귀가 어떻게 답에 도달하지?` | 중간 | 2,3,4,9 | 짧은 variation으로 유지 |
| C18 | 캐릭터, 작품 몰입, 공유 단위 | 진단보다 작품을 즐기는 사람이 먼저 보임 | `테스트 중에도 진짜 웃나?` | 높음 | 2,4,5,7,9,10 | C19 진입 비트로 유지 |
| C19 | 정확 이해, 캐릭터, 작품 몰입 | 단어·관계·상징 해석이 결합 | `이런 귀로 작품을 어디까지 즐기나?` | 중간 | 1,2,3,4,5,7,9 | 후반 질문을 갱신하므로 유지 |
| C20 | 작품 몰입 | 시각 상징을 읽음 | `청해 외 감상도 살아 있나?` | 중간 | 4,5,9 | 청해 인과로 쓰지 않고 보류 |
| C21 | 캐릭터, 작품 몰입 | 수상함에 대한 사용자 반복 농담 | `예감이 맞을까?` | 중간 | 4,5,7,9 | C25/C26 payoff 앞 짧은 복선 가능 |
| C22 | 작품 몰입 | 반전 예측 | `정체를 알아챘나?` | 중간 | 4,5,7,9 | 재확인 오염이 커 보류 |
| C23 | promise 증명, 정확 이해, 작품 몰입 | 긴 대화를 실제 서사 단위로 따라감 | `이건 단어 몇 개가 아니라 이야기를 듣는 건가?` | 중간 | 1,2,3,4,6,7,8,9 | 연속 청해 증거 1위, 유지 |
| C24 | 정확 이해, 작품 몰입 | 인물의 상태 변화를 파악 | `왜 도망가지 않나?` | 중간 | 2,4,7,9 | C23→C25 연결용 유지 |
| C25 | 정확 이해, 캐릭터, 작품 몰입, 공유 단위 | 정확 이해가 큰 웃음과 즉시 연결 | `들켰다—그 다음은?` | 매우 높음 | 1,2,3,4,5,7,8,9,10 | 캐릭터/공유 1위, 유지 |
| C26 | 정확 이해, 작품 몰입, payoff build | 추측을 바로 고치며 반전 핵심을 포착 | `관계가 액션으로 어떻게 뒤집히나?` | 높음 | 1,2,3,4,5,7,9,10 | 구조 전환 1위, 유지 |
| C27 | 작품 몰입 | 액션 반응 | `싸움이 어떻게 되나?` | 중간 | 4,5,7,9 | 짧은 브리지 외 보류 |
| C28 | 작품 몰입, 미이해 | 몰입과 구멍이 동시 존재 | `말을 놓쳐도 따라가나?` | 낮음 | 3,4,7,9 | C30/C33에 패배 |
| C29 | 부분 이해 | 여러 판정이 이어짐 | 새 질문이 약함 | 낮음 | 3,9 | 사례 나열 위험으로 탈락 |
| C30 | 작품 몰입 | 말없이 긴 전투를 봄 | `분석을 멈추고 작품에 빠졌나?` | 중간 | 2,4,5,7,9 | 8~12초만 유지 |
| C31 | 정확 이해 | 전투 문맥 이해 | `후반에도 듣나?` | 낮음 | 3,9 | C32가 더 강해 보류 |
| C32 | 정확 이해, 소리만 포착, 캐릭터, 작품 몰입, 공유 단위 | 문장 이해→`하야이` 모사→미소가 한 비트 | `후반 첫 반응에서도 귀와 재미가 같이 사나?` | 높음 | 1,2,3,4,5,7,8,9,10 | 후반 최초 반응 후보 1위 |
| C33 | 정확 이해, 미이해, 작품 몰입, payoff | 모르는 경계를 밝히고 다시 핵심을 따라감 | `못 들은 뒤에도 이야기를 회복하나?` | 중간 | 1,2,3,4,5,7,8,9 | 실패를 약점 나열이 아닌 회복으로 만듦 |
| C34 | 작품 몰입, 캐릭터, payoff | 청해 미이해와 결말 감정이 동시에 남음 | `결국 작품을 어떻게 경험했나?` | 중간 | 2,4,5,8,9 | 엔딩 감정용 유지, 청해 성공으로 사용 금지 |

장면 후보 총수는 **34개**다. `유지 18 / 보류 12 / 탈락 4`이며, 유지 장면 중 같은 기능은 셀렉트 릴에서 다시 묶어 **15개 select**로 압축했다.

## 5. 가장 강한 실제 장면 TOP 5

1. **53:00~54:28 (C23)** — `16살·학교·일·도망·행복·지켜줌·언젠가 학교`를 연속해서 따라간다. 짧은 단어 맞히기가 아니라 실제 서사를 듣는다는 가장 강한 증거다.
2. **33:29~33:41 (C15)** — `漢字読めないの？`에 `한자 못 읽는다는 말인가 / 나도 못 읽는데`. A+B의 모순과 패키지 promise를 가장 짧게 압축한다.
3. **56:00~56:26 (C25)** — `알았어, 걸렸다` 뒤 웃음, 그리고 `저런 질문하고 키스한다고?`. 이해·캐릭터·공유성이 동시에 산다.
4. **95:10~98:07 (C33)** — `공안에게 넘기면 까지는 알아들었는데 잘 모르겠고`라고 한계를 밝힌 뒤, 호감의 거짓·도망 제안·수영 회수는 다시 잡는다. 실패와 회복이 정직하다.
5. **57:42~58:10 (C26)** — `피를 마시는 건가?`에서 `덴지군의 심장 가져간다고`로 즉시 수정하며 관계극을 액션 payoff로 넘긴다.

TOP 5 밖의 가장 강한 캐릭터 보조는 C18~C19 수영장, 후반 최초 반응 후보는 C32다.

## 6. 셀렉트 릴 — 본 촬영 원본 시간순

Cold open용 복제 후보는 별도 표시하되 아래 chronology가 본편 기준이다.

| Select | 원본 TC | 장면 한 줄 | 역할 | A/B→C 기여 | viewer question | 유지 이유 |
|---|---:|---|---|---|---|---|
| S01 | 05:17~07:10 | 타이틀 카타카나를 실제로 읽다 `이`가 어디 갔는지 막힘 | promise 증명, 읽기-청해 격차, 캐릭터 | A의 읽기 출발점 실증 | `이 정도 읽기인데 자막을 끄면?` | 말보다 행동으로 조건을 잠금 |
| S02 | 08:54~09:55 | `血抜き` 소리를 붙잡고 오답 추측 뒤 `피를 뺀다`에 도달 | 소리만 포착, 정확 이해 | 귀에 남은 방식 자체를 보여줌 | `모르다가 귀로 풀기도 하나?` | 결과보다 과정이 재미있음 |
| S03 | 10:20~10:47 | `予定`를 `여정`으로 해석 | 오해, 공유 단위 | 비대칭의 실패 측면 | `문장 전체가 단어 하나로 틀어지나?` | 본 촬영 대표 오해 |
| S04 | 11:55~13:07 | 데이트·5시 도착·`여성과 노는 건 처음`을 연속 이해 | 정확 이해, promise 증명 | 실제 듣기 성공 증거 | `생각보다 꽤 듣나?` | S03 직후 판단을 뒤집음 |
| S05 | 15:50~16:45 | 영화 평가와 `한 편이 인생을 바꾼다`를 따라감 | 정확 이해, 작품 몰입, 캐릭터 | 언어를 작품 감정으로 사용 | `내용까지 즐기는가?` | 진단 사례를 감상으로 변주 |
| S06 | 21:15~21:55 | `나는 나를 좋아하는 사람이 좋다` | 캐릭터, 작품 몰입 | 사용자를 기억하게 함 | `이 사람은 관계를 어떻게 읽나?` | 짧은 인물 비트 |
| S07 | 33:29~33:41 | `漢字読めないの？`→`한자 못 읽는다는 말인가 / 나도 못 읽는데` | promise 증명, 읽기-청해 격차, 공유 단위 | A+B 모순 압축, C의 직접 장면 | `글은 약한데 저 말은 들려?` | promise proof 1위; Cold open 후보 |
| S08 | 38:00~38:12 | `히야시`를 반복하다 `차게 하자`로 연결 | 소리만 포착, 정확 이해 | 귀의 자가수정 변주 | `이 귀는 어떻게 답을 찾나?` | 12초 압축 가능 |
| S09 | 39:43~42:32 | 옷 벗은 덴지에 웃고 수영·관계·상징을 해석 | 캐릭터, 작품 몰입, 정확 이해 | 진단을 넘어 실제 소비 모습을 보여줌 | `이런 귀로 작품을 얼마나 즐기나?` | 후반 viewer question 갱신 |
| S10 | 53:00~54:28 | 도망 제안의 긴 대화를 연속 재구성 | promise 증명, 정확 이해, 작품 몰입 | 청해가 서사 단위로 작동함을 증명 | `단어가 아니라 이야기를 듣는 건가?` | 연속 청해 1위 |
| S11 | 56:00~56:26 | 다른 좋아하는 사람 질문에 `걸렸다`, 웃음 | 정확 이해, 캐릭터, 공유 단위 | 이해가 자연 반응으로 전환 | `레제는 뭘 할까?` | 캐릭터/공유 1위; Cold open 대안 |
| S12 | 57:42~58:10 | 심장을 가져간다는 대사로 추측을 즉시 수정 | 정확 이해, payoff build, 작품 몰입 | 귀의 작동과 사건 escalation 결합 | `관계가 어떻게 뒤집히나?` | payoff 전환 1위 |
| S13 | 70:20~70:32 | 클라이맥스 전투 무언 고정 응시 | 작품 몰입 | `듣기 테스트`가 실제 감상으로 귀결 | `말없이도 얼마나 빠졌나?` | 설명 없는 호흡 8~12초 |
| S14 | 84:01~85:08 | 죽음 회피 감정 문장 이해→`하야이` 모사→미소 | 정확 이해, 소리 포착, 캐릭터, 작품 몰입 | 후반에도 귀·감정·재미가 같이 움직임 | `후반 첫 반응도 같은가?` | 최초 반응 후보·변주 |
| S15 | 95:10~105:18 | 미이해를 밝히고 대화를 회복한 뒤 결말에 `아쉽다` | 미이해, 정확 이해, 작품 몰입, payoff | 구멍이 있어도 작품 경험이 성립하는 최종 증거 | `결국 무엇을 듣고 무엇을 느꼈나?` | C를 장면 누적으로 닫음; 실제 사용은 60~90초로 압축 |

## 7. Cold open 경쟁

### 1순위

`33:29~33:41` 한자 장면 → `10:20~10:47`의 `予定→여정` 1비트 → `56:00~56:26`의 `걸렸다` 웃음 → `일본어를 제대로 공부해본 적은 거의 없습니다`.

- promise를 12초 안에 회수한다.
- 성공만 자랑하지 않고 곧 오해를 붙인다.
- 세 번째 비트가 실제 사람과 작품 재미를 보여준다.
- 미해결 질문은 `그럼 전체 영화를 실제로 어디까지 따라가나?`다.

### 대안

`53:00~54:28`에서 `일 그만둬 / 같이 도망가자 / 행복하게 해줄게 / 지켜줄게`를 8~12초 몽타주 → `33:29` 한자 장면 → `10:20` `여정?`.

이 대안은 청해 증명이 더 강하지만, 독립 상황 설명 비용이 커 1순위보다 Cold open 즉시성이 낮다.

`次が最後→다음이 최고`는 본 촬영에서 실제로 발생하지 않았으므로 후보에서 제거한다.

## 8. Payoff 경쟁

### 1순위 payoff

단일 한자 장면이 아니라 **53:00~58:10 연속 구간**이다.

1. 긴 도망 제안의 핵심을 연속해서 잡는다.
2. 덴지가 현재 삶이 재미있어졌다는 이유를 따라간다.
3. 다른 좋아하는 사람이 있다는 질문에 `걸렸다`고 웃는다.
4. 곧 심장을 노린다는 대사로 관계 해석을 수정한다.

이 누적은 `단어 몇 개를 우연히 안다`를 넘어, 정확함과 구멍이 있는 귀로 실제 이야기를 따라가고 즐기는 모습을 보여준다. C는 이 장면 뒤 설명으로 새로 만드는 것이 아니라 앞의 읽기 약점·`予定` 오해·`血抜き` 자가수정과 연결하면서 생긴다.

### 한자 장면의 최종 경쟁 결과

`33:29`는 **핵심 payoff 1위에서 promise-proof 1위로 조정**한다. 짧은 공유 단위와 패키지 회수력은 최고지만 재확인 장면이며, 본 촬영 발화도 과거의 `나랑 똑같네`가 아니라 `한자 못 읽는다는 말인가 / 나도 못 읽는데`다. 긴 서사 이해를 증명하는 C23과, 이해가 웃음·반전으로 전환되는 C25~C26이 전체 영상 payoff로는 더 강하다.

## 9. 실제 타임코드 기반 러프 구조표

Cold open만 순서 예외다. 본편은 원본 시간순을 유지한다. 재확인과 후반 최초 반응 후보는 이 내부 로그에서만 구분하며 화면 자막·나레이션·overlay로 자동 노출하지 않는다.

| 예상 완성본 | 원본 TC | 장면 | 이 시점의 시청자 질문 | 새 정보·감정 | A/B→C 역할 | 구조 기능 | 편집 메모 | 사용 |
|---|---:|---|---|---|---|---|---|---|
| 0:00~0:28 | 33:29~33:41 + 10:20~10:47 + 56:00~56:26 | 한자 대사 이해→`여정?` 오해→`걸렸다` 웃음 | `글은 약한데 듣기는 되고, 또 저렇게 틀리기도 해?` | 성공·실패·인물성 3비트 | A+B 모순을 즉시 제시 | opening / promise proof | 결과 공개 허용. 각 비트 3~7초. 촬영 provenance는 내부 로그에만 유지 | 사용 |
| 0:28~1:12 | 05:17~07:10 | 타이틀 카타카나를 실제로 읽다 막힘 + A/B 최소 설명 | `이 읽기 상태로 자막 없이 어디까지?` | 출발점·조건 | A 실증, B 잠금 | setup / promise proof | 긴 표기 분석은 25~35초로 압축 | 사용 |
| 1:12~2:00 | 08:54~09:55 | `血抜き` 소리→오답→피를 뺀다로 자가수정 | `모르는 소리를 어떻게 뜻에 붙이지?` | 귀의 작동 과정 | C의 `이렇게 남음` 첫 체감 | escalation | desktop 대사와 mic 추측을 교차, 정답 해설 최소화 | 사용 |
| 2:00~2:35 | 10:20~10:47 | `予定`를 `여정`으로 오해 | `잘 듣는 게 아니라 익숙한 소리로 메우는 건가?` | 첫 명료한 실패 | C를 과장 없이 균형 | variation | Cold open 비트의 원래 맥락 회수 | 사용 |
| 2:35~3:25 | 11:55~13:07 + 15:50~16:45 | 데이트·도착·첫 경험과 영화 한 편의 의미를 이해 | `그런데 문장과 감정은 꽤 잡네?` | 판단 재반전 | B 성공 증거 | escalation / promise proof | 정확 이해를 2개만 남기고 판정표 나열 금지 | 사용 |
| 3:25~3:55 | 21:15~21:55 | `나는 나를 좋아하는 사람이 좋다` | `이 사람은 작품을 어떻게 보나?` | 사용자 캐릭터 | C를 사람의 경험으로 만듦 | character | 짧고 건조하게 살림 | 사용 |
| 3:55~4:30 | 33:29~33:41 | 한자 장면 전체 맥락 + 초반 읽기 recall | `한자 못 읽냐는 말은 왜 바로 들리지?` | 패키지 모순 완전 회수 | 읽기-청해 격차 | promise proof / midpoint turn | `나랑 똑같네`로 바꾸지 말고 본 촬영 실제 발화 사용 | 사용 |
| 4:30~4:52 | 38:00~38:12 | `히야시` 반복→차게 하자 | `우연한 한 문장인가, 반복되는 방식인가?` | 두 번째 자가수정 | C 누적 | variation | 10~15초 | 사용 |
| 4:52~5:48 | 39:43~42:32 | 수영장 진입 웃음→수영 단어→관계·상징 해석 | `이런 귀로 작품을 실제로 즐기나?` | 진단에서 감상으로 전환 | B가 실제 작품 소비가 됨 | character / escalation | 가장 큰 미소와 정확 이해를 45~55초로 압축. 청해만으로 웃었다고 주장 금지 | 사용 |
| 5:48~7:12 | 53:00~54:28 + 55:19~55:49 | 도망 제안과 덴지의 현재 삶을 연속 이해 | `단어 몇 개가 아니라 이야기를 듣는 건가?` | 연속 서사 이해 | A+B 특수성 최강 증거 | payoff build | 핵심 문장 6~8개, 중복 번역 자막 최소화 | 사용 |
| 7:12~7:58 | 56:00~56:26 + 57:42~58:10 | `걸렸다` 웃음→심장 대사로 즉시 뒤집힘 | `관계 해석이 액션 반전까지 따라가나?` | 웃음에서 긴장으로 급전환 | 이해·캐릭터·사건 결합 | payoff | 표정 변화와 대사 타이밍 보존 | 사용 |
| 7:58~8:12 | 70:20~70:32 | 전투 무언 고정 응시 | `분석을 잊고 본 건가?` | 호흡·몰입 | 작품 자체를 즐긴 결과 | variation / character | 설명 없이 8~12초, 음악 저작권·사용 범위는 실제 편집 때 검토 | 사용 |
| 8:12~8:48 | 84:01~85:08 | 감정 문장 이해→`하야이` 모사→미소 | `후반 반응에서도 같은 귀가 보이나?` | 후반 내부 최초 반응 후보에서 귀·감정 재등장 | C가 앞부분 장면에만 의존하지 않게 보강 | payoff build | 최초성은 내부 분석에서만 보수적으로 분류하고 화면에 주장하지 않음 | 사용 |
| 8:48~9:55 | 95:10~98:07 | `여기까지는 알아들었는데 잘 모르겠고`→후속 핵심은 회복 | `구멍이 생기면 이야기를 놓치나?` | 정직한 실패와 회복 | 실패가 C를 강화 | payoff | 긴 장면 중 미이해 선언+회복 3문장만 50~65초 | 사용 |
| 9:55~10:35 | 100:12~105:18 | `하나도 못 알아듣겠다` 뒤 결말을 보고 `아쉽다` | `결국 이 사람에게 무엇이 남았나?` | 성공이 아닌 실제 작품 감정 | C의 현장 결과 | payoff / emotional close | 결말 스포일러 범위는 편집에서 최소화. 청해 성공으로 포장 금지 | 사용 |
| 10:35~끝 | 전체 회수 + 엔딩 나레이션 | 읽기 약점·자가수정·오해·서사 이해·몰입을 4~5비트 회수 | `이 귀에 글자와 정확한 표현을 붙이면?` | 경험에 이름을 붙임 | 핵심 C+파생 C | exit hook | `20년 때문에`가 아니라 `20년 취미 시청 뒤 이런 상태가 남아 있었다`로 제한 | 사용 |

예상 1차 가편은 약 **10분 45초 전후**였다. 이는 문서상 추정치이며 길다/짧다를 사용자가 표만 보고 판정하지 않는다. AI가 중복·구조 위험을 먼저 조정한 REVIEW_B를 만든 뒤 실제 시청 호흡으로 검증한다.

## 10. 구조 검증 결과

- 첫 30초: package A의 `글은 잘 못 읽는데 들림?`을 C15로 바로 증명하고 C04 실패·C25 캐릭터로 질문을 확장한다.
- 질문 갱신: `들리나?` → `어떤 방식으로 남았나?` → `실제 이야기까지 따라가나?` → `구멍 뒤에도 회복하나?`로 변한다.
- 중간 평탄화: 정확/오답 분류를 챕터화하지 않고 C19의 작품 감상, C23의 연속 서사, C25~C26의 감정 급전환으로 끊는다.
- 작품 몰입: C18~C19, C25~C26, C30, C34가 남는다. 청해로만 웃었다고 주장하지 않는다.
- 정확 이해 반복: 초반 성공은 C05/C07 두 기능으로 제한하고, 이후는 자가수정·오해·인물·서사·몰입으로 기능을 바꾼다.
- 실패의 역할: C04는 익숙한 소리 오매칭, C33은 모르는 경계와 회복, C34는 청해와 작품 감정의 분리를 보여준다.
- 인과 경계: `20년이 청해를 만들었다`, `성우 따라 하기가 청해를 늘렸다`를 주장하지 않는다.
- C 형성: C02→C03/C04→C15→C23/C25/C26→C33/C34의 누적이 먼저 C를 만들고, 마지막 나레이션은 이름만 붙인다.
- payoff 경쟁: C15는 package proof, C23~C26이 본편 payoff 1위다.
- 자연스러운 예상 댓글: `한자는 못 읽는데 한자 못 읽냐는 말은 알아듣네`, `예정은 여정으로 듣는데 긴 연애 대화는 또 다 따라가는 게 이상하다`, `나도 자막 끄면 이런 식일지 궁금함`.
- exit hook: `이 귀에 지금 비어 있는 글자와 정확한 표현을 붙이면 어떻게 달라질까?`만 남기고 다음 학습법은 설명하지 않는다.

## H11. 당시 Package A 재검증

당시 판정: **최소 수정**.

- 제목 `일본어 제대로 안 배우고 20년 넘게 애니 본 사람, 자막을 꺼봤습니다`는 유지했다. 당시 A+B와 실제 본 촬영 전체에 맞는다고 판정했다.
- 썸네일 `글은 잘 못 읽는데 들림?`도 유지 가능하다고 판정했다. C02와 C15가 회수한다는 당시 근거였다.
- 당시 수정 대상은 패키지 문구가 아니라 Cold open 구성이었다. 본 촬영에서 `次が最後` 오해가 재현되지 않아 그 비트를 제거하고 `予定→여정`으로 교체했다.
- 당시 본편 payoff를 한자 장면 하나로 약속하지 않았다. 제목의 넓은 질문은 C23~C26과 C33이 회수한다고 판정했다.

## 12. Step 5 AI 전문 기획 판정

판정: **REVIEW_B 생성 진행 가능. 최종 Step 5 PASS/FAIL은 실제 시청 관측 전 보류.**

| 평가축 | AI 판정 | 근거·REVIEW_B 처리 |
|---|---|---|
| A/B→C 연결 | 유지 | C02의 읽기 출발점, C03/C04의 불완전성, C15의 모순, C23~C26의 서사 이해·반응, C33/C34의 실패·회복·감정이 핵심 C를 누적한다. |
| Promise | 유지 | package A의 `공부하지 않은 20년 + 자막 OFF`와 `글은 약한데 들림?`을 C02/C15/C23이 실제로 회수한다. |
| Opening | 유지 | 1순위 Cold open의 C15→C04→C25는 성공·실패·인물성의 낙차를 만들고 `전체 영화는 어디까지 따라가나`를 남긴다. 세 비트만 짧게 사용한다. |
| Viewer Question | 조건부 유지 | `들리나`→`어떻게 남았나`→`이야기까지 따라가나`→`구멍 뒤 회복하나`로 갱신된다. 초반 진단 사례가 길면 첫 전환이 늦어진다. |
| Escalation | 유지 | 단어/문장 판정에서 C15의 읽기-듣기 모순, C19의 작품 감상, C23~C26의 연속 관계극·반전으로 규모와 감정이 커진다. |
| Variation | 최소 수리 | C03→C04→C05→C07은 모두 남길 기능은 있지만 연속하면 진단 나열 위험이 있다. C05와 C07을 각각 약 20초로 압축한다. |
| Character | 최소 수리 | C09와 C25는 관계 대사에 대한 사용자 캐릭터를 보여주는 기능이 겹치며, C25가 웃음·사건·공유성까지 더 강하다. REVIEW_B에서도 C09/S06을 제외한다. C07·C19·C25·C32·C34로 인물성은 남는다. |
| Payoff | 유지 | C15는 promise proof, C23~C26은 서사 이해가 웃음과 반전으로 바뀌는 본편 payoff다. 역할 분리가 명확하다. |
| Packaging Fit | 유지 | package A가 넓은 질문을 걸고 C02/C15와 C23~C26/C33이 과장 없이 답한다. package B는 사용하지 않는다. |
| Exit Hook | 조건부 유지 | `글자와 정확한 표현을 붙이면?`은 자연스럽지만 설명이 길면 이미 장면으로 생긴 C를 약화한다. REVIEW_B에는 새 나레이션을 만들지 않고 현장 반응으로 닫아 과설명 위험을 분리 관찰한다. |
| 동일 기능 반복 | 최소 수리 | C09 제거, C05/C07 압축. C17은 C03보다 짧은 자가수정 변주라 12초 유지한다. |
| chronology integrity | 유지 | Cold open만 순서 예외. 본편은 남긴 primary source 구간의 원본 순서를 보존한다. |
| 사실 경계 | 유지 | 촬영 provenance는 내부 로그에 보존하되 화면에 자동 표시하지 않는다. 최초가 아닌 장면을 최초라고 주장하지 않고, 후반도 내부 `최초 반응 후보` 이상으로 단정하지 않는다. C34를 청해 성공으로 포장하지 않는다. |
| 장면 간 낙차 | 유지 | 자가수정→오해→성공, 읽기 약점→대사 이해, 웃음→심장 반전, 미이해→회복의 낙차가 존재한다. |
| 시청자 판단 갱신 | 조건부 유지 | 구조상 갱신은 있으나 초반 압축과 C19 이후 payoff 진입의 실제 체감은 rough cut으로 검증해야 한다. |
| 핵심 장면까지 볼 이유 | 유지 | C03/C04의 상반된 실패와 C05/C07의 압축 성공이 C15의 모순을 기다리게 한다. C09를 빼면 핵심 장면 도달이 빨라진다. |

10분 45초가 실제 호흡상 긴지는 문서만으로 확정하지 않는다. REVIEW_B의 실제 길이와 시청자의 첫 이탈 충동 시점을 evidence로 판단한다.

## 13. REVIEW_B 선택 계약

- 당시 34 candidates, 15 final selects, A/B/C, promise proof 1순위, payoff 1순위, 대표 오해, package A, Cold open 1순위·대안, chronology·최초성 경계는 REVIEW_B 선택 계약 안에서 변경하지 않았다.
- REVIEW_B는 REVIEW_A와 동일하게 기존 15 selects 중 **S06/C09만 제외**한다. 더 강한 S11/C25가 동일 character 기능을 수행하고 payoff 사건까지 결합하기 때문이다.
- **S04/C05와 S05/C07은 제외하지 않고 각각 약 20초로 압축**한다. C05는 C04 직후 판단 반전, C07은 언어 판정이 작품 감상으로 넘어가는 기능을 각각 보존한다.
- S01~S05, S07~S13의 재확인과 S14~S15의 내부 `최초 반응 후보` 분류는 이 문서에 보존하되 viewer-facing 영상에는 표시하지 않는다.
- `재확인 촬영`, `재시청`, `재촬영`, `최초 반응 후보`와 source TC overlay를 모두 제거하고 mixed audio 한 스트림만 사용한다. 새 나레이션·음악·효과·밈 편집을 만들지 않는다.
- REVIEW_B는 최종 편집물에 가까운 일반 시청 상태에서 장면 순서·호흡·길이·payoff를 체험하기 위한 artifact이며 repository에 넣지 않는다.

## 14. 사용자 시청 테스트 질문

REVIEW_B를 실제로 본 뒤, 전문 기획 용어 없이 다음 체감만 남긴다.

1. 처음 넘기고 싶었던 정확한 시점은 언제였나?
2. 집중이 확 올라간 정확한 시점은 언제였나?
3. 이해가 안 되거나 설명이 부족하다고 느낀 곳은 어디였나?
4. 반복처럼 느껴진 곳은 어디였나?
5. 가장 기억에 남은 장면은 무엇이었나?
6. 다 보고 난 직후 머리에 남은 한 문장이나 감상은 무엇이었나?
7. 다음 영상이 궁금한가?
8. 이 채널에서 이런 영상을 또 보고 싶은가?

AI는 이 관측을 타임코드와 연결해 viewer question 단절, 동일 기능 반복, payoff 약화, setup 과다, character 부족, promise mismatch 등으로 사후 해석하고 evidence와 PASS/FAIL 권고를 정리한다. 최종 제작 진행 여부는 사용자가 확정한다.
