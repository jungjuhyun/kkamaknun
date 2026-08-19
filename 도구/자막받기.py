# -*- coding: utf-8 -*-
"""kitsunekko에서 회차별 일본어 자막(srt)을 받는다.

  python 도구/자막받기.py "Jujutsu Kaisen"          작품 검색 -> 폴더·파일 목록
  python 도구/자막받기.py "Jujutsu Kaisen" 받기      전부 내려받기 (자막/<작품>/ 에 저장)

색인(Nadeshiko·ImmersionKit)에 없는 작품에서 표현을 찾을 때 쓴다.
자막은 텍스트만이다 — 클립·영상은 별도 확보 필요.
"""
import os, re, sys, time, urllib.parse, urllib.request

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
      "Referer": "https://kitsunekko.net/"}
BASE = "https://kitsunekko.net"


def 받기(url):
    req = urllib.request.Request(url, headers=UA)
    return urllib.request.urlopen(req, timeout=60).read()


def 폴더찾기(이름):
    h = 받기(BASE + "/dirlist.php?dir=subtitles%2Fjapanese%2F").decode("utf-8", "replace")
    rows = re.findall(r'href="(/dirlist\.php\?dir=[^"]+)"[^>]*>(?:<[^>]+>)*([^<]+)', h)
    return [(u, urllib.parse.unquote(n).strip()) for u, n in rows
            if 이름.lower() in urllib.parse.unquote(n).lower()]


def 파일목록(dir_url):
    h = 받기(BASE + dir_url).decode("utf-8", "replace")
    return re.findall(r'href="(subtitles/[^"]+\.(?:srt|ass|ssa|zip|rar|7z))"', h)


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return
    이름 = sys.argv[1]
    내려받기 = len(sys.argv) > 2 and sys.argv[2] == "받기"
    폴더들 = 폴더찾기(이름)
    if not 폴더들:
        print("「%s」 — 없음. 로마자 제목으로 검색하라 (예: Kimetsu, Jujutsu, Atashin)" % 이름)
        return
    for u, n in 폴더들:
        파일들 = 파일목록(u)
        print("\n[%s] 파일 %d개" % (n, len(파일들)))
        for f in 파일들[:40]:
            print("   " + urllib.parse.unquote(f).split("/")[-1])
        if 내려받기:
            대상 = os.path.join("자막", n)
            os.makedirs(대상, exist_ok=True)
            for f in 파일들:
                기본 = urllib.parse.unquote(f).split("/")[-1]
                경로 = os.path.join(대상, 기본)
                if os.path.exists(경로):
                    continue
                data = 받기(BASE + "/" + urllib.parse.quote(urllib.parse.unquote(f)))
                open(경로, "wb").write(data)
                print("   받음 %s (%d바이트)" % (기본, len(data)))
                time.sleep(0.5)


if __name__ == "__main__":
    main()
