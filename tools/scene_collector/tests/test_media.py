import copy
import datetime
import json
from pathlib import Path

import pytest
from nadeshiko.models import (
    ExternalId,
    Media,
    MediaAutocompleteResponse,
    MediaSummary,
    SearchFilters,
    SearchQuery,
    SearchResponse,
)

import scene_collector.search as search_module
from scene_collector.config import AISettings, AppSettings, SearchSettings, StorageSettings
from scene_collector.database import DatabaseError, SceneCollectorDatabase
from scene_collector.media import (
    media_display_name,
    refresh_media_metadata,
    search_media,
    store_media,
)
from scene_collector.models import ExpressionCandidate, ExpressionCandidates
from scene_collector.search import NoActiveMediaError, search_expressions

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "nadeshiko_search_response.json"


def _settings(work_data_dir: Path, *, candidate_count: int = 3) -> AppSettings:
    return AppSettings(
        storage=StorageSettings(work_data_dir=work_data_dir),
        ai=AISettings(service="provider-one", model="model-one"),
        search=SearchSettings(candidate_count=candidate_count, nadeshiko_take=2),
    )


def _summary(
    public_id: str,
    *,
    name_ja: str = "",
    name_romaji: str = "",
    name_en: str = "",
) -> MediaSummary:
    return MediaSummary(
        public_id=public_id,
        slug="anonymous-media",
        name_ja=name_ja,
        name_romaji=name_romaji,
        name_en=name_en,
        cover_url="https://media.example.invalid/cover.webp",
        category="ANIME",
    )


def _full_media(public_id: str, *, name_ja: str) -> Media:
    return Media(
        public_id=public_id,
        slug="anonymous-media",
        external_ids=ExternalId(anilist=None, imdb=None, tvdb=None, tmdb=None, youtube=None),
        name_ja=name_ja,
        name_romaji="Anonymous Media",
        name_en="Anonymous Media",
        airing_format="TV",
        airing_status="FINISHED",
        genres=["Comedy"],
        cover_url="https://media.example.invalid/cover.webp",
        banner_url="https://media.example.invalid/banner.webp",
        start_date=datetime.date(2020, 1, 1),
        end_date=None,
        category="ANIME",
        segment_count=100,
        episode_count=12,
        studio=None,
        season_name="WINTER",
        season_year=2020,
    )


def _search_response(
    *segments: tuple[str, str],
    media_public_id: str = "media-a",
) -> SearchResponse:
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
        segment["mediaPublicId"] = media_public_id
        segment["textJa"]["content"] = text_ja
        payload["segments"].append(segment)
    return SearchResponse.from_dict(payload)


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


class FilterRecordingNadeshiko:
    """공식 media filter 전달을 기록하는 offline fake."""

    def __init__(self, response: SearchResponse | None = None) -> None:
        self.response = response if response is not None else _search_response()
        self.calls: list[tuple[str, bool, tuple[str, ...]]] = []

    def search(
        self,
        *,
        query: SearchQuery,
        take: int,
        filters: SearchFilters,
    ) -> SearchResponse:
        included = tuple(item.media_public_id for item in filters.media.include)
        self.calls.append((query.search, bool(query.exact_match), included))
        return self.response


def test_search_media_uses_official_sdk_media_search() -> None:
    calls: list[dict[str, object]] = []
    summaries = [
        _summary("media-one", name_ja="作品一"),
        _summary("media-two", name_romaji="Sakuhin Two"),
    ]

    class FakeNadeshiko:
        def search_media(self, *, query: str, take: int | None = None) -> MediaAutocompleteResponse:
            call: dict[str, object] = {"query": query}
            if take is not None:
                call["take"] = take
            calls.append(call)
            return MediaAutocompleteResponse(media=list(summaries))

    found = search_media(FakeNadeshiko(), "  익명 작품  ")
    assert calls == [{"query": "익명 작품"}]
    assert [media.public_id for media in found] == ["media-one", "media-two"]
    assert [media_display_name(media) for media in found] == ["作品一", "Sakuhin Two"]

    search_media(FakeNadeshiko(), "익명 작품", take=3)
    assert calls[-1] == {"query": "익명 작품", "take": 3}

    with pytest.raises(ValueError, match="작품명"):
        search_media(FakeNadeshiko(), "   ")
    assert len(calls) == 2


def test_media_display_name_prefers_japanese_then_romaji_then_english() -> None:
    assert media_display_name(_summary("m", name_ja="日本語名", name_romaji="Romaji")) == "日本語名"
    assert media_display_name(_summary("m", name_romaji=" Romaji ", name_en="English")) == "Romaji"
    assert media_display_name(_summary("m", name_en="English")) == "English"
    assert media_display_name(_summary("m")) is None


def test_store_media_does_not_duplicate_the_same_public_id(tmp_path: Path) -> None:
    with SceneCollectorDatabase.open(_settings(tmp_path)) as database:
        first = store_media(database, _summary("media-one", name_ja="이전 표시명"))
        second = store_media(database, _summary("media-one", name_ja="최신 표시명"))

        assert first.id == second.id
        assert second.display_name == "최신 표시명"
        assert second.is_active is True
        assert second.preference is None
        assert second.content_group is None
        assert len(database.list_media()) == 1

        unnamed = store_media(database, _summary("media-one"))
        assert unnamed.display_name == "최신 표시명"


def test_refresh_media_metadata_fills_display_name_for_id_only_rows(tmp_path: Path) -> None:
    requested: list[str] = []

    class FakeNadeshiko:
        def get_media(self, media_public_id: str) -> Media:
            requested.append(media_public_id)
            return _full_media(media_public_id, name_ja="공식 표시명")

    with SceneCollectorDatabase.open(_settings(tmp_path)) as database:
        database.upsert_media("media-one")
        assert database.get_media("media-one").display_name is None

        refreshed = refresh_media_metadata(database, FakeNadeshiko(), "media-one")

        assert requested == ["media-one"]
        assert refreshed.display_name == "공식 표시명"


def test_refresh_media_metadata_preserves_user_managed_fields(tmp_path: Path) -> None:
    class FakeNadeshiko:
        def get_media(self, media_public_id: str) -> Media:
            return _full_media(media_public_id, name_ja="갱신된 표시명")

    with SceneCollectorDatabase.open(_settings(tmp_path)) as database:
        store_media(database, _summary("media-one", name_ja="이전 표시명"))
        database.set_media_preference("media-one", 7)
        database.set_media_content_group("media-one", "극장판")
        database.set_media_active("media-one", False)

        refreshed = refresh_media_metadata(database, FakeNadeshiko(), "media-one")

        assert refreshed.display_name == "갱신된 표시명"
        assert refreshed.preference == 7
        assert refreshed.content_group == "극장판"
        assert refreshed.is_active is False


def test_preference_content_group_and_active_are_stored_and_updated(tmp_path: Path) -> None:
    with SceneCollectorDatabase.open(_settings(tmp_path)) as database:
        store_media(database, _summary("media-one", name_ja="작품 하나"))

        database.set_media_preference("media-one", 3)
        assert database.get_media("media-one").preference == 3
        database.set_media_preference("media-one", None)
        assert database.get_media("media-one").preference is None

        database.set_media_content_group("media-one", "TV 소년만화")
        assert database.get_media("media-one").content_group == "TV 소년만화"
        database.set_media_content_group("media-one", "   ")
        assert database.get_media("media-one").content_group is None

        database.set_media_active("media-one", False)
        assert database.get_media("media-one").is_active is False
        database.set_media_active("media-one", True)
        assert database.get_media("media-one").is_active is True

        with pytest.raises(DatabaseError, match="작품을 찾을 수 없습니다"):
            database.set_media_preference("missing-media", 1)
        with pytest.raises(ValueError, match="public ID"):
            database.upsert_media("   ")


def test_media_state_survives_database_reopen(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    with SceneCollectorDatabase.open(settings) as database:
        store_media(database, _summary("media-one", name_ja="작품 하나"))
        store_media(database, _summary("media-two", name_ja="작품 둘"))
        database.set_media_preference("media-one", 5)
        database.set_media_content_group("media-one", "반복용")
        database.set_media_active("media-two", False)

    with SceneCollectorDatabase.open(settings) as reopened:
        first = reopened.get_media("media-one")
        second = reopened.get_media("media-two")
        assert first.display_name == "작품 하나"
        assert first.preference == 5
        assert first.content_group == "반복용"
        assert first.is_active is True
        assert second.is_active is False
        assert [media.nadeshiko_media_id for media in reopened.list_active_media()] == ["media-one"]


def test_list_active_media_excludes_inactive_media(tmp_path: Path) -> None:
    with SceneCollectorDatabase.open(_settings(tmp_path)) as database:
        store_media(database, _summary("media-one", name_ja="활성 하나"))
        store_media(database, _summary("media-two", name_ja="비활성"))
        store_media(database, _summary("media-three", name_ja="활성 둘"))
        database.set_media_active("media-two", False)

        assert [media.nadeshiko_media_id for media in database.list_media()] == [
            "media-one",
            "media-two",
            "media-three",
        ]
        assert [media.nadeshiko_media_id for media in database.list_active_media()] == [
            "media-one",
            "media-three",
        ]


def test_database_search_sends_only_active_media_as_official_filter(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        search_module,
        "create_structured_response",
        lambda *args, **kwargs: _candidates("大丈夫ですか", "大丈夫ですか", "大丈夫ですか"),
    )
    client = FilterRecordingNadeshiko(
        _search_response(
            ("segment-partial", "大丈夫？"),
            ("segment-exact", "あの、大丈夫ですか？"),
        )
    )
    settings = _settings(tmp_path)

    with SceneCollectorDatabase.open(settings) as database:
        store_media(database, _summary("media-b", name_ja="활성 나"))
        store_media(database, _summary("media-a", name_ja="활성 가"))
        store_media(database, _summary("media-inactive", name_ja="비활성"))
        database.set_media_active("media-inactive", False)

        result = search_expressions(
            settings,
            "다친 사람에게 괜찮냐고 묻는 말",
            nadeshiko_client=client,
            database=database,
        )

        assert client.calls == [("大丈夫ですか", False, ("media-a", "media-b"))]
        stored_conditions = database.connection.execute(
            "SELECT conditions_json FROM nadeshiko_search_cache"
        ).fetchall()
        assert [row["conditions_json"] for row in stored_conditions] == [
            '{"media_ids":["media-a","media-b"]}'
        ]
        assert [
            segment.text_ja.content
            for segment in result.corpus_backed_candidates[0].exact_segments
        ] == ["あの、大丈夫ですか？"]


def test_zero_active_media_raises_instead_of_global_fallback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ai_calls = 0

    def fake_structured_response(*args: object, **kwargs: object) -> ExpressionCandidates:
        nonlocal ai_calls
        ai_calls += 1
        return _candidates("大丈夫ですか", "平気", "怪我してない")

    monkeypatch.setattr(search_module, "create_structured_response", fake_structured_response)
    client = FilterRecordingNadeshiko()
    settings = _settings(tmp_path)

    with SceneCollectorDatabase.open(settings) as database:
        with pytest.raises(NoActiveMediaError, match="활성 선호 작품이 없습니다"):
            search_expressions(
                settings,
                "활성 작품 없이 검색",
                nadeshiko_client=client,
                database=database,
            )

        store_media(database, _summary("media-one", name_ja="비활성 하나"))
        database.set_media_active("media-one", False)
        with pytest.raises(NoActiveMediaError, match="활성 선호 작품이 없습니다"):
            search_expressions(
                settings,
                "활성 작품 없이 검색",
                nadeshiko_client=client,
                database=database,
            )

    assert ai_calls == 0
    assert client.calls == []


def test_same_media_conditions_hit_cache_and_changed_conditions_miss(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        search_module,
        "create_structured_response",
        lambda *args, **kwargs: _candidates("大丈夫ですか", "大丈夫ですか", "大丈夫ですか"),
    )
    client = FilterRecordingNadeshiko(_search_response(("segment-ok", "大丈夫ですか？")))
    settings = _settings(tmp_path)

    with SceneCollectorDatabase.open(settings) as database:
        store_media(database, _summary("media-a", name_ja="활성 가"))
        store_media(database, _summary("media-b", name_ja="활성 나"))

        search_expressions(settings, "같은 조건 반복", nadeshiko_client=client, database=database)
        assert len(client.calls) == 1

        search_expressions(settings, "같은 조건 반복", nadeshiko_client=client, database=database)
        assert len(client.calls) == 1

        database.set_media_active("media-b", False)
        search_expressions(settings, "같은 조건 반복", nadeshiko_client=client, database=database)
        assert len(client.calls) == 2
        assert client.calls[-1][2] == ("media-a",)

        database.set_media_active("media-b", True)
        search_expressions(settings, "같은 조건 반복", nadeshiko_client=client, database=database)
        assert len(client.calls) == 2

    with SceneCollectorDatabase.open(settings) as reopened:
        search_expressions(settings, "같은 조건 반복", nadeshiko_client=client, database=reopened)
        assert len(client.calls) == 2


def test_media_filtered_search_does_not_reuse_condition_free_cache(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        search_module,
        "create_structured_response",
        lambda *args, **kwargs: _candidates("大丈夫ですか", "大丈夫ですか", "大丈夫ですか"),
    )
    filtered_response = _search_response(("segment-filtered", "大丈夫ですか？"))
    client = FilterRecordingNadeshiko(filtered_response)
    settings = _settings(tmp_path)

    with SceneCollectorDatabase.open(settings) as database:
        database.put_nadeshiko_search_cache(
            search_text="大丈夫ですか",
            exact_match=False,
            take=settings.search.nadeshiko_take,
            response=_search_response(("segment-global", "大丈夫ですか？")),
        )
        store_media(database, _summary("media-a", name_ja="활성 가"))

        result = search_expressions(
            settings,
            "조건 없는 cache 오염 시험",
            nadeshiko_client=client,
            database=database,
        )

        assert len(client.calls) == 1
        assert [
            segment.public_id
            for segment in result.corpus_backed_candidates[0].exact_segments
        ] == ["segment-filtered"]

        condition_free = database.get_nadeshiko_search_cache(
            search_text="大丈夫ですか",
            exact_match=False,
            take=settings.search.nadeshiko_take,
        )
        assert condition_free is not None
        assert condition_free.segments[0].public_id == "segment-global"
