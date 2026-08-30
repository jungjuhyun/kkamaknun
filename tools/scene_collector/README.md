# 애니 표현 장면 수집기

한국어 의미에서 시작해 저장된 일본어 표현 자산을 보여주고(없으면 AI로 만들어 저장), 사용자가 고른 **의미→표현 관계 하나만** 실제 애니 대사에서 찾아 장면을 검수·내보내는 Windows 로컬 도구다.

검색 응답·문맥 응답은 저장하거나 캐시하지 않는다. DB에는 사용자의 작업 자산만 남는다: 작품 상태, 표현 자산(의미↔표현 관계), 그리고 판정·번역·메모가 실제로 발생한 작업 장면. 화면은 NiceGUI(native mode)이며 영상 플레이어는 하나만 두고 선택한 장면만 로딩한다.

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
- `search.expression_generation_limit`: AI가 한 번에 만들 표현 수의 상한, 1~20 (기본 20, 생략 가능)
- `search.scene_result_limit`: 정확히 같은 표현이 담긴 장면을 화면에 몇 개까지 보여줄지, 1~20 (기본 5, 생략 가능)

옛 `search.candidate_count`와 `search.nadeshiko_take` 키는 의미가 달라져 더 이상 사용하지 않는다. 남아 있어도 오류가 나지는 않지만 값은 승계되지 않으므로 새 이름으로 바꾸는 것을 권장한다. 두 숫자는 설정 탭에서 직접 바꿔 저장할 수도 있다.

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

기본 시험 검색어는 `大丈夫`다. 실제 대사 자료에서 결과가 없을 때만 `SCENE_COLLECTOR_NADESHIKO_LIVE_QUERY` 환경변수로 바꾼다. 실제 연결 시험은 인증, `get_me` 사용자·사용량, 작품 목록과 단건 조회, 대사 검색, `iter_search` 페이지 순회, 앞뒤 문맥, image/audio/video URL을 확인한다. `get_me` 확인에는 API 키의 `READ_PROFILE` 권한이 필요하다. 응답 본문·사용자명·API 키는 출력하거나 저장하지 않는다.

## AI 연결

[Instructor의 현재 통합 인터페이스](https://python.useinstructor.com/concepts/from_provider/)를 사용한다. OpenAI 지원은 Instructor 기본 설치에 포함되고, Google은 현재 권장 SDK용 `instructor[google-genai]` extra로 설치한다. `create_ai_client()`는 설정의 `ai.service`와 `ai.model`을 `service/model` 문자열로 합쳐 `instructor.from_provider()`에 전달한다. 구조화 출력은 provider와 무관하게 같은 `client.create(..., response_model=...)` 호출을 사용한다. 별도의 provider 추상화나 provider별 애플리케이션 로직은 두지 않는다.

provider나 Instructor가 내는 예외는 종류가 제각각이고 표준 예외 계층 밖에 있을 때도 있어서, 그대로 두면 화면의 오류 처리에 걸리지 않고 진행 표시가 멈춘 채로 남는다. `create_structured_response()`는 이런 실패를 `AIError`(RuntimeError) 하나로 바꿔 화면이 항상 사용자에게 알릴 수 있게 한다. 오류 메시지에는 예외 종류만 담고, 모델의 원본 응답이 실려 있을 수 있는 원문은 `__cause__`로만 남긴다.

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

## 한국어 의미 → 일본어 표현 자산

한국어 의미는 먼저 DB에서 조회한다. `search.find_saved_expressions(database, "괜찮아요")`가 저장된 표현을 돌려주면 **AI를 호출하지 않는다.** 의미는 NFKC·공백 정리·끝 문장부호 제거까지만 정규화(`database.normalize_korean_meaning`)해 조회 키로 쓰고, 화면에는 처음 입력한 원문을 보여준다.

저장된 표현이 하나도 없으면 같은 동작 안에서 `search.generate_expressions(settings, "괜찮아요", database=database)`가 AI를 한 번 호출한다. 사용자가 버튼을 한 번 더 누를 필요는 없다. 화면에서 이 두 단계를 묶은 진입점이 `ui_controller.lookup_or_generate_expressions()`이며, 저장된 표현이 있었는지는 결과의 `used_ai`로 구분한다. 이미 표현이 있는 의미에 더 붙이고 싶을 때만 사용자가 [표현 더 찾기]로 추가 생성을 요청한다.

프롬프트는 "실제 회화에서 자연스럽게 쓰는 서로 다른 표현을 가능한 한 폭넓게, 최대 `expression_generation_limit`(기본 20)개까지, 자연스러운 표현이 적으면 억지로 채우지 말 것"을 요구하고, 이미 저장된 표현이 있으면 그 목록을 함께 전달해 중복을 피한다. 반환 결과 중 기존 표현과 겹치는 항목은 저장하지 않는다. **더 붙일 자연스러운 표현이 없으면 AI가 빈 목록을 돌려주는 것도 정상 결과다.** 이때는 오류가 아니라 "새 표현 0개"로 표시하고 기존 표현은 그대로 둔다.

표현 카드에는 일본어와 한글 독음만 보여준다(예: `大丈夫です : 다이죠부데스`). 저장된 가나 읽기를 그때그때 바꿔 보여주는 것이라 AI를 다시 부르지 않고 DB 값도 그대로다. 국립국어원 외래어 표기법이 아니라 학습자가 소리를 짐작할 수 있는 표기를 쓴다. 형태소 정보가 없어 `おもう`가 "오모"가 되고 조사 `は`가 "하"로 읽히는 한계가 있다.

생성 결과는 캐시가 아니라 **표현 자산**으로 저장한다. 같은 일본어 표현은 `expressions`에 한 번만 저장하고, "이 한국어 의미에서의 뜻·말투"는 `meaning_expressions` 관계에 저장한다. 따라서 `괜찮아요 → 大丈夫`와 `문제없어요 → 大丈夫`는 같은 표현 하나에 서로 다른 설명 두 개로 연결된다.

## 선택한 표현 하나만 검색

사용자가 의미→표현 관계 하나를 고른 뒤에만 `search.search_selected_expression(settings, relation, nadeshiko_client=..., database=...)`가 그 일본어 표현 하나를 검색한다. AI가 표현을 만들었다는 이유로 표현들을 미리 검색하지 않는다.

검색은 활성 선호작만 대상으로 하며(활성 작품이 없으면 `NoActiveMediaError`), 공식 SDK 일반 검색 → 로컬 표면형 판정 → 결과가 0이면 `exact_match=True`로 한 번 더 → 같은 표면형 판정 순서를 유지한다. **검색 응답과 결과는 DB에 저장하거나 캐시하지 않는다.** 같은 표현을 나중에 다시 찾으면 Nadeshiko를 다시 호출한다.

API에서 가져오는 후보 수와 화면에 보여줄 장면 수는 다른 값이다. 흔한 표현은 첫 응답이 비슷하지만 다른 표현으로 채워져 표면형 판정에서 전부 떨어질 수 있으므로, `scene_result_limit`만큼 모일 때까지 공식 커서로 다음 후보를 이어서 훑는다. 목표를 채우면 즉시 멈춰 더 조회하지 않고, 후보가 계속 있어도 한 표현당 일반 검색 4번·정확 검색 2번을 넘기지 않는다(후보 200개 안팎). 흔한 표현은 대개 첫 요청 한 번으로 끝난다.

로컬 검사는 다음 차이만 완화한다.

- `unicodedata.normalize("NFKC", ...)`에 따른 Unicode 호환·전각/반각 차이
- 원문의 불필요한 Unicode 공백
- 표현 끝의 `?`, `!`, `.`, `。` 문장부호

내부 문장부호와 활용형은 지우지 않는다. 응답에 Nadeshiko top-level token이 있으면 원문의 token 시작·끝 위치를 표현 경계의 보조 자료로 사용한다. 따라서 독립 token인 `悪い` 뒤에 다른 말이 이어지는 문장은 허용하면서도, `気持ち悪い` compound token 안의 `悪い`는 통과시키지 않는다. 문장부호 없이 바로 다음 token이 이어질 때는 매치 구간 자체가 하나의 top-level token인 경우만 허용해, 여러 token으로 된 표현에 문법 suffix가 덧붙은 결과를 보수적으로 제외한다. token이 없는 응답의 짧은 표면형은 복합어 내부 일치를 피하도록 보수적으로 판정한다. `ほんとそれ`도 `ほんと? それって...`에 걸리지 않는다.

한자/가나 표기 차이는 자동 변환하지 않는다. `matches_surface()`의 `allowed_surfaces`에 검증한 가나 표기를 명시한 경우에만 허용한다. AI가 생성한 읽기(`reading`)는 정확한 허용 표기라고 보장할 수 없으므로 자동 연결하지 않는다.

영어 검색 대체 경로는 아직 하지 않는다.

일반 `uv run pytest`는 AI와 Nadeshiko를 가짜 객체로 대체한다. 실제 연결 품질 시험은 루트 `.env`에서 `GOOGLE_API_KEY`와 `NADESHIKO_API_KEY`만 현재 셸에 로드한 뒤 명시적으로 실행한다. 키 값과 `.env` 내용은 출력하거나 저장하지 않는다.

```powershell
$env:SCENE_COLLECTOR_SEARCH_LIVE_SERVICE = "google"
$env:SCENE_COLLECTOR_SEARCH_LIVE_MODEL = "gemini-3.6-flash"
$env:SCENE_COLLECTOR_SEARCH_LIVE_SCENE_RESULT_LIMIT = "5"
$env:SCENE_COLLECTOR_SEARCH_LIVE_REPORT = (Join-Path $env:TEMP "scene-collector-search-live.json")
uv run pytest --run-search-live -m search_live -ra
```

## 정확 동일표현 실제 연결 비교

작업 5의 실제 비교는 AI를 호출하지 않고 고정 일본어 target 6개만 사용한다. target마다 Nadeshiko 일반 검색과 `exact_match=True`를 한 번씩 호출하고, 두 응답의 로컬 표면형 수와 실제 파이프라인이 선택할 최종 수를 비교한다.

```powershell
$env:SCENE_COLLECTOR_SURFACE_LIVE_REPORT = (Join-Path $env:TEMP "scene-collector-surface-live.json")
uv run pytest --run-surface-live -m surface_live -ra
```

보고서에는 fetch 수·추정 전체 수·token 제공 수, 제거된 대표 원문과 채택된 대표 원문만 기록한다. API 키·사용자 정보·segment/media ID는 기록하지 않는다. 일반 `uv run pytest`에서는 이 시험이 항상 건너뛰어진다.

## 선호 작품 관리

작품 이름 문자열이 아니라 Nadeshiko public media ID를 내부 식별자로 저장한다. `display_name`은 사람에게 보여주기 위한 metadata일 뿐이므로 작품명이 바뀌어도 로컬 선택은 깨지지 않는다.

- `media.search_media(client, "작품명")`은 공식 SDK의 `search_media` endpoint로 public ID와 표시명 후보(`MediaSummary`)를 가져온다. 작품 목록 전체를 받아 로컬에서 문자열 검색하지 않는다.
- `media.store_media(database, media)`는 검색·조회 결과의 public ID와 표시명을 `media` table에 upsert한다. 같은 public ID는 중복 row를 만들지 않고, 표시명은 `name_ja → name_romaji → name_en` 순서로 고른다.
- `media.refresh_media_metadata(database, client, media_id)`는 필요한 작품 하나만 공식 `get_media`로 조회해 표시명을 갱신한다. 표시명 없이 public ID만 있는 row도 이 경로로 채운다. 어떤 갱신에서도 사용자 `preference`/`content_group`/`is_active`는 덮어쓰지 않는다.
- `SceneCollectorDatabase`의 `set_media_preference`(nullable 정수, scale 미확정), `set_media_content_group`(임의 문자열 또는 None, 빈 문자열은 None으로 정규화), `set_media_active`, `get_media`/`list_media`/`list_active_media`로 선호작 상태를 관리하고 재시작 후 복원한다.

장면 검색(`search.search_selected_expression()`)은 활성 작품의 public ID를 정렬해 공식 `SearchFilters.media.include` 필터로 한 요청에 전달한다. 비활성 작품은 검색하지 않으며, 활성 작품이 하나도 없으면 대사 자료 전체로 자동 확대하지 않고 `NoActiveMediaError`를 발생시킨다. 작품 필터를 건너뛰는 경로는 남겨 두지 않았다.

실제 Nadeshiko 작품 metadata·media filter 검증은 API 사용량이 발생하므로 명시적으로 실행한다. 루트 `.env`에서 `NADESHIKO_API_KEY`만 현재 셸에 로드하고 키 값은 출력하지 않는다. AI API 키는 필요 없다.

```powershell
uv run pytest --run-media-live -m media_live -ra
```

이 시험은 공식 `list_media`/`search_media`/`get_media`로 실제 작품 public ID와 표시명을 얻고, temp SQLite DB에 저장한 선호작 상태의 재시작 복원과, 해당 작품으로 필터한 실제 대사 검색(기본 검색어 `大丈夫`, 필요할 때만 `SCENE_COLLECTOR_MEDIA_LIVE_QUERY`로 변경)과 반복 검색의 cache 동작을 확인한다.

## 한국어 장면 번역

`ui_controller.translate_scene(settings, database, relation, segment, media_display_name, nadeshiko_client=...)`가 화면에서 쓰는 진입점이다. **사용자가 그 장면에서 명시적으로 요청했을 때만** 실행하며, 검색 결과 전체를 미리 번역하지 않는다.

- 문맥은 요청한 장면 하나에만 공식 `get_segment_context(segment_public_id, take=2)`로 조회한다. 응답 리스트 순서를 믿지 않고 같은 `media_public_id`·같은 `episode` 중 position이 가장 가까운 앞/뒤 장면을 고르며, 첫/마지막 장면의 빈 문맥은 정상 상태다.
- **문맥 원본 응답은 저장하거나 캐시하지 않는다.** 다시 번역하면 다시 조회한다.
- 번역은 `create_structured_response()` 경로와 `SceneTranslation` 자료형을 사용하며 장면 하나만 요청한다. 지시문 버전은 `scene-translation-v2`다.
- 문맥 조회와 번역만 하는 부분은 `translate.translate_segment()`이며 DB에 쓰지 않는다. 저장은 `ui_controller.translate_scene()`이 맡고, **두 호출이 모두 성공한 뒤에야** 작업 장면을 만들어 번역을 저장한다. 그래서 문맥 조회나 AI가 실패하면 빈 작업 장면이 남지 않고, 이미 작업 중이던 장면이라면 기존 판정·메모·번역이 그대로 남는다.
- 번역 결과는 캐시가 아니라 작업물이므로 `work_scenes`에 생성 이력(서비스·모델·지시문 버전·시각)과 함께 저장된다. `save_work_scene_translation()`은 판정·메모를 건드리지 않고, `set_work_scene_decision()`/`set_work_scene_notes()`는 번역을 건드리지 않는다.

실제 Nadeshiko 문맥 + AI 번역 검증은 API 사용량이 발생하므로 명시적으로 실행한다. 루트 `.env`에서 `NADESHIKO_API_KEY`와 사용할 provider의 키만 현재 셸에 로드하고 값은 출력하지 않는다.

```powershell
$env:SCENE_COLLECTOR_TRANSLATION_LIVE_SERVICE = "google"
$env:SCENE_COLLECTOR_TRANSLATION_LIVE_MODEL = "gemini-3.6-flash"
$env:SCENE_COLLECTOR_TRANSLATION_LIVE_REPORT = (Join-Path $env:TEMP "scene-collector-translation-live.json")
uv run pytest --run-translation-live -m translation_live -ra
```

이 시험은 실제 장면 하나만 번역하면서 문맥 조회 1회와 AI 1회만 발생하는지, 그리고 DB를 다시 열었을 때 저장된 번역이 추가 호출 없이 복원되는지 확인한다. 검색어는 기본 `大丈夫`이며 필요할 때만 `SCENE_COLLECTOR_TRANSLATION_LIVE_QUERY`로 바꾼다. 보고서에는 장면 텍스트와 번역만 기록하고 key·사용자 정보·segment/media ID는 넣지 않는다.

## 로컬 저장 구조

`SceneCollectorDatabase.open(settings)`는 새 경로 설정을 요구하지 않고 다음 파일을 관리한다.

```text
<storage.work_data_dir>/scene_collector.sqlite3
```

DB에는 사용자의 작업 자산만 둔다: 작품 상태(`media`, `local_segments`), 표현 자산(`meanings`, `expressions`, `meaning_expressions`), 실제 작업(`work_scenes`). **검색 응답·문맥 응답·AI 응답 캐시는 없다.**

- `meanings`: 정규화한 한국어 의미(UNIQUE)와 표시용 원문.
- `expressions`: 일본어 표현 자체(japanese UNIQUE, reading).
- `meaning_expressions`: 의미↔표현 관계와 **그 의미에서의 뜻·말투**. 같은 표현이 여러 의미에 연결될 수 있다.
- `work_scenes`: 판정(`채택`/`예비`/`제외`)·번역·메모 중 하나라도 실제로 발생한 장면만. 관계(`meaning_expression_id`)와 `segment_public_id` 기준으로 유일하며, 작품·화수·시각·일본어 원문은 그 시점의 작업물 스냅샷으로 저장한다. **영상/음성/이미지 주소와 원본 응답은 저장하지 않는다.**

검색 결과를 보기만 해서는 아무것도 저장되지 않는다. 번역은 캐시가 아니라 작업물이므로 생성 이력(서비스·모델·지시문 버전·시각)과 함께 `work_scenes`에 저장하고, 판정·메모와 서로 덮어쓰지 않는다.

빈 작업 장면은 남기지 않는다. 아직 작업하지 않은 장면에 빈 메모를 저장하면 행을 만들지 않고, 메모만 있던 장면에서 메모를 지우면 `delete_work_scene_if_empty()`가 그 행을 지운다. 판정이나 번역이 남아 있으면 지우지 않는다. 공백이나 폭 없는 문자만 남은 메모는 `normalize_work_scene_notes()`가 메모 없음으로 본다.

장면 스냅샷과 판정·번역·메모는 **한 transaction에서 함께 저장한다.** 두 번에 나눠 쓰면 뒤쪽이 실패했을 때(다른 프로그램이 DB를 쓰는 중이거나 도중에 종료되는 경우) 아무 작업도 없는 행이 남기 때문이다. 그래서 저장이 실패하면 장면 자체가 만들어지지 않고, 이미 작업하던 장면이라면 기존 내용이 그대로 남는다.

현재 schema는 `SCHEMA_VERSION = 4`이며 `PRAGMA user_version`으로 확인한다. 구버전 파일 DB는 열 때 각 단계 전에 `backup_before_schema_change()`로 같은 작업 데이터 위치에 `.pre-schema-v{n}.` 사본을 만든 뒤 한 transaction에서 v1 → v2 → v3 → v4로 순차 이동하며, 실패하면 해당 단계 이전 데이터를 그대로 유지한다. v3 → v4에서는 작품 상태·로컬 자막 색인·저장된 표현과 의미 연결·실제 작업(판정/번역/메모)을 새 구조로 옮기고, 검색 이력·검색 결과 장면·캐시·영상 주소는 옮기지 않는다. 여러 옛 table을 버리므로 SQLite 공식 절차대로 foreign key 검사를 잠시 끄고 수행하며 커밋 전에 `PRAGMA foreign_key_check`로 참조 무결성을 확인한다. 현재 코드보다 높은 version은 데이터를 변경하지 않고 거부한다. 각 연결에서 foreign key 검사를 명시적으로 켜고, WAL은 활성화하지 않아 SQLite 기본 롤백 저널을 유지한다.

자동시험은 파일 기반 임시 DB와 가짜 서비스를 사용한다. 일반 `uv run pytest`에서 인터넷이나 실제 AI/Nadeshiko API를 호출하지 않는다.

## 로컬 일본어 자막 대체 경로

Nadeshiko에 없는 작품은 사용자가 직접 확보한 일본어 timed subtitle(SRT/ASS)로 검색한다. 자막 파일은 저장소 밖 사용자 위치에 두고, 자동 다운로드는 없다.

```python
from pathlib import Path

from scene_collector.subtitles import index_local_subtitles

media, count = index_local_subtitles(database, "작품 표시명", Path("자막 폴더"))
```

화수는 파일명(`S1E01`, `第13話`, `Ep 7`, `- 02` 등 범용 패턴)에서 추정하며 극장판처럼 없으면 비워 둔다. 같은 작품을 다시 색인하면 기존 색인을 통째로 교체한다. 등록된 로컬 작품은 `media` table에 `source='local'`(Nadeshiko ID 없음)로 저장되어 기존 선호작처럼 `is_active`로 검색 포함 여부를 관리한다.

선택한 표현 하나를 검색할 때 활성 Nadeshiko 작품은 공식 검색으로, 활성 로컬 작품은 색인에서 LIKE로 1차 축소한 뒤 같은 표면형 판정으로 함께 조회한다(`SelectedExpressionScenes.nadeshiko_segments` + `local_segments`). 활성 Nadeshiko 작품이 없으면 Nadeshiko API를 호출하지 않는다.

**이번 범위에서 로컬 자막 결과는 그 표현이 자막 작품에 존재하는지 확인하는 참고 결과다.** 영상 재생·판정 저장·`work_scenes` 저장·내보내기는 Nadeshiko 장면만 지원한다. 로컬 결과는 작품 표시명·화수·start/end ms를 담고 있어 사용자가 보유한 원본 영상에서 위치를 찾는 데 쓰며, 자막과 원본의 판본 차이로 실측 기준 ±15초 안팎의 오프셋이 있을 수 있고 화마다 다를 수 있다.

## 화면 기술 선택 결과

Windows 11 + WebView2 Runtime에서 NiceGUI 3.16.0(native mode)과 pywebview 6.2.1을 같은 조건(같은 영상 목록·같은 창 구성·같은 EdgeChromium/WebView2 backend)의 작은 probe로 실측 비교해 **NiceGUI를 선택**했다.

실측에서 확인된 사실:

- 두 기술 모두 WebView2(EdgeChromium) renderer를 사용했고(user-agent `Edg/151` 확인) 영상 재생 능력 자체는 동일했다. NiceGUI native는 내부적으로 pywebview를 사용한다.
- **이번 Task 9에서 샘플링한 Nadeshiko sentence video_url 자산 20개는 시간대별 frame 차이가 인코딩 노이즈 수준이어서 실질적으로 "정지 화면 + 대사 음성" 형태의 MP4로 확인됐다.** ffprobe와 frame 픽셀 비교로 확인했으며, 이 결과를 Nadeshiko 전체 대사 자료의 모든 video_url 자산으로 일반화하지 않는다. 따라서 검수 화면에서 이런 자산이 정지 화면 + 음성으로 재생되는 것은 정상이며, 움직이는 MP4 재생 검증은 ffmpeg로 생성한 로컬 테스트 영상으로 별도 수행했다.
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

## 사용자 화면 실행

```powershell
uv run python -m scene_collector.app
```

실행 디렉터리의 `settings.toml`과 같은 위치의 `.env`를 읽는다. 다른 설정 파일이 필요할 때만 `SCENE_COLLECTOR_SETTINGS_FILE` 환경변수로 경로를 지정한다. NiceGUI native mode 창이 열린다.

화면은 표현 찾기 / 일본어 표현 선택 / 장면 검수 / 선호 작품 / 설정 다섯 탭이다. 제목과 탭 메뉴는 화면 맨 위에 고정되어 본문만 스크롤된다. 처음 사용 순서는 다음과 같다.

1. **설정** 탭에서 작업 데이터 위치·AI 서비스/모델·Nadeshiko 키 상태를 확인한다. 키 값 자체는 화면에 표시하지 않는다. 표현 생성 상한과 표시할 장면 수는 여기서 바꿔 `설정 저장`을 누르면 설정 파일에 저장되고 지금 실행에도 바로 반영된다. 작업 데이터 위치는 실행 중에 바꾸면 열려 있는 데이터베이스와 어긋나므로 파일에서만 바꾼다.
2. **선호 작품** 탭에서 작품을 활성화한다. 상단의 **추천 후보 목록(curated 97개, A군 63/B군 34)**에서 체크하면 그 항목에 연결된 Nadeshiko entry들이 함께 저장·활성화되고(예: 체인소 맨 = TV + 레제편), 해제하면 함께 비활성화된다. 전체/A군/B군 필터가 있고, 각 항목에 자료 상태(`장면 검색 바로 가능`/`연결된 일부만 장면 검색 가능 · 연결 N개`/`일본어 자막 준비 필요`)가 표시된다. 부분 지원 작품은 시리즈 전체가 아니라 현재 연결된 항목만 검색된다는 뜻이다. 선별에 쓴 내부 등급은 화면에 보여주지 않는다. `일본어 자막 준비 필요` 항목은 자막을 확보해 `index_local_subtitles`로 **curated 한국 제목과 같은 표시명**으로 색인한 뒤에만 체크할 수 있다(자동 다운로드 없음). curated 목록에 없는 작품은 아래의 작품 직접 검색으로 기존처럼 추가한다. 활성 작품이 하나도 없으면 검색은 실행되지 않고 "검색에 사용할 활성 작품이 없습니다" 안내가 표시된다. 97개 후보가 DB에 자동 삽입되지는 않으며, 체크한 작품만 저장된다.
3. **표현 찾기** 탭에서 한국어 의미를 입력하고 Enter를 누르거나 `표현 찾기`를 누른다. 둘은 완전히 같은 동작이다. 이 버튼 하나로 끝난다. 저장된 표현이 있으면 **AI를 호출하지 않고** 바로 보여주고, 하나도 없으면 같은 동작 안에서 AI를 한 번 호출해 표현을 만들어 저장한 뒤 보여준다. 어느 쪽이든 이 단계에서 Nadeshiko는 호출하지 않는다.
4. **일본어 표현 선택** 탭에서 저장된 표현이 전부 보인다(일본어·한글 독음·말투). `표현 더 찾기`는 기존 표현을 AI에 전달해 중복되지 않는 표현만 추가하며, 더 붙일 표현이 없으면 "새 표현 0개"로 표시된다. **표현 하나에서 `이 표현으로 장면 찾기`를 누른 순간에만** 그 표현이 검색된다.
5. **장면 검수** 탭은 현재 작업 맥락(한국어 의미 → 일본어 표현)을 보여주고, 찾은 장면을 텍스트 목록으로 표시한다. `이 장면 보기`를 누르면 **영상 플레이어 하나에 그 장면만** 로딩된다. 필요할 때만 `문맥 조회 + 한국어 번역`을 실행하고, 채택/예비/제외와 메모를 저장한다. 로컬 자막 결과는 그 표현이 자막 작품에 있는지 확인하는 참고 표시이며 영상·판정 대상이 아니다. 새 의미를 조회하거나 다른 표현을 고르면 이전 장면 목록·영상·번역 표시는 모두 지워지고, 영상은 장면을 다시 고른 뒤에만 나타난다.
6. 프로그램을 종료 후 다시 실행하면 **표현 자산과 실제 작업 장면이 유지된다.** 지난 검색 결과는 저장하지 않으므로 자동 복원되지 않고, 표현을 다시 고르면 그때 다시 검색한다.
7. **장면 검수** 탭의 `채택 장면 내보내기`는 채택 판정된 작업 장면 전체를 `<작업 데이터 위치>/exports/`로 내보낸다. 영상은 `exports/videos/<segment_public_id>.mp4` 하나로 저장되어 같은 장면이 여러 의미→표현 관계에서 채택돼도 한 번만 받으며, 정상 파일이 있으면 Nadeshiko를 호출하지 않고 재사용한다. 파일이 없을 때만 장면 ID로 현재 장면을 다시 조회해 그 시점의 주소로 내려받는다. 메타데이터는 관계별로 `accepted_scenes.json`(UTF-8)과 `accepted_scenes.csv`(Excel용 BOM 포함 UTF-8)에 기록되고, 한국어 의미는 그 작업이 실제로 연결된 의미 하나만 출력한다. `video_file`은 `exports` 기준 상대경로라 SSD를 옮겨도 유지된다. 로컬 자막 장면 영상 내보내기는 아직 지원하지 않는다.

화면 상태(조회한 표현·선택한 관계·검색 결과)는 창(클라이언트)별로 분리되어 다른 창의 조작이 내 화면을 바꾸지 않는다. DB·네트워크 호출은 단일 작업 thread에서만 실행한다.

## 아직 없는 기능

- 영어 검색 fallback
- 로컬 자막 장면의 번역·검수 저장
- 영상 저장과 내보내기
