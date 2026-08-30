import copy
import json
from collections.abc import Callable
from pathlib import Path

import pytest
from nadeshiko.models import Segment, SegmentContextResponse
from pydantic import ValidationError

import scene_collector.ai as ai_module
from scene_collector.config import AISettings, AppSettings, SearchSettings, StorageSettings
from scene_collector.database import SceneCollectorDatabase, StoredMeaningExpression
from scene_collector.models import SceneTranslation
from scene_collector.translate import (
    CONTEXT_TAKE,
    TRANSLATION_INSTRUCTION_VERSION,
    TranslatedScene,
    translate_work_scene,
)

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "nadeshiko_search_response.json"
FIXTURE_PAYLOAD = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))

KOREAN_MEANING = "괜찮냐고 묻는 말"
RELATION_JAPANESE = "大丈夫ですか"
RELATION_READING = "だいじょうぶですか"
RELATION_MEANING_KO = "괜찮아요?"
MEDIA_DISPLAY_NAME = "테스트 작품"


def _settings(work_data_dir: Path, *, model: str = "model-one") -> AppSettings:
    return AppSettings(
        storage=StorageSettings(work_data_dir=work_data_dir),
        ai=AISettings(service="provider-one", model=model),
        search=SearchSettings(nadeshiko_take=2),
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


def _segment(public_id: str, **overrides: object) -> Segment:
    return Segment.from_dict(_segment_dict(public_id, **overrides))


def _context_response(*segment_dicts: dict) -> SegmentContextResponse:
    return SegmentContextResponse.from_dict({"segments": list(segment_dicts)})


def _seed_relation(database: SceneCollectorDatabase) -> StoredMeaningExpression:
    """한국어 의미와 일본어 표현 하나를 표현 자산으로 저장한다."""
    meaning = database.upsert_meaning(KOREAN_MEANING)
    return database.add_meaning_expression(
        meaning.id,
        japanese=RELATION_JAPANESE,
        reading=RELATION_READING,
        meaning_ko=RELATION_MEANING_KO,
        register_text="정중체",
    )


def _work_scene_id(
    database: SceneCollectorDatabase,
    relation: StoredMeaningExpression,
    segment: Segment,
) -> int:
    """실제 화면처럼 작업이 발생하는 시점에 장면 스냅샷을 만든다."""
    return database.upsert_work_scene(
        relation.id,
        segment_public_id=segment.public_id,
        media_public_id=segment.media_public_id,
        media_display_name=MEDIA_DISPLAY_NAME,
        episode=segment.episode,
        start_time_ms=segment.start_time_ms,
        end_time_ms=segment.end_time_ms,
        japanese_text=segment.text_ja.content,
    )


def _translate_scene(
    settings: AppSettings,
    database: SceneCollectorDatabase,
    client: "FakeContextNadeshiko",
    relation: StoredMeaningExpression,
    segment: Segment,
) -> TranslatedScene:
    """사용자가 장면 하나를 골라 번역을 요청하는 흐름을 그대로 따른다."""
    return translate_work_scene(
        settings,
        relation=relation,
        segment=segment,
        work_scene_id=_work_scene_id(database, relation, segment),
        nadeshiko_client=client,
        database=database,
    )


class FakeContextNadeshiko:
    """문맥 조회 호출만 기록하는 fake Nadeshiko client."""

    def __init__(self, contexts: dict[str, SegmentContextResponse] | None = None) -> None:
        self.contexts = contexts or {}
        self.calls: list[tuple[str, int]] = []

    def get_segment_context(self, segment_public_id: str, *, take: int) -> SegmentContextResponse:
        self.calls.append((segment_public_id, take))
        return self.contexts.get(segment_public_id, _context_response())


class FakeTranslationClient:
    """prompt를 기록하고 결정적 번역 하나를 돌려주는 fake provider."""

    def __init__(self) -> None:
        self.prompts: list[str] = []
        self.responder: Callable[[str], SceneTranslation] = self._default_responder

    def create(
        self,
        *,
        response_model: type[SceneTranslation],
        messages: list[dict[str, str]],
    ) -> SceneTranslation:
        assert response_model is SceneTranslation
        prompt = messages[0]["content"]
        self.prompts.append(prompt)
        return self.responder(prompt)

    @staticmethod
    def _default_responder(prompt: str) -> SceneTranslation:
        return SceneTranslation(
            direct_meaning="직접 뜻",
            natural_translation="자연스러운 번역",
            scene_usage="상태 확인",
        )


@pytest.fixture()
def fake_ai(monkeypatch: pytest.MonkeyPatch) -> FakeTranslationClient:
    client = FakeTranslationClient()
    monkeypatch.setattr(ai_module.instructor, "from_provider", lambda _: client)
    return client


def test_requested_scene_uses_one_context_call_and_one_ai_call(
    tmp_path: Path,
    fake_ai: FakeTranslationClient,
) -> None:
    """장면 하나 요청에 문맥 조회 1회, AI 1회만 쓰고 가장 가까운 앞뒤를 고른다.

    문맥 응답의 순서를 믿지 않고 같은 작품·같은 화만 후보로 삼는지 함께 본다.
    """
    settings = _settings(tmp_path)
    current = _segment("seg-one", position=10, machine_translated=True)
    client = FakeContextNadeshiko(
        {
            "seg-one": _context_response(
                _segment_dict("seg-one", position=10),
                _segment_dict("noise-later-far", position=14),
                _segment_dict("next-one", position=12, text_ja="次の台詞"),
                _segment_dict("noise-other-media", media="other-media", position=9),
                _segment_dict("noise-other-episode", episode=2, position=9),
                _segment_dict("prev-one", position=8, text_ja="前の台詞"),
                _segment_dict("noise-earlier-far", position=5),
            )
        }
    )

    with SceneCollectorDatabase.open(settings) as database:
        relation = _seed_relation(database)
        work_scene_id = _work_scene_id(database, relation, current)

        translated = translate_work_scene(
            settings,
            relation=relation,
            segment=current,
            work_scene_id=work_scene_id,
            nadeshiko_client=client,
            database=database,
        )

    assert CONTEXT_TAKE == 2
    assert client.calls == [("seg-one", CONTEXT_TAKE)]
    assert len(fake_ai.prompts) == 1

    assert translated.work_scene_id == work_scene_id
    assert translated.segment_public_id == "seg-one"
    assert translated.previous_japanese == "前の台詞"
    assert translated.current_japanese == "大丈夫ですか？"
    assert translated.next_japanese == "次の台詞"
    assert translated.nadeshiko_english == "Are you all right? (기계번역)"
    assert translated.translation.natural_translation == "자연스러운 번역"


def test_missing_context_side_is_handled(
    tmp_path: Path,
    fake_ai: FakeTranslationClient,
) -> None:
    """앞이나 뒤 대사가 없어도 정상 처리하고 없는 쪽은 None으로 둔다."""
    settings = _settings(tmp_path)
    first = _segment("seg-first", position=1, text_en="")
    last = _segment("seg-last", position=99, text_en="")
    alone = _segment("seg-alone", position=50)
    client = FakeContextNadeshiko(
        {
            "seg-first": _context_response(
                _segment_dict("after", position=2, text_ja="次の台詞")
            ),
            "seg-last": _context_response(
                _segment_dict("before", position=98, text_ja="前の台詞")
            ),
        }
    )

    with SceneCollectorDatabase.open(settings) as database:
        relation = _seed_relation(database)
        first_scene = _translate_scene(settings, database, client, relation, first)
        last_scene = _translate_scene(settings, database, client, relation, last)
        alone_scene = _translate_scene(settings, database, client, relation, alone)

    assert first_scene.previous_japanese is None
    assert first_scene.next_japanese == "次の台詞"
    assert first_scene.nadeshiko_english is None
    assert last_scene.previous_japanese == "前の台詞"
    assert last_scene.next_japanese is None
    assert alone_scene.previous_japanese is None
    assert alone_scene.next_japanese is None

    assert "앞 대사: (없음)" in fake_ai.prompts[0]
    assert "뒤 대사: 次の台詞" in fake_ai.prompts[0]
    assert "앞 대사: 前の台詞" in fake_ai.prompts[1]
    assert "뒤 대사: (없음)" in fake_ai.prompts[1]
    assert "nadeshiko_english: (없음)" in fake_ai.prompts[0]


def test_prompt_contains_target_expression_and_context_lines(
    tmp_path: Path,
    fake_ai: FakeTranslationClient,
) -> None:
    """프롬프트에 목표 표현과 앞·현재·뒤 대사가 모두 들어간다."""
    settings = _settings(tmp_path)
    current = _segment("seg-one", position=10)
    client = FakeContextNadeshiko(
        {
            "seg-one": _context_response(
                _segment_dict("prev-one", position=9, text_ja="前の台詞"),
                _segment_dict("next-one", position=11, text_ja="次の台詞"),
            )
        }
    )

    with SceneCollectorDatabase.open(settings) as database:
        relation = _seed_relation(database)
        _translate_scene(settings, database, client, relation, current)

    prompt = fake_ai.prompts[0]
    assert f"목표 표현: {RELATION_JAPANESE} ({RELATION_READING})" in prompt
    assert f"목표 표현의 한국어 의미: {RELATION_MEANING_KO}" in prompt
    assert "앞 대사: 前の台詞" in prompt
    assert "현재 일본어 대사: 大丈夫ですか？" in prompt
    assert "뒤 대사: 次の台詞" in prompt
    assert "nadeshiko_english: Are you all right?" in prompt


def test_translation_is_saved_to_work_scene_with_provenance(
    tmp_path: Path,
    fake_ai: FakeTranslationClient,
) -> None:
    """번역 결과와 provenance가 work_scenes에 저장되고 재시작 후에도 남는다."""
    settings = _settings(tmp_path)
    current = _segment("seg-one")
    client = FakeContextNadeshiko()

    with SceneCollectorDatabase.open(settings) as database:
        relation = _seed_relation(database)
        _translate_scene(settings, database, client, relation, current)

        stored = database.get_work_scene(relation.id, "seg-one")
        assert stored is not None
        assert stored.decision is None
        assert stored.has_translation
        assert stored.direct_meaning == "직접 뜻"
        assert stored.natural_translation == "자연스러운 번역"
        assert stored.scene_usage == "상태 확인"
        assert stored.translation_ai_service == "provider-one"
        assert stored.translation_ai_model == "model-one"
        assert stored.translation_instruction_version == TRANSLATION_INSTRUCTION_VERSION
        assert stored.translated_at

    with SceneCollectorDatabase.open(settings) as reopened:
        restored = reopened.get_work_scene(relation.id, "seg-one")
        assert restored is not None
        assert restored.natural_translation == "자연스러운 번역"
        assert restored.translation_ai_model == "model-one"
        assert restored.translation_instruction_version == TRANSLATION_INSTRUCTION_VERSION


def test_translation_and_user_work_do_not_overwrite_each_other(
    tmp_path: Path,
    fake_ai: FakeTranslationClient,
) -> None:
    """번역 저장이 기존 판정·메모를 지우지 않고, 판정 저장도 번역을 지우지 않는다."""
    settings = _settings(tmp_path)
    current = _segment("seg-one")
    client = FakeContextNadeshiko()

    with SceneCollectorDatabase.open(settings) as database:
        relation = _seed_relation(database)
        work_scene_id = _work_scene_id(database, relation, current)
        database.set_work_scene_decision(work_scene_id, "채택")
        database.set_work_scene_notes(work_scene_id, "이 장면을 쓰자")

        _translate_scene(settings, database, client, relation, current)

        after_translation = database.get_work_scene(relation.id, "seg-one")
        assert after_translation is not None
        assert after_translation.decision == "채택"
        assert after_translation.notes == "이 장면을 쓰자"
        assert after_translation.natural_translation == "자연스러운 번역"

        database.set_work_scene_decision(work_scene_id, "예비")
        after_decision = database.get_work_scene(relation.id, "seg-one")
        assert after_decision is not None
        assert after_decision.decision == "예비"
        assert after_decision.notes == "이 장면을 쓰자"
        assert after_decision.direct_meaning == "직접 뜻"
        assert after_decision.natural_translation == "자연스러운 번역"
        assert after_decision.scene_usage == "상태 확인"


def test_context_and_ai_are_not_cached_between_translations(
    tmp_path: Path,
    fake_ai: FakeTranslationClient,
) -> None:
    """같은 장면을 다시 번역하면 문맥 조회와 AI를 다시 호출한다(캐시 없음)."""
    settings = _settings(tmp_path)
    current = _segment("seg-one", position=10)
    client = FakeContextNadeshiko(
        {
            "seg-one": _context_response(
                _segment_dict("prev-one", position=9, text_ja="前の台詞")
            )
        }
    )

    attempt = 0

    def counting_responder(prompt: str) -> SceneTranslation:
        nonlocal attempt
        attempt += 1
        return SceneTranslation(
            direct_meaning=f"직접 뜻 {attempt}",
            natural_translation=f"자연스러운 번역 {attempt}",
            scene_usage="상태 확인",
        )

    fake_ai.responder = counting_responder

    with SceneCollectorDatabase.open(settings) as database:
        relation = _seed_relation(database)
        _translate_scene(settings, database, client, relation, current)
        assert client.calls == [("seg-one", CONTEXT_TAKE)]
        assert len(fake_ai.prompts) == 1

        _translate_scene(settings, database, client, relation, current)
        assert client.calls == [("seg-one", CONTEXT_TAKE)] * 2
        assert len(fake_ai.prompts) == 2

    with SceneCollectorDatabase.open(settings) as reopened:
        _translate_scene(settings, reopened, client, relation, current)
        assert client.calls == [("seg-one", CONTEXT_TAKE)] * 3
        assert len(fake_ai.prompts) == 3

        # 다시 만든 번역이 저장된 작업물을 갱신한다.
        stored = reopened.get_work_scene(relation.id, "seg-one")
        assert stored is not None
        assert stored.natural_translation == "자연스러운 번역 3"


def test_scene_translation_model_rejects_empty_fields_and_scene_key() -> None:
    """장면 번역 자료형은 빈 값과 사라진 scene_key를 모두 거부한다."""
    with pytest.raises(ValidationError):
        SceneTranslation(
            direct_meaning="",
            natural_translation="자연스러운 번역",
            scene_usage="상태 확인",
        )
    with pytest.raises(ValidationError):
        SceneTranslation(
            scene_key="seg-one",
            direct_meaning="직접 뜻",
            natural_translation="자연스러운 번역",
            scene_usage="상태 확인",
        )
