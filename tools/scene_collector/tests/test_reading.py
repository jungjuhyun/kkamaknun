"""가나 읽기를 학습자용 한글 표기로 바꾸는 규칙을 고정한다."""

import pytest

from scene_collector.reading import korean_reading

# 사용자가 요구한 최소 기대 표기. 국립국어원 표기법과는 다르다.
REQUIRED = [
    ("だいじょうぶです", "다이죠부데스"),
    ("けっこうです", "켓코데스"),
    ("かまいません", "카마이마센"),
    ("もんだいありません", "몬다이아리마센"),
    ("へいきです", "헤이키데스"),
    ("さしつかえありません", "사시츠카에아리마센"),
]


@pytest.mark.parametrize(("kana", "expected"), REQUIRED)
def test_required_learner_readings(kana: str, expected: str) -> None:
    assert korean_reading(kana) == expected


def test_unvoiced_rows_are_aspirated_everywhere() -> None:
    """표기법과 달리 어두에서도 か·た·ぱ행을 ㅋ·ㅌ·ㅍ로 적는다."""
    assert korean_reading("かたな") == "카타나"
    assert korean_reading("ときょう") == "토쿄"
    assert korean_reading("ぱん") == "판"
    # 탁음은 그대로 ㄱ·ㄷ·ㅂ다.
    assert korean_reading("がっこう") == "갓코"
    assert korean_reading("だいがく") == "다이가쿠"


def test_long_vowels_are_not_written() -> None:
    """お단·う단 뒤 う와 장음부호는 적지 않는다."""
    assert korean_reading("とうきょう") == "토쿄"
    assert korean_reading("がっこう") == "갓코"
    assert korean_reading("すうじ") == "스지"
    assert korean_reading("おおきい") == "오키이"
    assert korean_reading("コーヒー") == "코히"
    # え단 뒤 い는 이로 적는다.
    assert korean_reading("へいき") == "헤이키"
    assert korean_reading("せんせい") == "센세이"
    # あ단 뒤 う는 장음이 아니다.
    assert korean_reading("かう") == "카우"


def test_sokuon_becomes_a_siot_final() -> None:
    assert korean_reading("いっぱい") == "잇파이"
    assert korean_reading("けっか") == "켓카"
    assert korean_reading("ちょっと") == "춋토"


def test_hatsuon_becomes_a_nieun_final() -> None:
    assert korean_reading("こんばん") == "콘반"
    assert korean_reading("あんない") == "안나이"
    assert korean_reading("ほん") == "혼"


def test_youon_is_one_syllable() -> None:
    assert korean_reading("じょじょ") == "죠죠"
    assert korean_reading("しゃしん") == "샤신"
    assert korean_reading("きょうしつ") == "쿄시츠"
    assert korean_reading("りゅうがく") == "류가쿠"


def test_katakana_and_foreign_sounds() -> None:
    assert korean_reading("ラーメン") == "라멘"
    assert korean_reading("ファイト") == "파이토"
    assert korean_reading("ヴィオラ") == "비오라"
    assert korean_reading("ティーシャツ") == "티샤츠"
    # 히라가나와 가타카나가 섞여도 같은 규칙을 쓴다.
    assert korean_reading("チェックです") == "쳇쿠데스"


def test_fixed_greetings_read_the_particle_ha() -> None:
    """굳어진 인사말에서만 끝 は를 조사로 읽는다."""
    assert korean_reading("こんにちは") == "콘니치와"
    assert korean_reading("こんばんは") == "콘반와"
    # 일반 규칙으로 넓히지 않는다 — 조사 は는 형태소 정보 없이 알 수 없다.
    assert korean_reading("はなし") == "하나시"


def test_known_limits_are_accepted_on_purpose() -> None:
    """형태소 정보가 없어 생기는 한계. 고쳐야 할 결함이 아니라 알려진 제한이다."""
    # 동사 어미 う와 장음 う를 구분할 수 없다.
    assert korean_reading("おもう") == "오모"
    # 조사 は는 그대로 하로 읽는다.
    assert korean_reading("それはちょっと") == "소레하춋토"


def test_empty_and_unknown_input() -> None:
    assert korean_reading("") == ""
    assert korean_reading("   ") == ""
    # 가나가 아닌 글자는 그대로 통과한다.
    assert korean_reading("大丈夫") == "大丈夫"
    # NFKC가 전각 물음표를 반각으로 접는다.
    assert korean_reading("だいじょうぶ？") == "다이죠부?"


def test_never_raises_for_any_kana_block_character() -> None:
    """어떤 입력에도 예외를 내지 않는다. 화면 표시 중에 터지면 안 된다."""
    for code_point in range(0x3000, 0x3100):
        korean_reading(chr(code_point))
    for code_point in range(0xFF61, 0xFFA0):  # 반각 가타카나
        korean_reading(chr(code_point))
    for stray in ("っ", "ん", "ー", "っっ", "んん", "ーー", "っん"):
        korean_reading(stray)
