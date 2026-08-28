"""사용자가 확보한 일본어 timed subtitle을 로컬 작품 색인으로 저장한다.

Nadeshiko 미수록 작품용 fallback이다. 파싱은 검증된 pysubs2를 사용하고
자막 파일 자체는 저장소 밖 사용자 위치에 둔다. 자동 다운로드는 없다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import pysubs2

from scene_collector.database import SceneCollectorDatabase, StoredMedia

SUBTITLE_SUFFIXES = frozenset({".srt", ".ass", ".ssa"})

# 파일명에서 화수를 찾는 범용 패턴 (작품별 예외 없음, 위에서부터 첫 일치 사용)
_EPISODE_PATTERNS = (
    re.compile(r"S\d{1,2}E(\d{1,3})", re.IGNORECASE),
    re.compile(r"第(\d{1,3})話"),
    re.compile(r"(?:^|[\s._-])(?:ep?|episode)\s*(\d{1,3})", re.IGNORECASE),
    re.compile(r"-\s*(\d{1,3})(?:\s*[\[(.]|$)"),
    re.compile(r"(?:^|[\s._])(\d{1,3})(?:\s*[\[(.]|$)"),
)


@dataclass(frozen=True)
class SubtitleCue:
    """기존 segments 개념(화수/시각/일본어 원문)을 미러한 자막 장면."""

    episode: int | None
    position: int
    start_time_ms: int
    end_time_ms: int
    japanese_text: str
    source_file: str


def episode_from_filename(name: str) -> int | None:
    """자막 파일명에서 화수를 추정한다. 극장판처럼 없으면 None."""
    stem = Path(name).stem
    for pattern in _EPISODE_PATTERNS:
        match = pattern.search(stem)
        if match:
            return int(match.group(1))
    return None


def parse_subtitle_directory(directory: Path) -> list[SubtitleCue]:
    """폴더의 SRT/ASS 파일들을 화수·시각·원문 cue 목록으로 파싱한다."""
    if not directory.is_dir():
        raise ValueError(f"자막 폴더가 없습니다: {directory}")

    files = sorted(
        path for path in directory.iterdir() if path.suffix.lower() in SUBTITLE_SUFFIXES
    )
    if not files:
        raise ValueError(f"자막 파일(.srt/.ass/.ssa)이 없습니다: {directory}")

    cues: list[SubtitleCue] = []
    for path in files:
        episode = episode_from_filename(path.name)
        subs = pysubs2.load(str(path), encoding="utf-8")
        events = sorted(
            (event for event in subs.events if not event.is_comment),
            key=lambda event: (event.start, event.end),
        )
        position = 0
        for event in events:
            text = event.plaintext.replace("\n", " ").strip()
            if not text:
                continue
            cues.append(
                SubtitleCue(
                    episode=episode,
                    position=position,
                    start_time_ms=int(event.start),
                    end_time_ms=int(event.end),
                    japanese_text=text,
                    source_file=path.name,
                )
            )
            position += 1
    return cues


def index_local_subtitles(
    database: SceneCollectorDatabase,
    display_name: str,
    directory: Path,
) -> tuple[StoredMedia, int]:
    """자막 폴더를 로컬 작품으로 등록·색인하고 (작품, 색인한 cue 수)를 반환한다.

    같은 작품을 다시 색인하면 기존 색인을 통째로 교체한다.
    """
    cues = parse_subtitle_directory(directory)
    media = database.register_local_media(display_name)
    count = database.replace_local_segments(media.id, cues)
    return media, count
