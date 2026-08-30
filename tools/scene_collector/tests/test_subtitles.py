import copy
import json
from pathlib import Path

import pytest
from nadeshiko.models import MediaSummary, SearchFilters, SearchQuery, SearchResponse

from scene_collector.config import AISettings, AppSettings, SearchSettings, StorageSettings
from scene_collector.database import (
    DatabaseError,
    SceneCollectorDatabase,
    StoredMeaningExpression,
)
from scene_collector.media import store_media
from scene_collector.search import search_selected_expression
from scene_collector.subtitles import (
    episode_from_filename,
    index_local_subtitles,
    parse_subtitle_directory,
)

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "nadeshiko_search_response.json"

SRT_EPISODE_1 = """1
00:00:01,000 --> 00:00:02,500
（ミサ）大丈夫ですか？

2
00:00:05,000 --> 00:00:06,000
気持ち悪いよ

3
00:00:09,000 --> 00:00:10,000
ありがとう
"""

SRT_EPISODE_2 = """1
00:01:00,000 --> 00:01:01,000
どうしたんですか？

2
00:01:30,000 --> 00:01:31,500
本当に大丈夫ですか？
"""

ASS_MOVIE = """[Script Info]
ScriptType: v4.00+

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,20,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,2,2,2,10,10,10,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:03.00,0:00:04.00,Default,,0,0,0,,ごめんなさい
Comment: 0,0:00:05.00,0:00:06.00,Default,,0,0,0,,コメント行は 무시
Dialogue: 0,0:00:01.00,0:00:02.00,Default,,0,0,0,,大丈夫ですか？
"""


def _settings(work_data_dir: Path) -> AppSettings:
    return AppSettings(
        storage=StorageSettings(work_data_dir=work_data_dir),
        ai=AISettings(service="provider-one", model="model-one"),
        search=SearchSettings(expression_generation_limit=3, nadeshiko_take=2),
    )


def _subtitle_dir(tmp_path: Path) -> Path:
    directory = tmp_path / "subs"
    directory.mkdir()
    (directory / "テスト作品 S1E01.srt").write_text(SRT_EPISODE_1, encoding="utf-8")
    (directory / "テスト作品 - 02.srt").write_text(SRT_EPISODE_2, encoding="utf-8")
    return directory


def _relation(
    database: SceneCollectorDatabase,
    japanese: str,
    *,
    korean_meaning: str = "괜찮냐고 묻는 말",
) -> StoredMeaningExpression:
    """검색에 사용할 의미→표현 관계를 AI 없이 직접 저장한다."""
    meaning = database.upsert_meaning(korean_meaning)
    return database.add_meaning_expression(
        meaning.id,
        japanese=japanese,
        reading="よみかた",
        meaning_ko="의미",
        register_text="말투",
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


class RecordingNadeshiko:
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


@pytest.mark.parametrize(
    ("filename", "expected"),
    (
        ("テスト作品 S1E01.srt", 1),
        ("テスト作品 - 02.srt", 2),
        ("作品 第13話.ass", 13),
        ("sakuhin ep 7.srt", 7),
        ("劇場版テスト.ass", None),
    ),
)
def test_episode_from_filename_uses_generic_patterns(
    filename: str, expected: int | None
) -> None:
    assert episode_from_filename(filename) == expected


def test_parse_subtitle_directory_reads_srt_and_ass(tmp_path: Path) -> None:
    directory = _subtitle_dir(tmp_path)
    (directory / "劇場版テスト.ass").write_text(ASS_MOVIE, encoding="utf-8")

    cues = parse_subtitle_directory(directory)

    assert len(cues) == 7
    movie_cues = [cue for cue in cues if cue.episode is None]
    assert [cue.japanese_text for cue in movie_cues] == ["大丈夫ですか？", "ごめんなさい"]
    assert [cue.position for cue in movie_cues] == [0, 1]
    first_episode = [cue for cue in cues if cue.episode == 1]
    assert [cue.japanese_text for cue in first_episode] == [
        "（ミサ）大丈夫ですか？",
        "気持ち悪いよ",
        "ありがとう",
    ]
    assert first_episode[0].start_time_ms == 1000
    assert first_episode[0].end_time_ms == 2500

    with pytest.raises(ValueError, match="자막 파일"):
        empty = tmp_path / "empty"
        empty.mkdir()
        parse_subtitle_directory(empty)
    with pytest.raises(ValueError, match="자막 폴더"):
        parse_subtitle_directory(tmp_path / "missing")


def test_index_local_subtitles_registers_and_reindexes_without_duplicates(
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path)
    directory = _subtitle_dir(tmp_path)

    with SceneCollectorDatabase.open(settings) as database:
        media, count = index_local_subtitles(database, "테스트 작품", directory)
        assert media.source == "local"
        assert media.nadeshiko_media_id is None
        assert media.is_active is True
        assert count == 5

        again, count_again = index_local_subtitles(database, "테스트 작품", directory)
        assert again.id == media.id
        assert count_again == 5
        stored = database.connection.execute(
            "SELECT COUNT(*) FROM local_segments"
        ).fetchone()[0]
        assert stored == 5

        with pytest.raises(ValueError, match="표시 이름"):
            database.register_local_media("   ")
        with pytest.raises(DatabaseError, match="로컬 작품"):
            database.replace_local_segments(9999, [])

    with SceneCollectorDatabase.open(settings) as reopened:
        restored = reopened.find_local_media("테스트 작품")
        assert restored is not None
        assert restored.id == media.id
        stored = reopened.connection.execute(
            "SELECT COUNT(*) FROM local_segments"
        ).fetchone()[0]
        assert stored == 5


def test_find_local_segments_prefilters_without_wildcard_injection(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    directory = tmp_path / "subs"
    directory.mkdir()
    (directory / "작품 - 01.srt").write_text(
        "1\n00:00:01,000 --> 00:00:02,000\n100%です\n\n"
        "2\n00:00:03,000 --> 00:00:04,000\n100点です\n",
        encoding="utf-8",
    )

    with SceneCollectorDatabase.open(settings) as database:
        media, _ = index_local_subtitles(database, "작품", directory)

        exact = database.find_local_segments(
            normalized_surface="100%です", media_row_ids=[media.id]
        )
        assert [match.japanese_text for match in exact] == ["100%です"]
        assert (
            database.find_local_segments(
                normalized_surface="100%です", media_row_ids=[]
            )
            == ()
        )


def test_search_uses_local_subtitles_when_no_nadeshiko_media_is_active(
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path)
    client = RecordingNadeshiko()

    with SceneCollectorDatabase.open(settings) as database:
        index_local_subtitles(database, "테스트 작품", _subtitle_dir(tmp_path))
        relation = _relation(database, "大丈夫ですか")

        found = search_selected_expression(
            settings, relation, nadeshiko_client=client, database=database
        )

        assert client.calls == []
        assert found.nadeshiko_segments == ()
        assert [scene.japanese_text for scene in found.local_segments] == [
            "（ミサ）大丈夫ですか？",
            "本当に大丈夫ですか？",
        ]
        assert [scene.episode for scene in found.local_segments] == [1, 2]
        assert found.local_segments[0].media_display_name == "테스트 작품"
        assert found.local_segments[0].start_time_ms == 1000
        assert found.has_results

        # LIKE 1차 후보(気持ち悪いよ)는 surface matcher가 최종 제거한다.
        near_miss = search_selected_expression(
            settings,
            _relation(database, "悪い"),
            nadeshiko_client=client,
            database=database,
        )
        assert near_miss.local_segments == ()
        no_hit = search_selected_expression(
            settings,
            _relation(database, "結果なし"),
            nadeshiko_client=client,
            database=database,
        )
        assert no_hit.local_segments == ()
        assert client.calls == []

    with SceneCollectorDatabase.open(settings) as reopened:
        restored = reopened.get_meaning_expression(relation.id)
        assert restored is not None
        again = search_selected_expression(
            settings, restored, nadeshiko_client=client, database=reopened
        )
        assert client.calls == []
        assert len(again.local_segments) == 2


def test_search_merges_nadeshiko_and_local_results(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    client = RecordingNadeshiko(
        _search_response(("segment-nadeshiko", "あの、大丈夫ですか？"))
    )

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
        relation = _relation(database, "大丈夫ですか")

        found = search_selected_expression(
            settings, relation, nadeshiko_client=client, database=database
        )

        assert client.calls == [("大丈夫ですか", False, ("anonymous-media-001",))]
        assert [segment.text_ja.content for segment in found.nadeshiko_segments] == [
            "あの、大丈夫ですか？"
        ]
        assert [scene.japanese_text for scene in found.local_segments] == [
            "（ミサ）大丈夫ですか？",
            "本当に大丈夫ですか？",
        ]
        assert found.has_results
