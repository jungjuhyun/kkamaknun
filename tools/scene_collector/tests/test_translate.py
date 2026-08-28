import copy
import json
from pathlib import Path

import pytest
from nadeshiko.models import SearchResponse, SegmentContextResponse
from pydantic import ValidationError

import scene_collector.ai as ai_module
import scene_collector.translate as translate_module
from scene_collector.config import AISettings, AppSettings, SearchSettings, StorageSettings
from scene_collector.database import SceneCollectorDatabase, StoredExpression
from scene_collector.models import (
    ExpressionCandidate,
    SceneTranslation,
    SceneTranslationBatch,
)
from scene_collector.search import CandidateSearchResult, ExpressionSearchResult
from scene_collector.translate import CONTEXT_TAKE, translate_expression_scenes

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "nadeshiko_search_response.json"
FIXTURE_PAYLOAD = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def _settings(work_data_dir: Path, *, model: str = "model-one") -> AppSettings:
    return AppSettings(
        storage=StorageSettings(work_data_dir=work_data_dir),
        ai=AISettings(service="provider-one", model=model),
        search=SearchSettings(candidate_count=3, nadeshiko_take=2),
    )


def _segment_dict(
    public_id: str,
    *,
    text_ja: str = "大丈夫ですか？",
    media: str = "anonymous-media-001",
    episode: int = 1,
    position: int = 42,
    text_en: str = "Are you all right?",
    machine_translated: bool = False,
) -> dict:
    segment = copy.deepcopy(FIXTURE_PAYLOAD["segments"][0])
    segment["publicId"] = public_id
    segment["mediaPublicId"] = media
    segment["episode"] = episode
    segment["position"] = position
    segment["textJa"]["content"] = text_ja
    segment["textEn"]["content"] = text_en
    segment["textEn"]["isMachineTranslated"] = machine_translated
    return segment


def _search_response(*segment_dicts: dict) -> SearchResponse:
    payload = {
        "segments": list(segment_dicts),
        "pagination": {
            "hasMore": False,
            "estimatedTotalHits": len(segment_dicts),
            "estimatedTotalHitsRelation": "EXACT",
            "cursor": None,
        },
    }
    return SearchResponse.from_dict(payload)


def _context_response(*segment_dicts: dict) -> SegmentContextResponse:
    return SegmentContextResponse.from_dict({"segments": list(segment_dicts)})


def _candidate(japanese: str) -> ExpressionCandidate:
    return ExpressionCandidate(
        japanese=japanese,
        reading="よみかた",
        meaning_ko="의미",
        register="말투",
    )


def _seed_expressions(
    database: SceneCollectorDatabase,
    *candidates_with_segments: tuple[str, tuple[dict, ...]],
) -> list[StoredExpression]:
    candidates = tuple(_candidate(japanese) for japanese, _ in candidates_with_segments)
    searches = []
    for candidate, (_, segment_dicts) in zip(candidates, candidates_with_segments):
        response = _search_response(*segment_dicts)
        searches.append(
            CandidateSearchResult(
                candidate=candidate,
                response=response,
                exact_match_response=None,
                exact_segments=tuple(response.segments),
            )
        )
    result = ExpressionSearchResult(
        korean_intent="번역 시험 의도",
        generated_candidates=candidates,
        candidate_searches=tuple(searches),
    )
    run_id = database.save_search_result(
        result,
        ai_service="provider-one",
        ai_model="model-one",
        instruction_version="candidate-v1",
    )
    run = database.load_search_run(run_id)
    assert run is not None
    return list(run.expressions)


class FakeContextNadeshiko:
    def __init__(self, contexts: dict[str, SegmentContextResponse] | None = None) -> None:
        self.contexts = contexts or {}
        self.calls: list[tuple[str, int]] = []

    def get_segment_context(self, segment_public_id: str, *, take: int) -> SegmentContextResponse:
        self.calls.append((segment_public_id, take))
        return self.contexts.get(segment_public_id, _context_response())


class FakeTranslationClient:
    """prompt의 장면 JSON을 읽어 결정적 번역을 돌려주는 fake provider."""

    def __init__(self) -> None:
        self.calls: list[list[dict]] = []
        self.responder = self._default_responder

    def create(
        self,
        *,
        response_model: type[SceneTranslationBatch],
        messages: list[dict[str, str]],
    ) -> SceneTranslationBatch:
        assert response_model is SceneTranslationBatch
        scenes = json.loads(messages[0]["content"].split("장면 JSON:\n", 1)[1])
        self.calls.append(scenes)
        return self.responder(scenes)

    @staticmethod
    def _default_responder(scenes: list[dict]) -> SceneTranslationBatch:
        return SceneTranslationBatch(
            translations=[
                SceneTranslation(
                    scene_key=scene["scene_key"],
                    direct_meaning=(
                        f"직접 {scene['target_expression']['japanese']} {scene['scene_key']}"
                    ),
                    natural_translation=f"자연 {scene['scene_key']}",
                    scene_usage="상태 확인",
                )
                for scene in scenes
            ]
        )


@pytest.fixture()
def fake_ai(monkeypatch: pytest.MonkeyPatch) -> FakeTranslationClient:
    client = FakeTranslationClient()
    monkeypatch.setattr(ai_module.instructor, "from_provider", lambda _: client)
    return client


def test_translates_stored_exact_segments_with_nearest_context(
    tmp_path: Path,
    fake_ai: FakeTranslationClient,
) -> None:
    settings = _settings(tmp_path)
    contexts = {
        "seg-one": _context_response(
            _segment_dict("seg-one", position=10),
            _segment_dict("noise-later-far", position=14),
            _segment_dict("next-one", position=12, text_ja="次の台詞"),
            _segment_dict("noise-other-media", media="other-media", position=9),
            _segment_dict("noise-other-episode", episode=2, position=9),
            _segment_dict("prev-one", position=8, text_ja="前の台詞"),
            _segment_dict("noise-earlier-far", position=5),
        ),
        "seg-two": _context_response(
            _segment_dict("prev-two", position=19, text_ja="前の台詞二"),
            _segment_dict("next-two", position=21, text_ja="次の台詞二"),
        ),
    }
    client = FakeContextNadeshiko(contexts)

    with SceneCollectorDatabase.open(settings) as database:
        expression = _seed_expressions(
            database,
            (
                "大丈夫ですか",
                (
                    _segment_dict("seg-one", position=10, machine_translated=True),
                    _segment_dict("seg-two", position=20, text_en=""),
                ),
            ),
        )[0]

        translated = translate_expression_scenes(
            settings,
            expression.id,
            nadeshiko_client=client,
            database=database,
        )

        assert sorted(client.calls) == [("seg-one", CONTEXT_TAKE), ("seg-two", CONTEXT_TAKE)]
        assert len(fake_ai.calls) == 1
        assert [scene["scene_key"] for scene in fake_ai.calls[0]] == ["seg-one", "seg-two"]

        first, second = translated
        assert first.previous_japanese == "前の台詞"
        assert first.next_japanese == "次の台詞"
        assert first.nadeshiko_english == "Are you all right? (기계번역)"
        assert second.previous_japanese == "前の台詞二"
        assert second.next_japanese == "次の台詞二"
        assert second.nadeshiko_english is None

        review = database.get_review(expression.id, first.segment_id)
        assert review is not None
        assert review.decision is None
        assert review.direct_meaning == "직접 大丈夫ですか seg-one"
        assert review.natural_translation == "자연 seg-one"
        assert review.scene_usage == "상태 확인"
        assert review.translation_ai_service == "provider-one"
        assert review.translation_ai_model == "model-one"
        assert review.translation_instruction_version == "scene-translation-v1"
        assert review.translation_input_hash
        assert review.translated_at


def test_first_and_last_scenes_have_empty_context_sides(
    tmp_path: Path,
    fake_ai: FakeTranslationClient,
) -> None:
    settings = _settings(tmp_path)
    contexts = {
        "seg-first": _context_response(_segment_dict("after", position=2)),
        "seg-last": _context_response(_segment_dict("before", position=98)),
    }
    client = FakeContextNadeshiko(contexts)

    with SceneCollectorDatabase.open(settings) as database:
        expression = _seed_expressions(
            database,
            (
                "大丈夫ですか",
                (
                    _segment_dict("seg-first", position=1),
                    _segment_dict("seg-last", position=99),
                ),
            ),
        )[0]

        translated = translate_expression_scenes(
            settings,
            expression.id,
            nadeshiko_client=client,
            database=database,
        )

        first, last = translated
        assert first.previous_japanese is None
        assert first.next_japanese is not None
        assert last.previous_japanese is not None
        assert last.next_japanese is None
        sent = {scene["scene_key"]: scene for scene in fake_ai.calls[0]}
        assert sent["seg-first"]["previous_japanese"] is None
        assert sent["seg-last"]["next_japanese"] is None


def test_context_cache_prevents_repeat_calls_even_after_reopen(
    tmp_path: Path,
    fake_ai: FakeTranslationClient,
) -> None:
    settings = _settings(tmp_path)
    client = FakeContextNadeshiko(
        {"seg-one": _context_response(_segment_dict("prev", position=41))}
    )

    with SceneCollectorDatabase.open(settings) as database:
        expression = _seed_expressions(
            database,
            ("大丈夫ですか", (_segment_dict("seg-one"),)),
        )[0]
        translate_expression_scenes(
            settings, expression.id, nadeshiko_client=client, database=database
        )
        assert client.calls == [("seg-one", CONTEXT_TAKE)]
        assert len(fake_ai.calls) == 1

        translate_expression_scenes(
            settings, expression.id, nadeshiko_client=client, database=database
        )
        assert client.calls == [("seg-one", CONTEXT_TAKE)]
        assert len(fake_ai.calls) == 1

    with SceneCollectorDatabase.open(settings) as reopened:
        translate_expression_scenes(
            settings, expression.id, nadeshiko_client=client, database=reopened
        )
        assert client.calls == [("seg-one", CONTEXT_TAKE)]
        assert len(fake_ai.calls) == 1


def test_ai_output_is_mapped_by_scene_key_not_order(
    tmp_path: Path,
    fake_ai: FakeTranslationClient,
) -> None:
    settings = _settings(tmp_path)
    client = FakeContextNadeshiko()

    def reversed_responder(scenes: list[dict]) -> SceneTranslationBatch:
        batch = FakeTranslationClient._default_responder(scenes)
        return SceneTranslationBatch(translations=list(reversed(batch.translations)))

    fake_ai.responder = reversed_responder

    with SceneCollectorDatabase.open(settings) as database:
        expression = _seed_expressions(
            database,
            (
                "大丈夫ですか",
                (
                    _segment_dict("seg-one", position=10),
                    _segment_dict("seg-two", position=20),
                ),
            ),
        )[0]
        translated = translate_expression_scenes(
            settings, expression.id, nadeshiko_client=client, database=database
        )

        by_public_id = {scene.segment_public_id: scene for scene in translated}
        assert by_public_id["seg-one"].translation.natural_translation == "자연 seg-one"
        assert by_public_id["seg-two"].translation.natural_translation == "자연 seg-two"


@pytest.mark.parametrize(
    ("mutation", "message"),
    (
        ("duplicate", "여러 번 반환"),
        ("missing", "누락"),
        ("unknown", "알 수 없는 장면"),
    ),
)
def test_rejects_invalid_ai_scene_mapping_without_saving(
    tmp_path: Path,
    fake_ai: FakeTranslationClient,
    mutation: str,
    message: str,
) -> None:
    settings = _settings(tmp_path)
    client = FakeContextNadeshiko()

    def broken_responder(scenes: list[dict]) -> SceneTranslationBatch:
        batch = FakeTranslationClient._default_responder(scenes)
        translations = list(batch.translations)
        if mutation == "duplicate":
            translations.append(translations[0])
        elif mutation == "missing":
            translations = translations[:-1]
        else:
            translations[0] = translations[0].model_copy(update={"scene_key": "unknown-key"})
        return SceneTranslationBatch(translations=translations)

    fake_ai.responder = broken_responder

    with SceneCollectorDatabase.open(settings) as database:
        expression = _seed_expressions(
            database,
            (
                "大丈夫ですか",
                (
                    _segment_dict("seg-one", position=10),
                    _segment_dict("seg-two", position=20),
                ),
            ),
        )[0]

        with pytest.raises(ValueError, match=message):
            translate_expression_scenes(
                settings, expression.id, nadeshiko_client=client, database=database
            )

        for stored in expression.segments:
            assert database.get_review(expression.id, stored.id) is None


def test_scene_translation_model_rejects_empty_fields() -> None:
    with pytest.raises(ValidationError):
        SceneTranslation(
            scene_key="scene",
            direct_meaning="",
            natural_translation="자연",
            scene_usage="쓰임",
        )
    with pytest.raises(ValidationError):
        SceneTranslationBatch(translations=[])


def test_ai_cache_misses_on_model_instruction_or_input_change(
    tmp_path: Path,
    fake_ai: FakeTranslationClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings(tmp_path)
    client = FakeContextNadeshiko(
        {"seg-one": _context_response(_segment_dict("prev", position=41, text_ja="元の前文"))}
    )

    with SceneCollectorDatabase.open(settings) as database:
        expression = _seed_expressions(
            database,
            ("大丈夫ですか", (_segment_dict("seg-one"),)),
        )[0]

        translate_expression_scenes(
            settings, expression.id, nadeshiko_client=client, database=database
        )
        translate_expression_scenes(
            settings, expression.id, nadeshiko_client=client, database=database
        )
        assert len(fake_ai.calls) == 1

        translate_expression_scenes(
            _settings(tmp_path, model="model-two"),
            expression.id,
            nadeshiko_client=client,
            database=database,
        )
        assert len(fake_ai.calls) == 2

        monkeypatch.setattr(
            translate_module,
            "TRANSLATION_INSTRUCTION_VERSION",
            "scene-translation-v2-test",
        )
        translate_expression_scenes(
            settings, expression.id, nadeshiko_client=client, database=database
        )
        assert len(fake_ai.calls) == 3
        monkeypatch.setattr(
            translate_module,
            "TRANSLATION_INSTRUCTION_VERSION",
            "scene-translation-v1",
        )

        database.put_nadeshiko_context_cache(
            segment_public_id="seg-one",
            take=CONTEXT_TAKE,
            response=_context_response(
                _segment_dict("prev", position=41, text_ja="바뀐前文")
            ),
        )
        translate_expression_scenes(
            settings, expression.id, nadeshiko_client=client, database=database
        )
        assert len(fake_ai.calls) == 4
        assert client.calls == [("seg-one", CONTEXT_TAKE)]


def test_translation_and_user_review_fields_do_not_overwrite_each_other(
    tmp_path: Path,
    fake_ai: FakeTranslationClient,
) -> None:
    settings = _settings(tmp_path)
    client = FakeContextNadeshiko()

    with SceneCollectorDatabase.open(settings) as database:
        expression = _seed_expressions(
            database,
            ("大丈夫ですか", (_segment_dict("seg-one"),)),
        )[0]
        segment_id = expression.segments[0].id

        translate_expression_scenes(
            settings, expression.id, nadeshiko_client=client, database=database
        )
        database.set_review_decision(expression.id, segment_id, "채택")

        review = database.get_review(expression.id, segment_id)
        assert review is not None
        assert review.decision == "채택"
        assert review.natural_translation == "자연 seg-one"
        assert review.translation_ai_model == "model-one"

        database.put_nadeshiko_context_cache(
            segment_public_id="seg-one",
            take=CONTEXT_TAKE,
            response=_context_response(_segment_dict("prev", position=41)),
        )
        translate_expression_scenes(
            settings, expression.id, nadeshiko_client=client, database=database
        )
        updated = database.get_review(expression.id, segment_id)
        assert updated is not None
        assert updated.decision == "채택"
        assert updated.natural_translation == "자연 seg-one"
        assert updated.translation_input_hash != review.translation_input_hash

    with SceneCollectorDatabase.open(settings) as reopened:
        restored = reopened.get_review(expression.id, segment_id)
        assert restored is not None
        assert restored.decision == "채택"
        assert restored.direct_meaning == "직접 大丈夫ですか seg-one"
        assert restored.natural_translation == "자연 seg-one"
        assert restored.scene_usage == "상태 확인"
        assert restored.translation_ai_service == "provider-one"
        assert restored.translation_instruction_version == "scene-translation-v1"


def test_shared_segment_reuses_context_but_keeps_relation_translations_apart(
    tmp_path: Path,
    fake_ai: FakeTranslationClient,
) -> None:
    settings = _settings(tmp_path)
    client = FakeContextNadeshiko()
    shared = _segment_dict("seg-shared", text_ja="もう大丈夫ですか？")

    with SceneCollectorDatabase.open(settings) as database:
        expressions = _seed_expressions(
            database,
            ("大丈夫ですか", (shared,)),
            ("もう大丈夫", (shared,)),
        )
        first, second = expressions
        shared_segment_id = first.segments[0].id
        assert second.segments[0].id == shared_segment_id

        translate_expression_scenes(
            settings, first.id, nadeshiko_client=client, database=database
        )
        assert client.calls == [("seg-shared", CONTEXT_TAKE)]

        translate_expression_scenes(
            settings, second.id, nadeshiko_client=client, database=database
        )
        assert client.calls == [("seg-shared", CONTEXT_TAKE)]
        assert len(fake_ai.calls) == 2

        first_review = database.get_review(first.id, shared_segment_id)
        second_review = database.get_review(second.id, shared_segment_id)
        assert first_review is not None and second_review is not None
        assert first_review.direct_meaning == "직접 大丈夫ですか seg-shared"
        assert second_review.direct_meaning == "직접 もう大丈夫 seg-shared"


def test_batches_are_bounded_and_all_scenes_translated(
    tmp_path: Path,
    fake_ai: FakeTranslationClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(translate_module, "TRANSLATION_BATCH_SIZE", 2)
    settings = _settings(tmp_path)
    client = FakeContextNadeshiko()

    with SceneCollectorDatabase.open(settings) as database:
        expression = _seed_expressions(
            database,
            (
                "大丈夫ですか",
                (
                    _segment_dict("seg-one", position=10),
                    _segment_dict("seg-two", position=20),
                    _segment_dict("seg-three", position=30),
                ),
            ),
        )[0]

        translated = translate_expression_scenes(
            settings, expression.id, nadeshiko_client=client, database=database
        )

        assert len(translated) == 3
        assert [len(call) for call in fake_ai.calls] == [2, 1]
        for stored in expression.segments:
            assert database.get_review(expression.id, stored.id) is not None


def test_unknown_expression_and_empty_expression_are_handled(
    tmp_path: Path,
    fake_ai: FakeTranslationClient,
) -> None:
    settings = _settings(tmp_path)
    client = FakeContextNadeshiko()

    with SceneCollectorDatabase.open(settings) as database:
        with pytest.raises(ValueError, match="표현을 찾을 수 없습니다"):
            translate_expression_scenes(
                settings, 9999, nadeshiko_client=client, database=database
            )

        expression = _seed_expressions(database, ("結果なし", ()))[0]
        assert (
            translate_expression_scenes(
                settings, expression.id, nadeshiko_client=client, database=database
            )
            == ()
        )
        assert client.calls == []
        assert fake_ai.calls == []
