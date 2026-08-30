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
from scene_collector.database import (
    DatabaseError,
    SceneCollectorDatabase,
    StoredMeaningExpression,
)
from scene_collector.media import (
    media_display_name,
    refresh_media_metadata,
    search_media,
    store_media,
)
from scene_collector.search import NoActiveMediaError, search_selected_expression

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "nadeshiko_search_response.json"


def _settings(work_data_dir: Path, *, expression_generation_limit: int = 3) -> AppSettings:
    return AppSettings(
        storage=StorageSettings(work_data_dir=work_data_dir),
        ai=AISettings(service="provider-one", model="model-one"),
        search=SearchSettings(
            expression_generation_limit=expression_generation_limit,
        ),
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


def _relation(
    database: SceneCollectorDatabase,
    japanese: str = "大丈夫ですか",
) -> StoredMeaningExpression:
    """검색에 사용할 의미→표현 관계를 AI 없이 직접 저장한다."""
    meaning = database.upsert_meaning("다친 사람에게 괜찮냐고 묻는 말")
    return database.add_meaning_expression(
        meaning.id,
        japanese=japanese,
        reading="だいじょうぶですか",
        meaning_ko="괜찮으세요?",
        register_text="존댓말",
    )


def _forbid_ai(monkeypatch: pytest.MonkeyPatch) -> None:
    """검색 경로에서 AI를 한 번도 부르지 않는 계약을 강제한다."""

    def fail(*args: object, **kwargs: object) -> object:
        raise AssertionError("표현 검색은 AI를 호출하지 않아야 합니다.")

    monkeypatch.setattr(search_module, "create_structured_response", fail)


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
    _forbid_ai(monkeypatch)
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

        found = search_selected_expression(
            settings,
            _relation(database),
            nadeshiko_client=client,
            database=database,
        )

        # 두 검색 경로 모두에 같은 활성 작품 필터가 붙는다.
        assert client.calls == [
            ("大丈夫ですか", False, ("media-a", "media-b")),
            ("大丈夫ですか", True, ("media-a", "media-b")),
        ]
        assert [segment.text_ja.content for segment in found.nadeshiko_segments] == [
            "あの、大丈夫ですか？"
        ]


def test_zero_active_media_raises_instead_of_global_fallback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _forbid_ai(monkeypatch)
    client = FilterRecordingNadeshiko()
    settings = _settings(tmp_path)

    with SceneCollectorDatabase.open(settings) as database:
        relation = _relation(database)

        with pytest.raises(NoActiveMediaError, match="활성 선호 작품이 없습니다"):
            search_selected_expression(
                settings, relation, nadeshiko_client=client, database=database
            )

        store_media(database, _summary("media-one", name_ja="비활성 하나"))
        database.set_media_active("media-one", False)
        with pytest.raises(NoActiveMediaError, match="활성 선호 작품이 없습니다"):
            search_selected_expression(
                settings, relation, nadeshiko_client=client, database=database
            )

    assert client.calls == []


def test_repeated_search_is_not_cached_and_follows_active_media_changes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _forbid_ai(monkeypatch)
    client = FilterRecordingNadeshiko(_search_response(("segment-ok", "大丈夫ですか？")))
    settings = _settings(tmp_path)

    with SceneCollectorDatabase.open(settings) as database:
        store_media(database, _summary("media-a", name_ja="활성 가"))
        store_media(database, _summary("media-b", name_ja="활성 나"))
        relation = _relation(database)

        for _ in range(2):
            search_selected_expression(
                settings, relation, nadeshiko_client=client, database=database
            )
        # 같은 표현을 다시 찾아도 저장된 결과를 재사용하지 않고 다시 호출한다.
        # 한 번 검색할 때 일반·정확 두 경로를 도므로 두 번 검색하면 4회다.
        assert len(client.calls) == 4
        assert client.calls[-1][2] == ("media-a", "media-b")

        database.set_media_active("media-b", False)
        search_selected_expression(
            settings, relation, nadeshiko_client=client, database=database
        )
        assert len(client.calls) == 6
        assert client.calls[-1][2] == ("media-a",)

        # 검색만으로는 작업 장면도 검색 캐시 table도 생기지 않는다.
        assert database.list_work_scenes(relation.id) == ()
        tables = {
            row["name"]
            for row in database.connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
        }
        assert "nadeshiko_search_cache" not in tables
        assert "segments" not in tables

    with SceneCollectorDatabase.open(settings) as reopened:
        restored = reopened.get_meaning_expression(relation.id)
        assert restored is not None
        search_selected_expression(
            settings, restored, nadeshiko_client=client, database=reopened
        )
        assert len(client.calls) == 8
