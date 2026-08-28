"""공식 Nadeshiko 작품 검색·조회를 로컬 선호작 저장에 연결한다."""

from __future__ import annotations

from nadeshiko import Nadeshiko
from nadeshiko.models import Media, MediaSummary

from scene_collector.database import SceneCollectorDatabase, StoredMedia


def search_media(
    client: Nadeshiko,
    query: str,
    *,
    take: int | None = None,
) -> tuple[MediaSummary, ...]:
    """공식 SDK 작품명 검색으로 안정적인 public ID와 표시명 후보를 가져온다."""
    text = query.strip()
    if not text:
        raise ValueError("찾을 작품명을 입력해야 합니다.")
    if take is None:
        response = client.search_media(query=text)
    else:
        response = client.search_media(query=text, take=take)
    return tuple(response.media)


def media_display_name(media: Media | MediaSummary) -> str | None:
    """공식 metadata에서 사람에게 보여줄 표시 작품명을 고른다."""
    for name in (media.name_ja, media.name_romaji, media.name_en):
        if isinstance(name, str) and name.strip():
            return name.strip()
    return None


def store_media(database: SceneCollectorDatabase, media: Media | MediaSummary) -> StoredMedia:
    """검색·조회한 작품의 public ID와 표시명을 로컬 선호작으로 저장한다."""
    return database.upsert_media(media.public_id, display_name=media_display_name(media))


def refresh_media_metadata(
    database: SceneCollectorDatabase,
    client: Nadeshiko,
    nadeshiko_media_id: str,
) -> StoredMedia:
    """필요한 작품 하나만 공식 get_media로 조회해 표시명 metadata를 갱신한다.

    기존 사용자 preference/content_group/is_active는 덮어쓰지 않는다.
    """
    media = client.get_media(nadeshiko_media_id)
    return store_media(database, media)
