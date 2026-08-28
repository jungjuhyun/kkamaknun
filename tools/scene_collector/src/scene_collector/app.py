"""작업 10 — 기존 검증 기능만 연결한 NiceGUI(native mode) 실제 사용자 화면.

화면은 표현 찾기 / 일본어 표현 선택 / 장면 검수 / 선호 작품 / 설정 다섯
영역만 있다. 검색·번역·저장 로직은 ui_controller를 통해 기존 함수를 그대로
사용하고, DB와 네트워크 호출은 단일 작업 thread에서만 실행한다(SQLite 연결의
thread 제약 유지). 검색 결과·선택 같은 화면 상태는 클라이언트(창)별로
관리해 다른 창의 조작이 내 화면 상태를 바꾸지 않는다. 설정 파일은 실행
디렉터리의 settings.toml이며 SCENE_COLLECTOR_SETTINGS_FILE 환경변수로만
다른 경로를 지정할 수 있다.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import TypeVar

from nicegui import ui

from scene_collector import ui_controller
from scene_collector.config import AppSettings, ConfigurationError, load_settings
from scene_collector.database import (
    DatabaseError,
    SceneCollectorDatabase,
    StoredExpression,
    StoredMedia,
)
from scene_collector.media import media_display_name, search_media, store_media
from scene_collector.nadeshiko import create_nadeshiko_client
from scene_collector.search import NoActiveMediaError

_T = TypeVar("_T")

_USER_ERRORS = (ConfigurationError, NoActiveMediaError, DatabaseError, ValueError, RuntimeError)
NO_ACTIVE_MEDIA_GUIDE = (
    "검색에 사용할 활성 작품이 없습니다. 선호 작품 탭에서 작품을 추가하거나 활성화하세요."
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

    # 화면 상태는 이 클라이언트(창)에만 속한다. 다른 창의 검색이 여기를 바꾸지 않는다.
    current: ui_controller.SearchScreenResult | None = None
    selected_expression_id: int | None = None
    media_rows: tuple[StoredMedia, ...] = ()
    media_names: dict[str, str] = {}

    async def refresh_media_state() -> None:
        nonlocal media_rows, media_names
        media_rows = await context.call(database.list_media)
        media_names = {
            media.nadeshiko_media_id: (media.display_name or media.nadeshiko_media_id)
            for media in media_rows
            if media.nadeshiko_media_id is not None
        }

    def selected_item() -> ui_controller.CandidateScreenItem | None:
        if current is None or selected_expression_id is None:
            return None
        for item in current.items:
            if item.expression.id == selected_expression_id:
                return item
        return None

    def replace_expression(expression: StoredExpression) -> None:
        nonlocal current
        if current is None:
            return
        items = tuple(
            ui_controller.CandidateScreenItem(
                expression=expression, local_scenes=item.local_scenes
            )
            if item.expression.id == expression.id
            else item
            for item in current.items
        )
        current = ui_controller.SearchScreenResult(
            run_id=current.run_id,
            korean_intent=current.korean_intent,
            items=items,
        )

    await refresh_media_state()
    current = await context.call(lambda: ui_controller.restore_latest_search(database))
    if current is not None:
        for item in current.items:
            if item.expression.selected:
                selected_expression_id = item.expression.id
                break

    with ui.header().classes("items-center"):
        ui.label("까막눈 애니 표현 장면 수집기").style("font-size: 1.15rem; font-weight: 600")

    with ui.tabs() as tabs:
        search_tab = ui.tab("표현 찾기")
        candidates_tab = ui.tab("일본어 표현 선택")
        scenes_tab = ui.tab("장면 검수")
        media_tab = ui.tab("선호 작품")
        settings_tab = ui.tab("설정")

    with ui.tab_panels(tabs, value=search_tab).classes("w-full"):
        with ui.tab_panel(search_tab):
            ui.label("한국어로 찾고 싶은 의미를 입력하면 기존 검색 흐름을 그대로 실행합니다.")
            intent_input = ui.input(
                "한국어 의미", placeholder="예: 괜찮냐고 걱정하며 묻는 말"
            ).classes("w-96")
            search_status = ui.label("")

            async def do_search() -> None:
                intent = (intent_input.value or "").strip()
                if not intent:
                    ui.notify("한국어 의미를 입력하세요.", type="warning")
                    return
                nonlocal current, selected_expression_id
                search_status.set_text("검색 중... (AI 후보 생성 + Nadeshiko/로컬 자막 검색)")
                search_button.disable()
                try:
                    result = await context.call(
                        lambda: ui_controller.run_expression_search(
                            settings,
                            intent,
                            nadeshiko_client=context.nadeshiko(),
                            database=database,
                        )
                    )
                except NoActiveMediaError:
                    search_status.set_text(NO_ACTIVE_MEDIA_GUIDE)
                    ui.notify(NO_ACTIVE_MEDIA_GUIDE, type="warning", multi_line=True)
                    return
                except _USER_ERRORS as error:
                    search_status.set_text(f"검색 실패: {error}")
                    _notify_error(error)
                    return
                finally:
                    search_button.enable()
                current = result
                selected_expression_id = None
                if result.items:
                    search_status.set_text(
                        f"corpus-backed 후보 {len(result.items)}개 — "
                        "일본어 표현 선택 탭에서 고르세요."
                    )
                else:
                    search_status.set_text(
                        "AI 후보는 생성됐지만 활성 작품 corpus에서 정확 동일표현 장면을 "
                        "찾지 못했습니다. 다른 한국어 의미로 다시 시도하거나 활성 작품을 "
                        "늘려 보세요."
                    )
                render_candidates()
                render_scenes()
                if result.items:
                    tabs.set_value(candidates_tab)

            search_button = ui.button("표현 찾기", on_click=do_search)

        with ui.tab_panel(candidates_tab):
            candidates_box = ui.column().classes("w-full")

        with ui.tab_panel(scenes_tab):
            scenes_box = ui.column().classes("w-full")

        with ui.tab_panel(media_tab):
            ui.label("Nadeshiko 작품을 검색해 저장하고, 기본 검색에 쓸 활성 작품을 관리합니다.")
            with ui.row().classes("items-end"):
                media_query_input = ui.input("작품명 검색", placeholder="예: Chainsaw Man")
                ui.button("Nadeshiko 작품 검색", on_click=lambda: do_media_search())
            media_results_box = ui.column().classes("w-full")
            ui.separator()
            ui.label("저장된 작품")
            media_list_box = ui.column().classes("w-full")

        with ui.tab_panel(settings_tab):
            settings_box = ui.column().classes("w-full")

    def render_candidates() -> None:
        candidates_box.clear()
        with candidates_box:
            if current is None or not current.items:
                ui.label(
                    "표시할 corpus-backed 후보가 없습니다. "
                    "표현 찾기 탭에서 검색을 실행하세요."
                )
                return
            ui.label(f"검색어: {current.korean_intent}")
            for item in current.items:
                candidate = item.expression.candidate
                with ui.card().classes("w-full"):
                    ui.label(f"{candidate.japanese} ({candidate.reading})").style(
                        "font-size: 1.1rem"
                    )
                    ui.label(f"의미: {candidate.meaning_ko} · 말투: {candidate.register}")
                    ui.label(
                        f"Nadeshiko 장면 {len(item.expression.segments)}개 · "
                        f"로컬 자막 장면 {len(item.local_scenes)}개"
                    )
                    if item.expression.id == selected_expression_id:
                        ui.label("선택됨").style("color: #2e7d32; font-weight: 600")

                    async def do_select(expression_id: int = item.expression.id) -> None:
                        nonlocal selected_expression_id
                        if current is None:
                            return
                        try:
                            await context.call(
                                lambda: ui_controller.select_expression(
                                    database, current, expression_id
                                )
                            )
                        except _USER_ERRORS as error:
                            _notify_error(error)
                            return
                        selected_expression_id = expression_id
                        render_candidates()
                        render_scenes()
                        tabs.set_value(scenes_tab)

                    ui.button("이 표현 선택", on_click=do_select)

    def render_scenes() -> None:
        scenes_box.clear()
        with scenes_box:
            item = selected_item()
            if item is None:
                ui.label("일본어 표현 선택 탭에서 표현을 먼저 선택하세요.")
                return
            expression_id = item.expression.id
            candidate = item.expression.candidate
            ui.label(f"선택한 표현: {candidate.japanese} ({candidate.reading})").style(
                "font-size: 1.1rem; font-weight: 600"
            )

            if item.expression.segments:

                async def do_translate() -> None:
                    translate_button.disable()
                    ui.notify("문맥 조회와 한국어 번역을 실행합니다. (캐시가 있으면 재사용)")
                    try:
                        await context.call(
                            lambda: ui_controller.load_scene_translations(
                                settings,
                                expression_id,
                                nadeshiko_client=context.nadeshiko(),
                                database=database,
                            )
                        )
                        refreshed = await context.call(
                            lambda: ui_controller.refresh_expression(database, expression_id)
                        )
                    except _USER_ERRORS as error:
                        _notify_error(error)
                        return
                    finally:
                        translate_button.enable()
                    replace_expression(refreshed)
                    render_scenes()

                translate_button = ui.button("문맥 조회 + 한국어 번역", on_click=do_translate)

            for stored in item.expression.segments:
                segment = stored.segment
                with ui.card().classes("w-full"):
                    media_name = media_names.get(
                        segment.media_public_id, segment.media_public_id
                    )
                    episode = f"{segment.episode}화" if segment.episode is not None else "화수 없음"
                    ui.label(f"{media_name} · {episode}")
                    if segment.urls.video_url:
                        ui.video(segment.urls.video_url, controls=True).style(
                            "width: 640px; max-height: 360px"
                        )
                    ui.label(segment.text_ja.content).style("font-size: 1.05rem")

                    review = stored.review
                    if review is not None and review.direct_meaning:
                        ui.label(f"직접적인 뜻: {review.direct_meaning}")
                        ui.label(f"자연스러운 번역: {review.natural_translation}")
                        ui.label(f"장면에서의 쓰임: {review.scene_usage}")
                    else:
                        ui.label("아직 한국어 번역이 없습니다. 위의 번역 버튼을 사용하세요.").style(
                            "color: #666"
                        )

                    decision = review.decision if review is not None else None
                    ui.label(f"판정: {decision}" if decision else "판정: 없음").style(
                        "font-weight: 600"
                    )

                    with ui.row():
                        for decision_value in ui_controller.REVIEW_DECISIONS:

                            async def do_decide(
                                segment_id: int = stored.id,
                                value: str = decision_value,
                            ) -> None:
                                try:
                                    await context.call(
                                        lambda: ui_controller.save_decision(
                                            database, expression_id, segment_id, value
                                        )
                                    )
                                    refreshed = await context.call(
                                        lambda: ui_controller.refresh_expression(
                                            database, expression_id
                                        )
                                    )
                                except _USER_ERRORS as error:
                                    _notify_error(error)
                                    return
                                replace_expression(refreshed)
                                ui.notify(f"판정을 저장했습니다: {value}")
                                render_scenes()

                            ui.button(decision_value, on_click=do_decide)

            if item.local_scenes:
                ui.separator()
                ui.label("로컬 자막 장면 (사용자가 보유한 원본 영상에서 직접 확인)").style(
                    "font-weight: 600"
                )
                ui.label(
                    "로컬 자막 작품에는 영상 미리보기가 없는 것이 정상입니다. "
                    "판본 차이로 타임코드에 ±15초 안팎의 offset이 있을 수 있습니다."
                ).style("color: #666")
                for scene in item.local_scenes:
                    ui.label(ui_controller.local_scene_line(scene))
            elif not item.expression.segments:
                ui.label("이 표현에는 표시할 장면이 없습니다.")

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

                    async def do_store(summary=summary) -> None:
                        try:
                            await context.call(lambda: store_media(database, summary))
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
                f"AI 후보 수: {summary.candidate_count} · "
                f"후보별 Nadeshiko 조회량: {summary.nadeshiko_take}"
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

    render_candidates()
    render_scenes()
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
