# -*- coding: utf-8 -*-
"""한 뜻의 말투 버전들이 작품군별로 몇 컷 나오는지 잰다 (ImmersionKit 전수 카운트).

  python 도구/표현모으기.py 안녕 おはよう こんにちは やあ 久しぶり ただいま
"""
import json, os, sys, time, urllib.parse, urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from 작품군 import 소년만화, 극장판

UA = {"User-Agent": "curl/8.0.1"}


def 검색(q):
    url = ("https://apiv2.immersionkit.com/search?q="
           + urllib.parse.quote(q) + "&exactMatch=true&limit=1")
    for t in range(4):
        try:
            req = urllib.request.Request(url, headers=UA)
            d = json.load(urllib.request.urlopen(req, timeout=50))
            return (d.get("deck_count") or {}).get("anime", {}) or {}
        except Exception:
            time.sleep(2 + 2 * t)
    return None


def 표(뜻, 버전들):
    print("=" * 96)
    print("  %s — 버전 %d개" % (뜻, len(버전들)))
    print("=" * 96)
    소년ok = 극장ok = 0
    for ja in 버전들:
        a = 검색(ja)
        if a is None:
            print("  %-16s 조회실패" % ja)
            continue
        소 = {소년만화[k]: v for k, v in a.items() if k in 소년만화}
        극 = {극장판[k]: v for k, v in a.items() if k in 극장판}
        if sum(소.values()):
            소년ok += 1
        if sum(극.values()):
            극장ok += 1
        s = ", ".join("%s%d" % kv for kv in sorted(소.items(), key=lambda x: -x[1])[:4])
        g = ", ".join("%s%d" % kv for kv in sorted(극.items(), key=lambda x: -x[1])[:4])
        print("  %-14s 전체%5d | 소년만화%4d  %-38s | 극장판%4d  %s"
              % (ja, sum(a.values()), sum(소.values()), s[:38], sum(극.values()), g[:42]))
        time.sleep(0.5)
    print("  --> 소년만화군에서 잡히는 버전 %d/%d, 극장판군 %d/%d"
          % (소년ok, len(버전들), 극장ok, len(버전들)))


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(0)
    표(sys.argv[1], sys.argv[2:])
