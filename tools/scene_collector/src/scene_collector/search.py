"""한국어 의도를 AI 후보와 Nadeshiko corpus 검색으로 연결한다."""

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
from scene_collector.models import ExpressionCandidate, ExpressionCandidates
from scene_collector.surface import _normalize_surface, matches_surface

if TYPE_CHECKING:
    from scene_collector.database import (
        LocalSegmentMatch,
        SceneCollectorDatabase,
        StoredMedia,
    )

CANDIDATE_INSTRUCTION_VERSION = "expression-candidates-v1"


class NoActiveMediaError(RuntimeError):
    """database가 연결된 검색에 활성 선호 작품이 하나도 없을 때 발생한다."""


@dataclass(frozen=True)
class CandidateSearchResult:
    """일본어 후보와 Nadeshiko 응답, 로컬 동일표현 segment.

    response가 None이면 활성 Nadeshiko 작품이 없어 Nadeshiko 검색 자체를
    건너뛴 경우다. local_segments는 사용자가 등록한 로컬 자막 색인에서
    같은 surface 검사를 통과한 장면이다.
    """

    candidate: ExpressionCandidate
    response: SearchResponse | None
    exact_match_response: SearchResponse | None
    exact_segments: tuple[Segment, ...]
    local_segments: tuple[LocalSegmentMatch, ...] = ()

    @property
    def has_results(self) -> bool:
        return bool(self.exact_segments) or bool(self.local_segments)


@dataclass(frozen=True)
class ExpressionSearchResult:
    """한 한국어 의도에 대한 AI 생성과 corpus 확인 결과."""

    korean_intent: str
    generated_candidates: tuple[ExpressionCandidate, ...]
    candidate_searches: tuple[CandidateSearchResult, ...]

    @property
    def corpus_backed_candidates(self) -> tuple[CandidateSearchResult, ...]:
        return tuple(result for result in self.candidate_searches if result.has_results)


def search_expressions(
    settings: AppSettings,
    korean_intent: str,
    *,
    nadeshiko_client: Nadeshiko,
    database: SceneCollectorDatabase | None = None,
) -> ExpressionSearchResult:
    """한국어 의도에서 일본어 후보를 만들고 실제 검색 결과가 있는 후보를 찾는다."""
    intent = korean_intent.strip()
    if not intent:
        raise ValueError("한국어로 찾을 의미를 입력해야 합니다.")

    media_ids, local_media = _split_active_media(database)
    generated = _generate_candidates(settings, intent, database=database)
    if len(generated.candidates) != settings.search.candidate_count:
        raise ValueError("AI가 설정한 수와 다른 개수의 일본어 후보를 반환했습니다.")

    unique_candidates = _deduplicate_candidates(generated.candidates)
    searches = tuple(
        _search_candidate(
            settings,
            candidate,
            nadeshiko_client=nadeshiko_client,
            database=database,
            media_ids=media_ids,
            local_media=local_media,
        )
        for candidate in unique_candidates
    )
    result = ExpressionSearchResult(
        korean_intent=intent,
        generated_candidates=tuple(generated.candidates),
        candidate_searches=searches,
    )
    if database is not None:
        database.save_search_result(
            result,
            ai_service=settings.ai.service,
            ai_model=settings.ai.model,
            instruction_version=CANDIDATE_INSTRUCTION_VERSION,
        )
    return result


def _generate_candidates(
    settings: AppSettings,
    intent: str,
    *,
    database: SceneCollectorDatabase | None,
) -> ExpressionCandidates:
    arguments = {
        "prompt": _candidate_prompt(intent, settings.search.candidate_count),
        "response_model": ExpressionCandidates,
    }
    if database is not None:
        return create_structured_response(
            settings,
            **arguments,
            cache=database,
            instruction_version=CANDIDATE_INSTRUCTION_VERSION,
        )
    return create_structured_response(settings, **arguments)


def _split_active_media(
    database: SceneCollectorDatabase | None,
) -> tuple[tuple[str, ...] | None, tuple[StoredMedia, ...]]:
    """활성 선호작을 Nadeshiko 필터용 ID와 로컬 자막 작품으로 나눈다.

    database가 없으면 기존 개발용 전체 corpus 검색을 유지한다(None, ()).
    database가 있으면 활성 작품이 하나도 없을 때 기존과 같이 오류를 낸다.
    """
    if database is None:
        return None, ()

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


def _search_candidate(
    settings: AppSettings,
    candidate: ExpressionCandidate,
    *,
    nadeshiko_client: Nadeshiko,
    database: SceneCollectorDatabase | None,
    media_ids: tuple[str, ...] | None,
    local_media: tuple[StoredMedia, ...],
) -> CandidateSearchResult:
    if media_ids is not None and not media_ids:
        response: SearchResponse | None = None
        exact_match_response: SearchResponse | None = None
        exact_segments: tuple[Segment, ...] = ()
    else:
        response = _search_nadeshiko(
            candidate.japanese,
            exact_match=False,
            take=settings.search.nadeshiko_take,
            nadeshiko_client=nadeshiko_client,
            database=database,
            media_ids=media_ids,
        )
        exact_segments = _surface_segments(response, candidate.japanese)
        exact_match_response = None

        if not exact_segments:
            exact_match_response = _search_nadeshiko(
                candidate.japanese,
                exact_match=True,
                take=settings.search.nadeshiko_take,
                nadeshiko_client=nadeshiko_client,
                database=database,
                media_ids=media_ids,
            )
            exact_segments = _surface_segments(exact_match_response, candidate.japanese)

    local_segments: tuple[LocalSegmentMatch, ...] = ()
    if database is not None and local_media:
        local_segments = _search_local_segments(database, candidate.japanese, local_media)

    return CandidateSearchResult(
        candidate=candidate,
        response=response,
        exact_match_response=exact_match_response,
        exact_segments=exact_segments,
        local_segments=local_segments,
    )


def _search_local_segments(
    database: SceneCollectorDatabase,
    surface: str,
    local_media: tuple[StoredMedia, ...],
) -> tuple[LocalSegmentMatch, ...]:
    """로컬 자막 색인에서 LIKE로 후보를 줄인 뒤 기존 surface 검사로 판정한다."""
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


def _search_nadeshiko(
    search_text: str,
    *,
    exact_match: bool,
    take: int,
    nadeshiko_client: Nadeshiko,
    database: SceneCollectorDatabase | None,
    media_ids: tuple[str, ...] | None = None,
) -> SearchResponse:
    conditions = {"media_ids": list(media_ids)} if media_ids is not None else None
    if database is not None:
        cached = database.get_nadeshiko_search_cache(
            search_text=search_text,
            exact_match=exact_match,
            take=take,
            conditions=conditions,
        )
        if cached is not None:
            return cached

    query = SearchQuery(search=search_text, exact_match=exact_match)
    if media_ids is None:
        response = nadeshiko_client.search(query=query, take=take)
    else:
        media_filter = SearchFiltersMedia(
            include=[MediaFilterItem(media_public_id=media_id) for media_id in media_ids]
        )
        response = nadeshiko_client.search(
            query=query,
            take=take,
            filters=SearchFilters(media=media_filter),
        )
    if database is not None:
        database.put_nadeshiko_search_cache(
            search_text=search_text,
            exact_match=exact_match,
            take=take,
            response=response,
            conditions=conditions,
        )
    return response


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


def _deduplicate_candidates(
    candidates: list[ExpressionCandidate],
) -> tuple[ExpressionCandidate, ...]:
    unique: list[ExpressionCandidate] = []
    seen: set[str] = set()
    for candidate in candidates:
        if candidate.japanese in seen:
            continue
        seen.add(candidate.japanese)
        unique.append(candidate)
    return tuple(unique)


def _candidate_prompt(korean_intent: str, candidate_count: int) -> str:
    return f"""다음 한국어 의도를 실제 일본어 회화나 애니 대사에서 자연스럽게 쓸 수 있는
서로 다른 일본어 표현 후보 {candidate_count}개로 바꾸세요.

한국어 의도: {korean_intent}

각 후보에는 일본어 표현 japanese, 표현 전체의 가나 읽기 reading,
간결한 한국어 의미 meaning_ko, 짧은 말투/격식 설명 register를 넣으세요.
같은 일본어 표현을 중복하지 마세요.
Nadeshiko corpus에 실제로 존재하는지는 판단하거나 주장하지 마세요."""
