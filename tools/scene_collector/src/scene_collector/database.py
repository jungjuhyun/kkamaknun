"""SQLite에 장면 수집기의 로컬 작업 상태와 요청 캐시를 저장한다."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Literal, TypeVar
from uuid import uuid4

from nadeshiko.models import SearchResponse, Segment, SegmentContextResponse
from pydantic import BaseModel, ValidationError

from scene_collector.config import AppSettings
from scene_collector.models import ExpressionCandidate

if TYPE_CHECKING:
    from scene_collector.search import ExpressionSearchResult

DATABASE_FILENAME = "scene_collector.sqlite3"
SCHEMA_VERSION = 2

ReviewDecision = Literal["채택", "예비", "제외"]
CachedResponse = TypeVar("CachedResponse", bound=BaseModel)


class DatabaseError(RuntimeError):
    """로컬 데이터베이스를 안전하게 사용할 수 없을 때 발생한다."""


class UnsupportedSchemaVersionError(DatabaseError):
    """DB 스키마가 현재 코드보다 새 버전일 때 발생한다."""


@dataclass(frozen=True)
class StoredMedia:
    """로컬에 저장된 사용자 선호 작품 상태."""

    id: int
    nadeshiko_media_id: str
    display_name: str | None
    preference: int | None
    content_group: str | None
    is_active: bool


@dataclass(frozen=True)
class StoredReview:
    """표현에 연결된 장면의 AI 번역과 사용자 검수 상태.

    decision이 None이면 번역은 존재하지만 사용자가 아직 판정하지 않은
    상태다. translation_* provenance는 AI가 생성한 번역에만 채워진다.
    """

    decision: ReviewDecision | None
    direct_meaning: str | None
    natural_translation: str | None
    scene_usage: str | None
    notes: str | None
    translation_ai_service: str | None
    translation_ai_model: str | None
    translation_instruction_version: str | None
    translation_input_hash: str | None
    translated_at: str | None
    updated_at: str


@dataclass(frozen=True)
class StoredSegment:
    """내부 ID와 SDK 원본 자료형으로 복원한 장면."""

    id: int
    segment: Segment
    review: StoredReview | None


@dataclass(frozen=True)
class StoredExpression:
    """저장된 표현 후보와 그 표현에서 살아남은 장면."""

    id: int
    candidate: ExpressionCandidate
    selected: bool
    segments: tuple[StoredSegment, ...]


@dataclass(frozen=True)
class StoredSearchRun:
    """한 번의 한국어 검색과 저장된 표현·장면 묶음."""

    id: int
    korean_intent: str
    created_at: str
    ai_service: str
    ai_model: str
    instruction_version: str
    expressions: tuple[StoredExpression, ...]


def _reviews_table_ddl(table_name: str) -> str:
    """새로 생성하는 v2 reviews와 migration 중간 table이 같은 구조를 쓰게 한다."""
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
        FOREIGN KEY (expression_id, segment_id)
            REFERENCES expression_segments(expression_id, segment_id) ON DELETE CASCADE
    )
    """


_CONTEXT_CACHE_TABLE_DDL = """
    CREATE TABLE nadeshiko_context_cache (
        segment_public_id TEXT NOT NULL,
        context_take INTEGER NOT NULL CHECK (context_take > 0),
        response_json TEXT NOT NULL,
        created_at TEXT NOT NULL,
        PRIMARY KEY (segment_public_id, context_take)
    )
    """


_SCHEMA_STATEMENTS = (
    """
    CREATE TABLE media (
        id INTEGER PRIMARY KEY,
        nadeshiko_media_id TEXT NOT NULL UNIQUE,
        display_name TEXT,
        preference INTEGER,
        content_group TEXT,
        is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1))
    )
    """,
    """
    CREATE TABLE search_runs (
        id INTEGER PRIMARY KEY,
        korean_intent TEXT NOT NULL,
        created_at TEXT NOT NULL,
        ai_service TEXT NOT NULL,
        ai_model TEXT NOT NULL,
        instruction_version TEXT NOT NULL
    )
    """,
    """
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
    """,
    """
    CREATE TABLE segments (
        id INTEGER PRIMARY KEY,
        nadeshiko_segment_id TEXT NOT NULL UNIQUE,
        media_id INTEGER NOT NULL,
        position INTEGER NOT NULL,
        episode INTEGER NOT NULL,
        start_time_ms INTEGER NOT NULL CHECK (start_time_ms >= 0),
        end_time_ms INTEGER NOT NULL CHECK (end_time_ms >= start_time_ms),
        external_video_id TEXT,
        japanese_text TEXT NOT NULL,
        video_url TEXT NOT NULL,
        audio_url TEXT NOT NULL,
        image_url TEXT NOT NULL,
        raw_json TEXT NOT NULL,
        FOREIGN KEY (media_id) REFERENCES media(id)
    )
    """,
    """
    CREATE TABLE expression_segments (
        expression_id INTEGER NOT NULL,
        segment_id INTEGER NOT NULL,
        ordinal INTEGER NOT NULL,
        PRIMARY KEY (expression_id, segment_id),
        FOREIGN KEY (expression_id) REFERENCES expressions(id) ON DELETE CASCADE,
        FOREIGN KEY (segment_id) REFERENCES segments(id)
    )
    """,
    _reviews_table_ddl("reviews"),
    """
    CREATE TABLE ai_cache (
        request_hash TEXT PRIMARY KEY,
        input_hash TEXT NOT NULL,
        ai_service TEXT NOT NULL,
        ai_model TEXT NOT NULL,
        instruction_version TEXT NOT NULL,
        response_json TEXT NOT NULL,
        created_at TEXT NOT NULL,
        UNIQUE (ai_service, ai_model, instruction_version, input_hash)
    )
    """,
    """
    CREATE TABLE nadeshiko_search_cache (
        request_hash TEXT PRIMARY KEY,
        search_text TEXT NOT NULL,
        exact_match INTEGER NOT NULL CHECK (exact_match IN (0, 1)),
        take INTEGER NOT NULL CHECK (take > 0),
        conditions_json TEXT NOT NULL,
        response_json TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    """,
    _CONTEXT_CACHE_TABLE_DDL,
    "CREATE INDEX expressions_search_run_idx ON expressions(search_run_id)",
    "CREATE INDEX expression_segments_segment_idx ON expression_segments(segment_id)",
)

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

_EXPECTED_TABLES = frozenset(
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
_REVIEW_DECISIONS = frozenset({"채택", "예비", "제외"})
_MEDIA_COLUMNS = "id, nadeshiko_media_id, display_name, preference, content_group, is_active"
_REVIEW_COLUMNS = (
    "decision, direct_meaning, natural_translation, scene_usage, notes, "
    "translation_ai_service, translation_ai_model, translation_instruction_version, "
    "translation_input_hash, translated_at, updated_at"
)


def database_path(settings: AppSettings) -> Path:
    """검증된 작업 데이터 디렉터리 안의 프로그램 관리 DB 경로를 반환한다."""
    return settings.storage.work_data_dir / DATABASE_FILENAME


class SceneCollectorDatabase:
    """한 SQLite 연결에서 작업 상태, 검수와 캐시를 관리한다."""

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
            connection.close()
            database._connection = None
            raise
        return database

    @property
    def connection(self) -> sqlite3.Connection:
        """현재 열린 표준 sqlite3 연결을 반환한다."""
        if self._connection is None:
            raise DatabaseError("이미 닫힌 데이터베이스 연결입니다.")
        return self._connection

    @property
    def schema_version(self) -> int:
        """현재 DB의 PRAGMA user_version 값을 반환한다."""
        row = self.connection.execute("PRAGMA user_version").fetchone()
        if row is None:
            raise DatabaseError("SQLite schema version을 읽을 수 없습니다.")
        return int(row[0])

    def __enter__(self) -> SceneCollectorDatabase:
        return self

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        connection = self._connection
        if connection is not None and connection.in_transaction:
            connection.rollback()
        self.close()

    def close(self) -> None:
        """열린 transaction을 rollback하고 연결을 명시적으로 닫는다."""
        connection = self._connection
        if connection is None:
            return
        if connection.in_transaction:
            connection.rollback()
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
        except BaseException:
            if connection.in_transaction:
                connection.rollback()
            raise
        else:
            try:
                connection.commit()
            except BaseException:
                if connection.in_transaction:
                    connection.rollback()
                raise

    def backup_before_schema_change(self) -> Path:
        """Connection.backup()으로 덮어쓰지 않는 구조 변경 전 사본을 만든다."""
        connection = self.connection
        if connection.in_transaction:
            raise DatabaseError("진행 중인 transaction을 끝낸 뒤 데이터베이스를 백업해야 합니다.")

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        while True:
            backup_path = self.path.with_name(
                f"{self.path.stem}.pre-schema-v{self.schema_version}."
                f"{timestamp}.{uuid4().hex[:8]}.sqlite3"
            )
            try:
                backup_path.touch(exist_ok=False)
            except FileExistsError:
                continue
            except OSError as error:
                raise DatabaseError("구조 변경 전 백업 파일을 만들 수 없습니다.") from error
            else:
                break

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
        """Nadeshiko public ID로 저장된 작품 하나를 읽는다."""
        row = self.connection.execute(
            f"SELECT {_MEDIA_COLUMNS} FROM media WHERE nadeshiko_media_id = ?",
            (_required_media_id(nadeshiko_media_id),),
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

    def save_search_result(
        self,
        result: ExpressionSearchResult,
        *,
        ai_service: str,
        ai_model: str,
        instruction_version: str,
    ) -> int:
        """검색 실행과 후보, 정확 surface 장면 관계를 원자적으로 저장한다."""
        created_at = _utc_now()
        searches_by_japanese = {
            item.candidate.japanese: item for item in result.candidate_searches
        }

        with self.transaction() as connection:
            cursor = connection.execute(
                """
                INSERT INTO search_runs (
                    korean_intent, created_at, ai_service, ai_model, instruction_version
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    result.korean_intent,
                    created_at,
                    ai_service,
                    ai_model,
                    instruction_version,
                ),
            )
            search_run_id = _last_row_id(cursor)

            for ordinal, candidate in enumerate(result.generated_candidates):
                cursor = connection.execute(
                    """
                    INSERT INTO expressions (
                        search_run_id, ordinal, japanese, reading, meaning_ko, register_text
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        search_run_id,
                        ordinal,
                        candidate.japanese,
                        candidate.reading,
                        candidate.meaning_ko,
                        candidate.register,
                    ),
                )
                expression_id = _last_row_id(cursor)
                candidate_search = searches_by_japanese.get(candidate.japanese)
                if candidate_search is None:
                    continue
                for segment_ordinal, segment in enumerate(candidate_search.exact_segments):
                    segment_id = self._upsert_segment(connection, segment)
                    connection.execute(
                        """
                        INSERT OR IGNORE INTO expression_segments (
                            expression_id, segment_id, ordinal
                        ) VALUES (?, ?, ?)
                        """,
                        (expression_id, segment_id, segment_ordinal),
                    )

        return search_run_id

    def load_search_run(self, search_run_id: int) -> StoredSearchRun | None:
        """검색 한 건을 기존 Pydantic/SDK 자료형과 함께 복원한다."""
        connection = self.connection
        run = connection.execute(
            """
            SELECT id, korean_intent, created_at, ai_service, ai_model, instruction_version
            FROM search_runs
            WHERE id = ?
            """,
            (search_run_id,),
        ).fetchone()
        if run is None:
            return None

        expression_rows = connection.execute(
            """
            SELECT id, japanese, reading, meaning_ko, register_text, is_selected
            FROM expressions
            WHERE search_run_id = ?
            ORDER BY ordinal, id
            """,
            (search_run_id,),
        ).fetchall()
        expressions = tuple(self._load_expression(row) for row in expression_rows)
        return StoredSearchRun(
            id=run["id"],
            korean_intent=run["korean_intent"],
            created_at=run["created_at"],
            ai_service=run["ai_service"],
            ai_model=run["ai_model"],
            instruction_version=run["instruction_version"],
            expressions=expressions,
        )

    def load_expression(self, expression_id: int) -> StoredExpression | None:
        """표현 하나와 그 표현에 연결된 장면·검수 상태를 복원한다."""
        row = self.connection.execute(
            """
            SELECT id, japanese, reading, meaning_ko, register_text, is_selected
            FROM expressions
            WHERE id = ?
            """,
            (expression_id,),
        ).fetchone()
        return self._load_expression(row) if row is not None else None

    def set_expression_selected(self, expression_id: int, selected: bool) -> None:
        """표현 후보의 사용자 선택 상태를 저장한다."""
        with self.transaction() as connection:
            cursor = connection.execute(
                "UPDATE expressions SET is_selected = ? WHERE id = ?",
                (int(selected), expression_id),
            )
            if cursor.rowcount != 1:
                raise DatabaseError("선택 상태를 저장할 표현을 찾을 수 없습니다.")

    def save_review(
        self,
        expression_id: int,
        segment_id: int,
        *,
        decision: ReviewDecision,
        direct_meaning: str | None = None,
        natural_translation: str | None = None,
        scene_usage: str | None = None,
        notes: str | None = None,
    ) -> None:
        """표현-장면 관계의 검수 상태 전체를 수동으로 다시 작성한다.

        번역 필드까지 통째로 덮어쓰는 수동 경로이므로 AI 번역 provenance는
        비운다. 사용자 판정만 바꿀 때는 set_review_decision을, AI 번역만
        저장할 때는 save_scene_translation을 사용한다.
        """
        if decision not in _REVIEW_DECISIONS:
            raise ValueError("검수 판정은 채택, 예비, 제외 중 하나여야 합니다.")

        with self.transaction() as connection:
            self._require_expression_segment(connection, expression_id, segment_id)
            connection.execute(
                """
                INSERT INTO reviews (
                    expression_id, segment_id, decision, direct_meaning,
                    natural_translation, scene_usage, notes, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(expression_id, segment_id) DO UPDATE SET
                    decision = excluded.decision,
                    direct_meaning = excluded.direct_meaning,
                    natural_translation = excluded.natural_translation,
                    scene_usage = excluded.scene_usage,
                    notes = excluded.notes,
                    translation_ai_service = NULL,
                    translation_ai_model = NULL,
                    translation_instruction_version = NULL,
                    translation_input_hash = NULL,
                    translated_at = NULL,
                    updated_at = excluded.updated_at
                """,
                (
                    expression_id,
                    segment_id,
                    decision,
                    direct_meaning,
                    natural_translation,
                    scene_usage,
                    notes,
                    _utc_now(),
                ),
            )

    def set_review_decision(
        self,
        expression_id: int,
        segment_id: int,
        decision: ReviewDecision,
    ) -> None:
        """사용자 판정만 저장하고 기존 AI 번역과 notes는 보존한다."""
        if decision not in _REVIEW_DECISIONS:
            raise ValueError("검수 판정은 채택, 예비, 제외 중 하나여야 합니다.")

        with self.transaction() as connection:
            self._require_expression_segment(connection, expression_id, segment_id)
            connection.execute(
                """
                INSERT INTO reviews (expression_id, segment_id, decision, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(expression_id, segment_id) DO UPDATE SET
                    decision = excluded.decision,
                    updated_at = excluded.updated_at
                """,
                (expression_id, segment_id, decision, _utc_now()),
            )

    def save_scene_translation(
        self,
        expression_id: int,
        segment_id: int,
        *,
        direct_meaning: str,
        natural_translation: str,
        scene_usage: str,
        ai_service: str,
        ai_model: str,
        instruction_version: str,
        input_hash: str,
    ) -> None:
        """AI 장면 번역과 provenance만 저장하고 사용자 decision/notes는 보존한다."""
        with self.transaction() as connection:
            self._require_expression_segment(connection, expression_id, segment_id)
            connection.execute(
                """
                INSERT INTO reviews (
                    expression_id, segment_id, direct_meaning, natural_translation,
                    scene_usage, translation_ai_service, translation_ai_model,
                    translation_instruction_version, translation_input_hash,
                    translated_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(expression_id, segment_id) DO UPDATE SET
                    direct_meaning = excluded.direct_meaning,
                    natural_translation = excluded.natural_translation,
                    scene_usage = excluded.scene_usage,
                    translation_ai_service = excluded.translation_ai_service,
                    translation_ai_model = excluded.translation_ai_model,
                    translation_instruction_version = excluded.translation_instruction_version,
                    translation_input_hash = excluded.translation_input_hash,
                    translated_at = excluded.translated_at,
                    updated_at = excluded.updated_at
                """,
                (
                    expression_id,
                    segment_id,
                    direct_meaning,
                    natural_translation,
                    scene_usage,
                    ai_service,
                    ai_model,
                    instruction_version,
                    input_hash,
                    _utc_now(),
                    _utc_now(),
                ),
            )

    def _require_expression_segment(
        self,
        connection: sqlite3.Connection,
        expression_id: int,
        segment_id: int,
    ) -> None:
        relation = connection.execute(
            """
            SELECT 1 FROM expression_segments
            WHERE expression_id = ? AND segment_id = ?
            """,
            (expression_id, segment_id),
        ).fetchone()
        if relation is None:
            raise DatabaseError("검수할 표현과 장면의 연결을 찾을 수 없습니다.")

    def get_review(self, expression_id: int, segment_id: int) -> StoredReview | None:
        """표현-장면 관계의 번역과 검수 상태를 읽는다."""
        row = self.connection.execute(
            f"""
            SELECT {_REVIEW_COLUMNS}
            FROM reviews
            WHERE expression_id = ? AND segment_id = ?
            """,
            (expression_id, segment_id),
        ).fetchone()
        return _stored_review(row) if row is not None else None

    def get_ai_cache(
        self,
        *,
        service: str,
        model: str,
        instruction_version: str,
        input_content: object,
        response_model: type[CachedResponse],
    ) -> CachedResponse | None:
        """동일 AI 요청의 JSON을 요청한 Pydantic 자료형으로 다시 검증해 읽는다."""
        request_hash, input_hash, _ = _ai_cache_identity(
            service=service,
            model=model,
            instruction_version=instruction_version,
            input_content=input_content,
        )
        row = self.connection.execute(
            """
            SELECT input_hash, ai_service, ai_model, instruction_version, response_json
            FROM ai_cache
            WHERE request_hash = ?
            """,
            (request_hash,),
        ).fetchone()
        if row is None or (
            row["input_hash"] != input_hash
            or row["ai_service"] != service
            or row["ai_model"] != model
            or row["instruction_version"] != instruction_version
        ):
            return None
        try:
            return response_model.model_validate_json(row["response_json"])
        except (ValidationError, TypeError, ValueError):
            return None

    def put_ai_cache(
        self,
        *,
        service: str,
        model: str,
        instruction_version: str,
        input_content: object,
        response: BaseModel,
    ) -> None:
        """AI 구조화 응답을 canonical key와 JSON으로 저장한다."""
        request_hash, input_hash, _ = _ai_cache_identity(
            service=service,
            model=model,
            instruction_version=instruction_version,
            input_content=input_content,
        )
        response_json = _canonical_json(response.model_dump(mode="json", by_alias=True))
        with self.transaction() as connection:
            connection.execute(
                """
                INSERT INTO ai_cache (
                    request_hash, input_hash, ai_service, ai_model,
                    instruction_version, response_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(request_hash) DO UPDATE SET
                    input_hash = excluded.input_hash,
                    ai_service = excluded.ai_service,
                    ai_model = excluded.ai_model,
                    instruction_version = excluded.instruction_version,
                    response_json = excluded.response_json,
                    created_at = excluded.created_at
                """,
                (
                    request_hash,
                    input_hash,
                    service,
                    model,
                    instruction_version,
                    response_json,
                    _utc_now(),
                ),
            )

    def get_nadeshiko_search_cache(
        self,
        *,
        search_text: str,
        exact_match: bool,
        take: int,
        conditions: Mapping[str, object] | None = None,
    ) -> SearchResponse | None:
        """동일 Nadeshiko 검색의 원본 SDK 응답을 복원한다."""
        request_hash, conditions_json = _nadeshiko_cache_identity(
            search_text=search_text,
            exact_match=exact_match,
            take=take,
            conditions=conditions,
        )
        row = self.connection.execute(
            """
            SELECT search_text, exact_match, take, conditions_json, response_json
            FROM nadeshiko_search_cache
            WHERE request_hash = ?
            """,
            (request_hash,),
        ).fetchone()
        if row is None or (
            row["search_text"] != search_text
            or bool(row["exact_match"]) is not exact_match
            or row["take"] != take
            or row["conditions_json"] != conditions_json
        ):
            return None
        try:
            payload = json.loads(row["response_json"])
            if not isinstance(payload, dict):
                return None
            return SearchResponse.from_dict(payload)
        except (json.JSONDecodeError, KeyError, TypeError, ValueError, AttributeError):
            return None

    def put_nadeshiko_search_cache(
        self,
        *,
        search_text: str,
        exact_match: bool,
        take: int,
        response: SearchResponse,
        conditions: Mapping[str, object] | None = None,
    ) -> None:
        """Nadeshiko 원본 검색 응답을 surface 판정과 분리해 저장한다."""
        request_hash, conditions_json = _nadeshiko_cache_identity(
            search_text=search_text,
            exact_match=exact_match,
            take=take,
            conditions=conditions,
        )
        response_json = _canonical_json(response.to_dict())
        with self.transaction() as connection:
            connection.execute(
                """
                INSERT INTO nadeshiko_search_cache (
                    request_hash, search_text, exact_match, take,
                    conditions_json, response_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(request_hash) DO UPDATE SET
                    search_text = excluded.search_text,
                    exact_match = excluded.exact_match,
                    take = excluded.take,
                    conditions_json = excluded.conditions_json,
                    response_json = excluded.response_json,
                    created_at = excluded.created_at
                """,
                (
                    request_hash,
                    search_text,
                    int(exact_match),
                    take,
                    conditions_json,
                    response_json,
                    _utc_now(),
                ),
            )

    def get_nadeshiko_context_cache(
        self,
        *,
        segment_public_id: str,
        take: int,
    ) -> SegmentContextResponse | None:
        """같은 장면·같은 범위의 앞뒤 문맥 원본 응답을 복원한다."""
        if take <= 0:
            raise ValueError("Nadeshiko context cache의 take는 1 이상이어야 합니다.")
        row = self.connection.execute(
            """
            SELECT response_json FROM nadeshiko_context_cache
            WHERE segment_public_id = ? AND context_take = ?
            """,
            (segment_public_id, take),
        ).fetchone()
        if row is None:
            return None
        try:
            payload = json.loads(row["response_json"])
            if not isinstance(payload, dict):
                return None
            return SegmentContextResponse.from_dict(payload)
        except (json.JSONDecodeError, KeyError, TypeError, ValueError, AttributeError):
            return None

    def put_nadeshiko_context_cache(
        self,
        *,
        segment_public_id: str,
        take: int,
        response: SegmentContextResponse,
    ) -> None:
        """Nadeshiko 앞뒤 문맥 원본 응답을 SDK 직렬화 그대로 저장한다."""
        if take <= 0:
            raise ValueError("Nadeshiko context cache의 take는 1 이상이어야 합니다.")
        response_json = _canonical_json(response.to_dict())
        with self.transaction() as connection:
            connection.execute(
                """
                INSERT INTO nadeshiko_context_cache (
                    segment_public_id, context_take, response_json, created_at
                ) VALUES (?, ?, ?, ?)
                ON CONFLICT(segment_public_id, context_take) DO UPDATE SET
                    response_json = excluded.response_json,
                    created_at = excluded.created_at
                """,
                (segment_public_id, take, response_json, _utc_now()),
            )

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
        if version == 1:
            self._migrate_v1_to_v2()
            return

        existing_tables = self._application_tables()
        if existing_tables:
            raise DatabaseError(
                "schema version 0인 비어 있지 않은 DB는 자동 변경하지 않습니다. "
                "명시적인 migration이 필요합니다."
            )
        self._initialize_schema()

    def _migrate_v1_to_v2(self) -> None:
        """기존 v1 DB를 백업한 뒤 한 transaction에서 v2 구조로 옮긴다."""
        self.backup_before_schema_change()
        try:
            with self.transaction() as connection:
                for statement in _V1_TO_V2_STATEMENTS:
                    connection.execute(statement)
                connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
                self._verify_schema()
        except sqlite3.Error as error:
            raise DatabaseError(
                "SQLite v1 → v2 migration에 실패했습니다. "
                "원본 데이터는 변경 전 상태로 유지됩니다."
            ) from error

        if self.schema_version != SCHEMA_VERSION:
            raise DatabaseError("SQLite v2 schema version 저장을 확인할 수 없습니다.")

    def _initialize_schema(self) -> None:
        try:
            with self.transaction() as connection:
                for statement in _SCHEMA_STATEMENTS:
                    connection.execute(statement)
                connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
                self._verify_schema()
        except sqlite3.Error as error:
            raise DatabaseError("SQLite v1 schema 초기화에 실패했습니다.") from error

        if self.schema_version != SCHEMA_VERSION:
            raise DatabaseError("SQLite schema version 저장을 확인할 수 없습니다.")

    def _verify_schema(self) -> None:
        missing_tables = _EXPECTED_TABLES - self._application_tables()
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

    def _upsert_segment(self, connection: sqlite3.Connection, segment: Segment) -> int:
        connection.execute(
            """
            INSERT INTO media (nadeshiko_media_id)
            VALUES (?)
            ON CONFLICT(nadeshiko_media_id) DO NOTHING
            """,
            (segment.media_public_id,),
        )
        media_row = connection.execute(
            "SELECT id FROM media WHERE nadeshiko_media_id = ?",
            (segment.media_public_id,),
        ).fetchone()
        if media_row is None:
            raise DatabaseError("장면의 작품 ID를 저장할 수 없습니다.")

        connection.execute(
            """
            INSERT INTO segments (
                nadeshiko_segment_id, media_id, position, episode,
                start_time_ms, end_time_ms, external_video_id, japanese_text,
                video_url, audio_url, image_url, raw_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(nadeshiko_segment_id) DO UPDATE SET
                media_id = excluded.media_id,
                position = excluded.position,
                episode = excluded.episode,
                start_time_ms = excluded.start_time_ms,
                end_time_ms = excluded.end_time_ms,
                external_video_id = excluded.external_video_id,
                japanese_text = excluded.japanese_text,
                video_url = excluded.video_url,
                audio_url = excluded.audio_url,
                image_url = excluded.image_url,
                raw_json = excluded.raw_json
            """,
            (
                segment.public_id,
                media_row["id"],
                segment.position,
                segment.episode,
                segment.start_time_ms,
                segment.end_time_ms,
                segment.external_video_id,
                segment.text_ja.content,
                segment.urls.video_url,
                segment.urls.audio_url,
                segment.urls.image_url,
                _canonical_json(segment.to_dict()),
            ),
        )
        segment_row = connection.execute(
            "SELECT id FROM segments WHERE nadeshiko_segment_id = ?",
            (segment.public_id,),
        ).fetchone()
        if segment_row is None:
            raise DatabaseError("Nadeshiko 장면을 저장할 수 없습니다.")
        return int(segment_row["id"])

    def _load_expression(self, row: sqlite3.Row) -> StoredExpression:
        expression_id = int(row["id"])
        segment_rows = self.connection.execute(
            """
            SELECT
                segments.id,
                segments.raw_json,
                reviews.decision,
                reviews.direct_meaning,
                reviews.natural_translation,
                reviews.scene_usage,
                reviews.notes,
                reviews.translation_ai_service,
                reviews.translation_ai_model,
                reviews.translation_instruction_version,
                reviews.translation_input_hash,
                reviews.translated_at,
                reviews.updated_at
            FROM expression_segments
            JOIN segments ON segments.id = expression_segments.segment_id
            LEFT JOIN reviews
                ON reviews.expression_id = expression_segments.expression_id
                AND reviews.segment_id = expression_segments.segment_id
            WHERE expression_segments.expression_id = ?
            ORDER BY expression_segments.ordinal, segments.id
            """,
            (expression_id,),
        ).fetchall()
        segments = tuple(_stored_segment(segment_row) for segment_row in segment_rows)
        return StoredExpression(
            id=expression_id,
            candidate=ExpressionCandidate(
                japanese=row["japanese"],
                reading=row["reading"],
                meaning_ko=row["meaning_ko"],
                register=row["register_text"],
            ),
            selected=bool(row["is_selected"]),
            segments=segments,
        )


def _required_media_id(nadeshiko_media_id: str) -> str:
    if not isinstance(nadeshiko_media_id, str) or not nadeshiko_media_id.strip():
        raise ValueError("Nadeshiko 작품 public ID를 입력해야 합니다.")
    return nadeshiko_media_id.strip()


def _stored_media(row: sqlite3.Row) -> StoredMedia:
    return StoredMedia(
        id=int(row["id"]),
        nadeshiko_media_id=row["nadeshiko_media_id"],
        display_name=row["display_name"],
        preference=row["preference"],
        content_group=row["content_group"],
        is_active=bool(row["is_active"]),
    )


def _stored_segment(row: sqlite3.Row) -> StoredSegment:
    try:
        payload = json.loads(row["raw_json"])
        if not isinstance(payload, dict):
            raise TypeError("segment raw JSON must be an object")
        segment = Segment.from_dict(payload)
    except (json.JSONDecodeError, KeyError, TypeError, ValueError, AttributeError) as error:
        raise DatabaseError("저장된 Nadeshiko 장면 JSON을 복원할 수 없습니다.") from error

    review = _stored_review(row) if row["updated_at"] is not None else None
    return StoredSegment(id=int(row["id"]), segment=segment, review=review)


def _stored_review(row: sqlite3.Row) -> StoredReview:
    return StoredReview(
        decision=row["decision"],
        direct_meaning=row["direct_meaning"],
        natural_translation=row["natural_translation"],
        scene_usage=row["scene_usage"],
        notes=row["notes"],
        translation_ai_service=row["translation_ai_service"],
        translation_ai_model=row["translation_ai_model"],
        translation_instruction_version=row["translation_instruction_version"],
        translation_input_hash=row["translation_input_hash"],
        translated_at=row["translated_at"],
        updated_at=row["updated_at"],
    )


def _ai_cache_identity(
    *,
    service: str,
    model: str,
    instruction_version: str,
    input_content: object,
) -> tuple[str, str, str]:
    input_json = _canonical_json(input_content)
    input_hash = _sha256(input_json)
    request_hash = _sha256(
        _canonical_json(
            {
                "service": service,
                "model": model,
                "instruction_version": instruction_version,
                "input_hash": input_hash,
            }
        )
    )
    return request_hash, input_hash, input_json


def _nadeshiko_cache_identity(
    *,
    search_text: str,
    exact_match: bool,
    take: int,
    conditions: Mapping[str, object] | None,
) -> tuple[str, str]:
    if take <= 0:
        raise ValueError("Nadeshiko cache의 take는 1 이상이어야 합니다.")
    conditions_json = _canonical_json(dict(conditions or {}))
    request_hash = _sha256(
        _canonical_json(
            {
                "search": search_text,
                "exact_match": exact_match,
                "take": take,
                "conditions": json.loads(conditions_json),
            }
        )
    )
    return request_hash, conditions_json


def _canonical_json(value: object) -> str:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    except (TypeError, ValueError) as error:
        raise ValueError("캐시 입력과 응답은 JSON으로 직렬화할 수 있어야 합니다.") from error


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _last_row_id(cursor: sqlite3.Cursor) -> int:
    if cursor.lastrowid is None:
        raise DatabaseError("SQLite가 새 행의 ID를 반환하지 않았습니다.")
    return int(cursor.lastrowid)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
