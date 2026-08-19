# -*- coding: utf-8 -*-
"""채널의 편별 조회수를 긁는다 (유튜브 채널 페이지 직접 조회).

  python 도구/유튜브실적.py @애니일본어 [@말이라도잘해야지 ...]

주의: "1.5만회" 같은 축약 표기를 숫자로 환산한다. 멤버십 전용 영상은 0으로 찍힌다 —
조회수 0이 아니라 비공개이니 그 숫자로 판정하지 마라 (실측/경쟁채널_편별조회수.txt 머리글 참조).
"""
import json, re, statistics, sys, time, urllib.parse, urllib.request

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
      "Accept-Language": "ko-KR,ko;q=0.9"}


def get(u):
    for t in range(3):
        try:
            req = urllib.request.Request(u, headers=UA)
            return urllib.request.urlopen(req, timeout=45).read().decode("utf-8", "replace")
        except Exception:
            time.sleep(3)
    return ""


def walk(o, key):
    if isinstance(o, dict):
        for k, v in o.items():
            if k == key:
                yield v
            yield from walk(v, key)
    elif isinstance(o, list):
        for v in o:
            yield from walk(v, key)


def 숫자(s):
    s = (s or "").replace("조회수", "")
    m = re.search(r"([\d,]+(?:\.\d+)?)\s*(억|만|천)?", s)
    if not m:
        return 0
    v = float(m.group(1).replace(",", ""))
    단위 = m.group(2)
    if 단위 == "억":
        v *= 100000000
    elif 단위 == "만":
        v *= 10000
    elif 단위 == "천":
        v *= 1000
    return int(v)


def 채널(handle):
    h = get("https://www.youtube.com/" + urllib.parse.quote(handle) + "/videos")
    m = re.search(r"var ytInitialData = (\{.*?\});</script>", h, re.S)
    if not m:
        return [], ""
    d = json.loads(m.group(1))
    구독 = ""
    mm = re.search(r'"구독자 ([^"]+)"', m.group(1))
    if mm:
        구독 = "구독자 " + mm.group(1)
    rows = []
    for lm in walk(d, "lockupMetadataViewModel"):
        t = (lm.get("title") or {}).get("content", "")
        조회 = 게시 = ""
        for mr in walk(lm.get("metadata") or {}, "metadataParts"):
            for p in mr:
                c = ((p or {}).get("text") or {}).get("content", "")
                if "조회수" in c:
                    조회 = c
                elif c.endswith("전"):
                    게시 = c
        if t:
            rows.append((t, 숫자(조회), 게시))
    return rows, 구독


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return
    for handle in sys.argv[1:]:
        rows, 구독 = 채널(handle)
        if not rows:
            print("%s -> 못 긁음" % handle)
            continue
        print("\n" + "=" * 100)
        print("  %s  %s   최신순 %d개" % (handle, 구독, len(rows)))
        print("=" * 100)
        for t, v, p in rows[:20]:
            print("  %9s  %-8s %s" % (format(v, ","), p, t[:70]))
        vs = [v for _, v, _ in rows if v]
        if vs:
            print("  --- 중앙값 %s  최고 %s  최저 %s  (0 제외 표본 %d)"
                  % (format(int(statistics.median(vs)), ","), format(max(vs), ","),
                     format(min(vs), ","), len(vs)))
        time.sleep(1.5)


if __name__ == "__main__":
    main()
