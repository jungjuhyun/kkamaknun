import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--run-nadeshiko-live",
        action="store_true",
        default=False,
        help="실제 Nadeshiko API 연결 시험을 실행합니다.",
    )
    parser.addoption(
        "--run-ai-live",
        action="store_true",
        default=False,
        help="실제 AI provider 연결 시험을 실행합니다.",
    )
    parser.addoption(
        "--run-search-live",
        action="store_true",
        default=False,
        help="실제 AI와 Nadeshiko를 사용하는 검색 품질 시험을 실행합니다.",
    )
    parser.addoption(
        "--run-surface-live",
        action="store_true",
        default=False,
        help="Nadeshiko 검색과 로컬 표면형 필터 비교 시험을 실행합니다.",
    )
    parser.addoption(
        "--run-media-live",
        action="store_true",
        default=False,
        help="실제 Nadeshiko 작품 metadata와 media filter 검색 시험을 실행합니다.",
    )
    parser.addoption(
        "--run-translation-live",
        action="store_true",
        default=False,
        help="실제 Nadeshiko 문맥 조회와 AI 장면 번역 시험을 실행합니다.",
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    for item in items:
        if "nadeshiko_live" in item.keywords and not config.getoption("--run-nadeshiko-live"):
            item.add_marker(
                pytest.mark.skip(reason="--run-nadeshiko-live로만 실제 연결 시험을 실행합니다.")
            )
        if "ai_live" in item.keywords and not config.getoption("--run-ai-live"):
            item.add_marker(
                pytest.mark.skip(reason="--run-ai-live로만 실제 AI 연결 시험을 실행합니다.")
            )
        if "search_live" in item.keywords and not config.getoption("--run-search-live"):
            item.add_marker(
                pytest.mark.skip(reason="--run-search-live로만 실제 검색 품질 시험을 실행합니다.")
            )
        if "surface_live" in item.keywords and not config.getoption("--run-surface-live"):
            item.add_marker(
                pytest.mark.skip(reason="--run-surface-live로만 실제 표면형 시험을 실행합니다.")
            )
        if "media_live" in item.keywords and not config.getoption("--run-media-live"):
            item.add_marker(
                pytest.mark.skip(reason="--run-media-live로만 실제 작품 metadata 시험을 실행합니다.")
            )
        if "translation_live" in item.keywords and not config.getoption("--run-translation-live"):
            item.add_marker(
                pytest.mark.skip(
                    reason="--run-translation-live로만 실제 장면 번역 시험을 실행합니다."
                )
            )


# ----------------------------------------------------------------------
# 검색 통계(oracle) 가짜 구현 — 모든 가짜 Nadeshiko client가 공유한다.
# ----------------------------------------------------------------------


def search_stats_response(counts: "dict[str, int] | None" = None):
    """작품별 매칭 수만 담은 공식 SearchStatsResponse를 만든다."""
    from nadeshiko.models import SearchStatsResponse

    return SearchStatsResponse.from_dict(
        {
            "media": [
                {"mediaPublicId": media_id, "matchCount": count, "episodeHits": []}
                for media_id, count in (counts or {}).items()
            ],
            "categories": [],
        }
    )


class FakeSearchStats:
    """가짜 client에 붙이는 기본 oracle.

    기본값은 "통계가 알려 줄 매칭이 없다"이므로 수집 검증은 항상 통과한다.
    검증 실패를 시험할 때만 expected_hits(일반 경로)와
    exact_expected_hits(정확 경로)를 지정한다. 실제 API의 통계는 검색과 같은
    exact_match 조건을 반영하므로 가짜도 경로를 구분한다.
    """

    expected_hits: "dict[str, int] | None" = None
    exact_expected_hits: "dict[str, int] | None" = None

    def get_search_stats(self, *, query=None, **kwargs: object):
        exact = bool(getattr(query, "exact_match", False))
        if exact:
            counts = (
                self.exact_expected_hits
                if self.exact_expected_hits is not None
                else self.expected_hits
            )
        else:
            counts = self.expected_hits
        return search_stats_response(counts)
