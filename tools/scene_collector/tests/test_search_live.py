import json
import os
from collections.abc import Callable
from pathlib import Path

import pytest
from nadeshiko import Nadeshiko
from nadeshiko.models import SearchResponse

import scene_collector.search as search_module
from scene_collector.config import AppSettings, load_settings
from scene_collector.database import SceneCollectorDatabase
from scene_collector.media import store_media
from scene_collector.nadeshiko import create_nadeshiko_client
from scene_collector.search import (
    find_saved_expressions,
    generate_expressions,
    search_selected_expression,
)

pytestmark = pytest.mark.search_live

INTENTS_PATH = Path(__file__).parent / "fixtures" / "search_live_intents.json"
DEFAULT_EXPRESSION_GENERATION_LIMIT = 20
LIVE_MEDIA_TAKE = 10


def _required_environment(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        pytest.fail(f"Missing required live-test environment variable: {name}")
    return value


def _expression_generation_limit() -> int:
    """상한을 지정하지 않으면 제품 기본값 20을 그대로 쓴다."""
    raw_value = os.environ.get(
        "SCENE_COLLECTOR_SEARCH_LIVE_EXPRESSION_GENERATION_LIMIT", ""
    ).strip()
    if not raw_value:
        return DEFAULT_EXPRESSION_GENERATION_LIMIT
    try:
        return int(raw_value)
    except ValueError:
        pytest.fail(
            "SCENE_COLLECTOR_SEARCH_LIVE_EXPRESSION_GENERATION_LIMIT는 정수여야 합니다."
        )


class _CountingStructuredResponse:
    """실제 AI 구조화 응답 호출 수만 세고 그대로 위임한다."""

    def __init__(self, inner: Callable[..., object]) -> None:
        self._inner = inner
        self.calls = 0

    def __call__(self, *args: object, **kwargs: object) -> object:
        self.calls += 1
        return self._inner(*args, **kwargs)


class _CountingNadeshiko:
    """실제 대사 검색 호출 수만 세는 공식 client wrapper."""

    def __init__(self, inner: Nadeshiko) -> None:
        self._inner = inner
        self.search_calls = 0

    def search(self, **kwargs: object) -> SearchResponse:
        self.search_calls += 1
        return self._inner.search(**kwargs)


@pytest.fixture()
def live_settings(tmp_path: Path) -> AppSettings:
    _required_environment("NADESHIKO_API_KEY")
    service = _required_environment("SCENE_COLLECTOR_SEARCH_LIVE_SERVICE")
    model = _required_environment("SCENE_COLLECTOR_SEARCH_LIVE_MODEL")
    if service == "google":
        _required_environment("GOOGLE_API_KEY")
    if service == "openai":
        _required_environment("OPENAI_API_KEY")
    nadeshiko_take = int(_required_environment("SCENE_COLLECTOR_SEARCH_LIVE_NADESHIKO_TAKE"))

    work_data_dir = tmp_path / "work-data"
    work_data_dir.mkdir()
    settings_file = tmp_path / "settings.toml"
    settings_file.write_text(
        "\n".join(
            (
                "[storage]",
                f"work_data_dir = {json.dumps(str(work_data_dir))}",
                "",
                "[ai]",
                f"service = {json.dumps(service)}",
                f"model = {json.dumps(model)}",
                "",
                "[search]",
                f"expression_generation_limit = {_expression_generation_limit()}",
                f"nadeshiko_take = {nadeshiko_take}",
                "",
            )
        ),
        encoding="utf-8",
    )
    return load_settings(settings_file)


def test_korean_meanings_become_searchable_expression_assets(
    live_settings: AppSettings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """한국어 의미 → 표현 자산 저장 → 표현 하나만 검색까지 실제로 확인한다.

    표현 생성은 의미마다 AI 1회만 하고, Nadeshiko 검색은 그 중 표현 하나에
    대해서만 실행해 실제 호출량을 늘리지 않는다.
    """
    intents = json.loads(INTENTS_PATH.read_text(encoding="utf-8"))
    if len(intents) != 10:
        pytest.fail("search live fixture must contain exactly 10 intents")

    counting_ai = _CountingStructuredResponse(search_module.create_structured_response)
    monkeypatch.setattr(search_module, "create_structured_response", counting_ai)

    raw_client = create_nadeshiko_client(live_settings)
    client = _CountingNadeshiko(raw_client)
    evaluations: list[dict[str, object]] = []
    try:
        media_page = raw_client.list_media(take=LIVE_MEDIA_TAKE)
        if not media_page.media:
            pytest.fail("Nadeshiko 작품 목록이 비어 있어 검색 대상을 만들 수 없습니다.")

        with SceneCollectorDatabase.open(live_settings) as database:
            for media in media_page.media:
                store_media(database, media)

            for intent in intents:
                ai_calls_before = counting_ai.calls
                added = generate_expressions(live_settings, intent, database=database)
                assert counting_ai.calls == ai_calls_before + 1
                if not added:
                    pytest.fail(f"AI가 표현을 하나도 만들지 못했습니다: {intent}")
                assert len(added) <= live_settings.search.expression_generation_limit

                # 저장된 표현 조회는 AI도 Nadeshiko도 호출하지 않는다.
                search_calls_before = client.search_calls
                saved = find_saved_expressions(database, intent)
                assert counting_ai.calls == ai_calls_before + 1
                assert client.search_calls == search_calls_before
                assert {relation.japanese for relation in added} <= {
                    relation.japanese for relation in saved
                }

                relation = saved[0]
                found = search_selected_expression(
                    live_settings,
                    relation,
                    nadeshiko_client=client,
                    database=database,
                )
                # 표현 하나당 일반 검색 1회, 결과가 없을 때만 정확 검색 1회를 더 한다.
                assert 1 <= client.search_calls - search_calls_before <= 2
                assert found.relation.id == relation.id
                # 검색 결과는 저장하지 않는다.
                assert database.list_work_scenes(relation.id) == ()

                first_segment = (
                    found.nadeshiko_segments[0] if found.nadeshiko_segments else None
                )
                evaluations.append(
                    {
                        "korean_meaning": intent,
                        "generated_expressions": [
                            {
                                "japanese": stored.japanese,
                                "reading": stored.reading,
                                "meaning_ko": stored.meaning_ko,
                                "register_text": stored.register_text,
                            }
                            for stored in added
                        ],
                        "searched_japanese": relation.japanese,
                        "nadeshiko_scene_count": len(found.nadeshiko_segments),
                        "local_scene_count": len(found.local_segments),
                        "first_japanese": (
                            first_segment.text_ja.content if first_segment is not None else None
                        ),
                        "first_english": (
                            first_segment.text_en.content if first_segment is not None else None
                        ),
                    }
                )
    finally:
        raw_client.close()

    scene_backed_count = sum(
        1 for evaluation in evaluations if evaluation["nadeshiko_scene_count"]
    )
    report = {
        "service": live_settings.ai.service,
        "model": live_settings.ai.model,
        "expression_generation_limit": live_settings.search.expression_generation_limit,
        "expression_generation_success_count": len(evaluations),
        "total_generated_expressions": sum(
            len(evaluation["generated_expressions"]) for evaluation in evaluations
        ),
        "searched_expression_count": len(evaluations),
        "inputs_with_scenes": scene_backed_count,
        "evaluations": evaluations,
    }
    report_path_value = os.environ.get("SCENE_COLLECTOR_SEARCH_LIVE_REPORT")
    if report_path_value:
        Path(report_path_value).write_text(
            json.dumps(report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    assert report["expression_generation_success_count"] == 10
    assert counting_ai.calls == 10
