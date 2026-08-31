"""curated 작품 풀 로딩과 체크 활성화 로직 (작업 10.5).

정적 curated_media_pool.json을 표준 라이브러리로 읽고, 사용자 체크를
기존 media.is_active 구조에 연결한다. 새 schema·검색 알고리즘 없음.
Jimaku 경로 작품은 자막이 실제로 색인된 경우에만 활성화할 수 있다.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from scene_collector.database import SceneCollectorDatabase, StoredMedia
from scene_collector.subtitles import SubtitleIndexReport, index_source_unit

_POOL_PATH = Path(__file__).with_name("curated_media_pool.json")
_GROUPS = frozenset({"A", "B"})
_TIERS = frozenset({1, 2, 3})
_GRADES = frozenset({"A", "B", "C"})
_KINDS = frozenset({"series_or_franchise", "standalone_movie"})
_STATUSES = frozenset({"nadeshiko", "nadeshiko_partial", "jimaku_required"})
_UNIT_KINDS = frozenset({"nadeshiko", "jimaku", "unavailable"})
_UNIT_MEDIA_TYPES = frozenset({"tv", "movie"})
_NADESHIKO_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{12}$")

STATUS_LABELS = {
    "nadeshiko": "장면 검색 바로 가능",
    "nadeshiko_partial": "연결된 일부만 장면 검색 가능",
    "jimaku_required": "일본어 자막 준비 필요",
}


class CuratedPoolError(ValueError):
    """curated 데이터 파일이 손상됐거나 계약을 위반할 때 발생한다."""


@dataclass(frozen=True)
class CuratedSourceUnit:
    """curated 항목(프랜차이즈) 아래의 실제 검색 자료 단위.

    사용자 선택 단위는 프랜차이즈 하나지만, 실제 검색은 이 단위들로 이뤄진다.
    kind: 'nadeshiko'(바로 검색), 'jimaku'(사용자가 자막을 색인해야 검색),
    'unavailable'(현재 사용 가능한 텍스트 자막이 확인되지 않음).
    """

    key: str
    label: str
    media_type: str
    kind: str
    nadeshiko_media_id: str | None
    jimaku_entry_id: int | None
    coverage: str


@dataclass(frozen=True)
class CuratedItem:
    """사용자가 체크하는 curated 선택 단위(작품/프랜차이즈)."""

    key: str
    korean_title: str
    japanese_title: str
    group: str
    tier: int
    popularity_evidence_grade: str
    kind: str
    source_status: str
    nadeshiko_media_ids: tuple[str, ...]
    jimaku_entry_ids: tuple[int, ...]
    note: str
    source_units: tuple[CuratedSourceUnit, ...] = ()


@dataclass(frozen=True)
class SourceUnitView:
    """현재 DB 상태를 반영한 source unit 하나의 화면용 상태."""

    unit: CuratedSourceUnit
    status: str
    status_label: str
    local_media_row_id: int | None
    indexable: bool


@dataclass(frozen=True)
class CuratedItemView:
    """현재 DB 상태를 반영한 curated 항목의 화면용 상태."""

    item: CuratedItem
    checkable: bool
    checked: bool
    local_media_row_ids: tuple[int, ...]
    status_label: str
    unit_views: tuple[SourceUnitView, ...] = ()


def load_curated_pool(path: Path = _POOL_PATH) -> tuple[CuratedItem, ...]:
    """curated 후보 풀을 읽고 계약(97개, A63/B34, 필드 유효성)을 검증한다."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise CuratedPoolError(f"curated 데이터 파일을 읽을 수 없습니다: {error}") from error

    raw_items = payload.get("items")
    if not isinstance(raw_items, list) or not raw_items:
        raise CuratedPoolError("curated 데이터에 items가 없습니다.")

    items: list[CuratedItem] = []
    for raw in raw_items:
        item = CuratedItem(
            key=raw["key"],
            korean_title=raw["korean_title"],
            japanese_title=raw["japanese_title"],
            group=raw["group"],
            tier=int(raw["tier"]),
            popularity_evidence_grade=raw["popularity_evidence_grade"],
            kind=raw["kind"],
            source_status=raw["source_status"],
            nadeshiko_media_ids=tuple(raw["nadeshiko_media_ids"]),
            jimaku_entry_ids=tuple(int(v) for v in raw["jimaku_entry_ids"]),
            note=raw.get("note", ""),
            source_units=tuple(
                CuratedSourceUnit(
                    key=unit["key"],
                    label=unit["label"],
                    media_type=unit["media_type"],
                    kind=unit["kind"],
                    nadeshiko_media_id=unit.get("nadeshiko_media_id"),
                    jimaku_entry_id=(
                        int(unit["jimaku_entry_id"])
                        if unit.get("jimaku_entry_id") is not None
                        else None
                    ),
                    coverage=unit.get("coverage", ""),
                )
                for unit in raw.get("source_units", ())
            ),
        )
        _validate_item(item)
        items.append(item)

    keys = [item.key for item in items]
    if len(set(keys)) != len(keys):
        raise CuratedPoolError("curated key가 중복됩니다.")
    all_ids = [nid for item in items for nid in item.nadeshiko_media_ids]
    if len(set(all_ids)) != len(all_ids):
        raise CuratedPoolError("같은 Nadeshiko media ID가 여러 항목에 연결됐습니다.")
    return tuple(items)


def _validate_item(item: CuratedItem) -> None:
    if not item.key or not item.korean_title or not item.japanese_title:
        raise CuratedPoolError(f"필수 문자열이 비어 있습니다: {item.key!r}")
    if item.group not in _GROUPS:
        raise CuratedPoolError(f"{item.key}: group이 A/B가 아닙니다.")
    if item.tier not in _TIERS:
        raise CuratedPoolError(f"{item.key}: tier가 1/2/3이 아닙니다.")
    if item.popularity_evidence_grade not in _GRADES:
        raise CuratedPoolError(f"{item.key}: 근거 등급이 A/B/C가 아닙니다.")
    if item.kind not in _KINDS:
        raise CuratedPoolError(f"{item.key}: kind가 유효하지 않습니다.")
    if item.source_status not in _STATUSES:
        raise CuratedPoolError(f"{item.key}: source_status가 유효하지 않습니다.")
    for nid in item.nadeshiko_media_ids:
        if not _NADESHIKO_ID_PATTERN.fullmatch(nid):
            raise CuratedPoolError(f"{item.key}: Nadeshiko ID 형식 오류 {nid!r}")
    if item.source_status in {"nadeshiko", "nadeshiko_partial"}:
        if not item.nadeshiko_media_ids:
            raise CuratedPoolError(f"{item.key}: Nadeshiko 항목에 media ID가 없습니다.")
    else:
        if item.nadeshiko_media_ids:
            raise CuratedPoolError(f"{item.key}: Jimaku 항목에 Nadeshiko ID가 있습니다.")
        if not item.jimaku_entry_ids:
            raise CuratedPoolError(f"{item.key}: Jimaku 항목에 entry 참조가 없습니다.")
    if item.source_units:
        _validate_source_units(item)


def _validate_source_units(item: CuratedItem) -> None:
    """source unit 목록이 항목의 기존 ID 목록과 정확히 대응하는지 검증한다."""
    keys = [unit.key for unit in item.source_units]
    if len(set(keys)) != len(keys):
        raise CuratedPoolError(f"{item.key}: source unit key가 중복됩니다.")

    nadeshiko_ids: list[str] = []
    jimaku_ids: list[int] = []
    for unit in item.source_units:
        if not unit.key or not unit.label:
            raise CuratedPoolError(f"{item.key}: source unit의 key/label이 비어 있습니다.")
        if unit.kind not in _UNIT_KINDS:
            raise CuratedPoolError(f"{item.key}/{unit.key}: unit kind가 유효하지 않습니다.")
        if unit.media_type not in _UNIT_MEDIA_TYPES:
            raise CuratedPoolError(f"{item.key}/{unit.key}: media_type이 유효하지 않습니다.")
        if unit.kind == "nadeshiko":
            if unit.nadeshiko_media_id is None or not _NADESHIKO_ID_PATTERN.fullmatch(
                unit.nadeshiko_media_id
            ):
                raise CuratedPoolError(
                    f"{item.key}/{unit.key}: nadeshiko unit의 media ID가 유효하지 않습니다."
                )
            nadeshiko_ids.append(unit.nadeshiko_media_id)
        elif unit.kind == "jimaku":
            if unit.jimaku_entry_id is None:
                raise CuratedPoolError(
                    f"{item.key}/{unit.key}: jimaku unit에 entry ID가 없습니다."
                )
            if unit.nadeshiko_media_id is not None:
                raise CuratedPoolError(
                    f"{item.key}/{unit.key}: jimaku unit에 Nadeshiko ID가 있습니다."
                )
            jimaku_ids.append(unit.jimaku_entry_id)

    if sorted(nadeshiko_ids) != sorted(item.nadeshiko_media_ids):
        raise CuratedPoolError(
            f"{item.key}: nadeshiko source unit이 nadeshiko_media_ids와 일치하지 않습니다."
        )
    if sorted(jimaku_ids) != sorted(item.jimaku_entry_ids):
        raise CuratedPoolError(
            f"{item.key}: jimaku source unit이 jimaku_entry_ids와 일치하지 않습니다."
        )


def _local_rows_for(item: CuratedItem, media_rows: tuple[StoredMedia, ...]) -> tuple[StoredMedia, ...]:
    """색인된 로컬 자막 작품을 표시명(한국/일본 제목 정확 일치)으로 연결한다."""
    titles = {item.korean_title, item.japanese_title}
    return tuple(
        media
        for media in media_rows
        if media.source == "local" and (media.display_name or "") in titles
    )


def unit_local_media_title(item: CuratedItem, unit: CuratedSourceUnit) -> str:
    """source unit용 canonical 로컬 작품 표시명.

    사용자가 UI에서 unit을 고르면 프로그램이 이 이름으로 색인하므로,
    연결은 문자열 추측이 아니라 프로그램이 정한 정확한 이름 일치다.
    """
    return f"{item.korean_title} · {unit.label}"


def _unit_local_row(
    item: CuratedItem,
    unit: CuratedSourceUnit,
    media_rows: tuple[StoredMedia, ...],
) -> StoredMedia | None:
    canonical = unit_local_media_title(item, unit)
    for media in media_rows:
        if media.source == "local" and media.display_name == canonical:
            return media
    return None


def _unit_views(
    item: CuratedItem,
    media_rows: tuple[StoredMedia, ...],
) -> tuple[SourceUnitView, ...]:
    views: list[SourceUnitView] = []
    for unit in item.source_units:
        if unit.kind == "nadeshiko":
            views.append(
                SourceUnitView(
                    unit=unit,
                    status="nadeshiko_ready",
                    status_label=f"장면 검색·제작 가능 · {unit.coverage}",
                    local_media_row_id=None,
                    indexable=False,
                )
            )
        elif unit.kind == "jimaku":
            row = _unit_local_row(item, unit, media_rows)
            if row is not None:
                views.append(
                    SourceUnitView(
                        unit=unit,
                        status="indexed",
                        status_label="로컬 자막 색인됨 · 위치 확인만 가능",
                        local_media_row_id=row.id,
                        indexable=True,
                    )
                )
            else:
                views.append(
                    SourceUnitView(
                        unit=unit,
                        status="needs_subtitles",
                        status_label=f"자막 준비 필요 · {unit.coverage}",
                        local_media_row_id=None,
                        indexable=True,
                    )
                )
        else:
            views.append(
                SourceUnitView(
                    unit=unit,
                    status="unavailable",
                    status_label=f"현재 검색 불가 · {unit.coverage}",
                    local_media_row_id=None,
                    indexable=False,
                )
            )
    return tuple(views)


def _indexed_unit_rows(
    item: CuratedItem,
    media_rows: tuple[StoredMedia, ...],
) -> tuple[StoredMedia, ...]:
    rows: list[StoredMedia] = []
    for unit in item.source_units:
        if unit.kind != "jimaku":
            continue
        row = _unit_local_row(item, unit, media_rows)
        if row is not None:
            rows.append(row)
    return tuple(rows)


def _is_item_checked(item: CuratedItem, media_rows: tuple[StoredMedia, ...]) -> bool:
    """프랜차이즈 체크 상태: 준비된 source 전부가 활성일 때만 ON이다."""
    nadeshiko_by_id = {
        media.nadeshiko_media_id: media
        for media in media_rows
        if media.nadeshiko_media_id is not None
    }
    indexed_rows = _indexed_unit_rows(item, media_rows)
    if item.nadeshiko_media_ids:
        mapped = [nadeshiko_by_id.get(nid) for nid in item.nadeshiko_media_ids]
        nadeshiko_ok = all(media is not None and media.is_active for media in mapped)
        return nadeshiko_ok and all(row.is_active for row in indexed_rows)
    if indexed_rows:
        return all(row.is_active for row in indexed_rows)
    return False


def _unit_item_summary(unit_views: tuple[SourceUnitView, ...]) -> str:
    searchable = sum(1 for view in unit_views if view.status in {"nadeshiko_ready", "indexed"})
    needs = sum(1 for view in unit_views if view.status == "needs_subtitles")
    unavailable = sum(1 for view in unit_views if view.status == "unavailable")
    parts = [f"검색 가능 {searchable}개"]
    if needs:
        parts.append(f"자막 준비 필요 {needs}개")
    if unavailable:
        parts.append(f"검색 불가 {unavailable}개")
    return " · ".join(parts)


def _nadeshiko_status_label(item: CuratedItem) -> str:
    """Nadeshiko 작품의 상태 문구.

    부분 지원 작품은 전체 시리즈가 아니라 연결된 것만 검색된다는 사실과 그 개수를
    함께 알린다. 공개 ID는 사용자에게 의미가 없으므로 노출하지 않고, 어느 시즌이
    빠졌는지는 자료에 없으므로 추측하지 않는다.
    """
    label = STATUS_LABELS[item.source_status]
    if item.source_status != "nadeshiko_partial":
        return label
    return f"{label} · 연결 {len(item.nadeshiko_media_ids)}개"


def curated_views(
    database: SceneCollectorDatabase,
    pool: tuple[CuratedItem, ...],
) -> tuple[CuratedItemView, ...]:
    """DB의 현재 media 상태를 읽어 각 curated 항목의 체크 상태를 만든다.

    이 함수는 DB를 읽기만 하며 media를 생성·활성화하지 않는다.
    """
    media_rows = database.list_media()
    nadeshiko_by_id = {
        media.nadeshiko_media_id: media
        for media in media_rows
        if media.nadeshiko_media_id is not None
    }

    views: list[CuratedItemView] = []
    for item in pool:
        if item.source_units:
            unit_views = _unit_views(item, media_rows)
            indexed_rows = _indexed_unit_rows(item, media_rows)
            checkable = bool(item.nadeshiko_media_ids) or bool(indexed_rows)
            views.append(
                CuratedItemView(
                    item=item,
                    checkable=checkable,
                    checked=_is_item_checked(item, media_rows),
                    local_media_row_ids=tuple(row.id for row in indexed_rows),
                    status_label=_unit_item_summary(unit_views),
                    unit_views=unit_views,
                )
            )
        elif item.source_status in {"nadeshiko", "nadeshiko_partial"}:
            mapped = [nadeshiko_by_id.get(nid) for nid in item.nadeshiko_media_ids]
            checked = all(media is not None and media.is_active for media in mapped)
            views.append(
                CuratedItemView(
                    item=item,
                    checkable=True,
                    checked=checked,
                    local_media_row_ids=(),
                    status_label=_nadeshiko_status_label(item),
                )
            )
        else:
            local_rows = _local_rows_for(item, media_rows)
            if local_rows:
                views.append(
                    CuratedItemView(
                        item=item,
                        checkable=True,
                        checked=all(media.is_active for media in local_rows),
                        local_media_row_ids=tuple(media.id for media in local_rows),
                        status_label="로컬 자막 색인됨",
                    )
                )
            else:
                views.append(
                    CuratedItemView(
                        item=item,
                        checkable=False,
                        checked=False,
                        local_media_row_ids=(),
                        status_label=STATUS_LABELS["jimaku_required"],
                    )
                )
    return tuple(views)


def set_curated_item_active(
    database: SceneCollectorDatabase,
    item: CuratedItem,
    active: bool,
) -> None:
    """사용자 체크 하나를 항목에 연결된 media 전체의 is_active로 반영한다.

    - Nadeshiko 항목: 체크 시 mapped entry를 upsert 후 전부 활성,
      해제 시 이미 저장된 entry만 전부 비활성(없는 entry를 만들지 않는다).
    - source unit이 있는 항목: 위에 더해, 색인된 unit의 로컬 자막 media도
      함께 활성/비활성한다. 색인 전 unit은 media를 만들지 않는다.
    - Jimaku 항목: 색인된 로컬 자막 media가 있을 때만 동작하고,
      없으면 오류로 알린다(가짜 media를 만들지 않는다).
    - 항목에 연결되지 않은 media는 건드리지 않는다.
    """
    if item.source_units:
        indexed_rows = _indexed_unit_rows(item, database.list_media())
        if active:
            for nid in item.nadeshiko_media_ids:
                database.upsert_media(nid, display_name=item.korean_title)
                database.set_media_active(nid, True)
        else:
            for nid in item.nadeshiko_media_ids:
                if database.get_media(nid) is not None:
                    database.set_media_active(nid, False)
        for row in indexed_rows:
            database.set_local_media_active(row.id, active)
        return

    if item.source_status in {"nadeshiko", "nadeshiko_partial"}:
        if active:
            for nid in item.nadeshiko_media_ids:
                database.upsert_media(nid, display_name=item.korean_title)
                database.set_media_active(nid, True)
        else:
            for nid in item.nadeshiko_media_ids:
                if database.get_media(nid) is not None:
                    database.set_media_active(nid, False)
        return

    local_rows = _local_rows_for(item, database.list_media())
    if not local_rows:
        raise CuratedPoolError(
            f"'{item.korean_title}'은(는) 일본어 자막을 색인한 뒤에만 활성화할 수 있습니다. "
            f"자막 확보 후 index_local_subtitles로 색인하세요. (Jimaku entry: "
            f"{', '.join(str(v) for v in item.jimaku_entry_ids)})"
        )
    for media in local_rows:
        database.set_local_media_active(media.id, active)


def index_source_unit_subtitles(
    database: SceneCollectorDatabase,
    item: CuratedItem,
    unit: CuratedSourceUnit,
    directory: Path,
) -> tuple[StoredMedia, SubtitleIndexReport]:
    """사용자가 UI에서 고른 source unit의 자막 폴더를 검증·색인·연결한다.

    canonical 표시명은 프로그램이 정하므로 로컬 media와 unit의 연결은 명시적이다.
    새로 색인된 unit의 활성 상태는 현재 프랜차이즈 체크 상태를 따른다 — 체크가
    꺼져 있으면 색인만 되고 검색 대상에는 들어가지 않는다.
    """
    if unit not in item.source_units:
        raise CuratedPoolError(f"'{unit.label}'은(는) '{item.korean_title}'의 source unit이 아닙니다.")
    if unit.kind != "jimaku":
        raise CuratedPoolError(f"'{unit.label}'은(는) 자막 색인 대상이 아닙니다.")

    checked_before = _is_item_checked(item, database.list_media())
    canonical = unit_local_media_title(item, unit)
    media, report = index_source_unit(
        database, canonical, directory, media_type=unit.media_type
    )
    database.set_local_media_active(media.id, checked_before)
    refreshed = database.find_local_media(canonical)
    return (refreshed if refreshed is not None else media), report
