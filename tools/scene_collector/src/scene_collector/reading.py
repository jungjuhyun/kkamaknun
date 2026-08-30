"""가나 읽기를 한국 학습자가 소리 내어 읽을 수 있는 한글로 바꾼다.

표시 전용이다. DB에 저장된 `expressions.reading` 값은 바꾸지 않는다.

국립국어원 외래어 표기법이 아니라 학습자가 소리를 짐작할 수 있는 표기를 쓴다.
표기법대로면 だいじょうぶです가 "다이조부데스", かまいません이 "가마이마센"이
되지만, 여기서는 무성 か·た·ぱ행을 위치와 무관하게 ㅋ·ㅌ·ㅍ로, つ를 츠로,
じょ를 죠로 적어 "다이죠부데스", "카마이마센"이 되게 한다.

형태소 정보가 없어서 생기는 한계가 셋 있다. 셋 다 표시에만 영향을 준다.

- おもう → 오모: 동사 어미 う와 장음 う를 구분할 수 없다. だいじょうぶ를
  다이죠부로 적는 규칙과 같은 규칙에서 나온다.
- それはちょっと → 소레하춋토: 조사 は·へ의 발음은 알 수 없다. こんにちは
  같은 굳어진 인사말만 예외로 둔다.
- おおきい → 오키이: おお도 장음으로 접는다.
"""

from __future__ import annotations

import unicodedata

# 가타카나를 히라가나로 접을 때 쓰는 거리. ぁ(U+3041)와 ァ(U+30A1)의 차이다.
_KATAKANA_OFFSET = 0x60
_KATAKANA_RANGE = range(0x30A1, 0x30F7)

_HANGUL_BASE = 0xAC00
_JUNGSEONG_COUNT = 21
_JONGSEONG_COUNT = 28
_JONGSEONG_NIEUN = 4
_JONGSEONG_SIOT = 19

_LONG_VOWEL_MARKS = "ー〜~"
_SOKUON = "っ"
_HATSUON = "ん"

# 굳어진 인사말에서만 끝 は를 조사로 읽는다. 일반 규칙으로 넓히지 않는다.
# 앞부분은 일반 규칙 그대로이고 끝 は만 와가 된다.
_PARTICLE_HA_WORDS = {"こんにちは": "콘니치와", "こんばんは": "콘반와"}

# 가나 한 글자 → (한글 음절, 모음). 모음은 장음 판정에만 쓴다.
_SINGLE: dict[str, tuple[str, str]] = {
    "あ": ("아", "a"), "い": ("이", "i"), "う": ("우", "u"), "え": ("에", "e"), "お": ("오", "o"),
    "か": ("카", "a"), "き": ("키", "i"), "く": ("쿠", "u"), "け": ("케", "e"), "こ": ("코", "o"),
    "が": ("가", "a"), "ぎ": ("기", "i"), "ぐ": ("구", "u"), "げ": ("게", "e"), "ご": ("고", "o"),
    "さ": ("사", "a"), "し": ("시", "i"), "す": ("스", "u"), "せ": ("세", "e"), "そ": ("소", "o"),
    "ざ": ("자", "a"), "じ": ("지", "i"), "ず": ("즈", "u"), "ぜ": ("제", "e"), "ぞ": ("조", "o"),
    "た": ("타", "a"), "ち": ("치", "i"), "つ": ("츠", "u"), "て": ("테", "e"), "と": ("토", "o"),
    "だ": ("다", "a"), "ぢ": ("지", "i"), "づ": ("즈", "u"), "で": ("데", "e"), "ど": ("도", "o"),
    "な": ("나", "a"), "に": ("니", "i"), "ぬ": ("누", "u"), "ね": ("네", "e"), "の": ("노", "o"),
    "は": ("하", "a"), "ひ": ("히", "i"), "ふ": ("후", "u"), "へ": ("헤", "e"), "ほ": ("호", "o"),
    "ば": ("바", "a"), "び": ("비", "i"), "ぶ": ("부", "u"), "べ": ("베", "e"), "ぼ": ("보", "o"),
    "ぱ": ("파", "a"), "ぴ": ("피", "i"), "ぷ": ("푸", "u"), "ぺ": ("페", "e"), "ぽ": ("포", "o"),
    "ま": ("마", "a"), "み": ("미", "i"), "む": ("무", "u"), "め": ("메", "e"), "も": ("모", "o"),
    "や": ("야", "a"), "ゆ": ("유", "u"), "よ": ("요", "o"),
    "ら": ("라", "a"), "り": ("리", "i"), "る": ("루", "u"), "れ": ("레", "e"), "ろ": ("로", "o"),
    "わ": ("와", "a"), "ゐ": ("이", "i"), "ゑ": ("에", "e"), "を": ("오", "o"),
    "ゔ": ("부", "u"),
    "ぁ": ("아", "a"), "ぃ": ("이", "i"), "ぅ": ("우", "u"), "ぇ": ("에", "e"), "ぉ": ("오", "o"),
    "ゃ": ("야", "a"), "ゅ": ("유", "u"), "ょ": ("요", "o"), "ゎ": ("와", "a"),
    "ゕ": ("카", "a"), "ゖ": ("케", "e"),
}

# 요음과 외래음. 두 글자를 한 음절로 읽는다.
_DOUBLE: dict[str, tuple[str, str]] = {
    "きゃ": ("캬", "a"), "きゅ": ("큐", "u"), "きょ": ("쿄", "o"),
    "ぎゃ": ("갸", "a"), "ぎゅ": ("규", "u"), "ぎょ": ("교", "o"),
    "しゃ": ("샤", "a"), "しゅ": ("슈", "u"), "しょ": ("쇼", "o"), "しぇ": ("셰", "e"),
    "じゃ": ("쟈", "a"), "じゅ": ("쥬", "u"), "じょ": ("죠", "o"), "じぇ": ("제", "e"),
    "ちゃ": ("챠", "a"), "ちゅ": ("츄", "u"), "ちょ": ("쵸", "o"), "ちぇ": ("체", "e"),
    "にゃ": ("냐", "a"), "にゅ": ("뉴", "u"), "にょ": ("뇨", "o"),
    "ひゃ": ("햐", "a"), "ひゅ": ("휴", "u"), "ひょ": ("효", "o"),
    "びゃ": ("뱌", "a"), "びゅ": ("뷰", "u"), "びょ": ("뵤", "o"),
    "ぴゃ": ("퍄", "a"), "ぴゅ": ("퓨", "u"), "ぴょ": ("표", "o"),
    "みゃ": ("먀", "a"), "みゅ": ("뮤", "u"), "みょ": ("묘", "o"),
    "りゃ": ("랴", "a"), "りゅ": ("류", "u"), "りょ": ("료", "o"),
    "ふぁ": ("파", "a"), "ふぃ": ("피", "i"), "ふぇ": ("페", "e"), "ふぉ": ("포", "o"),
    "ふゅ": ("퓨", "u"),
    "うぃ": ("위", "i"), "うぇ": ("웨", "e"), "うぉ": ("워", "o"),
    "てぃ": ("티", "i"), "てゅ": ("튜", "u"), "とぅ": ("투", "u"),
    "でぃ": ("디", "i"), "でゅ": ("듀", "u"), "どぅ": ("두", "u"),
    "ゔぁ": ("바", "a"), "ゔぃ": ("비", "i"), "ゔぇ": ("베", "e"), "ゔぉ": ("보", "o"),
    "ゔゅ": ("뷰", "u"),
}


def korean_reading(reading: str) -> str:
    """가나 읽기를 학습자용 한글 표기로 바꾼다.

    어떤 입력에도 예외를 내지 않는다. 아는 가나만 바꾸고 나머지는 그대로 둔다.
    """
    kana = _to_hiragana(reading)
    if not kana:
        return ""
    fixed = _PARTICLE_HA_WORDS.get(kana)
    if fixed is not None:
        return fixed

    syllables: list[str] = []
    previous_vowel = ""
    index = 0
    while index < len(kana):
        character = kana[index]

        if character in _LONG_VOWEL_MARKS:
            # 장음은 따로 적지 않는다. 코ー히ー는 코히다.
            index += 1
            continue

        if character == _SOKUON:
            _append_final(syllables, _JONGSEONG_SIOT)
            previous_vowel = ""
            index += 1
            continue

        if character == _HATSUON:
            _append_final(syllables, _JONGSEONG_NIEUN)
            previous_vowel = ""
            index += 1
            continue

        if character == "う" and previous_vowel in {"o", "u"}:
            # お단·う단 뒤의 う는 장음이라 적지 않는다. だいじょうぶ는 다이죠부다.
            index += 1
            continue
        if character == "お" and previous_vowel == "o":
            index += 1
            continue

        pair = _DOUBLE.get(kana[index : index + 2])
        if pair is not None:
            syllables.append(pair[0])
            previous_vowel = pair[1]
            index += 2
            continue

        single = _SINGLE.get(character)
        if single is not None:
            syllables.append(single[0])
            previous_vowel = single[1]
            index += 1
            continue

        # 모르는 문자는 그대로 통과시킨다.
        syllables.append(character)
        previous_vowel = ""
        index += 1

    return "".join(syllables)


def _to_hiragana(text: str) -> str:
    """NFKC로 정리한 뒤 가타카나를 히라가나로 접는다."""
    normalized = unicodedata.normalize("NFKC", text or "").strip()
    return "".join(
        chr(ord(character) - _KATAKANA_OFFSET)
        if ord(character) in _KATAKANA_RANGE
        else character
        for character in normalized
    )


def _append_final(syllables: list[str], final: int) -> None:
    """앞 음절에 받침을 붙인다. 붙일 자리가 없으면 아무것도 하지 않는다."""
    if not syllables:
        return
    offset = ord(syllables[-1]) - _HANGUL_BASE
    if not 0 <= offset < _JUNGSEONG_COUNT * _JONGSEONG_COUNT * 19:
        return
    if offset % _JONGSEONG_COUNT:
        # 이미 받침이 있으면 덮어쓰지 않는다.
        return
    syllables[-1] = chr(_HANGUL_BASE + offset + final)
