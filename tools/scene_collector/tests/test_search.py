import copy
import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from nadeshiko.models import SearchFilters, SearchQuery, SearchResponse, Token

import scene_collector.search as search_module
from scene_collector.config import (
    AISettings,
    AppSettings,
    SearchSettings,
    StorageSettings,
)
from scene_collector.database import SceneCollectorDatabase, StoredMeaningExpression
from scene_collector.models import ExpressionCandidate, GeneratedExpressions
from scene_collector.search import (
    NoActiveMediaError,
    find_saved_expressions,
    generate_expressions,
    search_selected_expression,
)
from scene_collector.subtitles import SubtitleCue

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "nadeshiko_search_response.json"

KOREAN_MEANING = "다친 사람에게 괜찮냐고 물어보는 말"


def _settings(
    tmp_path: Path,
    *,
    generation_limit: int = 20,
    nadeshiko_take: int = 2,
) -> AppSettings:
    return AppSettings(
        storage=StorageSettings(work_data_dir=tmp_path),
        ai=AISettings(service="provider-one", model="configured-model"),
        search=SearchSettings(
            expression_generation_limit=generation_limit,
            nadeshiko_take=nadeshiko_take,
        ),
    )


@pytest.fixture
def settings(tmp_path: Path) -> AppSettings:
    return _settings(tmp_path)


@pytest.fixture
def database(settings: AppSettings) -> Iterator[SceneCollectorDatabase]:
    with SceneCollectorDatabase.open(settings) as opened:
        yield opened


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


def _search_response(*texts_ja: str) -> SearchResponse:
    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    payload["pagination"] = {
        "hasMore": False,
        "estimatedTotalHits": len(texts_ja),
        "estimatedTotalHitsRelation": "EXACT",
        "cursor": None,
    }
    segment_template = payload["segments"][0]
    payload["segments"] = []
    for index, text_ja in enumerate(texts_ja, start=1):
        segment = copy.deepcopy(segment_template)
        segment["publicId"] = f"anonymous-segment-{index:03d}"
        segment["position"] = index
        segment["textJa"]["content"] = text_ja
        payload["segments"].append(segment)
    return SearchResponse.from_dict(payload)


class RecordingNadeshiko:
    """검색 호출 인자를 기록하는 가짜 Nadeshiko client."""

    def __init__(self, responses: dict[tuple[str, bool], SearchResponse] | None = None) -> None:
        self.responses = responses or {}
        # (검색어, exact_match, take, media filter에 들어간 작품 ID들)
        self.calls: list[tuple[str, bool, int, tuple[str, ...]]] = []

    def search(
        self,
        *,
        query: SearchQuery,
        take: int,
        filters: SearchFilters | None = None,
    ) -> SearchResponse:
        included: tuple[str, ...] = ()
        if filters is not None:
            included = tuple(item.media_public_id for item in filters.media.include)
        self.calls.append((query.search, bool(query.exact_match), take, included))
        return self.responses.get((query.search, bool(query.exact_match)), _search_response())


def _failing_ai(*args: object, **kwargs: object) -> GeneratedExpressions:
    """이 흐름에서 AI를 호출하면 시험이 실패하게 하는 stub."""
    raise AssertionError("이 흐름에서는 AI를 호출하면 안 됩니다.")


def _failing_nadeshiko_search(*args: object, **kwargs: object) -> SearchResponse:
    """이 흐름에서 Nadeshiko를 호출하면 시험이 실패하게 하는 stub."""
    raise AssertionError("이 흐름에서는 Nadeshiko를 호출하면 안 됩니다.")


class RecordingAI:
    """AI 호출 인자와 횟수를 기록하는 stub."""

    def __init__(self, response: GeneratedExpressions) -> None:
        self.response = response
        self.calls: list[tuple[AppSettings, str, type[GeneratedExpressions]]] = []

    def __call__(
        self,
        settings: AppSettings,
        *,
        prompt: str,
        response_model: type[GeneratedExpressions],
    ) -> GeneratedExpressions:
        self.calls.append((settings, prompt, response_model))
        return self.response


def _add_relation(
    database: SceneCollectorDatabase,
    korean_meaning: str,
    japanese: str,
) -> StoredMeaningExpression:
    """이미 저장돼 있는 의미→표현 관계를 만든다."""
    meaning = database.upsert_meaning(korean_meaning)
    return database.add_meaning_expression(
        meaning.id,
        japanese=japanese,
        reading="よみかた",
        meaning_ko="저장된 뜻",
        register_text="저장된 말투",
    )


def _activate_media(database: SceneCollectorDatabase, *media_ids: str) -> None:
    for media_id in media_ids:
        database.upsert_media(media_id, display_name=f"작품 {media_id}")


def _row_counts(database: SceneCollectorDatabase) -> dict[str, int]:
    """모든 application table의 행 수를 읽는다. 검색이 무엇도 저장하지 않음을 본다."""
    names = [
        row["name"]
        for row in database.connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
    ]
    return {
        name: database.connection.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
        for name in sorted(names)
    }


def test_saved_meaning_lookup_uses_no_ai_and_no_nadeshiko(
    database: SceneCollectorDatabase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(search_module, "create_structured_response", _failing_ai)
    monkeypatch.setattr(search_module, "_search_nadeshiko", _failing_nadeshiko_search)
    _add_relation(database, KOREAN_MEANING, "大丈夫ですか")
    _add_relation(database, KOREAN_MEANING, "平気ですか")

    # 끝의 문장부호만 다른 입력도 같은 저장된 의미로 조회된다.
    saved = find_saved_expressions(database, f"{KOREAN_MEANING}?")

    assert [relation.japanese for relation in saved] == ["大丈夫ですか", "平気ですか"]
    assert [relation.meaning_ko for relation in saved] == ["저장된 뜻", "저장된 뜻"]
    assert [relation.register_text for relation in saved] == ["저장된 말투", "저장된 말투"]
    assert find_saved_expressions(database, "저장한 적 없는 의미") == ()
    with pytest.raises(ValueError, match="한국어"):
        find_saved_expressions(database, "   ")


def test_new_meaning_generates_expressions_with_one_ai_call_and_no_nadeshiko(
    settings: AppSettings,
    database: SceneCollectorDatabase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ai = RecordingAI(_generated("大丈夫ですか", "平気ですか"))
    monkeypatch.setattr(search_module, "create_structured_response", ai)
    monkeypatch.setattr(search_module, "_search_nadeshiko", _failing_nadeshiko_search)

    assert find_saved_expressions(database, KOREAN_MEANING) == ()

    added = generate_expressions(settings, KOREAN_MEANING, database=database)

    assert len(ai.calls) == 1
    called_settings, prompt, response_model = ai.calls[0]
    assert called_settings is settings
    assert KOREAN_MEANING in prompt
    assert "20개" in prompt
    assert response_model is GeneratedExpressions
    assert [relation.japanese for relation in added] == ["大丈夫ですか", "平気ですか"]
    assert [relation.reading for relation in added] == ["よみかた1", "よみかた2"]
    assert [relation.meaning_ko for relation in added] == ["의미 1", "의미 2"]
    assert [relation.register_text for relation in added] == ["말투 1", "말투 2"]

    saved = find_saved_expressions(database, KOREAN_MEANING)
    assert [relation.id for relation in saved] == [relation.id for relation in added]


def test_generating_more_expressions_sends_known_ones_and_saves_only_new(
    settings: AppSettings,
    database: SceneCollectorDatabase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _add_relation(database, KOREAN_MEANING, "大丈夫ですか")
    _add_relation(database, KOREAN_MEANING, "平気ですか")
    ai = RecordingAI(_generated("大丈夫ですか", "無事ですか", "平気ですか", "けがない"))
    monkeypatch.setattr(search_module, "create_structured_response", ai)
    monkeypatch.setattr(search_module, "_search_nadeshiko", _failing_nadeshiko_search)

    added = generate_expressions(settings, KOREAN_MEANING, database=database)

    prompt = ai.calls[0][1]
    assert "大丈夫ですか" in prompt
    assert "平気ですか" in prompt
    assert [relation.japanese for relation in added] == ["無事ですか", "けがない"]
    assert [relation.japanese for relation in find_saved_expressions(database, KOREAN_MEANING)] == [
        "大丈夫ですか",
        "平気ですか",
        "無事ですか",
        "けがない",
    ]
    counts = _row_counts(database)
    assert counts["meaning_expressions"] == 4
    assert counts["expressions"] == 4
    assert counts["meanings"] == 1


def test_generation_stops_at_the_configured_limit(
    tmp_path: Path,
    database: SceneCollectorDatabase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    limited = _settings(tmp_path, generation_limit=3)
    ai = RecordingAI(_generated("表現一", "表現二", "表現三", "表現四", "表現五"))
    monkeypatch.setattr(search_module, "create_structured_response", ai)
    monkeypatch.setattr(search_module, "_search_nadeshiko", _failing_nadeshiko_search)

    added = generate_expressions(limited, KOREAN_MEANING, database=database)

    assert "3개" in ai.calls[0][1]
    assert [relation.japanese for relation in added] == ["表現一", "表現二", "表現三"]
    assert [relation.japanese for relation in find_saved_expressions(database, KOREAN_MEANING)] == [
        "表現一",
        "表現二",
        "表現三",
    ]


def test_empty_ai_expression_list_is_not_an_error_and_changes_nothing(
    settings: AppSettings,
    database: SceneCollectorDatabase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AI가 빈 목록을 돌려줘도 오류 없이 ()를 반환하고 저장된 표현을 건드리지 않는다."""
    first = _add_relation(database, KOREAN_MEANING, "大丈夫ですか")
    second = _add_relation(database, KOREAN_MEANING, "平気ですか")
    ai = RecordingAI(_generated())
    monkeypatch.setattr(search_module, "create_structured_response", ai)
    monkeypatch.setattr(search_module, "_search_nadeshiko", _failing_nadeshiko_search)
    before = _row_counts(database)

    added = generate_expressions(settings, KOREAN_MEANING, database=database)

    assert added == ()
    assert len(ai.calls) == 1
    # 행 수도 내용도 그대로다.
    assert _row_counts(database) == before
    assert list(find_saved_expressions(database, KOREAN_MEANING)) == [first, second]


def test_empty_ai_expression_list_for_a_new_meaning_saves_only_the_meaning(
    settings: AppSettings,
    database: SceneCollectorDatabase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """저장된 표현이 없던 의미에서 빈 목록이 오면 의미만 남고 관계는 0행이다."""
    ai = RecordingAI(_generated())
    monkeypatch.setattr(search_module, "create_structured_response", ai)
    monkeypatch.setattr(search_module, "_search_nadeshiko", _failing_nadeshiko_search)

    added = generate_expressions(settings, KOREAN_MEANING, database=database)

    assert added == ()
    counts = _row_counts(database)
    assert counts["meanings"] == 1
    assert counts["meaning_expressions"] == 0
    assert counts["expressions"] == 0
    assert find_saved_expressions(database, KOREAN_MEANING) == ()


def test_all_duplicate_expressions_add_nothing(
    settings: AppSettings,
    database: SceneCollectorDatabase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AI가 돌려준 표현이 전부 기존 표현이면 새로 저장하지 않는다."""
    first = _add_relation(database, KOREAN_MEANING, "大丈夫ですか")
    second = _add_relation(database, KOREAN_MEANING, "平気ですか")
    ai = RecordingAI(_generated("平気ですか", "大丈夫ですか"))
    monkeypatch.setattr(search_module, "create_structured_response", ai)
    monkeypatch.setattr(search_module, "_search_nadeshiko", _failing_nadeshiko_search)
    before = _row_counts(database)

    added = generate_expressions(settings, KOREAN_MEANING, database=database)

    assert added == ()
    assert _row_counts(database) == before
    assert list(find_saved_expressions(database, KOREAN_MEANING)) == [first, second]


def test_expression_prompt_allows_an_empty_list(
    settings: AppSettings,
    database: SceneCollectorDatabase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """빈 목록을 그대로 반환해도 된다는 지시가 프롬프트에 들어간다."""
    ai = RecordingAI(_generated("大丈夫ですか"))
    monkeypatch.setattr(search_module, "create_structured_response", ai)
    monkeypatch.setattr(search_module, "_search_nadeshiko", _failing_nadeshiko_search)

    generate_expressions(settings, KOREAN_MEANING, database=database)
    # 이미 저장된 표현이 있는 두 번째 호출에서도 같은 지시가 남아 있어야 한다.
    generate_expressions(settings, KOREAN_MEANING, database=database)

    assert len(ai.calls) == 2
    for _, prompt, _ in ai.calls:
        assert "빈 목록" in prompt
        assert "빈 목록을 그대로 반환" in prompt


def test_selected_expression_search_calls_nadeshiko_only_for_that_expression(
    settings: AppSettings,
    database: SceneCollectorDatabase,
) -> None:
    selected = _add_relation(database, KOREAN_MEANING, "悪い")
    _add_relation(database, KOREAN_MEANING, "ごめん")  # 사용자가 고르지 않은 표현
    _activate_media(database, "anonymous-media-002", "anonymous-media-001")
    _activate_media(database, "anonymous-media-003")
    database.set_media_active("anonymous-media-003", False)

    response = _search_response("悪い、遅れた", "気持ち悪い", "悪いと思う")
    # 형태소 경계가 오면 뒤에 말이 붙어도 같은 표현으로 인정한다.
    response.segments[2].text_ja.tokens = [
        Token(s="悪い", d="悪い", r="ワルイ", b=0, e=2, p="形容詞"),
        Token(s="と", d="と", r="ト", b=2, e=3, p="助詞"),
        Token(s="思う", d="思う", r="オモウ", b=3, e=5, p="動詞"),
    ]
    client = RecordingNadeshiko({("悪い", False): response})

    result = search_selected_expression(
        settings,
        selected,
        nadeshiko_client=client,
        database=database,
    )

    # 선택한 표현 하나로만, 활성 작품 필터를 달아 한 번 호출한다.
    assert client.calls == [
        ("悪い", False, 2, ("anonymous-media-001", "anonymous-media-002")),
    ]
    assert result.relation is selected
    # 「気持ち悪い」는 표면형 판정에서 걸러지는 거짓 양성이다.
    assert [segment.text_ja.content for segment in result.nadeshiko_segments] == [
        "悪い、遅れた",
        "悪いと思う",
    ]
    assert result.local_segments == ()
    assert result.has_results is True


def test_selected_expression_search_retries_once_with_exact_match(
    settings: AppSettings,
    database: SceneCollectorDatabase,
) -> None:
    relation = _add_relation(database, "다시 말해 달라고 하는 말", "もう一回言って")
    _activate_media(database, "anonymous-media-001")
    client = RecordingNadeshiko(
        {
            # 첫 검색 결과는 표면형 판정을 모두 통과하지 못한다.
            ("もう一回言って", False): _search_response("もう一回言ってください"),
            ("もう一回言って", True): _search_response("もう一回 言って。"),
        }
    )

    result = search_selected_expression(
        settings,
        relation,
        nadeshiko_client=client,
        database=database,
    )

    assert client.calls == [
        ("もう一回言って", False, 2, ("anonymous-media-001",)),
        ("もう一回言って", True, 2, ("anonymous-media-001",)),
    ]
    assert [segment.text_ja.content for segment in result.nadeshiko_segments] == ["もう一回 言って。"]


def test_selected_expression_search_stores_nothing(
    settings: AppSettings,
    database: SceneCollectorDatabase,
) -> None:
    relation = _add_relation(database, KOREAN_MEANING, "大丈夫ですか")
    _activate_media(database, "anonymous-media-001")
    client = RecordingNadeshiko(
        {("大丈夫ですか", False): _search_response("あの、大丈夫ですか？")}
    )
    before = _row_counts(database)

    result = search_selected_expression(
        settings,
        relation,
        nadeshiko_client=client,
        database=database,
    )

    assert [segment.text_ja.content for segment in result.nadeshiko_segments] == [
        "あの、大丈夫ですか？"
    ]
    assert _row_counts(database) == before
    assert before["work_scenes"] == 0


def test_searching_the_same_expression_again_calls_nadeshiko_again(
    settings: AppSettings,
    database: SceneCollectorDatabase,
) -> None:
    relation = _add_relation(database, KOREAN_MEANING, "大丈夫ですか")
    _activate_media(database, "anonymous-media-001")
    client = RecordingNadeshiko(
        {("大丈夫ですか", False): _search_response("あの、大丈夫ですか？")}
    )

    first = search_selected_expression(
        settings, relation, nadeshiko_client=client, database=database
    )
    second = search_selected_expression(
        settings, relation, nadeshiko_client=client, database=database
    )

    # 검색 결과를 캐시하지 않으므로 같은 표현이라도 다시 호출한다.
    assert len(client.calls) == 2
    assert client.calls[0] == client.calls[1]
    assert [segment.text_ja.content for segment in second.nadeshiko_segments] == [
        segment.text_ja.content for segment in first.nadeshiko_segments
    ]


def test_search_without_active_media_raises_before_calling_nadeshiko(
    settings: AppSettings,
    database: SceneCollectorDatabase,
) -> None:
    relation = _add_relation(database, KOREAN_MEANING, "大丈夫ですか")
    _activate_media(database, "anonymous-media-001")
    database.set_media_active("anonymous-media-001", False)
    client = RecordingNadeshiko()

    with pytest.raises(NoActiveMediaError, match="활성 선호 작품"):
        search_selected_expression(
            settings,
            relation,
            nadeshiko_client=client,
            database=database,
        )

    assert client.calls == []


def test_local_subtitle_matches_come_back_separately_from_nadeshiko_segments(
    settings: AppSettings,
    database: SceneCollectorDatabase,
) -> None:
    relation = _add_relation(database, KOREAN_MEANING, "大丈夫ですか")
    _activate_media(database, "anonymous-media-001")
    local_media = database.register_local_media("로컬 자막 작품")
    database.replace_local_segments(
        local_media.id,
        [
            SubtitleCue(
                episode=1,
                position=0,
                start_time_ms=1000,
                end_time_ms=2500,
                japanese_text="（ミサ）大丈夫ですか？",
                source_file="ep01.srt",
            ),
            # LIKE 후보에는 들어오지만 표면형 판정에서 걸러진다.
            SubtitleCue(
                episode=1,
                position=1,
                start_time_ms=3000,
                end_time_ms=4000,
                japanese_text="大丈夫ですかね",
                source_file="ep01.srt",
            ),
            SubtitleCue(
                episode=2,
                position=0,
                start_time_ms=5000,
                end_time_ms=6000,
                japanese_text="気持ち悪いよ",
                source_file="ep02.srt",
            ),
        ],
    )
    client = RecordingNadeshiko(
        {("大丈夫ですか", False): _search_response("あの、大丈夫ですか？")}
    )

    result = search_selected_expression(
        settings,
        relation,
        nadeshiko_client=client,
        database=database,
    )

    assert client.calls == [("大丈夫ですか", False, 2, ("anonymous-media-001",))]
    assert [segment.text_ja.content for segment in result.nadeshiko_segments] == [
        "あの、大丈夫ですか？"
    ]
    assert [match.japanese_text for match in result.local_segments] == ["（ミサ）大丈夫ですか？"]
    assert result.local_segments[0].media_display_name == "로컬 자막 작품"
    assert result.local_segments[0].episode == 1
    assert result.local_segments[0].source_file == "ep01.srt"


def test_local_only_active_media_skips_nadeshiko_entirely(
    settings: AppSettings,
    database: SceneCollectorDatabase,
) -> None:
    relation = _add_relation(database, KOREAN_MEANING, "大丈夫ですか")
    local_media = database.register_local_media("로컬 자막 작품")
    database.replace_local_segments(
        local_media.id,
        [
            SubtitleCue(
                episode=1,
                position=0,
                start_time_ms=1000,
                end_time_ms=2500,
                japanese_text="（ミサ）大丈夫ですか？",
                source_file="ep01.srt",
            )
        ],
    )
    client = RecordingNadeshiko()

    result = search_selected_expression(
        settings,
        relation,
        nadeshiko_client=client,
        database=database,
    )

    assert client.calls == []
    assert result.nadeshiko_segments == ()
    assert [match.japanese_text for match in result.local_segments] == ["（ミサ）大丈夫ですか？"]
    assert result.has_results is True
