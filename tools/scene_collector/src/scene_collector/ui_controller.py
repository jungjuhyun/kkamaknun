"""화면이 기존 검증 기능을 호출할 때 쓰는 얇은 어댑터.

NiceGUI에 의존하지 않아 자동시험으로 검증한다. 새 검색·번역·저장 알고리즘을
만들지 않고 database/search/translate/export의 기존 함수만 연결한다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from nadeshiko import Nadeshiko
from nadeshiko.models import Segment

from scene_collector.config import AppSettings
from scene_collector.database import (
    LocalSegmentMatch,
    ReviewDecision,
    SceneCollectorDatabase,
    StoredMeaningExpression,
    StoredWorkScene,
    database_path,
)
from scene_collector.search import (
    SelectedExpressionScenes,
    find_saved_expressions,
    generate_expressions,
    search_selected_expression,
)
from scene_collector.translate import (
    TRANSLATION_INSTRUCTION_VERSION,
    TranslatedScene,
    translate_segment,
)

REVIEW_DECISIONS: tuple[ReviewDecision, ...] = ("채택", "예비", "제외")


@dataclass(frozen=True)
class SettingsSummary:
    """설정 화면에 보여줄 값. 비밀키 값 자체는 절대 담지 않는다."""

    work_data_dir: Path
    database_file: Path
    ai_service: str
    ai_model: str
    expression_generation_limit: int
    nadeshiko_take: int
    nadeshiko_key_set: bool


@dataclass(frozen=True)
class ExpressionScreen:
    """한 한국어 의미와 그 의미에 저장된 표현 전부."""

    korean_meaning: str
    relations: tuple[StoredMeaningExpression, ...]

    @property
    def has_expressions(self) -> bool:
        return bool(self.relations)


@dataclass(frozen=True)
class ExpressionLookup:
    """[표현 찾기] 한 번의 결과. AI를 실제로 호출했는지 함께 알려준다."""

    screen: ExpressionScreen
    added: tuple[StoredMeaningExpression, ...]
    used_ai: bool


@dataclass(frozen=True)
class SceneRow:
    """장면 목록 한 줄. 이미 작업한 장면이면 저장 상태가 함께 온다."""

    segment: Segment
    media_display_name: str
    work_scene: StoredWorkScene | None

    @property
    def segment_public_id(self) -> str:
        return self.segment.public_id

    @property
    def decision(self) -> str | None:
        return self.work_scene.decision if self.work_scene else None


@dataclass
class SceneWorkState:
    """장면 검수 화면이 지금 다루는 대상. 의미나 표현을 바꾸면 전부 비운다.

    검색 결과는 저장하지 않으므로 이 상태는 창 하나가 열려 있는 동안만 산다.
    """

    relation: StoredMeaningExpression | None = None
    found: SelectedExpressionScenes | None = None
    rows: tuple[SceneRow, ...] = ()
    saved_scenes: tuple[StoredWorkScene, ...] = field(default_factory=tuple)
    selected_index: int | None = None

    def clear(self) -> None:
        """이전 의미·표현의 장면 결과를 하나도 남기지 않는다."""
        self.relation = None
        self.found = None
        self.rows = ()
        self.saved_scenes = ()
        self.selected_index = None

    def start_relation(self, relation: StoredMeaningExpression) -> None:
        """새 의미→표현 관계로 넘어간다. 이전 결과는 남기지 않는다."""
        self.clear()
        self.relation = relation

    def show_results(self, found: SelectedExpressionScenes, rows: tuple[SceneRow, ...]) -> None:
        """검색이 성공했을 때만 결과를 채운다. 장면은 아직 고르지 않은 상태다."""
        self.found = found
        self.rows = rows
        self.selected_index = None

    def selected_row(self) -> SceneRow | None:
        if self.selected_index is None or not 0 <= self.selected_index < len(self.rows):
            return None
        return self.rows[self.selected_index]

    @property
    def local_segments(self) -> tuple[LocalSegmentMatch, ...]:
        return self.found.local_segments if self.found else ()


class VideoPlayer(Protocol):
    """단일 영상 플레이어에서 이 어댑터가 쓰는 부분만."""

    def pause(self) -> None: ...

    def set_source(self, source: str) -> object: ...


def reset_player(player: VideoPlayer | None) -> None:
    """이전 영상이 더 이상 보이거나 재생되지 않게 하나뿐인 플레이어를 비운다.

    플레이어 인스턴스는 그대로 두고 재생만 멈추고 source를 지운다.
    """
    if player is None:
        return
    player.pause()
    player.set_source("")


def settings_summary(settings: AppSettings) -> SettingsSummary:
    """현재 설정을 화면 표시용으로 요약한다. 키는 존재 여부만 담는다."""
    secret = settings.nadeshiko_api_key
    key_set = secret is not None and bool(secret.get_secret_value().strip())
    return SettingsSummary(
        work_data_dir=settings.storage.work_data_dir,
        database_file=database_path(settings),
        ai_service=settings.ai.service,
        ai_model=settings.ai.model,
        expression_generation_limit=settings.search.expression_generation_limit,
        nadeshiko_take=settings.search.nadeshiko_take,
        nadeshiko_key_set=key_set,
    )


def lookup_expressions(
    database: SceneCollectorDatabase, korean_meaning: str
) -> ExpressionScreen:
    """저장된 표현만 조회한다. AI도 Nadeshiko도 호출하지 않는다."""
    relations = find_saved_expressions(database, korean_meaning)
    meaning = database.find_meaning(korean_meaning)
    display = meaning.display_korean_meaning if meaning else (korean_meaning or "").strip()
    return ExpressionScreen(korean_meaning=display, relations=relations)


def lookup_or_generate_expressions(
    settings: AppSettings,
    database: SceneCollectorDatabase,
    korean_meaning: str,
) -> ExpressionLookup:
    """[표현 찾기] 한 번의 동작.

    저장된 표현이 있으면 그대로 보여주고 AI를 부르지 않는다. 하나도 없으면
    같은 동작 안에서 AI를 한 번만 불러 표현을 만들어 저장한 뒤 보여준다.
    어느 쪽이든 Nadeshiko는 호출하지 않는다.
    """
    screen = lookup_expressions(database, korean_meaning)
    if screen.has_expressions:
        return ExpressionLookup(screen=screen, added=(), used_ai=False)
    screen, added = generate_more_expressions(settings, database, korean_meaning)
    return ExpressionLookup(screen=screen, added=added, used_ai=True)


def generate_more_expressions(
    settings: AppSettings,
    database: SceneCollectorDatabase,
    korean_meaning: str,
) -> tuple[ExpressionScreen, tuple[StoredMeaningExpression, ...]]:
    """AI로 표현을 만들어 자산으로 저장하고, 갱신된 화면과 새 표현을 돌려준다.

    이미 저장된 표현이 있으면 그 목록을 AI에 전달해 중복을 피한다.
    Nadeshiko는 호출하지 않는다.
    """
    added = generate_expressions(settings, korean_meaning, database=database)
    return lookup_expressions(database, korean_meaning), added


def search_relation(
    settings: AppSettings,
    database: SceneCollectorDatabase,
    relation: StoredMeaningExpression,
    *,
    nadeshiko_client: Nadeshiko,
) -> SelectedExpressionScenes:
    """선택한 의미→표현 관계 하나만 검색한다. 결과는 저장하지 않는다."""
    return search_selected_expression(
        settings, relation, nadeshiko_client=nadeshiko_client, database=database
    )


def scene_rows(
    database: SceneCollectorDatabase,
    found: SelectedExpressionScenes,
    media_names: dict[str, str],
) -> tuple[SceneRow, ...]:
    """검색된 Nadeshiko 장면에 이미 저장된 작업 상태를 붙여 목록을 만든다."""
    saved = {
        scene.segment_public_id: scene
        for scene in database.list_work_scenes(found.relation.id)
    }
    return tuple(
        SceneRow(
            segment=segment,
            media_display_name=media_names.get(
                segment.media_public_id, segment.media_public_id
            ),
            work_scene=saved.get(segment.public_id),
        )
        for segment in found.nadeshiko_segments
    )


def ensure_work_scene(
    database: SceneCollectorDatabase,
    relation: StoredMeaningExpression,
    segment: Segment,
    media_display_name: str | None,
) -> int:
    """실제 작업이 발생하는 순간에만 장면 스냅샷을 저장하고 ID를 돌려준다."""
    return database.upsert_work_scene(
        relation.id,
        segment_public_id=segment.public_id,
        media_public_id=segment.media_public_id,
        media_display_name=media_display_name,
        episode=segment.episode,
        start_time_ms=segment.start_time_ms,
        end_time_ms=segment.end_time_ms,
        japanese_text=segment.text_ja.content,
    )


def save_decision(
    database: SceneCollectorDatabase,
    relation: StoredMeaningExpression,
    segment: Segment,
    media_display_name: str | None,
    decision: ReviewDecision,
) -> StoredWorkScene:
    """채택/예비/제외를 저장한다. 이 시점에 작업 장면이 생긴다."""
    work_scene_id = ensure_work_scene(database, relation, segment, media_display_name)
    database.set_work_scene_decision(work_scene_id, decision)
    return _require_work_scene(database, relation, segment)


def save_notes(
    database: SceneCollectorDatabase,
    relation: StoredMeaningExpression,
    segment: Segment,
    media_display_name: str | None,
    notes: str | None,
) -> StoredWorkScene | None:
    """메모를 저장한다. 실제로 남길 내용이 있을 때만 작업 장면이 생긴다.

    아직 작업하지 않은 장면에 빈 메모를 저장하면 아무것도 만들지 않는다.
    이미 있는 장면의 메모를 비우는 것은 허용하며, 그 결과 판정도 번역도 없이
    비어 버린 행은 지운다. 어느 경우든 None을 돌려준다.
    """
    value = notes.strip() if isinstance(notes, str) else ""
    if not value and database.get_work_scene(relation.id, segment.public_id) is None:
        return None

    work_scene_id = ensure_work_scene(database, relation, segment, media_display_name)
    database.set_work_scene_notes(work_scene_id, value or None)
    if not value and database.delete_work_scene_if_empty(work_scene_id):
        return None
    return _require_work_scene(database, relation, segment)


def translate_scene(
    settings: AppSettings,
    database: SceneCollectorDatabase,
    relation: StoredMeaningExpression,
    segment: Segment,
    media_display_name: str | None,
    *,
    nadeshiko_client: Nadeshiko,
) -> TranslatedScene:
    """사용자가 요청한 장면 하나만 문맥 조회 후 번역하고 작업물로 저장한다.

    문맥 조회나 AI 번역이 실패하면 여기서 예외가 나가고 DB는 건드리지 않는다.
    그래서 실패한 장면에는 빈 작업 장면이 남지 않고, 이미 작업하던 장면이라면
    기존 판정·메모·번역도 그대로 있다.
    """
    translated = translate_segment(
        settings,
        relation=relation,
        segment=segment,
        nadeshiko_client=nadeshiko_client,
    )
    work_scene_id = ensure_work_scene(database, relation, segment, media_display_name)
    database.save_work_scene_translation(
        work_scene_id,
        direct_meaning=translated.translation.direct_meaning,
        natural_translation=translated.translation.natural_translation,
        scene_usage=translated.translation.scene_usage,
        ai_service=settings.ai.service,
        ai_model=settings.ai.model,
        instruction_version=TRANSLATION_INSTRUCTION_VERSION,
    )
    return translated


def _require_work_scene(
    database: SceneCollectorDatabase,
    relation: StoredMeaningExpression,
    segment: Segment,
) -> StoredWorkScene:
    stored = database.get_work_scene(relation.id, segment.public_id)
    if stored is None:
        raise RuntimeError("저장한 작업 장면을 다시 읽을 수 없습니다.")
    return stored


def format_timecode(milliseconds: int) -> str:
    """장면의 원본 위치 표시용 HH:MM:SS.mmm."""
    seconds, milli = divmod(max(0, int(milliseconds)), 1000)
    hours, rest = divmod(seconds, 3600)
    minutes, sec = divmod(rest, 60)
    return f"{hours:02d}:{minutes:02d}:{sec:02d}.{milli:03d}"


def scene_line(row: SceneRow) -> str:
    """Nadeshiko 장면 한 줄의 표시용 텍스트."""
    episode = f"{row.segment.episode}화" if row.segment.episode is not None else "화수 없음"
    start = format_timecode(row.segment.start_time_ms)
    text = row.segment.text_ja.content
    return f"{row.media_display_name} · {episode} · {start} · {text}"


def local_scene_line(scene: LocalSegmentMatch) -> str:
    """로컬 자막 참고 결과 한 줄(작품명·화수·타임코드·대사)."""
    title = scene.media_display_name or "(작품명 없음)"
    episode = f"{scene.episode}화" if scene.episode is not None else "극장판/단편"
    start = format_timecode(scene.start_time_ms)
    end = format_timecode(scene.end_time_ms)
    return f"{title} · {episode} · {start} ~ {end} · {scene.japanese_text}"


def work_scene_line(scene: StoredWorkScene) -> str:
    """이미 작업한 장면 한 줄(재실행 후 복원 확인용)."""
    title = scene.media_display_name or scene.media_public_id or "(작품명 없음)"
    episode = f"{scene.episode}화" if scene.episode is not None else "화수 없음"
    start = format_timecode(scene.start_time_ms)
    decision = scene.decision or "판정 없음"
    return f"[{decision}] {title} · {episode} · {start} · {scene.japanese_text}"
