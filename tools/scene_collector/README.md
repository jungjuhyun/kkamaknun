# 애니 표현 장면 수집기

한국어로 찾고 싶은 뜻에서 출발해 실제 애니 표현 장면을 수집하기 위한 Windows 로컬 도구다.

현재 저장소에는 **작업 0 — 개발 골격**과 **작업 1 — 설정 로딩/검증**이 들어 있다. 아직 Nadeshiko나 AI 서비스에는 실제 연결하지 않는다.

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

`settings.example.toml`을 `settings.toml`로 복사한 뒤 다음 필수 값을 채운다.

- `storage.work_data_dir`: 사용자가 지정한 작업 데이터 위치
- `ai.service`: 사용할 AI 서비스 이름
- `ai.model`: 사용할 모델 이름

빈 값은 설정 오류로 처리한다. 실제 경로와 모델명은 코드에 하드코딩하지 않는다.

비밀정보는 `.env.example`을 참고해 로컬 `.env`에만 넣는다. 현재 설정 계층에서 읽는 비밀정보는 `NADESHIKO_API_KEY`이며 작업 2 전까지 실제 API 호출에는 사용하지 않는다.

설정 우선순위는 다음과 같다.

```text
환경변수 > .env > settings.toml
```

중첩 설정을 환경변수로 덮어쓸 때는 다음 이름을 사용한다.

```text
SCENE_COLLECTOR_STORAGE__WORK_DATA_DIR
SCENE_COLLECTOR_AI__SERVICE
SCENE_COLLECTOR_AI__MODEL
```

실제 `settings.toml`, `.env`, 작업 경로, API 키는 저장소에 커밋하지 않는다.

## 아직 없는 기능

- Nadeshiko 검색 및 실제 API 연결
- AI 호출과 공급자 교체
- SQLite 저장과 캐시
- 사용자 화면
- 영상 저장과 내보내기
