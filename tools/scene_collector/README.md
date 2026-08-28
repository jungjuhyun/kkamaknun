# 애니 표현 장면 수집기

한국어로 찾고 싶은 뜻에서 출발해 실제 애니 표현 장면을 수집하기 위한 Windows 로컬 도구다.

현재 브랜치에는 **작업 0 — 개발 골격**부터 **작업 9 — 화면 기술 확인**까지 완료되어 있다. Nadeshiko 공식 exact-match와 로컬 표면형 검증을 연결해 실제 원문에 같은 표현이 있는 segment만 남기고, 검색·검수 상태와 외부 요청 캐시를 작업 데이터 위치의 SQLite DB에 저장한다. 사용자 선호 작품은 Nadeshiko public ID 기준으로 관리하며, DB가 연결된 제품 검색은 활성 선호작만 공식 media filter로 검색한다. 정확 후보 장면에는 앞뒤 문맥을 조회해 AI가 직접 의미·자연스러운 한국어·장면 쓰임을 구조화 반환하고 재시작 후 재사용한다. 화면 기술은 Windows 실측 비교로 **NiceGUI(native mode)**를 선택했고, 실제 제품 화면(Task 10)은 아직 없다.

## 개발 환경

- Python 3.11 이상
- [uv](https://docs.astral.sh/uv/)

`tools/scene_collector`에서 다음 명령을 실행한다.

```text
uv sync
uv run pytest
uv run ruff check .
```

## 로컬 설정

`settings.example.toml`을 복사해 `settings.toml`을 만들고 다음 필수값을 입력한다.

- `storage.work_data_dir`: 사용자가 지정한 기존 작업 데이터 디렉터리의 절대경로
- `ai.service`: 사용할 AI 서비스 식별자
- `ai.model`: 사용할 모델 식별자
- `search.candidate_count`: AI가 생성할 후보 수, 3~5
- `search.nadeshiko_take`: 후보 하나당 Nadeshiko 조회량, 1~20

기본 설정 파일 위치는 프로그램을 실행하는 현재 디렉터리의 `settings.toml`이다. 다른 위치를 사용할 때는 `load_settings()`에 경로를 전달한다.

```python
from pathlib import Path

from scene_collector.config import load_settings

settings = load_settings(Path("settings.toml"))
```

비밀정보는 `settings.toml`에 넣지 않는다. `.env.example`을 참고해 `settings.toml`과 같은 디렉터리에 `.env`를 만들고 `NADESHIKO_API_KEY`를 입력한다. 운영체제 환경변수에 같은 이름이 있으면 `.env` 값보다 우선한다. 설정과 비밀 파일은 저장소에 커밋하지 않는다.

비어 있는 필수값, 문자열이 아닌 AI 설정, 존재하지 않거나 디렉터리가 아닌 작업 데이터 위치는 설정 오류로 거부한다.

## Nadeshiko 연결

[공식 Python SDK](https://github.com/BrigadaSOS/nadeshiko-sdk-python)를 사용한다. `create_nadeshiko_client()`는 작업 1에서 검증한 설정의 `NADESHIKO_API_KEY`를 공식 SDK에 전달하는 역할만 하며, HTTP 통신·인증·재시도·페이지 순회·오류처리를 다시 구현하지 않는다.

일반 자동시험은 실제 계정이나 인터넷을 사용하지 않는다. `uv run pytest`에서는 `nadeshiko_live` 시험이 항상 건너뛰어진다.

실제 연결 시험은 API 사용량이 발생하므로 다음처럼 명시적으로 실행한다. 키를 운영체제 환경변수로 설정했다면 두 번째 줄은 생략한다. `.env`는 저장소에 커밋하지 않는다.

```powershell
$env:SCENE_COLLECTOR_NADESHIKO_ENV_FILE = (Resolve-Path ".env").Path
uv run pytest --run-nadeshiko-live -m nadeshiko_live -ra
```

기본 시험 검색어는 `大丈夫`다. 실제 corpus에서 결과가 없을 때만 `SCENE_COLLECTOR_NADESHIKO_LIVE_QUERY` 환경변수로 바꾼다. 실제 연결 시험은 인증, `get_me` 사용자·사용량, 작품 목록과 단건 조회, 대사 검색, `iter_search` 페이지 순회, 앞뒤 문맥, image/audio/video URL을 확인한다. `get_me` 확인에는 API 키의 `READ_PROFILE` 권한이 필요하다. 응답 본문·사용자명·API 키는 출력하거나 저장하지 않는다.

## AI 연결

[Instructor의 현재 통합 인터페이스](https://python.useinstructor.com/concepts/from_provider/)를 사용한다. OpenAI 지원은 Instructor 기본 설치에 포함되고, Google은 현재 권장 SDK용 `instructor[google-genai]` extra로 설치한다. `create_ai_client()`는 설정의 `ai.service`와 `ai.model`을 `service/model` 문자열로 합쳐 `instructor.from_provider()`에 전달한다. 구조화 출력은 provider와 무관하게 같은 `client.create(..., response_model=...)` 호출을 사용한다. 별도의 provider 추상화나 provider별 애플리케이션 로직은 두지 않는다.

일반 자동시험은 fake client로 설정 연결과 Pydantic 검증만 확인하므로 인터넷이나 API 키가 필요하지 않고 비용도 발생하지 않는다. 실제 연결 시험은 다음 환경변수가 모두 있을 때만 명시적으로 실행한다.

- `OPENAI_API_KEY`
- `GOOGLE_API_KEY`
- `SCENE_COLLECTOR_AI_LIVE_OPENAI_MODEL`
- `SCENE_COLLECTOR_AI_LIVE_GOOGLE_MODEL`

API 키는 `settings.toml`에 넣지 않는다. 운영체제 환경변수 또는 저장소에 커밋하지 않는 로컬 비밀 파일에서 현재 셸로 읽는다. 실제 키와 응답은 시험 fixture로 저장하지 않는다. 모델명은 Python 코드에 고정하지 않고 live 시험 실행 시 환경변수로 받아 임시 `settings.toml`에 기록한다.

2026-08-27 실제 연결 검증에 사용한 모델의 실행 예시는 다음과 같다. 실제 실행 전 각 provider 공식 문서에서 모델의 현재 사용 가능 여부를 다시 확인한다.

```powershell
$env:SCENE_COLLECTOR_AI_LIVE_OPENAI_MODEL = "gpt-5.4-nano"
$env:SCENE_COLLECTOR_AI_LIVE_GOOGLE_MODEL = "gemini-3.6-flash"
uv run pytest --run-ai-live -m ai_live -ra
```

실제 live 시험에서 OpenAI `gpt-5.4-nano`와 Google `gemini-3.6-flash`가 모두 같은 중립 프롬프트에 대해 `text: str`, `number: int`인 `ConnectivityProbe` Pydantic 자료형을 반환했다. 두 provider 모두 실제 호출과 자료형 검증에 성공해 작업 3은 PASS다. 이번 환경에서는 `gemini-2.5-flash` 호출이 404를 반환해 `gemini-3.6-flash`로 실제 검증했다.

## 한국어 표현 찾기

`search_expressions()`는 한국어 의도를 기존 Instructor 구조화 출력 경로에 전달해 `ExpressionCandidate` 3~5개를 받고, 일본어 문자열의 중복만 순서대로 제거한 뒤 공식 SDK로 각 후보를 일반 검색한다. 일반 검색 응답에서 로컬 표면형을 찾지 못한 경우에만 `SearchQuery(search=..., exact_match=True)`로 한 번 더 회수한다. 공식 exact 검색이 실제 동일표현을 놓치는 사례가 있어 일반 검색의 정상 결과를 대체하지 않는다. 두 경로 모두 반환 원문을 같은 로컬 검사에 통과시키며, 최종 `exact_segments`가 0개인 후보는 `corpus_backed_candidates`에서 제외한다. 일반 SDK 원본 `SearchResponse`와 실행한 경우의 `exact_match_response`는 검토용으로 유지한다.

로컬 검사는 다음 차이만 완화한다.

- `unicodedata.normalize("NFKC", ...)`에 따른 Unicode 호환·전각/반각 차이
- 원문의 불필요한 Unicode 공백
- 표현 끝의 `?`, `!`, `.`, `。` 문장부호

내부 문장부호와 활용형은 지우지 않는다. 응답에 Nadeshiko top-level token이 있으면 원문의 token 시작·끝 위치를 표현 경계의 보조 자료로 사용한다. 따라서 독립 token인 `悪い` 뒤에 다른 말이 이어지는 문장은 허용하면서도, `気持ち悪い` compound token 안의 `悪い`는 통과시키지 않는다. 문장부호 없이 바로 다음 token이 이어질 때는 매치 구간 자체가 하나의 top-level token인 경우만 허용해, 여러 token으로 된 표현에 문법 suffix가 덧붙은 결과를 보수적으로 제외한다. token이 없는 응답의 짧은 표면형은 복합어 내부 일치를 피하도록 보수적으로 판정한다. `ほんとそれ`도 `ほんと? それって...`에 걸리지 않는다.

한자/가나 표기 차이는 자동 변환하지 않는다. `matches_surface()`의 `allowed_surfaces`에 검증한 가나 표기를 명시한 경우에만 허용한다. AI가 생성한 `ExpressionCandidate.reading`은 정확한 허용 표기라고 보장할 수 없으므로 자동 연결하지 않는다.

영어 fallback과 앞뒤 문맥 조회는 아직 하지 않는다.

일반 `uv run pytest`는 AI와 Nadeshiko를 fake로 대체한다. 실제 10개 한국어 의도 품질 평가는 루트 `.env`에서 `GOOGLE_API_KEY`와 `NADESHIKO_API_KEY`만 현재 셸에 로드한 뒤 명시적으로 실행한다. 키 값과 `.env` 내용은 출력하거나 저장하지 않는다.

```powershell
$env:SCENE_COLLECTOR_SEARCH_LIVE_SERVICE = "google"
$env:SCENE_COLLECTOR_SEARCH_LIVE_MODEL = "gemini-3.6-flash"
$env:SCENE_COLLECTOR_SEARCH_LIVE_CANDIDATE_COUNT = "5"
$env:SCENE_COLLECTOR_SEARCH_LIVE_NADESHIKO_TAKE = "5"
$env:SCENE_COLLECTOR_SEARCH_LIVE_REPORT = (Join-Path $env:TEMP "scene-collector-search-live.json")
uv run pytest --run-search-live -m search_live -ra
```

평가 입력은 `tests/fixtures/search_live_intents.json`에 둔다. 보고서에는 후보 자료형, 검색 결과 유무, 첫 일본어·영어 대사, fetch 수와 `has_more`만 기록하며 API 키·사용자 정보·segment/media ID는 넣지 않는다.

## 정확 동일표현 live 비교

작업 5의 실제 비교는 AI를 호출하지 않고 고정 일본어 target 6개만 사용한다. target마다 Nadeshiko 일반 검색과 `exact_match=True`를 한 번씩 호출하고, 두 응답의 로컬 표면형 수와 실제 파이프라인이 선택할 최종 수를 비교한다.

```powershell
$env:SCENE_COLLECTOR_SURFACE_LIVE_REPORT = (Join-Path $env:TEMP "scene-collector-surface-live.json")
uv run pytest --run-surface-live -m surface_live -ra
```

보고서에는 fetch 수·추정 전체 수·token 제공 수, 제거된 대표 원문과 채택된 대표 원문만 기록한다. API 키·사용자 정보·segment/media ID는 기록하지 않는다. 일반 `uv run pytest`에서는 이 시험이 항상 건너뛰어진다.

## 선호 작품 관리

작품 이름 문자열이 아니라 Nadeshiko public media ID를 내부 식별자로 저장한다. `display_name`은 사람에게 보여주기 위한 metadata일 뿐이므로 작품명이 바뀌어도 로컬 선택은 깨지지 않는다.

- `media.search_media(client, "작품명")`은 공식 SDK의 `search_media` endpoint로 public ID와 표시명 후보(`MediaSummary`)를 가져온다. 전체 corpus를 받아 로컬에서 문자열 검색하지 않는다.
- `media.store_media(database, media)`는 검색·조회 결과의 public ID와 표시명을 `media` table에 upsert한다. 같은 public ID는 중복 row를 만들지 않고, 표시명은 `name_ja → name_romaji → name_en` 순서로 고른다.
- `media.refresh_media_metadata(database, client, media_id)`는 필요한 작품 하나만 공식 `get_media`로 조회해 표시명을 갱신한다. Task 6에서 segment 저장으로 public ID만 있는 row도 이 경로로 표시명을 채운다. 어떤 갱신에서도 사용자 `preference`/`content_group`/`is_active`는 덮어쓰지 않는다.
- `SceneCollectorDatabase`의 `set_media_preference`(nullable 정수, scale 미확정), `set_media_content_group`(임의 문자열 또는 None, 빈 문자열은 None으로 정규화), `set_media_active`, `get_media`/`list_media`/`list_active_media`로 선호작 상태를 관리하고 재시작 후 복원한다.

database를 전달한 제품 검색(`search_expressions(..., database=...)`)은 활성 작품의 public ID를 정렬해 공식 `SearchFilters.media.include` 필터로 한 요청에 전달한다. 비활성 작품은 검색하지 않으며, 활성 작품이 하나도 없으면 전체 corpus로 자동 확대하지 않고 `NoActiveMediaError`를 발생시킨다. database 없이 호출하는 개발용 검색 경로는 기존처럼 전체 corpus를 검색한다. media 조건은 Nadeshiko search cache identity(`conditions`의 정렬된 `media_ids`)에도 포함되므로 다른 활성 작품 조합이나 조건 없는 기존 cache와 섞이지 않는다.

실제 Nadeshiko 작품 metadata·media filter 검증은 API 사용량이 발생하므로 명시적으로 실행한다. 루트 `.env`에서 `NADESHIKO_API_KEY`만 현재 셸에 로드하고 키 값은 출력하지 않는다. AI API 키는 필요 없다.

```powershell
uv run pytest --run-media-live -m media_live -ra
```

이 시험은 공식 `list_media`/`search_media`/`get_media`로 실제 작품 public ID와 표시명을 얻고, temp SQLite DB에 저장한 선호작 상태의 재시작 복원과, 해당 작품으로 필터한 실제 대사 검색(기본 검색어 `大丈夫`, 필요할 때만 `SCENE_COLLECTOR_MEDIA_LIVE_QUERY`로 변경)과 반복 검색의 cache 동작을 확인한다.

## 한국어 장면 번역

`translate.translate_expression_scenes(settings, expression_id, nadeshiko_client=..., database=...)`가 Task 8의 제품 진입점이다. 사용자가 선택한 표현 하나의 정확 surface 장면들만 번역하며, 모든 search run의 모든 후보를 자동 번역하지 않는다.

- 문맥은 이미 DB에 저장된 exact segment에만 공식 `get_segment_context(segment_public_id, take=2)`로 조회한다. 응답 리스트 순서를 믿지 않고 같은 `media_public_id`·같은 `episode` 중 position이 가장 가까운 앞/뒤 장면을 고르며, 첫/마지막 장면의 빈 문맥은 정상 상태다.
- 문맥 원본 응답은 `nadeshiko_context_cache` table에 `(segment_public_id, take)` identity로 저장해 재시작 후에도 같은 조건이면 Nadeshiko를 다시 호출하지 않는다. 깨진 JSON은 cache miss로 처리한다.
- 번역은 기존 `create_structured_response()` 경로와 `SceneTranslationBatch` Pydantic 자료형을 사용한다. 여러 장면을 canonical JSON으로 묶어 한 요청(내부 batch 크기 5)에 보내고, AI가 반환한 scene_key의 중복·누락·알 수 없는 ID를 검증한 뒤에만 저장한다. 배열 순서는 믿지 않는다.
- 지시문 버전은 `scene-translation-v1`이며 Task 6 AI cache를 그대로 재사용한다. 같은 service/model/지시문/입력이면 provider를 다시 호출하지 않는다.
- 번역 결과는 `reviews`의 번역 필드에 AI provenance(service/model/지시문 버전/입력 hash/생성 시각)와 함께 저장된다. `decision`이 NULL이면 번역은 있지만 사용자가 아직 판정하지 않은 상태다. `save_scene_translation()`은 decision/notes를 건드리지 않고, `set_review_decision()`은 번역을 건드리지 않는다. `save_review()`는 번역 필드까지 통째로 다시 쓰는 수동 경로이므로 AI provenance를 비운다.

실제 Nadeshiko 문맥 + AI 번역 검증은 API 사용량이 발생하므로 명시적으로 실행한다. 루트 `.env`에서 `NADESHIKO_API_KEY`와 사용할 provider의 키만 현재 셸에 로드하고 값은 출력하지 않는다.

```powershell
$env:SCENE_COLLECTOR_TRANSLATION_LIVE_SERVICE = "google"
$env:SCENE_COLLECTOR_TRANSLATION_LIVE_MODEL = "gemini-3.6-flash"
$env:SCENE_COLLECTOR_TRANSLATION_LIVE_REPORT = (Join-Path $env:TEMP "scene-collector-translation-live.json")
uv run pytest --run-translation-live -m translation_live -ra
```

이 시험은 실제 장면 2~3개를 한 AI batch로 번역하고, 같은 DB 재실행과 reopen 후 재실행에서 Nadeshiko 문맥·AI 호출이 다시 발생하지 않는 것을 확인한다. 검색어는 기본 `大丈夫`이며 필요할 때만 `SCENE_COLLECTOR_TRANSLATION_LIVE_QUERY`로 바꾼다. 보고서에는 장면 텍스트와 번역만 기록하고 key·사용자 정보·segment/media ID는 넣지 않는다.

## 로컬 저장과 캐시

`SceneCollectorDatabase.open(settings)`는 새 경로 설정을 요구하지 않고 다음 파일을 관리한다.

```text
<storage.work_data_dir>/scene_collector.sqlite3
```

DB에는 `media`, `search_runs`, `expressions`, `segments`, `expression_segments`, `reviews`, `ai_cache`, `nadeshiko_search_cache`, `nadeshiko_context_cache`가 있다. 같은 Nadeshiko segment를 여러 표현과 검색에 연결할 수 있도록 `expression_segments`를 두고, 원본 segment JSON은 한 번만 저장한다. review 판정은 `채택`, `예비`, `제외`이며 판정 전의 AI 번역만 있는 상태는 `decision` NULL로 표현한다.

`search_expressions(..., database=database)`처럼 열린 DB를 전달하면 검색 완료 결과를 한 transaction으로 저장한다. AI cache는 서비스·모델·지시문 버전·실제 입력의 canonical hash가 모두 같은 경우에만 사용하고, JSON을 요청한 Pydantic 자료형으로 다시 검증한다. Nadeshiko cache는 검색 문자열·`exact_match`·`take`·검색 조건을 구분해 SDK의 원본 `SearchResponse`를 저장하며, 복원된 응답에도 현재 로컬 surface matcher를 다시 적용한다.

현재 schema는 `SCHEMA_VERSION = 2`이며 `PRAGMA user_version`으로 확인한다. Task 8에서 `reviews.decision`을 nullable로 바꾸고 번역 provenance column과 `nadeshiko_context_cache`를 추가했다. 기존 v1 파일 DB는 열 때 `backup_before_schema_change()`로 같은 작업 데이터 위치에 `.pre-schema-v1.` 사본을 만든 뒤 한 transaction에서 v2로 migration하며, 실패하면 원본 v1 데이터를 그대로 유지한다. 현재 코드보다 높은 version은 데이터를 변경하지 않고 거부한다. 각 연결에서 foreign key 검사를 명시적으로 켜고, WAL은 활성화하지 않아 SQLite 기본 rollback journal을 유지한다.

작업 6 자동시험은 파일 기반 임시 DB와 fake provider를 사용한다. 일반 `uv run pytest`에서 인터넷이나 실제 AI/Nadeshiko API를 호출하지 않는다.

## 화면 기술 — Task 9 선택 결과

Windows 11 + WebView2 Runtime에서 NiceGUI 3.16.0(native mode)과 pywebview 6.2.1을 같은 조건(같은 영상 목록·같은 창 구성·같은 EdgeChromium/WebView2 backend)의 작은 probe로 실측 비교해 **NiceGUI를 선택**했다.

실측에서 확인된 사실:

- 두 기술 모두 WebView2(EdgeChromium) renderer를 사용했고(user-agent `Edg/151` 확인) 영상 재생 능력 자체는 동일했다. NiceGUI native는 내부적으로 pywebview를 사용한다.
- **Nadeshiko sentence video asset은 "정지 frame 1장 + 대사 audio" 형식의 MP4다.** ffprobe와 frame 픽셀 비교로 확인했다(시간대별 frame이 인코딩 노이즈 수준으로 동일). 따라서 검수 화면에서 Nadeshiko 영상은 정지 화면 + 음성으로 재생되는 것이 정상이며, 움직이는 MP4 재생 검증은 ffmpeg로 생성한 로컬 테스트 영상으로 별도 수행했다.
- NiceGUI는 정지 자산 20개와 움직이는 테스트 MP4 20개 모두에서 순방향/역방향/재방문 100회 이상의 연속 source 전환을 오류·hang 없이 통과했고 사용자가 실제 frame 움직임과 clip별 소리 차이를 확인했다.
- pywebview도 수정판 probe에서 같은 수준으로 동작했지만, 첫 움직이는 영상 시험에서 js_api 객체의 public 속성(창 객체)이 JS로 재귀 노출되는 설계 때문에 실제 "(응답 없음)" hang이 발생했다. 3줄 수정으로 해결되는 문제였으나, Task 10의 다섯 화면을 직접 HTML/JS + bridge로 만들 때 같은 계열의 실수가 반복될 위험과 코드량 증가를 근거로 NiceGUI를 선택했다.

선택하지 않은 pywebview probe 코드와 직접 dependency는 제거했다. pywebview는 `nicegui[native]`의 transitive dependency로만 남는다.

`experiments/ui_probe/`에는 선택된 NiceGUI probe와 실제 Nadeshiko 영상 목록 생성 스크립트를 남겨 둔다. 재실행은 API 사용량이 발생하는 fetch 단계를 포함하므로 명시적으로만 한다.

```powershell
$env:SCENE_COLLECTOR_UI_PROBE_DATA = (Join-Path $env:TEMP "ui_probe_segments.json")
$env:SCENE_COLLECTOR_UI_PROBE_LOG = (Join-Path $env:TEMP "ui_probe.log")
uv run python experiments/ui_probe/fetch_probe_segments.py $env:SCENE_COLLECTOR_UI_PROBE_DATA
uv run python experiments/ui_probe/nicegui_probe.py
```

## 아직 없는 기능

- 영어 검색 fallback
- 사용자 화면
- 영상 저장과 내보내기
