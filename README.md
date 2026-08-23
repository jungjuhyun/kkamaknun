# kkamaknun (까막눈)

일본어 학습·실험 유튜브 채널 「까막눈」의 계획·판단·실측·도구 저장소.

이 저장소는 채널 제작 자료뿐 아니라, 세션이 바뀌어도 **현재 상태·장기 맥락·판단 기준·작업 절차·과거 근거**를 가능한 한 적은 사용자 개입으로 이어받기 위한 project system of record 역할을 한다.

## 프로젝트 기본 방향

채널의 주인공은 만드는 사람 본인이다. 강의 자체보다:

```text
문제 발견
→ 가설
→ 필요한 만큼 학습/훈련
→ 실제 상황에서 검증
→ 결과
→ 다음 문제
```

의 실험·성장 구조를 사용한다.

채널 성장·수익화·지속 가능한 생산성도 함께 판단한다.

## 현재 상태는 어디서 보나

README는 current-state mirror가 아니다.

현재 무엇을 하고 있는지는:

- [진행상태.md](진행상태.md) — project-level current state
- `진행상태.md`가 가리키는 활성 execution plan — 해당 작업 내부 phase/local state

를 따른다.

과거 README의 `현재 첫 콘텐츠 상태`, 장비 상태, startup 순서 등을 여기 다시 복제하지 않는다.

## agent bootstrap

- [AGENTS.md](AGENTS.md) — **작은 router/map**. 요청에 따라 필요한 문서만 추가로 읽는 progressive-disclosure 경로를 정의한다.
- [CLAUDE.md](CLAUDE.md) — 수정 금지 Karpathy 공통 상위 행동규칙.
- [PROJECT_RULES.md](PROJECT_RULES.md) — 프로젝트 전체에 오래 적용되는 durable 실패 방지 규칙.

모든 project work에서 planning/judgment/history 문서를 일괄 preload하지 않는다. 세부 routing은 `AGENTS.md`가 기준이다.

## 핵심 문서와 canonical 역할

| 파일 | 역할 |
|---|---|
| [AGENTS.md](AGENTS.md) | bootstrap / query routing |
| [CLAUDE.md](CLAUDE.md) | immutable common behavior |
| [PROJECT_RULES.md](PROJECT_RULES.md) | durable project invariants |
| [진행상태.md](진행상태.md) | **project-level current state canonical owner** |
| [USER_CONTEXT.md](USER_CONTEXT.md) | stable user/project context |
| [PLANNING_PROCESS.md](PLANNING_PROCESS.md) | major planning procedure |
| [JUDGMENT.md](JUDGMENT.md) | reusable judgment principles |
| [DECISIONS.md](DECISIONS.md) | historical decision transition log — current owner 아님 |
| [첫콘텐츠_계획.md](첫콘텐츠_계획.md) | first-content detailed domain owner |
| [장비세팅.md](장비세팅.md) | OBS·오디오·카메라·장비 domain owner |
| [계획.md](계획.md) | 2026-08-20 이전 반복듣기 설계 archive |
| [실측/](실측/) | raw measured evidence |
| [도구/](도구/) | 작업용 scripts |
| [기록/](기록/) | historical records, research, audits, architecture docs |

## memory 원칙

- current mutable fact는 가능한 한 canonical owner 하나에서 관리한다.
- `DECISIONS.md`, `기록/`, `계획.md`, git history는 과거 상태와 근거를 보존하지만 current truth의 대체물이 아니다.
- 필요한 과거 근거만 on-demand retrieval한다.
- raw evidence/history를 파괴적으로 덮어쓰지 않는다.
- 모든 대화·실패를 permanent rule이나 memory로 승격하지 않는다.
- 사용자가 새 세션마다 bootstrap prompt나 context-transfer block을 운반하는 방식에 의존하지 않는다.

## CLAUDE 보호

`CLAUDE.md`의 `BEGIN IMMUTABLE KARPATHY GUIDELINES` ~ `END IMMUTABLE KARPATHY GUIDELINES` 블록은 수정하지 않는다. repository-specific rule은 `PROJECT_RULES.md`에 둔다.
