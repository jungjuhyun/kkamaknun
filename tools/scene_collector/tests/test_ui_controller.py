import copy
import json
from pathlib import Path

import pytest
from nadeshiko.models import (
    MediaSummary,
    SearchFilters,
    SearchQuery,
    SearchResponse,
    Segment,
    SegmentContextResponse,
)
from pydantic import BaseModel

import scene_collector.search as search_module
import scene_collector.translate as translate_module
import scene_collector.ui_controller as ui_controller
from scene_collector.config import AISettings, AppSettings, SearchSettings, StorageSettings
from scene_collector.database import SceneCollectorDatabase, StoredMeaningExpression
from scene_collector.media import store_media
from scene_collector.models import ExpressionCandidate, GeneratedExpressions, SceneTranslation
from scene_collector.subtitles import index_local_subtitles
from scene_collector.translate import CONTEXT_TAKE
from scene_collector.ui_controller import (
    REVIEW_DECISIONS,
    SceneRow,
    ensure_work_scene,
    format_timecode,
    generate_more_expressions,
    local_scene_line,
    lookup_expressions,
    save_decision,
    save_notes,
    scene_line,
    scene_rows,
    search_relation,
    settings_summary,
    translate_scene,
    work_scene_line,
)

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "nadeshiko_search_response.json"
FIXTURE_PAYLOAD = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))

MEDIA_PUBLIC_ID = "anonymous-media-001"
MEDIA_NAMES = {MEDIA_PUBLIC_ID: "나데시코 작품"}

NADESHIKO_MEDIA = MediaSummary(
    public_id=MEDIA_PUBLIC_ID,
    slug="anonymous-media",
    name_ja="나데시코 작품",
    name_romaji="",
    name_en="",
    cover_url="https://media.example.invalid/cover.webp",
    category="ANIME",
)

SRT_EPISODE_1 = """1
00:00:01,000 --> 00:00:02,500
（ミサ）大丈夫ですか？

2
00:00:05,000 --> 00:00:06,000
ありがとう
"""


def _settings(
    work_data_dir: Path,
    *,
    api_key: str | None = None,
    generation_limit: int | None = None,
) -> AppSettings:
    """generation_limit이 None이면 표현 생성 상한의 기본값을 그대로 쓴다."""
    keyword: dict[str, str] = {"NADESHIKO_API_KEY": api_key} if api_key else {}
    search = (
        SearchSettings(nadeshiko_take=2)
        if generation_limit is None
        else SearchSettings(expression_generation_limit=generation_limit, nadeshiko_take=2)
    )
    return AppSettings(
        storage=StorageSettings(work_data_dir=work_data_dir),
        ai=AISettings(service="provider-one", model="model-one"),
        search=search,
        **keyword,
    )


def _generated(*japanese: str) -> GeneratedExpressions:
    return GeneratedExpressions(
        expressions=[
            ExpressionCandidate(
                japanese=text,
                reading=f"よみかた{index}",
                meaning_ko=f"의미 {index}",
                register=f"말투 {index}",
            )
            for index, text in enumerate(japanese, start=1)
        ]
    )


def _segment_dict(
    public_id: str,
    text_ja: str,
    *,
    position: int = 1,
    episode: int | None = 1,
) -> dict:
    segment = copy.deepcopy(FIXTURE_PAYLOAD["segments"][0])
    segment["publicId"] = public_id
    segment["position"] = position
    segment["episode"] = episode
    segment["mediaPublicId"] = MEDIA_PUBLIC_ID
    segment["textJa"]["content"] = text_ja
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


def _segment(public_id: str, text_ja: str, *, episode: int | None = 1) -> Segment:
    return _search_response(_segment_dict(public_id, text_ja, episode=episode)).segments[0]


def _seed_relations(
    database: SceneCollectorDatabase,
    korean_meaning: str,
    *japanese: str,
) -> tuple[StoredMeaningExpression, ...]:
    """AI 없이 표현 자산을 직접 저장한다."""
    meaning = database.upsert_meaning(korean_meaning)
    return tuple(
        database.add_meaning_expression(
            meaning.id,
            japanese=text,
            reading=f"よみかた{index}",
            meaning_ko=f"의미 {index}",
            register_text=f"말투 {index}",
        )
        for index, text in enumerate(japanese, start=1)
    )


def _subtitle_dir(tmp_path: Path) -> Path:
    directory = tmp_path / "subs"
    directory.mkdir()
    (directory / "테스트 작품 S1E01.srt").write_text(SRT_EPISODE_1, encoding="utf-8")
    return directory


def _forbidden_ai(*args: object, **kwargs: object) -> object:
    raise AssertionError("이 흐름에서는 AI를 호출하면 안 됩니다.")


class FakeAI:
    """AI 호출 횟수와 prompt를 기록하는 대역. 실제 provider를 부르지 않는다."""

    def __init__(self, *responses: BaseModel) -> None:
        self.responses = list(responses)
        self.prompts: list[str] = []

    def __call__(
        self,
        settings: AppSettings,
        *,
        prompt: str,
        response_model: type[BaseModel],
    ) -> BaseModel:
        self.prompts.append(prompt)
        if not self.responses:
            raise AssertionError("예상보다 AI 호출이 많습니다.")
        return self.responses.pop(0)

    @property
    def call_count(self) -> int:
        return len(self.prompts)


class FakeNadeshiko:
    """검색·문맥 조회 호출을 기록하는 대역. 실제 network를 사용하지 않는다."""

    def __init__(self, response: SearchResponse) -> None:
        self.response = response
        self.search_calls: list[tuple[str, bool]] = []
        self.context_calls: list[tuple[str, int]] = []

    def search(
        self,
        *,
        query: SearchQuery,
        take: int,
        filters: SearchFilters,
    ) -> SearchResponse:
        self.search_calls.append((query.search, bool(query.exact_match)))
        return self.response

    def get_segment_context(self, segment_public_id: str, *, take: int) -> SegmentContextResponse:
        self.context_calls.append((segment_public_id, take))
        return SegmentContextResponse.from_dict({"segments": []})


def test_settings_summary_reports_state_without_secret_value(tmp_path: Path) -> None:
    without_key = settings_summary(_settings(tmp_path, generation_limit=7))
    assert without_key.work_data_dir == tmp_path
    assert without_key.database_file.parent == tmp_path
    assert without_key.ai_service == "provider-one"
    assert without_key.ai_model == "model-one"
    assert without_key.expression_generation_limit == 7
    assert without_key.nadeshiko_take == 2
    assert without_key.nadeshiko_key_set is False

    secret = "very-secret-api-key"
    with_key = settings_summary(_settings(tmp_path, api_key=secret))
    assert with_key.nadeshiko_key_set is True
    assert with_key.expression_generation_limit == 20  # 표현 생성 상한 기본값
    assert secret not in repr(with_key)


def test_lookup_expressions_returns_saved_assets_without_ai(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # lookup_expressions는 Nadeshiko 클라이언트를 받지 않으므로 Nadeshiko 호출은 0회다.
    monkeypatch.setattr(search_module, "create_structured_response", _forbidden_ai)
    settings = _settings(tmp_path)

    with SceneCollectorDatabase.open(settings) as database:
        _seed_relations(database, "괜찮냐고 묻는 말", "大丈夫ですか", "平気ですか")

        # 끝 문장부호만 다른 입력도 같은 의미로 조회된다.
        screen = lookup_expressions(database, "괜찮냐고 묻는 말?")
        assert screen.has_expressions is True
        assert screen.korean_meaning == "괜찮냐고 묻는 말"
        assert [relation.japanese for relation in screen.relations] == [
            "大丈夫ですか",
            "平気ですか",
        ]
        assert screen.relations[0].meaning_ko == "의미 1"
        assert screen.relations[0].register_text == "말투 1"

        missing = lookup_expressions(database, " 처음 보는 의미 ")
        assert missing.has_expressions is False
        assert missing.relations == ()
        assert missing.korean_meaning == "처음 보는 의미"


def test_generate_more_expressions_calls_ai_once_and_returns_only_new(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_ai = FakeAI(
        _generated("大丈夫ですか", "平気ですか"),
        _generated("大丈夫ですか", "無事ですか"),
    )
    monkeypatch.setattr(search_module, "create_structured_response", fake_ai)
    settings = _settings(tmp_path)

    with SceneCollectorDatabase.open(settings) as database:
        screen, added = generate_more_expressions(settings, database, "괜찮냐고 묻는 말")
        assert fake_ai.call_count == 1
        assert [relation.japanese for relation in added] == ["大丈夫ですか", "平気ですか"]
        assert [relation.japanese for relation in screen.relations] == [
            "大丈夫ですか",
            "平気ですか",
        ]
        assert screen.korean_meaning == "괜찮냐고 묻는 말"

        more_screen, more_added = generate_more_expressions(settings, database, "괜찮냐고 묻는 말")
        assert fake_ai.call_count == 2
        # 이미 저장된 표현은 다시 추가하지 않고 새 표현만 돌려준다.
        assert [relation.japanese for relation in more_added] == ["無事ですか"]
        assert [relation.japanese for relation in more_screen.relations] == [
            "大丈夫ですか",
            "平気ですか",
            "無事ですか",
        ]
        # 두 번째 prompt에는 중복을 피하도록 기존 표현이 들어간다.
        assert "大丈夫ですか" in fake_ai.prompts[1]
        assert "平気ですか" in fake_ai.prompts[1]


def test_scene_rows_attach_saved_work_scene_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(search_module, "create_structured_response", _forbidden_ai)
    settings = _settings(tmp_path)
    client = FakeNadeshiko(
        _search_response(
            _segment_dict("segment-a", "あの、大丈夫ですか？", position=1),
            _segment_dict("segment-b", "大丈夫ですか、先輩。", position=2),
            _segment_dict("segment-c", "元気ですか？", position=3),
        )
    )

    with SceneCollectorDatabase.open(settings) as database:
        store_media(database, NADESHIKO_MEDIA)
        (relation,) = _seed_relations(database, "괜찮냐고 묻는 말", "大丈夫ですか")

        found = search_relation(settings, database, relation, nadeshiko_client=client)
        assert client.search_calls == [("大丈夫ですか", False)]
        assert found.relation == relation
        # 표면형이 다른 장면은 검색 결과에서 빠진다.
        assert [segment.public_id for segment in found.nadeshiko_segments] == [
            "segment-a",
            "segment-b",
        ]

        rows = scene_rows(database, found, MEDIA_NAMES)
        assert [row.segment_public_id for row in rows] == ["segment-a", "segment-b"]
        assert all(row.media_display_name == "나데시코 작품" for row in rows)
        # 작업이 없는 장면은 저장 상태가 없다.
        assert all(row.work_scene is None for row in rows)
        assert all(row.decision is None for row in rows)

        save_decision(database, relation, rows[0].segment, rows[0].media_display_name, "채택")

        refreshed = scene_rows(database, found, MEDIA_NAMES)
        assert refreshed[0].work_scene is not None
        assert refreshed[0].decision == "채택"
        assert refreshed[1].work_scene is None
        assert refreshed[1].decision is None

        # 표시명을 모르는 작품은 public ID로 대신 보여준다.
        unknown_names = scene_rows(database, found, {})
        assert unknown_names[0].media_display_name == MEDIA_PUBLIC_ID


def test_local_subtitle_matches_stay_reference_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """로컬 자막 결과는 참고 표시까지만 간다. 작업 장면도 내보내기도 되지 않는다."""
    monkeypatch.setattr(search_module, "create_structured_response", _forbidden_ai)
    settings = _settings(tmp_path)
    client = FakeNadeshiko(
        _search_response(_segment_dict("segment-a", "あの、大丈夫ですか？", position=1))
    )

    with SceneCollectorDatabase.open(settings) as database:
        store_media(database, NADESHIKO_MEDIA)
        index_local_subtitles(database, "테스트 작품", _subtitle_dir(tmp_path))
        (relation,) = _seed_relations(database, "괜찮냐고 묻는 말", "大丈夫ですか")

        found = search_relation(settings, database, relation, nadeshiko_client=client)
        assert found.local_segments, "로컬 자막 참고 결과가 있어야 한다"
        assert local_scene_line(found.local_segments[0])

        # 장면 목록은 Nadeshiko 장면만으로 만든다.
        rows = scene_rows(database, found, MEDIA_NAMES)
        assert [row.segment_public_id for row in rows] == ["segment-a"]

        save_decision(database, relation, rows[0].segment, rows[0].media_display_name, "채택")

        # 저장된 작업 장면과 내보내기 대상에는 Nadeshiko 장면 하나뿐이다.
        assert [scene.segment_public_id for scene in database.list_work_scenes(relation.id)] == [
            "segment-a"
        ]
        assert [row.segment_public_id for row in database.list_accepted_work_scenes()] == [
            "segment-a"
        ]


def test_save_decision_and_notes_create_work_scene_and_keep_each_other(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert REVIEW_DECISIONS == ("채택", "예비", "제외")
    monkeypatch.setattr(search_module, "create_structured_response", _forbidden_ai)
    settings = _settings(tmp_path)
    client = FakeNadeshiko(_search_response(_segment_dict("segment-a", "あの、大丈夫ですか？")))

    with SceneCollectorDatabase.open(settings) as database:
        store_media(database, NADESHIKO_MEDIA)
        (relation,) = _seed_relations(database, "괜찮냐고 묻는 말", "大丈夫ですか")

        found = search_relation(settings, database, relation, nadeshiko_client=client)
        # 검색만으로는 작업 장면이 저장되지 않는다.
        assert database.list_work_scenes(relation.id) == ()

        row = scene_rows(database, found, MEDIA_NAMES)[0]
        decided = save_decision(database, relation, row.segment, row.media_display_name, "채택")
        assert len(database.list_work_scenes(relation.id)) == 1
        assert decided.decision == "채택"
        assert decided.notes is None
        assert decided.segment_public_id == "segment-a"
        assert decided.media_public_id == MEDIA_PUBLIC_ID
        assert decided.media_display_name == "나데시코 작품"
        assert decided.episode == 1
        assert decided.japanese_text == "あの、大丈夫ですか？"

        noted = save_notes(database, relation, row.segment, row.media_display_name, "  발음 확인  ")
        assert noted.id == decided.id
        assert noted.notes == "발음 확인"
        # 메모 저장이 판정을 지우지 않는다.
        assert noted.decision == "채택"

        changed = save_decision(database, relation, row.segment, row.media_display_name, "예비")
        assert changed.id == decided.id
        assert changed.decision == "예비"
        # 판정 저장이 메모를 지우지 않는다.
        assert changed.notes == "발음 확인"
        assert len(database.list_work_scenes(relation.id)) == 1


def test_restart_keeps_expression_assets_and_work_scenes_without_search_restore(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_ai = FakeAI(_generated("大丈夫ですか", "平気ですか"))
    monkeypatch.setattr(search_module, "create_structured_response", fake_ai)
    settings = _settings(tmp_path)
    client = FakeNadeshiko(_search_response(_segment_dict("segment-a", "あの、大丈夫ですか？")))

    with SceneCollectorDatabase.open(settings) as database:
        store_media(database, NADESHIKO_MEDIA)
        screen, _ = generate_more_expressions(settings, database, "괜찮냐고 묻는 말")
        # 표현 생성은 Nadeshiko를 호출하지 않는다.
        assert client.search_calls == []

        relation = screen.relations[0]
        found = search_relation(settings, database, relation, nadeshiko_client=client)
        row = scene_rows(database, found, MEDIA_NAMES)[0]
        save_decision(database, relation, row.segment, row.media_display_name, "채택")
        save_notes(database, relation, row.segment, row.media_display_name, "다시 볼 장면")

    # 앱 재시작: 같은 설정으로 DB만 다시 연다.
    with SceneCollectorDatabase.open(settings) as reopened:
        restored = lookup_expressions(reopened, "괜찮냐고 묻는 말")
        assert [relation.japanese for relation in restored.relations] == [
            "大丈夫ですか",
            "平気ですか",
        ]

        scenes = reopened.list_work_scenes(restored.relations[0].id)
        assert len(scenes) == 1
        assert scenes[0].segment_public_id == "segment-a"
        assert scenes[0].decision == "채택"
        assert scenes[0].notes == "다시 볼 장면"

    # 재시작만으로는 AI도 Nadeshiko도 다시 부르지 않는다.
    assert fake_ai.call_count == 1
    assert len(client.search_calls) == 1
    # 지난 검색 결과를 자동으로 되살리는 API는 없다.
    for removed in ("restore_latest_search", "run_expression_search", "select_expression"):
        assert not hasattr(ui_controller, removed)


def test_translate_scene_saves_translation_on_the_work_scene(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(search_module, "create_structured_response", _forbidden_ai)
    fake_ai = FakeAI(
        SceneTranslation(
            direct_meaning="괜찮습니까",
            natural_translation="괜찮으세요?",
            scene_usage="상태 확인",
        )
    )
    monkeypatch.setattr(translate_module, "create_structured_response", fake_ai)
    settings = _settings(tmp_path)
    client = FakeNadeshiko(_search_response(_segment_dict("segment-a", "あの、大丈夫ですか？")))

    with SceneCollectorDatabase.open(settings) as database:
        store_media(database, NADESHIKO_MEDIA)
        (relation,) = _seed_relations(database, "괜찮냐고 묻는 말", "大丈夫ですか")
        found = search_relation(settings, database, relation, nadeshiko_client=client)
        row = scene_rows(database, found, MEDIA_NAMES)[0]

        translated = translate_scene(
            settings,
            database,
            relation,
            row.segment,
            row.media_display_name,
            nadeshiko_client=client,
        )

        assert fake_ai.call_count == 1
        assert client.context_calls == [("segment-a", CONTEXT_TAKE)]
        assert translated.translation.natural_translation == "괜찮으세요?"

        stored = database.get_work_scene(relation.id, "segment-a")
        assert stored is not None
        assert stored.id == translated.work_scene_id
        assert stored.direct_meaning == "괜찮습니까"
        assert stored.natural_translation == "괜찮으세요?"
        assert stored.scene_usage == "상태 확인"
        assert stored.translation_ai_service == "provider-one"
        assert stored.translation_ai_model == "model-one"
        # 번역만으로 판정이 생기지는 않는다.
        assert stored.decision is None


def test_format_timecode_pads_hours_minutes_seconds_and_milliseconds() -> None:
    assert format_timecode(0) == "00:00:00.000"
    assert format_timecode(123400) == "00:02:03.400"
    assert format_timecode(3723456) == "01:02:03.456"
    assert format_timecode(-5) == "00:00:00.000"


def test_scene_line_shows_media_episode_timecode_and_text() -> None:
    row = SceneRow(
        segment=_segment("segment-a", "あの、大丈夫ですか？"),
        media_display_name="나데시코 작품",
        work_scene=None,
    )
    assert scene_line(row) == "나데시코 작품 · 1화 · 00:02:03.400 · あの、大丈夫ですか？"

    no_episode = SceneRow(
        segment=_segment("segment-b", "大丈夫ですか、先輩。", episode=None),
        media_display_name="나데시코 작품",
        work_scene=None,
    )
    assert scene_line(no_episode).startswith("나데시코 작품 · 화수 없음 · 00:02:03.400 · ")


def test_work_scene_line_shows_decision_media_and_timecode(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    with SceneCollectorDatabase.open(settings) as database:
        (relation,) = _seed_relations(database, "괜찮냐고 묻는 말", "大丈夫ですか")

        named_id = ensure_work_scene(
            database, relation, _segment("segment-a", "あの、大丈夫ですか？"), "나데시코 작품"
        )
        pending = database.get_work_scene(relation.id, "segment-a")
        assert pending is not None
        assert work_scene_line(pending) == (
            "[판정 없음] 나데시코 작품 · 1화 · 00:02:03.400 · あの、大丈夫ですか？"
        )

        database.set_work_scene_decision(named_id, "채택")
        decided = database.get_work_scene(relation.id, "segment-a")
        assert decided is not None
        assert work_scene_line(decided) == (
            "[채택] 나데시코 작품 · 1화 · 00:02:03.400 · あの、大丈夫ですか？"
        )

        # 표시명이 없으면 작품 public ID로 대신 보여준다.
        ensure_work_scene(database, relation, _segment("segment-b", "大丈夫ですか、先輩。"), None)
        unnamed = database.get_work_scene(relation.id, "segment-b")
        assert unnamed is not None
        assert work_scene_line(unnamed).startswith(f"[판정 없음] {MEDIA_PUBLIC_ID} · 1화 · ")


def test_local_scene_line_formats_title_episode_and_timecode(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(search_module, "create_structured_response", _forbidden_ai)
    settings = _settings(tmp_path)
    client = FakeNadeshiko(_search_response(_segment_dict("segment-a", "あの、大丈夫ですか？")))

    with SceneCollectorDatabase.open(settings) as database:
        store_media(database, NADESHIKO_MEDIA)
        index_local_subtitles(database, "테스트 작품", _subtitle_dir(tmp_path))
        (relation,) = _seed_relations(database, "괜찮냐고 묻는 말", "大丈夫ですか")
        found = search_relation(settings, database, relation, nadeshiko_client=client)

    assert [scene.japanese_text for scene in found.local_segments] == ["（ミサ）大丈夫ですか？"]
    assert format_timecode(found.local_segments[0].start_time_ms) == "00:00:01.000"
    assert local_scene_line(found.local_segments[0]) == (
        "테스트 작품 · 1화 · 00:00:01.000 ~ 00:00:02.500 · （ミサ）大丈夫ですか？"
    )
