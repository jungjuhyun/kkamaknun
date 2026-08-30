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

_POOL_PATH = Path(__file__).with_name("curated_media_pool.json")
_GROUPS = frozenset({"A", "B"})
_TIERS = frozenset({1, 2, 3})
_GRADES = frozenset({"A", "B", "C"})
_KINDS = frozenset({"series_or_franchise", "standalone_movie"})
_STATUSES = frozenset({"nadeshiko", "nadeshiko_partial", "jimaku_required"})
_NADESHIKO_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{12}$")

STATUS_LABELS = {
    "nadeshiko": "장면 검색 바로 가능",
    "nadeshiko_partial": "연결된 일부만 장면 검색 가능",
    "jimaku_required": "일본어 자막 준비 필요",
}


class CuratedPoolError(ValueError):
    """curated 데이터 파일이 손상됐거나 계약을 위반할 때 발생한다."""


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


@dataclass(frozen=True)
class CuratedItemView:
    """현재 DB 상태를 반영한 curated 항목의 화면용 상태."""

    item: CuratedItem
    checkable: bool
    checked: bool
    local_media_row_ids: tuple[int, ...]
    status_label: str


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


def _local_rows_for(item: CuratedItem, media_rows: tuple[StoredMedia, ...]) -> tuple[StoredMedia, ...]:
    """색인된 로컬 자막 작품을 표시명(한국/일본 제목 정확 일치)으로 연결한다."""
    titles = {item.korean_title, item.japanese_title}
    return tuple(
        media
        for media in media_rows
        if media.source == "local" and (media.display_name or "") in titles
    )


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
        if item.source_status in {"nadeshiko", "nadeshiko_partial"}:
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
    - Jimaku 항목: 색인된 로컬 자막 media가 있을 때만 동작하고,
      없으면 오류로 알린다(가짜 media를 만들지 않는다).
    - 항목에 연결되지 않은 media는 건드리지 않는다.
    """
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
