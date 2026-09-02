"""기획 초안이 잠금 파일을 지켰는지 검사한다.

읽는 파일 (같은 폴더):
    COMMON_RULES.json  모든 편 공통. 필수 문장, 금지 표현.
    EP0_LOCK.json      이번 편 잠금. A/B 원문.

사용법:
    python check_draft.py 초안.md
    python check_draft.py 초안.md 다른편_LOCK.json

결과:
    PASS → 사용자에게 보여도 된다. 이 줄을 답변에 붙인다.
    FAIL → 어긋난 줄을 고친 뒤 다시 돌린다. 종료 코드 1.
"""
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).parent
COMMON = HERE / "COMMON_RULES.json"
LOCK = HERE / "EP0_LOCK.json"

# 비교할 때 무시할 기호: 백틱, 따옴표, 공백 차이
STRIP = re.compile(r"[`'\"“”‘’\s]")


def norm(text):
    return STRIP.sub("", text)


def load(path):
    return Path(path).read_text(encoding="utf-8")


def find_lines(text, needle):
    return [i + 1 for i, line in enumerate(text.splitlines()) if needle in line]


def check(draft_text, common, lock):
    fails = []
    draft_norm = norm(draft_text)

    for name, sentence in lock["잠금_문장"].items():
        if norm(sentence) not in draft_norm:
            fails.append(f"잠금 {name} 원문이 없거나 바뀜: {sentence}")

    for sentence in common["반드시_들어갈_문장"]:
        if norm(sentence) not in draft_norm:
            fails.append(f"필수 문장 없음: {sentence}")

    groups = [
        ("없는 자료를 있다고 씀", common["없는_자료를_있다고_쓰는_말"]),
        ("있는 자료를 없다고 씀", common["있는_자료를_없다고_쓰는_말"]),
    ]
    for label, needles in groups:
        for needle in needles:
            for line_no in find_lines(draft_text, needle):
                fails.append(f"{label} (줄 {line_no}): '{needle}'")

    return fails


def main():
    # Windows 콘솔(cp949)에서도 한글·기호가 깨지지 않게
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if len(sys.argv) not in (2, 3):
        print(__doc__)
        return 2
    lock_path = sys.argv[2] if len(sys.argv) == 3 else LOCK
    common = json.loads(load(COMMON))
    lock = json.loads(load(lock_path))
    fails = check(load(sys.argv[1]), common, lock)
    if not fails:
        print("PASS")
        return 0
    print(f"FAIL — {len(fails)}건")
    for f in fails:
        print(" -", f)
    return 1


if __name__ == "__main__":
    sys.exit(main())
