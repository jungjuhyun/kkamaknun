import copy
import csv
import io
import json
from pathlib import Path

import pytest
from nadeshiko.models import MediaSummary, SearchFilters, SearchQuery, SearchResponse

import scene_collector.export as export_module
import scene_collector.search as search_module
from scene_collector.config import AISettings, AppSettings, SearchSettings, StorageSettings
from scene_collector.database import SCHEMA_VERSION, SceneCollectorDatabase
from scene_collector.export import (
    ExportError,
    export_accepted_scenes,
    video_filename,
)
from scene_collector.media import store_media
from scene_collector.models import ExpressionCandidate, ExpressionCandidates
from scene_collector.search import search_expressions

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "nadeshiko_search_response.json"


def _settings(work_data_dir: Path) -> AppSettings:
    return AppSettings(
        storage=StorageSettings(work_data_dir=work_data_dir),
        ai=AISettings(service="provider-one", model="model-one"),
        search=SearchSettings(candidate_count=3, nadeshiko_take=3),
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
    template = payload["segments"][0]
    payload["segments"] = []
    for position, (public_id, text_ja) in enumerate(segments, start=1):
        segment = copy.deepcopy(template)
        segment["publicId"] = public_id
        segment["position"] = position
        segment["textJa"]["content"] = text_ja
        segment["urls"]["videoUrl"] = f"https://media.example.invalid/{public_id}.mp4"
        payload["segments"].append(segment)
    return SearchResponse.from_dict(payload)


class FakeNadeshiko:
    def __init__(self, response: SearchResponse) -> None:
        self.response = response

    def search(
        self,
        *,
        query: SearchQuery,
        take: int,
        filters: SearchFilters,
    ) -> SearchResponse:
        return self.response


class CountingDownloader:
    def __init__(self, payload: bytes = b"fake-mp4-bytes") -> None:
        self.payload = payload
        self.calls: list[str] = []

    def __call__(self, url: str, destination: Path) -> None:
        self.calls.append(url)
        destination.write_bytes(self.payload)


def _seed_accepted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    decisions: dict[str, str],
) -> AppSettings:
    """두 표현이 같은 장면 하나 + 서로 다른 장면을 채택하는 상태를 만든다.

    후보: 大丈夫ですか / ありがとう / 結果なし.
    segment-shared: 두 표현이 모두 정확 일치하는 대사.
    segment-only-a: 大丈夫ですか만 일치.
    """
    monkeypatch.setattr(
        search_module,
        "create_structured_response",
        lambda *args, **kwargs: _candidates("大丈夫ですか", "ありがとう", "結果なし"),
    )
    settings = _settings(tmp_path)
    client = FakeNadeshiko(
        _search_response(
            ("segment-shared", "大丈夫ですか、ありがとう。"),
            ("segment-only-a", "あの、大丈夫ですか？"),
        )
    )
    summary = MediaSummary(
        public_id="anonymous-media-001",
        slug="anonymous-media",
        name_ja="테스트 작품",
        name_romaji="",
        name_en="",
        cover_url="https://media.example.invalid/cover.webp",
        category="ANIME",
    )
    with SceneCollectorDatabase.open(settings) as database:
        store_media(database, summary)
        search_expressions(
            settings, "괜찮냐고 묻는 말", nadeshiko_client=client, database=database
        )
        run = database.load_search_run(database.latest_search_run_id())
        for expression in run.expressions:
            for stored in expression.segments:
                key = f"{expression.candidate.japanese}:{stored.segment.public_id}"
                if key in decisions:
                    database.set_review_decision(
                        expression.id, stored.id, decisions[key]
                    )
    return settings


ALL_ACCEPTED = {
    "大丈夫ですか:segment-shared": "채택",
    "ありがとう:segment-shared": "채택",
    "大丈夫ですか:segment-only-a": "채택",
}


def test_only_accepted_relations_are_exported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _seed_accepted(
        tmp_path,
        monkeypatch,
        decisions={
            "大丈夫ですか:segment-shared": "채택",
            "ありがとう:segment-shared": "예비",
            "大丈夫ですか:segment-only-a": "제외",
        },
    )
    with SceneCollectorDatabase.open(settings) as database:
        rows = database.list_accepted_scenes()
        assert len(rows) == 1
        row = rows[0]
        assert row.japanese == "大丈夫ですか"
        assert row.segment_public_id == "segment-shared"
        assert row.korean_intent == "괜찮냐고 묻는 말"
        assert row.media_display_name == "테스트 작품"
        assert row.decision == "채택"
        assert row.video_url.endswith("segment-shared.mp4")


def test_export_writes_video_json_csv_and_deduplicates_downloads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _seed_accepted(tmp_path, monkeypatch, decisions=ALL_ACCEPTED)
    downloader = CountingDownloader()

    with SceneCollectorDatabase.open(settings) as database:
        result = export_accepted_scenes(settings, database, downloader=downloader)

        # 관계 3개, 고유 영상 2개, 다운로드는 segment당 한 번
        assert result.relation_count == 3
        assert result.unique_video_count == 2
        assert result.downloaded_count == 2
        assert result.reused_count == 0
        assert result.failed_count == 0
        assert len(downloader.calls) == 2

        videos = tmp_path / "exports" / "videos"
        assert (videos / "segment-shared.mp4").read_bytes() == downloader.payload
        assert (videos / "segment-only-a.mp4").is_file()
        assert not list(videos.glob("*.part"))

        manifest = json.loads(result.json_path.read_text(encoding="utf-8"))
        assert manifest["schema"] == "accepted-scenes-v1"
        scenes = manifest["scenes"]
        assert len(scenes) == 3
        shared_rows = [s for s in scenes if s["segment_public_id"] == "segment-shared"]
        assert {s["japanese"] for s in shared_rows} == {"大丈夫ですか", "ありがとう"}
        assert all(s["video_file"] == "videos/segment-shared.mp4" for s in shared_rows)
        assert scenes[0]["korean_intent"] == "괜찮냐고 묻는 말"

        raw_csv = result.csv_path.read_bytes()
        assert raw_csv.startswith(b"\xef\xbb\xbf")  # Excel용 UTF-8 BOM
        reader = csv.DictReader(io.StringIO(raw_csv.decode("utf-8-sig")))
        csv_rows = list(reader)
        assert len(csv_rows) == 3
        assert csv_rows[0]["korean_intent"] == "괜찮냐고 묻는 말"
        assert {row["japanese"] for row in csv_rows} == {"大丈夫ですか", "ありがとう"}
        assert any(row["japanese_text"] == "大丈夫ですか、ありがとう。" for row in csv_rows)

        # DB schema는 그대로다
        assert database.schema_version == SCHEMA_VERSION == 3

        # 두 번째 export: 기존 MP4 재사용, network(다운로드) 호출 0
        downloader.calls.clear()
        second = export_accepted_scenes(settings, database, downloader=downloader)
        assert downloader.calls == []
        assert second.downloaded_count == 0
        assert second.reused_count == 2
        assert second.failed_count == 0


def test_failed_download_leaves_no_partial_and_keeps_existing_video(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _seed_accepted(tmp_path, monkeypatch, decisions=ALL_ACCEPTED)
    videos = tmp_path / "exports" / "videos"
    videos.mkdir(parents=True)
    (videos / "segment-shared.mp4").write_bytes(b"existing-good-video")

    def failing_downloader(url: str, destination: Path) -> None:
        destination.write_bytes(b"partial")
        raise ExportError("network 실패")

    with SceneCollectorDatabase.open(settings) as database:
        result = export_accepted_scenes(settings, database, downloader=failing_downloader)

    # 기존 정상 파일은 재사용되고 손상되지 않는다
    assert (videos / "segment-shared.mp4").read_bytes() == b"existing-good-video"
    assert result.reused_count == 1
    # 실패한 장면은 실패로 집계되고 .part 잔류가 없다
    assert result.failed_count == 1
    assert result.failures[0][0] == "segment-only-a"
    assert not (videos / "segment-only-a.mp4").exists()
    assert not list(videos.glob("*.part"))
    # manifest에는 실패 장면의 video_file이 비어 있다
    manifest = json.loads(result.json_path.read_text(encoding="utf-8"))
    by_segment = {s["segment_public_id"]: s for s in manifest["scenes"]}
    assert by_segment["segment-only-a"]["video_file"] is None
    assert by_segment["segment-shared"]["video_file"] == "videos/segment-shared.mp4"


def test_zero_byte_video_is_not_treated_as_complete(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _seed_accepted(
        tmp_path, monkeypatch, decisions={"大丈夫ですか:segment-only-a": "채택"}
    )
    videos = tmp_path / "exports" / "videos"
    videos.mkdir(parents=True)
    (videos / "segment-only-a.mp4").write_bytes(b"")
    downloader = CountingDownloader(payload=b"real-bytes")

    with SceneCollectorDatabase.open(settings) as database:
        result = export_accepted_scenes(settings, database, downloader=downloader)

    assert len(downloader.calls) == 1
    assert result.downloaded_count == 1
    assert (videos / "segment-only-a.mp4").read_bytes() == b"real-bytes"

    def zero_downloader(url: str, destination: Path) -> None:
        destination.write_bytes(b"")

    with SceneCollectorDatabase.open(settings) as database:
        (videos / "segment-only-a.mp4").unlink()
        second = export_accepted_scenes(settings, database, downloader=zero_downloader)
    assert second.failed_count == 1
    assert not (videos / "segment-only-a.mp4").exists()


def test_manifest_write_failure_preserves_existing_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _seed_accepted(
        tmp_path, monkeypatch, decisions={"大丈夫ですか:segment-only-a": "채택"}
    )
    downloader = CountingDownloader()
    with SceneCollectorDatabase.open(settings) as database:
        first = export_accepted_scenes(settings, database, downloader=downloader)
        original = first.json_path.read_text(encoding="utf-8")

        def broken_dumps(*args, **kwargs):
            raise ValueError("직렬화 실패")

        monkeypatch.setattr(export_module.json, "dumps", broken_dumps)
        with pytest.raises(ExportError, match="JSON"):
            export_accepted_scenes(settings, database, downloader=downloader)

    assert first.json_path.read_text(encoding="utf-8") == original
    assert not list(first.json_path.parent.glob("*.tmp"))


def test_no_accepted_scenes_returns_empty_without_network(tmp_path: Path) -> None:
    settings = _settings(tmp_path)

    def exploding_downloader(url: str, destination: Path) -> None:
        raise AssertionError("채택 0개에서는 다운로드가 호출되면 안 됩니다")

    with SceneCollectorDatabase.open(settings) as database:
        result = export_accepted_scenes(settings, database, downloader=exploding_downloader)
    assert result.relation_count == 0
    assert result.has_scenes is False
    assert result.json_path is None and result.csv_path is None
    assert not (tmp_path / "exports").exists()


def test_video_filename_rejects_path_traversal() -> None:
    assert video_filename("abcDEF123_-x") == "abcDEF123_-x.mp4"
    for bad in ("../evil", "a/b", "a\\b", "..", "", "a.b", "a b"):
        with pytest.raises(ExportError, match="안전하지 않은"):
            video_filename(bad)
