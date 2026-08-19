# -*- coding: utf-8 -*-
import json, time
exec(open('match.py',encoding='utf-8').read().split('def run(')[0])

WANT = [("어서오세요","いらっしゃいませ"),("잠시만 기다려주세요","お待ちください"),
        ("주문하시겠어요","ご注文"),("맛있어요","おいしい"),("잘 먹겠습니다","いただきます"),
        ("잘 먹었습니다","ごちそうさま"),("얼마예요","いくら"),("물 주세요","水を"),
        ("추천","おすすめ"),("메뉴","メニュー")]

print("식당편 — 유명작 실제 대사\n")
for ko, ja in WANT:
    d = search(ja)
    if not d: print("## %s (%s) 실패\n" % (ko, ja)); continue
    ex = d.get("examples") or []
    picked = [e for e in ex if e.get("title") in FAMOUS][:6]
    print("## %s  「%s」   유명작 예문 %d개 중 6개" % (ko, ja, len([e for e in ex if e.get("title") in FAMOUS])))
    for e in picked:
        s = (e.get("sentence") or "").strip()
        t = (e.get("translation") or "").strip()[:70]
        print("   [%s] %s" % (FAMOUS.get(e.get("title"),"?"), s))
        print("        %s" % t)
    print()
    time.sleep(0.4)
