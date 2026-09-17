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

## Immediate next action — transcription only

다음 실행은 **재전사 하나만** 한다.

1. primary recording에서 `audio stream 2 = desktop/source`와 `audio stream 3 = mic/user`를 서로 분리한다.
2. `audio stream 1 = mixed`는 재전사 입력으로 사용하지 않는다. provider가 multi-channel/stream audio를 합쳐 버리는 경로에도 의존하지 않는다.
3. 두 raw track을 각각 deterministic chunk로 나눈다. chunk는 current official Gemini API의 file/request 제한 안에 들어가야 하며 primary recording의 absolute start/end를 보존한다.
4. Gemini에는 해당 raw audio chunk와 전사 지시만 준다. 한국어 source subtitle, A/B, `FIRST_VIDEO.md`, 기존 transcript/sync/narrative/candidate/selection/pilot/UAT는 입력하지 않는다.
5. 각 chunk가 검증되는 즉시 `track`, absolute start/end, input SHA-256, model, prompt/config hash, raw response, normalized transcript, validation, next unit을 checkpoint한다.
6. 중단 후 재실행하면 verified checkpoint를 재호출하지 않고 마지막 미완료 unit부터 resume한다. API/network/quota/credential 실패를 기존 derived 자료 fallback으로 메우지 않는다.
7. 두 track 전체 범위, chunk merge의 누락·중복·순서, 완료 manifest를 검증한 뒤 **STOP**한다.

이 실행에서는 source narrative 분석, AV 해석, scene selection, RETAIN/BRIDGE/DROP, 편집 판단, pilot 생성을 하지 않는다. 재전사 run이 검증된 뒤에만 **별도 실행**으로 Gemini 분석을 시작한다.

구체적인 provider API 제한·지원 형식은 실행 직전 current official Gemini 문서를 다시 확인한다. 현재 repo에는 변할 수 있는 외부 서비스 숫자를 장기 상수로 잠그지 않는다.

## Owner pointers

- common executable planning process: `tools/harness/PIPELINE.yaml`
- EP1 stable facts·clean-room boundary: `FIRST_VIDEO.md`
- EP1 current planning results: `materials/ep1_main/PLANNING_RESULTS.md`
- runtime route·raw artifact registry·현재 clean-room run contract: `tools/harness/STATE.json`
- deterministic EP1 projection: `tools/harness/EP1_LOCK.json`
- long-lived judgment principles: `PLAYBOOK.md`

## Other workstreams

Cloud material storage, Scene Collector, System Evaluation 등 EP1 clean-room restart와 무관한 workstream의 기존 current truth는 이번 reset으로 변경하지 않는다.

현재 상태 질문은 이 파일을 기준으로 답하고, EP1 세부 사실은 위 owner로 이동해 확인한다.
