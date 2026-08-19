# -*- coding: utf-8 -*-
import json, urllib.parse, urllib.request, time, sys

FAMOUS = {
 "spirited_away":"센과 치히로","my_neighbor_totoro":"토토로","howl_s_moving_castle":"하울",
 "kiki_s_delivery_service":"키키","castle_in_the_sky":"라퓨타","princess_mononoke":"모노노케히메",
 "whisper_of_the_heart":"귀를 기울이면","only_yesterday":"추억은 방울방울",
 "the_secret_world_of_arrietty":"아리에티","the_cat_returns":"고양이의 보은",
 "from_up_on_poppy_hill":"코쿠리코","when_marnie_was_there":"마니","the_wind_rises":"바람이 분다",
 "grave_of_the_fireflies":"반딧불이의 묘","your_name":"너의 이름은","weathering_with_you":"날씨의 아이",
 "the_garden_of_words":"언어의 정원","demon_slayer___kimetsu_no_yaiba":"귀멸의 칼날",
 "death_note":"데스노트","fullmetal_alchemist_brotherhood":"강철의 연금술사","hunter_x_hunter":"헌터x헌터",
 "code_geass_season_1":"코드기어스","boku_no_hero_academia_season_1":"히로아카","steins_gate":"슈타인즈게이트",
 "sword_art_online":"소드아트온라인","frieren_beyond_journey_s_end":"프리렌",
 "re_zero___starting_life_in_another_world":"리제로","god_s_blessing_on_this_wonderful_world_":"코노스바",
 "assassination_classroom_season_1":"암살교실","your_lie_in_april":"4월은 너의 거짓말",
 "anohana_the_flower_we_saw_that_day":"아노하나","wolf_children":"늑대아이",
 "the_girl_who_leapt_through_time":"시간을 달리는 소녀","mahou_shoujo_madoka_magica":"마도카",
 "toradora_":"토라도라","clannad":"클라나드","clannad_after_story":"클라나드AS","k_on_":"케이온",
 "fairy_tail":"페어리테일","psycho_pass":"사이코패스","durarara__":"듀라라라",
}

def search(q, exact=True):
    url = ("https://apiv2.immersionkit.com/search?q=" + urllib.parse.quote(q)
           + ("&exactMatch=true" if exact else "") + "&limit=500")
    for _ in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "curl/8.0.1", "Accept": "*/*"})
            with urllib.request.urlopen(req, timeout=45) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception:
            time.sleep(2)
    return None

def run(rows, label):
    print("\n" + "="*78)
    print("  " + label)
    print("="*78)
    ok = 0
    for ko, ja in rows:
        d = search(ja)
        if d is None:
            print("  %-24s %-22s  조회실패" % (ko, ja)); continue
        anime = (d.get("deck_count") or {}).get("anime", {}) or {}
        drama = (d.get("deck_count") or {}).get("drama", {}) or {}
        tot = sum(anime.values())
        fam = {FAMOUS[k]: v for k, v in anime.items() if k in FAMOUS}
        famtot = sum(fam.values())
        if famtot: ok += 1
        top = ", ".join("%s %d" % (k, v) for k, v in sorted(fam.items(), key=lambda x: -x[1])[:5])
        print("  %-24s %-22s 전체%4d  유명작%3d  일드%3d  %s"
              % (ko, ja, tot, famtot, sum(drama.values()), top or "-"))
        time.sleep(0.4)
    print("  --> 유명작에서 클립 확보: %d / %d" % (ok, len(rows)))

식당 = [
 ("몇 분이세요","何名様"),("어서오세요","いらっしゃいませ"),("잠시만 기다려주세요","少々お待ちください"),
 ("주문하시겠어요","ご注文"),("이거 주세요","これをください"),("이거 뭐예요","これは何ですか"),
 ("맛있어요","おいしいです"),("잘 먹겠습니다","いただきます"),("잘 먹었습니다","ごちそうさま"),
 ("계산해주세요","お会計"),("얼마예요","いくらですか"),("물 좀 주세요","お水をください"),
 ("메뉴 주세요","メニューをください"),("추천이 뭐예요","おすすめは"),("포장해주세요","持ち帰り"),
]
가게 = [
 ("이거 어디 있어요","はどこですか"),("이거 있어요","ありますか"),("봉투 주세요","袋をください"),
 ("얼마예요","おいくらですか"),("괜찮아요","大丈夫です"),("이것 좀 보여주세요","見せてください"),
 ("이거로 할게요","これにします"),("좀 깎아주세요","安くして"),("영수증 주세요","レシート"),
 ("카드 되나요","カードで"),("죄송합니다","すみません"),("감사합니다","ありがとうございます"),
]
run(식당, "식당편")
run(가게, "가게·편의점편")
