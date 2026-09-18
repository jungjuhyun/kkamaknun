# STATE.md — 현재 상태

기준 시각: 2026-09-18 KST

## Active focus

EP1은 기존 파생 전사·동기화·서사 맵·scene candidate·selection·pilot·UAT 판단을 current truth에서 걷어낸 **raw-material-only clean-room restart** 상태다.

공통 video-planning harness와 `material_first` 경로는 유지한다. 기존 EP1 파생 산출물은 Git history나 external store에 남아 있을 수 있지만, 새 전사·분석의 입력이나 current evidence로 사용하지 않는다.

현재 runtime route는 `tools/harness/STATE.json`의 `video_planning / EP1 / material_first / tools/harness/EP1_LOCK.json`이다.

## 사용자 확정 방향

- 기존 EP1 derived transcript/sync/narrative/candidate/RETAIN·BRIDGE·DROP/pilot/UAT 결과는 새 분석의 기준으로 신뢰하지 않는다.
- `ep1.primary_recording`에서 Gemini API로 **재전사부터 다시 시작**한다.
- 재전사와 분석은 같은 실행에 묶지 않는다.
- 장시간 실행은 사용자가 걸어두고 자는 상황을 기본으로 보고, 각 검증 완료 unit을 checkpoint해서 마지막 완료 지점부터 resume할 수 있어야 한다.
- 새 clean-room 결과가 나오기 전에는 기존 scene/narrative ID, old narrative map, old scene pool, old pilot 구성으로 수렴하지 않는다.
- 재전사 완료 후 별도 실행에서는 **Gemini 3.8 Flash가 실제 재료 선별과 영상 편집 판단을 소유**한다. current repo의 A/B→C·source narrative·핵심 장면·boundary·Opening·payoff 등 방법론은 Gemini 판단 기준으로 전달하지만, retired GPT EP1 구체적 답안은 전달하지 않는다.
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
  - 현재 **재전사 run에는 넣지 않는다**. 이후 독립 분석 단계에서 필요할 때만 raw source로 검토한다.

## Current planning state

현재 C, packaging, Opening, Viewer Question, narrative spine, candidate, boundary, RETAIN/BRIDGE/DROP, body lock, Cold open, pilot, rough cut에 대한 current 결정은 **없다**.

`materials/ep1_main/PLANNING_RESULTS.md`는 reset 상태이며 새 clean-room 결과 전에는 planning decision을 기록하지 않는다.

## Gemini retranscription runner

재전사 실행기는 `tools/harness/gemini_transcribe.py`에 준비되어 있다. 이 구현이 생겼다고 해서 전사가 완료된 것은 아니며, 현재 transcript는 여전히 **미생성 / 미검증** 상태다.

2026-09-18 current official Gemini docs를 기준으로 Run 1은 전용 `gemini-3.5-transcribe`를 Files API + Interactions API로 사용한다. 이 전용 모델은 당시 Batch API를 지원하지 않으므로 generic Gemini Batch를 기본 경로로 채택하지 않았다. generic audio-understanding 경로는 multi-channel audio를 single channel로 합치므로 stream 2/3 분리 계약을 대신할 수 없다.

전사는 `verbatim`이 기본이다. word-level timestamp는 정확도를 낮출 수 있다는 provider 경고가 있으므로 기본값은 off다. 기본 chunk core는 겹치지 않으며, overlap을 켤 경우에만 word timestamp를 함께 사용해 각 word를 하나의 core interval에 결정론적으로 귀속한다. provider의 model/limit/support는 paid 실행 직전에 official docs로 다시 확인한다.

runner는 기존 `durable_media.py`의 journal/lease/object-store를 재사용한다. Gemini 응답이 돌아오면 normalized checkpoint보다 먼저 raw response를 durable store에 기록한다. SDK 자동 retry는 끄고, 각 paid Interactions API submit 직전에 `REQUEST_INTENT`를 먼저 durable하게 기록한다. response 없이 프로세스가 사라진 unit이나 수락 여부를 확정할 수 없는 실패는 자동 재호출하지 않아 이중 과금 가능성을 보수적으로 차단한다.

## Immediate next action — transcription only

다음 실행은 **재전사 하나만** 한다.

1. 로컬에서 최신 feature branch와 `ep1.primary_recording` identity를 확인하고 `tools/harness/requirements_gemini.txt`의 runtime dependency를 준비한다.
2. runner의 `plan` 경로로 source SHA/size, stream 2/3, deterministic chunk plan과 absolute coverage를 검증한다.
3. full run과 같은 config에서 `--max-new-units 2`로 **첫 두 planned unit만** 소규모 paid preflight를 실행한다. unit은 segment별로 stream 2/3이 교차되므로 두 track의 실제 upload → transcription → raw-response save → verified checkpoint 경로를 각각 확인한다. 이미 두 unit이 verified/reused여도 cap 밖 unit으로 전진하지 않는다.
4. preflight가 `PAUSED` 상태로 정상 종료되면 같은 run/config를 cap 없이 다시 실행해 verified unit을 재호출하지 않고 나머지를 resume한다.
5. 각 chunk가 검증되는 즉시 `track`, absolute start/end, input SHA-256, model, prompt/config hash, raw response, normalized transcript, validation, next unit을 checkpoint한다.
6. `audio stream 1 = mixed`, 한국어 source subtitle, A/B, `FIRST_VIDEO.md`, 기존 transcript/sync/narrative/candidate/selection/pilot/UAT는 Gemini 입력으로 사용하지 않는다.
7. 두 track 전체 범위, chunk merge의 누락·중복·순서, 완료 manifest와 marker를 검증한 뒤 **STOP**한다.

이 실행에서는 source narrative 분석, AV 해석, scene selection, RETAIN/BRIDGE/DROP, 편집 판단, pilot 생성을 하지 않는다. 재전사 run이 검증된 뒤에만 **별도 실행**으로 Gemini 3.8 Flash 분석·재료 선별·편집 판단을 시작한다.

구체적인 provider API 제한·지원 형식은 paid 실행 직전 current official Gemini 문서를 다시 확인한다. 현재 repo에는 변할 수 있는 외부 서비스 숫자를 장기 상수로 잠그지 않는다.

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
