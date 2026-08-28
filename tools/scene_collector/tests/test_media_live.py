import json
import os
from pathlib import Path

import pytest
from nadeshiko import Nadeshiko
from nadeshiko.models import SearchResponse

import scene_collector.search as search_module
from scene_collector.config import AppSettings, load_settings
from scene_collector.database import SceneCollectorDatabase
from scene_collector.media import media_display_name, refresh_media_metadata, search_media
from scene_collector.models import ExpressionCandidate, ExpressionCandidates
from scene_collector.nadeshiko import create_nadeshiko_client
from scene_collector.search import search_expressions

pytestmark = pytest.mark.media_live

LIVE_CANDIDATE_COUNT = 3


def _required_environment(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        pytest.fail(f"Missing required live-test environment variable: {name}")
    return value


def _live_query() -> str:
    query = os.environ.get("SCENE_COLLECTOR_MEDIA_LIVE_QUERY", "大丈夫").strip()
    if not query:
        pytest.fail("SCENE_COLLECTOR_MEDIA_LIVE_QUERY가 비어 있습니다.")
    return query


class _CountingNadeshiko:
    """실제 대사 검색 호출 수만 세는 공식 client wrapper."""

    def __init__(self, inner: Nadeshiko) -> None:
        self._inner = inner
        self.search_calls = 0

    def search(self, **kwargs: object) -> SearchResponse:
        self.search_calls += 1
        return self._inner.search(**kwargs)


@pytest.fixture()
def live_settings(tmp_path: Path) -> AppSettings:
    _required_environment("NADESHIKO_API_KEY")
    work_data_dir = tmp_path / "work-data"
    work_data_dir.mkdir()
    settings_file = tmp_path / "settings.toml"
    settings_file.write_text(
        "\n".join(
            (
                "[storage]",
                f"work_data_dir = {json.dumps(str(work_data_dir))}",
                "",
                "[ai]",
                'service = "unused-in-task-7"',
                'model = "unused-in-task-7"',
                "",
                "[search]",
                f"candidate_count = {LIVE_CANDIDATE_COUNT}",
                "nadeshiko_take = 5",
                "",
            )
        ),
        encoding="utf-8",
    )
    return load_settings(settings_file)


def test_media_management_and_filtered_search_live(
    live_settings: AppSettings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = create_nadeshiko_client(live_settings)
    try:
        media_page = client.list_media(take=5)
        assert media_page.media
        chosen = max(media_page.media, key=lambda media: media.segment_count)
        media_name = (chosen.name_romaji or "").strip() or media_display_name(chosen)
        assert media_name

        summaries = search_media(client, media_name)
        assert summaries
        assert any(summary.public_id == chosen.public_id for summary in summaries)

        with SceneCollectorDatabase.open(live_settings) as database:
            database.upsert_media(chosen.public_id)
            stored = refresh_media_metadata(database, client, chosen.public_id)
            assert stored.nadeshiko_media_id == chosen.public_id
            assert stored.display_name

            database.set_media_preference(chosen.public_id, 2)
            database.set_media_content_group(chosen.public_id, "media live 검증")
            database.set_media_active(chosen.public_id, False)
            database.set_media_active(chosen.public_id, True)

        with SceneCollectorDatabase.open(live_settings) as reopened:
            restored = reopened.get_media(chosen.public_id)
            assert restored is not None
            assert restored.display_name == stored.display_name
            assert restored.preference == 2
            assert restored.content_group == "media live 검증"
            assert restored.is_active is True
            assert [media.nadeshiko_media_id for media in reopened.list_active_media()] == [
                chosen.public_id
            ]

            live_target = _live_query()
            fixed_candidate = ExpressionCandidate(
                japanese=live_target,
                reading="らいぶけんしょう",
                meaning_ko="media live 시험 표현",
                register="시험용",
            )
            monkeypatch.setattr(
                search_module,
                "create_structured_response",
                lambda *args, **kwargs: ExpressionCandidates(
                    candidates=[fixed_candidate] * LIVE_CANDIDATE_COUNT
                ),
            )

            counting = _CountingNadeshiko(client)
            result = search_expressions(
                live_settings,
                "media live 필터 검증",
                nadeshiko_client=counting,
                database=reopened,
            )
            first_search_calls = counting.search_calls
            assert 1 <= first_search_calls <= 2

            candidate_search = result.candidate_searches[0]
            if not candidate_search.response.segments:
                pytest.fail(
                    "선택한 작품 안에서 검색 결과가 없습니다. "
                    "SCENE_COLLECTOR_MEDIA_LIVE_QUERY를 바꿔 다시 실행하세요."
                )
            assert all(
                segment.media_public_id == chosen.public_id
                for segment in candidate_search.response.segments
            )
            if candidate_search.exact_match_response is not None:
                assert all(
                    segment.media_public_id == chosen.public_id
                    for segment in candidate_search.exact_match_response.segments
                )

            search_expressions(
                live_settings,
                "media live 필터 검증",
                nadeshiko_client=counting,
                database=reopened,
            )
            assert counting.search_calls == first_search_calls
    finally:
        client.close()
