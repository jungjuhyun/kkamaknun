import pytest

from scene_collector.surface import matches_surface


@pytest.mark.parametrize(
    ("target", "source"),
    (
        ("悪い", "気持ち悪い"),
        ("ほんとそれ", "ほんと? それって甘い?"),
        ("ん？なんて？", "マンガ描けません なんて なるなよな"),
        ("今、何してるんですか？", "今 どこに寝泊まりしてるんです?"),
        ("大丈夫ですか？", "大丈夫？"),
        ("大丈夫ですか？", "大丈夫だよ"),
        ("大丈夫ですか？", "大丈夫なんですか？"),
        ("大丈夫ですか？", "大丈夫ですかね？"),
    ),
)
def test_rejects_partial_matches_and_grammar_variants(target: str, source: str) -> None:
    assert matches_surface(source, target) is False


@pytest.mark.parametrize(
    ("target", "source"),
    (
        ("大丈夫ですか？", "大丈夫ですか?"),
        ("大丈夫ですか？", "あの、大丈夫ですか？"),
        ("大丈夫ですか？", "本当に大丈夫ですか？"),
        ("もう一回言って。", "もう一回 言って。"),
        ("もう一回言って。", "もう一回言って"),
        ("もう一回言って。", "もう一回言って!"),
        ("ガンバレ！", "ｶﾞﾝﾊﾞﾚ!"),
        ("がんばって", "か\N{COMBINING KATAKANA-HIRAGANA VOICED SOUND MARK}んばって"),
    ),
)
def test_accepts_same_surface_with_notational_differences(target: str, source: str) -> None:
    assert matches_surface(source, target) is True


def test_keeps_internal_punctuation_as_an_expression_boundary() -> None:
    assert matches_surface("ほんと？ それ", "ほんとそれ") is False


def test_short_surface_can_follow_an_actual_text_boundary() -> None:
    assert matches_surface("それは 悪い。", "悪い") is True


def test_uses_existing_top_level_token_spans_as_word_boundaries() -> None:
    assert (
        matches_surface(
            "本当に悪い。",
            "悪い",
            token_spans=((0, 3), (3, 5), (5, 6)),
        )
        is True
    )
    assert (
        matches_surface(
            "気持ち悪い。",
            "悪い",
            token_spans=((0, 5), (5, 6)),
        )
        is False
    )


def test_whitespace_does_not_split_a_top_level_compound_token() -> None:
    assert (
        matches_surface(
            "気持ち 悪い。",
            "悪い",
            token_spans=((0, 6), (6, 7)),
        )
        is False
    )
    assert (
        matches_surface(
            "それは 悪い。",
            "悪い",
            token_spans=((0, 2), (2, 3), (4, 6), (6, 7)),
        )
        is True
    )


@pytest.mark.parametrize("source", ("悪いと思う", "悪い奴"))
def test_allows_words_after_a_target_at_a_token_boundary(source: str) -> None:
    assert matches_surface(source, "悪い", token_spans=((0, 2), (2, len(source)))) is True


@pytest.mark.parametrize(
    ("target", "source", "token_spans"),
    (
        (
            "大丈夫ですか？",
            "大丈夫ですかね？",
            ((0, 3), (3, 5), (5, 6), (6, 7), (7, 8)),
        ),
        (
            "大丈夫ですか",
            "大丈夫ですかね？",
            ((0, 3), (3, 5), (5, 6), (6, 7), (7, 8)),
        ),
        (
            "もう一回言って。",
            "もう一回言ってください",
            ((0, 2), (2, 4), (4, 7), (7, 11)),
        ),
        (
            "もう一回言って",
            "もう一回言ってください",
            ((0, 2), (2, 4), (4, 7), (7, 11)),
        ),
    ),
)
def test_multi_token_target_rejects_suffix_with_or_without_terminal_punctuation(
    target: str,
    source: str,
    token_spans: tuple[tuple[int, int], ...],
) -> None:
    assert matches_surface(source, target, token_spans=token_spans) is False


def test_rejects_a_long_surface_that_starts_inside_a_compound_token() -> None:
    assert matches_surface("気持ち悪い", "持ち悪い", token_spans=((0, 5),)) is False


def test_requires_an_explicit_allowed_kana_surface() -> None:
    source = "けがしてない？"

    assert matches_surface(source, "怪我してない？") is False
    assert (
        matches_surface(
            source,
            "怪我してない？",
            allowed_surfaces=("けがしてない？",),
        )
        is True
    )


@pytest.mark.parametrize("surface", ("", "   ", "？！"))
def test_rejects_empty_surface_after_normalization(surface: str) -> None:
    with pytest.raises(ValueError, match="표면형"):
        matches_surface("대상 원문", surface)
