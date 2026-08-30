"""한국어 의미의 표현 자산을 만들고, 선택한 표현 하나만 실제 대사에서 찾는다.

- 저장된 표현이 있으면 AI를 호출하지 않는다(호출자가 먼저 조회한다).
- AI가 만든 표현은 캐시가 아니라 표현 자산으로 DB에 저장한다.
- Nadeshiko/로컬 자막 검색은 사용자가 고른 의미→표현 관계 하나에 대해서만
  실행하며, 검색 결과는 현재 세션에서만 사용하고 저장·캐시하지 않는다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from nadeshiko import Nadeshiko
from nadeshiko.models import (
    MediaFilterItem,
    SearchFilters,
    SearchFiltersMedia,
    SearchQuery,
    SearchResponse,
    Segment,
)

from scene_collector.ai import create_structured_response
from scene_collector.config import AppSettings
from scene_collector.database import normalize_korean_meaning
from scene_collector.models import ExpressionCandidate, GeneratedExpressions
from scene_collector.surface import _normalize_surface, matches_surface

if TYPE_CHECKING:
    from scene_collector.database import (
        LocalSegmentMatch,
        SceneCollectorDatabase,
        StoredMeaningExpression,
        StoredMedia,
    )

_EXPRESSION_RULES = """당신은 한국어 의미에 맞는 실제 일본어 회화 표현을 모으는 도우미입니다.

규칙:
- 실제 일본어 회화에서 자연스럽게 쓰는 서로 다른 표현만 제시하세요.
- 가능한 한 폭넓게 제시하되 최대 {limit}개까지만 제시하세요.
- 자연스러운 표현이 그보다 적으면 억지로 개수를 채우지 마세요.
- 이미 저장된 표현 외에 자연스럽게 덧붙일 표현이 없으면 빈 목록을 그대로 반환하세요.
- 같은 표현의 사소한 표기 차이를 여러 항목으로 나누지 마세요.
- 각 표현에 japanese(실제 표기), reading(가나 읽기), meaning_ko(이 한국어 의미에서의 뜻), register(말투·격식)를 채우세요.
- 사전에만 있고 실제 대화에서 쓰지 않는 표현은 넣지 마세요."""


class NoActiveMediaError(RuntimeError):
    """검색에 사용할 활성 선호 작품이 없을 때 발생한다."""


@dataclass(frozen=True)
class SelectedExpressionScenes:
    """선택한 의미→표현 관계 하나의 검색 결과. 세션 동안만 사용한다.

    nadeshiko_segments만 실제 장면 작업 대상이다. local_segments는 그 표현이
    사용자 자막 작품에 존재하는지 확인하는 참고 결과다.
    """

    relation: StoredMeaningExpression
    nadeshiko_segments: tuple[Segment, ...]
    local_segments: tuple[LocalSegmentMatch, ...]

    @property
    def has_results(self) -> bool:
        return bool(self.nadeshiko_segments) or bool(self.local_segments)


def find_saved_expressions(
    database: SceneCollectorDatabase, korean_meaning: str
) -> tuple[StoredMeaningExpression, ...]:
    """저장된 한국어 의미의 표현 전부를 읽는다. AI를 호출하지 않는다."""
    intent = (korean_meaning or "").strip()
    if not intent:
        raise ValueError("한국어로 찾을 의미를 입력해야 합니다.")
    return database.find_expressions_for_meaning(intent)


def generate_expressions(
    settings: AppSettings,
    korean_meaning: str,
    *,
    database: SceneCollectorDatabase,
) -> tuple[StoredMeaningExpression, ...]:
    """AI로 일본어 표현을 만들어 표현 자산으로 저장하고 새로 추가된 것만 반환한다.

    이미 저장된 표현이 있으면 그 목록을 AI에 함께 전달해 중복되지 않는
    표현만 만들게 하고, 반환된 것 중 기존 표현과 겹치는 항목은 저장하지 않는다.

    실제로 저장할 새 표현이 생겼을 때만 DB에 쓴다. 처음 보는 의미인데 AI가
    실패하거나 새 표현을 하나도 주지 않으면 아무것도 남기지 않고, 이미 저장된
    의미라면 기존 자료를 그대로 둔다. 시도 자체는 기록하지 않는다.
    """
    intent = (korean_meaning or "").strip()
    if not intent:
        raise ValueError("한국어로 찾을 의미를 입력해야 합니다.")
    if not normalize_korean_meaning(intent):
        raise ValueError("한국어 의미를 입력해야 합니다.")

    meaning = database.find_meaning(intent)
    known = (
        {relation.japanese for relation in database.list_meaning_expressions(meaning.id)}
        if meaning is not None
        else set()
    )
    display = meaning.display_korean_meaning if meaning is not None else intent

    limit = settings.search.expression_generation_limit
    generated = create_structured_response(
        settings,
        prompt=_expression_prompt(display, limit, known),
        response_model=GeneratedExpressions,
    )

    fresh: list[tuple[str, ExpressionCandidate]] = []
    for candidate in generated.expressions:
        if len(fresh) >= limit:
            break
        japanese = candidate.japanese.strip()
        if not japanese or japanese in known:
            continue
        known.add(japanese)
        fresh.append((japanese, candidate))
    if not fresh:
        return ()

    stored = meaning if meaning is not None else database.upsert_meaning(intent)
    return tuple(
        database.add_meaning_expression(
            stored.id,
            japanese=japanese,
            reading=candidate.reading,
            meaning_ko=candidate.meaning_ko,
            register_text=candidate.register,
        )
        for japanese, candidate in fresh
    )


def _expression_prompt(korean_meaning: str, limit: int, known: set[str]) -> str:
    lines = [_EXPRESSION_RULES.format(limit=limit), "", f"한국어 의미: {korean_meaning}"]
    if known:
        lines.extend(
            [
                "",
                "이미 저장된 표현입니다. 이것들과 중복되지 않는 표현만 새로 제시하세요:",
                ", ".join(sorted(known)),
            ]
        )
    return "\n".join(lines)


def search_selected_expression(
    settings: AppSettings,
    relation: StoredMeaningExpression,
    *,
    nadeshiko_client: Nadeshiko,
    database: SceneCollectorDatabase,
) -> SelectedExpressionScenes:
    """사용자가 선택한 관계의 일본어 표현 하나만 실제 대사에서 찾는다.

    결과는 저장하거나 캐시하지 않는다. 같은 표현을 다시 찾으면 다시 호출한다.
    """
    media_ids, local_media = _split_active_media(database)

    segments: tuple[Segment, ...] = ()
    if media_ids:
        response = _search_nadeshiko(
            relation.japanese,
            exact_match=False,
            take=settings.search.nadeshiko_take,
            nadeshiko_client=nadeshiko_client,
            media_ids=media_ids,
        )
        segments = _surface_segments(response, relation.japanese)
        if not segments:
            exact_response = _search_nadeshiko(
                relation.japanese,
                exact_match=True,
                take=settings.search.nadeshiko_take,
                nadeshiko_client=nadeshiko_client,
                media_ids=media_ids,
            )
            segments = _surface_segments(exact_response, relation.japanese)

    local_segments: tuple[LocalSegmentMatch, ...] = ()
    if local_media:
        local_segments = _search_local_segments(database, relation.japanese, local_media)

    return SelectedExpressionScenes(
        relation=relation,
        nadeshiko_segments=segments,
        local_segments=local_segments,
    )


def _split_active_media(
    database: SceneCollectorDatabase,
) -> tuple[tuple[str, ...], tuple[StoredMedia, ...]]:
    """활성 선호작을 Nadeshiko 필터용 ID와 로컬 자막 작품으로 나눈다.

    database가 없는 개발용 호출은 지원하지 않는다. 활성 작품이 하나도 없으면
    전체 대사 자료로 자동 확대하지 않고 명확한 오류를 낸다.
    """
    active_media = database.list_active_media()
    if not active_media:
        raise NoActiveMediaError("검색에 사용할 활성 선호 작품이 없습니다.")

    nadeshiko_ids = tuple(
        sorted(
            media.nadeshiko_media_id
            for media in active_media
            if media.source == "nadeshiko" and media.nadeshiko_media_id is not None
        )
    )
    local_media = tuple(media for media in active_media if media.source == "local")
    return nadeshiko_ids, local_media


def _search_nadeshiko(
    search_text: str,
    *,
    exact_match: bool,
    take: int,
    nadeshiko_client: Nadeshiko,
    media_ids: tuple[str, ...],
) -> SearchResponse:
    query = SearchQuery(search=search_text, exact_match=exact_match)
    media_filter = SearchFiltersMedia(
        include=[MediaFilterItem(media_public_id=media_id) for media_id in media_ids]
    )
    return nadeshiko_client.search(
        query=query,
        take=take,
        filters=SearchFilters(media=media_filter),
    )


def _search_local_segments(
    database: SceneCollectorDatabase,
    surface: str,
    local_media: tuple[StoredMedia, ...],
) -> tuple[LocalSegmentMatch, ...]:
    """로컬 자막 색인에서 LIKE로 후보를 줄인 뒤 기존 표면형 검사로 판정한다."""
    normalized = _normalize_surface(surface)
    if not normalized:
        return ()

    matches = database.find_local_segments(
        normalized_surface=normalized,
        media_row_ids=[media.id for media in local_media],
    )
    return tuple(
        match for match in matches if matches_surface(match.japanese_text, surface)
    )


def _surface_segments(response: SearchResponse, primary_surface: str) -> tuple[Segment, ...]:
    return tuple(
        segment
        for segment in response.segments
        if matches_surface(
            segment.text_ja.content,
            primary_surface,
            token_spans=_token_spans(segment),
        )
    )


def _token_spans(segment: Segment) -> tuple[tuple[int, int], ...] | None:
    tokens = segment.text_ja.tokens
    if not isinstance(tokens, list):
        return None

    spans = tuple(
        (begin, end)
        for token in tokens
        if isinstance((begin := getattr(token, "b", None)), int)
        and isinstance((end := getattr(token, "e", None)), int)
    )
    return spans or None
