"""Claude Code SessionStart hook. STATE.md를 그대로 컨텍스트에 넣는다.

STATE.md가 짧아진 뒤로는 요약 대신 전문을 넣는다. 요약 코드는 두지 않는다.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    state = ROOT / "STATE.md"
    print("[harness] STATE.md 주입. 현재 상태와 다음 할 일은 이 파일이 owner다. AGENTS.md 시작 순서를 따른다.")
    print(state.read_text(encoding="utf-8"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
