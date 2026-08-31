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


class SubtitleVersionError(ValueError):
    """같은 화·같은 작품의 자막 판본이 겹쳐 색인이 부풀 수 있을 때 발생한다.

    Jimaku 한 entry에는 같은 화의 판본(Netflix/BD/팬섭, SRT/ASS)이 여러 개
    있을 수 있다. 이를 조용히 전부 색인하면 같은 대사가 판본 수만큼 중복되어
    "정확 동일표현 장면 수"가 가짜로 커진다. source unit 폴더에는 사용할 판본
    하나만 두는 것이 계약이며, 위반은 색인 전에 거절한다.
    """


@dataclass(frozen=True)
class SubtitleIndexReport:
    """색인 전후에 사용자에게 보여줄 실제 인식 결과."""

    file_count: int
    episodes: tuple[int, ...]
    cue_count: int


def _subtitle_files(directory: Path) -> list[Path]:
    if not directory.is_dir():
        raise ValueError(f"자막 폴더가 없습니다: {directory}")
    files = sorted(
        path for path in directory.iterdir() if path.suffix.lower() in SUBTITLE_SUFFIXES
    )
    if not files:
        raise ValueError(f"자막 파일(.srt/.ass/.ssa)이 없습니다: {directory}")
    return files


def _parse_file(path: Path, episode: int | None) -> list[SubtitleCue]:
    subs = pysubs2.load(str(path), encoding="utf-8")
    events = sorted(
        (event for event in subs.events if not event.is_comment),
        key=lambda event: (event.start, event.end),
    )
    cues: list[SubtitleCue] = []
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


def parse_subtitle_directory(directory: Path) -> list[SubtitleCue]:
    """폴더의 SRT/ASS 파일들을 화수·시각·원문 cue 목록으로 파싱한다."""
    cues: list[SubtitleCue] = []
    for path in _subtitle_files(directory):
        cues.extend(_parse_file(path, episode_from_filename(path.name)))
    return cues


def parse_source_unit_directory(
    directory: Path,
    *,
    media_type: str,
) -> tuple[list[SubtitleCue], SubtitleIndexReport]:
    """source unit 하나의 자막 폴더를 판본 중복 검증과 함께 파싱한다.

    - TV: 화당 파일 1개. 화수를 인식할 수 없는 파일이나 같은 화의 파일 여러 개는
      조용히 색인하지 않고 거절한다.
    - 극장판: 파일 정확히 1개. 여러 판본을 함께 넣으면 거절한다. 화수는 없음.
    """
    if media_type not in {"tv", "movie"}:
        raise ValueError(f"알 수 없는 source unit 종류입니다: {media_type!r}")

    files = _subtitle_files(directory)

    if media_type == "movie":
        if len(files) != 1:
            names = ", ".join(path.name for path in files)
            raise SubtitleVersionError(
                "극장판 자막 폴더에는 사용할 판본 파일 하나만 두세요. "
                f"자막 파일 {len(files)}개가 발견됐습니다: {names}"
            )
        cues = _parse_file(files[0], None)
        if not cues:
            raise ValueError(f"자막에서 대사를 읽지 못했습니다: {files[0].name}")
        return cues, SubtitleIndexReport(file_count=1, episodes=(), cue_count=len(cues))

    episode_files: dict[int, list[str]] = {}
    unknown: list[str] = []
    for path in files:
        episode = episode_from_filename(path.name)
        if episode is None:
            unknown.append(path.name)
        else:
            episode_files.setdefault(episode, []).append(path.name)
    if unknown:
        raise SubtitleVersionError(
            "화수를 인식할 수 없는 자막 파일이 있습니다. 파일명에 화수를 남기고 "
            f"사용할 판본 하나만 두세요: {', '.join(unknown)}"
        )
    duplicated = {
        episode: names for episode, names in episode_files.items() if len(names) > 1
    }
    if duplicated:
        detail = " / ".join(
            f"{episode}화({', '.join(names)})" for episode, names in sorted(duplicated.items())
        )
        raise SubtitleVersionError(
            f"같은 화의 자막 파일이 여러 개 있습니다: {detail}. "
            "화당 사용할 판본 파일 하나만 남기고 다시 색인하세요."
        )

    cues: list[SubtitleCue] = []
    for path in files:
        cues.extend(_parse_file(path, episode_from_filename(path.name)))
    if not cues:
        raise ValueError(f"자막에서 대사를 읽지 못했습니다: {directory}")
    return cues, SubtitleIndexReport(
        file_count=len(files),
        episodes=tuple(sorted(episode_files)),
        cue_count=len(cues),
    )


def index_source_unit(
    database: SceneCollectorDatabase,
    display_name: str,
    directory: Path,
    *,
    media_type: str,
) -> tuple[StoredMedia, SubtitleIndexReport]:
    """source unit 자막 폴더를 검증 후 색인한다. 재색인하면 통째로 교체한다."""
    cues, report = parse_source_unit_directory(directory, media_type=media_type)
    media = database.register_local_media(display_name)
    database.replace_local_segments(media.id, cues)
    return media, report


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
