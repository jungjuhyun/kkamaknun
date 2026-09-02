"""Claude Code UserPromptSubmit hook. 매 발화마다 핵심 규칙 1줄을 다시 넣는다."""
import sys


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print("[harness] 완료는 사용자만 선언한다. 확보하지 못한 자료를 확보했다고 하지 않는다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
