import json
import os
from collections.abc import Iterator
from itertools import islice
from pathlib import Path
from urllib.parse import urlsplit

import pytest
from nadeshiko import Nadeshiko, NadeshikoError
from nadeshiko.models import SearchQuery, SearchResponse, Segment, SegmentContextResponse

from scene_collector.config import load_settings
from scene_collector.nadeshiko import create_nadeshiko_client

pytestmark = pytest.mark.nadeshiko_live


def _live_query() -> str:
    query = os.environ.get("SCENE_COLLECTOR_NADESHIKO_LIVE_QUERY", "大丈夫").strip()
    if not query:
        pytest.fail("SCENE_COLLECTOR_NADESHIKO_LIVE_QUERY가 비어 있습니다.")
    return query


@pytest.fixture(scope="module")
def live_client(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Nadeshiko]:
    config_dir = tmp_path_factory.mktemp("nadeshiko-live")
    settings_file = config_dir / "settings.toml"
    settings_file.write_text(
        "\n".join(
            (
                "[storage]",
                f"work_data_dir = {json.dumps(str(config_dir))}",
                "",
                "[ai]",
                'service = "unused-in-task-2"',
                'model = "unused-in-task-2"',
                "",
                "[search]",
                "candidate_count = 5",
                "nadeshiko_take = 5",
                "",
            )
        ),
        encoding="utf-8",
    )

    env_file_value = os.environ.get("SCENE_COLLECTOR_NADESHIKO_ENV_FILE")
    env_file = Path(env_file_value).expanduser().resolve() if env_file_value else None
    client = create_nadeshiko_client(load_settings(settings_file, env_file=env_file))
    yield client
    client.close()


@pytest.fixture(scope="module")
def live_search_response(live_client: Nadeshiko) -> SearchResponse:
    response = live_client.search(query=SearchQuery(search=_live_query()), take=10)
    if not response.segments:
        pytest.fail("실제 검색 결과가 없습니다. 시험 검색어를 바꿔 다시 실행하세요.")
    return response


@pytest.fixture(scope="module")
def live_segment(live_search_response: SearchResponse) -> Segment:
    return next(
        (segment for segment in live_search_response.segments if segment.position > 1),
        live_search_response.segments[0],
    )


@pytest.fixture(scope="module")
def live_context(live_client: Nadeshiko, live_segment: Segment) -> SegmentContextResponse:
    return live_client.get_segment_context(live_segment.public_id, take=2)


def test_authentication(live_search_response: SearchResponse) -> None:
    assert live_search_response.segments


def test_get_me_returns_user_and_usage(live_client: Nadeshiko) -> None:
    try:
        live_me = live_client.get_me()
    except NadeshikoError as error:
        pytest.fail(
            f"get_me 실제 호출 실패 ({error.code}): {error.detail}",
            pytrace=False,
        )

    assert live_me.user.username
    assert 0 <= live_me.quota.used <= live_me.quota.limit
    assert 0 <= live_me.quota.remaining <= live_me.quota.limit


def test_media_lookup(live_client: Nadeshiko) -> None:
    media_page = live_client.list_media(take=1)
    assert media_page.media

    media = live_client.get_media(media_page.media[0].public_id)
    assert media.public_id == media_page.media[0].public_id
    assert media.name_ja or media.name_romaji or media.name_en


def test_dialogue_search(live_search_response: SearchResponse) -> None:
    assert live_search_response.segments
    assert live_search_response.segments[0].text_ja.content


def test_iter_search_crosses_a_page_boundary(live_client: Nadeshiko) -> None:
    segments = list(
        islice(
            live_client.iter_search(query=SearchQuery(search=_live_query()), take=1),
            2,
        )
    )

    assert len(segments) == 2
    assert segments[0].public_id != segments[1].public_id


def test_segment_context_has_before_and_after(
    live_segment: Segment,
    live_context: SegmentContextResponse,
) -> None:
    same_episode = [
        segment
        for segment in live_context.segments
        if segment.media_public_id == live_segment.media_public_id
        and segment.episode == live_segment.episode
    ]
    assert any(segment.position < live_segment.position for segment in same_episode)
    assert any(segment.position > live_segment.position for segment in same_episode)


@pytest.mark.parametrize("url_field", ("image_url", "audio_url", "video_url"))
def test_segment_media_url(live_segment: Segment, url_field: str) -> None:
    value = getattr(live_segment.urls, url_field)
    parsed = urlsplit(value)

    assert parsed.scheme == "https"
    assert parsed.netloc
