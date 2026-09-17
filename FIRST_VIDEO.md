# FIRST_VIDEO.md — EP1 stable facts

## 현재 상태

이 문서는 2026-09-18 clean-room reset 이후 **EP1의 안정적인 사실과 raw-material boundary만** 소유한다.

이전의 전사·동기화·narrative map·candidate·scene ID·RETAIN/BRIDGE/DROP·Opening·packaging·pilot·UAT·rough-cut 판단은 current truth가 아니다. 그런 내용이 Git history나 external artifact에 남아 있더라도 새 Gemini 전사·분석의 입력으로 사용하지 않는다.

## EP1 기본 premise

A:

> 20년 이상 취미로 애니를 봐왔지만 일본어를 제대로 공부해본 적은 없는 사람

B:

> `체인소 맨: 레제편`을 한국어 자막 없이 보고, 자기 귀에 실제로 무엇이 남아 있는지 확인한다.

현재 C, 제목, 썸네일, Opening, Viewer Question, narrative spine, scene candidate, body 구조와 payoff는 **미확정**이다. 새 raw-material 분석 전에 이전 값을 복원하거나 승계하지 않는다.

이 영상은 카타카나 암기 영상으로 고정하지 않는다.

사용자의 안정적인 배경 사실은 `USER_PROFILE.md`를 따른다.

## Primary material truth

현재 primary material logical ID는 `ep1.primary_recording` 한 파일이다.

| 항목 | 확정 내용 |
|---|---|
| object key | `source/ep1/2026-09-06 23-54-01-01.mp4` |
| size | `5,065,619,726` bytes |
| SHA-256 | `7847fbeebd3db7dd94141f332fd80fa11e0620ed23b58789898b6485cfefd525` |
| duration | `6325.0625s` |
| Video stream 0 | source video |
| Audio stream 1 | mixed |
| Audio stream 2 | desktop/source |
| Audio stream 3 | mic/user |

영상은 단일 MP4다. 별도 camera/window 영상 세트가 있다고 가정하지 않는다. 원본의 absolute recording timeline을 기준 시간축으로 사용한다.

## Raw supplemental source

`ep1.source_subtitles_ko`는 raw Korean source-subtitle directory다.

자막은 source narrative를 확인하는 원시 자료로 보존할 수 있지만, 이전 파생 narrative map이나 scene selection을 되살리는 근거로 사용하지 않는다. 자막 TC와 OBS recording TC가 동일하다고 미리 가정하지 않는다.

## Clean-room exclusion boundary

다음 종류의 기존 EP1 파생 결과는 모두 retired 상태이며 새 분석의 입력에서 제외한다.

- desktop/mic transcript
- sync timeline
- narrative map
- transcription QA
- scene pool
- full-rescan/direct-AV checkpoint에서 파생된 candidate 판단
- 기존 scene/narrative ID 체계
- RETAIN / BRIDGE / DROP
- 기존 Opening / Viewer Question / packaging 판단
- review artifact와 pilot 구성
- 기존 UAT를 이용한 scene-level 수정 방향
- 기존 body lock / Cold open / Step 9 판단

필요하면 새 clean-room 전사·분석이 독립적으로 완료된 **이후에만** 과거 결과를 historical comparison 대상으로 열 수 있다. 비교 결과가 새 판단을 자동으로 덮어쓰지는 않는다.

## 현재 실행 경계

현재 EP1 planning result는 비어 있다. 다음 실행과 checkpoint/resume 요구사항은 `STATE.md`와 `tools/harness/STATE.json`이 소유한다.

공통 material-first 절차는 `tools/harness/PIPELINE.yaml`을 따른다.
