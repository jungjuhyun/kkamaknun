"""SQLite에 장면 수집기의 표현 자산과 실제 작업 장면을 저장한다.

저장 대상은 사용자의 작업 자산뿐이다.

- 작품 상태: media, local_segments
- 표현 자산: meanings ↔ meaning_expressions ↔ expressions
- 실제 작업: work_scenes (판정·번역·메모가 실제로 발생한 장면만)

Nadeshiko 검색 응답·문맥 응답·AI 응답은 캐시하거나 영구 저장하지 않는다.
영상 주소도 저장하지 않고, 필요할 때 segment_public_id로 다시 조회한다.
"""

from __future__ import annotations

import re
import sqlite3
import unicodedata
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Literal
from uuid import uuid4

from scene_collector.config import AppSettings
from scene_collector.surface import _normalize_source

if TYPE_CHECKING:
    from scene_collector.subtitles import SubtitleCue

DATABASE_FILENAME = "scene_collector.sqlite3"
SCHEMA_VERSION = 4

ReviewDecision = Literal["채택", "예비", "제외"]

_LOCKED_SQLITE_ERROR_CODES = frozenset({sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED})
_LOCKED_MESSAGE = (
    "작업 데이터베이스를 사용할 수 없습니다. 다른 프로그램이나 작업이 사용 중인지 확인하세요."
)

# 한국어 의미 정규화: NFKC → 공백 정리 → 끝의 단순 문장부호 제거까지만 한다.
_MEANING_TERMINAL_PUNCTUATION = "?!.？！．。"
_WHITESPACE_RUN = re.compile(r"\s+")


def _raise_if_locked(error: sqlite3.OperationalError) -> None:
    """DB 잠김(BUSY/LOCKED)만 사용자용 DatabaseError로 바꾼다. 그 외는 그대로 둔다."""
    if getattr(error, "sqlite_errorcode", None) in _LOCKED_SQLITE_ERROR_CODES:
        raise DatabaseError(_LOCKED_MESSAGE) from error


class DatabaseError(RuntimeError):
    """로컬 데이터베이스를 안전하게 사용할 수 없을 때 발생한다."""


class UnsupportedSchemaVersionError(DatabaseError):
    """DB 스키마가 현재 코드보다 새 버전일 때 발생한다."""


def normalize_korean_meaning(text: str) -> str:
    """한국어 의미를 조회 키로 쓸 수 있게 최소한으로만 정규화한다.

    NFKC → 양끝 공백 제거 → 연속 공백 축약 → 끝의 단순 문장부호 제거.
    형태소 분석이나 의미 자동 병합은 하지 않는다.
    """
    normalized = unicodedata.normalize("NFKC", text or "")
    normalized = _WHITESPACE_RUN.sub(" ", normalized).strip()
    return normalized.rstrip(_MEANING_TERMINAL_PUNCTUATION).strip()


@dataclass(frozen=True)
class StoredMedia:
    """로컬에 저장된 사용자 선호 작품 상태.

    source가 'nadeshiko'면 nadeshiko_media_id가 있고, 사용자가 등록한
    로컬 자막 작품('local')이면 nadeshiko_media_id는 None이다.
    """

    id: int
    nadeshiko_media_id: str | None
    display_name: str | None
    preference: int | None
    content_group: str | None
    is_active: bool
    source: str


@dataclass(frozen=True)
class LocalSegmentMatch:
    """로컬 자막 색인에서 찾은 장면과 소속 작품 표시명."""

    id: int
    media_id: int
    media_display_name: str | None
    episode: int | None
    position: int
    start_time_ms: int
    end_time_ms: int
    japanese_text: str
    source_file: str


@dataclass(frozen=True)
class StoredMeaning:
    """사용자가 입력한 한국어 의미."""

    id: int
    normalized_korean_meaning: str
    display_korean_meaning: str


@dataclass(frozen=True)
class StoredMeaningExpression:
    """한국어 의미와 일본어 표현의 연결. 뜻·말투는 이 관계에 속한다.

    같은 일본어 표현이 여러 한국어 의미에 연결될 수 있고 의미마다 설명이
    다를 수 있으므로 meaning_ko와 register_text는 표현이 아니라 관계에 둔다.
    """

    id: int
    meaning_id: int
    expression_id: int
    japanese: str
    reading: str
    meaning_ko: str
    register_text: str


@dataclass(frozen=True)
class StoredWorkScene:
    """실제로 작업한 장면. 판정·번역·메모 중 하나라도 있을 때만 존재한다."""

    id: int
    meaning_expression_id: int
    segment_public_id: str
    media_public_id: str | None
    media_display_name: str | None
    episode: int | None
    start_time_ms: int
    end_time_ms: int
    japanese_text: str
    decision: ReviewDecision | None
    direct_meaning: str | None
    natural_translation: str | None
    scene_usage: str | None
    translation_ai_service: str | None
    translation_ai_model: str | None
    translation_instruction_version: str | None
    translated_at: str | None
    notes: str | None
    updated_at: str

    @property
    def has_translation(self) -> bool:
        return self.natural_translation is not None


@dataclass(frozen=True)
class AcceptedSceneExportRow:
    """제작 내보내기용으로 조립한 채택 작업 장면 한 건."""

    korean_meaning: str
    japanese: str
    reading: str
    meaning_ko: str
    register_text: str
    segment_public_id: str
    media_public_id: str | None
    media_display_name: str | None
    episode: int | None
    start_time_ms: int
    end_time_ms: int
    japanese_text: str
    direct_meaning: str | None
    natural_translation: str | None
    scene_usage: str | None
    notes: str | None
    decision: str


def _media_table_ddl(table_name: str) -> str:
    """새로 생성하는 media와 migration 중간 table이 같은 구조를 쓰게 한다."""
    return f"""
    CREATE TABLE {table_name} (
        id INTEGER PRIMARY KEY,
        nadeshiko_media_id TEXT UNIQUE,
        display_name TEXT,
        preference INTEGER,
        content_group TEXT,
        is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
        source TEXT NOT NULL DEFAULT 'nadeshiko'
            CHECK (source IN ('nadeshiko', 'local')),
        CHECK ((nadeshiko_media_id IS NOT NULL) = (source = 'nadeshiko'))
    )
    """


_LOCAL_SEGMENTS_TABLE_DDL = """
    CREATE TABLE local_segments (
        id INTEGER PRIMARY KEY,
        media_id INTEGER NOT NULL,
        episode INTEGER,
        position INTEGER NOT NULL,
        start_time_ms INTEGER NOT NULL CHECK (start_time_ms >= 0),
        end_time_ms INTEGER NOT NULL CHECK (end_time_ms >= start_time_ms),
        japanese_text TEXT NOT NULL,
        normalized_text TEXT NOT NULL,
        source_file TEXT NOT NULL,
        FOREIGN KEY (media_id) REFERENCES media(id) ON DELETE CASCADE
    )
    """


_MEANINGS_TABLE_DDL = """
    CREATE TABLE meanings (
        id INTEGER PRIMARY KEY,
        normalized_korean_meaning TEXT NOT NULL UNIQUE,
        display_korean_meaning TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    """


def _expressions_table_ddl(table_name: str) -> str:
    """표현 자체만 담는다. 의미별 뜻·말투는 meaning_expressions에 둔다."""
    return f"""
    CREATE TABLE {table_name} (
        id INTEGER PRIMARY KEY,
        japanese TEXT NOT NULL UNIQUE,
        reading TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    """


def _meaning_expressions_table_ddl(expressions_table: str) -> str:
    return f"""
    CREATE TABLE meaning_expressions (
        id INTEGER PRIMARY KEY,
        meaning_id INTEGER NOT NULL,
        expression_id INTEGER NOT NULL,
        meaning_ko TEXT NOT NULL,
        register_text TEXT NOT NULL,
        created_at TEXT NOT NULL,
        UNIQUE (meaning_id, expression_id),
        FOREIGN KEY (meaning_id) REFERENCES meanings(id) ON DELETE CASCADE,
        FOREIGN KEY (expression_id) REFERENCES {expressions_table}(id) ON DELETE CASCADE
    )
    """


_WORK_SCENES_TABLE_DDL = """
    CREATE TABLE work_scenes (
        id INTEGER PRIMARY KEY,
        meaning_expression_id INTEGER NOT NULL,
        segment_public_id TEXT NOT NULL,
        media_public_id TEXT,
        media_display_name TEXT,
        episode INTEGER,
        start_time_ms INTEGER NOT NULL CHECK (start_time_ms >= 0),
        end_time_ms INTEGER NOT NULL CHECK (end_time_ms >= start_time_ms),
        japanese_text TEXT NOT NULL,
        decision TEXT CHECK (decision IN ('채택', '예비', '제외')),
        direct_meaning TEXT,
        natural_translation TEXT,
        scene_usage TEXT,
        translation_ai_service TEXT,
        translation_ai_model TEXT,
        translation_instruction_version TEXT,
        translated_at TEXT,
        notes TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        UNIQUE (meaning_expression_id, segment_public_id),
        FOREIGN KEY (meaning_expression_id)
            REFERENCES meaning_expressions(id) ON DELETE CASCADE
    )
    """


_SCHEMA_STATEMENTS = (
    _media_table_ddl("media"),
    _LOCAL_SEGMENTS_TABLE_DDL,
    _MEANINGS_TABLE_DDL,
    _expressions_table_ddl("expressions"),
    _meaning_expressions_table_ddl("expressions"),
    _WORK_SCENES_TABLE_DDL,
    "CREATE INDEX local_segments_media_idx ON local_segments(media_id)",
    "CREATE INDEX meaning_expressions_meaning_idx ON meaning_expressions(meaning_id)",
    "CREATE INDEX work_scenes_relation_idx ON work_scenes(meaning_expression_id)",
    "CREATE INDEX work_scenes_segment_idx ON work_scenes(segment_public_id)",
)


def _reviews_table_ddl(table_name: str) -> str:
    """v1 → v2 migration이 만드는 옛 reviews 구조(과거 DB 이동 전용)."""
    return f"""
    CREATE TABLE {table_name} (
        expression_id INTEGER NOT NULL,
        segment_id INTEGER NOT NULL,
        decision TEXT CHECK (decision IN ('채택', '예비', '제외')),
        direct_meaning TEXT,
        natural_translation TEXT,
        scene_usage TEXT,
        notes TEXT,
        translation_ai_service TEXT,
        translation_ai_model TEXT,
        translation_instruction_version TEXT,
        translation_input_hash TEXT,
        translated_at TEXT,
        updated_at TEXT NOT NULL,
        PRIMARY KEY (expression_id, segment_id),
        FOREIGN KEY (expression_id) REFERENCES expressions(id),
        FOREIGN KEY (segment_id) REFERENCES segments(id)
    )
    """


_CONTEXT_CACHE_TABLE_DDL = """
    CREATE TABLE nadeshiko_context_cache (
        segment_public_id TEXT NOT NULL,
        context_take INTEGER NOT NULL,
        response_json TEXT NOT NULL,
        created_at TEXT NOT NULL,
        PRIMARY KEY (segment_public_id, context_take)
    )
    """


# 과거 DB(v1/v2/v3)를 현재 구조로 옮기기 위한 migration 전용 문장들이다.
# 현재 제품이 이 구조를 다시 만들지는 않는다.
_V1_TO_V2_STATEMENTS = (
    _reviews_table_ddl("reviews_v2"),
    """
    INSERT INTO reviews_v2 (
        expression_id, segment_id, decision, direct_meaning,
        natural_translation, scene_usage, notes, updated_at
    )
    SELECT
        expression_id, segment_id, decision, direct_meaning,
        natural_translation, scene_usage, notes, updated_at
    FROM reviews
    """,
    "DROP TABLE reviews",
    "ALTER TABLE reviews_v2 RENAME TO reviews",
    _CONTEXT_CACHE_TABLE_DDL,
)

_V2_TO_V3_STATEMENTS = (
    _media_table_ddl("media_v3"),
    """
    INSERT INTO media_v3 (
        id, nadeshiko_media_id, display_name, preference, content_group, is_active, source
    )
    SELECT
        id, nadeshiko_media_id, display_name, preference, content_group, is_active, 'nadeshiko'
    FROM media
    """,
    "DROP TABLE media",
    "ALTER TABLE media_v3 RENAME TO media",
    _LOCAL_SEGMENTS_TABLE_DDL,
    "CREATE INDEX local_segments_media_idx ON local_segments(media_id)",
)

# v3 → v4: 표현 자산과 실제 작업만 남기고 검색 저장·캐시는 버린다.
_V3_TO_V4_CREATE_STATEMENTS = (
    _MEANINGS_TABLE_DDL,
    _expressions_table_ddl("expressions_v4"),
    _meaning_expressions_table_ddl("expressions_v4"),
    _WORK_SCENES_TABLE_DDL,
)

_V3_TO_V4_DROP_STATEMENTS = (
    "DROP TABLE IF EXISTS reviews",
    "DROP TABLE IF EXISTS expression_segments",
    "DROP TABLE IF EXISTS segments",
    "DROP TABLE IF EXISTS expressions",
    "DROP TABLE IF EXISTS search_runs",
    "DROP TABLE IF EXISTS ai_cache",
    "DROP TABLE IF EXISTS nadeshiko_search_cache",
    "DROP TABLE IF EXISTS nadeshiko_context_cache",
    "ALTER TABLE expressions_v4 RENAME TO expressions",
    "CREATE INDEX meaning_expressions_meaning_idx ON meaning_expressions(meaning_id)",
    "CREATE INDEX work_scenes_relation_idx ON work_scenes(meaning_expression_id)",
    "CREATE INDEX work_scenes_segment_idx ON work_scenes(segment_public_id)",
)

_EXPECTED_TABLES_V2 = frozenset(
    {
        "media",
        "search_runs",
        "expressions",
        "segments",
        "expression_segments",
        "reviews",
        "ai_cache",
        "nadeshiko_search_cache",
        "nadeshiko_context_cache",
    }
)
_EXPECTED_TABLES_V3 = _EXPECTED_TABLES_V2 | {"local_segments"}
_EXPECTED_TABLES = frozenset(
    {
        "media",
        "local_segments",
        "meanings",
        "expressions",
        "meaning_expressions",
        "work_scenes",
    }
)
_REVIEW_DECISIONS = frozenset({"채택", "예비", "제외"})
_MEDIA_COLUMNS = (
    "id, nadeshiko_media_id, display_name, preference, content_group, is_active, source"
)
_RELATION_COLUMNS = """
    meaning_expressions.id AS relation_id,
    meaning_expressions.meaning_id,
    meaning_expressions.expression_id,
    expressions.japanese,
    expressions.reading,
    meaning_expressions.meaning_ko,
    meaning_expressions.register_text
"""
_WORK_SCENE_COLUMNS = """
    id, meaning_expression_id, segment_public_id, media_public_id, media_display_name,
    episode, start_time_ms, end_time_ms, japanese_text, decision, direct_meaning,
    natural_translation, scene_usage, translation_ai_service, translation_ai_model,
    translation_instruction_version, translated_at, notes, updated_at
"""


def database_path(settings: AppSettings) -> Path:
    """설정의 작업 데이터 위치에 있는 DB 파일 경로를 만든다."""
    return settings.storage.work_data_dir / DATABASE_FILENAME


class SceneCollectorDatabase:
    """한 SQLite 연결에서 표현 자산과 실제 작업 장면을 관리한다."""

    def __init__(self, path: Path, connection: sqlite3.Connection) -> None:
        self.path = path
        self._connection: sqlite3.Connection | None = connection

    @classmethod
    def open(cls, settings: AppSettings) -> SceneCollectorDatabase:
        """설정의 작업 데이터 위치에서 DB를 열고 현재 schema를 보장한다."""
        path = database_path(settings)
        parent = path.parent
        if not parent.exists() or not parent.is_dir():
            raise DatabaseError("작업 데이터 디렉터리가 없어 데이터베이스를 열 수 없습니다.")

        try:
            connection = sqlite3.connect(path, isolation_level=None)
        except sqlite3.Error as error:
            raise DatabaseError("작업 데이터 디렉터리에서 데이터베이스를 열 수 없습니다.") from error

        database = cls(path, connection)
        try:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON")
            foreign_keys = connection.execute("PRAGMA foreign_keys").fetchone()
            if foreign_keys is None or foreign_keys[0] != 1:
                raise DatabaseError("SQLite foreign key 검사를 활성화할 수 없습니다.")
            database._ensure_schema()
        except BaseException:
            database.close()
            raise
        return database

    @property
    def connection(self) -> sqlite3.Connection:
        if self._connection is None:
            raise DatabaseError("이미 닫힌 데이터베이스 연결입니다.")
        return self._connection

    @property
    def schema_version(self) -> int:
        """현재 DB의 PRAGMA user_version 값을 반환한다."""
        try:
            row = self.connection.execute("PRAGMA user_version").fetchone()
        except sqlite3.OperationalError as error:
            _raise_if_locked(error)
            raise
        if row is None:
            raise DatabaseError("SQLite schema version을 읽을 수 없습니다.")
        return int(row[0])

    def __enter__(self) -> SceneCollectorDatabase:
        return self

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        self.close()

    def close(self) -> None:
        connection = self._connection
        if connection is not None and connection.in_transaction:
            connection.rollback()
        if connection is not None:
            connection.close()
        self._connection = None

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """명시적 transaction을 열고 실패하면 전체 변경을 rollback한다."""
        connection = self.connection
        if connection.in_transaction:
            raise DatabaseError("중첩된 데이터베이스 transaction은 지원하지 않습니다.")

        connection.execute("BEGIN")
        try:
            yield connection
        except sqlite3.OperationalError as error:
            if connection.in_transaction:
                connection.rollback()
            _raise_if_locked(error)
            raise
        except BaseException:
            if connection.in_transaction:
                connection.rollback()
            raise
        else:
            try:
                connection.commit()
            except sqlite3.OperationalError as error:
                if connection.in_transaction:
                    connection.rollback()
                _raise_if_locked(error)
                raise
            except BaseException:
                if connection.in_transaction:
                    connection.rollback()
                raise

    def backup_before_schema_change(self) -> Path:
        """구조를 바꾸기 전에 같은 작업 데이터 위치로 DB 사본을 만든다."""
        connection = self.connection
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        version = self.schema_version
        for attempt in range(100):
            suffix = "" if attempt == 0 else f".{uuid4().hex[:8]}"
            backup_path = self.path.with_name(
                f"{self.path.name}.pre-schema-v{version}.{stamp}{suffix}.bak"
            )
            if not backup_path.exists():
                break
        else:  # pragma: no cover - 같은 초에 100번 실패하는 경우
            raise DatabaseError("백업 파일 이름을 만들 수 없습니다.")

        try:
            destination = sqlite3.connect(backup_path, isolation_level=None)
            try:
                connection.backup(destination)
            finally:
                destination.close()
        except sqlite3.Error as error:
            try:
                backup_path.unlink(missing_ok=True)
            except OSError:
                pass
            raise DatabaseError("구조 변경 전 데이터베이스 백업에 실패했습니다.") from error
        return backup_path

    # ------------------------------------------------------------------
    # 작품 관리 (선호작 · 로컬 자막 작품)
    # ------------------------------------------------------------------

    def upsert_media(
        self,
        nadeshiko_media_id: str,
        *,
        display_name: str | None = None,
    ) -> StoredMedia:
        """작품을 public ID 기준으로 저장하고 표시명 metadata만 갱신한다.

        같은 public ID의 row는 중복 생성하지 않는다. display_name이 None이면
        기존 표시명을 유지하고, preference/content_group/is_active는 어떤
        경우에도 덮어쓰지 않는다.
        """
        media_id = _required_media_id(nadeshiko_media_id)
        with self.transaction() as connection:
            connection.execute(
                """
                INSERT INTO media (nadeshiko_media_id, display_name)
                VALUES (?, ?)
                ON CONFLICT(nadeshiko_media_id) DO UPDATE SET
                    display_name = COALESCE(excluded.display_name, media.display_name)
                """,
                (media_id, display_name),
            )
        stored = self.get_media(media_id)
        if stored is None:
            raise DatabaseError("저장한 작품을 다시 읽을 수 없습니다.")
        return stored

    def get_media(self, nadeshiko_media_id: str) -> StoredMedia | None:
        """Nadeshiko 작품 public ID로 저장된 상태를 읽는다."""
        row = self.connection.execute(
            f"SELECT {_MEDIA_COLUMNS} FROM media WHERE nadeshiko_media_id = ?",
            (nadeshiko_media_id,),
        ).fetchone()
        return _stored_media(row) if row is not None else None

    def list_media(self) -> tuple[StoredMedia, ...]:
        """저장된 전체 작품을 저장 순서대로 반환한다."""
        rows = self.connection.execute(
            f"SELECT {_MEDIA_COLUMNS} FROM media ORDER BY id"
        ).fetchall()
        return tuple(_stored_media(row) for row in rows)

    def list_active_media(self) -> tuple[StoredMedia, ...]:
        """기본 검색 대상인 활성 작품만 반환한다."""
        rows = self.connection.execute(
            f"SELECT {_MEDIA_COLUMNS} FROM media WHERE is_active = 1 ORDER BY id"
        ).fetchall()
        return tuple(_stored_media(row) for row in rows)

    def set_media_preference(self, nadeshiko_media_id: str, preference: int | None) -> None:
        """작품의 선호도 값을 저장한다."""
        self._update_media_field(nadeshiko_media_id, "preference", preference)

    def set_media_content_group(self, nadeshiko_media_id: str, content_group: str | None) -> None:
        """작품의 사용자 콘텐츠 묶음을 저장한다. 빈 문자열은 None으로 정규화한다."""
        if content_group is not None:
            content_group = content_group.strip() or None
        self._update_media_field(nadeshiko_media_id, "content_group", content_group)

    def set_media_active(self, nadeshiko_media_id: str, active: bool) -> None:
        """작품의 기본 검색 포함 여부를 저장한다."""
        self._update_media_field(nadeshiko_media_id, "is_active", int(active))

    def set_local_media_active(self, media_row_id: int, active: bool) -> None:
        """로컬 자막 작품의 기본 검색 포함 여부를 row ID로 저장한다."""
        with self.transaction() as connection:
            cursor = connection.execute(
                "UPDATE media SET is_active = ? WHERE id = ? AND source = 'local'",
                (int(active), media_row_id),
            )
            if cursor.rowcount != 1:
                raise DatabaseError("상태를 저장할 로컬 작품을 찾을 수 없습니다.")

    def _update_media_field(
        self,
        nadeshiko_media_id: str,
        column: str,
        value: object,
    ) -> None:
        media_id = _required_media_id(nadeshiko_media_id)
        with self.transaction() as connection:
            cursor = connection.execute(
                f"UPDATE media SET {column} = ? WHERE nadeshiko_media_id = ?",
                (value, media_id),
            )
            if cursor.rowcount != 1:
                raise DatabaseError("상태를 저장할 작품을 찾을 수 없습니다.")

    def register_local_media(self, display_name: str) -> StoredMedia:
        """로컬 자막 작품을 등록한다. 같은 이름의 local 작품이 있으면 재사용한다."""
        name = display_name.strip() if isinstance(display_name, str) else ""
        if not name:
            raise ValueError("로컬 작품의 표시 이름을 입력해야 합니다.")

        existing = self.find_local_media(name)
        if existing is not None:
            return existing
        with self.transaction() as connection:
            cursor = connection.execute(
                """
                INSERT INTO media (nadeshiko_media_id, display_name, source)
                VALUES (NULL, ?, 'local')
                """,
                (name,),
            )
            row_id = _last_row_id(cursor)
        stored = self._media_by_row_id(row_id)
        if stored is None:
            raise DatabaseError("등록한 로컬 작품을 다시 읽을 수 없습니다.")
        return stored

    def find_local_media(self, display_name: str) -> StoredMedia | None:
        """표시 이름으로 등록된 로컬 자막 작품을 찾는다."""
        row = self.connection.execute(
            f"""
            SELECT {_MEDIA_COLUMNS} FROM media
            WHERE source = 'local' AND display_name = ?
            """,
            (display_name.strip(),),
        ).fetchone()
        return _stored_media(row) if row is not None else None

    def _media_by_row_id(self, media_row_id: int) -> StoredMedia | None:
        row = self.connection.execute(
            f"SELECT {_MEDIA_COLUMNS} FROM media WHERE id = ?",
            (media_row_id,),
        ).fetchone()
        return _stored_media(row) if row is not None else None

    def replace_local_segments(self, media_row_id: int, cues: Sequence[SubtitleCue]) -> int:
        """로컬 작품의 자막 색인을 통째로 교체한다. 재색인해도 중복이 없다."""
        media = self._media_by_row_id(media_row_id)
        if media is None or media.source != "local":
            raise DatabaseError("자막을 색인할 로컬 작품을 찾을 수 없습니다.")

        with self.transaction() as connection:
            connection.execute(
                "DELETE FROM local_segments WHERE media_id = ?", (media_row_id,)
            )
            for cue in cues:
                connection.execute(
                    """
                    INSERT INTO local_segments (
                        media_id, episode, position, start_time_ms, end_time_ms,
                        japanese_text, normalized_text, source_file
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        media_row_id,
                        cue.episode,
                        cue.position,
                        cue.start_time_ms,
                        cue.end_time_ms,
                        cue.japanese_text,
                        _normalize_source(cue.japanese_text).text,
                        cue.source_file,
                    ),
                )
        return len(cues)

    def find_local_segments(
        self,
        *,
        normalized_surface: str,
        media_row_ids: Sequence[int],
    ) -> tuple[LocalSegmentMatch, ...]:
        """로컬 자막 색인에서 정규화 표면형 포함 후보만 1차로 줄여 반환한다.

        LIKE는 후보 축소용이며 최종 판정은 호출자가 기존 표면형 판정으로 한다.
        """
        if not normalized_surface:
            raise ValueError("검색할 표면형이 비어 있습니다.")
        ids = [int(value) for value in media_row_ids]
        if not ids:
            return ()

        escaped = (
            normalized_surface.replace("!", "!!").replace("%", "!%").replace("_", "!_")
        )
        placeholders = ", ".join("?" for _ in ids)
        rows = self.connection.execute(
            f"""
            SELECT
                local_segments.id, local_segments.media_id, media.display_name,
                local_segments.episode, local_segments.position,
                local_segments.start_time_ms, local_segments.end_time_ms,
                local_segments.japanese_text, local_segments.source_file
            FROM local_segments
            JOIN media ON media.id = local_segments.media_id
            WHERE local_segments.media_id IN ({placeholders})
                AND local_segments.normalized_text LIKE ? ESCAPE '!'
            ORDER BY local_segments.media_id, local_segments.episode,
                local_segments.source_file, local_segments.position
            """,
            (*ids, f"%{escaped}%"),
        ).fetchall()
        return tuple(
            LocalSegmentMatch(
                id=int(row["id"]),
                media_id=int(row["media_id"]),
                media_display_name=row["display_name"],
                episode=row["episode"],
                position=int(row["position"]),
                start_time_ms=int(row["start_time_ms"]),
                end_time_ms=int(row["end_time_ms"]),
                japanese_text=row["japanese_text"],
                source_file=row["source_file"],
            )
            for row in rows
        )

    # ------------------------------------------------------------------
    # 표현 자산 (의미 ↔ 관계 ↔ 표현)
    # ------------------------------------------------------------------

    def find_meaning(self, korean_meaning: str) -> StoredMeaning | None:
        """정규화한 한국어 의미로 저장된 의미를 찾는다."""
        normalized = normalize_korean_meaning(korean_meaning)
        if not normalized:
            return None
        row = self.connection.execute(
            """
            SELECT id, normalized_korean_meaning, display_korean_meaning
            FROM meanings WHERE normalized_korean_meaning = ?
            """,
            (normalized,),
        ).fetchone()
        return _stored_meaning(row) if row is not None else None

    def upsert_meaning(self, korean_meaning: str) -> StoredMeaning:
        """한국어 의미를 저장하거나 기존 의미를 그대로 돌려준다.

        표시용 원문은 처음 입력한 값을 유지한다.
        """
        normalized = normalize_korean_meaning(korean_meaning)
        if not normalized:
            raise ValueError("한국어 의미를 입력해야 합니다.")
        display = (korean_meaning or "").strip() or normalized
        with self.transaction() as connection:
            connection.execute(
                """
                INSERT INTO meanings (
                    normalized_korean_meaning, display_korean_meaning, created_at
                ) VALUES (?, ?, ?)
                ON CONFLICT(normalized_korean_meaning) DO NOTHING
                """,
                (normalized, display, _utc_now()),
            )
        stored = self.find_meaning(normalized)
        if stored is None:
            raise DatabaseError("저장한 한국어 의미를 다시 읽을 수 없습니다.")
        return stored

    def list_meaning_expressions(self, meaning_id: int) -> tuple[StoredMeaningExpression, ...]:
        """한 의미에 연결된 일본어 표현 전부를 저장 순서대로 반환한다."""
        rows = self.connection.execute(
            f"""
            SELECT {_RELATION_COLUMNS}
            FROM meaning_expressions
            JOIN expressions ON expressions.id = meaning_expressions.expression_id
            WHERE meaning_expressions.meaning_id = ?
            ORDER BY meaning_expressions.id
            """,
            (meaning_id,),
        ).fetchall()
        return tuple(_stored_relation(row) for row in rows)

    def find_expressions_for_meaning(
        self, korean_meaning: str
    ) -> tuple[StoredMeaningExpression, ...]:
        """저장된 한국어 의미의 표현 전부를 찾는다. 없으면 빈 튜플."""
        meaning = self.find_meaning(korean_meaning)
        if meaning is None:
            return ()
        return self.list_meaning_expressions(meaning.id)

    def add_meaning_expression(
        self,
        meaning_id: int,
        *,
        japanese: str,
        reading: str,
        meaning_ko: str,
        register_text: str,
    ) -> StoredMeaningExpression:
        """표현을 자산으로 저장하고 이 의미와 연결한다.

        같은 일본어 표현은 expressions에 한 번만 저장하고, 의미별 뜻·말투는
        관계에 저장한다. 같은 관계가 이미 있으면 기존 관계를 그대로 돌려준다.
        """
        japanese_text = (japanese or "").strip()
        if not japanese_text:
            raise ValueError("일본어 표현을 입력해야 합니다.")

        with self.transaction() as connection:
            connection.execute(
                """
                INSERT INTO expressions (japanese, reading, created_at)
                VALUES (?, ?, ?)
                ON CONFLICT(japanese) DO NOTHING
                """,
                (japanese_text, (reading or "").strip(), _utc_now()),
            )
            expression_row = connection.execute(
                "SELECT id FROM expressions WHERE japanese = ?", (japanese_text,)
            ).fetchone()
            if expression_row is None:
                raise DatabaseError("일본어 표현을 저장할 수 없습니다.")
            connection.execute(
                """
                INSERT INTO meaning_expressions (
                    meaning_id, expression_id, meaning_ko, register_text, created_at
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(meaning_id, expression_id) DO NOTHING
                """,
                (
                    meaning_id,
                    int(expression_row["id"]),
                    (meaning_ko or "").strip(),
                    (register_text or "").strip(),
                    _utc_now(),
                ),
            )

        row = self.connection.execute(
            f"""
            SELECT {_RELATION_COLUMNS}
            FROM meaning_expressions
            JOIN expressions ON expressions.id = meaning_expressions.expression_id
            WHERE meaning_expressions.meaning_id = ? AND expressions.japanese = ?
            """,
            (meaning_id, japanese_text),
        ).fetchone()
        if row is None:
            raise DatabaseError("저장한 표현 연결을 다시 읽을 수 없습니다.")
        return _stored_relation(row)

    def get_meaning_expression(self, relation_id: int) -> StoredMeaningExpression | None:
        """의미→표현 관계 하나를 읽는다."""
        row = self.connection.execute(
            f"""
            SELECT {_RELATION_COLUMNS}
            FROM meaning_expressions
            JOIN expressions ON expressions.id = meaning_expressions.expression_id
            WHERE meaning_expressions.id = ?
            """,
            (relation_id,),
        ).fetchone()
        return _stored_relation(row) if row is not None else None

    def get_meaning(self, meaning_id: int) -> StoredMeaning | None:
        """의미 하나를 ID로 읽는다."""
        row = self.connection.execute(
            """
            SELECT id, normalized_korean_meaning, display_korean_meaning
            FROM meanings WHERE id = ?
            """,
            (meaning_id,),
        ).fetchone()
        return _stored_meaning(row) if row is not None else None

    # ------------------------------------------------------------------
    # 실제 작업 장면
    # ------------------------------------------------------------------

    def upsert_work_scene(
        self,
        meaning_expression_id: int,
        *,
        segment_public_id: str,
        media_public_id: str | None,
        media_display_name: str | None,
        episode: int | None,
        start_time_ms: int,
        end_time_ms: int,
        japanese_text: str,
    ) -> int:
        """작업 장면의 스냅샷을 저장하고 work_scene ID를 반환한다.

        이미 있는 장면이면 스냅샷만 갱신하고 판정·번역·메모는 보존한다.
        영상/음성/이미지 주소와 원본 응답은 저장하지 않는다.
        """
        if not (segment_public_id or "").strip():
            raise ValueError("Nadeshiko 장면 ID가 필요합니다.")
        if self.get_meaning_expression(meaning_expression_id) is None:
            raise DatabaseError("작업 장면을 저장할 표현 연결을 찾을 수 없습니다.")

        now = _utc_now()
        with self.transaction() as connection:
            connection.execute(
                """
                INSERT INTO work_scenes (
                    meaning_expression_id, segment_public_id, media_public_id,
                    media_display_name, episode, start_time_ms, end_time_ms,
                    japanese_text, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(meaning_expression_id, segment_public_id) DO UPDATE SET
                    media_public_id = excluded.media_public_id,
                    media_display_name = excluded.media_display_name,
                    episode = excluded.episode,
                    start_time_ms = excluded.start_time_ms,
                    end_time_ms = excluded.end_time_ms,
                    japanese_text = excluded.japanese_text,
                    updated_at = excluded.updated_at
                """,
                (
                    meaning_expression_id,
                    segment_public_id,
                    media_public_id,
                    media_display_name,
                    episode,
                    start_time_ms,
                    end_time_ms,
                    japanese_text,
                    now,
                    now,
                ),
            )
        row = self.connection.execute(
            """
            SELECT id FROM work_scenes
            WHERE meaning_expression_id = ? AND segment_public_id = ?
            """,
            (meaning_expression_id, segment_public_id),
        ).fetchone()
        if row is None:
            raise DatabaseError("저장한 작업 장면을 다시 읽을 수 없습니다.")
        return int(row["id"])

    def set_work_scene_decision(self, work_scene_id: int, decision: ReviewDecision) -> None:
        """사용자 판정만 저장하고 번역·메모는 보존한다."""
        if decision not in _REVIEW_DECISIONS:
            raise ValueError("검수 판정은 채택, 예비, 제외 중 하나여야 합니다.")
        self._update_work_scene(
            work_scene_id, "decision = ?, updated_at = ?", (decision, _utc_now())
        )

    def set_work_scene_notes(self, work_scene_id: int, notes: str | None) -> None:
        """사용자 메모만 저장하고 판정·번역은 보존한다."""
        value = notes.strip() if isinstance(notes, str) else None
        self._update_work_scene(
            work_scene_id, "notes = ?, updated_at = ?", (value or None, _utc_now())
        )

    def save_work_scene_translation(
        self,
        work_scene_id: int,
        *,
        direct_meaning: str,
        natural_translation: str,
        scene_usage: str,
        ai_service: str,
        ai_model: str,
        instruction_version: str,
    ) -> None:
        """사용자가 요청해 만든 번역을 작업물로 저장한다. 판정·메모는 보존한다."""
        now = _utc_now()
        self._update_work_scene(
            work_scene_id,
            """
            direct_meaning = ?, natural_translation = ?, scene_usage = ?,
            translation_ai_service = ?, translation_ai_model = ?,
            translation_instruction_version = ?, translated_at = ?, updated_at = ?
            """,
            (
                direct_meaning,
                natural_translation,
                scene_usage,
                ai_service,
                ai_model,
                instruction_version,
                now,
                now,
            ),
        )

    def _update_work_scene(self, work_scene_id: int, assignment: str, values: tuple) -> None:
        with self.transaction() as connection:
            cursor = connection.execute(
                f"UPDATE work_scenes SET {assignment} WHERE id = ?",
                (*values, work_scene_id),
            )
            if cursor.rowcount != 1:
                raise DatabaseError("갱신할 작업 장면을 찾을 수 없습니다.")

    def get_work_scene(
        self, meaning_expression_id: int, segment_public_id: str
    ) -> StoredWorkScene | None:
        """관계와 장면 ID로 저장된 작업 장면을 읽는다."""
        row = self.connection.execute(
            f"""
            SELECT {_WORK_SCENE_COLUMNS} FROM work_scenes
            WHERE meaning_expression_id = ? AND segment_public_id = ?
            """,
            (meaning_expression_id, segment_public_id),
        ).fetchone()
        return _stored_work_scene(row) if row is not None else None

    def list_work_scenes(self, meaning_expression_id: int) -> tuple[StoredWorkScene, ...]:
        """한 관계에서 실제로 작업한 장면 전부를 반환한다."""
        rows = self.connection.execute(
            f"""
            SELECT {_WORK_SCENE_COLUMNS} FROM work_scenes
            WHERE meaning_expression_id = ?
            ORDER BY id
            """,
            (meaning_expression_id,),
        ).fetchall()
        return tuple(_stored_work_scene(row) for row in rows)

    def list_accepted_work_scenes(self) -> tuple[AcceptedSceneExportRow, ...]:
        """decision='채택'인 작업 장면을 내보내기용으로 읽는다.

        같은 장면이 여러 의미→표현 관계에서 채택되면 관계별로 한 행씩 나온다.
        """
        rows = self.connection.execute(
            """
            SELECT
                meanings.display_korean_meaning,
                expressions.japanese,
                expressions.reading,
                meaning_expressions.meaning_ko,
                meaning_expressions.register_text,
                work_scenes.segment_public_id,
                work_scenes.media_public_id,
                work_scenes.media_display_name,
                work_scenes.episode,
                work_scenes.start_time_ms,
                work_scenes.end_time_ms,
                work_scenes.japanese_text,
                work_scenes.direct_meaning,
                work_scenes.natural_translation,
                work_scenes.scene_usage,
                work_scenes.notes,
                work_scenes.decision
            FROM work_scenes
            JOIN meaning_expressions
                ON meaning_expressions.id = work_scenes.meaning_expression_id
            JOIN expressions ON expressions.id = meaning_expressions.expression_id
            JOIN meanings ON meanings.id = meaning_expressions.meaning_id
            WHERE work_scenes.decision = '채택'
            ORDER BY meanings.id, meaning_expressions.id, work_scenes.id
            """
        ).fetchall()
        return tuple(
            AcceptedSceneExportRow(
                korean_meaning=row["display_korean_meaning"],
                japanese=row["japanese"],
                reading=row["reading"],
                meaning_ko=row["meaning_ko"],
                register_text=row["register_text"],
                segment_public_id=row["segment_public_id"],
                media_public_id=row["media_public_id"],
                media_display_name=row["media_display_name"],
                episode=row["episode"],
                start_time_ms=int(row["start_time_ms"]),
                end_time_ms=int(row["end_time_ms"]),
                japanese_text=row["japanese_text"],
                direct_meaning=row["direct_meaning"],
                natural_translation=row["natural_translation"],
                scene_usage=row["scene_usage"],
                notes=row["notes"],
                decision=row["decision"],
            )
            for row in rows
        )

    # ------------------------------------------------------------------
    # schema 보장과 migration
    # ------------------------------------------------------------------

    def _ensure_schema(self) -> None:
        version = self.schema_version
        if version > SCHEMA_VERSION:
            raise UnsupportedSchemaVersionError(
                f"DB schema version {version}은 현재 코드의 version "
                f"{SCHEMA_VERSION}보다 새 버전입니다. 데이터를 수정하지 않았습니다."
            )
        if version == SCHEMA_VERSION:
            self._verify_schema()
            return
        if version == 0:
            existing_tables = self._application_tables()
            if existing_tables:
                raise DatabaseError(
                    "schema version 0인 비어 있지 않은 DB는 자동 변경하지 않습니다. "
                    "명시적인 migration이 필요합니다."
                )
            self._initialize_schema()
            return

        if version == 1:
            self._migrate_v1_to_v2()
        if self.schema_version == 2:
            self._migrate_v2_to_v3()
        if self.schema_version == 3:
            self._migrate_v3_to_v4()
        self._verify_schema()

    def _migrate_v1_to_v2(self) -> None:
        """기존 v1 DB를 백업한 뒤 한 transaction에서 v2 구조로 옮긴다."""
        self.backup_before_schema_change()
        try:
            with self.transaction() as connection:
                for statement in _V1_TO_V2_STATEMENTS:
                    connection.execute(statement)
                connection.execute("PRAGMA user_version = 2")
                self._verify_schema(expected=_EXPECTED_TABLES_V2)
        except sqlite3.Error as error:
            raise DatabaseError(
                "SQLite v1 → v2 migration에 실패했습니다. "
                "원본 데이터는 변경 전 상태로 유지됩니다."
            ) from error

        if self.schema_version != 2:
            raise DatabaseError("SQLite v2 schema version 저장을 확인할 수 없습니다.")

    def _migrate_v2_to_v3(self) -> None:
        """기존 v2 DB를 백업한 뒤 media 재작성과 local_segments 추가를 수행한다.

        media는 segments가 참조하는 parent table이라 SQLite 공식 절차대로
        transaction 밖에서 foreign key 검사를 잠시 끄고 재작성하며,
        commit 전에 PRAGMA foreign_key_check로 참조 무결성을 확인한다.
        """
        self.backup_before_schema_change()
        connection = self.connection
        connection.execute("PRAGMA foreign_keys = OFF")
        try:
            try:
                with self.transaction() as tx:
                    for statement in _V2_TO_V3_STATEMENTS:
                        tx.execute(statement)
                    tx.execute("PRAGMA user_version = 3")
                    self._verify_schema(expected=_EXPECTED_TABLES_V3)
                    violations = tx.execute("PRAGMA foreign_key_check").fetchall()
                    if violations:
                        raise sqlite3.IntegrityError(
                            "migration 후 foreign key 위반이 발견됐습니다."
                        )
            except sqlite3.Error as error:
                raise DatabaseError(
                    "SQLite v2 → v3 migration에 실패했습니다. "
                    "원본 데이터는 변경 전 상태로 유지됩니다."
                ) from error
        finally:
            connection.execute("PRAGMA foreign_keys = ON")

        if self.schema_version != 3:
            raise DatabaseError("SQLite v3 schema version 저장을 확인할 수 없습니다.")

    def _migrate_v3_to_v4(self) -> None:
        """기존 v3 DB를 백업한 뒤 표현 자산·실제 작업만 새 구조로 옮긴다.

        보존: 작품 상태, 로컬 자막 색인, 저장된 일본어 표현과 한국어 의미 연결,
        판정·번역·메모가 있는 실제 작업.
        폐기: 검색 이력, 검색 결과 장면, 캐시, 영상 주소와 원본 응답.

        여러 옛 table을 통째로 버리므로 SQLite 공식 절차대로 transaction 밖에서
        foreign key 검사를 잠시 끄고 수행하며, commit 전에 참조 무결성을 확인한다.
        """
        self.backup_before_schema_change()
        connection = self.connection
        connection.execute("PRAGMA foreign_keys = OFF")
        try:
            try:
                with self.transaction() as tx:
                    for statement in _V3_TO_V4_CREATE_STATEMENTS:
                        tx.execute(statement)
                    self._copy_v3_expression_assets(tx)
                    for statement in _V3_TO_V4_DROP_STATEMENTS:
                        tx.execute(statement)
                    tx.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
                    self._verify_schema()
                    violations = tx.execute("PRAGMA foreign_key_check").fetchall()
                    if violations:
                        raise sqlite3.IntegrityError(
                            "migration 후 foreign key 위반이 발견됐습니다."
                        )
            except sqlite3.Error as error:
                raise DatabaseError(
                    "SQLite v3 → v4 migration에 실패했습니다. "
                    "원본 데이터는 변경 전 상태로 유지됩니다."
                ) from error
        finally:
            connection.execute("PRAGMA foreign_keys = ON")

        if self.schema_version != SCHEMA_VERSION:
            raise DatabaseError("SQLite v4 schema version 저장을 확인할 수 없습니다.")

    def _copy_v3_expression_assets(self, connection: sqlite3.Connection) -> None:
        """옛 검색 기록에서 표현 자산과 실제 작업만 새 table로 옮긴다."""
        now = _utc_now()

        meaning_ids: dict[int, int] = {}
        for run in connection.execute(
            "SELECT id, korean_intent FROM search_runs ORDER BY id"
        ).fetchall():
            normalized = normalize_korean_meaning(run["korean_intent"])
            if not normalized:
                continue
            connection.execute(
                """
                INSERT INTO meanings (
                    normalized_korean_meaning, display_korean_meaning, created_at
                ) VALUES (?, ?, ?)
                ON CONFLICT(normalized_korean_meaning) DO NOTHING
                """,
                (normalized, (run["korean_intent"] or normalized).strip(), now),
            )
            meaning_row = connection.execute(
                "SELECT id FROM meanings WHERE normalized_korean_meaning = ?",
                (normalized,),
            ).fetchone()
            if meaning_row is not None:
                meaning_ids[int(run["id"])] = int(meaning_row["id"])

        relation_ids: dict[int, int] = {}
        for expression in connection.execute(
            """
            SELECT id, search_run_id, japanese, reading, meaning_ko, register_text
            FROM expressions ORDER BY id
            """
        ).fetchall():
            meaning_id = meaning_ids.get(int(expression["search_run_id"]))
            if meaning_id is None:
                continue
            japanese = (expression["japanese"] or "").strip()
            if not japanese:
                continue
            connection.execute(
                """
                INSERT INTO expressions_v4 (japanese, reading, created_at)
                VALUES (?, ?, ?)
                ON CONFLICT(japanese) DO NOTHING
                """,
                (japanese, (expression["reading"] or "").strip(), now),
            )
            expression_row = connection.execute(
                "SELECT id FROM expressions_v4 WHERE japanese = ?", (japanese,)
            ).fetchone()
            if expression_row is None:
                continue
            connection.execute(
                """
                INSERT INTO meaning_expressions (
                    meaning_id, expression_id, meaning_ko, register_text, created_at
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(meaning_id, expression_id) DO NOTHING
                """,
                (
                    meaning_id,
                    int(expression_row["id"]),
                    (expression["meaning_ko"] or "").strip(),
                    (expression["register_text"] or "").strip(),
                    now,
                ),
            )
            relation_row = connection.execute(
                """
                SELECT id FROM meaning_expressions
                WHERE meaning_id = ? AND expression_id = ?
                """,
                (meaning_id, int(expression_row["id"])),
            ).fetchone()
            if relation_row is not None:
                relation_ids[int(expression["id"])] = int(relation_row["id"])

        for review in connection.execute(
            """
            SELECT
                reviews.expression_id,
                reviews.decision,
                reviews.direct_meaning,
                reviews.natural_translation,
                reviews.scene_usage,
                reviews.notes,
                reviews.translation_ai_service,
                reviews.translation_ai_model,
                reviews.translation_instruction_version,
                reviews.translated_at,
                reviews.updated_at,
                segments.nadeshiko_segment_id,
                segments.episode,
                segments.start_time_ms,
                segments.end_time_ms,
                segments.japanese_text,
                media.nadeshiko_media_id,
                media.display_name
            FROM reviews
            JOIN segments ON segments.id = reviews.segment_id
            JOIN media ON media.id = segments.media_id
            WHERE reviews.decision IS NOT NULL
                OR reviews.natural_translation IS NOT NULL
                OR reviews.notes IS NOT NULL
            ORDER BY reviews.expression_id, reviews.segment_id
            """
        ).fetchall():
            relation_id = relation_ids.get(int(review["expression_id"]))
            if relation_id is None:
                continue
            connection.execute(
                """
                INSERT INTO work_scenes (
                    meaning_expression_id, segment_public_id, media_public_id,
                    media_display_name, episode, start_time_ms, end_time_ms,
                    japanese_text, decision, direct_meaning, natural_translation,
                    scene_usage, translation_ai_service, translation_ai_model,
                    translation_instruction_version, translated_at, notes,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(meaning_expression_id, segment_public_id) DO NOTHING
                """,
                (
                    relation_id,
                    review["nadeshiko_segment_id"],
                    review["nadeshiko_media_id"],
                    review["display_name"],
                    review["episode"],
                    review["start_time_ms"],
                    review["end_time_ms"],
                    review["japanese_text"],
                    review["decision"],
                    review["direct_meaning"],
                    review["natural_translation"],
                    review["scene_usage"],
                    review["translation_ai_service"],
                    review["translation_ai_model"],
                    review["translation_instruction_version"],
                    review["translated_at"],
                    review["notes"],
                    review["updated_at"] or now,
                    review["updated_at"] or now,
                ),
            )

    def _initialize_schema(self) -> None:
        try:
            with self.transaction() as connection:
                for statement in _SCHEMA_STATEMENTS:
                    connection.execute(statement)
                connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
                self._verify_schema()
        except sqlite3.Error as error:
            raise DatabaseError("SQLite schema 초기화에 실패했습니다.") from error

        if self.schema_version != SCHEMA_VERSION:
            raise DatabaseError("SQLite schema version 저장을 확인할 수 없습니다.")

    def _verify_schema(self, expected: frozenset[str] = _EXPECTED_TABLES) -> None:
        missing_tables = expected - self._application_tables()
        if missing_tables:
            missing = ", ".join(sorted(missing_tables))
            raise DatabaseError(f"SQLite schema에 필요한 table이 없습니다: {missing}")

    def _application_tables(self) -> frozenset[str]:
        rows = self.connection.execute(
            """
            SELECT name FROM sqlite_master
            WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
            """
        ).fetchall()
        return frozenset(row["name"] for row in rows)


def _required_media_id(nadeshiko_media_id: str) -> str:
    media_id = nadeshiko_media_id.strip() if isinstance(nadeshiko_media_id, str) else ""
    if not media_id:
        raise ValueError("Nadeshiko 작품 public ID가 필요합니다.")
    return media_id


def _stored_media(row: sqlite3.Row) -> StoredMedia:
    return StoredMedia(
        id=int(row["id"]),
        nadeshiko_media_id=row["nadeshiko_media_id"],
        display_name=row["display_name"],
        preference=row["preference"],
        content_group=row["content_group"],
        is_active=bool(row["is_active"]),
        source=row["source"],
    )


def _stored_meaning(row: sqlite3.Row) -> StoredMeaning:
    return StoredMeaning(
        id=int(row["id"]),
        normalized_korean_meaning=row["normalized_korean_meaning"],
        display_korean_meaning=row["display_korean_meaning"],
    )


def _stored_relation(row: sqlite3.Row) -> StoredMeaningExpression:
    return StoredMeaningExpression(
        id=int(row["relation_id"]),
        meaning_id=int(row["meaning_id"]),
        expression_id=int(row["expression_id"]),
        japanese=row["japanese"],
        reading=row["reading"],
        meaning_ko=row["meaning_ko"],
        register_text=row["register_text"],
    )


def _stored_work_scene(row: sqlite3.Row) -> StoredWorkScene:
    return StoredWorkScene(
        id=int(row["id"]),
        meaning_expression_id=int(row["meaning_expression_id"]),
        segment_public_id=row["segment_public_id"],
        media_public_id=row["media_public_id"],
        media_display_name=row["media_display_name"],
        episode=row["episode"],
        start_time_ms=int(row["start_time_ms"]),
        end_time_ms=int(row["end_time_ms"]),
        japanese_text=row["japanese_text"],
        decision=row["decision"],
        direct_meaning=row["direct_meaning"],
        natural_translation=row["natural_translation"],
        scene_usage=row["scene_usage"],
        translation_ai_service=row["translation_ai_service"],
        translation_ai_model=row["translation_ai_model"],
        translation_instruction_version=row["translation_instruction_version"],
        translated_at=row["translated_at"],
        notes=row["notes"],
        updated_at=row["updated_at"],
    )


def _last_row_id(cursor: sqlite3.Cursor) -> int:
    if cursor.lastrowid is None:
        raise DatabaseError("SQLite가 새 행의 ID를 반환하지 않았습니다.")
    return int(cursor.lastrowid)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
