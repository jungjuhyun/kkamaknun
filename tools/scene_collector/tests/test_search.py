import json
from pathlib import Path

import pytest
from nadeshiko.models import SearchQuery, SearchResponse
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


def _search_response(*, text_ja: str | None) -> SearchResponse:
    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    payload["pagination"] = {
        "hasMore": False,
        "estimatedTotalHits": 1 if text_ja else 0,
        "estimatedTotalHitsRelation": "EXACT",
        "cursor": None,
    }
    if text_ja is None:
        payload["segments"] = []
    else:
        payload["segments"][0]["textJa"]["content"] = text_ja
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
                "大丈夫ですか": _search_response(text_ja="候補とは異なる実際の台詞"),
                "ちょっと待って": _search_response(text_ja=None),
                "分からない": _search_response(text_ja="分からないよ"),
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
        "分からない",
    ]
    assert all(call[0].exact_match is False for call in client.calls)
    assert all(call[1] == 2 for call in client.calls)
    assert len(result.generated_candidates) == 4
    assert [item.candidate.japanese for item in result.corpus_backed_candidates] == [
        "大丈夫ですか",
        "分からない",
    ]


@pytest.mark.parametrize("count", (2, 6))
def test_expression_candidate_list_rejects_counts_outside_three_to_five(count: int) -> None:
    with pytest.raises(ValidationError):
        ExpressionCandidates(candidates=[_candidate(f"候補{index}", index) for index in range(count)])


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
