import json
import os
from collections.abc import Callable
from pathlib import Path

import pytest
from nadeshiko import Nadeshiko
from nadeshiko.models import SearchResponse

import scene_collector.search as search_module
from scene_collector.config import AppSettings, load_settings
from scene_collector.curated import load_curated_pool
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


class _PathCountingNadeshiko:
    """일반·정확 검색의 페이지 수와 표면형 통과 수를 따로 세는 wrapper.

    실제 대사나 응답 원본은 보관하지 않고 개수만 센다.
    """

    def __init__(self, inner: Nadeshiko) -> None:
        self._inner = inner
        self.general_pages = 0
        self.exact_pages = 0
        self.general_matches = 0
        self.exact_matches = 0

    def search(self, **kwargs: object) -> SearchResponse:
        response = self._inner.search(**kwargs)
        query = kwargs.get("query")
        exact = bool(getattr(query, "exact_match", False))
        matched = len(
            search_module._surface_segments(response, getattr(query, "search", ""))
        )
        if exact:
            self.exact_pages += 1
            self.exact_matches += matched
        else:
            self.general_pages += 1
            self.general_matches += matched
        return response


@pytest.fixture()
def live_settings(tmp_path: Path) -> AppSettings:
    _required_environment("NADESHIKO_API_KEY")
    service = _required_environment("SCENE_COLLECTOR_SEARCH_LIVE_SERVICE")
    model = _required_environment("SCENE_COLLECTOR_SEARCH_LIVE_MODEL")
    if service == "google":
        _required_environment("GOOGLE_API_KEY")
    if service == "openai":
        _required_environment("OPENAI_API_KEY")

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
                # 표현 하나당 일반 검색과 정확 검색을 각각 페이지 끝까지 훑고 장면
                # ID로 합치므로, 호출 수는 그 표현의 실제 페이지 수만큼 늘어난다.
                search_calls = client.search_calls - search_calls_before
                # 장면 수를 자르지 않으므로 호출 수와 결과 수에 상한을 두지 않는다.
                assert search_calls >= 1
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
                        # 페이지 순회가 실제 사용량을 얼마나 쓰는지 관측한다.
                        "nadeshiko_search_calls": search_calls,
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


# ----------------------------------------------------------------------
# UAT에서 0건이 나온 실제 조합을 그대로 확인한다
# ----------------------------------------------------------------------

_RECALL_ITEM_KEY = "kimetsu_no_yaiba"
_RECALL_EXPRESSION = "大丈夫です"


@pytest.fixture()
def recall_settings(tmp_path: Path) -> AppSettings:
    """회수 확인 전용 설정. AI는 부르지 않으므로 Nadeshiko 키만 요구한다."""
    _required_environment("NADESHIKO_API_KEY")
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
                'service = "unused-in-this-check"',
                'model = "unused-in-this-check"',
                "",
                "[search]",
                "",
            )
        ),
        encoding="utf-8",
    )
    return load_settings(settings_file)


def test_paged_search_recovers_a_common_expression_in_a_real_media(
    recall_settings: AppSettings,
) -> None:
    """UAT에서 0건이 나왔던 조합을 실제 연결로 확인한다.

    사용자 DB는 건드리지 않는다. 임시 DB에 작품만 등록하고 검색만 한다.
    AI도 부르지 않는다 — 표현을 직접 저장하고 그 표현 하나만 찾는다.
    보고할 값은 정확 일치 장면 수와 논리 검색 호출 수뿐이다.
    """
    live_settings = recall_settings
    item = next(
        candidate for candidate in load_curated_pool() if candidate.key == _RECALL_ITEM_KEY
    )
    assert item.nadeshiko_media_ids, "이 확인에는 연결된 Nadeshiko 작품이 필요합니다."

    client = _PathCountingNadeshiko(create_nadeshiko_client(live_settings))
    with SceneCollectorDatabase.open(live_settings) as database:
        for media_id in item.nadeshiko_media_ids:
            database.upsert_media(media_id, display_name=item.korean_title)
        meaning = database.upsert_meaning("괜찮습니다")
        relation = database.add_meaning_expression(
            meaning.id,
            japanese=_RECALL_EXPRESSION,
            reading="だいじょうぶです",
            meaning_ko="괜찮습니다",
            register_text="정중체",
        )

        found = search_selected_expression(
            live_settings, relation, nadeshiko_client=client, database=database
        )

        # 검색만으로는 아무것도 저장되지 않는다.
        assert database.list_work_scenes(relation.id) == ()

    final_count = len(found.nadeshiko_segments)
    before_dedup = client.general_matches + client.exact_matches
    print(
        "[collection]"
        f" media={len(item.nadeshiko_media_ids)}개"
        f" general_pages={client.general_pages}"
        f" exact_pages={client.exact_pages}"
        f" before_dedup={before_dedup}"
        f" after_dedup={final_count}"
    )
    # 페이지를 다 훑고도 0건이면 수정이 끝난 것이 아니다. 원인을 다시 조사해야 한다.
    assert final_count > 0, (
        f"{_RECALL_EXPRESSION}의 정확 동일표현이 0건이다. "
        f"일반 {client.general_pages}쪽·정확 {client.exact_pages}쪽을 훑었다. "
        "원인을 다시 조사해야 한다."
    )
