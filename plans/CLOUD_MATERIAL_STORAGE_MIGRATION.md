# CLOUD_MATERIAL_STORAGE_MIGRATION

상태: COMPLETE — Phase E K-less recovery test PASS; Phase F cutover validation PASS; next action is Phase G production return
승인일: 2026-09-16 KST

## 1. 목적

까막눈의 repository와 external material을 특정 PC, drive letter, 이동식 SSD에 묶지 않는다.

목표 구조:

- GitHub: code, current truth, planning state, logical artifact metadata
- cloud material store: 대용량 source/evidence/review/research bytes의 durable storage
- local material cache: 현재 기기에서 실제 ffmpeg/ASR/render/analysis를 수행하는 disposable workspace
- K: SSD: migration 완료 뒤 optional offline backup

최종 acceptance는 새 기기에서 GitHub checkout과 cloud access만으로 필요한 material을 local cache에 복원하고 검증한 뒤 작업을 이어갈 수 있는 상태다.

이 계획은 video-planning 하네스를 대체하지 않는다. Cloud migration은 EP1 selection rebuild와 이후 하네스 검증을 더 안정적으로 실행하기 위한 지원 인프라 작업이다.

## 2. Phase A snapshot에서 확인된 문제

2026-09-16 Phase A read-only audit에서 다음 historical conditions를 확인했다.

- canonical local repository가 `C:\kkamaknun`으로 고정돼 있다.
- current external material identity가 `K:\kkamaknun\...` 절대경로와 결합돼 있다.
- 같은 physical path가 AGENTS.md, STATE.md, tools/harness/STATE.json, FIRST_VIDEO.md, EP1 lock, PLANNING_RESULTS.md 등에 반복된다.
- repository-resident EP1 processing code가 K:를 직접 여는 hidden dependency는 발견되지 않았다.
- `K:\kkamaknun\repo`는 active worktree/remote가 아니라 historical transport copy다.
- Scene Collector code는 pathlib/config 기반이지만 macOS native UI는 검증되지 않았다.
- System Evaluation 문서의 실행 예시는 Windows 중심이며 macOS 실행은 별도 검증 범위다.

따라서 핵심 결함은 media-processing code보다 current-truth/runtime contract가 physical location을 identity처럼 소유하는 데 있다.

## 3. 설계 원칙

### 3.1 repository root

repository의 의미는 checkout 위치와 분리한다.

- current truth의 canonical sync source는 GitHub다.
- `C:\kkamaknun`, `~/work/kkamaknun` 같은 실제 checkout 위치는 machine-local detail이다.
- repo 내부 instruction/runtime은 특정 drive letter를 repository identity로 사용하지 않는다.

### 3.2 external artifact identity

external artifact는 physical path가 아니라 logical artifact ID로 식별한다.

예:

- `ep1.primary_recording`
- `ep1.source_subtitles_ko`
- `ep1.desktop_transcript`
- `ep1.mic_transcript`
- `ep1.sync_timeline_jsonl`
- `ep1.review_b`
- `ep1.review_c`

logical ID는 provider나 local path가 바뀌어도 유지한다.

현재 한 편의 active bundle만 있으므로 별도 permanent asset-manifest owner는 만들지 않는다. Cutover 시 runtime owner인 `tools/harness/STATE.json`에 최소 artifact registry를 두고, 규모가 커져 독립 version/lifecycle owner가 실제로 필요해질 때만 manifest 분리를 재검토한다.

### 3.3 cloud material store

repo core contract는 Google Drive라는 제품명에 종속하지 않는다.

- core contract: authenticated cloud material store
- 초기 구현: rclone-compatible remote
- 첫 provider: Google Drive
- provider credential과 rclone config는 machine-local secret/config이며 Git에 넣지 않는다.

### 3.4 local cache

실제 media processing은 cloud-mounted placeholder가 아니라 완전히 materialize된 local file에서 수행한다.

local cache 위치는 `KKAMAKNUN_MATERIAL_ROOT` 환경변수로 주입한다.
cloud remote root는 `KKAMAKNUN_MATERIAL_REMOTE` 환경변수로 주입한다.

둘 다 current truth가 아니며 Git에 commit하지 않는다.

### 3.5 source와 derived artifact

- source: immutable 취급. 같은 logical ID를 다른 bytes로 조용히 덮어쓰지 않는다.
- transcription/evidence: source provenance를 보존한다.
- review/render: 재생성 가능하지만 durable output만 publish한다.
- temporary render/cache/download state는 cloud durable storage나 Git에 남기지 않는다.

## 4. 전환 단계

### Phase A — dependency audit

완료.

active dependency, historical provenance, fixture/example을 분리했고 결과는 `SAFE_TO_DESIGN`이다.

### Phase B — preparation (complete)

이 계획과 최소 cross-platform material helper를 repository에 추가한다.

At that stage, the current K: path contract was not yet cut over and the Google Drive upload was not authoritative.

목적은 다음 단계에서 copy-first migration과 검증을 안전하게 실행할 도구·경계를 준비하는 것이다.

### Phase C — cloud bootstrap / copy-first migration

**PASS (2026-09-16).** rclone `v1.75.1` copied 146 files to the cloud material hierarchy (source 3, transcription 141, review 2), totaling 5,639,409,226 bytes. Hierarchy/count/total-size matched; source/transcription/review `rclone check` passed. The primary recording round-tripped to a clean local cache with SHA-256 `7847fbeebd3db7dd94141f332fd80fa11e0620ed23b58789898b6485cfefd525`. K originals were not deleted, moved, or renamed; no credential contamination was found.

local 실행 환경에서:

1. rclone 설치/확인
2. Google Drive remote 구성
3. provider credential이 repo 밖에 있는지 확인
4. cloud root 생성
5. K current material을 relative hierarchy를 보존해 cloud로 copy
6. copy 결과 검증
7. K 원본은 삭제하지 않고 rollback source로 유지

초기 cloud hierarchy는 migration 비용을 낮추기 위해 현재 K root의 relative path를 유지한다.

```text
source/ep1/...
transcription/...
review/...
```

### Phase D — logical-ID cutover

**Complete (2026-09-16).** Runtime registry ownership remains in `tools/harness/STATE.json`; active instruction/current-state/runtime references use logical artifact IDs, and the material helper resolves those IDs through local environment configuration.

cloud round-trip이 검증된 뒤에만 instruction/current-truth/runtime owner를 통합 리팩터링한다.

반드시 함께 검토·수정:

- AGENTS.md
- STATE.md
- tools/harness/STATE.json
- FIRST_VIDEO.md
- tools/harness/EP1_LOCK.json
- materials/ep1_main/PLANNING_RESULTS.md
- 현재 실행에 실제로 영향을 주는 plan/config/reference

원칙:

- active `C:\kkamaknun` repository dependency 제거
- active `K:\...` material dependency 제거
- current runtime은 logical artifact ID를 사용
- physical cloud/local resolution은 local config/helper가 담당
- historical `C:\OBS`, J:, 과거 K path는 provenance로 명확히 표시된 경우 보존 가능
- plans/history에 남은 과거 path를 current runtime truth로 승격하지 않음

instruction/config/workflow 변경은 부분 패치하지 않고 관련 owner·중복·stale reference를 한 번에 정리한다.

### Phase E — K-less recovery test

**PASS (2026-09-16).** K:가 물리적으로 분리된 상태에서 첫 clean cache와 두 번째 clean cache를 사용했다. `ep1.primary_recording`을 cloud에서 materialize해 size `5,065,619,726` 및 SHA-256 `7847fbeebd3db7dd94141f332fd80fa11e0620ed23b58789898b6485cfefd525`를 확인했고, ffprobe와 start/middle/end decode를 통과했다. 필요한 evidence logical artifact도 materialize했다. 5초 H.264/AAC probe (`3,340,960` bytes, SHA-256 `3c9f3452e6b27bb2a3cf1081baa6f4749df212af19e843df41cc49db72e86777`)를 `migration_validation/phase_e/005d74f1/probe.mp4`에 publish한 뒤 두 번째 clean cache에 rematerialize해 SHA 일치를 확인했다. credential contamination은 0이었다.

K:를 사용하지 않는 상태에서:

1. 빈 local material cache 준비
2. current repo checkout
3. cloud remote 인증
4. EP1 primary source materialize
5. integrity validation
6. ffprobe/read access 확인
7. 필요한 evidence materialize
8. 작은 derived artifact 생성
9. cloud publish
10. 다른 빈 local 위치에 다시 materialize해 동일성 확인

K:를 current execution dependency로 사용하지 않는 recovery가 검증됐다. K SSD는 optional offline backup으로만 보존한다.

### Phase F — cutover validation

**PASS (2026-09-16).** Active current-state/runtime/instruction contract에서 K: hard dependency, `C:\kkamaknun` hard dependency, checkout drive-letter dependency는 모두 0이다. historical provenance와 example은 active dependency가 아니다. JSON/YAML/Python parse, material helper unit tests·registry resolution·source publish protection, video-planning deterministic validator regression, `git diff --check`, credential scan을 통과했다. Phase E cache primary SHA와 derived probe 두 copy SHA를 재검증했고 published probe object 존재도 확인했다.

- active current source에서 K: hard dependency 0
- active current source에서 C:\kkamaknun hard dependency 0
- repo 안에 provider credential/token 0
- JSON/YAML/Python parse PASS
- material helper test PASS
- current video-planning validator regression PASS
- final ref/reference scan PASS

### Phase G — production return (next action)

migration을 별도 플랫폼 프로젝트로 확장하지 않는다.
cutover 완료 후 즉시 EP1 selection/compression contract와 original-source rescan으로 복귀한다.

이 migration 완료는 Google Drive를 영구 provider로 lock하거나 macOS 전체 workflow를 실기 검증했다는 뜻이 아니며, EP1 production 완료·REVIEW_C failure 해결·video-planning 최종 PASS도 뜻하지 않는다.

## 5. rclone 사용 경계

rclone은 storage transport adapter다. current truth owner가 아니다.

환경변수:

- `KKAMAKNUN_MATERIAL_ROOT`: 현재 기기의 local material cache root
- `KKAMAKNUN_MATERIAL_REMOTE`: rclone remote root. 예: `remote:kkamaknun_external`
- `KKAMAKNUN_RCLONE`: 필요할 때 rclone executable override

`rclone.conf`, OAuth token, client secret, service-account credential은 repo 밖에서 관리한다.

2026년 현재 rclone의 shared Google client ID는 retirement 중이므로 Google Drive를 실제 구성할 때는 사용자 소유 OAuth client ID 사용을 우선한다. 이 외부 도구 사실은 구현 시 최신 공식 문서를 다시 확인한다.

## 6. migration 중 안전 규칙

- K source를 먼저 삭제하거나 이동하지 않는다.
- source bytes를 Git repository 안으로 복사하지 않는다.
- cloud URL 자체를 logical artifact identity로 사용하지 않는다.
- local cache가 존재한다는 이유만으로 cloud publish 성공으로 간주하지 않는다.
- checksum/size가 알려진 artifact는 local verify를 우선한다.
- identity checksum이 아직 없는 source는 cutover 전에 계산·기록 방식을 확정한다.
- credential 값은 로그, plan, commit, ChatGPT 답변에 기록하지 않는다.

## 7. 완료 정의

다음 상태가 모두 참일 때 migration 완료다.

- 특정 PC가 없어도 project state를 GitHub에서 복원할 수 있다.
- 특정 K: SSD가 없어도 current external material을 cloud에서 복원할 수 있다.
- Windows drive letter가 runtime contract가 아니다.
- macOS에서도 같은 logical artifact contract를 사용할 수 있다.
- local cache는 지워도 다시 만들 수 있다.
- K:는 optional offline backup이다.
- video-planning 하네스의 current truth와 EP1 production state가 migration 과정에서 손실되지 않았다.
