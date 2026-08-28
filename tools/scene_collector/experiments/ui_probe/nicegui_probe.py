"""Task 9 — NiceGUI native mode probe.

실제 Nadeshiko MP4 목록을 한 창에서 연속 탐색한다.
SCENE_COLLECTOR_UI_PROBE_DATA: fetch_probe_segments.py가 만든 JSON 경로
SCENE_COLLECTOR_UI_PROBE_LOG: 진단 로그 파일 경로
"""

from __future__ import annotations

import atexit
import json
import os
import time
from datetime import datetime
from importlib import metadata

from nicegui import app, ui

DATA_PATH = os.environ["SCENE_COLLECTOR_UI_PROBE_DATA"]
LOG_PATH = os.environ["SCENE_COLLECTOR_UI_PROBE_LOG"]
KOREAN_TEST_TEXT = "한국어 표시 시험 문구입니다. 괜찮으세요?"

with open(DATA_PATH, encoding="utf-8") as handle:
    SCENES = json.load(handle)

START_TIME = time.monotonic()


def log(message: str) -> None:
    stamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    with open(LOG_PATH, "a", encoding="utf-8") as handle:
        handle.write(f"[{stamp}] {message}\n")


log(f"probe start, nicegui {metadata.version('nicegui')}, "
    f"pywebview {metadata.version('pywebview')}, scenes {len(SCENES)}")
atexit.register(lambda: log("probe process exit"))

state = {"index": 0, "playing": True}


@ui.page("/")
def main_page() -> None:
    status = ui.label()
    ja = ui.label().style("font-size: 1.2rem")
    ui.label(KOREAN_TEST_TEXT)
    ua = ui.label("user-agent: 확인 중...").style("font-size: 0.75rem; color: #666")
    video = ui.video(SCENES[0]["video_url"], controls=True, autoplay=True).style(
        "width: 920px; max-height: 520px"
    )

    def show(index: int) -> None:
        state["index"] = index % len(SCENES)
        scene = SCENES[state["index"]]
        try:
            video.set_source(scene["video_url"])
            video.play()
            state["playing"] = True
            play_button.set_text("일시정지")
            status.set_text(f"{state['index'] + 1} / {len(SCENES)}")
            ja.set_text(scene["text_ja"])
            log(f"scene {state['index'] + 1} shown")
        except Exception as error:  # 진단 목적의 광범위한 기록
            log(f"scene change ERROR: {error!r}")

    def toggle_play() -> None:
        if state["playing"]:
            video.pause()
            state["playing"] = False
            play_button.set_text("재생")
        else:
            video.play()
            state["playing"] = True
            play_button.set_text("일시정지")

    with ui.row():
        ui.button("이전", on_click=lambda: show(state["index"] - 1))
        play_button = ui.button("일시정지", on_click=toggle_play)
        ui.button("다음", on_click=lambda: show(state["index"] + 1))

    show(0)

    async def grab_user_agent() -> None:
        try:
            agent = await ui.run_javascript("navigator.userAgent")
            ua.set_text(f"user-agent: {agent}")
            log(f"user-agent: {agent}")
        except Exception as error:
            log(f"user-agent ERROR: {error!r}")

    ui.timer(1.0, grab_user_agent, once=True)


def on_connect() -> None:
    log(f"client connected, {time.monotonic() - START_TIME:.1f}s after start")


app.on_connect(on_connect)

if __name__ == "__main__":
    ui.run(
        native=True,
        window_size=(1000, 760),
        title="NiceGUI probe — Task 9",
        reload=False,
        show_welcome_message=False,
    )
