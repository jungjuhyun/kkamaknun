import copy
import json
import re
from collections import Counter
from pathlib import Path

import pytest
from nadeshiko.models import MediaSummary, SearchFilters, SearchQuery, SearchResponse

import scene_collector.search as search_module
from scene_collector.config import AISettings, AppSettings, SearchSettings, StorageSettings
from scene_collector.curated import (
    CuratedPoolError,
    curated_views,
    load_curated_pool,
    set_curated_item_active,
)
from scene_collector.database import DatabaseError, SceneCollectorDatabase
from scene_collector.media import store_media
from scene_collector.models import ExpressionCandidate, ExpressionCandidates
from scene_collector.search import search_expressions
from scene_collector.subtitles import index_local_subtitles

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "nadeshiko_search_response.json"

SRT_SAMPLE = """1
00:00:01,000 --> 00:00:02,500
大丈夫ですか？
"""


def _settings(work_data_dir: Path) -> AppSettings:
    return AppSettings(
        storage=StorageSettings(work_data_dir=work_data_dir),
        ai=AISettings(service="provider-one", model="model-one"),
        search=SearchSettings(candidate_count=3, nadeshiko_take=2),
    )


def _item(pool, key):
    matches = [item for item in pool if item.key == key]
    assert len(matches) == 1, key
    return matches[0]


def _view(database, pool, key):
    views = [view for view in curated_views(database, pool) if view.item.key == key]
    assert len(views) == 1, key
    return views[0]


def test_curated_pool_contract() -> None:
    pool = load_curated_pool()

    assert len(pool) == 97
    keys = [item.key for item in pool]
    assert len(set(keys)) == 97

    groups = Counter(item.group for item in pool)
    assert groups["A"] == 63
    assert groups["B"] == 34

    assert all(item.tier in (1, 2, 3) for item in pool)
    assert all(item.popularity_evidence_grade in ("A", "B", "C") for item in pool)
    assert all(
        item.kind in ("series_or_franchise", "standalone_movie") for item in pool
    )

    all_ids = [nid for item in pool for nid in item.nadeshiko_media_ids]
    assert len(all_ids) == len(set(all_ids))
    id_pattern = re.compile(r"^[A-Za-z0-9_-]{12}$")
    assert all(id_pattern.fullmatch(nid) for nid in all_ids)

    for item in pool:
        if item.source_status in ("nadeshiko", "nadeshiko_partial"):
            assert item.nadeshiko_media_ids
        else:
            assert item.source_status == "jimaku_required"
            assert not item.nadeshiko_media_ids
            assert item.jimaku_entry_ids

    chainsaw = _item(pool, "chainsaw_man")
    assert "_BFaSkaRJ8tf" in chainsaw.nadeshiko_media_ids
    assert len(chainsaw.nadeshiko_media_ids) == 2


def test_check_and_uncheck_updates_only_mapped_media(tmp_path: Path) -> None:
    pool = load_curated_pool()
    chainsaw = _item(pool, "chainsaw_man")
    suzume = _item(pool, "suzume_no_tojimari")

    settings = _settings(tmp_path)
    with SceneCollectorDatabase.open(settings) as database:
        manual = MediaSummary(
            public_id="anonymous-media-001",
            slug="anonymous-media",
            name_ja="수동 추가 작품",
            name_romaji="",
            name_en="",
            cover_url="https://media.example.invalid/cover.webp",
            category="ANIME",
        )
        store_media(database, manual)

        # 체크: mapped entry 전부 upsert + 활성
        set_curated_item_active(database, chainsaw, True)
        set_curated_item_active(database, suzume, True)
        for nid in chainsaw.nadeshiko_media_ids + suzume.nadeshiko_media_ids:
            stored = database.get_media(nid)
            assert stored is not None
            assert stored.is_active is True
            assert stored.display_name in {chainsaw.korean_title, suzume.korean_title}

        assert _view(database, pool, "chainsaw_man").checked is True
        assert _view(database, pool, "suzume_no_tojimari").checked is True

        # 해제: 그 항목의 entry만 비활성, 다른 curated·수동 media는 영향 없음
        set_curated_item_active(database, chainsaw, False)
        for nid in chainsaw.nadeshiko_media_ids:
            stored = database.get_media(nid)
            assert stored is not None and stored.is_active is False
        assert _view(database, pool, "chainsaw_man").checked is False
        assert _view(database, pool, "suzume_no_tojimari").checked is True
        manual_row = database.get_media("anonymous-media-001")
        assert manual_row is not None and manual_row.is_active is True

        # 다른 curated 항목의 media는 생성되지 않았다 (97개 자동 삽입 금지)
        stored_ids = {
            media.nadeshiko_media_id
            for media in database.list_media()
            if media.nadeshiko_media_id
        }
        expected = set(chainsaw.nadeshiko_media_ids + suzume.nadeshiko_media_ids) | {
            "anonymous-media-001"
        }
        assert stored_ids == expected

    # 재실행(DB reopen) 후 체크 상태 유지
    with SceneCollectorDatabase.open(settings) as reopened:
        assert _view(reopened, pool, "suzume_no_tojimari").checked is True
        assert _view(reopened, pool, "chainsaw_man").checked is False


def test_unchecking_missing_rows_is_safe(tmp_path: Path) -> None:
    pool = load_curated_pool()
    frieren = _item(pool, "sousou_no_frieren")
    settings = _settings(tmp_path)
    with SceneCollectorDatabase.open(settings) as database:
        set_curated_item_active(database, frieren, False)
        assert database.list_media() == ()


class RecordingNadeshiko:
    def __init__(self, response: SearchResponse) -> None:
        self.response = response
        self.calls: list[tuple[str, bool, tuple[str, ...]]] = []

    def search(
        self,
        *,
        query: SearchQuery,
        take: int,
        filters: SearchFilters,
    ) -> SearchResponse:
        included = tuple(item.media_public_id for item in filters.media.include)
        self.calls.append((query.search, bool(query.exact_match), included))
        return self.response


def _empty_response() -> SearchResponse:
    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    payload["pagination"] = {
        "hasMore": False,
        "estimatedTotalHits": 0,
        "estimatedTotalHitsRelation": "EXACT",
        "cursor": None,
    }
    payload["segments"] = []
    return SearchResponse.from_dict(payload)


def test_checked_items_drive_existing_search_media_filter(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        search_module,
        "create_structured_response",
        lambda *args, **kwargs: ExpressionCandidates(
            candidates=[
                ExpressionCandidate(
                    japanese="大丈夫ですか",
                    reading="だいじょうぶですか",
                    meaning_ko="괜찮으세요?",
                    register="존댓말",
                )
            ]
            * 3
        ),
    )
    pool = load_curated_pool()
    chainsaw = _item(pool, "chainsaw_man")
    settings = _settings(tmp_path)
    client = RecordingNadeshiko(_empty_response())

    with SceneCollectorDatabase.open(settings) as database:
        set_curated_item_active(database, chainsaw, True)

        search_expressions(
            settings, "괜찮냐고 묻는 말", nadeshiko_client=client, database=database
        )
        assert client.calls
        for _, _, included in client.calls:
            assert included == tuple(sorted(chainsaw.nadeshiko_media_ids))

        # 해제 후에는 활성 작품이 없어 기존 오류 동작으로 돌아간다
        set_curated_item_active(database, chainsaw, False)
        client.calls.clear()
        with pytest.raises(search_module.NoActiveMediaError):
            search_expressions(
                settings, "괜찮냐고 묻는 말", nadeshiko_client=client, database=database
            )
        assert client.calls == []


def test_jimaku_only_item_requires_indexed_subtitles(tmp_path: Path) -> None:
    pool = load_curated_pool()
    chihiro = _item(pool, "sen_to_chihiro")
    settings = _settings(tmp_path)

    with SceneCollectorDatabase.open(settings) as database:
        view = _view(database, pool, "sen_to_chihiro")
        assert view.checkable is False
        assert view.checked is False
        assert view.status_label == "일본어 자막 준비 필요"

        # 색인 전 활성화 시도는 오류이고, 가짜 media row를 만들지 않는다
        with pytest.raises(CuratedPoolError, match="색인"):
            set_curated_item_active(database, chihiro, True)
        assert database.list_media() == ()

        # curated 한국 제목으로 자막을 색인하면 체크 가능해진다
        directory = tmp_path / "subs"
        directory.mkdir()
        (directory / "영화.srt").write_text(SRT_SAMPLE, encoding="utf-8")
        index_local_subtitles(database, chihiro.korean_title, directory)

        view = _view(database, pool, "sen_to_chihiro")
        assert view.checkable is True
        assert view.checked is True  # 색인 시 기본 활성
        assert view.status_label == "로컬 자막 색인됨"

        set_curated_item_active(database, chihiro, False)
        assert _view(database, pool, "sen_to_chihiro").checked is False
        set_curated_item_active(database, chihiro, True)
        assert _view(database, pool, "sen_to_chihiro").checked is True


def test_set_local_media_active_rejects_nadeshiko_rows(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    with SceneCollectorDatabase.open(settings) as database:
        stored = database.upsert_media("anonymous-media-001", display_name="작품")
        with pytest.raises(DatabaseError):
            database.set_local_media_active(stored.id, False)


def test_curated_views_do_not_create_media(tmp_path: Path) -> None:
    pool = load_curated_pool()
    settings = _settings(tmp_path)
    with SceneCollectorDatabase.open(settings) as database:
        views = curated_views(database, pool)
        assert len(views) == 97
        assert all(view.checked is False for view in views)
        assert database.list_media() == ()


def test_load_rejects_corrupted_pool(tmp_path: Path) -> None:
    broken = tmp_path / "broken.json"
    broken.write_text('{"items": [{"key": "x"}]}', encoding="utf-8")
    with pytest.raises((CuratedPoolError, KeyError)):
        load_curated_pool(broken)

    payload = json.loads(
        (Path(__file__).parents[1] / "src" / "scene_collector" / "curated_media_pool.json")
        .read_text(encoding="utf-8")
    )
    duplicated = copy.deepcopy(payload)
    duplicated["items"][1]["key"] = duplicated["items"][0]["key"]
    dup_path = tmp_path / "dup.json"
    dup_path.write_text(json.dumps(duplicated, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(CuratedPoolError, match="중복"):
        load_curated_pool(dup_path)
