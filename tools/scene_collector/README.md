# 애니 표현 장면 수집기

한국어로 찾고 싶은 뜻에서 출발해 실제 애니 표현 장면을 수집하기 위한 Windows 로컬 도구다.

현재 저장소에는 **작업 0 — 개발 골격**과 **작업 1 — 설정**만 들어 있다. 설정 로딩 이후의 외부 서비스 연결이나 실제 애플리케이션 기능은 아직 없다.

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

## 아직 없는 기능

- Nadeshiko 검색 및 실제 API 연결
- AI 호출과 공급자 교체
- SQLite 저장과 캐시
- 사용자 화면
- 영상 저장과 내보내기
