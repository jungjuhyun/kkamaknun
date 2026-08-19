# -*- coding: utf-8 -*-
import json, urllib.parse, urllib.request, time
exec(open('match.py',encoding='utf-8').read().split('def run(')[0])

def probe(ja):
    d = search(ja)
    if d is None: return None
    a = (d.get("deck_count") or {}).get("anime", {}) or {}
    dr = (d.get("deck_count") or {}).get("drama", {}) or {}
    fam = {FAMOUS[k]: v for k, v in a.items() if k in FAMOUS}
    return sum(a.values()), sum(fam.values()), sum(dr.values()), fam

def run2(rows, label):
    print("\n" + "=" * 96)
    print("  " + label)
    print("=" * 96)
    ok = 0
    for ko, cands in rows:
        best = None
        for ja in cands:
            r = probe(ja)
            time.sleep(0.3)
            if r and (best is None or r[1] > best[1][1]): best = (ja, r)
            if r and r[1] >= 8: break
        if not best: print("  %-22s 조회실패" % ko); continue
        ja, (tot, famtot, drtot, fam) = best
        if famtot: ok += 1
        top = ", ".join("%s %d" % (k, v) for k, v in sorted(fam.items(), key=lambda x: -x[1])[:6])
        mark = "O" if famtot >= 3 else ("△" if famtot else "X")
        print("  %s %-22s %-16s 전체%5d 유명작%4d 일드%4d  %s" % (mark, ko, ja, tot, famtot, drtot, top or "-"))
    print("  ---> 유명작 3컷 이상 확보: %d / %d" % (ok, len(rows)))

식당2 = [
 ("어서오세요",["いらっしゃいませ"]),
 ("몇 분이세요",["何名様","何名"]),
 ("잠시만 기다려주세요",["お待ちください","少々お待ち"]),
 ("주문하시겠어요",["ご注文","注文"]),
 ("이거 주세요",["これください","ください"]),
 ("이거 뭐예요",["これは何","何ですか"]),
 ("맛있어요",["おいしい","うまい"]),
 ("잘 먹겠습니다",["いただきます"]),
 ("잘 먹었습니다",["ごちそうさま"]),
 ("계산해주세요",["お会計","会計"]),
 ("얼마예요",["いくら"]),
 ("물 주세요",["お水","水を"]),
 ("메뉴",["メニュー"]),
 ("추천이 뭐예요",["おすすめ"]),
 ("포장해주세요",["持ち帰り","お持ち帰り"]),
]
가게2 = [
 ("어디 있어요",["どこですか","どこ"]),
 ("있어요?",["ありますか"]),
 ("봉투 주세요",["袋"]),
 ("보여주세요",["見せて"]),
 ("이걸로 할게요",["これにします","にします"]),
 ("카드 되나요",["カード"]),
 ("죄송합니다",["すみません"]),
 ("감사합니다",["ありがとうございます"]),
 ("괜찮아요",["大丈夫です","大丈夫"]),
 ("부탁드립니다",["お願いします"]),
 ("영수증",["レシート","領収書"]),
 ("깎아주세요",["安くして","まけて"]),
]
run2(식당2, "식당편")
run2(가게2, "가게·편의점편")
