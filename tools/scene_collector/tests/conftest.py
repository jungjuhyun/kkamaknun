import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--run-nadeshiko-live",
        action="store_true",
        default=False,
        help="실제 Nadeshiko API 연결 시험을 실행합니다.",
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if config.getoption("--run-nadeshiko-live"):
        return

    skip_live = pytest.mark.skip(reason="--run-nadeshiko-live로만 실제 연결 시험을 실행합니다.")
    for item in items:
        if "nadeshiko_live" in item.keywords:
            item.add_marker(skip_live)
