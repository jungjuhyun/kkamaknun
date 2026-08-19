# -*- coding: utf-8 -*-
"""Nadeshiko 문장 검색 — 대사·작품·회차·클립(mp4) 주소를 뽑는다.

  python 도구/나데시코검색.py ありがとう

로그인 없이 검색 결과 페이지에 보이는 상위 30건까지만.
mp4는 공식 다운로드 기능이 아니라 플레이어가 재생하는 원본 주소다 —
사이트가 주소 체계를 바꾸면 막힐 수 있다 (실측/Nadeshiko_mp4실측.txt).
"""
import re, sys, urllib.parse, urllib.request

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"}


def 태그제거(html):
    html = re.sub(r"<rt>.*?</rt>", "", html, flags=re.S)     # 후리가나 제거
    html = re.sub(r"<[^>]+>", "\n", html)
    return [l.strip() for l in html.split("\n") if l.strip()]


def main(q):
    url = "https://nadeshiko.co/en/search/" + urllib.parse.quote(q)
    req = urllib.request.Request(url, headers=UA)
    h = urllib.request.urlopen(req, timeout=60).read().decode("utf-8", "replace")
    카드들 = h.split('data-testid="segment-card"')[1:]
    print("「%s」 — 화면 상위 %d건\n" % (q, len(카드들)))
    for i, c in enumerate(카드들, 1):
        작품 = re.search(r'alt="Screenshot for ([^"]+)"', c)
        mp4 = re.search(r'(https://cdn\.nadeshiko\.co/[A-Za-z0-9/._-]+\.mp4)', c)
        if not mp4:
            # 카드 스틸(webp)과 클립(mp4)은 같은 주소에 확장자만 다르다 (실측 확인)
            w = re.search(r'src="(https://cdn\.nadeshiko\.co/[A-Za-z0-9/._-]+)\.webp"', c)
            if w:
                mp4 = re.match(r"(.*)", w.group(1) + ".mp4")
        줄들 = 태그제거(c)
        # 일본어 대사: 가나·한자가 든 첫 줄
        일 = next((l for l in 줄들 if re.search(r"[\u3040-\u30ff\u4e00-\u9fff]", l) and len(l) >= 2), "")
        # 영어 번역: EN 표시 다음 줄
        영 = ""
        for j, l in enumerate(줄들):
            if l == "EN" and j + 1 < len(줄들):
                영 = 줄들[j + 1]
                break
        # 회차·타임코드
        회차 = next((l for l in 줄들 if re.search(r"Episode \d+", l)), "")
        print("%2d. [%s] %s" % (i, 작품.group(1) if 작품 else "?", 일))
        if 영:
            print("      %s" % 영[:80])
        if 회차:
            print("      %s" % 회차)
        if mp4:
            print("      클립: %s" % mp4.group(1))
        print()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(0)
    main(sys.argv[1])
