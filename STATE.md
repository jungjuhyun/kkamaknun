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
- 장시간 실행은 사용자가 걸어두고 자는 상황을 기본으로 보고, 중간 결과와 진행 위치를 checkpoint로 남겨 resume 가능해야 한다.
- 새 clean-room 결과가 나오기 전에는 기존 scene/narrative ID, old narrative map, old scene pool, old pilot 구성으로 수렴하지 않는다.

## Raw input headline

현재 active raw input은 다음뿐이다.

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
  - 보존은 하되 새 Gemini 재전사 결과를 미리 정답으로 유도하는 derived evidence로 취급하지 않는다.

## Current planning state

현재 C, packaging, Opening, Viewer Question, narrative spine, candidate, boundary, RETAIN/BRIDGE/DROP, body lock, Cold open, pilot, rough cut에 대한 current 결정은 **없다**.

`materials/ep1_main/PLANNING_RESULTS.md`는 reset 상태이며 새 clean-room 결과 전에는 planning decision을 기록하지 않는다.

## Immediate next action

다음 실행은 하나만 한다.

> Gemini API로 `ep1.primary_recording`을 처음부터 재전사한다. 이 실행에서는 서사 분석, scene selection, 편집 판단, pilot 생성까지 진행하지 않는다. 장시간 무인 실행을 전제로 checkpoint/resume 상태를 저장하고, 재전사 결과와 완료 범위를 검증한 뒤 STOP한다.

재전사 run이 검증된 뒤에만 **별도 실행**으로 Gemini 분석을 시작한다.

## Owner pointers

- common executable planning process: `tools/harness/PIPELINE.yaml`
- EP1 stable facts·clean-room boundary: `FIRST_VIDEO.md`
- EP1 current planning results: `materials/ep1_main/PLANNING_RESULTS.md`
- runtime route·raw artifact registry: `tools/harness/STATE.json`
- deterministic EP1 projection: `tools/harness/EP1_LOCK.json`
- long-lived judgment principles: `PLAYBOOK.md`

## Other workstreams

Cloud material storage, Scene Collector, System Evaluation 등 EP1 clean-room restart와 무관한 workstream의 기존 current truth는 이번 reset으로 변경하지 않는다.

현재 상태 질문은 이 파일을 기준으로 답하고, EP1 세부 사실은 위 owner로 이동해 확인한다.
