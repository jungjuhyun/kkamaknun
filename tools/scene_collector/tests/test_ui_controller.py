import copy
import json
import sqlite3
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
from scene_collector.database import (
    DATABASE_FILENAME,
    DatabaseError,
    LocalSegmentMatch,
    SceneCollectorDatabase,
    StoredMeaningExpression,
)
from scene_collector.media import store_media
from scene_collector.models import ExpressionCandidate, GeneratedExpressions, SceneTranslation
from scene_collector.search import SelectedExpressionScenes
from scene_collector.subtitles import index_local_subtitles
from scene_collector.translate import CONTEXT_TAKE, TRANSLATION_INSTRUCTION_VERSION
from scene_collector.ui_controller import (
    REVIEW_DECISIONS,
    SceneRow,
    SceneWorkState,
    ensure_work_scene,
    format_timecode,
    generate_more_expressions,
    local_scene_line,
    lookup_expressions,
    lookup_or_generate_expressions,
    reset_player,
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


def _local_match() -> LocalSegmentMatch:
    """로컬 자막 참고 결과 한 건. DB 없이 상태 객체만 검증할 때 쓴다."""
    return LocalSegmentMatch(
        id=1,
        media_id=1,
        media_display_name="테스트 작품",
        episode=1,
        position=1,
        start_time_ms=1000,
        end_time_ms=2500,
        japanese_text="（ミサ）大丈夫ですか？",
        source_file="테스트 작품 S1E01.srt",
    )


def _forbidden_ai(*args: object, **kwargs: object) -> object:
    raise AssertionError("이 흐름에서는 AI를 호출하면 안 됩니다.")


def _failing_ai(*args: object, **kwargs: object) -> object:
    raise RuntimeError("AI 번역 실패")


class FakeVideoPlayer:
    """pause/set_source 호출을 순서대로 기록하는 대역. NiceGUI를 쓰지 않는다."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def pause(self) -> None:
        self.calls.append(("pause", ""))

    def set_source(self, source: str) -> object:
        self.calls.append(("set_source", source))
        return self


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


class FailingContextNadeshiko(FakeNadeshiko):
    """검색은 되지만 문맥 조회만 실패하는 대역."""

    def get_segment_context(self, segment_public_id: str, *, take: int) -> SegmentContextResponse:
        self.context_calls.append((segment_public_id, take))
        raise RuntimeError("문맥 조회 실패")


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


def test_lookup_or_generate_expressions_shows_saved_expressions_without_ai(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """저장된 표현이 있으면 [표현 찾기] 한 번에 AI도 Nadeshiko도 부르지 않는다."""
    monkeypatch.setattr(search_module, "create_structured_response", _forbidden_ai)
    settings = _settings(tmp_path)
    client = FakeNadeshiko(_search_response())

    with SceneCollectorDatabase.open(settings) as database:
        saved = _seed_relations(database, "괜찮냐고 묻는 말", "大丈夫ですか", "平気ですか")

        lookup = lookup_or_generate_expressions(settings, database, "괜찮냐고 묻는 말")
        assert lookup.used_ai is False
        assert lookup.added == ()
        assert lookup.screen.has_expressions is True
        assert lookup.screen.korean_meaning == "괜찮냐고 묻는 말"
        # 저장된 표현이 전부 화면에 온다.
        assert lookup.screen.relations == saved

    # 표현 찾기는 Nadeshiko를 쓰지 않는다.
    assert client.search_calls == []
    assert client.context_calls == []


def test_lookup_or_generate_expressions_generates_once_when_nothing_saved(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """저장된 표현이 없으면 같은 동작 안에서 AI를 정확히 한 번만 부른다."""
    # 응답이 하나뿐이라 AI를 두 번 부르면 FakeAI가 실패한다.
    fake_ai = FakeAI(_generated("大丈夫ですか", "平気ですか"))
    monkeypatch.setattr(search_module, "create_structured_response", fake_ai)
    settings = _settings(tmp_path)
    client = FakeNadeshiko(_search_response())

    with SceneCollectorDatabase.open(settings) as database:
        lookup = lookup_or_generate_expressions(settings, database, "괜찮냐고 묻는 말")
        assert fake_ai.call_count == 1
        assert lookup.used_ai is True
        assert [relation.japanese for relation in lookup.added] == ["大丈夫ですか", "平気ですか"]
        assert [relation.japanese for relation in lookup.screen.relations] == [
            "大丈夫ですか",
            "平気ですか",
        ]

        # 만든 표현은 자산으로 저장돼 AI 없이 다시 조회된다.
        assert lookup_expressions(database, "괜찮냐고 묻는 말").relations == lookup.screen.relations

        again = lookup_or_generate_expressions(settings, database, "괜찮냐고 묻는 말")
        assert fake_ai.call_count == 1
        assert again.used_ai is False
        assert again.added == ()
        assert again.screen.relations == lookup.screen.relations

    assert client.search_calls == []
    assert client.context_calls == []


def test_lookup_or_generate_expressions_accepts_empty_ai_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AI가 표현을 하나도 만들지 못해도 오류가 아니고 기존 표현도 그대로다."""
    fake_ai = FakeAI(_generated(), _generated())
    monkeypatch.setattr(search_module, "create_structured_response", fake_ai)
    settings = _settings(tmp_path)
    client = FakeNadeshiko(_search_response())

    with SceneCollectorDatabase.open(settings) as database:
        lookup = lookup_or_generate_expressions(settings, database, " 처음 보는 의미 ")
        assert fake_ai.call_count == 1
        assert lookup.used_ai is True
        assert lookup.added == ()
        assert lookup.screen.has_expressions is False
        assert lookup.screen.relations == ()
        assert lookup.screen.korean_meaning == "처음 보는 의미"
        assert database.find_expressions_for_meaning("처음 보는 의미") == ()

        # 이미 표현이 있는 의미에서 빈 목록이 와도 저장된 표현을 건드리지 않는다.
        saved = _seed_relations(database, "괜찮냐고 묻는 말", "大丈夫ですか")
        screen, added = generate_more_expressions(settings, database, "괜찮냐고 묻는 말")
        assert fake_ai.call_count == 2
        assert added == ()
        assert screen.relations == saved

    assert client.search_calls == []
    assert client.context_calls == []


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


def test_scene_work_state_keeps_nothing_from_the_previous_relation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """다른 의미→표현으로 넘어가면 이전 장면 결과가 하나도 남지 않는다."""
    monkeypatch.setattr(search_module, "create_structured_response", _forbidden_ai)
    settings = _settings(tmp_path)
    client = FakeNadeshiko(
        _search_response(
            _segment_dict("segment-a", "あの、大丈夫ですか？", position=1),
            _segment_dict("segment-b", "大丈夫ですか、先輩。", position=2),
        )
    )

    with SceneCollectorDatabase.open(settings) as database:
        store_media(database, NADESHIKO_MEDIA)
        first, second = _seed_relations(
            database, "괜찮냐고 묻는 말", "大丈夫ですか", "平気ですか"
        )

        state = SceneWorkState()
        # 아직 아무것도 고르지 않은 상태.
        assert state.relation is None
        assert state.found is None
        assert state.rows == ()
        assert state.saved_scenes == ()
        assert state.selected_index is None
        assert state.local_segments == ()
        assert state.selected_row() is None

        state.start_relation(first)
        found = search_relation(settings, database, first, nadeshiko_client=client)
        rows = scene_rows(database, found, MEDIA_NAMES)
        state.show_results(found, rows)
        # 결과를 보여준 직후에는 장면을 고르지 않은 상태다.
        assert state.selected_index is None
        assert state.selected_row() is None
        assert state.found is found
        assert state.rows == rows

        state.selected_index = 1
        assert state.selected_row() is rows[1]
        # 범위를 벗어난 선택은 장면으로 보지 않는다.
        state.selected_index = len(rows)
        assert state.selected_row() is None
        state.selected_index = -1
        assert state.selected_row() is None
        state.selected_index = 0

        save_decision(database, first, rows[0].segment, rows[0].media_display_name, "채택")
        state.saved_scenes = database.list_work_scenes(first.id)
        assert state.saved_scenes

        state.start_relation(second)
        assert state.relation == second
        assert state.found is None
        assert state.rows == ()
        assert state.saved_scenes == ()
        assert state.selected_index is None
        assert state.local_segments == ()
        assert state.selected_row() is None

        # found가 있으면 로컬 자막 참고 결과를 그대로 보여준다.
        reference = SelectedExpressionScenes(
            relation=second,
            nadeshiko_segments=(),
            local_segments=(_local_match(),),
        )
        state.show_results(reference, ())
        assert state.local_segments == reference.local_segments
        # 빈 목록에서는 어떤 번호를 골라도 장면이 없다.
        state.selected_index = 0
        assert state.selected_row() is None

        # clear()는 관계까지 비운다.
        state.clear()
        assert state.relation is None
        assert state.found is None
        assert state.rows == ()
        assert state.saved_scenes == ()
        assert state.selected_index is None


def test_reset_player_stops_and_clears_the_single_player() -> None:
    """플레이어는 하나뿐이므로 교체하지 않고 재생만 멈추고 source를 지운다."""
    player = FakeVideoPlayer()
    same_player = player

    assert reset_player(player) is None
    assert player.calls == [("pause", ""), ("set_source", "")]
    assert same_player is player

    # 여러 번 불러도 같은 플레이어에 같은 동작만 반복한다.
    reset_player(player)
    assert player.calls == [
        ("pause", ""),
        ("set_source", ""),
        ("pause", ""),
        ("set_source", ""),
    ]

    # 아직 플레이어가 없으면 아무 일도 일어나지 않는다.
    assert reset_player(None) is None


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
        assert noted is not None
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


def test_save_notes_never_creates_an_empty_work_scene(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """빈 메모만으로는 작업 장면이 생기지 않는다."""
    monkeypatch.setattr(search_module, "create_structured_response", _forbidden_ai)
    settings = _settings(tmp_path)
    client = FakeNadeshiko(_search_response(_segment_dict("segment-a", "あの、大丈夫ですか？")))

    with SceneCollectorDatabase.open(settings) as database:
        store_media(database, NADESHIKO_MEDIA)
        (relation,) = _seed_relations(database, "괜찮냐고 묻는 말", "大丈夫ですか")
        found = search_relation(settings, database, relation, nadeshiko_client=client)
        row = scene_rows(database, found, MEDIA_NAMES)[0]

        for empty in ("", "   ", None):
            assert (
                save_notes(database, relation, row.segment, row.media_display_name, empty) is None
            )
            assert database.list_work_scenes(relation.id) == ()

        # 실제로 남길 내용이 있을 때만 장면이 생긴다.
        noted = save_notes(database, relation, row.segment, row.media_display_name, " 발음 확인 ")
        assert noted is not None
        assert noted.notes == "발음 확인"
        assert len(database.list_work_scenes(relation.id)) == 1


def test_save_notes_deletes_note_only_work_scene_when_note_is_cleared(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """메모만 있던 장면에서 메모를 비우면 행 자체가 사라진다."""
    monkeypatch.setattr(search_module, "create_structured_response", _forbidden_ai)
    settings = _settings(tmp_path)
    client = FakeNadeshiko(_search_response(_segment_dict("segment-a", "あの、大丈夫ですか？")))

    with SceneCollectorDatabase.open(settings) as database:
        store_media(database, NADESHIKO_MEDIA)
        (relation,) = _seed_relations(database, "괜찮냐고 묻는 말", "大丈夫ですか")
        found = search_relation(settings, database, relation, nadeshiko_client=client)
        row = scene_rows(database, found, MEDIA_NAMES)[0]

        save_notes(database, relation, row.segment, row.media_display_name, "다시 볼 장면")
        assert len(database.list_work_scenes(relation.id)) == 1

        assert save_notes(database, relation, row.segment, row.media_display_name, "  ") is None
        assert database.list_work_scenes(relation.id) == ()
        assert database.get_work_scene(relation.id, "segment-a") is None


def test_save_notes_keeps_work_scene_that_still_has_decision_or_translation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """판정이나 번역이 남아 있으면 메모를 비워도 행과 작업물은 그대로다."""
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
    client = FakeNadeshiko(
        _search_response(
            _segment_dict("segment-a", "あの、大丈夫ですか？", position=1),
            _segment_dict("segment-b", "大丈夫ですか、先輩。", position=2),
        )
    )

    with SceneCollectorDatabase.open(settings) as database:
        store_media(database, NADESHIKO_MEDIA)
        (relation,) = _seed_relations(database, "괜찮냐고 묻는 말", "大丈夫ですか")
        found = search_relation(settings, database, relation, nadeshiko_client=client)
        decided_row, translated_row = scene_rows(database, found, MEDIA_NAMES)

        # 판정이 있는 장면: 메모를 비워도 행과 판정이 남는다.
        save_decision(
            database, relation, decided_row.segment, decided_row.media_display_name, "채택"
        )
        save_notes(database, relation, decided_row.segment, decided_row.media_display_name, "메모")
        cleared = save_notes(
            database, relation, decided_row.segment, decided_row.media_display_name, ""
        )
        # 행이 남으므로 갱신된 작업 장면이 그대로 돌아온다.
        assert cleared is not None
        assert cleared.decision == "채택"
        assert cleared.notes is None
        kept = database.get_work_scene(relation.id, "segment-a")
        assert kept == cleared

        # 번역이 있는 장면: 메모를 비워도 행과 번역이 남는다.
        translate_scene(
            settings,
            database,
            relation,
            translated_row.segment,
            translated_row.media_display_name,
            nadeshiko_client=client,
        )
        save_notes(
            database, relation, translated_row.segment, translated_row.media_display_name, "메모"
        )
        save_notes(
            database,
            relation,
            translated_row.segment,
            translated_row.media_display_name,
            "   ",
        )
        translated = database.get_work_scene(relation.id, "segment-b")
        assert translated is not None
        assert translated.notes is None
        assert translated.decision is None
        assert translated.direct_meaning == "괜찮습니까"
        assert translated.natural_translation == "괜찮으세요?"
        assert translated.scene_usage == "상태 확인"

        assert len(database.list_work_scenes(relation.id)) == 2


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
        assert translated.segment_public_id == "segment-a"
        # 번역 함수는 DB를 모르므로 work_scene ID를 들고 다니지 않는다.
        assert not hasattr(translated, "work_scene_id")

        assert len(database.list_work_scenes(relation.id)) == 1
        stored = database.get_work_scene(relation.id, "segment-a")
        assert stored is not None
        assert stored.direct_meaning == "괜찮습니까"
        assert stored.natural_translation == "괜찮으세요?"
        assert stored.scene_usage == "상태 확인"
        assert stored.translation_ai_service == "provider-one"
        assert stored.translation_ai_model == "model-one"
        assert stored.translation_instruction_version == TRANSLATION_INSTRUCTION_VERSION
        assert stored.translated_at
        # 번역만으로 판정이 생기지는 않는다.
        assert stored.decision is None
        assert stored.notes is None


def test_translate_scene_leaves_no_work_scene_when_context_lookup_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """문맥 조회가 실패하면 AI도 부르지 않고 빈 작업 장면도 남기지 않는다."""
    monkeypatch.setattr(search_module, "create_structured_response", _forbidden_ai)
    monkeypatch.setattr(translate_module, "create_structured_response", _forbidden_ai)
    settings = _settings(tmp_path)
    client = FailingContextNadeshiko(
        _search_response(_segment_dict("segment-a", "あの、大丈夫ですか？"))
    )

    with SceneCollectorDatabase.open(settings) as database:
        store_media(database, NADESHIKO_MEDIA)
        (relation,) = _seed_relations(database, "괜찮냐고 묻는 말", "大丈夫ですか")
        found = search_relation(settings, database, relation, nadeshiko_client=client)
        row = scene_rows(database, found, MEDIA_NAMES)[0]

        with pytest.raises(RuntimeError, match="문맥 조회 실패"):
            translate_scene(
                settings,
                database,
                relation,
                row.segment,
                row.media_display_name,
                nadeshiko_client=client,
            )

        assert client.context_calls == [("segment-a", CONTEXT_TAKE)]
        assert database.list_work_scenes(relation.id) == ()
        assert database.get_work_scene(relation.id, "segment-a") is None


def test_translate_scene_leaves_no_work_scene_when_ai_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AI 번역이 실패하면 문맥까지 갔더라도 작업 장면을 만들지 않는다."""
    monkeypatch.setattr(search_module, "create_structured_response", _forbidden_ai)
    monkeypatch.setattr(translate_module, "create_structured_response", _failing_ai)
    settings = _settings(tmp_path)
    client = FakeNadeshiko(_search_response(_segment_dict("segment-a", "あの、大丈夫ですか？")))

    with SceneCollectorDatabase.open(settings) as database:
        store_media(database, NADESHIKO_MEDIA)
        (relation,) = _seed_relations(database, "괜찮냐고 묻는 말", "大丈夫ですか")
        found = search_relation(settings, database, relation, nadeshiko_client=client)
        row = scene_rows(database, found, MEDIA_NAMES)[0]

        with pytest.raises(RuntimeError, match="AI 번역 실패"):
            translate_scene(
                settings,
                database,
                relation,
                row.segment,
                row.media_display_name,
                nadeshiko_client=client,
            )

        assert client.context_calls == [("segment-a", CONTEXT_TAKE)]
        assert database.list_work_scenes(relation.id) == ()
        assert database.get_work_scene(relation.id, "segment-a") is None


def test_translate_scene_failure_keeps_existing_decision_notes_and_translation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """이미 작업하던 장면이면 번역 실패가 기존 작업물을 건드리지 않는다."""
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

        save_decision(database, relation, row.segment, row.media_display_name, "채택")
        save_notes(database, relation, row.segment, row.media_display_name, "다시 볼 장면")
        translate_scene(
            settings,
            database,
            relation,
            row.segment,
            row.media_display_name,
            nadeshiko_client=client,
        )
        before = database.get_work_scene(relation.id, "segment-a")
        assert before is not None

        monkeypatch.setattr(translate_module, "create_structured_response", _failing_ai)
        with pytest.raises(RuntimeError, match="AI 번역 실패"):
            translate_scene(
                settings,
                database,
                relation,
                row.segment,
                row.media_display_name,
                nadeshiko_client=client,
            )

        after = database.get_work_scene(relation.id, "segment-a")
        assert after is not None
        assert after.id == before.id
        assert after.decision == "채택"
        assert after.notes == "다시 볼 장면"
        assert after.direct_meaning == "괜찮습니까"
        assert after.natural_translation == "괜찮으세요?"
        assert after.scene_usage == "상태 확인"
        assert len(database.list_work_scenes(relation.id)) == 1


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


# ----------------------------------------------------------------------
# 저장이 실패했을 때 빈 작업 장면을 남기지 않는다
# ----------------------------------------------------------------------


def _prepare_scene(
    database: SceneCollectorDatabase,
    settings: AppSettings,
    client: "FakeNadeshiko",
) -> tuple[StoredMeaningExpression, SceneRow]:
    """작업할 관계 하나와 그 관계에서 찾은 장면 한 줄을 준비한다."""
    store_media(database, NADESHIKO_MEDIA)
    (relation,) = _seed_relations(database, "괜찮냐고 묻는 말", "大丈夫ですか")
    found = search_relation(settings, database, relation, nadeshiko_client=client)
    return relation, scene_rows(database, found, MEDIA_NAMES)[0]


def test_save_decision_rejects_unknown_decision_before_creating_anything(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """판정값이 잘못되면 작업 장면을 만들기 전에 거절한다."""
    monkeypatch.setattr(search_module, "create_structured_response", _forbidden_ai)
    settings = _settings(tmp_path)
    client = FakeNadeshiko(_search_response(_segment_dict("segment-a", "あの、大丈夫ですか？")))

    with SceneCollectorDatabase.open(settings) as database:
        relation, row = _prepare_scene(database, settings, client)

        with pytest.raises(ValueError):
            save_decision(database, relation, row.segment, row.media_display_name, "보류")

        assert database.list_work_scenes(relation.id) == ()


def test_failed_decision_save_leaves_no_empty_work_scene(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """판정 저장이 실패하면 방금 만든 빈 장면을 되돌린다.

    장면 스냅샷과 판정은 서로 다른 transaction이라, 뒤쪽만 실패하면 아무 작업도
    없는 행이 남을 수 있다.
    """
    monkeypatch.setattr(search_module, "create_structured_response", _forbidden_ai)
    settings = _settings(tmp_path)
    client = FakeNadeshiko(_search_response(_segment_dict("segment-a", "あの、大丈夫ですか？")))

    with SceneCollectorDatabase.open(settings) as database:
        relation, row = _prepare_scene(database, settings, client)

        def failing_decision(work_scene_id: int, decision: str, **kwargs: object) -> None:
            raise RuntimeError("판정을 쓰지 못했습니다")

        monkeypatch.setattr(database, "set_work_scene_decision", failing_decision)
        with pytest.raises(RuntimeError):
            save_decision(database, relation, row.segment, row.media_display_name, "채택")

        assert database.list_work_scenes(relation.id) == ()


def test_failed_translation_save_leaves_no_empty_work_scene(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """번역을 만든 뒤 저장이 실패해도 빈 장면이 남지 않는다."""
    monkeypatch.setattr(search_module, "create_structured_response", _forbidden_ai)
    monkeypatch.setattr(
        translate_module,
        "create_structured_response",
        FakeAI(
            SceneTranslation(
                direct_meaning="괜찮습니까",
                natural_translation="괜찮으세요?",
                scene_usage="상태 확인",
            )
        ),
    )
    settings = _settings(tmp_path)
    client = FakeNadeshiko(_search_response(_segment_dict("segment-a", "あの、大丈夫ですか？")))

    with SceneCollectorDatabase.open(settings) as database:
        relation, row = _prepare_scene(database, settings, client)

        def failing_translation(work_scene_id: int, **kwargs: object) -> None:
            raise RuntimeError("번역을 쓰지 못했습니다")

        monkeypatch.setattr(database, "save_work_scene_translation", failing_translation)
        with pytest.raises(RuntimeError):
            translate_scene(
                settings,
                database,
                relation,
                row.segment,
                row.media_display_name,
                nadeshiko_client=client,
            )

        assert database.list_work_scenes(relation.id) == ()


def test_failed_save_keeps_an_already_worked_scene_untouched(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """이미 작업한 장면이면 저장 실패가 기존 판정·메모를 지우지 않는다."""
    monkeypatch.setattr(search_module, "create_structured_response", _forbidden_ai)
    settings = _settings(tmp_path)
    client = FakeNadeshiko(_search_response(_segment_dict("segment-a", "あの、大丈夫ですか？")))

    with SceneCollectorDatabase.open(settings) as database:
        relation, row = _prepare_scene(database, settings, client)
        save_decision(database, relation, row.segment, row.media_display_name, "채택")
        save_notes(database, relation, row.segment, row.media_display_name, "도입부 후보")

        def failing_decision(work_scene_id: int, decision: str, **kwargs: object) -> None:
            raise RuntimeError("판정을 쓰지 못했습니다")

        monkeypatch.setattr(database, "set_work_scene_decision", failing_decision)
        with pytest.raises(RuntimeError):
            save_decision(database, relation, row.segment, row.media_display_name, "제외")

        stored = database.get_work_scene(relation.id, "segment-a")
        assert stored is not None
        assert stored.decision == "채택"
        assert stored.notes == "도입부 후보"


def test_invisible_only_note_is_treated_as_no_note(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """폭 없는 문자만 있는 메모는 화면에서 비어 보이므로 작업으로 세지 않는다."""
    monkeypatch.setattr(search_module, "create_structured_response", _forbidden_ai)
    settings = _settings(tmp_path)
    client = FakeNadeshiko(_search_response(_segment_dict("segment-a", "あの、大丈夫ですか？")))

    with SceneCollectorDatabase.open(settings) as database:
        relation, row = _prepare_scene(database, settings, client)

        for blank in ("\u200b", "\ufeff", "\u3000", "\u00a0", " \u200b \t"):
            assert (
                save_notes(database, relation, row.segment, row.media_display_name, blank)
                is None
            )
            assert database.list_work_scenes(relation.id) == ()

        # 실제 글자가 섞여 있으면 정상 메모이고, 앞뒤의 보이지 않는 문자만 정리한다.
        saved = save_notes(
            database, relation, row.segment, row.media_display_name, "\u200b 도입부 후보 "
        )
        assert saved is not None and saved.notes == "도입부 후보"


# ----------------------------------------------------------------------
# 늦게 도착한 조회 결과가 새 화면을 덮지 않는다
# ----------------------------------------------------------------------


def test_scene_work_state_invalidates_results_from_a_replaced_relation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """표현을 바꾸면 앞서 시작한 조회의 표가 더 이상 현재가 아니게 된다."""
    monkeypatch.setattr(search_module, "create_structured_response", _forbidden_ai)
    settings = _settings(tmp_path)
    client = FakeNadeshiko(_search_response(_segment_dict("segment-a", "あの、大丈夫ですか？")))

    with SceneCollectorDatabase.open(settings) as database:
        store_media(database, NADESHIKO_MEDIA)
        first, second = _seed_relations(
            database, "괜찮냐고 묻는 말", "大丈夫ですか", "平気ですか"
        )
        found = search_relation(settings, database, first, nadeshiko_client=client)
        rows = scene_rows(database, found, MEDIA_NAMES)

    state = SceneWorkState()
    first_token = state.start_relation(first)
    assert state.is_current(first_token)

    # 첫 조회가 끝나기 전에 사용자가 다른 표현을 골랐다.
    second_token = state.start_relation(second)
    assert second_token != first_token
    assert state.is_current(second_token)
    assert not state.is_current(first_token)

    # 늦게 도착한 첫 조회 결과는 버려야 한다.
    if state.is_current(first_token):  # pragma: no cover - 위 단언이 막는다
        state.show_results(found, rows)
    assert state.relation is second
    assert state.found is None
    assert state.rows == ()

    # 화면을 통째로 비우는 것도 진행 중이던 조회를 무효로 만든다.
    state.clear()
    assert not state.is_current(second_token)


def test_locked_database_during_save_leaves_no_work_scene(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """저장 도중 DB가 잠겨 실패해도 빈 작업 장면이 남지 않는다.

    장면 스냅샷과 판정·메모는 한 transaction에서 함께 쓰므로, 쓰기가 막히면
    아무것도 저장되지 않는다.
    """
    monkeypatch.setattr(search_module, "create_structured_response", _forbidden_ai)
    settings = _settings(tmp_path)
    client = FakeNadeshiko(_search_response(_segment_dict("segment-a", "あの、大丈夫ですか？")))

    with SceneCollectorDatabase.open(settings) as database:
        relation, row = _prepare_scene(database, settings, client)

        blocker = sqlite3.connect(tmp_path / DATABASE_FILENAME, timeout=0.1)
        try:
            # 다른 연결이 쓰기 잠금을 쥔 채로 저장을 시도한다.
            blocker.execute("BEGIN IMMEDIATE")
            blocker.execute("UPDATE meanings SET display_korean_meaning = 'x' WHERE id = 1")

            with pytest.raises(DatabaseError):
                save_decision(database, relation, row.segment, row.media_display_name, "채택")
            assert database.list_work_scenes(relation.id) == ()

            with pytest.raises(DatabaseError):
                save_notes(database, relation, row.segment, row.media_display_name, "메모")
            assert database.list_work_scenes(relation.id) == ()
        finally:
            blocker.rollback()
            blocker.close()

        # 잠금이 풀리면 정상적으로 저장된다.
        saved = save_decision(database, relation, row.segment, row.media_display_name, "채택")
        assert saved.decision == "채택"
