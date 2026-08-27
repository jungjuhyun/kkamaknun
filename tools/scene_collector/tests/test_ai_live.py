import json
import os
from pathlib import Path

import pytest
from pydantic import BaseModel

from scene_collector.ai import create_structured_response
from scene_collector.config import load_settings


class ConnectivityProbe(BaseModel):
    text: str
    number: int


PROMPT = (
    "Return these facts as structured data: text must be 'connection-ok' and number must be 7."
)


@pytest.mark.ai_live
@pytest.mark.parametrize(
    ("service", "api_key_environment", "model_environment"),
    (
        ("openai", "OPENAI_API_KEY", "SCENE_COLLECTOR_AI_LIVE_OPENAI_MODEL"),
        ("google", "GOOGLE_API_KEY", "SCENE_COLLECTOR_AI_LIVE_GOOGLE_MODEL"),
    ),
    ids=("openai", "google"),
)
def test_provider_returns_same_structured_response(
    tmp_path: Path,
    service: str,
    api_key_environment: str,
    model_environment: str,
) -> None:
    if not os.environ.get(api_key_environment):
        pytest.fail(f"Missing required live-test environment variable: {api_key_environment}")

    model = os.environ.get(model_environment)
    if not model:
        pytest.fail(f"Missing required live-test environment variable: {model_environment}")

    work_data_dir = tmp_path / "work-data"
    work_data_dir.mkdir()
    settings_file = tmp_path / "settings.toml"
    settings_file.write_text(
        "\n".join(
            (
                "[storage]",
                f"work_data_dir = {json.dumps(str(work_data_dir))}",
                "",
                "[ai]",
                f"service = {json.dumps(service)}",
                f"model = {json.dumps(model)}",
                "",
                "[search]",
                "candidate_count = 5",
                "nadeshiko_take = 5",
                "",
            )
        ),
        encoding="utf-8",
    )
    settings = load_settings(settings_file)

    response = create_structured_response(
        settings,
        prompt=PROMPT,
        response_model=ConnectivityProbe,
    )

    assert isinstance(response, ConnectivityProbe)
    assert response.text == "connection-ok"
    assert type(response.text) is str
    assert response.number == 7
    assert type(response.number) is int
