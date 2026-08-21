# AGENTS.md — 필수 시작 절차

이 저장소에서 작업하기 전에 아래 파일을 **이 순서대로 반드시 읽는다.**

1. `CLAUDE.md` — Karpathy 공통 상위 행동 규칙
2. `PROJECT_RULES.md` — 까막눈 프로젝트 전용 실패 방지 규칙
3. `USER_CONTEXT.md` — 사용자 의도·취향·판단 기준·작업 방식
4. `진행상태.md` — 현재 최우선 과제와 다음 행동
5. `DECISIONS.md` — 확정·보류·폐기된 결정

필요할 때만 `기록/`, `실측/`, `계획.md`의 과거 자료를 조회한다.

## 우선순위

- 시스템/개발자/현재 사용자 지시가 저장소 문서보다 우선한다.
- 저장소 내부에서는 `CLAUDE.md`의 Karpathy 규칙을 공통 상위 행동 규칙으로 본다.
- `PROJECT_RULES.md`는 이를 확장할 수 있지만 약화·대체하지 않는다.
- 현재 상태 판단은 `진행상태.md`와 `DECISIONS.md`를 우선한다.
- 과거 문서의 분량이 많다고 현재 주력으로 추정하지 않는다.
- 폐기·보류된 아이디어를 되살리기 전에 `DECISIONS.md`를 확인한다.

## CLAUDE.md 보호

`CLAUDE.md`의 `BEGIN IMMUTABLE KARPATHY GUIDELINES` ~ `END IMMUTABLE KARPATHY GUIDELINES` 블록은 수정·삭제·요약·재작성·재배열하지 않는다.
새 프로젝트 규칙은 `PROJECT_RULES.md`에만 추가한다.

## 작업 종료 전

프로젝트 방향·편성·우선순위·사용자 선호에 의미 있는 변경이 생겼으면 종료 전에 다음을 갱신한다.

- 현재 상태 변화 → `진행상태.md`
- 결정/철회 → `DECISIONS.md`
- 장기적으로 재사용할 사용자 맥락 → `USER_CONTEXT.md`
- 긴 대화·조사 과정 보존 필요 → `기록/`

문서 갱신 자체가 목적이 되어 작업을 방해하지 않도록 한다.