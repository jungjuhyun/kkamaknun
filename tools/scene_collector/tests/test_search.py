import copy
import json
from pathlib import Path

import pytest
from nadeshiko.models import SearchQuery, SearchResponse, Token
from pydantic import ValidationError

import scene_collector.search as search_module
from scene_collector.config import (
    AISettings,
    AppSettings,
    SearchSettings,
    StorageSettings,
)
from scene_collector.models import ExpressionCandidate, ExpressionCandidates
from scene_collector.search import search_expressions

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "nadeshiko_search_response.json"


def _candidate(japanese: str, number: int) -> ExpressionCandidate:
    return ExpressionCandidate(
        japanese=japanese,
        reading=f"よみかた{number}",
        meaning_ko=f"의미 {number}",
        register=f"말투 {number}",
    )


def _settings(tmp_path: Path, *, service: str, candidate_count: int = 4) -> AppSettings:
    return AppSettings(
        storage=StorageSettings(work_data_dir=tmp_path),
        ai=AISettings(service=service, model="configured-model"),
        search=SearchSettings(candidate_count=candidate_count, nadeshiko_take=2),
    )


def _search_response(*texts_ja: str) -> SearchResponse:
    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    payload["pagination"] = {
        "hasMore": False,
        "estimatedTotalHits": len(texts_ja),
        "estimatedTotalHitsRelation": "EXACT",
        "cursor": None,
    }
    segment_template = payload["segments"][0]
    payload["segments"] = []
    for index, text_ja in enumerate(texts_ja, start=1):
        segment = copy.deepcopy(segment_template)
        segment["publicId"] = f"anonymous-segment-{index:03d}"
        segment["position"] = index
        segment["textJa"]["content"] = text_ja
        payload["segments"].append(segment)
    return SearchResponse.from_dict(payload)


@pytest.mark.parametrize("service", ("provider-one", "provider-two"))
def test_searches_unique_ai_candidates_and_filters_empty_results(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    service: str,
) -> None:
    generated = ExpressionCandidates(
        candidates=[
            _candidate("大丈夫ですか", 1),
            _candidate("ちょっと待って", 2),
            _candidate("大丈夫ですか", 3),
            _candidate("分からない", 4),
        ]
    )
    ai_calls: list[tuple[AppSettings, str, type[ExpressionCandidates]]] = []

    def fake_structured_response(
        settings: AppSettings,
        *,
        prompt: str,
        response_model: type[ExpressionCandidates],
    ) -> ExpressionCandidates:
        ai_calls.append((settings, prompt, response_model))
        return generated

    class FakeNadeshiko:
        def __init__(self) -> None:
            self.calls: list[tuple[SearchQuery, int]] = []

        def search(self, *, query: SearchQuery, take: int) -> SearchResponse:
            self.calls.append((query, take))
            responses = {
                "大丈夫ですか": _search_response(
                    "大丈夫？",
                    "あの、大丈夫ですか？",
                    "本当に大丈夫ですか?",
                ),
                "ちょっと待って": _search_response(),
                "分からない": _search_response("分からないよ", "分からない。"),
            }
            return responses[query.search]

    monkeypatch.setattr(search_module, "create_structured_response", fake_structured_response)
    client = FakeNadeshiko()
    korean_intent = "다친 사람에게 괜찮냐고 물어보는 말"

    result = search_expressions(
        _settings(tmp_path, service=service),
        korean_intent,
        nadeshiko_client=client,
    )

    assert len(ai_calls) == 1
    called_settings, prompt, response_model = ai_calls[0]
    assert called_settings.ai.service == service
    assert korean_intent in prompt
    assert "4개" in prompt
    assert response_model is ExpressionCandidates
    assert [call[0].search for call in client.calls] == [
        "大丈夫ですか",
        "ちょっと待って",
        "ちょっと待って",
        "分からない",
    ]
    assert [call[0].exact_match for call in client.calls] == [False, False, True, False]
    assert all(call[1] == 2 for call in client.calls)
    assert len(result.generated_candidates) == 4
    assert [item.candidate.japanese for item in result.corpus_backed_candidates] == [
        "大丈夫ですか",
        "分からない",
    ]
    assert [
        segment.text_ja.content for segment in result.candidate_searches[0].response.segments
    ] == [
        "大丈夫？",
        "あの、大丈夫ですか？",
        "本当に大丈夫ですか?",
    ]
    assert [segment.text_ja.content for segment in result.candidate_searches[0].exact_segments] == [
        "あの、大丈夫ですか？",
        "本当に大丈夫ですか?",
    ]
    assert [segment.text_ja.content for segment in result.candidate_searches[2].exact_segments] == [
        "分からない。"
    ]
    assert result.candidate_searches[0].exact_match_response is None
    assert result.candidate_searches[1].exact_match_response is not None
    assert result.candidate_searches[2].exact_match_response is None


def test_removes_task_4_false_positive_segments_and_unbacks_candidates(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    false_positive_pairs = (
        ("悪い", "気持ち悪い"),
        ("ほんとそれ", "ほんと? それって甘い?"),
        ("ん？なんて？", "マンガ描けません なんて なるなよな"),
        ("今、何してるんですか？", "今 どこに寝泊まりしてるんです?"),
    )
    generated = ExpressionCandidates(
        candidates=[
            _candidate(target, index)
            for index, (target, _) in enumerate(false_positive_pairs, start=1)
        ]
    )
    monkeypatch.setattr(
        search_module,
        "create_structured_response",
        lambda *args, **kwargs: generated,
    )

    class FakeNadeshiko:
        def __init__(self) -> None:
            self.calls: list[tuple[SearchQuery, int]] = []

        def search(self, *, query: SearchQuery, take: int) -> SearchResponse:
            self.calls.append((query, take))
            source_by_target = dict(false_positive_pairs)
            return _search_response(source_by_target[query.search])

    client = FakeNadeshiko()
    result = search_expressions(
        _settings(tmp_path, service="provider-one"),
        "작업 4 거짓 양성 회귀시험",
        nadeshiko_client=client,
    )

    assert [item.candidate.japanese for item in result.candidate_searches] == [
        target for target, _ in false_positive_pairs
    ]
    assert all(item.response.segments for item in result.candidate_searches)
    assert all(item.exact_match_response is not None for item in result.candidate_searches)
    assert all(not item.exact_segments for item in result.candidate_searches)
    assert result.corpus_backed_candidates == ()
    assert [call[0].exact_match for call in client.calls] == [False, True] * 4


def test_keeps_a_target_before_following_words_at_nadeshiko_token_boundaries(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    generated = ExpressionCandidates(
        candidates=[
            _candidate("悪い", 1),
            _candidate("別候補一", 2),
            _candidate("別候補二", 3),
        ]
    )
    monkeypatch.setattr(
        search_module,
        "create_structured_response",
        lambda *args, **kwargs: generated,
    )
    tokenized_response = _search_response("悪いと思う")
    tokenized_response.segments[0].text_ja.tokens = [
        Token(s="悪い", d="悪い", r="ワルイ", b=0, e=2, p="形容詞"),
        Token(s="と", d="と", r="ト", b=2, e=3, p="助詞"),
        Token(s="思う", d="思う", r="オモウ", b=3, e=5, p="動詞"),
    ]

    class FakeNadeshiko:
        def search(self, *, query: SearchQuery, take: int) -> SearchResponse:
            return tokenized_response if query.search == "悪い" else _search_response()

    result = search_expressions(
        _settings(tmp_path, service="provider-one", candidate_count=3),
        "나쁘다고 생각한다고 말하는 표현",
        nadeshiko_client=FakeNadeshiko(),
    )

    assert [item.candidate.japanese for item in result.corpus_backed_candidates] == ["悪い"]
    assert [
        segment.text_ja.content for segment in result.corpus_backed_candidates[0].exact_segments
    ] == ["悪いと思う"]
    assert result.corpus_backed_candidates[0].exact_match_response is None


def test_uses_exact_match_only_as_a_fallback_without_losing_normal_matches(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    generated = ExpressionCandidates(
        candidates=[
            _candidate("もう一回言って。", 1),
            _candidate("見つけた", 2),
            _candidate("結果なし", 3),
        ]
    )
    monkeypatch.setattr(
        search_module,
        "create_structured_response",
        lambda *args, **kwargs: generated,
    )

    class FakeNadeshiko:
        def __init__(self) -> None:
            self.calls: list[SearchQuery] = []

        def search(self, *, query: SearchQuery, take: int) -> SearchResponse:
            self.calls.append(query)
            if query.search == "もう一回言って。":
                if query.exact_match is True:
                    raise AssertionError(
                        "normal surface match must not be replaced by exact search"
                    )
                return _search_response("もう一回 言って。")
            if query.search == "見つけた" and query.exact_match is True:
                return _search_response("見つけた。")
            return _search_response()

    client = FakeNadeshiko()
    result = search_expressions(
        _settings(tmp_path, service="provider-one", candidate_count=3),
        "일반 검색 결과를 잃지 않는 fallback 시험",
        nadeshiko_client=client,
    )

    assert [item.candidate.japanese for item in result.corpus_backed_candidates] == [
        "もう一回言って。",
        "見つけた",
    ]
    assert [query.exact_match for query in client.calls] == [False, False, True, False, True]
    assert result.candidate_searches[0].exact_match_response is None
    assert result.candidate_searches[1].exact_match_response is not None
    assert result.candidate_searches[2].exact_match_response is not None


@pytest.mark.parametrize("count", (2, 6))
def test_expression_candidate_list_rejects_counts_outside_three_to_five(count: int) -> None:
    with pytest.raises(ValidationError):
        ExpressionCandidates(
            candidates=[_candidate(f"候補{index}", index) for index in range(count)]
        )


def test_expression_candidate_schema_exposes_required_product_fields() -> None:
    properties = ExpressionCandidate.model_json_schema()["properties"]

    assert set(properties) == {"japanese", "reading", "meaning_ko", "register"}


def test_rejects_ai_candidate_count_different_from_settings(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    generated = ExpressionCandidates(
        candidates=[_candidate(f"候補{index}", index) for index in range(3)]
    )
    monkeypatch.setattr(
        search_module,
        "create_structured_response",
        lambda *args, **kwargs: generated,
    )

    with pytest.raises(ValueError, match="다른 개수"):
        search_expressions(
            _settings(tmp_path, service="provider-one", candidate_count=4),
            "시험할 한국어 의미",
            nadeshiko_client=object(),
        )
