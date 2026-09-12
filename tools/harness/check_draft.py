"""기획 초안의 deterministic 위반만 검사한다.

기본 입력:
    COMMON_RULES.json  모든 편 공통 검사 정의.
    STATE.json         현재 편의 lock 경로를 선택.
    <현재 lock>        A/B 등 편별 잠금과 명백한 금지 문구.

사용법:
    python check_draft.py 초안.md
    python check_draft.py 초안.md tools/harness/다른편_LOCK.json

주의:
    PASS는 current truth·lock·자료 경계의 기계 검사 통과만 뜻한다.
    재미, 콘텐츠 각, 시청지속, RED TEAM 품질을 보증하지 않는다.
"""
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
COMMON = HERE / "COMMON_RULES.json"
STATE = HERE / "STATE.json"

# 비교할 때 무시할 기호: 백틱, 따옴표, 공백 차이
STRIP = re.compile(r"[`'\"“”‘’\s]")


def norm(text):
    return STRIP.sub("", text)


def load(path):
    return Path(path).read_text(encoding="utf-8")


def find_lines(text, needle):
    return [i + 1 for i, line in enumerate(text.splitlines()) if needle in line]


def resolve_path(raw):
    path = Path(raw)
    if path.is_absolute():
        return path
    cwd_path = Path.cwd() / path
    if cwd_path.exists():
        return cwd_path
    root_path = ROOT / path
    if root_path.exists():
        return root_path
    here_path = HERE / path
    if here_path.exists():
        return here_path
    return root_path


def resolve_lock_path(lock_arg=None, state_path=STATE):
    if lock_arg:
        return resolve_path(lock_arg)

    state = json.loads(load(state_path))
    raw = state.get("현재_lock")
    if not raw:
        return None
    return resolve_path(raw)


def check_forbidden_groups(draft_text, groups, fails):
    for label, needles in groups.items():
        for needle in needles:
            for line_no in find_lines(draft_text, needle):
                fails.append(f"{label} (줄 {line_no}): '{needle}'")


def check(draft_text, common, lock=None):
    """텍스트만 보고 확정적으로 판정 가능한 위반만 반환한다."""
    fails = []
    draft_norm = norm(draft_text)

    if lock:
        for name, sentence in lock.get("잠금_문장", {}).items():
            if norm(sentence) not in draft_norm:
                fails.append(f"잠금 {name} 원문이 없거나 바뀜: {sentence}")

    for sentence in common.get("반드시_들어갈_문장", []):
        if norm(sentence) not in draft_norm:
            fails.append(f"필수 문장 없음: {sentence}")

    check_forbidden_groups(
        draft_text, common.get("금지_문구_그룹", {}), fails
    )
    if lock:
        check_forbidden_groups(
            draft_text, lock.get("금지_문구_그룹", {}), fails
        )

    return fails


def main():
    # Windows 콘솔(cp949)에서도 한글·기호가 깨지지 않게
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if len(sys.argv) not in (2, 3):
        print(__doc__)
        return 2

    try:
        lock_path = resolve_lock_path(sys.argv[2] if len(sys.argv) == 3 else None)
        common = json.loads(load(COMMON))
        lock = json.loads(load(lock_path)) if lock_path else None
        fails = check(load(sys.argv[1]), common, lock)
    except (OSError, json.JSONDecodeError, KeyError) as exc:
        print(f"FAIL — validator 설정/입력 오류: {exc}")
        return 2

    if not fails:
        print("PASS")
        return 0

    print(f"FAIL — {len(fails)}건")
    for fail in fails:
        print(" -", fail)
    return 1


if __name__ == "__main__":
    sys.exit(main())
