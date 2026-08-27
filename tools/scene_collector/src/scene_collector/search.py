"""한국어 의도를 AI 후보와 Nadeshiko corpus 검색으로 연결한다."""

from dataclasses import dataclass

from nadeshiko import Nadeshiko
from nadeshiko.models import SearchQuery, SearchResponse

from scene_collector.ai import create_structured_response
from scene_collector.config import AppSettings
from scene_collector.models import ExpressionCandidate, ExpressionCandidates


@dataclass(frozen=True)
class CandidateSearchResult:
    """일본어 후보 하나와 해당 Nadeshiko 검색 응답."""

    candidate: ExpressionCandidate
    response: SearchResponse

    @property
    def has_results(self) -> bool:
        return bool(self.response.segments)


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
) -> ExpressionSearchResult:
    """한국어 의도에서 일본어 후보를 만들고 실제 검색 결과가 있는 후보를 찾는다."""
    intent = korean_intent.strip()
    if not intent:
        raise ValueError("한국어로 찾을 의미를 입력해야 합니다.")

    generated = create_structured_response(
        settings,
        prompt=_candidate_prompt(intent, settings.search.candidate_count),
        response_model=ExpressionCandidates,
    )
    if len(generated.candidates) != settings.search.candidate_count:
        raise ValueError("AI가 설정한 수와 다른 개수의 일본어 후보를 반환했습니다.")

    unique_candidates = _deduplicate_candidates(generated.candidates)
    searches = tuple(
        CandidateSearchResult(
            candidate=candidate,
            response=nadeshiko_client.search(
                query=SearchQuery(search=candidate.japanese),
                take=settings.search.nadeshiko_take,
            ),
        )
        for candidate in unique_candidates
    )
    return ExpressionSearchResult(
        korean_intent=intent,
        generated_candidates=tuple(generated.candidates),
        candidate_searches=searches,
    )


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
