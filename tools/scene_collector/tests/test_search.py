import copy
import hashlib
import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from nadeshiko.models import SearchFilters, SearchQuery, SearchResponse, Token

import scene_collector.search as search_module
import scene_collector.ui_controller as ui_controller
from conftest import FakeSearchStats
from scene_collector.config import (
    AISettings,
    AppSettings,
    SearchSettings,
    StorageSettings,
)
from scene_collector.database import SceneCollectorDatabase, StoredMeaningExpression
from scene_collector.models import ExpressionCandidate, GeneratedExpressions
from scene_collector.search import (
    SEARCH_PAGE_TAKE,
    NoActiveMediaError,
    SearchPaginationError,
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
) -> AppSettings:
    return AppSettings(
        storage=StorageSettings(work_data_dir=tmp_path),
        ai=AISettings(service="provider-one", model="configured-model"),
        search=SearchSettings(expression_generation_limit=generation_limit),
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


def _search_response(*texts_ja: str, cursor: str | None = None) -> SearchResponse:
    """검색 응답 한 페이지. cursor를 주면 다음 페이지가 있는 응답이 된다.

    장면 ID는 대사에서 만든다. 실제 API에서 공개 ID는 장면을 유일하게
    가리키므로, 서로 다른 대사가 같은 ID를 갖는 응답을 흉내 내면 중복 제거
    시험이 실제와 달라진다.
    """
    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    payload["pagination"] = {
        "hasMore": cursor is not None,
        "estimatedTotalHits": len(texts_ja),
        "estimatedTotalHitsRelation": "EXACT",
        "cursor": cursor,
    }
    segment_template = payload["segments"][0]
    payload["segments"] = []
    for index, text_ja in enumerate(texts_ja, start=1):
        segment = copy.deepcopy(segment_template)
        digest = hashlib.sha1(text_ja.encode("utf-8")).hexdigest()[:8]
        segment["publicId"] = f"anonymous-segment-{digest}"
        segment["position"] = index
        segment["textJa"]["content"] = text_ja
        payload["segments"].append(segment)
    return SearchResponse.from_dict(payload)


class RecordingNadeshiko(FakeSearchStats):
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
        sort: object = None,
    ) -> SearchResponse:
        included: tuple[str, ...] = ()
        if filters is not None:
            included = tuple(item.media_public_id for item in filters.media.include)
        self.calls.append((query.search, bool(query.exact_match), take, included))
        return self.responses.get((query.search, bool(query.exact_match)), _search_response())


class PagingNadeshiko(FakeSearchStats):
    """(검색어, exact_match, cursor)마다 다른 페이지를 돌려주는 가짜 client.

    등록하지 않은 페이지를 요청하면 실패한다. "이 페이지는 요청하면 안 된다"를
    시험에서 그대로 표현하기 위해서다.
    """

    def __init__(self, pages: dict[tuple[str, bool, str | None], SearchResponse]) -> None:
        self.pages = pages
        # (검색어, exact_match, take, 작품 ID들, cursor)
        self.calls: list[tuple[str, bool, int, tuple[str, ...], str | None]] = []

    def search(
        self,
        *,
        query: SearchQuery,
        take: int,
        filters: SearchFilters | None = None,
        cursor: str | None = None,
        sort: object = None,
    ) -> SearchResponse:
        included: tuple[str, ...] = ()
        if filters is not None:
            included = tuple(item.media_public_id for item in filters.media.include)
        self.calls.append((query.search, bool(query.exact_match), take, included, cursor))
        key = (query.search, bool(query.exact_match), cursor)
        if key not in self.pages:
            raise AssertionError(f"요청하지 않아야 할 페이지를 요청했습니다: {key}")
        return self.pages[key]


class RepeatingCursorNadeshiko(FakeSearchStats):
    """같은 cursor를 계속 돌려주는 비정상 client. 순환 안전장치 시험용이다."""

    def __init__(self, *texts_ja: str) -> None:
        self.texts_ja = texts_ja
        self.calls: list[tuple[str, bool, str | None]] = []

    def search(
        self,
        *,
        query: SearchQuery,
        take: int,
        filters: SearchFilters | None = None,
        cursor: str | None = None,
        sort: object = None,
    ) -> SearchResponse:
        self.calls.append((query.search, bool(query.exact_match), cursor))
        return _search_response(*self.texts_ja, cursor="stuck-page")


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


def test_empty_ai_expression_list_for_a_new_meaning_writes_nothing(
    settings: AppSettings,
    database: SceneCollectorDatabase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """처음 보는 의미에서 빈 목록이 오면 의미 행조차 남기지 않는다.

    찾아본 시도 자체는 작업물이 아니므로 DB에 기록하지 않는다.
    """
    ai = RecordingAI(_generated())
    monkeypatch.setattr(search_module, "create_structured_response", ai)
    monkeypatch.setattr(search_module, "_search_nadeshiko", _failing_nadeshiko_search)
    before = _row_counts(database)

    added = generate_expressions(settings, KOREAN_MEANING, database=database)

    assert added == ()
    assert len(ai.calls) == 1
    counts = _row_counts(database)
    assert counts["meanings"] == 0
    assert counts["expressions"] == 0
    assert counts["meaning_expressions"] == 0
    assert counts == before
    assert database.find_meaning(KOREAN_MEANING) is None
    assert find_saved_expressions(database, KOREAN_MEANING) == ()


def test_ai_failure_for_a_new_meaning_writes_nothing(
    settings: AppSettings,
    database: SceneCollectorDatabase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """처음 보는 의미에서 AI가 실패하면 DB에 아무 변화도 남지 않는다."""

    def failing_ai(*args: object, **kwargs: object) -> object:
        raise RuntimeError("AI 응답을 받지 못했습니다")

    monkeypatch.setattr(search_module, "create_structured_response", failing_ai)
    monkeypatch.setattr(search_module, "_search_nadeshiko", _failing_nadeshiko_search)
    before = _row_counts(database)

    with pytest.raises(RuntimeError):
        generate_expressions(settings, KOREAN_MEANING, database=database)

    counts = _row_counts(database)
    assert counts["meanings"] == 0
    assert counts["expressions"] == 0
    assert counts["meaning_expressions"] == 0
    assert counts == before
    assert database.find_meaning(KOREAN_MEANING) is None


def test_ai_failure_for_a_saved_meaning_keeps_existing_assets(
    settings: AppSettings,
    database: SceneCollectorDatabase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """이미 저장된 의미에서 AI가 실패해도 기존 표현 자산은 그대로다."""
    first = _add_relation(database, KOREAN_MEANING, "大丈夫ですか")
    second = _add_relation(database, KOREAN_MEANING, "平気ですか")

    def failing_ai(*args: object, **kwargs: object) -> object:
        raise RuntimeError("AI 응답을 받지 못했습니다")

    monkeypatch.setattr(search_module, "create_structured_response", failing_ai)
    monkeypatch.setattr(search_module, "_search_nadeshiko", _failing_nadeshiko_search)
    before = _row_counts(database)

    with pytest.raises(RuntimeError):
        generate_expressions(settings, KOREAN_MEANING, database=database)

    assert _row_counts(database) == before
    assert list(find_saved_expressions(database, KOREAN_MEANING)) == [first, second]


def test_meaning_row_appears_only_when_a_new_expression_is_saved(
    settings: AppSettings,
    database: SceneCollectorDatabase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """빈 결과로 아무것도 남지 않은 뒤, 실제 표현이 오면 그때 의미가 저장된다."""
    empty_ai = RecordingAI(_generated())
    monkeypatch.setattr(search_module, "create_structured_response", empty_ai)
    monkeypatch.setattr(search_module, "_search_nadeshiko", _failing_nadeshiko_search)

    assert generate_expressions(settings, KOREAN_MEANING, database=database) == ()
    assert _row_counts(database)["meanings"] == 0

    monkeypatch.setattr(
        search_module, "create_structured_response", RecordingAI(_generated("大丈夫ですか"))
    )
    added = generate_expressions(settings, KOREAN_MEANING, database=database)

    assert [relation.japanese for relation in added] == ["大丈夫ですか"]
    counts = _row_counts(database)
    assert counts["meanings"] == 1
    assert counts["expressions"] == 1
    assert counts["meaning_expressions"] == 1
    stored = database.find_meaning(KOREAN_MEANING)
    assert stored is not None and stored.display_korean_meaning == KOREAN_MEANING


def test_punctuation_only_meaning_is_rejected_before_calling_ai(
    settings: AppSettings,
    database: SceneCollectorDatabase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """정규화하면 아무 글자도 남지 않는 입력은 AI를 부르기 전에 거절한다."""
    ai = RecordingAI(_generated("大丈夫ですか"))
    monkeypatch.setattr(search_module, "create_structured_response", ai)
    monkeypatch.setattr(search_module, "_search_nadeshiko", _failing_nadeshiko_search)

    with pytest.raises(ValueError):
        generate_expressions(settings, "???", database=database)

    assert ai.calls == []
    assert _row_counts(database)["meanings"] == 0


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
    # 두 검색 경로를 모두 돌고, 비활성 작품은 어느 쪽에도 들어가지 않는다.
    assert client.calls == [
        ("悪い", False, SEARCH_PAGE_TAKE, ("anonymous-media-001", "anonymous-media-002")),
        ("悪い", True, SEARCH_PAGE_TAKE, ("anonymous-media-001", "anonymous-media-002")),
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
        ("もう一回言って", False, SEARCH_PAGE_TAKE, ("anonymous-media-001",)),
        ("もう一回言って", True, SEARCH_PAGE_TAKE, ("anonymous-media-001",)),
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
    # 한 번 검색할 때 일반·정확 두 경로를 돌므로 두 번 검색하면 4회다.
    assert len(client.calls) == 4
    # 두 번째 검색이 첫 번째와 같은 요청을 그대로 다시 보낸다.
    assert client.calls[:2] == client.calls[2:]
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

    assert client.calls == [
        ("大丈夫ですか", False, SEARCH_PAGE_TAKE, ("anonymous-media-001",)),
        ("大丈夫ですか", True, SEARCH_PAGE_TAKE, ("anonymous-media-001",)),
    ]
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


# ----------------------------------------------------------------------
# 고른 표현의 정확 동일표현 장면을 빠짐없이 수집한다
#
# 이 도구는 표현 하나를 여러 장면에서 반복해 보여줄 제작 재료를 모은다.
# 그래서 "몇 개 찾았으니 그만"이나 "몇 페이지 봤으니 그만"으로 정상 결과를
# 자르지 않는다.
# ----------------------------------------------------------------------

_ACTIVE_MEDIA = "anonymous-media-001"
_TARGET = "大丈夫です"
# 표면형 판정에서 떨어지는 비슷한 표현들. 흔한 표현의 첫 페이지가 이렇게 채워진다.
_NEAR_MISSES = ("大丈夫ですよ", "大丈夫ですか", "本当に大丈夫ですか")


def _page(*texts_ja: str, cursor: str | None = None, first_id: int = 1) -> SearchResponse:
    """장면 ID를 지정할 수 있는 검색 응답 한 페이지."""
    response = _search_response(*texts_ja, cursor=cursor)
    for offset, segment in enumerate(response.segments):
        segment.public_id = f"anonymous-segment-{first_id + offset:03d}"
    return response


def _collect(
    settings: AppSettings,
    database: SceneCollectorDatabase,
    client: object,
) -> tuple[str, ...]:
    """활성 작품 하나로 목표 표현을 검색하고 찾은 장면 ID를 돌려준다."""
    relation = _add_relation(database, KOREAN_MEANING, _TARGET)
    found = search_selected_expression(
        settings, relation, nadeshiko_client=client, database=database
    )
    return tuple(segment.public_id for segment in found.nadeshiko_segments)


def _no_exact_pages(search_text: str) -> dict:
    """정확 검색은 결과가 없는 한 페이지로 끝나게 한다."""
    return {(search_text, True, None): _search_response()}


def test_every_page_of_matches_is_collected(
    tmp_path: Path,
    database: SceneCollectorDatabase,
) -> None:
    """페이지마다 나온 정확 일치를 전부 모은다. 중간에서 멈추지 않는다."""
    _activate_media(database, _ACTIVE_MEDIA)
    pages = {
        (_TARGET, False, None): _page(_TARGET, _TARGET, cursor="p2", first_id=1),
        (_TARGET, False, "p2"): _page(_TARGET, _TARGET, _TARGET, cursor="p3", first_id=11),
        (_TARGET, False, "p3"): _page(_TARGET, _TARGET, _TARGET, _TARGET, first_id=21),
    }
    pages.update(_no_exact_pages(_TARGET))
    client = PagingNadeshiko(pages)

    found = _collect(_settings(tmp_path), database, client)

    # 2 + 3 + 4 = 9건이 전부 남는다. 옛 "5개 제한"이 있으면 여기서 실패한다.
    assert len(found) == 9


def test_pagination_runs_past_any_fixed_page_cap(
    tmp_path: Path,
    database: SceneCollectorDatabase,
) -> None:
    """페이지가 10쪽이 넘어도 has_more가 끝날 때까지 전부 조회한다."""
    _activate_media(database, _ACTIVE_MEDIA)
    page_count = 12
    pages: dict = {}
    for index in range(page_count):
        cursor = None if index == 0 else f"p{index}"
        next_cursor = f"p{index + 1}" if index < page_count - 1 else None
        pages[(_TARGET, False, cursor)] = _page(
            _TARGET, cursor=next_cursor, first_id=index + 1
        )
    pages.update(_no_exact_pages(_TARGET))
    client = PagingNadeshiko(pages)

    found = _collect(_settings(tmp_path), database, client)

    assert len(found) == page_count
    general_calls = [call for call in client.calls if call[1] is False]
    assert len(general_calls) == page_count


def test_a_large_first_page_does_not_stop_the_search(
    tmp_path: Path,
    database: SceneCollectorDatabase,
) -> None:
    """이미 많이 찾았다는 이유로 멈추지 않는다."""
    _activate_media(database, _ACTIVE_MEDIA)
    pages = {
        (_TARGET, False, None): _page(*([_TARGET] * 20), cursor="p2", first_id=1),
        (_TARGET, False, "p2"): _page(_TARGET, first_id=101),
    }
    pages.update(_no_exact_pages(_TARGET))
    client = PagingNadeshiko(pages)

    found = _collect(_settings(tmp_path), database, client)

    assert len(found) == 21
    assert "anonymous-segment-101" in found


def test_exact_match_search_runs_even_when_the_general_search_found_scenes(
    tmp_path: Path,
    database: SceneCollectorDatabase,
) -> None:
    """일반 검색에서 이미 여러 건이 나와도 정확 검색을 건너뛰지 않는다.

    두 경로가 같은 결과를 준다는 공식 보장이 없어 합집합으로 회수를 최대화한다.
    """
    _activate_media(database, _ACTIVE_MEDIA)
    client = PagingNadeshiko(
        {
            (_TARGET, False, None): _page(_TARGET, _TARGET, first_id=1),
            (_TARGET, True, None): _page(_TARGET, first_id=50),
        }
    )

    found = _collect(_settings(tmp_path), database, client)

    assert found == (
        "anonymous-segment-001",
        "anonymous-segment-002",
        "anonymous-segment-050",
    )
    assert [call[1] for call in client.calls] == [False, True]


def test_a_scene_found_by_both_paths_is_listed_once(
    tmp_path: Path,
    database: SceneCollectorDatabase,
) -> None:
    """일반 검색과 정확 검색에 같은 장면이 있으면 한 번만 남는다."""
    _activate_media(database, _ACTIVE_MEDIA)
    client = PagingNadeshiko(
        {
            (_TARGET, False, None): _page(_TARGET, _TARGET, first_id=1),
            (_TARGET, True, None): _page(_TARGET, _TARGET, first_id=1),
        }
    )

    found = _collect(_settings(tmp_path), database, client)

    assert found == ("anonymous-segment-001", "anonymous-segment-002")


def test_a_scene_repeated_across_pages_is_listed_once(
    tmp_path: Path,
    database: SceneCollectorDatabase,
) -> None:
    """색인이 갱신되는 중이면 같은 장면이 두 페이지에 걸쳐 올 수 있다."""
    _activate_media(database, _ACTIVE_MEDIA)
    pages = {
        (_TARGET, False, None): _page(_TARGET, cursor="p2", first_id=1),
        (_TARGET, False, "p2"): _page(_TARGET, _TARGET, first_id=1),
    }
    pages.update(_no_exact_pages(_TARGET))
    client = PagingNadeshiko(pages)

    found = _collect(_settings(tmp_path), database, client)

    assert found == ("anonymous-segment-001", "anonymous-segment-002")


def test_every_request_keeps_the_active_media_filter(
    tmp_path: Path,
    database: SceneCollectorDatabase,
) -> None:
    """작품 필터는 모든 페이지와 두 검색 경로 전부에 그대로 붙는다."""
    _activate_media(database, _ACTIVE_MEDIA, "anonymous-media-002")
    database.set_media_active("anonymous-media-002", False)
    client = PagingNadeshiko(
        {
            (_TARGET, False, None): _page(*_NEAR_MISSES, cursor="p2"),
            (_TARGET, False, "p2"): _page(_TARGET, first_id=10),
            (_TARGET, True, None): _page(*_NEAR_MISSES, cursor="q2"),
            (_TARGET, True, "q2"): _page(_TARGET, first_id=10),
        }
    )

    _collect(_settings(tmp_path), database, client)

    assert len(client.calls) == 4
    for call in client.calls:
        assert call[3] == (_ACTIVE_MEDIA,)
        assert call[2] == SEARCH_PAGE_TAKE


def test_full_collection_stores_nothing(
    tmp_path: Path,
    database: SceneCollectorDatabase,
) -> None:
    """여러 페이지를 훑어도 검색 결과는 DB에 남지 않는다."""
    _activate_media(database, _ACTIVE_MEDIA)
    pages = {
        (_TARGET, False, None): _page(_TARGET, cursor="p2"),
        (_TARGET, False, "p2"): _page(_TARGET, first_id=10),
    }
    pages.update(_no_exact_pages(_TARGET))
    client = PagingNadeshiko(pages)
    relation = _add_relation(database, KOREAN_MEANING, _TARGET)
    before = _row_counts(database)

    search_selected_expression(
        _settings(tmp_path), relation, nadeshiko_client=client, database=database
    )

    assert _row_counts(database) == before
    assert database.list_work_scenes(relation.id) == ()


def test_a_repeating_cursor_fails_instead_of_looping_forever(
    tmp_path: Path,
    database: SceneCollectorDatabase,
) -> None:
    """같은 자리를 반복해서 주는 응답은 무한히 돌지 않고 명확히 실패한다."""
    _activate_media(database, _ACTIVE_MEDIA)
    client = RepeatingCursorNadeshiko(_TARGET)

    relation = _add_relation(database, KOREAN_MEANING, _TARGET)
    with pytest.raises(SearchPaginationError, match="반복"):
        search_selected_expression(
            _settings(tmp_path), relation, nadeshiko_client=client, database=database
        )


def test_a_missing_cursor_with_more_pages_is_an_error(
    tmp_path: Path,
    database: SceneCollectorDatabase,
) -> None:
    """더 있다면서 cursor를 주지 않으면 부분 결과를 완료로 돌려주지 않는다."""
    _activate_media(database, _ACTIVE_MEDIA)
    broken = _page(_TARGET)
    broken.pagination.has_more = True
    broken.pagination.cursor = None
    client = PagingNadeshiko({(_TARGET, False, None): broken})

    relation = _add_relation(database, KOREAN_MEANING, _TARGET)
    with pytest.raises(SearchPaginationError, match="전체 장면을 확인하지 못했습니다"):
        search_selected_expression(
            _settings(tmp_path), relation, nadeshiko_client=client, database=database
        )


def test_search_settings_no_longer_limit_the_scene_count() -> None:
    """찾은 장면 수를 자르는 설정은 없다."""
    settings = SearchSettings()
    assert not hasattr(settings, "scene_result_limit")
    assert not hasattr(settings, "nadeshiko_take")
    assert set(SearchSettings.model_fields) == {"expression_generation_limit"}


# ----------------------------------------------------------------------
# UAT FIX 4 — 검색 회수 무결성
# ----------------------------------------------------------------------


class OracleNadeshiko(FakeSearchStats):
    """작품별 매칭 수(oracle)와 페이지를 함께 흉내 내는 가짜 client."""

    def __init__(
        self,
        pages: dict[tuple[str, bool, str | None], SearchResponse],
        expected_hits: dict[str, int] | None = None,
        exact_expected_hits: dict[str, int] | None = None,
    ) -> None:
        self.pages = pages
        self.expected_hits = expected_hits
        self.exact_expected_hits = exact_expected_hits
        self.calls: list[tuple[str, bool, str | None, tuple[str, ...], object]] = []
        # 통계도 검색 경로마다 따로 물어야 하므로 어떤 조건으로 물었는지 남긴다.
        self.stats_calls: list[bool] = []

    def get_search_stats(self, *, query=None, **kwargs: object):
        self.stats_calls.append(bool(getattr(query, "exact_match", False)))
        return super().get_search_stats(query=query, **kwargs)

    def search(
        self,
        *,
        query: SearchQuery,
        take: int,
        filters: SearchFilters | None = None,
        cursor: str | None = None,
        sort: object = None,
    ) -> SearchResponse:
        included: tuple[str, ...] = ()
        if filters is not None:
            included = tuple(item.media_public_id for item in filters.media.include)
        self.calls.append((query.search, bool(query.exact_match), cursor, included, sort))
        key = (query.search, bool(query.exact_match), cursor)
        if key not in self.pages:
            raise AssertionError(f"요청하지 않아야 할 페이지를 요청했습니다: {key}")
        return self.pages[key]


def _media_response(
    *pairs: tuple[str, str],
    cursor: str | None = None,
) -> SearchResponse:
    """(작품 ID, 대사) 쌍으로 한 페이지를 만든다."""
    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    payload["pagination"] = {
        "hasMore": cursor is not None,
        "estimatedTotalHits": len(pairs),
        "estimatedTotalHitsRelation": "EXACT",
        "cursor": cursor,
    }
    template = payload["segments"][0]
    payload["segments"] = []
    for index, (media_id, text_ja) in enumerate(pairs, start=1):
        segment = copy.deepcopy(template)
        digest = hashlib.sha1(f"{media_id}{text_ja}".encode("utf-8")).hexdigest()[:8]
        segment["publicId"] = f"seg-{digest}"
        segment["mediaPublicId"] = media_id
        segment["position"] = index
        segment["textJa"]["content"] = text_ja
        payload["segments"].append(segment)
    return SearchResponse.from_dict(payload)


def test_collection_uses_deterministic_time_sort_on_every_page(
    settings: AppSettings,
    database: SceneCollectorDatabase,
) -> None:
    """커서 순회는 화수·위치 기준 결정적 정렬로 모든 페이지에서 같은 구성을 쓴다."""
    relation = _add_relation(database, KOREAN_MEANING, "大丈夫")
    _activate_media(database, "media-a")
    pages = {
        ("大丈夫", False, None): _media_response(
            ("media-a", "大丈夫。"), cursor="page-2"
        ),
        ("大丈夫", False, "page-2"): _media_response(("media-a", "もう大丈夫")),
        ("大丈夫", True, None): _media_response(),
    }
    client = OracleNadeshiko(pages)

    found = search_selected_expression(
        settings, relation, nadeshiko_client=client, database=database
    )

    assert len(found.nadeshiko_segments) == 2
    modes = {call[4].mode for call in client.calls}
    assert modes == {"TIME_ASC"}
    # 커서는 정렬 구성과 짝이 맞아야 하므로 페이지마다 정렬을 바꾸지 않는다.
    assert len({call[4].mode for call in client.calls}) == 1


def test_search_reports_full_coverage_when_oracle_counts_are_met(
    settings: AppSettings,
    database: SceneCollectorDatabase,
) -> None:
    """작품별 매칭 수를 다 받았으면 검증 통과로 보고한다."""
    relation = _add_relation(database, KOREAN_MEANING, "大丈夫")
    _activate_media(database, "media-a", "media-b")
    pages = {
        ("大丈夫", False, None): _media_response(
            ("media-a", "大丈夫。"), ("media-b", "もう大丈夫。"), ("media-b", "大丈夫。 ほんとに")
        ),
        ("大丈夫", True, None): _media_response(),
    }
    client = OracleNadeshiko(
        pages, expected_hits={"media-a": 1, "media-b": 2}, exact_expected_hits={}
    )

    found = search_selected_expression(
        settings, relation, nadeshiko_client=client, database=database
    )

    # 통계는 일반·정확 경로에 각각 물어본다.
    assert client.stats_calls == [False, True]
    assert found.search_fully_checked is True
    assert found.unverified_sources == ()
    assert found.normal_retrieved_hits == 3
    by_media = {item.media_public_id: item for item in found.coverage}
    assert by_media["media-a"].normal.retrieved_hits == 1
    assert by_media["media-b"].normal.retrieved_hits == 2
    assert by_media["media-b"].matched_scenes == 2


def test_search_flags_the_source_it_could_not_fully_retrieve(
    settings: AppSettings,
    database: SceneCollectorDatabase,
) -> None:
    """검색이 매칭했다고 한 수보다 적게 받으면 조용히 완전한 척하지 않는다."""
    relation = _add_relation(database, KOREAN_MEANING, "大丈夫")
    _activate_media(database, "media-a", "media-b")
    pages = {
        ("大丈夫", False, None): _media_response(("media-a", "大丈夫。")),
        ("大丈夫", True, None): _media_response(),
    }
    # media-b는 5건이 매칭된다고 통계가 알려 줬지만 실제로는 하나도 받지 못했다.
    client = OracleNadeshiko(
        pages, expected_hits={"media-a": 1, "media-b": 5}, exact_expected_hits={}
    )

    found = search_selected_expression(
        settings, relation, nadeshiko_client=client, database=database
    )

    assert found.search_fully_checked is False
    unverified = found.unverified_sources
    assert [item.media_public_id for item in unverified] == ["media-b"]
    assert unverified[0].normal.expected_hits == 5
    assert unverified[0].normal.retrieved_hits == 0
    assert unverified[0].normal.verified is False
    line = ui_controller.search_coverage_line(found)
    assert "일부를 받지 못했습니다" in line
    assert "일반 검색 1개 작품" in line
    assert "빠짐없이" not in line


def test_coverage_line_never_claims_every_occurrence(
    settings: AppSettings,
    database: SceneCollectorDatabase,
) -> None:
    """검증에 성공해도 '작품 안의 모든 출현'을 찾았다고 말하지 않는다."""
    relation = _add_relation(database, KOREAN_MEANING, "大丈夫")
    _activate_media(database, "media-a")
    pages = {
        ("大丈夫", False, None): _media_response(("media-a", "大丈夫。")),
        ("大丈夫", True, None): _media_response(),
    }
    client = OracleNadeshiko(pages, expected_hits={"media-a": 1}, exact_expected_hits={})

    found = search_selected_expression(
        settings, relation, nadeshiko_client=client, database=database
    )

    line = ui_controller.search_coverage_line(found)
    assert "빠짐없이 받았습니다" in line
    assert "형태소" in line
    assert "보장하지는 않습니다" in line
    assert "모두 찾았습니다" not in line

    header = ui_controller.scene_count_summary(len(found.nadeshiko_segments), 0)
    assert header.startswith("Nadeshiko 검색에서 확인된")


def test_exact_only_and_general_only_scenes_are_both_kept(
    settings: AppSettings,
    database: SceneCollectorDatabase,
) -> None:
    """일반 검색에만 있는 장면과 정확 검색에만 있는 장면을 모두 남긴다."""
    relation = _add_relation(database, KOREAN_MEANING, "大丈夫")
    _activate_media(database, "media-a")
    shared = ("media-a", "大丈夫。")
    pages = {
        ("大丈夫", False, None): _media_response(shared, ("media-a", "まだ大丈夫")),
        ("大丈夫", True, None): _media_response(shared, ("media-a", "もう大丈夫")),
    }
    client = OracleNadeshiko(
        pages, expected_hits={"media-a": 2}, exact_expected_hits={"media-a": 2}
    )

    found = search_selected_expression(
        settings, relation, nadeshiko_client=client, database=database
    )

    texts = [segment.text_ja.content for segment in found.nadeshiko_segments]
    assert texts == ["大丈夫。", "まだ大丈夫", "もう大丈夫"]
    # 같은 장면이 두 경로에 나와도 한 번만 센다.
    assert len({segment.public_id for segment in found.nadeshiko_segments}) == 3
    assert found.normal_retrieved_hits == 2
    assert found.exact_retrieved_hits == 2


def test_scenes_from_several_media_are_kept_apart_and_deduped(
    settings: AppSettings,
    database: SceneCollectorDatabase,
) -> None:
    """여러 작품이 한 번에 검색돼도 작품별로 집계하고 같은 장면은 한 번만 센다."""
    relation = _add_relation(database, KOREAN_MEANING, "大丈夫")
    _activate_media(database, "media-a", "media-b")
    pages = {
        ("大丈夫", False, None): _media_response(
            ("media-a", "大丈夫。"), ("media-b", "大丈夫。")
        ),
        ("大丈夫", True, None): _media_response(("media-a", "大丈夫。")),
    }
    client = OracleNadeshiko(
        pages,
        expected_hits={"media-a": 1, "media-b": 1},
        exact_expected_hits={"media-a": 1},
    )

    found = search_selected_expression(
        settings, relation, nadeshiko_client=client, database=database
    )

    # 같은 대사라도 작품이 다르면 다른 장면이다.
    assert len(found.nadeshiko_segments) == 2
    by_media = {
        item.media_public_id: item.normal.retrieved_hits for item in found.coverage
    }
    assert by_media == {"media-a": 1, "media-b": 1}


def test_search_still_stores_nothing_and_keeps_no_scene_limit(
    settings: AppSettings,
    database: SceneCollectorDatabase,
) -> None:
    """검증을 붙여도 결과 저장은 없고 장면 수 제한도 생기지 않는다."""
    relation = _add_relation(database, KOREAN_MEANING, "大丈夫")
    _activate_media(database, "media-a")
    many = tuple(("media-a", f"大丈夫。 {index}番目") for index in range(120))
    pages = {
        ("大丈夫", False, None): _media_response(*many[:60], cursor="p2"),
        ("大丈夫", False, "p2"): _media_response(*many[60:]),
        ("大丈夫", True, None): _media_response(),
    }
    client = OracleNadeshiko(
        pages, expected_hits={"media-a": 120}, exact_expected_hits={}
    )
    before = _row_counts(database)

    found = search_selected_expression(
        settings, relation, nadeshiko_client=client, database=database
    )

    assert len(found.nadeshiko_segments) == 120
    assert found.search_fully_checked is True
    assert _row_counts(database) == before


# ----------------------------------------------------------------------
# UAT FIX 4.1 — 경로별 회수 검증 (합친 뒤 세면 누락이 가려진다)
# ----------------------------------------------------------------------


def test_exact_extras_never_cover_a_general_search_shortfall(
    settings: AppSettings,
    database: SceneCollectorDatabase,
) -> None:
    """CASE A — 정확 검색의 추가 장면이 일반 검색의 누락을 메우면 안 된다.

    일반 검색은 통계상 10건인데 9건만 왔고, 정확 검색에만 있는 장면 하나가
    합류해 합계가 10이 된다. 합친 뒤에 세면 10 >= 10으로 검증을 통과해
    버리지만, 일반 경로는 여전히 1건을 놓친 상태다.
    """
    relation = _add_relation(database, KOREAN_MEANING, "大丈夫")
    _activate_media(database, "media-a")
    normal_nine = tuple(("media-a", f"大丈夫。 {index}番目") for index in range(9))
    pages = {
        ("大丈夫", False, None): _media_response(*normal_nine),
        ("大丈夫", True, None): _media_response(("media-a", "もう大丈夫。")),
    }
    client = OracleNadeshiko(
        pages,
        expected_hits={"media-a": 10},  # 일반 검색은 10건이라고 알려 줬다
        exact_expected_hits={"media-a": 1},  # 정확 검색은 1건뿐이고 그건 다 받았다
    )

    found = search_selected_expression(
        settings, relation, nadeshiko_client=client, database=database
    )

    # 합친 raw는 10건이지만 일반 경로가 모자라므로 검증은 실패해야 한다.
    assert len(found.nadeshiko_segments) == 10
    assert found.search_fully_checked is False
    coverage = {item.media_public_id: item for item in found.coverage}["media-a"]
    assert coverage.normal.expected_hits == 10
    assert coverage.normal.retrieved_hits == 9
    assert coverage.normal.verified is False
    assert coverage.exact.verified is True
    assert coverage.verified is False
    line = ui_controller.search_coverage_line(found)
    assert "일부를 받지 못했습니다" in line
    assert "일반 검색 1개 작품" in line

    # 합친 뒤 하나의 통계와만 비교하면 10 >= 10이라 통과해 버리는 상황이다.
    # 이 시험은 그 허위 성공을 다시 만들지 않게 막는다.
    union_raw = len({segment.public_id for segment in found.nadeshiko_segments})
    assert union_raw >= coverage.normal.expected_hits


def test_general_path_verified_even_when_exact_adds_more(
    settings: AppSettings,
    database: SceneCollectorDatabase,
) -> None:
    """CASE B — 일반 경로가 통계를 다 채웠으면 정확 경로의 추가분과 무관하게 통과."""
    relation = _add_relation(database, KOREAN_MEANING, "大丈夫")
    _activate_media(database, "media-a")
    normal_ten = tuple(("media-a", f"大丈夫。 {index}番目") for index in range(10))
    exact_extra = tuple(("media-a", f"もう大丈夫。 {index}回") for index in range(3))
    pages = {
        ("大丈夫", False, None): _media_response(*normal_ten),
        ("大丈夫", True, None): _media_response(*exact_extra),
    }
    client = OracleNadeshiko(
        pages, expected_hits={"media-a": 10}, exact_expected_hits={"media-a": 3}
    )

    found = search_selected_expression(
        settings, relation, nadeshiko_client=client, database=database
    )

    assert found.search_fully_checked is True
    assert found.normal_retrieved_hits == 10
    assert found.exact_retrieved_hits == 3
    assert len(found.nadeshiko_segments) == 13


def test_exact_path_shortfall_is_not_hidden_by_a_complete_general_path(
    settings: AppSettings,
    database: SceneCollectorDatabase,
) -> None:
    """CASE C — 일반 경로가 완전해도 정확 경로의 누락을 숨기지 않는다."""
    relation = _add_relation(database, KOREAN_MEANING, "大丈夫")
    _activate_media(database, "media-a")
    pages = {
        ("大丈夫", False, None): _media_response(
            ("media-a", "大丈夫。"), ("media-a", "もう大丈夫。")
        ),
        ("大丈夫", True, None): _media_response(
            ("media-a", "大丈夫。"), ("media-a", "まだ大丈夫。"), ("media-a", "全部大丈夫。")
        ),
    }
    client = OracleNadeshiko(
        pages,
        expected_hits={"media-a": 2},  # 일반은 2건 다 받았다
        exact_expected_hits={"media-a": 4},  # 정확은 4건이라는데 3건만 왔다
    )

    found = search_selected_expression(
        settings, relation, nadeshiko_client=client, database=database
    )

    coverage = {item.media_public_id: item for item in found.coverage}["media-a"]
    assert coverage.normal.verified is True
    assert coverage.exact.expected_hits == 4
    assert coverage.exact.retrieved_hits == 3
    assert coverage.exact.verified is False
    assert found.search_fully_checked is False
    line = ui_controller.search_coverage_line(found)
    assert "정확 검색 1개 작품" in line


def test_the_same_scene_in_both_paths_counts_once_in_the_final_list(
    settings: AppSettings,
    database: SceneCollectorDatabase,
) -> None:
    """CASE D — 두 경로에 같은 장면이 있어도 최종 제작 장면은 하나다."""
    relation = _add_relation(database, KOREAN_MEANING, "大丈夫")
    _activate_media(database, "media-a")
    shared = ("media-a", "大丈夫。")
    pages = {
        ("大丈夫", False, None): _media_response(shared, ("media-a", "もう大丈夫。")),
        ("大丈夫", True, None): _media_response(shared),
    }
    client = OracleNadeshiko(
        pages, expected_hits={"media-a": 2}, exact_expected_hits={"media-a": 1}
    )

    found = search_selected_expression(
        settings, relation, nadeshiko_client=client, database=database
    )

    ids = [segment.public_id for segment in found.nadeshiko_segments]
    assert len(ids) == len(set(ids)) == 2
    # 경로별 수신 수는 각자 세므로 중복 제거의 영향을 받지 않는다.
    assert found.normal_retrieved_hits == 2
    assert found.exact_retrieved_hits == 1
    assert found.search_fully_checked is True


def test_one_unverified_source_blocks_the_whole_search_from_reading_complete(
    settings: AppSettings,
    database: SceneCollectorDatabase,
) -> None:
    """CASE E — 작품 하나라도 검증 실패면 전체를 '빠짐없이'로 표시하지 않는다."""
    relation = _add_relation(database, KOREAN_MEANING, "大丈夫")
    _activate_media(database, "media-a", "media-b")
    pages = {
        ("大丈夫", False, None): _media_response(
            ("media-a", "大丈夫。"), ("media-b", "もう大丈夫。")
        ),
        ("大丈夫", True, None): _media_response(),
    }
    client = OracleNadeshiko(
        pages,
        expected_hits={"media-a": 1, "media-b": 3},  # media-b만 모자라다
        exact_expected_hits={},
    )

    found = search_selected_expression(
        settings, relation, nadeshiko_client=client, database=database
    )

    by_media = {item.media_public_id: item for item in found.coverage}
    assert by_media["media-a"].verified is True
    assert by_media["media-b"].verified is False
    assert found.search_fully_checked is False
    line = ui_controller.search_coverage_line(found)
    assert "빠짐없이" not in line


def test_duplicate_pages_do_not_inflate_a_paths_retrieved_count(
    settings: AppSettings,
    database: SceneCollectorDatabase,
) -> None:
    """같은 장면이 페이지 경계에서 두 번 와도 회수 수를 부풀리지 않는다."""
    relation = _add_relation(database, KOREAN_MEANING, "大丈夫")
    _activate_media(database, "media-a")
    repeated = ("media-a", "大丈夫。")
    pages = {
        ("大丈夫", False, None): _media_response(repeated, cursor="p2"),
        ("大丈夫", False, "p2"): _media_response(repeated),
        ("大丈夫", True, None): _media_response(),
    }
    client = OracleNadeshiko(pages, expected_hits={"media-a": 2}, exact_expected_hits={})

    found = search_selected_expression(
        settings, relation, nadeshiko_client=client, database=database
    )

    # 같은 장면을 두 번 받았을 뿐 서로 다른 장면은 하나다.
    assert found.normal_retrieved_hits == 1
    assert found.search_fully_checked is False
    assert len(found.nadeshiko_segments) == 1
