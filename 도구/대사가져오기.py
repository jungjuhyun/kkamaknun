# -*- coding: utf-8 -*-
"""표현의 실제 대사·번역·이미지·음성 주소를 뽑는다 (ImmersionKit, 메이저작만).

  python 도구/대사가져오기.py おはよう [개수]
"""
import json, os, sys, urllib.parse, urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from 작품군 import 메이저, 미디어폴더

UA = {"User-Agent": "curl/8.0.1"}
미디어 = "https://us-southeast-1.linodeobjects.com/immersionkit/media/anime/%s/media/%s"


def main(q, n):
    url = ("https://apiv2.immersionkit.com/search?q="
           + urllib.parse.quote(q) + "&exactMatch=true&limit=500")
    req = urllib.request.Request(url, headers=UA)
    d = json.load(urllib.request.urlopen(req, timeout=60))
    예문 = [e for e in (d.get("examples") or []) if e.get("title") in 메이저]
    print("「%s」 메이저작 예문 %d개 중 %d개 표시\n" % (q, len(예문), min(n, len(예문))))
    for e in 예문[:n]:
        deck = e["title"]
        폴더 = 미디어폴더.get(deck)
        print("[%s] %s" % (메이저[deck], (e.get("sentence") or "").strip()))
        print("     %s" % (e.get("translation") or "").strip())
        if 폴더:
            f = urllib.parse.quote(폴더)
            print("     이미지: " + 미디어 % (f, urllib.parse.quote(e.get("image") or "")))
            print("     음성  : " + 미디어 % (f, urllib.parse.quote(e.get("sound") or "")))
        else:
            print("     (폴더명 미확인 작품 — immersionkit.com 화면에서 받는다. 파일명: %s)"
                  % (e.get("image") or ""))
        print()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(0)
    main(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 8)
