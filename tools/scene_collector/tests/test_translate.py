import copy
import dataclasses
import inspect
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
from scene_collector.translate import CONTEXT_TAKE, TranslatedScene, translate_segment

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
        search=SearchSettings(scene_result_limit=2),
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


def _relation() -> StoredMeaningExpression:
    """DB 없이 만드는 의미→표현 관계. translate_segment는 DB를 모른다."""
    return StoredMeaningExpression(
        id=1,
        meaning_id=1,
        expression_id=1,
        japanese=RELATION_JAPANESE,
        reading=RELATION_READING,
        meaning_ko=RELATION_MEANING_KO,
        register_text="정중체",
    )


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


def _work_scene_count(database: SceneCollectorDatabase) -> int:
    """work_scenes 전체 행 수를 DB에서 직접 센다."""
    row = database.connection.execute("SELECT COUNT(*) AS total FROM work_scenes").fetchone()
    return int(row["total"])


def _translate_scene(
    settings: AppSettings,
    client: "FakeContextNadeshiko",
    relation: StoredMeaningExpression,
    segment: Segment,
) -> TranslatedScene:
    """사용자가 장면 하나를 골라 번역을 요청하는 흐름을 그대로 따른다."""
    return translate_segment(
        settings,
        relation=relation,
        segment=segment,
        nadeshiko_client=client,
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

    translated = translate_segment(
        settings,
        relation=_relation(),
        segment=current,
        nadeshiko_client=client,
    )

    assert CONTEXT_TAKE == 2
    assert client.calls == [("seg-one", CONTEXT_TAKE)]
    assert len(fake_ai.prompts) == 1

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
    relation = _relation()
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

    first_scene = _translate_scene(settings, client, relation, first)
    last_scene = _translate_scene(settings, client, relation, last)
    alone_scene = _translate_scene(settings, client, relation, alone)

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

    _translate_scene(settings, client, _relation(), current)

    prompt = fake_ai.prompts[0]
    assert f"목표 표현: {RELATION_JAPANESE} ({RELATION_READING})" in prompt
    assert f"목표 표현의 한국어 의미: {RELATION_MEANING_KO}" in prompt
    assert "앞 대사: 前の台詞" in prompt
    assert "현재 일본어 대사: 大丈夫ですか？" in prompt
    assert "뒤 대사: 次の台詞" in prompt
    assert "nadeshiko_english: Are you all right?" in prompt


def test_translate_segment_takes_no_database_and_has_no_work_scene_id() -> None:
    """번역 함수는 DB 인자를 받지 않고 결과에도 작업 장면 ID가 없다.

    저장은 ui_controller.translate_scene의 책임이므로 여기서는 순수 함수다.
    """
    parameters = inspect.signature(translate_segment).parameters
    assert "database" not in parameters
    assert "work_scene_id" not in parameters

    field_names = {field.name for field in dataclasses.fields(TranslatedScene)}
    assert "work_scene_id" not in field_names


def test_translate_segment_does_not_write_to_database(
    tmp_path: Path,
    fake_ai: FakeTranslationClient,
) -> None:
    """번역만으로는 work_scenes가 하나도 늘거나 바뀌지 않는다.

    같은 DB에 이미 작업 중인 장면을 하나 두고, 번역 호출 전후의 행 수와 내용을
    직접 비교한다. 번역 결과 저장은 ui_controller.translate_scene이 맡는다.
    """
    settings = _settings(tmp_path)
    current = _segment("seg-one")
    other = _segment("seg-other", position=77)
    client = FakeContextNadeshiko()

    with SceneCollectorDatabase.open(settings) as database:
        relation = _seed_relation(database)
        existing_id = _work_scene_id(database, relation, other)
        database.set_work_scene_decision(existing_id, "예비")

        before_count = _work_scene_count(database)
        before_rows = database.list_work_scenes(relation.id)
        assert before_count == 1

        translated = translate_segment(
            settings,
            relation=relation,
            segment=current,
            nadeshiko_client=client,
        )

        assert translated.translation.natural_translation == "자연스러운 번역"
        assert _work_scene_count(database) == before_count
        assert database.list_work_scenes(relation.id) == before_rows
        # 번역한 장면에는 작업 장면이 생기지 않는다.
        assert database.get_work_scene(relation.id, "seg-one") is None

    with SceneCollectorDatabase.open(settings) as reopened:
        assert _work_scene_count(reopened) == before_count
        assert reopened.list_work_scenes(relation.id) == before_rows
        assert reopened.get_work_scene(relation.id, "seg-one") is None


def test_context_and_ai_are_not_cached_between_translations(
    tmp_path: Path,
    fake_ai: FakeTranslationClient,
) -> None:
    """같은 장면을 다시 번역하면 문맥 조회와 AI를 다시 호출한다(캐시 없음)."""
    settings = _settings(tmp_path)
    relation = _relation()
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

    first = _translate_scene(settings, client, relation, current)
    assert client.calls == [("seg-one", CONTEXT_TAKE)]
    assert len(fake_ai.prompts) == 1

    second = _translate_scene(settings, client, relation, current)
    assert client.calls == [("seg-one", CONTEXT_TAKE)] * 2
    assert len(fake_ai.prompts) == 2

    third = _translate_scene(settings, client, relation, current)
    assert client.calls == [("seg-one", CONTEXT_TAKE)] * 3
    assert len(fake_ai.prompts) == 3

    # 매번 새로 만든 번역이 그대로 돌아온다.
    assert first.translation.natural_translation == "자연스러운 번역 1"
    assert second.translation.natural_translation == "자연스러운 번역 2"
    assert third.translation.natural_translation == "자연스러운 번역 3"


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
