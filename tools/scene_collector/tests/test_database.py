import copy
import json
import sqlite3
from pathlib import Path

import pytest
from nadeshiko.models import SearchQuery, SearchResponse
from pydantic import BaseModel

import scene_collector.ai as ai_module
import scene_collector.database as database_module
from scene_collector.ai import create_structured_response
from scene_collector.config import AISettings, AppSettings, SearchSettings, StorageSettings
from scene_collector.database import (
    DATABASE_FILENAME,
    SCHEMA_VERSION,
    DatabaseError,
    SceneCollectorDatabase,
    UnsupportedSchemaVersionError,
)
from scene_collector.models import ExpressionCandidate, ExpressionCandidates
from scene_collector.search import (
    CANDIDATE_INSTRUCTION_VERSION,
    CandidateSearchResult,
    ExpressionSearchResult,
    search_expressions,
)

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "nadeshiko_search_response.json"
EXPECTED_TABLES = {
    "ai_cache",
    "expression_segments",
    "expressions",
    "media",
    "nadeshiko_search_cache",
    "reviews",
    "search_runs",
    "segments",
}


class CacheProbe(BaseModel):
    text: str
    number: int


def _settings(
    work_data_dir: Path,
    *,
    service: str = "provider-one",
    model: str = "model-one",
    candidate_count: int = 3,
    nadeshiko_take: int = 2,
) -> AppSettings:
    return AppSettings(
        storage=StorageSettings(work_data_dir=work_data_dir),
        ai=AISettings(service=service, model=model),
        search=SearchSettings(
            candidate_count=candidate_count,
            nadeshiko_take=nadeshiko_take,
        ),
    )


def _candidate(japanese: str, number: int) -> ExpressionCandidate:
    return ExpressionCandidate(
        japanese=japanese,
        reading=f"よみかた{number}",
        meaning_ko=f"의미 {number}",
        register=f"말투 {number}",
    )


def _search_response(*segments: tuple[str, str]) -> SearchResponse:
    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    payload["pagination"] = {
        "hasMore": False,
        "estimatedTotalHits": len(segments),
        "estimatedTotalHitsRelation": "EXACT",
        "cursor": None,
    }
    segment_template = payload["segments"][0]
    payload["segments"] = []
    for position, (public_id, text_ja) in enumerate(segments, start=1):
        segment = copy.deepcopy(segment_template)
        segment["publicId"] = public_id
        segment["position"] = position
        segment["textJa"]["content"] = text_ja
        payload["segments"].append(segment)
    return SearchResponse.from_dict(payload)


def _result_with_shared_segment() -> ExpressionSearchResult:
    first = _candidate("大丈夫ですか", 1)
    duplicate = _candidate("大丈夫ですか", 2)
    empty = _candidate("結果なし", 3)
    matching_response = _search_response(("anonymous-segment-shared", "大丈夫ですか？"))
    empty_response = _search_response()
    return ExpressionSearchResult(
        korean_intent="다친 사람에게 괜찮냐고 묻는 말",
        generated_candidates=(first, duplicate, empty),
        candidate_searches=(
            CandidateSearchResult(
                candidate=first,
                response=matching_response,
                exact_match_response=None,
                exact_segments=tuple(matching_response.segments),
            ),
            CandidateSearchResult(
                candidate=empty,
                response=empty_response,
                exact_match_response=empty_response,
                exact_segments=(),
            ),
        ),
    )


def _table_names(connection: sqlite3.Connection) -> set[str]:
    return {
        row[0]
        for row in connection.execute(
            """
            SELECT name FROM sqlite_master
            WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
            """
        )
    }


def test_creates_file_database_v1_with_foreign_keys_and_default_journal(tmp_path: Path) -> None:
    settings = _settings(tmp_path)

    with SceneCollectorDatabase.open(settings) as database:
        assert database.path == tmp_path / DATABASE_FILENAME
        assert database.path.is_file()
        assert database.schema_version == SCHEMA_VERSION == 1
        assert _table_names(database.connection) == EXPECTED_TABLES
        assert database.connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert database.connection.execute("PRAGMA journal_mode").fetchone()[0] == "delete"


def test_rejects_missing_work_data_directory_at_open_time(tmp_path: Path) -> None:
    work_data_dir = tmp_path / "work-data"
    work_data_dir.mkdir()
    settings = _settings(work_data_dir)
    work_data_dir.rmdir()

    with pytest.raises(DatabaseError, match="작업 데이터 디렉터리"):
        SceneCollectorDatabase.open(settings)


def test_schema_initialization_failure_rolls_back_all_tables(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    statements = database_module._SCHEMA_STATEMENTS
    monkeypatch.setattr(
        database_module,
        "_SCHEMA_STATEMENTS",
        (statements[0], "CREATE TABLE broken (", *statements[1:]),
    )
    path = tmp_path / DATABASE_FILENAME

    with pytest.raises(DatabaseError, match="schema 초기화"):
        SceneCollectorDatabase.open(_settings(tmp_path))

    with sqlite3.connect(path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 0
        assert _table_names(connection) == set()


def test_future_schema_version_is_rejected_without_writes(tmp_path: Path) -> None:
    path = tmp_path / DATABASE_FILENAME
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE sentinel (value TEXT NOT NULL)")
        connection.execute("INSERT INTO sentinel VALUES ('preserved')")
        connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION + 1}")

    with pytest.raises(UnsupportedSchemaVersionError, match="데이터를 수정하지 않았습니다"):
        SceneCollectorDatabase.open(_settings(tmp_path))

    with sqlite3.connect(path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 2
        assert connection.execute("SELECT value FROM sentinel").fetchone()[0] == "preserved"
        assert _table_names(connection) == {"sentinel"}


def test_foreign_key_failure_rolls_back_the_whole_transaction(tmp_path: Path) -> None:
    with SceneCollectorDatabase.open(_settings(tmp_path)) as database:
        with pytest.raises(sqlite3.IntegrityError):
            with database.transaction() as connection:
                connection.execute(
                    """
                    INSERT INTO search_runs (
                        korean_intent, created_at, ai_service, ai_model, instruction_version
                    ) VALUES ('rollback me', 'now', 'service', 'model', 'v1')
                    """
                )
                connection.execute(
                    """
                    INSERT INTO expressions (
                        search_run_id, ordinal, japanese, reading, meaning_ko, register_text
                    ) VALUES (9999, 0, '例', 'れい', '예', '보통')
                    """
                )

        assert database.connection.execute("SELECT COUNT(*) FROM search_runs").fetchone()[0] == 0
        assert database.connection.execute("SELECT COUNT(*) FROM expressions").fetchone()[0] == 0


def test_search_review_and_shared_segment_survive_reopen(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    with SceneCollectorDatabase.open(settings) as database:
        search_run_id = database.save_search_result(
            _result_with_shared_segment(),
            ai_service="provider-one",
            ai_model="model-one",
            instruction_version="candidate-v1",
        )
        stored = database.load_search_run(search_run_id)
        assert stored is not None
        first_expression, duplicate_expression, _ = stored.expressions
        shared_segment_id = first_expression.segments[0].id
        assert duplicate_expression.segments[0].id == shared_segment_id
        assert database.connection.execute("SELECT COUNT(*) FROM segments").fetchone()[0] == 1
        assert (
            database.connection.execute("SELECT COUNT(*) FROM expression_segments").fetchone()[0]
            == 2
        )

        database.set_expression_selected(first_expression.id, True)
        database.save_review(
            first_expression.id,
            shared_segment_id,
            decision="예비",
        )
        empty_review = database.get_review(first_expression.id, shared_segment_id)
        assert empty_review is not None
        assert empty_review.direct_meaning is None
        assert empty_review.natural_translation is None
        assert empty_review.scene_usage is None
        assert empty_review.notes is None

        database.save_review(
            first_expression.id,
            shared_segment_id,
            decision="채택",
            direct_meaning="괜찮습니까?",
            natural_translation="괜찮아요?",
            scene_usage="상대의 상태를 확인함",
            notes="재검수 완료",
        )

    with SceneCollectorDatabase.open(settings) as reopened:
        assert reopened.schema_version == 1
        restored = reopened.load_search_run(search_run_id)
        assert restored is not None
        assert restored.korean_intent == "다친 사람에게 괜찮냐고 묻는 말"
        assert restored.ai_service == "provider-one"
        assert restored.ai_model == "model-one"
        assert restored.instruction_version == "candidate-v1"
        assert len(restored.expressions) == 3
        assert restored.expressions[0].selected is True
        assert restored.expressions[1].selected is False
        first_segment = restored.expressions[0].segments[0]
        second_segment = restored.expressions[1].segments[0]
        assert first_segment.id == second_segment.id
        assert first_segment.segment.public_id == "anonymous-segment-shared"
        assert first_segment.segment.text_ja.content == "大丈夫ですか？"
        assert first_segment.segment.urls.video_url.endswith("/video.mp4")
        assert first_segment.review is not None
        assert first_segment.review.decision == "채택"
        assert first_segment.review.natural_translation == "괜찮아요?"
        assert second_segment.review is None


def test_rejects_review_outside_the_allowed_decisions(tmp_path: Path) -> None:
    with SceneCollectorDatabase.open(_settings(tmp_path)) as database:
        stored_id = database.save_search_result(
            _result_with_shared_segment(),
            ai_service="provider-one",
            ai_model="model-one",
            instruction_version="candidate-v1",
        )
        stored = database.load_search_run(stored_id)
        assert stored is not None
        expression = stored.expressions[0]

        with pytest.raises(ValueError, match="채택, 예비, 제외"):
            database.save_review(
                expression.id,
                expression.segments[0].id,
                decision="보류",  # type: ignore[arg-type]
            )


def test_connection_backup_preserves_sentinel_and_schema_version(tmp_path: Path) -> None:
    with SceneCollectorDatabase.open(_settings(tmp_path)) as database:
        with database.transaction() as connection:
            connection.execute(
                """
                INSERT INTO search_runs (
                    korean_intent, created_at, ai_service, ai_model, instruction_version
                ) VALUES ('backup sentinel', 'now', 'service', 'model', 'v1')
                """
            )
        first_backup = database.backup_before_schema_change()
        second_backup = database.backup_before_schema_change()

    assert first_backup.parent == tmp_path
    assert first_backup != second_backup
    assert ".pre-schema-v1." in first_backup.name
    with sqlite3.connect(first_backup) as backup:
        assert backup.execute("PRAGMA user_version").fetchone()[0] == 1
        assert (
            backup.execute("SELECT korean_intent FROM search_runs").fetchone()[0]
            == "backup sentinel"
        )


def test_ai_cache_hits_and_separates_service_model_version_and_input(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    class FakeClient:
        def create(
            self,
            *,
            response_model: type[CacheProbe],
            messages: list[dict[str, str]],
        ) -> CacheProbe:
            calls.append(messages[0]["content"])
            return response_model(text="connection-ok", number=7)

    monkeypatch.setattr(ai_module.instructor, "from_provider", lambda _: FakeClient())

    with SceneCollectorDatabase.open(_settings(tmp_path)) as database:
        base_settings = _settings(tmp_path)
        for _ in range(2):
            response = create_structured_response(
                base_settings,
                prompt="same input",
                response_model=CacheProbe,
                cache=database,
                instruction_version="probe-v1",
            )
            assert isinstance(response, CacheProbe)

        create_structured_response(
            _settings(tmp_path, service="provider-two"),
            prompt="same input",
            response_model=CacheProbe,
            cache=database,
            instruction_version="probe-v1",
        )
        create_structured_response(
            _settings(tmp_path, model="model-two"),
            prompt="same input",
            response_model=CacheProbe,
            cache=database,
            instruction_version="probe-v1",
        )
        create_structured_response(
            base_settings,
            prompt="same input",
            response_model=CacheProbe,
            cache=database,
            instruction_version="probe-v2",
        )
        create_structured_response(
            base_settings,
            prompt="different input",
            response_model=CacheProbe,
            cache=database,
            instruction_version="probe-v1",
        )

        assert len(calls) == 5
        assert database.connection.execute("SELECT COUNT(*) FROM ai_cache").fetchone()[0] == 5

        with database.transaction() as connection:
            connection.execute(
                """
                UPDATE ai_cache SET response_json = '{broken-json'
                WHERE ai_service = 'provider-one'
                    AND ai_model = 'model-one'
                    AND instruction_version = 'probe-v1'
                """
            )
        create_structured_response(
            base_settings,
            prompt="same input",
            response_model=CacheProbe,
            cache=database,
            instruction_version="probe-v1",
        )
        assert len(calls) == 6

        with database.transaction() as connection:
            connection.execute(
                """
                UPDATE ai_cache SET response_json = '{"text":"connection-ok","number":"wrong"}'
                WHERE ai_service = 'provider-one'
                    AND ai_model = 'model-one'
                    AND instruction_version = 'probe-v1'
                """
            )
        create_structured_response(
            base_settings,
            prompt="same input",
            response_model=CacheProbe,
            cache=database,
            instruction_version="probe-v1",
        )
        assert len(calls) == 7


def test_nadeshiko_cache_key_separates_exact_take_and_conditions(tmp_path: Path) -> None:
    response = _search_response(("cache-segment", "大丈夫ですか？"))
    with SceneCollectorDatabase.open(_settings(tmp_path)) as database:
        database.put_nadeshiko_search_cache(
            search_text="大丈夫ですか",
            exact_match=False,
            take=2,
            conditions={"media_ids": ["media-one"]},
            response=response,
        )

        cached = database.get_nadeshiko_search_cache(
            search_text="大丈夫ですか",
            exact_match=False,
            take=2,
            conditions={"media_ids": ["media-one"]},
        )
        assert cached is not None
        assert cached.segments[0].public_id == "cache-segment"
        assert (
            database.get_nadeshiko_search_cache(
                search_text="大丈夫ですか",
                exact_match=True,
                take=2,
                conditions={"media_ids": ["media-one"]},
            )
            is None
        )
        assert (
            database.get_nadeshiko_search_cache(
                search_text="大丈夫ですか",
                exact_match=False,
                take=3,
                conditions={"media_ids": ["media-one"]},
            )
            is None
        )
        assert (
            database.get_nadeshiko_search_cache(
                search_text="大丈夫ですか",
                exact_match=False,
                take=2,
                conditions={"media_ids": ["media-two"]},
            )
            is None
        )


def test_repeated_search_uses_both_caches_and_persists_each_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    generated = ExpressionCandidates(
        candidates=[
            _candidate("大丈夫ですか", 1),
            _candidate("ちょっと待って", 2),
            _candidate("結果なし", 3),
        ]
    )
    ai_call_count = 0

    class FakeAIClient:
        def create(
            self,
            *,
            response_model: type[ExpressionCandidates],
            messages: list[dict[str, str]],
        ) -> ExpressionCandidates:
            nonlocal ai_call_count
            ai_call_count += 1
            assert response_model is ExpressionCandidates
            assert messages
            return generated

    class FakeNadeshiko:
        def __init__(self) -> None:
            self.calls: list[tuple[str, bool, int]] = []

        def search(self, *, query: SearchQuery, take: int) -> SearchResponse:
            self.calls.append((query.search, bool(query.exact_match), take))
            if query.search == "大丈夫ですか":
                return _search_response(("segment-ok", "大丈夫ですか？"))
            if query.search == "ちょっと待って" and query.exact_match:
                return _search_response(("segment-wait", "ちょっと待って。"))
            return _search_response()

    monkeypatch.setattr(ai_module.instructor, "from_provider", lambda _: FakeAIClient())
    settings = _settings(tmp_path)
    client = FakeNadeshiko()

    with SceneCollectorDatabase.open(settings) as database:
        first = search_expressions(
            settings,
            "상대에게 기다려 달라고 말하기",
            nadeshiko_client=client,
            database=database,
        )
        first_calls = tuple(client.calls)
        second = search_expressions(
            settings,
            "상대에게 기다려 달라고 말하기",
            nadeshiko_client=client,
            database=database,
        )

        assert ai_call_count == 1
        assert tuple(client.calls) == first_calls
        assert len(client.calls) == 5
        assert [item.candidate.japanese for item in first.corpus_backed_candidates] == [
            "大丈夫ですか",
            "ちょっと待って",
        ]
        assert [item.candidate.japanese for item in second.corpus_backed_candidates] == [
            "大丈夫ですか",
            "ちょっと待って",
        ]
        assert database.connection.execute("SELECT COUNT(*) FROM ai_cache").fetchone()[0] == 1
        assert (
            database.connection.execute("SELECT COUNT(*) FROM nadeshiko_search_cache").fetchone()[
                0
            ]
            == 5
        )
        assert database.connection.execute("SELECT COUNT(*) FROM search_runs").fetchone()[0] == 2
        latest_run = database.load_search_run(2)
        assert latest_run is not None
        assert latest_run.instruction_version == CANDIDATE_INSTRUCTION_VERSION
        assert latest_run.expressions[0].segments[0].segment.public_id == "segment-ok"

    with SceneCollectorDatabase.open(settings) as reopened:
        third = search_expressions(
            settings,
            "상대에게 기다려 달라고 말하기",
            nadeshiko_client=client,
            database=reopened,
        )
        assert ai_call_count == 1
        assert tuple(client.calls) == first_calls
        assert [item.candidate.japanese for item in third.corpus_backed_candidates] == [
            "大丈夫ですか",
            "ちょっと待って",
        ]
        assert reopened.connection.execute("SELECT COUNT(*) FROM search_runs").fetchone()[0] == 3
