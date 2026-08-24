<!-- PROTECTED FILE -->
<!--
The block between BEGIN/END IMMUTABLE KARPATHY GUIDELINES is vendored from:
https://github.com/multica-ai/andrej-karpathy-skills/blob/main/CLAUDE.md

DO NOT edit, delete, paraphrase, reorder, or replace any line inside that block.
This file is the Claude-facing adapter only. Project truth lives in the shared canonical documents listed below.
-->

<!-- BEGIN IMMUTABLE KARPATHY GUIDELINES -->
# CLAUDE.md

Behavioral guidelines to reduce common LLM coding mistakes. Merge with project-specific instructions as needed.

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

---

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.
<!-- END IMMUTABLE KARPATHY GUIDELINES -->

## Claude project adapter

이 파일은 Claude용 진입점일 뿐이며 현재 프로젝트 사실을 소유하지 않는다.
프로젝트 사실과 판단은 아래 shared owner 문서를 사용한다.

- `STATE.md` — 현재 상태와 다음 행동
- `PROJECT_CONTEXT.md` — 오래 유지되는 프로젝트 정체성·목표
- `PLAYBOOK.md` — 공통 판단·작업 원칙
- `FIRST_VIDEO.md` — 현재 첫 콘텐츠 세부
- `USER_PROFILE.md` — 사용자 적합성이 실제 판단을 바꿀 때만 읽는 안정적 사용자 프로필

### 시작 순서

1. `이어가자`, `지금 어디까지`, `다음 뭐야`처럼 **현재 프로젝트 연속성에 의존하는 요청이면 가장 먼저 `STATE.md`를 읽는다.**
2. 그 다음 현재 요청에 실제로 필요한 owner만 추가로 읽는다.
   - 첫 콘텐츠 세부 → `FIRST_VIDEO.md`
   - 큰 기획·판단 → `PLAYBOOK.md`
   - 프로젝트 정체성·목표 → `PROJECT_CONTEXT.md`
   - 사용자 취향·성향·지속 가능성이 실제 판단을 바꿀 때 → `USER_PROFILE.md`
3. 연속성에 의존하지 않는 큰 판단/기획에서는 `PLAYBOOK.md`를 필요에 따라 확인한다.
4. 모든 문서를 무조건 한꺼번에 읽지 않는다.

### 권위와 과거 자료

- 현재 상태는 `STATE.md`, 첫 콘텐츠 세부는 `FIRST_VIDEO.md`가 우선한다.
- 안정적 프로젝트 정체성·목표는 `PROJECT_CONTEXT.md`, 안정적 사용자 특성은 `USER_PROFILE.md`가 담당한다.
- `AGENTS.md`와 이 파일은 adapter이며 별도의 프로젝트 사실 owner가 아니다.
- git history, backup branch, 삭제된 과거 문서는 사용자가 명시적으로 과거 기록·복구를 요청한 경우에만 본다.
- repo와 모델 기억이 충돌하면 해당 current owner를 우선한다.
- repo를 확인할 수 없으면 과거 기억으로 현재 상태를 추측하지 않는다.

### 수정 위치

- 현재 상태 변경 → `STATE.md`
- 안정적 프로젝트 정체성·목표 변경 → `PROJECT_CONTEXT.md`
- 오래 유지될 판단·작업 원칙 변경 → `PLAYBOOK.md`
- 첫 콘텐츠 세부 변경 → `FIRST_VIDEO.md`
- 오래 유지되고 의사결정을 실제로 바꾸는 비민감 사용자 취향·성향 변경 → `USER_PROFILE.md`

같은 사실을 `CLAUDE.md`에 다시 복제하지 않는다.
