"""timed Japanese subtitle POC — 자막 폴더에서 표현을 찾아 원본 장면 위치를 출력한다.

Nadeshiko 미수록 작품의 SRT/ASS 자막(사용자가 별도로 확보)을 기존 Task 5
surface matcher로 검색해 작품/Season/Episode/타임코드를 출력하는 범용 POC다.
특정 작품 전용 로직은 두지 않는다. DB에는 아무것도 저장하지 않는다.

사용:
    uv run --with pysubs2 python experiments/subtitle_poc/search_subtitles.py \
        <자막폴더> --title "작품명" [--season 1] [--expressions 大丈夫 ...]
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import pysubs2

from scene_collector.surface import matches_surface

DEFAULT_EXPRESSIONS = ("大丈夫", "ありがとう", "ごめん", "何してる", "どうした")
SUBTITLE_SUFFIXES = {".srt", ".ass", ".ssa"}

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
    """기존 segments 개념(episode/start/end/일본어 원문)을 미러한 장면 후보."""

    episode: int | None
    start_time_ms: int
    end_time_ms: int
    japanese_text: str
    source_file: str


def episode_from_filename(name: str) -> int | None:
    stem = Path(name).stem
    for pattern in _EPISODE_PATTERNS:
        match = pattern.search(stem)
        if match:
            return int(match.group(1))
    return None


def load_cues(directory: Path) -> list[SubtitleCue]:
    cues: list[SubtitleCue] = []
    files = sorted(
        path for path in directory.iterdir()
        if path.suffix.lower() in SUBTITLE_SUFFIXES
    )
    if not files:
        raise SystemExit(f"자막 파일(.srt/.ass/.ssa)이 없습니다: {directory}")

    for path in files:
        episode = episode_from_filename(path.name)
        subs = pysubs2.load(str(path), encoding="utf-8")
        for event in subs.events:
            if event.is_comment:
                continue
            text = event.plaintext.replace("\n", " ").strip()
            if not text:
                continue
            cues.append(
                SubtitleCue(
                    episode=episode,
                    start_time_ms=int(event.start),
                    end_time_ms=int(event.end),
                    japanese_text=text,
                    source_file=path.name,
                )
            )
    return cues


def hms(ms: int) -> str:
    seconds, milli = divmod(ms, 1000)
    hours, rest = divmod(seconds, 3600)
    minutes, sec = divmod(rest, 60)
    return f"{hours:02d}:{minutes:02d}:{sec:02d}.{milli:03d}"


def search(cues: list[SubtitleCue], expression: str) -> list[SubtitleCue]:
    return [
        cue
        for cue in cues
        if matches_surface(cue.japanese_text, expression)
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path, help="자막 폴더 (화당 파일 1개)")
    parser.add_argument("--title", required=True, help="작품명 (출력 표기용)")
    parser.add_argument("--season", default=None, help="Season 표기 (선택)")
    parser.add_argument(
        "--expressions",
        nargs="+",
        default=list(DEFAULT_EXPRESSIONS),
        help="검색할 일본어 표현 목록",
    )
    parser.add_argument(
        "--max-per-expression",
        type=int,
        default=5,
        help="표현당 출력할 최대 장면 수",
    )
    args = parser.parse_args()

    if not args.directory.is_dir():
        raise SystemExit(f"자막 폴더가 없습니다: {args.directory}")

    cues = load_cues(args.directory)
    episodes = sorted({cue.episode for cue in cues if cue.episode is not None})
    print(f"자막 cue {len(cues)}개, 화수 파일 {episodes if episodes else '없음(극장판?)'}")

    for expression in args.expressions:
        hits = search(cues, expression)
        print(f"\n=== 표현 {expression!r}: {len(hits)}개 장면 ===")
        for cue in hits[: args.max_per_expression]:
            print(f"작품: {args.title}")
            if args.season is not None:
                print(f"Season: {args.season}")
            episode_label = cue.episode if cue.episode is not None else "극장판/단편"
            print(f"Episode: {episode_label}")
            print(f"Start: {hms(cue.start_time_ms)}")
            print(f"End: {hms(cue.end_time_ms)}")
            print(f"대사: {cue.japanese_text}")
            print("---")
        if len(hits) > args.max_per_expression:
            print(f"... 외 {len(hits) - args.max_per_expression}개")
    return 0


if __name__ == "__main__":
    sys.exit(main())
