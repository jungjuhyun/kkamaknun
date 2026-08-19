# -*- coding: utf-8 -*-
"""조사 진행률 보기.

  python 도구/조사현황.py        진행률
  python 도구/조사현황.py -v     나온 결과까지
  python 도구/조사현황.py -w     10초마다 자동 갱신
"""
import json, os, sys, glob, time

BASE = os.path.expanduser(
    r"~\.claude\projects\c--Claude-Code-youtube"
    r"\e45d4c53-2036-437e-aeeb-28f4fbe913b1\subagents\workflows")

# (표시명, 런ID, 총 에이전트 수)
RUNS = [("투자자 공격 — 계획.md 실사", "wf_0f1bcc52-678", 11)]

VERBOSE = "-v" in sys.argv
WATCH = "-w" in sys.argv


def bar(done, total, width=40):
    filled = int(width * done / total) if total else 0
    return "[" + "#" * filled + "." * (width - filled) + "]"


def show():
    print("=" * 72)
    print("  조사 진행률   " + time.strftime("%H:%M:%S"))
    print("=" * 72)
    for label, run, total in RUNS:
        d = os.path.join(BASE, run)
        jp = os.path.join(d, "journal.jsonl")
        print("\n[ %s ]" % label)
        if not os.path.exists(jp):
            print("   아직 시작 안 함")
            continue

        started = results = 0
        done_entries = []
        for line in open(jp, encoding="utf-8"):
            try:
                e = json.loads(line)
            except Exception:
                continue
            if e.get("type") == "started":
                started += 1
            elif e.get("type") == "result":
                results += 1
                done_entries.append(e)

        pct = 100.0 * results / total if total else 0
        print("   %s  %5.1f%%   (%d/%d 완료, %d개 돌는 중)"
              % (bar(results, total), pct, results, total, max(0, started - results)))

        now = time.time()
        live = 0
        for f in glob.glob(os.path.join(d, "agent-*.jsonl")):
            if now - os.path.getmtime(f) < 120:
                live += 1
        print("   살아 움직이는 에이전트: %d개" % live)

        if VERBOSE and done_entries:
            print()
            for e in done_entries:
                r = e.get("result") or {}
                if not isinstance(r, dict):
                    continue
                print("   --- %s" % e["agentId"][:8])
                for k in ("kill_shot", "what_broke"):
                    if r.get(k):
                        print("     %s: %s" % (k, str(r[k])[:200]))
                for key in ("overblown", "survives"):
                    v = r.get(key)
                    if isinstance(v, list) and v:
                        print("     %s: %d건" % (key, len(v)))
                for fd in (r.get("findings") or [])[:4]:
                    sev = fd.get("severity", "")
                    print("     [%s] %s" % (sev, str(fd.get("claim", ""))[:150]))
                print()
    print("\n" + "=" * 72)
    if not VERBOSE:
        print("  자세히: python 도구/조사현황.py -v      자동갱신: -w")


if WATCH:
    try:
        while True:
            os.system("cls" if os.name == "nt" else "clear")
            show()
            time.sleep(10)
    except KeyboardInterrupt:
        pass
else:
    show()
