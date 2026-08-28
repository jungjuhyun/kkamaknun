"""작업 11 — 채택 장면의 MP4 저장과 제작용 JSON/CSV 내보내기.

현재 실제로 저장된 채택(decision='채택') Nadeshiko 장면만 지원한다.
로컬 자막 장면은 영상 URL/검수 저장 계약이 없어 이번 export 대상이 아니다.

- 영상 identity는 Nadeshiko segment_public_id, 파일은
  <work_data_dir>/exports/videos/<segment_public_id>.mp4 하나다.
- 같은 장면이 여러 표현에서 채택되면 MP4는 1개, metadata row는 관계별로 둔다.
- 이미 정상(>0 byte) 파일이 있으면 다시 다운로드하지 않는다.
- 다운로드는 .part 임시 파일에 받은 뒤 os.replace로 원자적으로 확정하고,
  실패 시 .part만 제거하며 기존 정상 파일은 건드리지 않는다.
- manifest(JSON/CSV)도 temp → replace로 작성해 중간 실패가 기존 파일을 깨지 않는다.

새 dependency 없이 Python 표준 라이브러리만 사용한다.
"""

from __future__ import annotations

import csv
import json
import os
import re
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from scene_collector.config import AppSettings
from scene_collector.database import AcceptedSceneExportRow, SceneCollectorDatabase

EXPORT_DIR_NAME = "exports"
VIDEOS_DIR_NAME = "videos"
JSON_FILENAME = "accepted_scenes.json"
CSV_FILENAME = "accepted_scenes.csv"
MANIFEST_SCHEMA = "accepted-scenes-v1"
_DOWNLOAD_TIMEOUT_SECONDS = 60
_SEGMENT_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")

_CSV_COLUMNS = (
    "search_run_id",
    "korean_intent",
    "expression_id",
    "japanese",
    "reading",
    "meaning_ko",
    "register",
    "segment_public_id",
    "media_public_id",
    "media_display_name",
    "episode",
    "start_time_ms",
    "end_time_ms",
    "japanese_text",
    "direct_meaning",
    "natural_translation",
    "scene_usage",
    "notes",
    "decision",
    "video_file",
    "video_url",
)

Downloader = Callable[[str, Path], None]


class ExportError(RuntimeError):
    """export 결과 전체를 만들 수 없을 때 발생한다."""


@dataclass(frozen=True)
class ExportResult:
    """한 번의 채택 장면 export 실행 결과."""

    relation_count: int
    unique_video_count: int
    downloaded_count: int
    reused_count: int
    failed_count: int
    json_path: Path | None
    csv_path: Path | None
    failures: tuple[tuple[str, str], ...]

    @property
    def has_scenes(self) -> bool:
        return self.relation_count > 0


def video_filename(segment_public_id: str) -> str:
    """segment_public_id를 안전한 결정적 파일명으로 바꾼다. traversal 불가."""
    if not _SEGMENT_ID_PATTERN.fullmatch(segment_public_id or ""):
        raise ExportError(f"안전하지 않은 segment ID입니다: {segment_public_id!r}")
    return f"{segment_public_id}.mp4"


def _download_with_stdlib(url: str, destination: Path) -> None:
    """저장된 video_url의 실제 bytes를 임시 경로에 저장한다."""
    if urlparse(url or "").scheme.lower() not in {"http", "https"}:
        raise ExportError(f"video_url이 비어 있거나 http(s)가 아닙니다: {url!r}")
    request = urllib.request.Request(url, headers={"User-Agent": "scene-collector-export"})
    with urllib.request.urlopen(request, timeout=_DOWNLOAD_TIMEOUT_SECONDS) as response:
        with destination.open("wb") as handle:
            while True:
                chunk = response.read(1024 * 256)
                if not chunk:
                    break
                handle.write(chunk)


def _has_valid_video(path: Path) -> bool:
    try:
        return path.is_file() and path.stat().st_size > 0
    except OSError:
        return False


def _fetch_video(url: str, final_path: Path, downloader: Downloader) -> None:
    """part 파일로 받은 뒤 성공 시에만 최종 파일로 원자 교체한다."""
    part_path = final_path.with_name(final_path.name + ".part")
    try:
        downloader(url, part_path)
        if not _has_valid_video(part_path):
            raise ExportError("다운로드 결과가 비어 있습니다(0 byte).")
        os.replace(part_path, final_path)
    finally:
        part_path.unlink(missing_ok=True)


def _atomic_write_text(path: Path, content: str, *, encoding: str) -> None:
    temp_path = path.with_name(path.name + ".tmp")
    try:
        temp_path.write_text(content, encoding=encoding, newline="")
        os.replace(temp_path, path)
    finally:
        temp_path.unlink(missing_ok=True)


def _manifest_scene(row: AcceptedSceneExportRow, video_file: str | None) -> dict[str, object]:
    return {
        "search_run_id": row.search_run_id,
        "korean_intent": row.korean_intent,
        "expression_id": row.expression_id,
        "japanese": row.japanese,
        "reading": row.reading,
        "meaning_ko": row.meaning_ko,
        "register": row.register,
        "segment_public_id": row.segment_public_id,
        "media_public_id": row.media_public_id,
        "media_display_name": row.media_display_name,
        "episode": row.episode,
        "start_time_ms": row.start_time_ms,
        "end_time_ms": row.end_time_ms,
        "japanese_text": row.japanese_text,
        "direct_meaning": row.direct_meaning,
        "natural_translation": row.natural_translation,
        "scene_usage": row.scene_usage,
        "notes": row.notes,
        "decision": row.decision,
        "video_file": video_file,
        "video_url": row.video_url,
    }


def export_accepted_scenes(
    settings: AppSettings,
    database: SceneCollectorDatabase,
    *,
    downloader: Downloader | None = None,
) -> ExportResult:
    """채택 장면 전체를 work_data_dir/exports로 내보낸다.

    채택 장면이 없으면 network 호출 없이 빈 결과를 돌려준다.
    """
    rows = database.list_accepted_scenes()
    if not rows:
        return ExportResult(0, 0, 0, 0, 0, None, None, ())

    fetch = downloader if downloader is not None else _download_with_stdlib
    export_dir = settings.storage.work_data_dir / EXPORT_DIR_NAME
    videos_dir = export_dir / VIDEOS_DIR_NAME
    try:
        videos_dir.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise ExportError(f"export 디렉터리를 만들 수 없습니다: {error}") from error

    # 영상 identity는 segment_public_id 하나다. 같은 장면은 한 번만 처리한다.
    unique_videos: dict[str, str] = {}
    for row in rows:
        unique_videos.setdefault(row.segment_public_id, row.video_url)

    downloaded = 0
    reused = 0
    failures: list[tuple[str, str]] = []
    video_files: dict[str, str | None] = {}
    for segment_public_id, url in unique_videos.items():
        try:
            filename = video_filename(segment_public_id)
            final_path = videos_dir / filename
            if _has_valid_video(final_path):
                reused += 1
            else:
                _fetch_video(url, final_path, fetch)
                downloaded += 1
            video_files[segment_public_id] = f"{VIDEOS_DIR_NAME}/{filename}"
        except Exception as error:  # 장면 하나의 실패가 전체를 멈추지 않게 한다
            failures.append((segment_public_id, str(error)))
            video_files[segment_public_id] = None

    scenes = [_manifest_scene(row, video_files.get(row.segment_public_id)) for row in rows]

    json_path = export_dir / JSON_FILENAME
    manifest = {
        "schema": MANIFEST_SCHEMA,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "scenes": scenes,
    }
    try:
        _atomic_write_text(
            json_path, json.dumps(manifest, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
        )
    except (OSError, TypeError, ValueError) as error:
        raise ExportError(f"JSON manifest 작성에 실패했습니다: {error}") from error

    csv_path = export_dir / CSV_FILENAME
    try:
        lines: list[str] = []
        writer_target = _CsvBuffer(lines)
        writer = csv.DictWriter(writer_target, fieldnames=_CSV_COLUMNS)
        writer.writeheader()
        for scene in scenes:
            writer.writerow({column: scene[column] for column in _CSV_COLUMNS})
        # Excel에서 한국어/일본어가 깨지지 않도록 BOM 포함 UTF-8을 사용한다.
        _atomic_write_text(csv_path, "".join(lines), encoding="utf-8-sig")
    except (OSError, ValueError) as error:
        raise ExportError(f"CSV 작성에 실패했습니다: {error}") from error

    return ExportResult(
        relation_count=len(rows),
        unique_video_count=len(unique_videos),
        downloaded_count=downloaded,
        reused_count=reused,
        failed_count=len(failures),
        json_path=json_path,
        csv_path=csv_path,
        failures=tuple(failures),
    )


class _CsvBuffer:
    """csv.writer가 요구하는 write 인터페이스로 문자열 목록을 채운다."""

    def __init__(self, lines: list[str]) -> None:
        self._lines = lines

    def write(self, text: str) -> None:
        self._lines.append(text)
