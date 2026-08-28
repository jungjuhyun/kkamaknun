import json
import os
from pathlib import Path

import pytest
from nadeshiko import Nadeshiko

import scene_collector.ai as ai_module
import scene_collector.search as search_module
from scene_collector.config import AppSettings, load_settings
from scene_collector.database import SceneCollectorDatabase
from scene_collector.media import store_media
from scene_collector.models import ExpressionCandidate, ExpressionCandidates
from scene_collector.nadeshiko import create_nadeshiko_client
from scene_collector.search import search_expressions
from scene_collector.translate import TranslatedScene, translate_expression_scenes

pytestmark = pytest.mark.translation_live

LIVE_CANDIDATE_COUNT = 3
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


class _CountingNadeshiko:
    """검색과 문맥 조회 실제 호출 수만 세는 공식 client wrapper."""

    def __init__(self, inner: Nadeshiko) -> None:
        self._inner = inner
        self.search_calls = 0
        self.context_calls = 0

    def search(self, **kwargs: object):
        self.search_calls += 1
        return self._inner.search(**kwargs)

    def get_segment_context(self, segment_public_id: str, *, take: int):
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
                f"candidate_count = {LIVE_CANDIDATE_COUNT}",
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


def test_context_and_batch_translation_live(
    live_settings: AppSettings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    live_target = _live_query()
    fixed_candidate = ExpressionCandidate(
        japanese=live_target,
        reading="らいぶけんしょう",
        meaning_ko="translation live 시험 표현",
        register="시험용",
    )
    monkeypatch.setattr(
        search_module,
        "create_structured_response",
        lambda *args, **kwargs: ExpressionCandidates(
            candidates=[fixed_candidate] * LIVE_CANDIDATE_COUNT
        ),
    )

    provider_creations = 0
    original_from_provider = ai_module.instructor.from_provider

    def counting_from_provider(provider_model: str):
        nonlocal provider_creations
        provider_creations += 1
        return original_from_provider(provider_model)

    monkeypatch.setattr(ai_module.instructor, "from_provider", counting_from_provider)

    raw_client = create_nadeshiko_client(live_settings)
    client = _CountingNadeshiko(raw_client)
    try:
        media_page = raw_client.list_media(take=5)
        assert media_page.media
        chosen = max(media_page.media, key=lambda media: media.segment_count)

        with SceneCollectorDatabase.open(live_settings) as database:
            store_media(database, chosen)

            search_result = search_expressions(
                live_settings,
                "translation live 검증",
                nadeshiko_client=client,
                database=database,
            )
            backed = search_result.corpus_backed_candidates
            if not backed or len(backed[0].exact_segments) < 2:
                pytest.fail(
                    "정확 surface 장면이 2개 미만입니다. "
                    "SCENE_COLLECTOR_TRANSLATION_LIVE_QUERY를 바꿔 다시 실행하세요."
                )

            run = database.load_search_run(1)
            assert run is not None
            expression = next(
                stored for stored in run.expressions if stored.segments
            )
            scene_count = len(expression.segments)
            assert scene_count >= 2

            translated = translate_expression_scenes(
                live_settings,
                expression.id,
                nadeshiko_client=client,
                database=database,
            )
            assert len(translated) == scene_count
            assert client.context_calls == scene_count
            first_provider_creations = provider_creations
            assert first_provider_creations == 1

            for scene in translated:
                assert scene.translation.direct_meaning
                assert scene.translation.natural_translation
                assert scene.translation.scene_usage

            translate_expression_scenes(
                live_settings,
                expression.id,
                nadeshiko_client=client,
                database=database,
            )
            assert client.context_calls == scene_count
            assert provider_creations == first_provider_creations

        with SceneCollectorDatabase.open(live_settings) as reopened:
            reopened_scenes = translate_expression_scenes(
                live_settings,
                expression.id,
                nadeshiko_client=client,
                database=reopened,
            )
            assert client.context_calls == scene_count
            assert provider_creations == first_provider_creations
            restored = reopened.get_review(expression.id, translated[0].segment_id)
            assert restored is not None
            assert restored.decision is None
            assert restored.natural_translation == translated[0].translation.natural_translation
            assert restored.translation_ai_service == live_settings.ai.service
            assert restored.translation_ai_model == live_settings.ai.model

        report_path_value = os.environ.get("SCENE_COLLECTOR_TRANSLATION_LIVE_REPORT")
        if report_path_value:
            report = {
                "service": live_settings.ai.service,
                "model": live_settings.ai.model,
                "scene_count": len(reopened_scenes),
                "scenes": [
                    _scene_report(scene, expression.candidate.japanese)
                    for scene in reopened_scenes
                ],
            }
            Path(report_path_value).write_text(
                json.dumps(report, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
    finally:
        raw_client.close()
