# -*- coding: utf-8 -*-
"""작품군 정의 — 유일한 정의처. 다른 도구가 전부 여기서 가져다 쓴다.

기준 (계획.md 4-3):
  1. 진짜 메이저작 — 라프텔 역대 인기 100위에 든 프랜차이즈
  2. 극장 흥행 상위작 — 한국 관객수 상위
"""

# ImmersionKit 색인 안의 메이저작 (deck id -> 한글)
소년만화 = {
    "demon_slayer___kimetsu_no_yaiba": "귀멸의 칼날",
    "boku_no_hero_academia_season_1": "히로아카",
    "fullmetal_alchemist_brotherhood": "강철의 연금술사",
    "assassination_classroom_season_1": "암살교실",
    "sword_art_online": "소드아트온라인",
    "re_zero___starting_life_in_another_world": "리제로",
    "death_note": "데스노트",
    "steins_gate": "슈타인즈게이트",
    "frieren_beyond_journey_s_end": "프리렌",
}

극장판 = {
    "your_name": "너의 이름은",
    "weathering_with_you": "날씨의 아이",
    "the_garden_of_words": "언어의 정원",
    "spirited_away": "센과 치히로",
    "my_neighbor_totoro": "토토로",
    "howl_s_moving_castle": "하울의 움직이는 성",
    "kiki_s_delivery_service": "마녀배달부 키키",
    "castle_in_the_sky": "천공의 성 라퓨타",
    "princess_mononoke": "모노노케 히메",
    "grave_of_the_fireflies": "반딧불이의 묘",
    "whisper_of_the_heart": "귀를 기울이면",
    "only_yesterday": "추억은 방울방울",
    "the_wind_rises": "바람이 분다",
    "the_secret_world_of_arrietty": "마루 밑 아리에티",
    "when_marnie_was_there": "추억의 마니",
    "from_up_on_poppy_hill": "코쿠리코 언덕에서",
    "the_cat_returns": "고양이의 보은",
}

메이저 = dict(소년만화)
메이저.update(극장판)

# Nadeshiko 수록작 판별 키워드 (영문 제목 소문자 부분일치)
나데시코_메이저 = [
    "jujutsu", "demon slayer", "death note", "frieren", "spy x family",
    "chainsaw", "one piece", "bleach", "my hero academia", "fullmetal",
    "assassination classroom", "sword art", "re:zero", "steins", "oshi no ko",
    "mushoku", "dress-up darling", "dan da dan", "kaiju no", "solo leveling",
    "kaguya", "bocchi", "dragon maid", "bungo stray", "shield hero",
    "reincarnated as a slime", "86 eighty", "your name", "suzume", "howl",
    "boy and the heron", "silent voice", "grave of the fireflies",
    "whisper of the heart", "girl who leapt", "summer wars", "only yesterday",
    "poppy hill",
]

# ImmersionKit 미디어 폴더명 (2026-08-19 실측 — 후보 순회로 200 확인)
# None = 폴더명 미확인(403). 그 작품은 immersionkit.com 화면에서 받는다.
미디어폴더 = {
    "demon_slayer___kimetsu_no_yaiba": "Demon Slayer - Kimetsu no Yaiba",
    "boku_no_hero_academia_season_1": "Boku no Hero Academia Season 1",
    "fullmetal_alchemist_brotherhood": "Fullmetal Alchemist Brotherhood",
    "assassination_classroom_season_1": "Assassination Classroom Season 1",
    "sword_art_online": "Sword Art Online",
    "re_zero___starting_life_in_another_world": None,
    "death_note": "Death Note",
    "steins_gate": "Steins Gate",
    "frieren_beyond_journey_s_end": "Frieren Beyond Journey's End",
    "your_name": "Your Name",
    "weathering_with_you": "Weathering with You",
    "the_garden_of_words": "The Garden of Words",
    "spirited_away": "Spirited Away",
    "my_neighbor_totoro": "My Neighbor Totoro",
    "howl_s_moving_castle": "Howl's Moving Castle",
    "kiki_s_delivery_service": "Kiki's Delivery Service",
    "castle_in_the_sky": None,
    "princess_mononoke": "Princess Mononoke",
    "grave_of_the_fireflies": "Grave of the Fireflies",
    "whisper_of_the_heart": "Whisper of the Heart",
    "only_yesterday": "Only Yesterday",
    "the_wind_rises": "The Wind Rises",
    "the_secret_world_of_arrietty": "The Secret World of Arrietty",
    "when_marnie_was_there": "When Marnie Was There",
    "from_up_on_poppy_hill": "From Up on Poppy Hill",
    "the_cat_returns": "The Cat Returns",
}
