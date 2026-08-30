import copy
import csv
import io
import json
from pathlib import Path

import pytest
from nadeshiko.models import Segment

import scene_collector.export as export_module
from scene_collector.config import AISettings, AppSettings, SearchSettings, StorageSettings
from scene_collector.database import SCHEMA_VERSION, SceneCollectorDatabase
from scene_collector.export import (
    ExportError,
    export_accepted_scenes,
    video_filename,
)

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "nadeshiko_search_response.json"
_FIXTURE = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))

MEDIA_PUBLIC_ID = "anonymous-media-001"
MEDIA_DISPLAY_NAME = "테스트 작품"

# 두 한국어 의미가 서로 다른 표현을 갖고, 그중 segment-shared 장면 하나는
# 두 의미 모두에서 작업된다. segment-only-b는 판정을 하지 않는 미판정 장면이다.
_WORK_SCENES = (
    ("괜찮냐고 묻는 말", "大丈夫ですか", "だいじょうぶですか", "segment-shared", "大丈夫ですか、ありがとう。"),
    ("괜찮냐고 묻는 말", "大丈夫ですか", "だいじょうぶですか", "segment-only-a", "あの、大丈夫ですか？"),
    ("고맙다고 말하기", "ありがとう", "ありがとう", "segment-shared", "大丈夫ですか、ありがとう。"),
    ("고맙다고 말하기", "ありがとう", "ありがとう", "segment-only-b", "ありがとうございます。"),
)

# 번역·메모까지 실제로 작업한 장면. 내보내기 행에 그대로 실려야 한다.
_TRANSLATED_KEY = "大丈夫ですか:segment-shared"

ALL_ACCEPTED = {
    "大丈夫ですか:segment-shared": "채택",
    "大丈夫ですか:segment-only-a": "채택",
    "ありがとう:segment-shared": "채택",
}


def _settings(work_data_dir: Path) -> AppSettings:
    return AppSettings(
        storage=StorageSettings(work_data_dir=work_data_dir),
        ai=AISettings(service="provider-one", model="model-one"),
        search=SearchSettings(),
    )


def _segment(public_id: str, video_url: str) -> Segment:
    """fixture 장면 하나를 지정한 ID와 현재 영상 주소로 바꿔 만든다."""
    payload = copy.deepcopy(_FIXTURE["segments"][0])
    payload["publicId"] = public_id
    payload["urls"]["videoUrl"] = video_url
    return Segment.from_dict(payload)


class CountingNadeshiko:
    """get_segment 호출을 세는 가짜 Nadeshiko 연결. 검색은 하지 않는다."""

    def __init__(self, video_urls: dict[str, str] | None = None) -> None:
        self.video_urls = video_urls or {}
        self.calls: list[str] = []

    def get_segment(self, segment_public_id: str) -> Segment:
        self.calls.append(segment_public_id)
        url = self.video_urls.get(
            segment_public_id,
            f"https://media.example.invalid/current/{segment_public_id}.mp4",
        )
        return _segment(segment_public_id, url)


class ExplodingNadeshiko:
    """호출되면 안 되는 자리에 두는 가짜 Nadeshiko 연결."""

    def get_segment(self, segment_public_id: str) -> Segment:
        raise AssertionError("이 시험에서는 Nadeshiko 호출이 있으면 안 됩니다")


class CountingDownloader:
    def __init__(self, payload: bytes = b"fake-mp4-bytes") -> None:
        self.payload = payload
        self.calls: list[str] = []

    def __call__(self, url: str, destination: Path) -> None:
        self.calls.append(url)
        destination.write_bytes(self.payload)


def _seed_work_scenes(tmp_path: Path, *, decisions: dict[str, str]) -> AppSettings:
    """의미→표현 관계와 작업 장면을 만들고 요청한 판정만 저장한다.

    decisions 키는 "<일본어 표현>:<장면 ID>" 형식이며, 없는 장면은 미판정으로
    남는다.
    """
    settings = _settings(tmp_path)
    with SceneCollectorDatabase.open(settings) as database:
        for korean_meaning, japanese, reading, segment_public_id, japanese_text in _WORK_SCENES:
            meaning = database.upsert_meaning(korean_meaning)
            relation = database.add_meaning_expression(
                meaning.id,
                japanese=japanese,
                reading=reading,
                meaning_ko=f"{korean_meaning}의 뜻",
                register_text="정중체",
            )
            work_scene_id = database.upsert_work_scene(
                relation.id,
                segment_public_id=segment_public_id,
                media_public_id=MEDIA_PUBLIC_ID,
                media_display_name=MEDIA_DISPLAY_NAME,
                episode=1,
                start_time_ms=1_000,
                end_time_ms=3_000,
                japanese_text=japanese_text,
            )
            key = f"{japanese}:{segment_public_id}"
            if key in decisions:
                database.set_work_scene_decision(work_scene_id, decisions[key])
            if key == _TRANSLATED_KEY:
                database.save_work_scene_translation(
                    work_scene_id,
                    direct_meaning="괜찮습니까",
                    natural_translation="괜찮으세요?",
                    scene_usage="상대를 걱정하며 묻는 장면",
                    ai_service="provider-one",
                    ai_model="model-one",
                    instruction_version="scene-translation-v1",
                )
                database.set_work_scene_notes(work_scene_id, "도입부 후보")
    return settings


def _manifest_scenes(result_json_path: Path) -> list[dict]:
    return json.loads(result_json_path.read_text(encoding="utf-8"))["scenes"]


def test_only_accepted_work_scenes_are_exported(tmp_path: Path) -> None:
    settings = _seed_work_scenes(
        tmp_path,
        decisions={
            "大丈夫ですか:segment-shared": "채택",
            "ありがとう:segment-shared": "예비",
            "大丈夫ですか:segment-only-a": "제외",
        },
    )
    client = CountingNadeshiko()
    downloader = CountingDownloader()

    with SceneCollectorDatabase.open(settings) as database:
        result = export_accepted_scenes(
            settings, database, nadeshiko_client=client, downloader=downloader
        )
        assert database.schema_version == SCHEMA_VERSION == 4

    # 예비·제외·미판정(segment-only-b)은 모두 빠지고 채택 한 건만 남는다
    assert result.relation_count == 1
    assert result.unique_video_count == 1
    assert client.calls == ["segment-shared"]

    scenes = _manifest_scenes(result.json_path)
    assert len(scenes) == 1
    scene = scenes[0]
    assert scene["korean_meaning"] == "괜찮냐고 묻는 말"
    assert scene["japanese"] == "大丈夫ですか"
    assert scene["segment_public_id"] == "segment-shared"
    assert scene["decision"] == "채택"
    assert scene["media_display_name"] == MEDIA_DISPLAY_NAME
    assert scene["media_public_id"] == MEDIA_PUBLIC_ID
    assert scene["natural_translation"] == "괜찮으세요?"
    assert scene["notes"] == "도입부 후보"


def test_shared_scene_keeps_one_video_and_separate_meaning_rows(tmp_path: Path) -> None:
    settings = _seed_work_scenes(tmp_path, decisions=ALL_ACCEPTED)
    client = CountingNadeshiko()
    downloader = CountingDownloader()

    with SceneCollectorDatabase.open(settings) as database:
        result = export_accepted_scenes(
            settings, database, nadeshiko_client=client, downloader=downloader
        )

    # 관계 3개, 고유 영상 2개, MP4 다운로드는 장면당 한 번뿐이다
    assert result.relation_count == 3
    assert result.unique_video_count == 2
    assert result.downloaded_count == 2
    assert result.reused_count == 0
    assert result.failed_count == 0
    assert result.has_scenes is True
    assert sorted(client.calls) == ["segment-only-a", "segment-shared"]
    assert len(downloader.calls) == 2

    videos = tmp_path / "exports" / "videos"
    assert (videos / "segment-shared.mp4").read_bytes() == downloader.payload
    assert (videos / "segment-only-a.mp4").is_file()
    assert not list(videos.glob("*.part"))

    manifest = json.loads(result.json_path.read_text(encoding="utf-8"))
    assert manifest["schema"] == "accepted-scenes-v2"
    scenes = manifest["scenes"]
    assert len(scenes) == 3

    # 같은 장면이지만 의미가 다른 두 행이며, 의미를 합치지 않는다
    shared_rows = [scene for scene in scenes if scene["segment_public_id"] == "segment-shared"]
    assert len(shared_rows) == 2
    assert {scene["korean_meaning"] for scene in shared_rows} == {
        "괜찮냐고 묻는 말",
        "고맙다고 말하기",
    }
    assert {scene["japanese"] for scene in shared_rows} == {"大丈夫ですか", "ありがとう"}
    assert all(scene["video_file"] == "videos/segment-shared.mp4" for scene in shared_rows)
    for scene in shared_rows:
        expected = "괜찮냐고 묻는 말" if scene["japanese"] == "大丈夫ですか" else "고맙다고 말하기"
        assert scene["korean_meaning"] == expected
        assert scene["meaning_ko"] == f"{expected}의 뜻"

    raw_csv = result.csv_path.read_bytes()
    assert raw_csv.startswith(b"\xef\xbb\xbf")  # Excel용 UTF-8 BOM
    reader = csv.DictReader(io.StringIO(raw_csv.decode("utf-8-sig")))
    csv_rows = list(reader)
    assert "korean_meaning" in reader.fieldnames
    assert "video_url" not in reader.fieldnames  # 영상 주소는 저장·내보내기하지 않는다
    assert len(csv_rows) == 3
    csv_shared = [row for row in csv_rows if row["segment_public_id"] == "segment-shared"]
    assert {row["korean_meaning"] for row in csv_shared} == {
        "괜찮냐고 묻는 말",
        "고맙다고 말하기",
    }
    assert any(row["japanese_text"] == "大丈夫ですか、ありがとう。" for row in csv_rows)
    assert all(row["decision"] == "채택" for row in csv_rows)


def test_existing_video_is_reused_without_nadeshiko_call(tmp_path: Path) -> None:
    settings = _seed_work_scenes(tmp_path, decisions=ALL_ACCEPTED)
    client = CountingNadeshiko()
    downloader = CountingDownloader()

    with SceneCollectorDatabase.open(settings) as database:
        export_accepted_scenes(
            settings, database, nadeshiko_client=client, downloader=downloader
        )
        client.calls.clear()
        downloader.calls.clear()
        second = export_accepted_scenes(
            settings, database, nadeshiko_client=client, downloader=downloader
        )

    # 정상 MP4가 이미 있으면 장면 재조회도 다운로드도 하지 않는다
    assert client.calls == []
    assert downloader.calls == []
    assert second.downloaded_count == 0
    assert second.reused_count == 2
    assert second.failed_count == 0
    assert second.relation_count == 3


def test_missing_video_downloads_from_current_segment_url(tmp_path: Path) -> None:
    settings = _seed_work_scenes(tmp_path, decisions={"大丈夫ですか:segment-only-a": "채택"})
    fresh_url = "https://media.example.invalid/fresh-token/segment-only-a.mp4"
    client = CountingNadeshiko({"segment-only-a": fresh_url})
    downloader = CountingDownloader(payload=b"downloaded-bytes")

    with SceneCollectorDatabase.open(settings) as database:
        result = export_accepted_scenes(
            settings, database, nadeshiko_client=client, downloader=downloader
        )

    # 파일이 없을 때만 장면을 한 번 다시 조회해 그때의 주소로 받는다
    assert client.calls == ["segment-only-a"]
    assert downloader.calls == [fresh_url]
    assert result.downloaded_count == 1
    assert result.reused_count == 0
    videos = tmp_path / "exports" / "videos"
    assert (videos / "segment-only-a.mp4").read_bytes() == b"downloaded-bytes"


def test_failed_download_leaves_no_partial_and_keeps_existing_video(tmp_path: Path) -> None:
    settings = _seed_work_scenes(tmp_path, decisions=ALL_ACCEPTED)
    videos = tmp_path / "exports" / "videos"
    videos.mkdir(parents=True)
    (videos / "segment-shared.mp4").write_bytes(b"existing-good-video")
    client = CountingNadeshiko()

    def failing_downloader(url: str, destination: Path) -> None:
        destination.write_bytes(b"partial")
        raise ExportError("network 실패")

    with SceneCollectorDatabase.open(settings) as database:
        result = export_accepted_scenes(
            settings, database, nadeshiko_client=client, downloader=failing_downloader
        )

    # 기존 정상 파일은 재사용되고 손상되지 않는다
    assert (videos / "segment-shared.mp4").read_bytes() == b"existing-good-video"
    assert result.reused_count == 1
    assert client.calls == ["segment-only-a"]
    # 실패한 장면은 실패로 집계되고 .part 잔류가 없다
    assert result.failed_count == 1
    assert result.failures[0][0] == "segment-only-a"
    assert "network 실패" in result.failures[0][1]
    assert not (videos / "segment-only-a.mp4").exists()
    assert not list(videos.glob("*.part"))
    # manifest에는 실패 장면의 video_file이 비어 있다
    by_segment = {scene["segment_public_id"]: scene for scene in _manifest_scenes(result.json_path)}
    assert by_segment["segment-only-a"]["video_file"] is None
    assert by_segment["segment-shared"]["video_file"] == "videos/segment-shared.mp4"


def test_zero_byte_video_is_not_treated_as_complete(tmp_path: Path) -> None:
    settings = _seed_work_scenes(tmp_path, decisions={"大丈夫ですか:segment-only-a": "채택"})
    videos = tmp_path / "exports" / "videos"
    videos.mkdir(parents=True)
    (videos / "segment-only-a.mp4").write_bytes(b"")
    downloader = CountingDownloader(payload=b"real-bytes")

    with SceneCollectorDatabase.open(settings) as database:
        result = export_accepted_scenes(
            settings, database, nadeshiko_client=CountingNadeshiko(), downloader=downloader
        )

    # 0바이트 파일은 완료로 보지 않고 다시 받는다
    assert len(downloader.calls) == 1
    assert result.downloaded_count == 1
    assert result.reused_count == 0
    assert (videos / "segment-only-a.mp4").read_bytes() == b"real-bytes"

    def zero_downloader(url: str, destination: Path) -> None:
        destination.write_bytes(b"")

    with SceneCollectorDatabase.open(settings) as database:
        (videos / "segment-only-a.mp4").unlink()
        second = export_accepted_scenes(
            settings, database, nadeshiko_client=CountingNadeshiko(), downloader=zero_downloader
        )

    # 0바이트 결과도 완료가 아니라 실패다
    assert second.failed_count == 1
    assert second.downloaded_count == 0
    assert not (videos / "segment-only-a.mp4").exists()
    assert not list(videos.glob("*.part"))


def test_manifest_write_failure_preserves_existing_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _seed_work_scenes(tmp_path, decisions={"大丈夫ですか:segment-only-a": "채택"})
    downloader = CountingDownloader()
    with SceneCollectorDatabase.open(settings) as database:
        first = export_accepted_scenes(
            settings, database, nadeshiko_client=CountingNadeshiko(), downloader=downloader
        )
        original = first.json_path.read_text(encoding="utf-8")

        def broken_dumps(*args, **kwargs):
            raise ValueError("직렬화 실패")

        monkeypatch.setattr(export_module.json, "dumps", broken_dumps)
        with pytest.raises(ExportError, match="JSON"):
            export_accepted_scenes(
                settings, database, nadeshiko_client=CountingNadeshiko(), downloader=downloader
            )

    assert first.json_path.read_text(encoding="utf-8") == original
    assert not list(first.json_path.parent.glob("*.tmp"))


def test_no_accepted_scenes_returns_empty_without_network(tmp_path: Path) -> None:
    settings = _seed_work_scenes(tmp_path, decisions={"大丈夫ですか:segment-only-a": "예비"})

    def exploding_downloader(url: str, destination: Path) -> None:
        raise AssertionError("채택 0개에서는 다운로드가 호출되면 안 됩니다")

    with SceneCollectorDatabase.open(settings) as database:
        result = export_accepted_scenes(
            settings,
            database,
            nadeshiko_client=ExplodingNadeshiko(),
            downloader=exploding_downloader,
        )

    assert result.relation_count == 0
    assert result.has_scenes is False
    assert result.json_path is None and result.csv_path is None
    assert not (tmp_path / "exports").exists()


def test_video_filename_rejects_path_traversal() -> None:
    assert video_filename("abcDEF123_-x") == "abcDEF123_-x.mp4"
    for bad in ("../evil", "a/b", "a\\b", "..", "", "a.b", "a b"):
        with pytest.raises(ExportError, match="안전하지 않은"):
            video_filename(bad)
