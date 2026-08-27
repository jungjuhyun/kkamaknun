# 애니 표현 장면 수집기

한국어로 찾고 싶은 뜻에서 출발해 실제 애니 표현 장면을 수집하기 위한 Windows 로컬 도구다.

현재 저장소에는 **작업 0 — 개발 골격**, **작업 1 — 설정**, **작업 2 — Nadeshiko 실제 연결 확인**이 완료되어 있다. 이 브랜치에는 **작업 3 — AI 실제 연결 확인**을 위한 연결 코드와 opt-in 시험이 들어 있다. 검색 품질 로직이나 저장·화면 기능은 아직 없다.

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

2026-08-27 기준 공식 문서에서 확인한 저비용 모델을 사용하는 실행 예시는 다음과 같다. 실제 실행 전 각 provider 공식 문서에서 모델의 현재 사용 가능 여부를 다시 확인한다.

```powershell
$env:SCENE_COLLECTOR_AI_LIVE_OPENAI_MODEL = "gpt-5.4-nano"
$env:SCENE_COLLECTOR_AI_LIVE_GOOGLE_MODEL = "gemini-2.5-flash"
uv run pytest --run-ai-live -m ai_live -ra
```

두 서비스 시험은 같은 중립 프롬프트와 `text: str`, `number: int` Pydantic 자료형을 사용한다. 두 서비스가 모두 실제 호출과 자료형 검증에 성공해야 작업 3을 통과한 것으로 본다.

## 아직 없는 기능

- 한국어 → 일본어 표현 후보 생성과 검색 품질 로직
- SQLite 저장과 캐시
- 사용자 화면
- 영상 저장과 내보내기
