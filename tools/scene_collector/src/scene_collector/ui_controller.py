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
    normalize_work_scene_notes,
)
from scene_collector.reading import korean_reading
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
    request_id: int = 0

    def clear(self) -> None:
        """이전 의미·표현의 장면 결과를 하나도 남기지 않는다.

        진행 중이던 조회에는 지금까지의 표를 무효로 만들어, 늦게 도착한 결과가
        새 화면 위에 덮이지 않게 한다.
        """
        self.relation = None
        self.found = None
        self.rows = ()
        self.saved_scenes = ()
        self.selected_index = None
        self.request_id += 1

    def start_relation(self, relation: StoredMeaningExpression) -> int:
        """새 의미→표현 관계로 넘어가고 이번 조회를 가리키는 표를 돌려준다."""
        self.clear()
        self.relation = relation
        return self.request_id

    def is_current(self, request_id: int) -> bool:
        """그 표가 아직 지금 화면의 것인지. 아니면 결과를 버려야 한다."""
        return request_id == self.request_id

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


@dataclass
class ActionGuard:
    """같은 동작이 이미 실행 중이면 두 번째 요청을 버린다.

    버튼은 눌린 동안 비활성으로 막을 수 있지만 입력창의 Enter는 그렇게 막을 수
    없다. 한국어 IME가 조합을 확정하는 Enter를 한 번 더 보내는 경우까지 포함해
    같은 조회가 두 번 실행되지 않게 한다.
    """

    running: bool = False

    def try_begin(self) -> bool:
        """시작해도 되면 True. 이미 실행 중이면 False를 주고 아무것도 하지 않는다."""
        if self.running:
            return False
        self.running = True
        return True

    def finish(self) -> None:
        self.running = False


def expression_line(relation: StoredMeaningExpression) -> str:
    """표현 카드와 작업 맥락에 함께 쓰는 표기.

    한국어 학습자가 읽을 수 있게 일본어와 한글 독음만 보여준다. 히라가나 읽기는
    화면에 그대로 내지 않는다. 예: 大丈夫です : 다이죠부데스
    """
    korean = korean_reading(relation.reading)
    return f"{relation.japanese} : {korean}" if korean else relation.japanese


def parse_setting_number(value: object, *, label: str) -> int:
    """설정 화면의 숫자 입력을 정수로 바꾼다.

    ui.number는 실수를 주고 범위 제한도 포커스를 잃을 때만 적용하므로, 저장 전에
    여기서 정수인지 확인한다. 범위 검사는 설정 자료형이 맡는다.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label}에 숫자를 입력하세요.")
    number = int(value)
    if number != value:
        raise ValueError(f"{label}은 정수여야 합니다.")
    return number


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
    *,
    connection: object | None = None,
) -> int:
    """실제 작업이 발생하는 순간에만 장면 스냅샷을 저장하고 ID를 돌려준다.

    connection을 주면 그 transaction 안에서 저장한다. 판정·번역·메모와 같은
    transaction으로 묶어야 중간에 실패했을 때 빈 장면이 남지 않는다.
    """
    return database.upsert_work_scene(
        relation.id,
        segment_public_id=segment.public_id,
        media_public_id=segment.media_public_id,
        media_display_name=media_display_name,
        episode=segment.episode,
        start_time_ms=segment.start_time_ms,
        end_time_ms=segment.end_time_ms,
        japanese_text=segment.text_ja.content,
        connection=connection,
    )


def save_decision(
    database: SceneCollectorDatabase,
    relation: StoredMeaningExpression,
    segment: Segment,
    media_display_name: str | None,
    decision: ReviewDecision,
) -> StoredWorkScene:
    """채택/예비/제외를 저장한다. 이 시점에 작업 장면이 생긴다.

    판정값을 먼저 확인하고 만들며, 판정 저장이 실패하면 방금 만든 빈 장면을
    되돌린다. 그래서 실패한 저장이 빈 작업 장면으로 남지 않는다.
    """
    if decision not in REVIEW_DECISIONS:
        raise ValueError("검수 판정은 채택, 예비, 제외 중 하나여야 합니다.")
    with database.transaction() as connection:
        work_scene_id = ensure_work_scene(
            database, relation, segment, media_display_name, connection=connection
        )
        database.set_work_scene_decision(work_scene_id, decision, connection=connection)
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
    비어 버린 행은 지운다.

    저장 뒤에도 작업 장면이 남아 있으면 그 장면을, 만들지 않았거나 비어서
    지웠으면 None을 돌려준다.
    """
    value = normalize_work_scene_notes(notes)
    if value is None and database.get_work_scene(relation.id, segment.public_id) is None:
        return None

    with database.transaction() as connection:
        work_scene_id = ensure_work_scene(
            database, relation, segment, media_display_name, connection=connection
        )
        database.set_work_scene_notes(work_scene_id, value, connection=connection)
        emptied = value is None and database.delete_work_scene_if_empty(
            work_scene_id, connection=connection
        )
    return None if emptied else _require_work_scene(database, relation, segment)


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
    with database.transaction() as connection:
        work_scene_id = ensure_work_scene(
            database, relation, segment, media_display_name, connection=connection
        )
        database.save_work_scene_translation(
            work_scene_id,
            direct_meaning=translated.translation.direct_meaning,
            natural_translation=translated.translation.natural_translation,
            scene_usage=translated.translation.scene_usage,
            ai_service=settings.ai.service,
            ai_model=settings.ai.model,
            instruction_version=TRANSLATION_INSTRUCTION_VERSION,
            connection=connection,
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


def scene_count_summary(nadeshiko_count: int, local_count: int) -> str:
    """검색 결과 머리줄. 제작 가능 장면과 위치 후보를 절대 합산 표기하지 않는다.

    "Nadeshiko 검색에서 확인된"이라고 적는다. 이 수는 검색이 매칭해 준 것 중
    정확 동일표현인 장면 수이지, 작품 안의 모든 출현 수가 아니다.
    """
    total = nadeshiko_count + local_count
    return (
        f"Nadeshiko 검색에서 확인된 제작 가능 장면(영상 검수 대상) {nadeshiko_count}개 · "
        f"로컬 자막 위치 후보(위치 확인만 가능) {local_count}개 · "
        f"검색 확인 합계 {total}개"
    )


def search_coverage_line(found: SelectedExpressionScenes) -> str:
    """검색이 매칭한 결과를 실제로 다 확인했는지 사용자에게 알린다.

    공식 검색 통계가 알려 준 작품별 매칭 수와 실제로 받은 수를 대조한 결과다.
    작품 공개 ID는 사용자에게 의미가 없으므로 노출하지 않는다.
    """
    coverage = found.coverage
    if not coverage:
        return ""
    checked = len([item for item in coverage if item.expected_hits or item.retrieved_hits])
    if not found.search_fully_checked:
        missing = len(found.unverified_sources)
        return (
            f"⚠ 검색이 매칭했다고 알려 준 결과 중 일부를 받지 못했습니다"
            f"(작품 {missing}개). 아래 목록은 완전하지 않을 수 있습니다."
        )
    return (
        f"검색이 매칭한 {found.retrieved_hits}건을 작품 {checked}개에서 빠짐없이 확인한 결과입니다. "
        "다만 검색은 문자열이 아니라 형태소 기준으로 찾으므로, 작품 안의 모든 출현을 "
        "찾았다고 보장하지는 않습니다."
    )


def local_counts_by_title(
    local_segments: tuple[LocalSegmentMatch, ...],
) -> tuple[tuple[str, int], ...]:
    """로컬 위치 후보를 source unit(작품 표시명)별로 센다. 처음 나온 순서 유지."""
    counts: dict[str, int] = {}
    for scene in local_segments:
        title = scene.media_display_name or "(작품명 없음)"
        counts[title] = counts.get(title, 0) + 1
    return tuple(counts.items())


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
