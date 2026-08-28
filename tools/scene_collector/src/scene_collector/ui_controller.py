"""작업 10 화면이 기존 검증 기능을 호출할 때 쓰는 얇은 adapter.

NiceGUI에 의존하지 않아 offline pytest로 검증한다. 새 검색·번역·저장
알고리즘을 만들지 않고 기존 search/translate/database 함수만 연결한다.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from nadeshiko import Nadeshiko

from scene_collector.config import AppSettings
from scene_collector.database import (
    LocalSegmentMatch,
    ReviewDecision,
    SceneCollectorDatabase,
    StoredExpression,
    StoredReview,
    database_path,
)
from scene_collector.search import search_expressions
from scene_collector.translate import TranslatedScene, translate_expression_scenes

REVIEW_DECISIONS: tuple[ReviewDecision, ...] = ("채택", "예비", "제외")


@dataclass(frozen=True)
class SettingsSummary:
    """설정 화면에 보여줄 값. 비밀키 값 자체는 절대 담지 않는다."""

    work_data_dir: Path
    database_file: Path
    ai_service: str
    ai_model: str
    candidate_count: int
    nadeshiko_take: int
    nadeshiko_key_set: bool


@dataclass(frozen=True)
class CandidateScreenItem:
    """후보 선택·장면 검수 화면에서 쓰는 corpus-backed 후보 하나."""

    expression: StoredExpression
    local_scenes: tuple[LocalSegmentMatch, ...]


@dataclass(frozen=True)
class SearchScreenResult:
    """한 번의 한국어 검색을 화면에서 다루는 형태."""

    run_id: int
    korean_intent: str
    items: tuple[CandidateScreenItem, ...]


def settings_summary(settings: AppSettings) -> SettingsSummary:
    """현재 설정을 화면 표시용으로 요약한다. 키는 존재 여부만 담는다."""
    secret = settings.nadeshiko_api_key
    key_set = secret is not None and bool(secret.get_secret_value().strip())
    return SettingsSummary(
        work_data_dir=settings.storage.work_data_dir,
        database_file=database_path(settings),
        ai_service=settings.ai.service,
        ai_model=settings.ai.model,
        candidate_count=settings.search.candidate_count,
        nadeshiko_take=settings.search.nadeshiko_take,
        nadeshiko_key_set=key_set,
    )


def run_expression_search(
    settings: AppSettings,
    korean_intent: str,
    *,
    nadeshiko_client: Nadeshiko,
    database: SceneCollectorDatabase,
) -> SearchScreenResult:
    """기존 search_expressions를 실행하고 저장된 run을 화면 형태로 돌려준다."""
    result = search_expressions(
        settings,
        korean_intent,
        nadeshiko_client=nadeshiko_client,
        database=database,
    )
    run_id = database.latest_search_run_id()
    if run_id is None:
        raise RuntimeError("검색 결과가 저장되지 않았습니다.")
    run = database.load_search_run(run_id)
    if run is None:
        raise RuntimeError("저장된 검색을 다시 읽을 수 없습니다.")

    stored_by_japanese = {
        expression.candidate.japanese: expression for expression in run.expressions
    }
    items: list[CandidateScreenItem] = []
    for candidate_search in result.corpus_backed_candidates:
        stored = stored_by_japanese.get(candidate_search.candidate.japanese)
        if stored is None:
            continue
        items.append(
            CandidateScreenItem(
                expression=stored,
                local_scenes=candidate_search.local_segments,
            )
        )
    return SearchScreenResult(
        run_id=run.id,
        korean_intent=run.korean_intent,
        items=tuple(items),
    )


def restore_latest_search(database: SceneCollectorDatabase) -> SearchScreenResult | None:
    """재실행 시 장면이 남아 있는 가장 최근 검색과 검수 상태를 복원한다.

    후보가 하나도 없던 검색은 검수를 이어갈 수 없으므로 건너뛴다.
    로컬 자막 장면은 DB에 저장하지 않는 세션 결과라 복원 대상이 아니다.
    """
    for run_id in database.list_search_run_ids():
        run = database.load_search_run(run_id)
        if run is None:
            continue
        items = tuple(
            CandidateScreenItem(expression=expression, local_scenes=())
            for expression in run.expressions
            if expression.segments
        )
        if items:
            return SearchScreenResult(
                run_id=run.id, korean_intent=run.korean_intent, items=items
            )
    return None


def select_expression(
    database: SceneCollectorDatabase,
    result: SearchScreenResult,
    expression_id: int,
) -> None:
    """검색 안에서 선택한 표현 하나만 is_selected로 저장한다."""
    known_ids = {item.expression.id for item in result.items}
    if expression_id not in known_ids:
        raise ValueError("현재 검색 결과에 없는 표현입니다.")
    for item in result.items:
        database.set_expression_selected(
            item.expression.id, item.expression.id == expression_id
        )


def save_decision(
    database: SceneCollectorDatabase,
    expression_id: int,
    segment_id: int,
    decision: ReviewDecision,
) -> StoredReview:
    """기존 set_review_decision으로 판정을 저장하고 저장된 상태를 돌려준다."""
    database.set_review_decision(expression_id, segment_id, decision)
    review = database.get_review(expression_id, segment_id)
    if review is None:
        raise RuntimeError("저장한 검수 상태를 다시 읽을 수 없습니다.")
    return review


def refresh_expression(
    database: SceneCollectorDatabase,
    expression_id: int,
) -> StoredExpression:
    """번역·판정 저장 후 표현 하나를 최신 상태로 다시 읽는다."""
    expression = database.load_expression(expression_id)
    if expression is None:
        raise ValueError("표현을 찾을 수 없습니다.")
    return expression


def load_scene_translations(
    settings: AppSettings,
    expression_id: int,
    *,
    nadeshiko_client: Nadeshiko,
    database: SceneCollectorDatabase,
) -> tuple[TranslatedScene, ...]:
    """기존 translate 흐름(문맥 조회 + 캐시 재사용 번역)을 그대로 실행한다."""
    return translate_expression_scenes(
        settings,
        expression_id,
        nadeshiko_client=nadeshiko_client,
        database=database,
    )


def format_timecode(milliseconds: int) -> str:
    """로컬 자막 장면의 원본 위치 표시용 HH:MM:SS.mmm."""
    seconds, milli = divmod(max(0, int(milliseconds)), 1000)
    hours, rest = divmod(seconds, 3600)
    minutes, sec = divmod(rest, 60)
    return f"{hours:02d}:{minutes:02d}:{sec:02d}.{milli:03d}"


def local_scene_line(scene: LocalSegmentMatch) -> str:
    """로컬 자막 장면 한 건의 표시용 텍스트(작품명·화수·타임코드·대사)."""
    title = scene.media_display_name or "(작품명 없음)"
    episode = f"{scene.episode}화" if scene.episode is not None else "극장판/단편"
    start = format_timecode(scene.start_time_ms)
    end = format_timecode(scene.end_time_ms)
    return f"{title} · {episode} · {start} ~ {end} · {scene.japanese_text}"
