import copy
import json
import re
from collections import Counter
from pathlib import Path

import pytest
from nadeshiko.models import MediaSummary, SearchFilters, SearchQuery, SearchResponse

from scene_collector.config import AISettings, AppSettings, SearchSettings, StorageSettings
from scene_collector.curated import (
    CuratedPoolError,
    curated_views,
    index_source_unit_subtitles,
    load_curated_pool,
    set_curated_item_active,
    unit_local_media_title,
)
from scene_collector.database import (
    DatabaseError,
    SceneCollectorDatabase,
    StoredMeaningExpression,
)
from scene_collector.media import store_media
from scene_collector.search import NoActiveMediaError, search_selected_expression
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
        search=SearchSettings(expression_generation_limit=3),
    )


def _relation(
    database: SceneCollectorDatabase,
    korean_meaning: str,
    japanese: str,
) -> StoredMeaningExpression:
    """검색에 사용할 의미→표현 관계를 AI 없이 직접 저장한다."""
    meaning = database.upsert_meaning(korean_meaning)
    return database.add_meaning_expression(
        meaning.id,
        japanese=japanese,
        reading="だいじょうぶですか",
        meaning_ko="괜찮으세요?",
        register_text="존댓말",
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


def test_checked_items_drive_selected_expression_media_filter(tmp_path: Path) -> None:
    pool = load_curated_pool()
    chainsaw = _item(pool, "chainsaw_man")
    settings = _settings(tmp_path)
    client = RecordingNadeshiko(_empty_response())

    with SceneCollectorDatabase.open(settings) as database:
        set_curated_item_active(database, chainsaw, True)
        relation = _relation(database, "괜찮냐고 묻는 말", "大丈夫ですか")

        search_selected_expression(
            settings, relation, nadeshiko_client=client, database=database
        )
        assert client.calls
        for _, _, included in client.calls:
            assert included == tuple(sorted(chainsaw.nadeshiko_media_ids))

        # 해제 후에는 활성 작품이 없어 기존 오류 동작으로 돌아간다
        set_curated_item_active(database, chainsaw, False)
        client.calls.clear()
        with pytest.raises(NoActiveMediaError):
            search_selected_expression(
                settings, relation, nadeshiko_client=client, database=database
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


def test_partial_items_say_only_the_linked_titles_are_searchable(tmp_path: Path) -> None:
    """부분 지원 작품은 전체가 아니라 연결된 것만 검색된다는 사실을 알린다."""
    pool = load_curated_pool()
    with SceneCollectorDatabase.open(_settings(tmp_path)) as database:
        views = {view.item.key: view for view in curated_views(database, pool)}

        # source unit이 있는 항목은 unit 기준의 정직한 커버리지 요약을 쓴다.
        kimetsu = views["kimetsu_no_yaiba"]
        assert kimetsu.item.source_status == "nadeshiko_partial"
        assert kimetsu.status_label == "검색 가능 1개 · 자막 준비 필요 5개 · 검색 불가 1개"

        # 전체 지원 작품에는 개수를 붙이지 않는다.
        assert views["chainsaw_man"].status_label == "장면 검색 바로 가능"

        for view in views.values():
            if view.item.source_units:
                assert "검색 가능" in view.status_label
            elif view.item.source_status == "nadeshiko_partial":
                assert "일부" in view.status_label
                assert f"연결 {len(view.item.nadeshiko_media_ids)}개" in view.status_label


def test_status_labels_never_leak_internal_data(tmp_path: Path) -> None:
    """공개 ID와 내부 note는 사용자 화면 문자열에 들어가지 않는다."""
    pool = load_curated_pool()
    with SceneCollectorDatabase.open(_settings(tmp_path)) as database:
        for view in curated_views(database, pool):
            for media_id in view.item.nadeshiko_media_ids:
                assert media_id not in view.status_label
            if view.item.note:
                assert view.item.note not in view.status_label
            # 등급·tier 같은 내부 분류도 상태 문구에 없다.
            assert "Tier" not in view.status_label
            assert "근거" not in view.status_label


# ----------------------------------------------------------------------
# source unit (UAT FIX 3-A)
# ----------------------------------------------------------------------

UNIT_SRT = """1
00:00:01,000 --> 00:00:02,500
（ミサ）大丈夫ですか？

2
00:00:05,000 --> 00:00:06,000
ありがとう
"""


def _unit_srt_dir(tmp_path: Path, name: str, episodes: tuple[int, ...]) -> Path:
    directory = tmp_path / name
    directory.mkdir()
    for episode in episodes:
        (directory / f"자막 - {episode:02d}.srt").write_text(UNIT_SRT, encoding="utf-8")
    return directory


def _unit(item, key):
    matches = [unit for unit in item.source_units if unit.key == key]
    assert len(matches) == 1, key
    return matches[0]


def test_kimetsu_source_units_match_verified_coverage() -> None:
    pool = load_curated_pool()
    kimetsu = _item(pool, "kimetsu_no_yaiba")

    assert len(kimetsu.source_units) == 7
    kinds = Counter(unit.kind for unit in kimetsu.source_units)
    assert kinds == Counter({"jimaku": 5, "nadeshiko": 1, "unavailable": 1})

    s1 = _unit(kimetsu, "s1_tv")
    assert s1.nadeshiko_media_id == kimetsu.nadeshiko_media_ids[0]
    assert s1.media_type == "tv"

    jimaku_ids = sorted(
        unit.jimaku_entry_id for unit in kimetsu.source_units if unit.kind == "jimaku"
    )
    assert jimaku_ids == sorted(kimetsu.jimaku_entry_ids)

    unavailable = _unit(kimetsu, "mugen_jou_movie_1")
    assert unavailable.kind == "unavailable"

    labels = [unit.label for unit in kimetsu.source_units]
    assert len(set(labels)) == 7


def test_franchise_check_toggles_nadeshiko_and_indexed_units(tmp_path: Path) -> None:
    pool = load_curated_pool()
    kimetsu = _item(pool, "kimetsu_no_yaiba")
    yuukaku = _unit(kimetsu, "yuukaku")
    settings = _settings(tmp_path)
    directory = _unit_srt_dir(tmp_path, "yuukaku-subs", (1, 2))

    with SceneCollectorDatabase.open(settings) as database:
        unrelated = database.register_local_media("무관한 로컬 작품")
        assert unrelated.is_active is True

        # 체크가 꺼진 상태에서 색인: 색인은 되지만 검색 대상에는 들어가지 않는다.
        media, report = index_source_unit_subtitles(
            database, kimetsu, yuukaku, directory
        )
        assert media.display_name == unit_local_media_title(kimetsu, yuukaku)
        assert media.display_name == "귀멸의 칼날 · 유곽편"
        assert media.is_active is False
        assert report.file_count == 2
        assert report.episodes == (1, 2)
        assert report.cue_count == 4

        view = _view(database, pool, "kimetsu_no_yaiba")
        assert view.checked is False
        statuses = {u.unit.key: u.status for u in view.unit_views}
        assert statuses["s1_tv"] == "nadeshiko_ready"
        assert statuses["yuukaku"] == "indexed"
        assert statuses["katanakaji"] == "needs_subtitles"
        assert statuses["mugen_jou_movie_1"] == "unavailable"

        # 체크 ON: Nadeshiko + 색인된 unit 로컬 media가 함께 활성.
        set_curated_item_active(database, kimetsu, True)
        assert database.get_media(kimetsu.nadeshiko_media_ids[0]).is_active is True
        assert database.find_local_media("귀멸의 칼날 · 유곽편").is_active is True
        assert _view(database, pool, "kimetsu_no_yaiba").checked is True

        # 체크 OFF: 둘 다 비활성. 무관한 로컬 media는 영향 없음.
        set_curated_item_active(database, kimetsu, False)
        assert database.get_media(kimetsu.nadeshiko_media_ids[0]).is_active is False
        assert database.find_local_media("귀멸의 칼날 · 유곽편").is_active is False
        assert database.find_local_media("무관한 로컬 작품").is_active is True
        assert _view(database, pool, "kimetsu_no_yaiba").checked is False

        set_curated_item_active(database, kimetsu, True)

    # 재시작 후 체크 상태와 unit 상태가 복원된다.
    with SceneCollectorDatabase.open(settings) as reopened:
        view = _view(reopened, pool, "kimetsu_no_yaiba")
        assert view.checked is True
        statuses = {u.unit.key: u.status for u in view.unit_views}
        assert statuses["yuukaku"] == "indexed"


def test_index_source_unit_respects_current_check_state_and_scope(tmp_path: Path) -> None:
    pool = load_curated_pool()
    kimetsu = _item(pool, "kimetsu_no_yaiba")
    settings = _settings(tmp_path)

    with SceneCollectorDatabase.open(settings) as database:
        set_curated_item_active(database, kimetsu, True)

        # 체크가 켜진 상태에서 색인하면 새 unit도 즉시 검색 대상이 된다.
        directory = _unit_srt_dir(tmp_path, "katanakaji-subs", (1,))
        media, _ = index_source_unit_subtitles(
            database, kimetsu, _unit(kimetsu, "katanakaji"), directory
        )
        assert media.is_active is True

        # nadeshiko/unavailable unit은 색인 대상이 아니다.
        with pytest.raises(CuratedPoolError, match="색인 대상이 아닙니다"):
            index_source_unit_subtitles(
                database, kimetsu, _unit(kimetsu, "s1_tv"), directory
            )
        with pytest.raises(CuratedPoolError, match="색인 대상이 아닙니다"):
            index_source_unit_subtitles(
                database, kimetsu, _unit(kimetsu, "mugen_jou_movie_1"), directory
            )

        # 이 색인은 귀멸 항목에만 연결된다: 다른 jimaku 항목은 그대로 색인 필요 상태다.
        chihiro_view = _view(database, pool, "sen_to_chihiro")
        assert chihiro_view.checkable is False


def test_search_uses_indexed_units_only_while_checked(tmp_path: Path) -> None:
    pool = load_curated_pool()
    kimetsu = _item(pool, "kimetsu_no_yaiba")
    settings = _settings(tmp_path)
    client = RecordingNadeshiko(_empty_response())
    directory = _unit_srt_dir(tmp_path, "yuukaku-subs", (3,))

    with SceneCollectorDatabase.open(settings) as database:
        set_curated_item_active(database, kimetsu, True)
        index_source_unit_subtitles(database, kimetsu, _unit(kimetsu, "yuukaku"), directory)
        relation = _relation(database, "괜찮냐고 묻는 말", "大丈夫ですか")

        found = search_selected_expression(
            settings, relation, nadeshiko_client=client, database=database
        )
        for _, _, included in client.calls:
            assert included == tuple(sorted(kimetsu.nadeshiko_media_ids))
        assert [scene.media_display_name for scene in found.local_segments] == [
            "귀멸의 칼날 · 유곽편"
        ]
        assert [scene.episode for scene in found.local_segments] == [3]

        # 체크 해제 한 번으로 Nadeshiko와 로컬 unit이 모두 검색에서 빠진다.
        set_curated_item_active(database, kimetsu, False)
        client.calls.clear()
        with pytest.raises(NoActiveMediaError):
            search_selected_expression(
                settings, relation, nadeshiko_client=client, database=database
            )
        assert client.calls == []


def test_pool_rejects_inconsistent_source_units(tmp_path: Path) -> None:
    pool_path = (
        Path(__file__).parent.parent / "src" / "scene_collector" / "curated_media_pool.json"
    )
    payload = json.loads(pool_path.read_text(encoding="utf-8"))

    broken_kind = copy.deepcopy(payload)
    next(
        item for item in broken_kind["items"] if item["key"] == "kimetsu_no_yaiba"
    )["source_units"][0]["kind"] = "unknown"
    broken_path = tmp_path / "broken_kind.json"
    broken_path.write_text(json.dumps(broken_kind, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(CuratedPoolError, match="unit kind"):
        load_curated_pool(broken_path)

    missing_unit = copy.deepcopy(payload)
    target = next(
        item for item in missing_unit["items"] if item["key"] == "kimetsu_no_yaiba"
    )
    target["source_units"] = [
        unit for unit in target["source_units"] if unit["key"] != "yuukaku"
    ]
    missing_path = tmp_path / "missing_unit.json"
    missing_path.write_text(json.dumps(missing_unit, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(CuratedPoolError, match="jimaku_entry_ids"):
        load_curated_pool(missing_path)
