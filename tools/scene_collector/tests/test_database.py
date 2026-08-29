import copy
import json
import sqlite3
from pathlib import Path

import pytest
from nadeshiko.models import (
    SearchFilters,
    SearchQuery,
    SearchResponse,
    SegmentContextResponse,
)
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
    "local_segments",
    "media",
    "nadeshiko_context_cache",
    "nadeshiko_search_cache",
    "reviews",
    "search_runs",
    "segments",
}

V1_MEDIA_DDL = """
    CREATE TABLE media (
        id INTEGER PRIMARY KEY,
        nadeshiko_media_id TEXT NOT NULL UNIQUE,
        display_name TEXT,
        preference INTEGER,
        content_group TEXT,
        is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1))
    )
    """

V1_REVIEWS_DDL = """
    CREATE TABLE reviews (
        expression_id INTEGER NOT NULL,
        segment_id INTEGER NOT NULL,
        decision TEXT NOT NULL CHECK (decision IN ('채택', '예비', '제외')),
        direct_meaning TEXT,
        natural_translation TEXT,
        scene_usage TEXT,
        notes TEXT,
        updated_at TEXT NOT NULL,
        PRIMARY KEY (expression_id, segment_id),
        FOREIGN KEY (expression_id, segment_id)
            REFERENCES expression_segments(expression_id, segment_id) ON DELETE CASCADE
    )
    """


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


def test_creates_file_database_with_foreign_keys_and_default_journal(tmp_path: Path) -> None:
    settings = _settings(tmp_path)

    with SceneCollectorDatabase.open(settings) as database:
        assert database.path == tmp_path / DATABASE_FILENAME
        assert database.path.is_file()
        assert database.schema_version == SCHEMA_VERSION == 3
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
        assert connection.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION + 1
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
        assert reopened.schema_version == SCHEMA_VERSION
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
    assert ".pre-schema-v3." in first_backup.name
    with sqlite3.connect(first_backup) as backup:
        assert backup.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
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


def _create_seeded_v1_database(path: Path) -> None:
    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    segment_json = json.dumps(payload["segments"][0], ensure_ascii=False)
    connection = sqlite3.connect(path)
    try:
        with connection:
            for statement in database_module._SCHEMA_STATEMENTS:
                if "nadeshiko_context_cache" in statement or "local_segments" in statement:
                    continue
                if "CREATE TABLE media" in statement:
                    connection.execute(V1_MEDIA_DDL)
                    continue
                if "CREATE TABLE reviews" in statement:
                    connection.execute(V1_REVIEWS_DDL)
                    continue
                connection.execute(statement)
            connection.execute(
                """
                INSERT INTO media (id, nadeshiko_media_id, display_name)
                VALUES (1, 'anonymous-media-001', '익명 작품')
                """
            )
            connection.execute(
                """
                INSERT INTO search_runs (
                    id, korean_intent, created_at, ai_service, ai_model, instruction_version
                ) VALUES (1, '괜찮냐고 묻는 말', 'past', 'service', 'model', 'candidate-v1')
                """
            )
            connection.execute(
                """
                INSERT INTO expressions (
                    id, search_run_id, ordinal, japanese, reading,
                    meaning_ko, register_text, is_selected
                ) VALUES (1, 1, 0, '大丈夫ですか', 'だいじょうぶですか', '괜찮으세요?', '정중', 1)
                """
            )
            connection.execute(
                """
                INSERT INTO segments (
                    id, nadeshiko_segment_id, media_id, position, episode,
                    start_time_ms, end_time_ms, external_video_id, japanese_text,
                    video_url, audio_url, image_url, raw_json
                ) VALUES (
                    1, 'anonymous-segment-001', 1, 42, 1, 0, 1000, NULL, '大丈夫ですか？',
                    'https://media.example.invalid/video.mp4',
                    'https://media.example.invalid/audio.mp3',
                    'https://media.example.invalid/image.jpg', ?
                )
                """,
                (segment_json,),
            )
            connection.execute(
                "INSERT INTO expression_segments (expression_id, segment_id, ordinal)"
                " VALUES (1, 1, 0)"
            )
            connection.execute(
                """
                INSERT INTO reviews (
                    expression_id, segment_id, decision, direct_meaning,
                    natural_translation, scene_usage, notes, updated_at
                ) VALUES (1, 1, '채택', '괜찮습니까?', '괜찮아요?', '상태 확인', '메모', 'past')
                """
            )
            connection.execute("PRAGMA user_version = 1")
    finally:
        connection.close()


def test_v1_database_migrates_to_current_schema_with_backups(tmp_path: Path) -> None:
    path = tmp_path / DATABASE_FILENAME
    _create_seeded_v1_database(path)

    with SceneCollectorDatabase.open(_settings(tmp_path)) as database:
        assert database.schema_version == SCHEMA_VERSION == 3
        assert _table_names(database.connection) == EXPECTED_TABLES
        review = database.get_review(1, 1)
        assert review is not None
        assert review.decision == "채택"
        assert review.direct_meaning == "괜찮습니까?"
        assert review.natural_translation == "괜찮아요?"
        assert review.scene_usage == "상태 확인"
        assert review.notes == "메모"
        assert review.translation_ai_service is None
        assert review.translation_ai_model is None
        assert review.translation_instruction_version is None
        assert review.translation_input_hash is None
        assert review.translated_at is None
        restored = database.load_search_run(1)
        assert restored is not None
        segment = restored.expressions[0].segments[0]
        assert segment.segment.public_id == "anonymous-segment-001"
        assert segment.review is not None
        assert segment.review.decision == "채택"
        migrated_media = database.get_media("anonymous-media-001")
        assert migrated_media is not None
        assert migrated_media.source == "nadeshiko"
        assert migrated_media.display_name == "익명 작품"
        assert (
            database.connection.execute("PRAGMA foreign_key_check").fetchall() == []
        )

    v1_backups = sorted(tmp_path.glob("*.pre-schema-v1.*"))
    v2_backups = sorted(tmp_path.glob("*.pre-schema-v2.*"))
    assert len(v1_backups) == 1
    assert len(v2_backups) == 1
    with sqlite3.connect(v1_backups[0]) as backup:
        assert backup.execute("PRAGMA user_version").fetchone()[0] == 1
        assert backup.execute("SELECT decision FROM reviews").fetchone()[0] == "채택"
    with sqlite3.connect(v2_backups[0]) as backup:
        assert backup.execute("PRAGMA user_version").fetchone()[0] == 2

    with SceneCollectorDatabase.open(_settings(tmp_path)) as reopened:
        assert reopened.schema_version == SCHEMA_VERSION
    assert len(sorted(tmp_path.glob("*.pre-schema-v1.*"))) == 1
    assert len(sorted(tmp_path.glob("*.pre-schema-v2.*"))) == 1


def _create_seeded_v2_database(path: Path) -> None:
    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    segment_json = json.dumps(payload["segments"][0], ensure_ascii=False)
    connection = sqlite3.connect(path)
    try:
        with connection:
            for statement in database_module._SCHEMA_STATEMENTS:
                if "local_segments" in statement:
                    continue
                if "CREATE TABLE media" in statement:
                    connection.execute(V1_MEDIA_DDL)
                    continue
                connection.execute(statement)
            connection.execute(
                """
                INSERT INTO media (
                    id, nadeshiko_media_id, display_name, preference, content_group, is_active
                ) VALUES (1, 'anonymous-media-001', '익명 작품', 4, '극장판', 0)
                """
            )
            connection.execute(
                """
                INSERT INTO segments (
                    id, nadeshiko_segment_id, media_id, position, episode,
                    start_time_ms, end_time_ms, external_video_id, japanese_text,
                    video_url, audio_url, image_url, raw_json
                ) VALUES (
                    1, 'anonymous-segment-001', 1, 42, 1, 0, 1000, NULL, '大丈夫ですか？',
                    'https://media.example.invalid/video.mp4',
                    'https://media.example.invalid/audio.mp3',
                    'https://media.example.invalid/image.jpg', ?
                )
                """,
                (segment_json,),
            )
            connection.execute("PRAGMA user_version = 2")
    finally:
        connection.close()


def test_v2_database_migrates_to_v3_preserving_media_and_references(tmp_path: Path) -> None:
    path = tmp_path / DATABASE_FILENAME
    _create_seeded_v2_database(path)

    with SceneCollectorDatabase.open(_settings(tmp_path)) as database:
        assert database.schema_version == SCHEMA_VERSION == 3
        assert _table_names(database.connection) == EXPECTED_TABLES
        media = database.get_media("anonymous-media-001")
        assert media is not None
        assert media.source == "nadeshiko"
        assert media.display_name == "익명 작품"
        assert media.preference == 4
        assert media.content_group == "극장판"
        assert media.is_active is False
        joined = database.connection.execute(
            """
            SELECT media.nadeshiko_media_id
            FROM segments JOIN media ON media.id = segments.media_id
            """
        ).fetchone()
        assert joined[0] == "anonymous-media-001"
        assert database.connection.execute("PRAGMA foreign_key_check").fetchall() == []
        local = database.register_local_media("로컬 작품")
        assert local.source == "local"
        assert local.nadeshiko_media_id is None

    assert len(sorted(tmp_path.glob("*.pre-schema-v2.*"))) == 1


def test_v2_migration_failure_keeps_original_v2_data(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / DATABASE_FILENAME
    _create_seeded_v2_database(path)
    statements = database_module._V2_TO_V3_STATEMENTS
    monkeypatch.setattr(
        database_module,
        "_V2_TO_V3_STATEMENTS",
        (*statements[:4], "CREATE TABLE broken (", *statements[4:]),
    )

    with pytest.raises(DatabaseError, match="v2 → v3 migration"):
        SceneCollectorDatabase.open(_settings(tmp_path))

    with sqlite3.connect(path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 2
        tables = _table_names(connection)
        assert "media" in tables
        assert "media_v3" not in tables
        assert "local_segments" not in tables
        row = connection.execute(
            "SELECT nadeshiko_media_id, preference FROM media"
        ).fetchone()
        assert tuple(row) == ("anonymous-media-001", 4)
        assert connection.execute("SELECT COUNT(*) FROM segments").fetchone()[0] == 1


def test_v1_migration_failure_keeps_original_v1_data(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / DATABASE_FILENAME
    _create_seeded_v1_database(path)
    statements = database_module._V1_TO_V2_STATEMENTS
    monkeypatch.setattr(
        database_module,
        "_V1_TO_V2_STATEMENTS",
        (*statements[:2], "CREATE TABLE broken (", *statements[2:]),
    )

    with pytest.raises(DatabaseError, match="migration"):
        SceneCollectorDatabase.open(_settings(tmp_path))

    with sqlite3.connect(path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 1
        tables = _table_names(connection)
        assert "reviews" in tables
        assert "reviews_v2" not in tables
        assert "nadeshiko_context_cache" not in tables
        row = connection.execute("SELECT decision, notes FROM reviews").fetchone()
        assert tuple(row) == ("채택", "메모")


def test_nadeshiko_context_cache_hits_same_identity_and_misses_other(tmp_path: Path) -> None:
    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    context = SegmentContextResponse.from_dict({"segments": payload["segments"]})

    with SceneCollectorDatabase.open(_settings(tmp_path)) as database:
        database.put_nadeshiko_context_cache(
            segment_public_id="anonymous-segment-001",
            take=2,
            response=context,
        )
        cached = database.get_nadeshiko_context_cache(
            segment_public_id="anonymous-segment-001",
            take=2,
        )
        assert cached is not None
        assert cached.segments[0].public_id == "anonymous-segment-001"
        assert (
            database.get_nadeshiko_context_cache(
                segment_public_id="anonymous-segment-001",
                take=3,
            )
            is None
        )
        assert (
            database.get_nadeshiko_context_cache(
                segment_public_id="anonymous-segment-002",
                take=2,
            )
            is None
        )

        with database.transaction() as connection:
            connection.execute(
                "UPDATE nadeshiko_context_cache SET response_json = '{broken-json'"
            )
        assert (
            database.get_nadeshiko_context_cache(
                segment_public_id="anonymous-segment-001",
                take=2,
            )
            is None
        )


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
            self.calls: list[tuple[str, bool, int, tuple[str, ...]]] = []

        def search(
            self,
            *,
            query: SearchQuery,
            take: int,
            filters: SearchFilters,
        ) -> SearchResponse:
            included = tuple(item.media_public_id for item in filters.media.include)
            self.calls.append((query.search, bool(query.exact_match), take, included))
            if query.search == "大丈夫ですか":
                return _search_response(("segment-ok", "大丈夫ですか？"))
            if query.search == "ちょっと待って" and query.exact_match:
                return _search_response(("segment-wait", "ちょっと待って。"))
            return _search_response()

    monkeypatch.setattr(ai_module.instructor, "from_provider", lambda _: FakeAIClient())
    settings = _settings(tmp_path)
    client = FakeNadeshiko()

    with SceneCollectorDatabase.open(settings) as database:
        database.upsert_media("anonymous-media-001", display_name="익명 작품 1")
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
        assert all(call[3] == ("anonymous-media-001",) for call in client.calls)
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


def test_locked_database_raises_database_error_and_preserves_data(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    with SceneCollectorDatabase.open(settings) as database:
        database.upsert_media("anonymous-media-001", display_name="잠금 시험 작품")
        # 시험을 빠르게 하기 위한 대기 시간 축소 (기본 5초)
        database.connection.execute("PRAGMA busy_timeout = 100")

        locker = sqlite3.connect(database.path, isolation_level=None)
        locker.execute("BEGIN EXCLUSIVE")
        try:
            with pytest.raises(DatabaseError, match="사용할 수 없습니다"):
                database.set_media_active("anonymous-media-001", False)
            with pytest.raises(DatabaseError, match="사용할 수 없습니다"):
                database.schema_version
        finally:
            locker.execute("ROLLBACK")
            locker.close()

        # 잠금 해제 후에는 그대로 사용 가능하고 데이터가 보존된다
        assert database.schema_version == SCHEMA_VERSION
        stored = database.get_media("anonymous-media-001")
        assert stored is not None and stored.is_active is True
        database.set_media_active("anonymous-media-001", False)
        assert (
            database.connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        )

    with SceneCollectorDatabase.open(settings) as reopened:
        stored = reopened.get_media("anonymous-media-001")
        assert stored is not None and stored.is_active is False
