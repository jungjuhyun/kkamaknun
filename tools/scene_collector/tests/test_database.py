import sqlite3
from pathlib import Path

import pytest

import scene_collector.database as database_module
from scene_collector.config import AISettings, AppSettings, SearchSettings, StorageSettings
from scene_collector.database import (
    DATABASE_FILENAME,
    SCHEMA_VERSION,
    DatabaseError,
    SceneCollectorDatabase,
    StoredMeaningExpression,
    UnsupportedSchemaVersionError,
    normalize_korean_meaning,
    normalize_work_scene_notes,
)
from scene_collector.subtitles import SubtitleCue

EXPECTED_TABLES = {
    "expressions",
    "local_segments",
    "meaning_expressions",
    "meanings",
    "media",
    "work_scenes",
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

# 옛 DB(v1~v3)에만 있던 검색 이력·검색 결과·캐시 table들이다.
# 현재 제품은 이 구조를 다시 만들지 않으므로 migration 시험의 시드 전용으로 둔다.
OLD_SEARCH_RUNS_DDL = """
    CREATE TABLE search_runs (
        id INTEGER PRIMARY KEY,
        korean_intent TEXT NOT NULL,
        created_at TEXT NOT NULL,
        ai_service TEXT NOT NULL,
        ai_model TEXT NOT NULL,
        instruction_version TEXT NOT NULL
    )
    """

OLD_EXPRESSIONS_DDL = """
    CREATE TABLE expressions (
        id INTEGER PRIMARY KEY,
        search_run_id INTEGER NOT NULL,
        ordinal INTEGER NOT NULL,
        japanese TEXT NOT NULL,
        reading TEXT NOT NULL,
        meaning_ko TEXT NOT NULL,
        register_text TEXT NOT NULL,
        is_selected INTEGER NOT NULL DEFAULT 0 CHECK (is_selected IN (0, 1)),
        UNIQUE (search_run_id, ordinal),
        FOREIGN KEY (search_run_id) REFERENCES search_runs(id) ON DELETE CASCADE
    )
    """

OLD_SEGMENTS_DDL = """
    CREATE TABLE segments (
        id INTEGER PRIMARY KEY,
        nadeshiko_segment_id TEXT NOT NULL UNIQUE,
        media_id INTEGER NOT NULL,
        position INTEGER NOT NULL,
        episode INTEGER,
        start_time_ms INTEGER NOT NULL,
        end_time_ms INTEGER NOT NULL,
        external_video_id TEXT,
        japanese_text TEXT NOT NULL,
        video_url TEXT NOT NULL,
        audio_url TEXT NOT NULL,
        image_url TEXT NOT NULL,
        raw_json TEXT NOT NULL,
        FOREIGN KEY (media_id) REFERENCES media(id)
    )
    """

OLD_EXPRESSION_SEGMENTS_DDL = """
    CREATE TABLE expression_segments (
        expression_id INTEGER NOT NULL,
        segment_id INTEGER NOT NULL,
        ordinal INTEGER NOT NULL,
        PRIMARY KEY (expression_id, segment_id),
        FOREIGN KEY (expression_id) REFERENCES expressions(id) ON DELETE CASCADE,
        FOREIGN KEY (segment_id) REFERENCES segments(id) ON DELETE CASCADE
    )
    """

OLD_AI_CACHE_DDL = """
    CREATE TABLE ai_cache (
        cache_key TEXT PRIMARY KEY,
        ai_service TEXT NOT NULL,
        ai_model TEXT NOT NULL,
        instruction_version TEXT NOT NULL,
        response_json TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    """

OLD_SEARCH_CACHE_DDL = """
    CREATE TABLE nadeshiko_search_cache (
        cache_key TEXT PRIMARY KEY,
        response_json TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    """


def _settings(work_data_dir: Path) -> AppSettings:
    return AppSettings(
        storage=StorageSettings(work_data_dir=work_data_dir),
        ai=AISettings(service="provider-one", model="model-one"),
        search=SearchSettings(scene_result_limit=2),
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


def _cue(position: int, japanese_text: str, *, episode: int = 1) -> SubtitleCue:
    return SubtitleCue(
        episode=episode,
        position=position,
        start_time_ms=position * 1000,
        end_time_ms=position * 1000 + 900,
        japanese_text=japanese_text,
        source_file=f"ep{episode:02d}.srt",
    )


def _add_relation(
    database: SceneCollectorDatabase,
    korean_meaning: str,
    *,
    japanese: str,
    reading: str,
    meaning_ko: str,
    register_text: str,
) -> StoredMeaningExpression:
    """한국어 의미를 저장하고 일본어 표현 하나를 연결한다."""
    meaning = database.upsert_meaning(korean_meaning)
    return database.add_meaning_expression(
        meaning.id,
        japanese=japanese,
        reading=reading,
        meaning_ko=meaning_ko,
        register_text=register_text,
    )


def _add_work_scene(
    database: SceneCollectorDatabase,
    relation_id: int,
    *,
    segment_public_id: str,
    japanese_text: str = "大丈夫ですか？",
    episode: int | None = 1,
) -> int:
    return database.upsert_work_scene(
        relation_id,
        segment_public_id=segment_public_id,
        media_public_id="anonymous-media-001",
        media_display_name="익명 작품",
        episode=episode,
        start_time_ms=0,
        end_time_ms=1000,
        japanese_text=japanese_text,
    )


# ----------------------------------------------------------------------
# 파일·schema 기반
# ----------------------------------------------------------------------


def test_creates_file_database_with_foreign_keys_and_default_journal(tmp_path: Path) -> None:
    settings = _settings(tmp_path)

    with SceneCollectorDatabase.open(settings) as database:
        assert database.path == tmp_path / DATABASE_FILENAME
        assert database.path.is_file()
        assert database.schema_version == SCHEMA_VERSION == 4
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


def test_nonempty_version_zero_database_is_rejected_without_writes(tmp_path: Path) -> None:
    path = tmp_path / DATABASE_FILENAME
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE sentinel (value TEXT NOT NULL)")
        connection.execute("INSERT INTO sentinel VALUES ('preserved')")

    with pytest.raises(DatabaseError, match="명시적인 migration"):
        SceneCollectorDatabase.open(_settings(tmp_path))

    with sqlite3.connect(path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 0
        assert _table_names(connection) == {"sentinel"}
        assert connection.execute("SELECT value FROM sentinel").fetchone()[0] == "preserved"


def test_rejects_nested_transaction(tmp_path: Path) -> None:
    with SceneCollectorDatabase.open(_settings(tmp_path)) as database:
        with database.transaction():
            with pytest.raises(DatabaseError, match="중첩된"):
                with database.transaction():
                    pass


def test_foreign_key_failure_rolls_back_the_whole_transaction(tmp_path: Path) -> None:
    with SceneCollectorDatabase.open(_settings(tmp_path)) as database:
        with pytest.raises(sqlite3.IntegrityError):
            with database.transaction() as connection:
                connection.execute(
                    """
                    INSERT INTO meanings (
                        normalized_korean_meaning, display_korean_meaning, created_at
                    ) VALUES ('되돌릴 의미', '되돌릴 의미', 'now')
                    """
                )
                connection.execute(
                    """
                    INSERT INTO meaning_expressions (
                        meaning_id, expression_id, meaning_ko, register_text, created_at
                    ) VALUES (9999, 9999, '뜻', '말투', 'now')
                    """
                )

        assert database.connection.execute("SELECT COUNT(*) FROM meanings").fetchone()[0] == 0
        assert (
            database.connection.execute("SELECT COUNT(*) FROM meaning_expressions").fetchone()[0]
            == 0
        )


def test_connection_backup_preserves_sentinel_and_schema_version(tmp_path: Path) -> None:
    with SceneCollectorDatabase.open(_settings(tmp_path)) as database:
        database.upsert_meaning("백업 표시 의미")
        first_backup = database.backup_before_schema_change()
        second_backup = database.backup_before_schema_change()

    assert first_backup.parent == tmp_path
    assert first_backup != second_backup
    assert ".pre-schema-v4." in first_backup.name
    with sqlite3.connect(first_backup) as backup:
        assert backup.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
        assert (
            backup.execute("SELECT display_korean_meaning FROM meanings").fetchone()[0]
            == "백업 표시 의미"
        )


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
        assert database.connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"

    with SceneCollectorDatabase.open(settings) as reopened:
        stored = reopened.get_media("anonymous-media-001")
        assert stored is not None and stored.is_active is False


# ----------------------------------------------------------------------
# 작품 상태와 로컬 자막 색인
# ----------------------------------------------------------------------


def test_media_state_and_local_media_registration_round_trip(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    with SceneCollectorDatabase.open(settings) as database:
        stored = database.upsert_media("anonymous-media-001", display_name="익명 작품")
        assert stored.source == "nadeshiko"
        assert stored.is_active is True
        assert stored.preference is None

        database.set_media_preference("anonymous-media-001", 4)
        database.set_media_content_group("anonymous-media-001", "  극장판  ")
        # 표시명 없이 다시 저장해도 기존 표시명과 사용자 상태를 덮어쓰지 않는다
        again = database.upsert_media("anonymous-media-001")
        assert again.display_name == "익명 작품"
        assert again.preference == 4
        assert again.content_group == "극장판"
        assert len(database.list_media()) == 1

        local = database.register_local_media("  로컬 작품  ")
        assert local.source == "local"
        assert local.nadeshiko_media_id is None
        assert local.display_name == "로컬 작품"
        # 같은 이름의 로컬 작품은 다시 등록해도 재사용한다
        assert database.register_local_media("로컬 작품").id == local.id
        assert database.find_local_media("로컬 작품") is not None
        assert database.find_local_media("없는 로컬 작품") is None

        database.set_media_active("anonymous-media-001", False)
        database.set_local_media_active(local.id, False)
        assert database.list_active_media() == ()

        with pytest.raises(DatabaseError, match="작품을 찾을 수 없습니다"):
            database.set_media_preference("anonymous-media-999", 1)
        with pytest.raises(DatabaseError, match="로컬 작품을 찾을 수 없습니다"):
            database.set_local_media_active(9999, True)
        with pytest.raises(ValueError, match="public ID"):
            database.upsert_media("   ")
        with pytest.raises(ValueError, match="표시 이름"):
            database.register_local_media("   ")

    with SceneCollectorDatabase.open(settings) as reopened:
        assert len(reopened.list_media()) == 2
        assert reopened.list_active_media() == ()


def test_local_segments_are_replaced_and_searched_by_normalized_surface(tmp_path: Path) -> None:
    with SceneCollectorDatabase.open(_settings(tmp_path)) as database:
        first = database.register_local_media("로컬 작품 1")
        second = database.register_local_media("로컬 작품 2")
        assert (
            database.replace_local_segments(
                first.id, [_cue(1, "大丈夫 ですか？"), _cue(2, "ありがとう。")]
            )
            == 2
        )
        assert database.replace_local_segments(second.id, [_cue(1, "もう大丈夫ですか")]) == 1
        # 재색인해도 중복이 쌓이지 않고 이전 색인만 사라진다
        assert database.replace_local_segments(first.id, [_cue(1, "大丈夫ですか？")]) == 1
        assert (
            database.connection.execute("SELECT COUNT(*) FROM local_segments").fetchone()[0] == 2
        )

        matches = database.find_local_segments(
            normalized_surface="大丈夫ですか",
            media_row_ids=[first.id, second.id],
        )
        assert [match.media_id for match in matches] == [first.id, second.id]
        assert matches[0].media_display_name == "로컬 작품 1"
        assert matches[0].japanese_text == "大丈夫ですか？"
        assert matches[0].episode == 1
        assert matches[0].source_file == "ep01.srt"
        assert matches[1].japanese_text == "もう大丈夫ですか"

        only_second = database.find_local_segments(
            normalized_surface="大丈夫ですか",
            media_row_ids=[second.id],
        )
        assert [match.id for match in only_second] == [matches[1].id]
        assert (
            database.find_local_segments(
                normalized_surface="ありがとう", media_row_ids=[first.id]
            )
            == ()
        )
        assert (
            database.find_local_segments(normalized_surface="大丈夫ですか", media_row_ids=[]) == ()
        )
        # LIKE 특수문자는 그대로 찾을 문자로 다룬다
        assert (
            database.find_local_segments(normalized_surface="%", media_row_ids=[first.id]) == ()
        )
        with pytest.raises(ValueError, match="표면형"):
            database.find_local_segments(normalized_surface="", media_row_ids=[first.id])

        nadeshiko = database.upsert_media("anonymous-media-001", display_name="익명 작품")
        with pytest.raises(DatabaseError, match="로컬 작품을 찾을 수 없습니다"):
            database.replace_local_segments(nadeshiko.id, [])
        with pytest.raises(DatabaseError, match="로컬 작품을 찾을 수 없습니다"):
            database.replace_local_segments(9999, [])


# ----------------------------------------------------------------------
# 한국어 의미와 표현 자산
# ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("  괜찮냐고 묻는 말  ", "괜찮냐고 묻는 말"),  # 양끝 공백 제거
        ("괜찮냐고\t묻는   말", "괜찮냐고 묻는 말"),  # 연속 공백 축약
        ("괜찮아?", "괜찮아"),  # 끝의 물음표 제거
        ("괜찮아！！", "괜찮아"),  # NFKC로 반각이 된 전각 문장부호 제거
        ("괜찮아。", "괜찮아"),  # 일본어 마침표 제거
        ("가？", "가"),  # 분리된 한글 자모 조합 + 전각 물음표
        ("  ?!.  ", ""),  # 문장부호만 있으면 빈 문자열
    ],
)
def test_normalize_korean_meaning_cases(raw: str, expected: str) -> None:
    assert normalize_korean_meaning(raw) == expected


def test_meaning_lookup_uses_normalized_key_and_keeps_first_display_text(tmp_path: Path) -> None:
    with SceneCollectorDatabase.open(_settings(tmp_path)) as database:
        stored = database.upsert_meaning(" 괜찮냐고  묻는 말? ")
        assert stored.normalized_korean_meaning == "괜찮냐고 묻는 말"
        assert stored.display_korean_meaning == "괜찮냐고  묻는 말?"

        # 정규화 결과가 같으면 같은 의미이고 표시용 원문은 처음 입력을 유지한다
        again = database.upsert_meaning("괜찮냐고 묻는 말!")
        assert again == stored
        assert database.connection.execute("SELECT COUNT(*) FROM meanings").fetchone()[0] == 1

        assert database.find_meaning("괜찮냐고 묻는 말") == stored
        assert database.find_meaning("다른 의미") is None
        assert database.find_meaning("   ") is None
        assert database.get_meaning(stored.id) == stored
        assert database.get_meaning(9999) is None

        with pytest.raises(ValueError, match="한국어 의미"):
            database.upsert_meaning("  ?  ")


def test_same_expression_is_shared_by_two_meanings_with_own_descriptions(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    with SceneCollectorDatabase.open(settings) as database:
        asking = _add_relation(
            database,
            "괜찮냐고 묻는 말",
            japanese="大丈夫ですか",
            reading="だいじょうぶですか",
            meaning_ko="괜찮으세요?",
            register_text="정중",
        )
        checking = _add_relation(
            database,
            "몸 상태를 확인하는 말",
            japanese="大丈夫ですか",
            reading="だいじょうぶですか",
            meaning_ko="몸은 괜찮나요?",
            register_text="다정",
        )

        # 표현 자체는 하나만 저장하고 뜻·말투는 의미마다 따로 가진다
        assert asking.expression_id == checking.expression_id
        assert asking.id != checking.id
        assert asking.meaning_id != checking.meaning_id
        assert database.connection.execute("SELECT COUNT(*) FROM expressions").fetchone()[0] == 1
        assert (
            database.connection.execute("SELECT COUNT(*) FROM meaning_expressions").fetchone()[0]
            == 2
        )
        assert (asking.meaning_ko, asking.register_text) == ("괜찮으세요?", "정중")
        assert (checking.meaning_ko, checking.register_text) == ("몸은 괜찮나요?", "다정")

        # 같은 관계를 다시 저장해도 관계는 늘지 않고 처음 설명을 유지한다
        repeated = database.add_meaning_expression(
            asking.meaning_id,
            japanese="大丈夫ですか",
            reading="だいじょうぶですか",
            meaning_ko="덮어쓰지 않는 뜻",
            register_text="덮어쓰지 않는 말투",
        )
        assert repeated == asking
        assert (
            database.connection.execute("SELECT COUNT(*) FROM meaning_expressions").fetchone()[0]
            == 2
        )

        second = database.add_meaning_expression(
            asking.meaning_id,
            japanese="平気ですか",
            reading="へいきですか",
            meaning_ko="멀쩡해요?",
            register_text="담담",
        )
        assert database.list_meaning_expressions(asking.meaning_id) == (asking, second)
        assert database.find_expressions_for_meaning("괜찮냐고 묻는 말?") == (asking, second)
        assert database.find_expressions_for_meaning("저장한 적 없는 의미") == ()
        assert database.get_meaning_expression(asking.id) == asking
        assert database.get_meaning_expression(9999) is None

        with pytest.raises(ValueError, match="일본어 표현"):
            database.add_meaning_expression(
                asking.meaning_id,
                japanese="   ",
                reading="よみ",
                meaning_ko="뜻",
                register_text="말투",
            )

    with SceneCollectorDatabase.open(settings) as reopened:
        assert reopened.get_meaning_expression(checking.id) == checking


# ----------------------------------------------------------------------
# 실제 작업 장면
# ----------------------------------------------------------------------


def test_work_scene_snapshot_update_keeps_decision_translation_and_notes(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    with SceneCollectorDatabase.open(settings) as database:
        relation = _add_relation(
            database,
            "괜찮냐고 묻는 말",
            japanese="大丈夫ですか",
            reading="だいじょうぶですか",
            meaning_ko="괜찮으세요?",
            register_text="정중",
        )
        scene_id = _add_work_scene(
            database, relation.id, segment_public_id="anonymous-segment-001"
        )
        created = database.get_work_scene(relation.id, "anonymous-segment-001")
        assert created is not None
        assert created.id == scene_id
        assert created.decision is None
        assert created.notes is None
        assert created.has_translation is False
        assert created.media_public_id == "anonymous-media-001"

        # 판정 → 번역 → 메모 순서로 저장해도 서로를 지우지 않는다
        database.set_work_scene_decision(scene_id, "예비")
        database.save_work_scene_translation(
            scene_id,
            direct_meaning="괜찮습니까?",
            natural_translation="괜찮아요?",
            scene_usage="상대의 상태를 확인함",
            ai_service="provider-one",
            ai_model="model-one",
            instruction_version="scene-v1",
        )
        database.set_work_scene_notes(scene_id, "  재검수 완료  ")
        database.set_work_scene_decision(scene_id, "채택")

        # 같은 관계·장면을 다시 저장하면 스냅샷만 갱신된다
        assert (
            _add_work_scene(
                database,
                relation.id,
                segment_public_id="anonymous-segment-001",
                japanese_text="あの、大丈夫ですか？",
                episode=7,
            )
            == scene_id
        )
        assert database.connection.execute("SELECT COUNT(*) FROM work_scenes").fetchone()[0] == 1

        updated = database.get_work_scene(relation.id, "anonymous-segment-001")
        assert updated is not None
        assert updated.japanese_text == "あの、大丈夫ですか？"
        assert updated.episode == 7
        assert updated.decision == "채택"
        assert updated.direct_meaning == "괜찮습니까?"
        assert updated.natural_translation == "괜찮아요?"
        assert updated.scene_usage == "상대의 상태를 확인함"
        assert updated.translation_ai_service == "provider-one"
        assert updated.translation_ai_model == "model-one"
        assert updated.translation_instruction_version == "scene-v1"
        assert updated.translated_at is not None
        assert updated.notes == "재검수 완료"
        assert updated.has_translation is True

        # 메모만 비워도 판정과 번역은 남는다
        database.set_work_scene_notes(scene_id, "   ")
        cleared = database.get_work_scene(relation.id, "anonymous-segment-001")
        assert cleared is not None
        assert cleared.notes is None
        assert cleared.decision == "채택"
        assert cleared.natural_translation == "괜찮아요?"

    with SceneCollectorDatabase.open(settings) as reopened:
        reopened_scene = reopened.get_work_scene(relation.id, "anonymous-segment-001")
        assert reopened_scene is not None
        assert reopened_scene.decision == "채택"
        assert reopened_scene.natural_translation == "괜찮아요?"


def test_work_scene_rejects_unknown_relation_scene_and_decision(tmp_path: Path) -> None:
    with SceneCollectorDatabase.open(_settings(tmp_path)) as database:
        relation = _add_relation(
            database,
            "괜찮냐고 묻는 말",
            japanese="大丈夫ですか",
            reading="だいじょうぶですか",
            meaning_ko="괜찮으세요?",
            register_text="정중",
        )

        with pytest.raises(DatabaseError, match="표현 연결을 찾을 수 없습니다"):
            _add_work_scene(database, 9999, segment_public_id="anonymous-segment-001")
        with pytest.raises(ValueError, match="장면 ID"):
            _add_work_scene(database, relation.id, segment_public_id="   ")

        scene_id = _add_work_scene(
            database, relation.id, segment_public_id="anonymous-segment-001"
        )
        with pytest.raises(ValueError, match="채택, 예비, 제외"):
            database.set_work_scene_decision(scene_id, "보류")  # type: ignore[arg-type]
        with pytest.raises(DatabaseError, match="갱신할 작업 장면"):
            database.set_work_scene_decision(9999, "채택")
        with pytest.raises(DatabaseError, match="갱신할 작업 장면"):
            database.set_work_scene_notes(9999, "메모")

        assert database.get_work_scene(relation.id, "없는 장면") is None
        assert database.get_work_scene(9999, "anonymous-segment-001") is None
        assert database.list_work_scenes(9999) == ()


def test_accepted_scenes_are_listed_per_relation_and_survive_reopen(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    with SceneCollectorDatabase.open(settings) as database:
        asking = _add_relation(
            database,
            "괜찮냐고 묻는 말",
            japanese="大丈夫ですか",
            reading="だいじょうぶですか",
            meaning_ko="괜찮으세요?",
            register_text="정중",
        )
        thanking = _add_relation(
            database,
            "고맙다고 말하기",
            japanese="ありがとう",
            reading="ありがとう",
            meaning_ko="고마워",
            register_text="반말",
        )
        # 같은 장면을 두 관계에서 채택하고, 한 관계에서만 다른 장면을 제외한다
        shared_for_asking = _add_work_scene(
            database,
            asking.id,
            segment_public_id="segment-shared",
            japanese_text="大丈夫ですか、ありがとう。",
        )
        shared_for_thanking = _add_work_scene(
            database,
            thanking.id,
            segment_public_id="segment-shared",
            japanese_text="大丈夫ですか、ありがとう。",
        )
        excluded = _add_work_scene(database, asking.id, segment_public_id="segment-only-a")
        assert shared_for_asking != shared_for_thanking

        database.set_work_scene_decision(shared_for_asking, "채택")
        database.set_work_scene_decision(shared_for_thanking, "채택")
        database.set_work_scene_decision(excluded, "제외")

        assert [scene.segment_public_id for scene in database.list_work_scenes(asking.id)] == [
            "segment-shared",
            "segment-only-a",
        ]
        assert [scene.segment_public_id for scene in database.list_work_scenes(thanking.id)] == [
            "segment-shared"
        ]

    with SceneCollectorDatabase.open(settings) as reopened:
        rows = reopened.list_accepted_work_scenes()
        assert [
            (row.korean_meaning, row.japanese, row.segment_public_id) for row in rows
        ] == [
            ("괜찮냐고 묻는 말", "大丈夫ですか", "segment-shared"),
            ("고맙다고 말하기", "ありがとう", "segment-shared"),
        ]
        assert all(row.decision == "채택" for row in rows)
        assert (rows[0].reading, rows[0].meaning_ko, rows[0].register_text) == (
            "だいじょうぶですか",
            "괜찮으세요?",
            "정중",
        )
        assert rows[1].meaning_ko == "고마워"
        assert rows[0].media_public_id == "anonymous-media-001"
        assert rows[0].media_display_name == "익명 작품"
        assert rows[0].japanese_text == "大丈夫ですか、ありがとう。"
        assert rows[0].natural_translation is None


# ----------------------------------------------------------------------
# 빈 작업 장면 정리
# ----------------------------------------------------------------------


def test_empty_work_scene_is_deleted_and_recreated_by_the_next_upsert(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    with SceneCollectorDatabase.open(settings) as database:
        relation = _add_relation(
            database,
            "괜찮냐고 묻는 말",
            japanese="大丈夫ですか",
            reading="だいじょうぶですか",
            meaning_ko="괜찮으세요?",
            register_text="정중",
        )
        empty_id = _add_work_scene(
            database, relation.id, segment_public_id="anonymous-segment-001"
        )
        # 뒤에 만든 행이 남아 있어야 재작업 때 예전 ID가 그대로 재사용되지 않는다
        kept_id = _add_work_scene(database, relation.id, segment_public_id="anonymous-segment-002")
        database.set_work_scene_notes(kept_id, "남겨둘 메모")

        assert database.delete_work_scene_if_empty(empty_id) is True
        assert database.get_work_scene(relation.id, "anonymous-segment-001") is None
        assert [scene.id for scene in database.list_work_scenes(relation.id)] == [kept_id]
        # 이미 지운 행을 다시 지우려 해도 조용히 False다
        assert database.delete_work_scene_if_empty(empty_id) is False

        # 같은 장면을 다시 작업하면 새 행으로 되살아난다
        recreated_id = _add_work_scene(
            database, relation.id, segment_public_id="anonymous-segment-001"
        )
        assert recreated_id != empty_id
        recreated = database.get_work_scene(relation.id, "anonymous-segment-001")
        assert recreated is not None
        assert recreated.id == recreated_id
        assert recreated.decision is None
        assert recreated.notes is None
        assert recreated.has_translation is False

        database.set_work_scene_decision(recreated_id, "채택")

    with SceneCollectorDatabase.open(settings) as reopened:
        survivor = reopened.get_work_scene(relation.id, "anonymous-segment-001")
        assert survivor is not None
        assert survivor.decision == "채택"
        assert reopened.connection.execute("SELECT COUNT(*) FROM work_scenes").fetchone()[0] == 2


def test_work_scene_that_has_only_a_decision_is_not_deleted(tmp_path: Path) -> None:
    with SceneCollectorDatabase.open(_settings(tmp_path)) as database:
        relation = _add_relation(
            database,
            "괜찮냐고 묻는 말",
            japanese="大丈夫ですか",
            reading="だいじょうぶですか",
            meaning_ko="괜찮으세요?",
            register_text="정중",
        )
        scene_id = _add_work_scene(
            database, relation.id, segment_public_id="anonymous-segment-001"
        )
        database.set_work_scene_decision(scene_id, "제외")

        assert database.delete_work_scene_if_empty(scene_id) is False
        kept = database.get_work_scene(relation.id, "anonymous-segment-001")
        assert kept is not None
        assert kept.id == scene_id
        assert kept.decision == "제외"


def test_work_scene_that_has_only_notes_is_not_deleted(tmp_path: Path) -> None:
    with SceneCollectorDatabase.open(_settings(tmp_path)) as database:
        relation = _add_relation(
            database,
            "괜찮냐고 묻는 말",
            japanese="大丈夫ですか",
            reading="だいじょうぶですか",
            meaning_ko="괜찮으세요?",
            register_text="정중",
        )
        scene_id = _add_work_scene(
            database, relation.id, segment_public_id="anonymous-segment-001"
        )
        database.set_work_scene_notes(scene_id, "메모만 있는 장면")

        assert database.delete_work_scene_if_empty(scene_id) is False
        kept = database.get_work_scene(relation.id, "anonymous-segment-001")
        assert kept is not None
        assert kept.decision is None
        assert kept.notes == "메모만 있는 장면"


def test_work_scene_that_has_only_a_translation_is_not_deleted(tmp_path: Path) -> None:
    with SceneCollectorDatabase.open(_settings(tmp_path)) as database:
        relation = _add_relation(
            database,
            "괜찮냐고 묻는 말",
            japanese="大丈夫ですか",
            reading="だいじょうぶですか",
            meaning_ko="괜찮으세요?",
            register_text="정중",
        )
        scene_id = _add_work_scene(
            database, relation.id, segment_public_id="anonymous-segment-001"
        )
        database.save_work_scene_translation(
            scene_id,
            direct_meaning="괜찮습니까?",
            natural_translation="괜찮아요?",
            scene_usage="상대의 상태를 확인함",
            ai_service="provider-one",
            ai_model="model-one",
            instruction_version="scene-v1",
        )

        assert database.delete_work_scene_if_empty(scene_id) is False
        kept = database.get_work_scene(relation.id, "anonymous-segment-001")
        assert kept is not None
        assert kept.decision is None
        assert kept.notes is None
        assert kept.has_translation is True
        assert kept.natural_translation == "괜찮아요?"


@pytest.mark.parametrize(
    ("column", "value"),
    [
        ("decision", "예비"),
        ("notes", "메모"),
        ("direct_meaning", "괜찮습니까?"),
        ("natural_translation", "괜찮아요?"),
        ("scene_usage", "상대의 상태를 확인함"),
    ],
)
def test_single_filled_work_column_blocks_deletion(
    tmp_path: Path, column: str, value: str
) -> None:
    """작업 칸 중 하나만 채워져 있어도 그 행은 지우면 안 된다."""
    with SceneCollectorDatabase.open(_settings(tmp_path)) as database:
        relation = _add_relation(
            database,
            "괜찮냐고 묻는 말",
            japanese="大丈夫ですか",
            reading="だいじょうぶですか",
            meaning_ko="괜찮으세요?",
            register_text="정중",
        )
        scene_id = _add_work_scene(
            database, relation.id, segment_public_id="anonymous-segment-001"
        )
        with database.transaction() as connection:
            connection.execute(
                f"UPDATE work_scenes SET {column} = ? WHERE id = ?", (value, scene_id)
            )

        assert database.delete_work_scene_if_empty(scene_id) is False
        assert (
            database.connection.execute(
                f"SELECT {column} FROM work_scenes WHERE id = ?", (scene_id,)
            ).fetchone()[0]
            == value
        )


def test_delete_work_scene_if_empty_ignores_unknown_id(tmp_path: Path) -> None:
    with SceneCollectorDatabase.open(_settings(tmp_path)) as database:
        assert database.delete_work_scene_if_empty(9999) is False
        assert database.connection.execute("SELECT COUNT(*) FROM work_scenes").fetchone()[0] == 0


def test_delete_work_scene_if_empty_touches_only_the_target_row(tmp_path: Path) -> None:
    with SceneCollectorDatabase.open(_settings(tmp_path)) as database:
        asking = _add_relation(
            database,
            "괜찮냐고 묻는 말",
            japanese="大丈夫ですか",
            reading="だいじょうぶですか",
            meaning_ko="괜찮으세요?",
            register_text="정중",
        )
        thanking = _add_relation(
            database,
            "고맙다고 말하기",
            japanese="ありがとう",
            reading="ありがとう",
            meaning_ko="고마워",
            register_text="반말",
        )
        target = _add_work_scene(database, asking.id, segment_public_id="segment-empty")
        sibling = _add_work_scene(database, asking.id, segment_public_id="segment-sibling")
        database.set_work_scene_decision(sibling, "채택")
        # 같은 장면 ID를 쓰는 다른 관계의 빈 행도 그대로 남아야 한다
        other_relation_row = _add_work_scene(
            database, thanking.id, segment_public_id="segment-empty"
        )

        assert database.delete_work_scene_if_empty(target) is True

        assert [scene.segment_public_id for scene in database.list_work_scenes(asking.id)] == [
            "segment-sibling"
        ]
        assert [scene.id for scene in database.list_work_scenes(thanking.id)] == [
            other_relation_row
        ]
        remaining = database.get_work_scene(asking.id, "segment-sibling")
        assert remaining is not None
        assert remaining.decision == "채택"
        assert database.connection.execute("SELECT COUNT(*) FROM work_scenes").fetchone()[0] == 2


# ----------------------------------------------------------------------
# 옛 DB migration
# ----------------------------------------------------------------------


def _insert_old_segment(
    connection: sqlite3.Connection,
    segment_id: int,
    public_id: str,
    *,
    japanese_text: str,
) -> None:
    connection.execute(
        """
        INSERT INTO segments (
            id, nadeshiko_segment_id, media_id, position, episode,
            start_time_ms, end_time_ms, external_video_id, japanese_text,
            video_url, audio_url, image_url, raw_json
        ) VALUES (
            ?, ?, 1, ?, 1, ?, ?, NULL, ?,
            'https://media.example.invalid/video.mp4',
            'https://media.example.invalid/audio.mp3',
            'https://media.example.invalid/image.jpg', '{}'
        )
        """,
        (
            segment_id,
            public_id,
            segment_id * 10,
            segment_id * 1000,
            segment_id * 1000 + 900,
            japanese_text,
        ),
    )


def _create_seeded_v1_database(path: Path) -> None:
    """검색 이력 1건과 검수 1건이 있는 옛 v1 DB를 만든다."""
    connection = sqlite3.connect(path)
    try:
        with connection:
            for statement in (
                V1_MEDIA_DDL,
                OLD_SEARCH_RUNS_DDL,
                OLD_EXPRESSIONS_DDL,
                OLD_SEGMENTS_DDL,
                OLD_EXPRESSION_SEGMENTS_DDL,
                V1_REVIEWS_DDL,
                OLD_AI_CACHE_DDL,
                OLD_SEARCH_CACHE_DDL,
            ):
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
                ) VALUES (1, '괜찮냐고 묻는 말?', 'past', 'service', 'model', 'candidate-v1')
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
            _insert_old_segment(
                connection, 1, "anonymous-segment-001", japanese_text="大丈夫ですか？"
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


def _create_seeded_v3_database(path: Path) -> None:
    """작품·로컬 자막·검색 이력·검수가 모두 있는 옛 v3 DB를 만든다.

    같은 일본어 표현이 서로 다른 두 한국어 의도에 저장돼 있고, 실제 작업이
    없는 검수(판정·번역·메모 모두 없음)도 한 건 들어 있다.
    """
    connection = sqlite3.connect(path)
    try:
        with connection:
            for statement in (
                database_module._media_table_ddl("media"),
                database_module._LOCAL_SEGMENTS_TABLE_DDL,
                OLD_SEARCH_RUNS_DDL,
                OLD_EXPRESSIONS_DDL,
                OLD_SEGMENTS_DDL,
                OLD_EXPRESSION_SEGMENTS_DDL,
                database_module._reviews_table_ddl("reviews"),
                OLD_AI_CACHE_DDL,
                OLD_SEARCH_CACHE_DDL,
                database_module._CONTEXT_CACHE_TABLE_DDL,
            ):
                connection.execute(statement)
            connection.execute(
                """
                INSERT INTO media (
                    id, nadeshiko_media_id, display_name, preference,
                    content_group, is_active, source
                ) VALUES (1, 'anonymous-media-001', '익명 작품', 4, '극장판', 0, 'nadeshiko')
                """
            )
            connection.execute(
                """
                INSERT INTO media (id, nadeshiko_media_id, display_name, source)
                VALUES (2, NULL, '로컬 작품', 'local')
                """
            )
            connection.execute(
                """
                INSERT INTO local_segments (
                    media_id, episode, position, start_time_ms, end_time_ms,
                    japanese_text, normalized_text, source_file
                ) VALUES (2, 1, 1, 0, 900, '大丈夫ですか？', '大丈夫ですか？', 'ep01.srt')
                """
            )
            connection.executemany(
                """
                INSERT INTO search_runs (
                    id, korean_intent, created_at, ai_service, ai_model, instruction_version
                ) VALUES (?, ?, 'past', 'service', 'model', 'candidate-v1')
                """,
                ((1, "괜찮냐고 묻는 말?"), (2, "몸 상태를 확인하는 말")),
            )
            connection.executemany(
                """
                INSERT INTO expressions (
                    id, search_run_id, ordinal, japanese, reading,
                    meaning_ko, register_text, is_selected
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 0)
                """,
                (
                    (1, 1, 0, "大丈夫ですか", "だいじょうぶですか", "괜찮으세요?", "정중"),
                    (2, 1, 1, "平気ですか", "へいきですか", "멀쩡해요?", "담담"),
                    (3, 2, 0, "大丈夫ですか", "だいじょうぶですか", "몸은 괜찮나요?", "다정"),
                ),
            )
            _insert_old_segment(
                connection, 1, "anonymous-segment-001", japanese_text="大丈夫ですか？"
            )
            _insert_old_segment(
                connection, 2, "anonymous-segment-002", japanese_text="平気ですか？"
            )
            connection.executemany(
                "INSERT INTO expression_segments (expression_id, segment_id, ordinal)"
                " VALUES (?, ?, 0)",
                ((1, 1), (2, 2), (3, 1)),
            )
            connection.execute(
                """
                INSERT INTO reviews (
                    expression_id, segment_id, decision, direct_meaning,
                    natural_translation, scene_usage, notes, translation_ai_service,
                    translation_ai_model, translation_instruction_version,
                    translated_at, updated_at
                ) VALUES (
                    1, 1, '채택', '괜찮습니까?', '괜찮아요?', '상태 확인', '메모',
                    'provider-one', 'model-one', 'scene-v1', 'past', 'past'
                )
                """
            )
            connection.execute(
                """
                INSERT INTO reviews (expression_id, segment_id, notes, updated_at)
                VALUES (3, 1, '다른 의미의 메모', 'past')
                """
            )
            # 판정·번역·메모가 없는 검수는 실제 작업이 아니다
            connection.execute(
                "INSERT INTO reviews (expression_id, segment_id, updated_at)"
                " VALUES (2, 2, 'past')"
            )
            # 메모 칸이 공백뿐인 검수도 실제 작업이 아니다
            connection.execute(
                "INSERT INTO reviews (expression_id, segment_id, notes, updated_at)"
                " VALUES (2, 1, '   ', 'past')"
            )
            connection.execute("PRAGMA user_version = 3")
    finally:
        connection.close()


def test_v1_database_migrates_to_v4_with_stepwise_backups(tmp_path: Path) -> None:
    path = tmp_path / DATABASE_FILENAME
    _create_seeded_v1_database(path)

    with SceneCollectorDatabase.open(_settings(tmp_path)) as database:
        assert database.schema_version == SCHEMA_VERSION == 4
        assert _table_names(database.connection) == EXPECTED_TABLES

        media = database.get_media("anonymous-media-001")
        assert media is not None
        assert media.source == "nadeshiko"
        assert media.display_name == "익명 작품"
        assert (
            database.connection.execute("SELECT COUNT(*) FROM local_segments").fetchone()[0] == 0
        )

        meaning = database.find_meaning("괜찮냐고 묻는 말")
        assert meaning is not None
        assert meaning.display_korean_meaning == "괜찮냐고 묻는 말?"
        relations = database.list_meaning_expressions(meaning.id)
        assert [relation.japanese for relation in relations] == ["大丈夫ですか"]
        assert relations[0].reading == "だいじょうぶですか"
        assert relations[0].meaning_ko == "괜찮으세요?"
        assert relations[0].register_text == "정중"

        scene = database.get_work_scene(relations[0].id, "anonymous-segment-001")
        assert scene is not None
        assert scene.decision == "채택"
        assert scene.direct_meaning == "괜찮습니까?"
        assert scene.natural_translation == "괜찮아요?"
        assert scene.scene_usage == "상태 확인"
        assert scene.notes == "메모"
        assert scene.media_public_id == "anonymous-media-001"
        assert scene.media_display_name == "익명 작품"
        assert scene.episode == 1
        assert scene.japanese_text == "大丈夫ですか？"
        # v1에는 없던 번역 출처 정보는 비어 있다
        assert scene.translation_ai_service is None
        assert scene.translation_ai_model is None
        assert scene.translation_instruction_version is None
        assert scene.translated_at is None
        assert database.connection.execute("PRAGMA foreign_key_check").fetchall() == []

    v1_backups = sorted(tmp_path.glob("*.pre-schema-v1.*"))
    v2_backups = sorted(tmp_path.glob("*.pre-schema-v2.*"))
    v3_backups = sorted(tmp_path.glob("*.pre-schema-v3.*"))
    assert len(v1_backups) == len(v2_backups) == len(v3_backups) == 1
    with sqlite3.connect(v1_backups[0]) as backup:
        assert backup.execute("PRAGMA user_version").fetchone()[0] == 1
        assert backup.execute("SELECT decision FROM reviews").fetchone()[0] == "채택"
    with sqlite3.connect(v2_backups[0]) as backup:
        assert backup.execute("PRAGMA user_version").fetchone()[0] == 2
    with sqlite3.connect(v3_backups[0]) as backup:
        assert backup.execute("PRAGMA user_version").fetchone()[0] == 3
        assert backup.execute("SELECT COUNT(*) FROM segments").fetchone()[0] == 1

    with SceneCollectorDatabase.open(_settings(tmp_path)) as reopened:
        assert reopened.schema_version == SCHEMA_VERSION
    # 이미 옮긴 DB를 다시 열 때는 백업을 새로 만들지 않는다
    assert len(sorted(tmp_path.glob("*.pre-schema-v1.*"))) == 1
    assert len(sorted(tmp_path.glob("*.pre-schema-v2.*"))) == 1
    assert len(sorted(tmp_path.glob("*.pre-schema-v3.*"))) == 1


def test_v3_database_migrates_to_v4_keeping_assets_and_dropping_search_history(
    tmp_path: Path,
) -> None:
    path = tmp_path / DATABASE_FILENAME
    _create_seeded_v3_database(path)

    with SceneCollectorDatabase.open(_settings(tmp_path)) as database:
        assert database.schema_version == SCHEMA_VERSION == 4
        # 검색 이력·검색 결과 장면·캐시 table은 모두 사라진다
        assert _table_names(database.connection) == EXPECTED_TABLES

        media = database.get_media("anonymous-media-001")
        assert media is not None
        assert media.preference == 4
        assert media.content_group == "극장판"
        assert media.is_active is False
        local = database.find_local_media("로컬 작품")
        assert local is not None
        assert (
            len(
                database.find_local_segments(
                    normalized_surface="大丈夫ですか", media_row_ids=[local.id]
                )
            )
            == 1
        )

        # 같은 일본어 표현이 두 의미에 연결되고 표현 자체는 하나만 남는다
        assert database.connection.execute("SELECT COUNT(*) FROM expressions").fetchone()[0] == 2
        asking = database.find_expressions_for_meaning("괜찮냐고 묻는 말")
        checking = database.find_expressions_for_meaning("몸 상태를 확인하는 말")
        assert [relation.japanese for relation in asking] == ["大丈夫ですか", "平気ですか"]
        assert [relation.japanese for relation in checking] == ["大丈夫ですか"]
        assert asking[0].expression_id == checking[0].expression_id
        assert asking[0].meaning_ko == "괜찮으세요?"
        assert asking[0].register_text == "정중"
        assert checking[0].meaning_ko == "몸은 괜찮나요?"
        assert checking[0].register_text == "다정"

        # 판정·번역·메모가 있는 작업만 남는다
        accepted = database.get_work_scene(asking[0].id, "anonymous-segment-001")
        assert accepted is not None
        assert accepted.decision == "채택"
        assert accepted.direct_meaning == "괜찮습니까?"
        assert accepted.natural_translation == "괜찮아요?"
        assert accepted.scene_usage == "상태 확인"
        assert accepted.notes == "메모"
        assert accepted.translation_ai_service == "provider-one"
        assert accepted.translation_ai_model == "model-one"
        assert accepted.translation_instruction_version == "scene-v1"
        assert accepted.media_public_id == "anonymous-media-001"

        note_only = database.get_work_scene(checking[0].id, "anonymous-segment-001")
        assert note_only is not None
        assert note_only.decision is None
        assert note_only.notes == "다른 의미의 메모"
        assert note_only.has_translation is False

        # 실제 작업이 없던 검수는 옮기지 않는다
        assert database.list_work_scenes(asking[1].id) == ()
        assert database.connection.execute("SELECT COUNT(*) FROM work_scenes").fetchone()[0] == 2

        accepted_rows = database.list_accepted_work_scenes()
        assert [row.korean_meaning for row in accepted_rows] == ["괜찮냐고 묻는 말?"]
        assert database.connection.execute("PRAGMA foreign_key_check").fetchall() == []

    assert len(sorted(tmp_path.glob("*.pre-schema-v3.*"))) == 1


def test_v3_migration_failure_keeps_original_v3_data(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / DATABASE_FILENAME
    _create_seeded_v3_database(path)
    statements = database_module._V3_TO_V4_DROP_STATEMENTS
    monkeypatch.setattr(
        database_module,
        "_V3_TO_V4_DROP_STATEMENTS",
        (*statements[:4], "CREATE TABLE broken (", *statements[4:]),
    )

    with pytest.raises(DatabaseError, match="v3 → v4 migration"):
        SceneCollectorDatabase.open(_settings(tmp_path))

    with sqlite3.connect(path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 3
        tables = _table_names(connection)
        assert {
            "expression_segments",
            "expressions",
            "reviews",
            "search_runs",
            "segments",
        } <= tables
        assert "meanings" not in tables
        assert "meaning_expressions" not in tables
        assert "work_scenes" not in tables
        assert "expressions_v4" not in tables
        assert connection.execute("SELECT COUNT(*) FROM expressions").fetchone()[0] == 3
        row = connection.execute(
            "SELECT decision, notes FROM reviews WHERE expression_id = 1"
        ).fetchone()
        assert tuple(row) == ("채택", "메모")


def test_v2_migration_failure_keeps_original_v2_data(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / DATABASE_FILENAME
    _create_seeded_v1_database(path)
    statements = database_module._V2_TO_V3_STATEMENTS
    monkeypatch.setattr(
        database_module,
        "_V2_TO_V3_STATEMENTS",
        (*statements[:4], "CREATE TABLE broken (", *statements[4:]),
    )

    with pytest.raises(DatabaseError, match="v2 → v3 migration"):
        SceneCollectorDatabase.open(_settings(tmp_path))

    with sqlite3.connect(path) as connection:
        # v1 → v2까지만 진행된 상태로 남는다
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 2
        tables = _table_names(connection)
        assert "media" in tables
        assert "media_v3" not in tables
        assert "local_segments" not in tables
        row = connection.execute("SELECT nadeshiko_media_id, display_name FROM media").fetchone()
        assert tuple(row) == ("anonymous-media-001", "익명 작품")
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

    with pytest.raises(DatabaseError, match="v1 → v2 migration"):
        SceneCollectorDatabase.open(_settings(tmp_path))

    with sqlite3.connect(path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 1
        tables = _table_names(connection)
        assert "reviews" in tables
        assert "reviews_v2" not in tables
        assert "nadeshiko_context_cache" not in tables
        row = connection.execute("SELECT decision, notes FROM reviews").fetchone()
        assert tuple(row) == ("채택", "메모")


def test_normalize_work_scene_notes_treats_invisible_text_as_no_note() -> None:
    """공백과 폭 없는 문자만 남은 메모는 메모 없음으로 본다."""
    for blank in ("", "   ", "\t\n", "\u3000", "\u00a0", "\u200b", "\ufeff", " \u200b\t"):
        assert normalize_work_scene_notes(blank) is None
    assert normalize_work_scene_notes(None) is None
    assert normalize_work_scene_notes("도입부 후보") == "도입부 후보"
    assert normalize_work_scene_notes("\u200b 도입부 후보 \u3000") == "도입부 후보"
    # 안쪽 공백은 사용자가 쓴 그대로 둔다.
    assert normalize_work_scene_notes(" 앞  뒤 ") == "앞  뒤"


def test_blank_note_is_stored_as_no_note_and_row_can_be_cleaned(tmp_path: Path) -> None:
    """공백뿐인 메모를 저장하면 메모 없음이 되고, 그 행은 빈 행으로 정리된다."""
    settings = _settings(tmp_path)
    with SceneCollectorDatabase.open(settings) as database:
        meaning = database.upsert_meaning("괜찮냐고 묻는 말")
        relation = database.add_meaning_expression(
            meaning.id,
            japanese="大丈夫ですか",
            reading="だいじょうぶですか",
            meaning_ko="괜찮으세요?",
            register_text="존댓말",
        )
        work_scene_id = database.upsert_work_scene(
            relation.id,
            segment_public_id="segment-a",
            media_public_id="anonymous-media-001",
            media_display_name="테스트 작품",
            episode=1,
            start_time_ms=1_000,
            end_time_ms=3_000,
            japanese_text="あの、大丈夫ですか？",
        )

        database.set_work_scene_notes(work_scene_id, "\u200b   ")
        stored = database.get_work_scene(relation.id, "segment-a")
        assert stored is not None and stored.notes is None
        assert database.delete_work_scene_if_empty(work_scene_id) is True
        assert database.list_work_scenes(relation.id) == ()
