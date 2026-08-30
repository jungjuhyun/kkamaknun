import json
from pathlib import Path

import pytest
from nadeshiko.models import SearchResponse

import scene_collector.nadeshiko as nadeshiko_module
from scene_collector.config import (
    AISettings,
    AppSettings,
    ConfigurationError,
    SearchSettings,
    StorageSettings,
)

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "nadeshiko_search_response.json"


def _settings(tmp_path: Path, *, api_key: str | None) -> AppSettings:
    values: dict[str, object] = {
        "storage": StorageSettings(work_data_dir=tmp_path),
        "ai": AISettings(service="unused-in-task-2", model="unused-in-task-2"),
        "search": SearchSettings(expression_generation_limit=5, scene_result_limit=5),
    }
    if api_key is not None:
        values["NADESHIKO_API_KEY"] = api_key
    return AppSettings(**values)


def test_creates_official_sdk_client_from_settings(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    received: dict[str, str] = {}

    class FakeNadeshiko:
        def __init__(self, *, api_key: str) -> None:
            received["api_key"] = api_key

    monkeypatch.setattr(nadeshiko_module, "Nadeshiko", FakeNadeshiko)

    client = nadeshiko_module.create_nadeshiko_client(
        _settings(tmp_path, api_key="offline-test-secret")
    )

    assert isinstance(client, FakeNadeshiko)
    assert received == {"api_key": "offline-test-secret"}


def test_rejects_missing_nadeshiko_api_key(tmp_path: Path) -> None:
    with pytest.raises(ConfigurationError, match="NADESHIKO_API_KEY"):
        nadeshiko_module.create_nadeshiko_client(_settings(tmp_path, api_key=None))


def test_anonymized_fixture_matches_official_sdk_models() -> None:
    response = SearchResponse.from_dict(json.loads(FIXTURE_PATH.read_text(encoding="utf-8")))

    assert len(response.segments) == 1
    segment = response.segments[0]
    assert segment.public_id == "anonymous-segment-001"
    assert segment.text_ja.content == "大丈夫ですか？"
    assert segment.urls.image_url.endswith("/image.jpg")
    assert segment.urls.audio_url.endswith("/audio.mp3")
    assert segment.urls.video_url.endswith("/video.mp4")
    assert response.pagination.has_more is True
