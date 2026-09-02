"""Claude Code PreToolUse hook (Bash/PowerShell). 위험한 git 명령을 막는다.

막는 것:
    main 브랜치에서 git commit
    main으로 git push
    backup 브랜치 checkout / switch
종료 코드 2 = 차단. stderr가 Claude에게 전달된다.
"""
import json
import re
import subprocess
import sys

COMMIT = re.compile(r"\bgit\b(?:\s+-C\s+(\S+))?.*\bcommit\b")
PUSH_MAIN = re.compile(r"\bgit\b.*\bpush\b.*(?:\s|:)main\b")
BACKUP = re.compile(r"\bgit\b.*\b(?:checkout|switch)\b.*backup")


def branch(cwd):
    try:
        out = subprocess.run(["git", "branch", "--show-current"],
                             cwd=cwd, capture_output=True, text=True, timeout=5)
        return out.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def strip_text(cmd):
    """따옴표 안과 heredoc 본문(커밋 메시지 등)은 검사하지 않는다."""
    cmd = re.sub(r"<<-?\s*['\"]?\w+['\"]?.*", "", cmd, flags=re.S)
    return re.sub(r"\"[^\"]*\"|'[^']*'", "", cmd)


def main():
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    data = json.load(sys.stdin)
    cmd = strip_text(data.get("tool_input", {}).get("command", ""))
    cwd = data.get("cwd") or None
    reasons = []
    m = COMMIT.search(cmd)
    if m and branch(m.group(1) or cwd) == "main":
        reasons.append("main 브랜치에 직접 커밋하지 않는다. 작업 브랜치에서 커밋한다.")
    if PUSH_MAIN.search(cmd):
        reasons.append("main으로 직접 push하지 않는다.")
    if BACKUP.search(cmd):
        reasons.append("backup 브랜치는 사용자가 명시적으로 과거 기록을 요청할 때만 본다.")
    if reasons:
        print("[harness 차단] " + " / ".join(reasons), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
