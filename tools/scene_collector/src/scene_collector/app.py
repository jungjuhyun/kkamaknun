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
from pathlib import Path
from typing import TypeVar

from nicegui import ui

from scene_collector import curated, ui_controller
from scene_collector.config import (
    AppSettings,
    ConfigurationError,
    load_settings,
    save_search_settings,
)
from scene_collector.database import (
    DatabaseError,
    SceneCollectorDatabase,
    StoredMeaningExpression,
    StoredMedia,
    normalize_korean_meaning,
)
from scene_collector.export import export_accepted_scenes
from scene_collector.media import media_display_name, search_media, store_media
from scene_collector.nadeshiko import create_nadeshiko_client
from scene_collector.search import NoActiveMediaError

_T = TypeVar("_T")

_USER_ERRORS = (ConfigurationError, NoActiveMediaError, DatabaseError, ValueError, RuntimeError)
NO_ACTIVE_MEDIA_GUIDE = (
    "검색에 사용할 활성 작품이 없습니다. 선호 작품 탭에서 작품을 추가하거나 활성화하세요."
)
# 제목 줄과 탭 줄을 쌓은 헤더의 대략적인 높이. Quasar가 실측 높이로 본문 여백을
# 잡기 전 첫 프레임에만 쓰이므로 정확할 필요는 없고, 기본값 50px보다만 크면 된다.
_HEADER_HEIGHT_HINT = 108

# 한국어 IME는 조합을 확정하는 Enter에서도 keydown을 보낸다. 그 이벤트를 client에서
# 버려야 (a) 같은 입력이 두 번 조회되지 않고 (b) 마지막 음절이 빠진 값으로 조회되지
# 않는다. NiceGUI/Vue/Quasar에는 조합 상태를 걸러 주는 기능이 없어 공식 확장점인
# js_handler로 처리한다.
_ENTER_WITHOUT_IME = "(event) => { if (!event.isComposing && event.keyCode !== 229) emit(); }"

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
        self.settings_file: Path | None = None
        self.startup_error: str | None = None

    async def call(self, fn: Callable[[], _T]) -> _T:
        """모든 DB·네트워크 작업을 단일 작업 thread에서 실행한다."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self.executor, fn)

    def _startup_sync(self) -> None:
        settings_file = os.environ.get("SCENE_COLLECTOR_SETTINGS_FILE", "settings.toml")
        self.settings = load_settings(settings_file)
        # 설정을 저장할 때 같은 파일을 쓰려면 실행 위치와 무관한 절대경로가 필요하다.
        self.settings_file = Path(settings_file).expanduser().resolve()
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
    state = ui_controller.SceneWorkState()
    lookup_guard = ui_controller.ActionGuard()
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

    # 제목과 탭을 함께 헤더에 넣어 본문만 스크롤되게 한다. 헤더 안은 가로 배치라
    # 전체 너비 세로 상자를 하나 두고 제목 줄과 탭 줄을 2단으로 쌓는다.
    # 탭 내용(tab_panels)은 본문에 남겨 계속 스크롤되게 한다.
    with ui.header().props(f"height-hint={_HEADER_HEIGHT_HINT}"):
        with ui.column().classes("w-full gap-1"):
            ui.label("까막눈 애니 표현 장면 수집기").style(
                "font-size: 1.15rem; font-weight: 600"
            )
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
                "저장된 표현이 있으면 AI를 호출하지 않고, 없으면 그 자리에서 한 번 만듭니다."
            )
            meaning_input = ui.input(
                "한국어 의미", placeholder="예: 괜찮아요"
            ).classes("w-96")
            search_status = ui.label("")
            lookup_button = ui.button("표현 찾기", on_click=lambda: do_lookup())
            # Enter와 버튼이 같은 do_lookup 하나를 부른다.
            meaning_input.on(
                "keydown.enter", lambda: do_lookup(), js_handler=_ENTER_WITHOUT_IME
            )

        with ui.tab_panel(expressions_tab):
            with ui.row().classes("items-center"):
                more_button = ui.button("표현 더 찾기", on_click=lambda: do_generate())
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
                "추천 작품 목록 — 체크한 작품만 검색에 사용합니다. "
                "작품을 체크하면 현재 지원되는 연결 항목이 함께 검색 대상이 됩니다."
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
            ui.separator()
            ui.label("바꿀 수 있는 값").style("font-weight: 600")
            with ui.row().classes("items-end"):
                generation_limit_input = ui.number(
                    "표현 생성 상한",
                    value=settings.search.expression_generation_limit,
                    min=1,
                    max=20,
                    precision=0,
                ).classes("w-40")
                scene_limit_input = ui.number(
                    "표시할 장면 수",
                    value=settings.search.scene_result_limit,
                    min=1,
                    max=20,
                    precision=0,
                ).classes("w-40")
                save_settings_button = ui.button(
                    "설정 저장", on_click=lambda: do_save_settings()
                )
            settings_save_status = ui.label("")

    # ------------------------------------------------------------------
    # 표현 찾기 / 표현 선택
    # ------------------------------------------------------------------

    async def do_lookup() -> None:
        """저장된 표현을 찾고, 하나도 없으면 그 자리에서 AI로 한 번 만든다."""
        nonlocal screen
        text = (meaning_input.value or "").strip()
        if not text:
            ui.notify("한국어 의미를 입력하세요.", type="warning")
            return
        if not lookup_guard.try_begin():
            # 이미 조회 중이면 두 번째 요청은 버린다. 버튼은 비활성으로 막히지만
            # 입력창의 Enter는 그렇게 막히지 않는다.
            return
        # 의미가 바뀌면 이전 표현의 장면 결과도, 이전 의미의 표현 목록도 유효하지 않다.
        # 조회를 기다리는 동안 옛 표현 버튼이 눌리면 새 의미와 옛 표현이 섞인다.
        screen = None
        clear_scene_screen()
        render_expressions()
        lookup_button.disable()
        search_status.set_text("저장된 표현을 찾는 중...")
        try:
            result = await context.call(
                lambda: ui_controller.lookup_or_generate_expressions(
                    settings, database, text
                )
            )
        except _USER_ERRORS as error:
            search_status.set_text(f"표현 찾기 실패: {error}")
            _notify_error(error)
            return
        finally:
            lookup_button.enable()
            lookup_guard.finish()
        screen = result.screen
        if not result.used_ai:
            search_status.set_text(
                f"저장된 표현 {len(screen.relations)}개 — AI를 호출하지 않았습니다."
            )
        elif result.added:
            search_status.set_text(
                f"저장된 표현이 없어 AI로 {len(result.added)}개를 만들어 저장했습니다."
            )
        else:
            search_status.set_text(
                "AI가 이 의미에 자연스러운 일본어 표현을 찾지 못했습니다. "
                "의미를 조금 더 구체적으로 적어 보세요."
            )
        render_expressions()
        if screen.has_expressions:
            tabs.set_value(expressions_tab)

    async def do_generate() -> None:
        """이미 표현이 있을 때 사용자가 추가 생성을 요청하는 동작."""
        nonlocal screen
        text = (meaning_input.value or "").strip()
        if not text:
            ui.notify("한국어 의미를 입력하세요.", type="warning")
            return
        # 입력창의 의미를 바꾼 뒤 눌렀다면 이전 표현의 장면 화면은 더 이상 맞지 않는다.
        if screen is None or normalize_korean_meaning(text) != normalize_korean_meaning(
            screen.korean_meaning
        ):
            screen = None
            clear_scene_screen()
            render_expressions()
        more_button.disable()
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
            more_button.enable()
        if added:
            search_status.set_text(
                f"새 표현 {len(added)}개 저장 · 저장된 표현 {len(screen.relations)}개"
            )
        else:
            search_status.set_text(
                f"새 표현 0개 — 더 붙일 자연스러운 표현이 없습니다 · "
                f"저장된 표현 {len(screen.relations)}개"
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
                    ui.label(ui_controller.expression_line(item)).style("font-size: 1.1rem")
                    ui.label(f"말투: {item.register_text}")
                    if state.relation is not None and state.relation.id == item.id:
                        ui.label("선택됨").style("color: #2e7d32; font-weight: 600")

                    async def do_select(chosen: StoredMeaningExpression = item) -> None:
                        await select_relation(chosen)

                    ui.button("이 표현으로 장면 찾기", on_click=do_select)

    # ------------------------------------------------------------------
    # 장면 검수
    # ------------------------------------------------------------------

    def clear_scene_screen() -> None:
        """이전 의미·표현의 장면 화면을 하나도 남기지 않고 비운다.

        영상 플레이어 인스턴스는 계속 하나만 쓰되, 이전 영상이 보이거나
        재생되지 않도록 멈추고 감춘다.
        """
        state.clear()
        ui_controller.reset_player(player)
        player_box.set_visibility(False)
        saved_box.clear()
        scene_list_box.clear()
        detail_box.clear()
        local_box.clear()
        render_scene_header()

    async def select_relation(chosen: StoredMeaningExpression) -> None:
        """선택한 표현 하나만 검색한다. 검색 결과는 저장하지 않는다."""
        # 이전 표현의 장면·영상·번역 표시가 새 표현과 섞이면 안 된다.
        clear_scene_screen()
        token = state.start_relation(chosen)
        saved = await context.call(lambda: database.list_work_scenes(chosen.id))
        if not state.is_current(token):
            return
        state.saved_scenes = saved
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
            # 사용자가 그 사이 다른 표현으로 넘어갔으면 이 화면은 더 이상 없다.
            if not state.is_current(token):
                return
            render_scene_list(message=NO_ACTIVE_MEDIA_GUIDE)
            ui.notify(NO_ACTIVE_MEDIA_GUIDE, type="warning", multi_line=True)
            return
        except _USER_ERRORS as error:
            if not state.is_current(token):
                return
            render_scene_list(message=f"검색 실패: {error}")
            _notify_error(error)
            return
        if not state.is_current(token):
            return
        state.show_results(found, rows)
        render_scene_list()
        render_local_scenes()
        render_detail()

    def render_scene_header() -> None:
        chosen = state.relation
        if chosen is None or screen is None:
            scene_header.set_text("")
            return
        scene_header.set_text(
            f"작업 맥락: {screen.korean_meaning} → {ui_controller.expression_line(chosen)}"
        )

    def render_saved_scenes() -> None:
        saved_box.clear()
        if state.relation is None or not state.saved_scenes:
            return
        with saved_box:
            ui.label(f"이미 작업한 장면 {len(state.saved_scenes)}개").style("font-weight: 600")
            for scene in state.saved_scenes:
                ui.label(ui_controller.work_scene_line(scene)).style("font-size: 0.9rem")
            ui.separator()

    def render_scene_list(message: str | None = None) -> None:
        scene_list_box.clear()
        with scene_list_box:
            if message is not None:
                ui.label(message)
                return
            if state.relation is None:
                ui.label("일본어 표현 선택 탭에서 표현을 먼저 고르세요.")
                return
            if not state.rows:
                ui.label(
                    "이 표현으로 찾은 Nadeshiko 장면이 없습니다. "
                    "다른 표현을 고르거나 활성 작품을 늘려 보세요."
                )
                return
            ui.label(
                f"Nadeshiko 장면 {len(state.rows)}개 — 하나를 고르면 영상이 로딩됩니다."
            ).style("font-weight: 600")
            for index, row in enumerate(state.rows):
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
        nonlocal player
        if index < 0 or index >= len(state.rows):
            return
        state.selected_index = index
        source = state.rows[index].segment.urls.video_url or ""
        if player is None:
            with player_box:
                player = ui.video(source, controls=True).style(
                    "width: 640px; max-height: 360px"
                )
        else:
            player.set_source(source)
        # 장면을 실제로 고른 지금에만 영상을 보여준다.
        player_box.set_visibility(True)
        render_detail()
        render_scene_list()

    def render_detail() -> None:
        detail_box.clear()
        row = state.selected_row()
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
                row_now = state.selected_row()
                relation = state.relation
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
        row_now = state.selected_row()
        relation = state.relation
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
        row_now = state.selected_row()
        relation = state.relation
        if row_now is None or relation is None:
            return
        try:
            saved = await context.call(
                lambda: ui_controller.save_notes(
                    database, relation, row_now.segment, row_now.media_display_name, value
                )
            )
        except _USER_ERRORS as error:
            _notify_error(error)
            return
        ui.notify("메모를 저장했습니다." if saved is not None else "메모를 비웠습니다.")
        await refresh_rows()

    async def refresh_rows() -> None:
        """저장 후 목록의 작업 상태만 다시 읽는다. 재검색은 하지 않는다."""
        found = state.found
        relation = state.relation
        if found is None or relation is None:
            return
        token = state.request_id
        rows = await context.call(
            lambda: ui_controller.scene_rows(database, found, media_names)
        )
        saved = await context.call(lambda: database.list_work_scenes(relation.id))
        # 읽는 동안 사용자가 다른 표현으로 넘어갔으면 옛 결과를 되살리지 않는다.
        if not state.is_current(token):
            return
        state.rows = rows
        state.saved_scenes = saved
        render_saved_scenes()
        render_scene_list()
        render_detail()

    def render_local_scenes() -> None:
        local_box.clear()
        local_segments = state.local_segments
        if not local_segments:
            return
        with local_box:
            ui.separator()
            ui.label(f"로컬 자막 참고 결과 {len(local_segments)}개").style("font-weight: 600")
            ui.label(LOCAL_SUBTITLE_NOTICE).style("color: #666; font-size: 0.85rem")
            for scene in local_segments:
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
                    ui.label(item.korean_title)
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
            ui.label(
                f"작업 데이터 위치: {summary.work_data_dir} "
                "(실행 중에 바꾸면 열려 있는 데이터베이스와 어긋나므로 파일에서만 바꿉니다)"
            )
            ui.label(f"데이터베이스 파일: {summary.database_file}")
            if context.settings_file is not None:
                ui.label(f"설정 파일: {context.settings_file}")
            ui.label(f"AI 서비스 / 모델: {summary.ai_service} / {summary.ai_model}")
            ui.label(
                f"표현 생성 상한: {summary.expression_generation_limit} · "
                f"표시할 장면 수: {summary.scene_result_limit}"
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

    async def do_save_settings() -> None:
        """설정 파일의 검색 값 두 개를 저장하고 지금 실행에도 반영한다."""
        nonlocal settings
        if context.settings_file is None:
            return
        settings_file = context.settings_file
        try:
            # ui.number는 실수를 주고 범위 제한도 포커스를 잃을 때만 걸린다.
            limit = ui_controller.parse_setting_number(
                generation_limit_input.value, label="표현 생성 상한"
            )
            scene_limit = ui_controller.parse_setting_number(
                scene_limit_input.value, label="표시할 장면 수"
            )
        except _USER_ERRORS as error:
            settings_save_status.set_text(f"설정 저장 실패: {error}")
            _notify_error(error)
            return

        save_settings_button.disable()
        settings_save_status.set_text("설정을 저장하는 중...")
        try:
            saved = await context.call(
                lambda: save_search_settings(
                    settings_file,
                    expression_generation_limit=limit,
                    scene_result_limit=scene_limit,
                )
            )
        except _USER_ERRORS as error:
            settings_save_status.set_text(f"설정 저장 실패: {error}")
            _notify_error(error)
            return
        finally:
            save_settings_button.enable()

        # 다시 읽어 확인한 설정을 지금 열려 있는 화면에도 그대로 쓴다.
        settings = saved
        context.settings = saved
        settings_save_status.set_text("설정을 저장하고 다시 읽어 확인했습니다.")
        render_settings()

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
