# AGENTS.md — 프로젝트 bootstrap / router

이 파일은 거대한 매뉴얼이 아니라 **어디를 언제 읽을지 정하는 작은 지도**다.

## 기본 시작

1. `CLAUDE.md` — 공통 상위 행동 규칙. 현재 harness가 이미 주입했다면 중복으로 다시 읽지 않는다.
2. `PROJECT_RULES.md` — 까막눈 프로젝트 전체에 적용되는 durable 실패 방지 규칙.
3. 현재 요청을 분류한 뒤 **필요한 문서만 추가로 읽는다.**

모든 프로젝트 작업에서 `PLANNING_PROCESS.md`, `JUDGMENT.md`, `USER_CONTEXT.md`, `DECISIONS.md`를 일괄 preload하지 않는다.

## 프로젝트 식별 / repo verification gate

`까막눈 프로젝트`, `kkamaknun`, `이 프로젝트 이어서`, `지금 어디까지 왔지`처럼 **현재 프로젝트 상태나 연속성에 의존하는 요청**에서는 답을 만들기 전에 repository 기준 상태를 확인한다.

- canonical repository: `jungjuhyun/kkamaknun`
- 기본 branch: `main`
- current-state owner: `진행상태.md`

GitHub/repository 접근이 가능한 환경에서는 **과거 ChatGPT memory, 이전 채팅 기억, 사용자 프로필/요약보다 repo 확인을 먼저 수행한다.**

repo 접근을 시도했지만 실패했거나 해당 세션에서 GitHub 접근 자체가 불가능하면:

1. 현재 프로젝트 상태를 **복원했다고 말하지 않는다.**
2. 과거 ChatGPT memory나 예전 대화 내용을 빈칸 채우기용으로 사용해 current state를 만들어내지 않는다.
3. `repo를 확인하지 못해 현재 상태를 검증할 수 없다`고 명시한다.
4. 사용자가 현재 대화 안에서 직접 제공한 정보만 답의 근거로 쓸 수 있으며, 그 경우도 `repo 검증 전`이라고 구분한다.

## 현재 상태를 이어갈 때

사용자가 `이 프로젝트 이어서 하자`, `다음 뭐하지`, `지금 어디까지 왔지`처럼 현재 작업에 의존하는 요청을 하면:

1. **먼저 `진행상태.md`를 읽는다.**
2. `진행상태.md`에 활성 execution plan이 있으면 그 파일을 읽는다.
3. 그 두 문서만으로 현재 단계와 다음 행동이 충분히 결정되면 **history/decision/archive는 읽지 않는다.**
4. 세부 실행 정보가 실제로 필요할 때만 해당 domain 문서를 추가한다.

`진행상태.md`는 **project-level current state**의 기준이다. 활성 execution plan이 있으면 그 plan은 **해당 작업 내부 phase/local state**의 기준이다.

현재 상태 질문에서 과거 기록을 먼저 읽거나, 오래된 프로젝트 맥락을 서론처럼 나열하지 않는다.

## 요청별 routing

- **새 콘텐츠/포맷/큰 방향 판단** → `진행상태.md` → `PLANNING_PROCESS.md` → `JUDGMENT.md`; 사용자 적합성 판단이 실제로 필요할 때만 `USER_CONTEXT.md` 추가.
- **첫 콘텐츠 세부** → `진행상태.md` → `첫콘텐츠_계획.md`; 큰 판단이면 planning/judgment 문서 추가.
- **장비·OBS·녹화 세팅** → 필요하면 `진행상태.md` → `장비세팅.md`.
- **사용자 장기 성향·배경** → `USER_CONTEXT.md`.
- **왜 그렇게 정했는지 / 과거 변경 이유** → current owner를 먼저 확인한 뒤 `DECISIONS.md`; 필요하면 `기록/` 또는 git history.
- **실측·시장·재료 근거** → 관련 domain owner → `실측/`; 최신 외부 사실이면 웹/공식 자료.
- **과거 반복듣기 설계** → `계획.md`, 필요 시 관련 `기록/`, `실측/`, `도구/`.

## 권위와 stale 처리

- 시스템/개발자/현재 사용자 지시가 저장소 문서보다 우선한다.
- mutable current fact는 **그 정보의 canonical owner**가 우선한다.
- **ChatGPT personalization memory / 과거 채팅 기억은 project current truth의 canonical source가 아니다.** repo와 충돌하면 repo current owner를 우선하고, repo로 확인되지 않은 구체 사실을 project fact처럼 쓰지 않는다.
- `DECISIONS.md`, `기록/`, `계획.md`, git history는 current truth의 대체물이 아니라 history/evidence다.
- 오래된 기록 한 줄을 찾았다는 이유로 현재 상태로 승격하지 않는다. 현재값이 필요한 질문이면 current/domain owner와 충돌 여부를 확인한다.
- 명확히 대체된 값은 새 값을 사용한다. 실제로 어느 쪽이 current인지 불분명하면 임의로 하나를 고르지 않는다.
- **평가용·가상·예시·테스트 시나리오는 실제 프로젝트 사실이 아니다.** 문서나 대화에서 발견해도 canonical owner가 실제 사실로 확인하지 않으면 현재/과거 프로젝트 사건처럼 서술하지 않는다.
- 현재 상태 답변에는 과거 사실을 `예전에는...` 식으로 자동 소개하지 않는다. 사용자가 history를 묻거나 현재 판단에 실제로 필요한 경우에만 꺼낸다.

## 주요 기획

사용자가 별도로 `공격해봐`라고 지시하기를 기다리지 않는다.
새 포맷·후속 콘텐츠·큰 구조 변경은 `PLANNING_PROCESS.md`의 자기검수를 거쳐 제출한다.
무엇을 좋은 기획으로 보는지는 `JUDGMENT.md`를 따른다.

## memory write routing

의미 있는 변화만 canonical memory에 승격한다.

- project current state → `진행상태.md`
- active task phase → 해당 active execution plan
- durable project invariant → `PROJECT_RULES.md`
- reusable planning procedure → `PLANNING_PROCESS.md`
- reusable judgment principle → `JUDGMENT.md`
- stable user/project context → `USER_CONTEXT.md`
- domain detail → 해당 domain 문서
- 의미 있는 decision transition → `DECISIONS.md`
- 긴 조사/과정/원본 보존 → `기록/`

일회성 대화나 단일 실패를 자동으로 영구 규칙으로 만들지 않는다. 같은 정보를 여러 current owner에 복제하지 않는다.

## CLAUDE.md 보호

`CLAUDE.md`의 `BEGIN IMMUTABLE KARPATHY GUIDELINES` ~ `END IMMUTABLE KARPATHY GUIDELINES` 블록은 수정·삭제·요약·재작성·재배열하지 않는다.
새 프로젝트 규칙은 `PROJECT_RULES.md`에만 둔다.
