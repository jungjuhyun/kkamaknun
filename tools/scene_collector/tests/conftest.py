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
