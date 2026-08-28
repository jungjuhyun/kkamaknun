import copy
import json
from pathlib import Path

import pytest
from nadeshiko.models import MediaSummary, SearchFilters, SearchQuery, SearchResponse

import scene_collector.search as search_module
from scene_collector.config import AISettings, AppSettings, SearchSettings, StorageSettings
from scene_collector.database import SceneCollectorDatabase
from scene_collector.media import store_media
from scene_collector.models import ExpressionCandidate, ExpressionCandidates
from scene_collector.subtitles import index_local_subtitles
from scene_collector.ui_controller import (
    format_timecode,
    local_scene_line,
    restore_latest_search,
    run_expression_search,
    save_decision,
    select_expression,
    settings_summary,
)

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "nadeshiko_search_response.json"

SRT_EPISODE_1 = """1
00:00:01,000 --> 00:00:02,500
（ミサ）大丈夫ですか？

2
00:00:05,000 --> 00:00:06,000
ありがとう
"""


def _settings(work_data_dir: Path, *, api_key: str | None = None) -> AppSettings:
    keyword: dict[str, str] = {"NADESHIKO_API_KEY": api_key} if api_key else {}
    return AppSettings(
        storage=StorageSettings(work_data_dir=work_data_dir),
        ai=AISettings(service="provider-one", model="model-one"),
        search=SearchSettings(candidate_count=3, nadeshiko_take=2),
        **keyword,
    )


def _candidates(*japanese: str) -> ExpressionCandidates:
    return ExpressionCandidates(
        candidates=[
            ExpressionCandidate(
                japanese=text,
                reading=f"よみかた{index}",
                meaning_ko=f"의미 {index}",
                register=f"말투 {index}",
            )
            for index, text in enumerate(japanese, start=1)
        ]
    )


def _search_response(*segments: tuple[str, str]) -> SearchResponse:
    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    payload["pagination"] = {
        "hasMore": False,
        "estimatedTotalHits": len(segments),
        "estimatedTotalHitsRelation": "EXACT",
        "cursor": None,
    }
    segment_template = payload["segments"][0]
    payload["segments"] = []
    for position, (public_id, text_ja) in enumerate(segments, start=1):
        segment = copy.deepcopy(segment_template)
        segment["publicId"] = public_id
        segment["position"] = position
        segment["textJa"]["content"] = text_ja
        payload["segments"].append(segment)
    return SearchResponse.from_dict(payload)


class FakeNadeshiko:
    def __init__(self, response: SearchResponse) -> None:
        self.response = response
        self.calls: list[tuple[str, bool]] = []

    def search(
        self,
        *,
        query: SearchQuery,
        take: int,
        filters: SearchFilters,
    ) -> SearchResponse:
        self.calls.append((query.search, bool(query.exact_match)))
        return self.response


def _subtitle_dir(tmp_path: Path) -> Path:
    directory = tmp_path / "subs"
    directory.mkdir()
    (directory / "테스트 작품 S1E01.srt").write_text(SRT_EPISODE_1, encoding="utf-8")
    return directory


def test_settings_summary_reports_state_without_secret_value(tmp_path: Path) -> None:
    without_key = settings_summary(_settings(tmp_path))
    assert without_key.work_data_dir == tmp_path
    assert without_key.database_file.parent == tmp_path
    assert without_key.ai_service == "provider-one"
    assert without_key.ai_model == "model-one"
    assert without_key.nadeshiko_key_set is False

    secret = "very-secret-api-key"
    with_key = settings_summary(_settings(tmp_path, api_key=secret))
    assert with_key.nadeshiko_key_set is True
    assert secret not in repr(with_key)


def test_search_select_review_and_restart_restore_flow(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        search_module,
        "create_structured_response",
        lambda *args, **kwargs: _candidates("大丈夫ですか", "結果なしの表現", "もう一つの表現"),
    )
    settings = _settings(tmp_path)
    client = FakeNadeshiko(_search_response(("segment-nadeshiko", "あの、大丈夫ですか？")))
    summary = MediaSummary(
        public_id="anonymous-media-001",
        slug="anonymous-media",
        name_ja="나데시코 작품",
        name_romaji="",
        name_en="",
        cover_url="https://media.example.invalid/cover.webp",
        category="ANIME",
    )

    with SceneCollectorDatabase.open(settings) as database:
        store_media(database, summary)
        index_local_subtitles(database, "테스트 작품", _subtitle_dir(tmp_path))

        result = run_expression_search(
            settings,
            "괜찮냐고 묻는 말",
            nadeshiko_client=client,
            database=database,
        )

        assert result.korean_intent == "괜찮냐고 묻는 말"
        assert [item.expression.candidate.japanese for item in result.items] == [
            "大丈夫ですか"
        ]
        item = result.items[0]
        assert [stored.segment.text_ja.content for stored in item.expression.segments] == [
            "あの、大丈夫ですか？"
        ]
        assert [scene.japanese_text for scene in item.local_scenes] == [
            "（ミサ）大丈夫ですか？"
        ]
        assert item.local_scenes[0].media_display_name == "테스트 작품"

        select_expression(database, result, item.expression.id)
        stored_expression = database.load_expression(item.expression.id)
        assert stored_expression is not None
        assert stored_expression.selected is True

        with pytest.raises(ValueError, match="현재 검색 결과에 없는 표현"):
            select_expression(database, result, item.expression.id + 999)

        segment_id = item.expression.segments[0].id
        review = save_decision(database, item.expression.id, segment_id, "채택")
        assert review.decision == "채택"

    with SceneCollectorDatabase.open(settings) as reopened:
        restored = restore_latest_search(reopened)
        assert restored is not None
        assert restored.korean_intent == "괜찮냐고 묻는 말"
        assert len(restored.items) == 1
        restored_item = restored.items[0]
        assert restored_item.expression.candidate.japanese == "大丈夫ですか"
        assert restored_item.expression.selected is True
        assert restored_item.local_scenes == ()
        restored_review = restored_item.expression.segments[0].review
        assert restored_review is not None
        assert restored_review.decision == "채택"

        media_rows = reopened.list_media()
        sources = {media.source for media in media_rows}
        assert sources == {"nadeshiko", "local"}
        local_rows = [media for media in media_rows if media.source == "local"]
        assert local_rows[0].nadeshiko_media_id is None


def test_restore_returns_none_without_saved_search(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    with SceneCollectorDatabase.open(settings) as database:
        assert restore_latest_search(database) is None


def test_restore_skips_latest_run_without_scenes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings(tmp_path)
    client = FakeNadeshiko(_search_response(("segment-nadeshiko", "あの、大丈夫ですか？")))
    summary = MediaSummary(
        public_id="anonymous-media-001",
        slug="anonymous-media",
        name_ja="나데시코 작품",
        name_romaji="",
        name_en="",
        cover_url="https://media.example.invalid/cover.webp",
        category="ANIME",
    )
    with SceneCollectorDatabase.open(settings) as database:
        store_media(database, summary)

        monkeypatch.setattr(
            search_module,
            "create_structured_response",
            lambda *args, **kwargs: _candidates("大丈夫ですか", "候補二", "候補三"),
        )
        first = run_expression_search(
            settings, "괜찮냐고 묻는 말", nadeshiko_client=client, database=database
        )
        assert len(first.items) == 1

        monkeypatch.setattr(
            search_module,
            "create_structured_response",
            lambda *args, **kwargs: _candidates("結構です", "構いません", "候補三"),
        )
        empty = run_expression_search(
            settings, "괜찮습니다", nadeshiko_client=client, database=database
        )
        assert empty.items == ()

        restored = restore_latest_search(database)
        assert restored is not None
        assert restored.korean_intent == "괜찮냐고 묻는 말"
        assert restored.run_id == first.run_id


def test_local_scene_line_formats_title_episode_and_timecode(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    with SceneCollectorDatabase.open(settings) as database:
        media, _ = index_local_subtitles(database, "테스트 작품", _subtitle_dir(tmp_path))
        scenes = database.find_local_segments(
            normalized_surface="大丈夫ですか", media_row_ids=[media.id]
        )
    assert format_timecode(scenes[0].start_time_ms) == "00:00:01.000"
    line = local_scene_line(scenes[0])
    assert "테스트 작품" in line
    assert "1화" in line
    assert "00:00:01.000 ~ 00:00:02.500" in line
    assert "（ミサ）大丈夫ですか？" in line
