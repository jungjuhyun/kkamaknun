import json
import os
from collections.abc import Callable
from pathlib import Path

import pytest
from nadeshiko import Nadeshiko
from nadeshiko.models import SearchResponse, SegmentContextResponse

import scene_collector.search as search_module
import scene_collector.translate as translate_module
from scene_collector.config import AppSettings, load_settings
from scene_collector.database import SceneCollectorDatabase
from scene_collector.media import media_display_name, store_media
from scene_collector.models import ExpressionCandidate, GeneratedExpressions
from scene_collector.nadeshiko import create_nadeshiko_client
from scene_collector.search import generate_expressions, search_selected_expression
from scene_collector.translate import TRANSLATION_INSTRUCTION_VERSION, TranslatedScene
from scene_collector.ui_controller import translate_scene

pytestmark = pytest.mark.translation_live

LIVE_EXPRESSION_GENERATION_LIMIT = 3
LIVE_NADESHIKO_TAKE = 3


def _required_environment(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        pytest.fail(f"Missing required live-test environment variable: {name}")
    return value


def _live_query() -> str:
    query = os.environ.get("SCENE_COLLECTOR_TRANSLATION_LIVE_QUERY", "大丈夫").strip()
    if not query:
        pytest.fail("SCENE_COLLECTOR_TRANSLATION_LIVE_QUERY가 비어 있습니다.")
    return query


class _CountingStructuredResponse:
    """실제 AI 구조화 응답 호출 수만 세고 그대로 위임한다."""

    def __init__(self, inner: Callable[..., object]) -> None:
        self._inner = inner
        self.calls = 0

    def __call__(self, *args: object, **kwargs: object) -> object:
        self.calls += 1
        return self._inner(*args, **kwargs)


class _CountingNadeshiko:
    """검색과 문맥 조회 실제 호출 수만 세는 공식 client wrapper."""

    def __init__(self, inner: Nadeshiko) -> None:
        self._inner = inner
        self.search_calls = 0
        self.context_calls = 0

    def search(self, **kwargs: object) -> SearchResponse:
        self.search_calls += 1
        return self._inner.search(**kwargs)

    def get_segment_context(
        self, segment_public_id: str, *, take: int
    ) -> SegmentContextResponse:
        self.context_calls += 1
        return self._inner.get_segment_context(segment_public_id, take=take)


@pytest.fixture()
def live_settings(tmp_path: Path) -> AppSettings:
    _required_environment("NADESHIKO_API_KEY")
    service = _required_environment("SCENE_COLLECTOR_TRANSLATION_LIVE_SERVICE")
    model = _required_environment("SCENE_COLLECTOR_TRANSLATION_LIVE_MODEL")
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
                f"expression_generation_limit = {LIVE_EXPRESSION_GENERATION_LIMIT}",
                f"nadeshiko_take = {LIVE_NADESHIKO_TAKE}",
                "",
            )
        ),
        encoding="utf-8",
    )
    return load_settings(settings_file)


def _scene_report(scene: TranslatedScene, target_japanese: str) -> dict[str, object]:
    return {
        "target_expression": target_japanese,
        "previous_japanese": scene.previous_japanese,
        "current_japanese": scene.current_japanese,
        "next_japanese": scene.next_japanese,
        "nadeshiko_english": scene.nadeshiko_english,
        "direct_meaning": scene.translation.direct_meaning,
        "natural_translation": scene.translation.natural_translation,
        "scene_usage": scene.translation.scene_usage,
    }


def test_context_and_single_scene_translation_live(
    live_settings: AppSettings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """사용자가 고른 장면 하나만 문맥 1회 + AI 1회로 번역해 작업물로 저장한다."""
    live_target = _live_query()
    fixed_candidate = ExpressionCandidate(
        japanese=live_target,
        reading="らいぶけんしょう",
        meaning_ko="translation live 시험 표현",
        register="시험용",
    )
    # 표현 생성은 이 시험의 대상이 아니므로 고정하고, 실제 AI는 장면 번역에만 쓴다.
    monkeypatch.setattr(
        search_module,
        "create_structured_response",
        lambda *args, **kwargs: GeneratedExpressions(expressions=[fixed_candidate]),
    )
    counting_ai = _CountingStructuredResponse(translate_module.create_structured_response)
    monkeypatch.setattr(translate_module, "create_structured_response", counting_ai)

    raw_client = create_nadeshiko_client(live_settings)
    client = _CountingNadeshiko(raw_client)
    try:
        media_page = raw_client.list_media(take=5)
        assert media_page.media
        chosen = max(media_page.media, key=lambda media: media.segment_count)
        display_name = media_display_name(chosen)

        with SceneCollectorDatabase.open(live_settings) as database:
            store_media(database, chosen)

            relations = generate_expressions(
                live_settings,
                "translation live 검증",
                database=database,
            )
            assert len(relations) == 1
            relation = relations[0]
            assert relation.japanese == live_target

            found = search_selected_expression(
                live_settings,
                relation,
                nadeshiko_client=client,
                database=database,
            )
            if not found.nadeshiko_segments:
                pytest.fail(
                    "선택한 작품에서 표면형이 맞는 장면을 찾지 못했습니다. "
                    "SCENE_COLLECTOR_TRANSLATION_LIVE_QUERY를 바꿔 다시 실행하세요."
                )
            # 검색만으로는 작업 장면이 생기지 않는다.
            assert database.list_work_scenes(relation.id) == ()

            # 앞뒤 문맥이 있는 장면을 골라 문맥 조회 결과까지 확인한다.
            segment = next(
                (scene for scene in found.nadeshiko_segments if scene.position > 1),
                found.nadeshiko_segments[0],
            )
            assert counting_ai.calls == 0
            assert client.context_calls == 0

            # 저장은 ui_controller.translate_scene이 번역 성공 뒤에만 맡는다.
            scene = translate_scene(
                live_settings,
                database,
                relation,
                segment,
                display_name,
                nadeshiko_client=client,
            )

            assert client.context_calls == 1
            assert counting_ai.calls == 1
            assert scene.segment_public_id == segment.public_id
            assert scene.current_japanese == segment.text_ja.content
            assert scene.previous_japanese is not None or scene.next_japanese is not None
            assert scene.translation.direct_meaning
            assert scene.translation.natural_translation
            assert scene.translation.scene_usage
            # 번역한 장면 하나만 작업물로 남는다.
            assert len(database.list_work_scenes(relation.id)) == 1

        with SceneCollectorDatabase.open(live_settings) as reopened:
            restored = reopened.get_work_scene(relation.id, segment.public_id)
            assert restored is not None
            assert restored.decision is None
            assert restored.media_public_id == segment.media_public_id
            assert restored.media_display_name == display_name
            assert restored.japanese_text == segment.text_ja.content
            assert restored.direct_meaning == scene.translation.direct_meaning
            assert restored.natural_translation == scene.translation.natural_translation
            assert restored.scene_usage == scene.translation.scene_usage
            assert restored.translation_ai_service == live_settings.ai.service
            assert restored.translation_ai_model == live_settings.ai.model
            assert restored.translation_instruction_version == TRANSLATION_INSTRUCTION_VERSION
            assert restored.has_translation is True
            # 저장된 작업물을 다시 읽을 때는 문맥도 AI도 다시 호출하지 않는다.
            assert client.context_calls == 1
            assert counting_ai.calls == 1

        report_path_value = os.environ.get("SCENE_COLLECTOR_TRANSLATION_LIVE_REPORT")
        if report_path_value:
            report = {
                "service": live_settings.ai.service,
                "model": live_settings.ai.model,
                "korean_meaning": "translation live 검증",
                "scene": _scene_report(scene, relation.japanese),
            }
            Path(report_path_value).write_text(
                json.dumps(report, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
    finally:
        raw_client.close()
