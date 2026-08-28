"""Task 9 UI probe용 실제 Nadeshiko 영상 목록을 임시 JSON으로 저장한다.

사용법:
    uv run python experiments/ui_probe/fetch_probe_segments.py <출력.json>

NADESHIKO_API_KEY 환경변수가 필요하다. 출력 JSON은 저장소에 commit하지 않는다.
"""

from __future__ import annotations

import json
import os
import sys

from nadeshiko import Nadeshiko
from nadeshiko.models import SearchQuery

PROBE_QUERY = os.environ.get("SCENE_COLLECTOR_UI_PROBE_QUERY", "大丈夫")
PROBE_COUNT = 20


def main() -> int:
    if len(sys.argv) != 2:
        print("출력 JSON 경로 하나를 인자로 전달하세요.")
        return 1
    api_key = os.environ.get("NADESHIKO_API_KEY", "").strip()
    if not api_key:
        print("NADESHIKO_API_KEY 환경변수가 필요합니다.")
        return 1

    client = Nadeshiko(api_key=api_key)
    try:
        response = client.search(query=SearchQuery(search=PROBE_QUERY), take=PROBE_COUNT)
    finally:
        client.close()

    scenes = [
        {
            "video_url": segment.urls.video_url,
            "text_ja": segment.text_ja.content,
        }
        for segment in response.segments
    ]
    if len(scenes) < PROBE_COUNT:
        print(f"경고: 요청한 {PROBE_COUNT}개보다 적은 {len(scenes)}개만 회수했습니다.")
    with open(sys.argv[1], "w", encoding="utf-8") as handle:
        json.dump(scenes, handle, ensure_ascii=False, indent=2)
    print(f"{len(scenes)}개 장면을 저장했습니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
