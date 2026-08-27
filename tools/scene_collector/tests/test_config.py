from pathlib import Path

import pytest

from scene_collector.config import SettingsLoadError, load_settings


def write_settings(
    path: Path,
    work_data_dir: Path,
    *,
    service: str = "openai",
    model: str = "test-model",
) -> None:
    path.write_text(
        "\n".join(
            [
                "[storage]",
                f'work_data_dir = "{work_data_dir.as_posix()}"',
                "",
                "[ai]",
                f'service = "{service}"',
                f'model = "{model}"',
                "",
            ]
        ),
        encoding="utf-8",
    )


def test_load_settings_from_toml(tmp_path: Path) -> None:
    settings_path = tmp_path / "settings.toml"
    work_data_dir = tmp_path / "work-data"
    write_settings(settings_path, work_data_dir)

    settings = load_settings(settings_path, env_file=None)

    assert settings.storage.work_data_dir == work_data_dir
    assert settings.ai.service == "openai"
    assert settings.ai.model == "test-model"
    assert settings.nadeshiko_api_key is None


def test_environment_overrides_toml(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    settings_path = tmp_path / "settings.toml"
    write_settings(settings_path, tmp_path / "work-data")
    monkeypatch.setenv("SCENE_COLLECTOR_AI__MODEL", "environment-model")

    settings = load_settings(settings_path, env_file=None)

    assert settings.ai.model == "environment-model"


def test_environment_overrides_dotenv_and_dotenv_overrides_toml(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings_path = tmp_path / "settings.toml"
    env_path = tmp_path / ".env"
    write_settings(settings_path, tmp_path / "work-data")
    env_path.write_text(
        "\n".join(
            [
                "SCENE_COLLECTOR_AI__SERVICE=dotenv-service",
                "SCENE_COLLECTOR_AI__MODEL=dotenv-model",
                "NADESHIKO_API_KEY=test-secret",
                "",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("SCENE_COLLECTOR_AI__MODEL", "environment-model")

    settings = load_settings(settings_path, env_file=env_path)

    assert settings.ai.service == "dotenv-service"
    assert settings.ai.model == "environment-model"
    assert settings.nadeshiko_api_key is not None
    assert settings.nadeshiko_api_key.get_secret_value() == "test-secret"


def test_blank_required_value_has_clear_error(tmp_path: Path) -> None:
    settings_path = tmp_path / "settings.toml"
    settings_path.write_text(
        """[storage]
work_data_dir = ""

[ai]
service = "openai"
model = "test-model"
""",
        encoding="utf-8",
    )

    with pytest.raises(SettingsLoadError, match="work_data_dir"):
        load_settings(settings_path, env_file=None)


def test_missing_settings_file_has_clear_error(tmp_path: Path) -> None:
    missing_path = tmp_path / "missing.toml"

    with pytest.raises(SettingsLoadError, match="설정 파일을 찾을 수 없습니다"):
        load_settings(missing_path, env_file=None)
