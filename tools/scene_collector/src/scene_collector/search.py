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

SEARCH_PAGE_TAKE = 50
"""한 번의 검색 요청으로 받아올 후보 수. Nadeshiko 공식 take 상한이다.

사용자에게 보여줄 장면 수와 다른 값이다. 같은 수의 후보를 보는 데 필요한
요청 수가 가장 적어서 상한을 그대로 쓴다.
"""

SEARCH_MAX_PAGES = 4
"""일반 검색에서 훑을 최대 페이지 수. 4 x 50 = 후보 200개.

과거 회수 검증에서 문제 표현 세 개는 상위 200장면까지 정확 일치가 0이었고
`大丈夫ですか`는 첫 20건에서 17건을 회수했다. 200을 넘겨 더 훑을 실익이 없다.
"""

EXACT_MATCH_MAX_PAGES = 2
"""정확 검색 대체 경로의 최대 페이지 수.

이 경로는 일반 검색으로 후보 200개를 다 본 뒤에도 0건일 때만 돌므로 더 짧게 잡는다.
표현 하나를 찾는 데 드는 검색 호출은 최대 SEARCH_MAX_PAGES + EXACT_MATCH_MAX_PAGES회다.
"""

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
        target = settings.search.scene_result_limit
        segments = _collect_surface_segments(
            relation.japanese,
            exact_match=False,
            target=target,
            max_pages=SEARCH_MAX_PAGES,
            nadeshiko_client=nadeshiko_client,
            media_ids=media_ids,
        )
        if not segments:
            # 훑을 수 있는 후보를 전부 본 뒤에도 0건일 때만 정확 검색으로 넘어간다.
            # 부족할 때마다 정확 검색을 돌리면 과거에 확인된 정상 표현 회수 저하가
            # 되살아난다.
            segments = _collect_surface_segments(
                relation.japanese,
                exact_match=True,
                target=target,
                max_pages=EXACT_MATCH_MAX_PAGES,
                nadeshiko_client=nadeshiko_client,
                media_ids=media_ids,
            )

    local_segments: tuple[LocalSegmentMatch, ...] = ()
    if local_media:
        local_segments = _search_local_segments(database, relation.japanese, local_media)

    return SelectedExpressionScenes(
        relation=relation,
        nadeshiko_segments=segments,
        local_segments=local_segments,
    )


def _collect_surface_segments(
    search_text: str,
    *,
    exact_match: bool,
    target: int,
    max_pages: int,
    nadeshiko_client: Nadeshiko,
    media_ids: tuple[str, ...],
) -> tuple[Segment, ...]:
    """정확히 같은 표현이 담긴 장면을 target개 모을 때까지 페이지를 넘긴다.

    API가 주는 후보 수와 사용자에게 보여줄 장면 수는 다르다. 흔한 표현일수록
    첫 페이지가 비슷하지만 다른 표현으로 채워져 표면형 판정에서 전부 떨어질 수
    있으므로, 목표 수를 채울 때까지 다음 페이지를 이어서 훑는다.

    목표를 채우면 즉시 멈춰 다음 페이지를 요청하지 않고, 페이지가 계속 있어도
    max_pages를 넘지 않는다. 작품 필터는 모든 페이지에 그대로 붙는다.

    순회 도중 호출이 실패하면 예외를 그대로 올린다. 모은 것만 돌려주면 0건이
    실제로 없는 것인지 못 본 것인지 구분할 수 없게 된다.
    """
    collected: list[Segment] = []
    seen: set[str] = set()
    cursor: str | None = None
    for _ in range(max_pages):
        response = _search_nadeshiko(
            search_text,
            exact_match=exact_match,
            take=SEARCH_PAGE_TAKE,
            nadeshiko_client=nadeshiko_client,
            media_ids=media_ids,
            cursor=cursor,
        )
        for segment in _surface_segments(response, search_text):
            if segment.public_id in seen:
                # 색인이 갱신되는 중이면 같은 장면이 두 페이지에 걸쳐 올 수 있다.
                continue
            seen.add(segment.public_id)
            collected.append(segment)
            if len(collected) >= target:
                return tuple(collected)
        cursor = _next_cursor(response)
        if cursor is None:
            break
    return tuple(collected)


def _next_cursor(response: SearchResponse) -> str | None:
    """다음 페이지가 실제로 있을 때만 cursor를 준다."""
    pagination = response.pagination
    if not pagination.has_more or not pagination.cursor:
        return None
    return pagination.cursor


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
    cursor: str | None = None,
) -> SearchResponse:
    query = SearchQuery(search=search_text, exact_match=exact_match)
    media_filter = SearchFiltersMedia(
        include=[MediaFilterItem(media_public_id=media_id) for media_id in media_ids]
    )
    filters = SearchFilters(media=media_filter)
    if cursor is None:
        # 공식 API에서 cursor를 생략하는 것이 곧 첫 페이지다.
        return nadeshiko_client.search(query=query, take=take, filters=filters)
    return nadeshiko_client.search(query=query, take=take, cursor=cursor, filters=filters)


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
