# 애니 표현 장면 수집기

한국어로 찾고 싶은 뜻에서 출발해 실제 애니 표현 장면을 수집하기 위한 Windows 로컬 도구다.

현재 저장소에는 **작업 0 — 개발 골격**만 들어 있다. import 가능한 최소 Python 패키지, uv 프로젝트 설정, pytest 시험, Ruff 검사 설정과 비어 있는 설정 예제를 제공한다.

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

`settings.example.toml`과 `.env.example`은 형식 확인용 예제다. 실제 사용 시 별도 `settings.toml`과 `.env`를 만들고, 실제 작업 데이터 위치와 비밀키는 그 로컬 파일에만 넣는다. 경로와 키 값은 저장소에 커밋하지 않는다.

설정 로딩은 작업 1에서 구현한다. 현재 예제 파일을 읽는 애플리케이션 코드는 없다.

## 아직 없는 기능

- 설정 로딩과 검증
- Nadeshiko 검색 및 실제 API 연결
- AI 호출과 공급자 교체
- SQLite 저장과 캐시
- 사용자 화면
- 영상 저장과 내보내기
