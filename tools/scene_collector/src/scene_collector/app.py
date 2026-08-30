"""NiceGUI(native mode) 실제 사용자 화면.

흐름: 한국어 의미 → 저장된 표현 조회(AI 미호출) → 없으면 AI로 표현 생성·저장
→ 표현 전부 표시 → 사용자가 의미→표현 관계 하나 선택 → 그 표현만 검색
→ 장면 하나 선택 시 단일 플레이어에 그 영상만 로딩 → 요청 시 문맥·번역
→ 판정·번역·메모가 발생한 장면만 저장 → 채택 장면 내보내기.

검색 결과는 현재 세션에서만 사용하고 저장·캐시하지 않는다. 화면 상태는
클라이언트(창)별로 관리하고, DB·네트워크 호출은 단일 작업 thread에서만 한다.
설정 파일은 실행 디렉터리의 settings.toml이며 SCENE_COLLECTOR_SETTINGS_FILE
환경변수로만 다른 경로를 지정할 수 있다.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import TypeVar

from nicegui import ui

from scene_collector import curated, ui_controller
from scene_collector.config import AppSettings, ConfigurationError, load_settings
from scene_collector.database import (
    DatabaseError,
    SceneCollectorDatabase,
    StoredMeaningExpression,
    StoredMedia,
)
from scene_collector.export import export_accepted_scenes
from scene_collector.media import media_display_name, search_media, store_media
from scene_collector.nadeshiko import create_nadeshiko_client
from scene_collector.search import NoActiveMediaError, SelectedExpressionScenes

_T = TypeVar("_T")

_USER_ERRORS = (ConfigurationError, NoActiveMediaError, DatabaseError, ValueError, RuntimeError)
NO_ACTIVE_MEDIA_GUIDE = (
    "검색에 사용할 활성 작품이 없습니다. 선호 작품 탭에서 작품을 추가하거나 활성화하세요."
)
LOCAL_SUBTITLE_NOTICE = (
    "로컬 자막 결과는 그 표현이 자막 작품에 있는지 확인하는 참고 표시입니다. "
    "영상 재생·판정 저장·내보내기는 Nadeshiko 장면만 지원합니다."
)


class AppContext:
    """설정·DB·Nadeshiko 클라이언트와 단일 작업 thread를 관리한다."""

    def __init__(self) -> None:
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="scene-work")
        self.settings: AppSettings | None = None
        self.database: SceneCollectorDatabase | None = None
        self._nadeshiko = None
        self.startup_error: str | None = None

    async def call(self, fn: Callable[[], _T]) -> _T:
        """모든 DB·네트워크 작업을 단일 작업 thread에서 실행한다."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self.executor, fn)

    def _startup_sync(self) -> None:
        settings_file = os.environ.get("SCENE_COLLECTOR_SETTINGS_FILE", "settings.toml")
        self.settings = load_settings(settings_file)
        self.database = SceneCollectorDatabase.open(self.settings)

    async def ensure_started(self) -> bool:
        if self.database is not None:
            return True
        if self.startup_error is not None:
            return False
        try:
            await self.call(self._startup_sync)
        except (ConfigurationError, DatabaseError) as error:
            self.startup_error = str(error)
            return False
        return True

    def nadeshiko(self):
        """작업 thread 안에서만 호출한다. 키가 없으면 ConfigurationError."""
        if self._nadeshiko is None:
            assert self.settings is not None
            self._nadeshiko = create_nadeshiko_client(self.settings)
        return self._nadeshiko


context = AppContext()


def _notify_error(error: Exception) -> None:
    ui.notify(str(error), type="warning", close_button="닫기", multi_line=True)


@ui.page("/")
async def main_page() -> None:
    started = await context.ensure_started()
    if not started:
        ui.label("설정을 읽지 못해 프로그램을 시작할 수 없습니다.").style("font-size: 1.1rem")
        ui.label(context.startup_error or "알 수 없는 오류").style("color: #b00020")
        return

    assert context.settings is not None and context.database is not None
    settings = context.settings
    database = context.database

    # 화면 상태는 이 클라이언트(창)에만 속한다. 지난 검색을 자동 복원하지 않는다.
    screen: ui_controller.ExpressionScreen | None = None
    relation: StoredMeaningExpression | None = None
    found: SelectedExpressionScenes | None = None
    rows: tuple[ui_controller.SceneRow, ...] = ()
    saved_scenes: tuple = ()
    selected_index: int | None = None
    player = None
    media_rows: tuple[StoredMedia, ...] = ()
    media_names: dict[str, str] = {}
    curated_pool: tuple[curated.CuratedItem, ...] = ()
    curated_view_rows: tuple[curated.CuratedItemView, ...] = ()
    curated_load_error: str | None = None

    async def refresh_media_state() -> None:
        nonlocal media_rows, media_names
        media_rows = await context.call(database.list_media)
        media_names = {
            media.nadeshiko_media_id: (media.display_name or media.nadeshiko_media_id)
            for media in media_rows
            if media.nadeshiko_media_id is not None
        }

    await refresh_media_state()
    try:
        curated_pool = await context.call(curated.load_curated_pool)
        curated_view_rows = await context.call(
            lambda: curated.curated_views(database, curated_pool)
        )
    except curated.CuratedPoolError as error:
        curated_load_error = str(error)

    with ui.header().classes("items-center"):
        ui.label("까막눈 애니 표현 장면 수집기").style("font-size: 1.15rem; font-weight: 600")

    with ui.tabs() as tabs:
        search_tab = ui.tab("표현 찾기")
        expressions_tab = ui.tab("일본어 표현 선택")
        scenes_tab = ui.tab("장면 검수")
        media_tab = ui.tab("선호 작품")
        settings_tab = ui.tab("설정")

    with ui.tab_panels(tabs, value=search_tab).classes("w-full"):
        with ui.tab_panel(search_tab):
            ui.label(
                "한국어 의미를 입력하면 먼저 저장된 일본어 표현을 찾습니다. "
                "저장된 표현이 있으면 AI를 호출하지 않습니다."
            )
            meaning_input = ui.input(
                "한국어 의미", placeholder="예: 괜찮아요"
            ).classes("w-96")
            search_status = ui.label("")
            with ui.row():
                lookup_button = ui.button("표현 찾기", on_click=lambda: do_lookup())
                generate_button = ui.button(
                    "AI로 표현 생성", on_click=lambda: do_generate()
                )

        with ui.tab_panel(expressions_tab):
            with ui.row().classes("items-center"):
                ui.button("표현 더 찾기", on_click=lambda: do_generate())
                ui.label(
                    "이미 저장된 표현을 AI에 전달해 중복되지 않는 표현만 추가합니다."
                ).style("color: #666; font-size: 0.85rem")
            expressions_box = ui.column().classes("w-full")

        with ui.tab_panel(scenes_tab):
            scene_header = ui.label("").style("font-weight: 600")
            with ui.row().classes("items-center"):
                export_button = ui.button(
                    "채택 장면 내보내기", on_click=lambda: do_export()
                )
                export_status = ui.label("")
            ui.separator()
            saved_box = ui.column().classes("w-full")
            scene_list_box = ui.column().classes("w-full")
            player_box = ui.column().classes("w-full")
            detail_box = ui.column().classes("w-full")
            local_box = ui.column().classes("w-full")

        with ui.tab_panel(media_tab):
            ui.label(
                "추천 후보 목록 — 체크한 작품만 기본 검색 대상이 됩니다. "
                "프랜차이즈 하나를 체크하면 연결된 entry가 함께 활성화됩니다."
            ).style("font-weight: 600")
            curated_filter = ui.toggle(
                ["전체", "A군", "B군"], value="전체", on_change=lambda: render_curated()
            )
            curated_box = ui.column().classes("w-full")
            ui.separator()
            ui.label("작품 직접 검색 (curated 목록에 없는 작품 추가)")
            with ui.row().classes("items-end"):
                media_query_input = ui.input("작품명 검색", placeholder="예: Chainsaw Man")
                ui.button("Nadeshiko 작품 검색", on_click=lambda: do_media_search())
            media_results_box = ui.column().classes("w-full")
            ui.separator()
            ui.label("저장된 작품")
            media_list_box = ui.column().classes("w-full")

        with ui.tab_panel(settings_tab):
            settings_box = ui.column().classes("w-full")

    # ------------------------------------------------------------------
    # 표현 찾기 / 표현 선택
    # ------------------------------------------------------------------

    async def do_lookup() -> None:
        """저장된 표현만 조회한다. AI·Nadeshiko 호출 없음."""
        nonlocal screen
        text = (meaning_input.value or "").strip()
        if not text:
            ui.notify("한국어 의미를 입력하세요.", type="warning")
            return
        lookup_button.disable()
        try:
            screen = await context.call(
                lambda: ui_controller.lookup_expressions(database, text)
            )
        except _USER_ERRORS as error:
            _notify_error(error)
            return
        finally:
            lookup_button.enable()
        if screen.has_expressions:
            search_status.set_text(
                f"저장된 표현 {len(screen.relations)}개 — AI를 호출하지 않았습니다."
            )
            render_expressions()
            tabs.set_value(expressions_tab)
        else:
            search_status.set_text(
                "저장된 표현이 없습니다. [AI로 표현 생성]으로 표현 자산을 만드세요."
            )
            render_expressions()

    async def do_generate() -> None:
        """AI로 표현을 만들어 자산으로 저장한다. Nadeshiko는 호출하지 않는다."""
        nonlocal screen
        text = (meaning_input.value or "").strip()
        if not text:
            ui.notify("한국어 의미를 입력하세요.", type="warning")
            return
        generate_button.disable()
        search_status.set_text("AI로 표현을 만드는 중...")
        try:
            screen, added = await context.call(
                lambda: ui_controller.generate_more_expressions(settings, database, text)
            )
        except _USER_ERRORS as error:
            search_status.set_text(f"표현 생성 실패: {error}")
            _notify_error(error)
            return
        finally:
            generate_button.enable()
        search_status.set_text(
            f"새 표현 {len(added)}개 저장 · 저장된 표현 {len(screen.relations)}개"
        )
        render_expressions()
        if screen.has_expressions:
            tabs.set_value(expressions_tab)

    def render_expressions() -> None:
        expressions_box.clear()
        with expressions_box:
            if screen is None or not screen.has_expressions:
                ui.label(
                    "표시할 표현이 없습니다. 표현 찾기 탭에서 한국어 의미를 먼저 조회하세요."
                )
                return
            ui.label(f"한국어 의미: {screen.korean_meaning}").style("font-weight: 600")
            for item in screen.relations:
                with ui.card().classes("w-full"):
                    ui.label(f"{item.japanese} ({item.reading})").style("font-size: 1.1rem")
                    ui.label(f"이 의미에서의 뜻: {item.meaning_ko}")
                    ui.label(f"말투: {item.register_text}")
                    if relation is not None and relation.id == item.id:
                        ui.label("선택됨").style("color: #2e7d32; font-weight: 600")

                    async def do_select(chosen: StoredMeaningExpression = item) -> None:
                        await select_relation(chosen)

                    ui.button("이 표현으로 장면 찾기", on_click=do_select)

    # ------------------------------------------------------------------
    # 장면 검수
    # ------------------------------------------------------------------

    async def select_relation(chosen: StoredMeaningExpression) -> None:
        """선택한 표현 하나만 검색한다. 검색 결과는 저장하지 않는다."""
        nonlocal relation, found, rows, selected_index, saved_scenes
        relation = chosen
        selected_index = None
        saved_scenes = await context.call(lambda: database.list_work_scenes(chosen.id))
        render_expressions()
        render_scene_header()
        render_saved_scenes()
        scene_list_box.clear()
        with scene_list_box:
            ui.label("장면을 검색하는 중...")
        tabs.set_value(scenes_tab)
        try:
            found = await context.call(
                lambda: ui_controller.search_relation(
                    settings, database, chosen, nadeshiko_client=context.nadeshiko()
                )
            )
            rows = await context.call(
                lambda: ui_controller.scene_rows(database, found, media_names)
            )
        except NoActiveMediaError:
            found = None
            rows = ()
            render_scene_list(message=NO_ACTIVE_MEDIA_GUIDE)
            ui.notify(NO_ACTIVE_MEDIA_GUIDE, type="warning", multi_line=True)
            return
        except _USER_ERRORS as error:
            found = None
            rows = ()
            render_scene_list(message=f"검색 실패: {error}")
            _notify_error(error)
            return
        render_scene_list()
        render_local_scenes()
        render_detail()

    def render_scene_header() -> None:
        if relation is None or screen is None:
            scene_header.set_text("")
            return
        scene_header.set_text(
            f"작업 맥락: {screen.korean_meaning} → {relation.japanese} ({relation.reading})"
        )

    def render_saved_scenes() -> None:
        saved_box.clear()
        if relation is None or not saved_scenes:
            return
        with saved_box:
            ui.label(f"이미 작업한 장면 {len(saved_scenes)}개").style("font-weight: 600")
            for scene in saved_scenes:
                ui.label(ui_controller.work_scene_line(scene)).style("font-size: 0.9rem")
            ui.separator()

    def render_scene_list(message: str | None = None) -> None:
        scene_list_box.clear()
        with scene_list_box:
            if message is not None:
                ui.label(message)
                return
            if relation is None:
                ui.label("일본어 표현 선택 탭에서 표현을 먼저 고르세요.")
                return
            if not rows:
                ui.label(
                    "이 표현으로 찾은 Nadeshiko 장면이 없습니다. "
                    "다른 표현을 고르거나 활성 작품을 늘려 보세요."
                )
                return
            ui.label(f"Nadeshiko 장면 {len(rows)}개 — 하나를 고르면 영상이 로딩됩니다.").style(
                "font-weight: 600"
            )
            for index, row in enumerate(rows):
                with ui.row().classes("items-center w-full"):
                    decision = row.decision
                    if decision:
                        ui.label(f"[{decision}]").style("color: #2e7d32")
                    ui.label(ui_controller.scene_line(row))

                    async def do_pick(chosen: int = index) -> None:
                        await pick_scene(chosen)

                    ui.button("이 장면 보기", on_click=do_pick)

    async def pick_scene(index: int) -> None:
        """선택한 장면 하나만 단일 플레이어에 로딩한다."""
        nonlocal selected_index, player
        if index < 0 or index >= len(rows):
            return
        selected_index = index
        source = rows[index].segment.urls.video_url or ""
        if player is None:
            with player_box:
                player = ui.video(source, controls=True).style(
                    "width: 640px; max-height: 360px"
                )
        else:
            player.set_source(source)
        render_detail()
        render_scene_list()

    def selected_row() -> ui_controller.SceneRow | None:
        if selected_index is None or selected_index >= len(rows):
            return None
        return rows[selected_index]

    def render_detail() -> None:
        detail_box.clear()
        row = selected_row()
        with detail_box:
            if row is None:
                ui.label("장면 목록에서 장면 하나를 고르세요.")
                return
            ui.label(row.segment.text_ja.content).style("font-size: 1.05rem")
            saved = row.work_scene
            if saved is not None and saved.natural_translation:
                ui.label(f"직접적인 뜻: {saved.direct_meaning}")
                ui.label(f"자연스러운 번역: {saved.natural_translation}")
                ui.label(f"장면에서의 쓰임: {saved.scene_usage}")
            else:
                ui.label("아직 번역이 없습니다. 필요할 때만 아래 버튼으로 실행하세요.").style(
                    "color: #666"
                )
            ui.label(f"판정: {saved.decision if saved and saved.decision else '없음'}").style(
                "font-weight: 600"
            )

            with ui.row().classes("items-center"):
                translate_button = ui.button(
                    "문맥 조회 + 한국어 번역", on_click=lambda: do_translate()
                )
                for value in ui_controller.REVIEW_DECISIONS:

                    async def do_decide(decision: str = value) -> None:
                        await save_decision(decision)

                    ui.button(value, on_click=do_decide)

            notes_input = ui.input(
                "메모", value=(saved.notes if saved and saved.notes else "")
            ).classes("w-96")

            async def do_save_notes() -> None:
                await save_notes(notes_input.value)

            ui.button("메모 저장", on_click=do_save_notes)

            async def do_translate() -> None:
                row_now = selected_row()
                if row_now is None or relation is None:
                    return
                translate_button.disable()
                ui.notify("문맥 조회와 번역을 실행합니다.")
                try:
                    await context.call(
                        lambda: ui_controller.translate_scene(
                            settings,
                            database,
                            relation,
                            row_now.segment,
                            row_now.media_display_name,
                            nadeshiko_client=context.nadeshiko(),
                        )
                    )
                except _USER_ERRORS as error:
                    _notify_error(error)
                    return
                finally:
                    translate_button.enable()
                await refresh_rows()

    async def save_decision(decision: str) -> None:
        row_now = selected_row()
        if row_now is None or relation is None:
            return
        try:
            await context.call(
                lambda: ui_controller.save_decision(
                    database, relation, row_now.segment, row_now.media_display_name, decision
                )
            )
        except _USER_ERRORS as error:
            _notify_error(error)
            return
        ui.notify(f"판정을 저장했습니다: {decision}")
        await refresh_rows()

    async def save_notes(value: str | None) -> None:
        row_now = selected_row()
        if row_now is None or relation is None:
            return
        try:
            await context.call(
                lambda: ui_controller.save_notes(
                    database, relation, row_now.segment, row_now.media_display_name, value
                )
            )
        except _USER_ERRORS as error:
            _notify_error(error)
            return
        ui.notify("메모를 저장했습니다.")
        await refresh_rows()

    async def refresh_rows() -> None:
        """저장 후 목록의 작업 상태만 다시 읽는다. 재검색은 하지 않는다."""
        nonlocal rows, saved_scenes
        if found is None or relation is None:
            return
        rows = await context.call(
            lambda: ui_controller.scene_rows(database, found, media_names)
        )
        saved_scenes = await context.call(lambda: database.list_work_scenes(relation.id))
        render_saved_scenes()
        render_scene_list()
        render_detail()

    def render_local_scenes() -> None:
        local_box.clear()
        if found is None or not found.local_segments:
            return
        with local_box:
            ui.separator()
            ui.label(f"로컬 자막 참고 결과 {len(found.local_segments)}개").style(
                "font-weight: 600"
            )
            ui.label(LOCAL_SUBTITLE_NOTICE).style("color: #666; font-size: 0.85rem")
            for scene in found.local_segments:
                ui.label(ui_controller.local_scene_line(scene))

    async def do_export() -> None:
        export_button.disable()
        export_status.set_text("내보내는 중...")
        try:
            result = await context.call(
                lambda: export_accepted_scenes(
                    settings, database, nadeshiko_client=context.nadeshiko()
                )
            )
        except _USER_ERRORS as error:
            export_status.set_text(f"내보내기 실패: {error}")
            _notify_error(error)
            return
        finally:
            export_button.enable()
        if not result.has_scenes:
            export_status.set_text(
                "채택 장면이 없습니다. 장면 검수에서 먼저 채택 판정을 저장하세요."
            )
            return
        export_status.set_text(
            f"채택 관계 {result.relation_count}개 · 고유 영상 {result.unique_video_count}개 · "
            f"새로 받음 {result.downloaded_count}개 · 기존 재사용 {result.reused_count}개 · "
            f"실패 {result.failed_count}개 — JSON: {result.json_path}"
        )
        if result.failures:
            first_id, first_error = result.failures[0]
            ui.notify(
                f"일부 영상 다운로드에 실패했습니다 ({first_id}: {first_error})",
                type="warning",
                multi_line=True,
            )
        else:
            ui.notify("채택 장면 내보내기를 완료했습니다.")

    # ------------------------------------------------------------------
    # 선호 작품 · 설정 (작업 10/10.5에서 검증된 화면 유지)
    # ------------------------------------------------------------------

    async def refresh_curated() -> None:
        nonlocal curated_view_rows
        if curated_load_error is not None:
            return
        curated_view_rows = await context.call(
            lambda: curated.curated_views(database, curated_pool)
        )
        render_curated()

    async def do_toggle_curated(item: curated.CuratedItem, active: bool) -> None:
        try:
            await context.call(lambda: curated.set_curated_item_active(database, item, active))
        except _USER_ERRORS as error:
            _notify_error(error)
            await refresh_curated()
            return
        ui.notify(f"{item.korean_title}: {'활성화' if active else '비활성화'}했습니다.")
        await refresh_media_state()
        await refresh_curated()
        render_media_list()

    def render_curated() -> None:
        curated_box.clear()
        with curated_box:
            if curated_load_error is not None:
                ui.label(f"추천 후보 목록을 읽지 못했습니다: {curated_load_error}").style(
                    "color: #b00020"
                )
                return
            selected = curated_filter.value
            visible = [
                view
                for view in curated_view_rows
                if selected == "전체"
                or (selected == "A군" and view.item.group == "A")
                or (selected == "B군" and view.item.group == "B")
            ]
            active_count = sum(1 for view in curated_view_rows if view.checked)
            ui.label(
                f"{len(visible)}개 표시 · 전체 {len(curated_view_rows)}개 중 체크 {active_count}개"
            ).style("color: #666")
            for view in visible:
                item = view.item
                with ui.row().classes("items-center w-full"):
                    checkbox = ui.checkbox(
                        value=view.checked,
                        on_change=lambda e, it=item: do_toggle_curated(it, e.value),
                    )
                    if not view.checkable:
                        checkbox.disable()
                    ui.label(
                        f"[{item.group}{item.tier} · 근거 {item.popularity_evidence_grade}] "
                        f"{item.korean_title}"
                    )
                    ui.label(view.status_label).style("color: #666; font-size: 0.85rem")

    async def do_media_search() -> None:
        query = (media_query_input.value or "").strip()
        if not query:
            ui.notify("찾을 작품명을 입력하세요.", type="warning")
            return
        try:
            summaries = await context.call(lambda: search_media(context.nadeshiko(), query))
        except _USER_ERRORS as error:
            _notify_error(error)
            return
        media_results_box.clear()
        with media_results_box:
            if not summaries:
                ui.label("검색 결과가 없습니다.")
                return
            for summary in summaries:
                with ui.row().classes("items-center"):
                    ui.label(media_display_name(summary) or summary.public_id)

                    async def do_store(chosen=summary) -> None:
                        try:
                            await context.call(lambda: store_media(database, chosen))
                        except _USER_ERRORS as error:
                            _notify_error(error)
                            return
                        ui.notify("작품을 저장했습니다.")
                        await refresh_media_state()
                        render_media_list()

                    ui.button("저장", on_click=do_store)

    def render_media_list() -> None:
        media_list_box.clear()
        with media_list_box:
            if not media_rows:
                ui.label("저장된 작품이 없습니다. 위에서 Nadeshiko 작품을 검색해 저장하세요.")
                return
            for media in media_rows:
                with ui.card().classes("w-full"):
                    source_label = "Nadeshiko" if media.source == "nadeshiko" else "로컬 자막"
                    ui.label(
                        f"{media.display_name or '(표시명 없음)'} · {source_label}"
                    ).style("font-weight: 600")
                    if media.source != "nadeshiko":
                        ui.label(
                            "로컬 자막 작품입니다. Nadeshiko ID가 없는 것이 정상이며 "
                            f"현재 {'활성' if media.is_active else '비활성'} 상태입니다."
                        ).style("color: #666")
                        continue

                    nadeshiko_id = media.nadeshiko_media_id
                    assert nadeshiko_id is not None
                    with ui.row().classes("items-center"):
                        preference_input = ui.number(
                            "선호도", value=media.preference, min=0, max=10, precision=0
                        ).classes("w-24")
                        group_input = ui.input(
                            "콘텐츠 묶음", value=media.content_group or ""
                        ).classes("w-40")

                        async def do_save_media(
                            media_id: str = nadeshiko_id,
                            preference_field=preference_input,
                            group_field=group_input,
                        ) -> None:
                            preference = (
                                int(preference_field.value)
                                if preference_field.value is not None
                                else None
                            )
                            group = group_field.value or None
                            try:
                                await context.call(
                                    lambda: database.set_media_preference(media_id, preference)
                                )
                                await context.call(
                                    lambda: database.set_media_content_group(media_id, group)
                                )
                            except _USER_ERRORS as error:
                                _notify_error(error)
                                return
                            ui.notify("작품 상태를 저장했습니다.")
                            await refresh_media_state()

                        ui.button("저장", on_click=do_save_media)

                        async def do_toggle_active(
                            event,
                            media_id: str = nadeshiko_id,
                        ) -> None:
                            try:
                                await context.call(
                                    lambda: database.set_media_active(media_id, event.value)
                                )
                            except _USER_ERRORS as error:
                                _notify_error(error)
                                return
                            await refresh_media_state()

                        ui.switch(
                            "기본 검색에 포함",
                            value=media.is_active,
                            on_change=do_toggle_active,
                        )

    def render_settings() -> None:
        settings_box.clear()
        summary = ui_controller.settings_summary(settings)
        with settings_box:
            ui.label("현재 설정").style("font-weight: 600")
            ui.label(f"작업 데이터 위치: {summary.work_data_dir}")
            ui.label(f"데이터베이스 파일: {summary.database_file}")
            ui.label(f"AI 서비스 / 모델: {summary.ai_service} / {summary.ai_model}")
            ui.label(
                f"표현 생성 상한: {summary.expression_generation_limit} · "
                f"장면 검색 조회량: {summary.nadeshiko_take}"
            )
            ui.label(
                "Nadeshiko API 키: 설정됨 (값은 표시하지 않습니다)"
                if summary.nadeshiko_key_set
                else "Nadeshiko API 키: 없음 — .env 또는 환경변수에 NADESHIKO_API_KEY가 필요합니다"
            )
            ui.label("데이터베이스 연결: 정상 (이 화면이 열렸다면 DB가 열린 상태입니다)")
            connection_label = ui.label("Nadeshiko 연결 상태: 아직 확인하지 않음")

            async def do_check_connection() -> None:
                try:
                    await context.call(lambda: context.nadeshiko().get_me())
                except _USER_ERRORS as error:
                    connection_label.set_text("Nadeshiko 연결 상태: 실패")
                    _notify_error(error)
                    return
                connection_label.set_text("Nadeshiko 연결 상태: 연결 성공 (get_me 확인)")

            ui.button("Nadeshiko 연결 확인 (실제 API 1회 호출)", on_click=do_check_connection)

    render_expressions()
    render_scene_header()
    render_scene_list()
    render_detail()
    render_curated()
    render_media_list()
    render_settings()


def main() -> None:
    ui.run(
        native=True,
        window_size=(1280, 860),
        title="까막눈 장면 수집기",
        reload=False,
        show_welcome_message=False,
    )


if __name__ == "__main__":
    main()
