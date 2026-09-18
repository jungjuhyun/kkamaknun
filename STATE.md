# STATE.md — 현재 상태

기준 시각: 2026-09-18 KST

## Active focus

EP1은 기존 파생 전사·동기화·서사 맵·scene candidate·selection·pilot·UAT 판단을 current truth에서 걷어낸 **raw-material-only clean-room restart** 상태다.

공통 video-planning harness와 `material_first` 경로는 유지한다. 기존 EP1 파생 산출물은 Git history나 external store에 남아 있을 수 있지만, 새 분석의 입력이나 current evidence로 사용하지 않는다.

현재 runtime route는 `tools/harness/STATE.json`의 `video_planning / EP1 / material_first / tools/harness/EP1_LOCK.json`이다.

## 사용자 확정 방향

- 기존 EP1 derived transcript/sync/narrative/candidate/RETAIN·BRIDGE·DROP/pilot/UAT 결과는 새 분석의 기준으로 신뢰하지 않는다.
- `ep1.primary_recording`에서 Gemini API로 clean-room 재전사를 수행하고, 재전사와 분석은 같은 실행에 묶지 않는다.
- 장시간 실행은 사용자가 걸어두고 자는 상황을 기본으로 보고, 각 검증 완료 unit을 checkpoint해서 마지막 완료 지점부터 resume할 수 있어야 한다.
- 새 clean-room 결과가 나오기 전에는 기존 scene/narrative ID, old narrative map, old scene pool, old pilot 구성으로 수렴하지 않는다.
- 재전사 완료 후 별도 실행에서는 **Gemini 3.8 Flash가 실제 재료 선별과 영상 편집 판단을 소유**한다. current repo의 A/B→C·source narrative·핵심 장면·boundary·Opening·payoff 등 방법론은 planning synthesis 단계에서 Gemini 판단 기준으로 전달하지만, retired GPT EP1 구체적 답안은 전달하지 않는다.
- GPT/harness는 Gemini 판단을 영상 취향으로 재판하지 않고 current truth 전달·provenance/타임코드/형식 검증·Gemini edit plan의 deterministic assembly만 담당한다.
- Gemini가 재료 선별부터 최종 조합까지 판단한 실제 rough cut도 부적합하면 추가 harness/prompt/process 보강으로 구제하지 않고 AI autonomous planning을 종료해 사용자 직접 기획으로 전환한다.

## Raw input headline

현재 active raw source는 다음 두 개만 registry에 남긴다.

- `ep1.primary_recording`
  - object key: `source/ep1/2026-09-06 23-54-01-01.mp4`
  - size: `5,065,619,726` bytes
  - SHA-256: `7847fbeebd3db7dd94141f332fd80fa11e0620ed23b58789898b6485cfefd525`
  - duration: `6325.0625s`
  - video stream 0
  - mixed audio stream 1
  - desktop/source audio stream 2
  - mic/user audio stream 3
- `ep1.source_subtitles_ko`
  - raw Korean source-subtitle directory
  - 재전사에는 사용하지 않았고, 이후 독립 source reconstruction에서 raw source로만 사용할 수 있다.

## Current planning state

현재 C, packaging, Opening, Viewer Question, narrative spine, candidate, boundary, RETAIN/BRIDGE/DROP, body lock, Cold open, pilot, rough cut에 대한 current 결정은 **없다**.

`materials/ep1_main/PLANNING_RESULTS.md`는 reset 상태이며 새 clean-room source reconstruction과 planning synthesis가 완료되기 전에는 planning decision을 기록하지 않는다.

## Gemini retranscription — 완료 보고

2026-09-18 로컬 실행 결과 보고 기준으로 clean-room Gemini 재전사는 completion gate를 통과했다.

- source identity: registry의 size/SHA-256/duration/stream 0–3과 일치
- model/runtime: `gemini-3.5-transcribe`, Files API + Interactions API, verbatim, word timestamp off, overlap 0, SDK automatic retry off
- preflight: 첫 두 planned unit인 stream 2/3 각 1개가 실제 E2E `TRANSCRIBED` + verified 후 `PREFLIGHT_STOP / PAUSED`
- full resume: 첫 두 unit은 `REUSED`, 나머지 14 unit만 새 paid submit
- paid submit: 총 16회
- durable state: `REQUEST_INTENT` 16개, raw response 16개, verified checkpoint 16개
- unresolved `REQUEST_INTENT`: 0
- `AMBIGUOUS`: 0
- verified units: 16/16
- stream 2 coverage: `0–6325.0625s`, PASS
- stream 3 coverage: `0–6325.0625s`, PASS
- gap / duplicate / order: PASS
- completion manifest / marker: 존재하며 로컬 실행에서 검증 통과
- repository working tree: clean

이 완료 상태는 다음 로컬 분석 실행 시작 시 durable completion marker·manifest와 input identity를 다시 읽어 확인한다. marker가 불일치하면 기존 전사를 다시 실행하지 않고 분석을 중단해 artifact lookup/integrity 문제로 분리한다.

## Immediate next action — independent source reconstruction only

다음 실행은 **Gemini 3.8 Flash를 사용한 독립 source reconstruction**이다. 재전사를 다시 하지 않고, 최종 scene selection·편집 조합까지 자동 연쇄하지 않는다.

1. durable transcription completion marker·manifest와 `ep1.primary_recording` identity를 재확인한다.
2. fresh stream 2/3 transcript, `ep1.source_subtitles_ko`, 실제 primary video/audio를 사용해 `PIPELINE.yaml` material-first Step 3의 네 layer를 복원한다.
   - A: source narrative
   - B: desktop/source dialogue/audio
   - C: user mic raw
   - D: visual/nonverbal reaction
3. source narrative는 사건·관계·목표·위험·감정 변화·앞뒤 의존·climax/resolution/emotional closure를 recording absolute TC와 연결한다.
4. visual/nonverbal reaction은 transcript만으로 확정하지 않고 실제 영상의 표정·웃음·침묵·억양·타이밍·몰입으로 확인한다.
5. 네 layer를 absolute TC로 정렬한 synchronized evidence timeline과 uncertainty/provenance를 만든다.
6. 이 독립 reconstruction에는 A/B premise, `FIRST_VIDEO.md`의 planning premise, retired GPT EP1 구체적 답안·candidate·selection·pilot/UAT를 입력하지 않는다.
7. reconstruction이 완결되면 **STOP**한다. scene candidate 경쟁, A/B→C planning synthesis, RETAIN/DROP, Opening/body order, final composition은 다음 별도 실행에서만 시작한다.

그 다음 planning synthesis 실행에서만 current repo owner의 A/B→C·`나라면 왜 보나`·핵심 장면·boundary·Opening·payoff 등 방법론을 Gemini에 투영하고, Gemini가 material selection부터 최종 edit plan까지 판단한다.

## Owner pointers

- common executable planning process: `tools/harness/PIPELINE.yaml`
- EP1 stable facts·clean-room boundary: `FIRST_VIDEO.md`
- EP1 current planning results: `materials/ep1_main/PLANNING_RESULTS.md`
- runtime route·raw artifact registry·현재 clean-room run contract: `tools/harness/STATE.json`
- crash-safe Gemini retranscription execution: `tools/harness/gemini_transcribe.py`
- external media run journal·checkpoint lifecycle: `tools/harness/durable_media.py`
- deterministic EP1 projection: `tools/harness/EP1_LOCK.json`
- long-lived judgment principles: `PLAYBOOK.md`

## Other workstreams

Cloud material storage, Scene Collector, System Evaluation 등 EP1 clean-room restart와 무관한 workstream의 기존 current truth는 이번 reset으로 변경하지 않는다.

현재 상태 질문은 이 파일을 기준으로 답하고, EP1 세부 사실은 위 owner로 이동해 확인한다.
