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
    SearchSort,
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

내부 효율값이며 사용자 설정이 아니다. 같은 수의 후보를 보는 데 필요한 요청
수가 가장 적어서 상한을 그대로 쓴다.
"""

COLLECTION_SORT_MODE = "TIME_ASC"
"""수집용 정렬. 화수와 화 안의 위치 기준이라 결정적이다.

공식 검색은 Elasticsearch `search_after`(keyset) 커서로 페이지를 넘긴다.
기본 `RELEVANCE` 정렬은 점수 동점이 많아 커서가 가리키는 자리가 흔들릴 수
있는 반면 화수·위치는 장면마다 갈리므로 순회가 안정적이다. 결과 순서도
사용자가 읽기 쉬운 화수 순이 된다.
"""


class SearchPaginationError(RuntimeError):
    """페이지 순회가 비정상적으로 끝나 전체 장면을 확인하지 못했을 때 발생한다.

    이때 모은 것만 조용히 돌려주면 사용자가 "이 표현은 장면이 이만큼뿐"이라고
    잘못 판단하게 된다. 제작 재료를 빠짐없이 모으는 것이 목적이므로 명확히
    실패로 알린다.
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
class PathCoverage:
    """검색 경로 하나(일반 또는 정확)의 회수 무결성.

    expected_hits는 그 경로와 **같은 조건**으로 물어본 공식 검색 통계가 알려 준
    매칭 수이고, retrieved_hits는 그 경로에서 페이지를 끝까지 넘겨 실제로 받은
    서로 다른 장면 수다.
    """

    expected_hits: int
    retrieved_hits: int

    @property
    def verified(self) -> bool:
        return self.retrieved_hits >= self.expected_hits


@dataclass(frozen=True)
class SourceCoverage:
    """작품 하나에서 이번 검색이 실제로 무엇을 확인했는지 남기는 진단 자료.

    DB에 저장하지 않고 세션 동안만 산다. 사용자 화면에는 공개 ID를 노출하지
    않고 합계와 검증 여부만 쓴다.

    **검색 경로별로 따로 판정한다.** 두 경로를 합친 뒤에 세면, 정확 검색이
    더 준 장면이 일반 검색에서 놓친 자리를 메워 검증이 통과해 버린다. 예를
    들어 일반 검색이 10건 중 9건만 왔는데 정확 검색에만 있는 장면 하나가
    합류하면 합계는 10이 되지만 일반 경로는 여전히 1건을 놓친 상태다.
    """

    media_public_id: str
    normal: PathCoverage
    exact: PathCoverage
    matched_scenes: int

    @property
    def verified(self) -> bool:
        """두 경로가 각각 자기 통계만큼 받았는지. 한쪽이라도 모자라면 실패다."""
        return self.normal.verified and self.exact.verified


@dataclass(frozen=True)
class SelectedExpressionScenes:
    """선택한 의미→표현 관계 하나의 검색 결과. 세션 동안만 사용한다.

    nadeshiko_segments만 실제 장면 작업 대상이다. local_segments는 그 표현이
    사용자 자막 작품에 존재하는지 확인하는 참고 결과다.
    """

    relation: StoredMeaningExpression
    nadeshiko_segments: tuple[Segment, ...]
    local_segments: tuple[LocalSegmentMatch, ...]
    coverage: tuple[SourceCoverage, ...] = ()

    @property
    def has_results(self) -> bool:
        return bool(self.nadeshiko_segments) or bool(self.local_segments)

    @property
    def normal_retrieved_hits(self) -> int:
        return sum(item.normal.retrieved_hits for item in self.coverage)

    @property
    def exact_retrieved_hits(self) -> int:
        return sum(item.exact.retrieved_hits for item in self.coverage)

    @property
    def unverified_sources(self) -> tuple[SourceCoverage, ...]:
        """어느 한 검색 경로라도 통계가 알려 준 만큼 받지 못한 작품."""
        return tuple(item for item in self.coverage if not item.verified)

    @property
    def checked_sources(self) -> int:
        """이번 검색에서 실제로 매칭이 있었던 작품 수."""
        return len(
            [
                item
                for item in self.coverage
                if item.normal.expected_hits
                or item.exact.expected_hits
                or item.normal.retrieved_hits
                or item.exact.retrieved_hits
            ]
        )

    @property
    def search_fully_checked(self) -> bool:
        """검색이 매칭한 결과를 작품마다 빠짐없이 확인했는지.

        이것은 "작품 안의 모든 문자열 출현을 찾았다"는 뜻이 **아니다.**
        공식 검색은 문자열이 아니라 형태소 기준으로 매칭하므로, 검색이
        애초에 잡지 않은 출현은 이 검증으로도 알 수 없다.
        """
        return not self.unverified_sources


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
    coverage: tuple[SourceCoverage, ...] = ()
    if media_ids:
        # 검색 경로마다 같은 조건으로 공식 통계에 먼저 물어 작품별 매칭 수를
        # 받아 둔다. 이 수와 그 경로가 실제로 받은 수를 대조해야 "검색이
        # 준다고 한 것을 다 봤다"고 말할 수 있다. 페이지가 끝났다는 사실만으로는
        # 알 수 없다.
        #
        # 두 검색 경로가 정확히 같은 결과를 준다는 공식 보장이 없으므로 둘 다
        # 끝까지 훑는다. 제작 재료는 많을수록 좋고, 여기서 개수를 자르지 않는다.
        paths = {
            exact_match: _SearchPath(
                expected=_search_hit_counts(
                    relation.japanese,
                    exact_match=exact_match,
                    nadeshiko_client=nadeshiko_client,
                    media_ids=media_ids,
                ),
                segments=_collect_search_segments(
                    relation.japanese,
                    exact_match=exact_match,
                    nadeshiko_client=nadeshiko_client,
                    media_ids=media_ids,
                ),
            )
            for exact_match in (False, True)
        }
        # 경로별 판정을 끝낸 뒤에만 합친다.
        raw = _unique_segments(paths[False].segments, paths[True].segments)
        segments = _surface_segments(raw, relation.japanese)
        coverage = _build_coverage(
            normal=paths[False],
            exact=paths[True],
            matched=segments,
            media_ids=media_ids,
        )

    local_segments: tuple[LocalSegmentMatch, ...] = ()
    if local_media:
        local_segments = _search_local_segments(database, relation.japanese, local_media)

    return SelectedExpressionScenes(
        relation=relation,
        nadeshiko_segments=segments,
        local_segments=local_segments,
        coverage=coverage,
    )


@dataclass(frozen=True)
class _SearchPath:
    """한 검색 경로의 통계와 실제로 받은 장면. 경로별 판정에만 쓴다."""

    expected: dict[str, int]
    segments: tuple[Segment, ...]

    def retrieved_by_media(self) -> dict[str, int]:
        """작품별로 서로 다른 장면 수를 센다.

        같은 장면이 페이지 경계에서 두 번 와도 한 번만 센다. 그래야 중복 수신이
        누락을 가리지 못한다.
        """
        seen: set[str] = set()
        counts: dict[str, int] = {}
        for segment in self.segments:
            if segment.public_id in seen:
                continue
            seen.add(segment.public_id)
            counts[segment.media_public_id] = counts.get(segment.media_public_id, 0) + 1
        return counts


def _search_hit_counts(
    search_text: str,
    *,
    exact_match: bool,
    nadeshiko_client: Nadeshiko,
    media_ids: tuple[str, ...],
) -> dict[str, int]:
    """공식 검색 통계로 작품별 매칭 수를 미리 받는다(경로당 요청 1회).

    결과 장면을 받지 않고 개수만 주는 공식 경로라 값이 싸다. 통계는 검색과
    같은 `exact_match` 조건을 반영하므로 경로마다 따로 물어야 그 경로의
    회수를 검증할 수 있다. 통계에 없는 작품은 매칭이 0건이라는 뜻이다.
    """
    stats = nadeshiko_client.get_search_stats(
        query=SearchQuery(search=search_text, exact_match=exact_match),
        filters=_media_filters(media_ids),
    )
    return {item.media_public_id: int(item.match_count) for item in stats.media}


def _build_coverage(
    *,
    normal: _SearchPath,
    exact: _SearchPath,
    matched: tuple[Segment, ...],
    media_ids: tuple[str, ...],
) -> tuple[SourceCoverage, ...]:
    """작품별로 두 경로의 예상·수신 수와 최종 장면 수를 따로 모은다."""
    normal_retrieved = normal.retrieved_by_media()
    exact_retrieved = exact.retrieved_by_media()
    scenes: dict[str, int] = {}
    for segment in matched:
        scenes[segment.media_public_id] = scenes.get(segment.media_public_id, 0) + 1

    # 검색한 작품과 어느 경로에든 등장한 작품을 모두 확인 대상으로 둔다.
    keys = sorted(
        set(media_ids)
        | set(normal.expected)
        | set(exact.expected)
        | set(normal_retrieved)
        | set(exact_retrieved)
    )
    return tuple(
        SourceCoverage(
            media_public_id=key,
            normal=PathCoverage(
                expected_hits=normal.expected.get(key, 0),
                retrieved_hits=normal_retrieved.get(key, 0),
            ),
            exact=PathCoverage(
                expected_hits=exact.expected.get(key, 0),
                retrieved_hits=exact_retrieved.get(key, 0),
            ),
            matched_scenes=scenes.get(key, 0),
        )
        for key in keys
    )


def _collect_search_segments(
    search_text: str,
    *,
    exact_match: bool,
    nadeshiko_client: Nadeshiko,
    media_ids: tuple[str, ...],
) -> tuple[Segment, ...]:
    """검색이 돌려주는 장면을 페이지가 끝날 때까지 거르지 않고 모두 모은다.

    이 도구의 목적은 고른 표현 하나를 여러 장면에서 반복해 보여줄 제작 재료를
    모으는 것이다. 그래서 "몇 개 찾았으니 그만"이나 "몇 페이지 봤으니 그만"으로
    정상 결과를 자르지 않고, Nadeshiko가 더 줄 것이 없을 때까지 훑는다.

    표면형 판정은 여기서 하지 않는다. 검색이 준 원본 수를 그대로 세어 공식
    검색 통계와 대조해야 빠뜨린 페이지가 있는지 알 수 있기 때문이다.

    작품 필터와 정렬은 모든 페이지에 똑같이 붙는다. 공식 커서는 요청의 정렬
    구성과 짝이 맞아야 하므로 순회 도중 정렬을 바꾸지 않는다. 순회가 비정상으로
    끝나면 SearchPaginationError를 내고, 모은 것만 조용히 완료로 돌려주지 않는다.
    """
    collected: list[Segment] = []
    seen_cursors: set[str] = set()
    cursor: str | None = None
    while True:
        response = _search_nadeshiko(
            search_text,
            exact_match=exact_match,
            take=SEARCH_PAGE_TAKE,
            nadeshiko_client=nadeshiko_client,
            media_ids=media_ids,
            cursor=cursor,
        )
        collected.extend(response.segments)

        pagination = response.pagination
        if not pagination.has_more:
            return tuple(collected)

        next_cursor = pagination.cursor
        if not next_cursor:
            raise SearchPaginationError(
                "검색 페이지 순회가 비정상적으로 종료되어 전체 장면을 확인하지 못했습니다."
            )
        if next_cursor in seen_cursors:
            # 같은 페이지를 계속 주는 응답이다. 무한히 돌지 않고 실패로 알린다.
            raise SearchPaginationError(
                "검색 페이지가 같은 자리에서 반복되어 전체 장면을 확인하지 못했습니다."
            )
        seen_cursors.add(next_cursor)
        cursor = next_cursor


def _unique_segments(*groups: tuple[Segment, ...]) -> tuple[Segment, ...]:
    """장면 ID 기준으로 한 번씩만 남긴다. 처음 나온 순서를 유지한다.

    페이지 경계, 일반 검색과 정확 검색 사이, Nadeshiko 색인 특성 때문에 같은
    장면이 여러 번 올 수 있다.
    """
    unique: list[Segment] = []
    seen: set[str] = set()
    for group in groups:
        for segment in group:
            if segment.public_id in seen:
                continue
            seen.add(segment.public_id)
            unique.append(segment)
    return tuple(unique)


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


def _media_filters(media_ids: tuple[str, ...]) -> SearchFilters:
    return SearchFilters(
        media=SearchFiltersMedia(
            include=[MediaFilterItem(media_public_id=media_id) for media_id in media_ids]
        )
    )


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
    filters = _media_filters(media_ids)
    sort = SearchSort(mode=COLLECTION_SORT_MODE)
    if cursor is None:
        # 공식 API에서 cursor를 생략하는 것이 곧 첫 페이지다.
        return nadeshiko_client.search(query=query, take=take, filters=filters, sort=sort)
    return nadeshiko_client.search(
        query=query, take=take, cursor=cursor, filters=filters, sort=sort
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


def _surface_segments(
    segments: tuple[Segment, ...], primary_surface: str
) -> tuple[Segment, ...]:
    """검색이 준 장면 중 목표 표현이 같은 표면형으로 있는 것만 남긴다."""
    return tuple(
        segment
        for segment in segments
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
