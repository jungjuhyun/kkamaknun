import json
import re
from pathlib import Path

import pytest

import scene_collector.config as config_module
from scene_collector.config import ConfigurationError, load_settings


def _toml_string(value: str | Path) -> str:
    return json.dumps(str(value))


def _write_settings(
    settings_file: Path,
    *,
    work_data_dir: str,
    service: str = '"test-service"',
    model: str = '"test-model"',
    candidate_count: str = "5",
    nadeshiko_take: str = "5",
) -> None:
    settings_file.write_text(
        "\n".join(
            (
                "[storage]",
                f"work_data_dir = {work_data_dir}",
                "",
                "[ai]",
                f"service = {service}",
                f"model = {model}",
                "",
                "[search]",
                f"candidate_count = {candidate_count}",
                f"nadeshiko_take = {nadeshiko_take}",
                "",
            )
        ),
        encoding="utf-8",
    )


def test_loads_valid_settings_from_toml(tmp_path: Path) -> None:
    work_data_dir = tmp_path / "work-data"
    work_data_dir.mkdir()
    settings_file = tmp_path / "settings.toml"
    _write_settings(settings_file, work_data_dir=_toml_string(work_data_dir))

    settings = load_settings(settings_file)

    assert settings.storage.work_data_dir == work_data_dir
    assert settings.ai.service == "test-service"
    assert settings.ai.model == "test-model"
    assert settings.search.candidate_count == 5
    assert settings.search.nadeshiko_take == 5


@pytest.mark.parametrize(
    ("overrides", "location"),
    (
        ({"work_data_dir": '""'}, "storage.work_data_dir"),
        ({"service": '""'}, "ai.service"),
        ({"model": '"   "'}, "ai.model"),
    ),
)
def test_rejects_empty_required_values(
    tmp_path: Path,
    overrides: dict[str, str],
    location: str,
) -> None:
    work_data_dir = tmp_path / "work-data"
    work_data_dir.mkdir()
    values = {
        "work_data_dir": _toml_string(work_data_dir),
        "service": '"test-service"',
        "model": '"test-model"',
    }
    values.update(overrides)
    settings_file = tmp_path / "settings.toml"
    _write_settings(settings_file, **values)

    with pytest.raises(ConfigurationError, match=location):
        load_settings(settings_file)


def test_loads_secret_from_dotenv(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NADESHIKO_API_KEY", raising=False)
    work_data_dir = tmp_path / "work-data"
    work_data_dir.mkdir()
    settings_file = tmp_path / "settings.toml"
    _write_settings(settings_file, work_data_dir=_toml_string(work_data_dir))
    (tmp_path / ".env").write_text(
        "NADESHIKO_API_KEY=dotenv-test-secret\n",
        encoding="utf-8",
    )

    settings = load_settings(settings_file)

    assert settings.nadeshiko_api_key is not None
    assert settings.nadeshiko_api_key.get_secret_value() == "dotenv-test-secret"
    assert "dotenv-test-secret" not in repr(settings)


def test_environment_secret_overrides_dotenv(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    work_data_dir = tmp_path / "work-data"
    work_data_dir.mkdir()
    settings_file = tmp_path / "settings.toml"
    _write_settings(settings_file, work_data_dir=_toml_string(work_data_dir))
    (tmp_path / ".env").write_text(
        "NADESHIKO_API_KEY=dotenv-test-secret\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("NADESHIKO_API_KEY", "environment-test-secret")

    settings = load_settings(settings_file)

    assert settings.nadeshiko_api_key is not None
    assert settings.nadeshiko_api_key.get_secret_value() == "environment-test-secret"


def test_rejects_invalid_setting_type(tmp_path: Path) -> None:
    work_data_dir = tmp_path / "work-data"
    work_data_dir.mkdir()
    settings_file = tmp_path / "settings.toml"
    _write_settings(
        settings_file,
        work_data_dir=_toml_string(work_data_dir),
        model="123",
    )

    with pytest.raises(ConfigurationError, match="ai.model"):
        load_settings(settings_file)


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("candidate_count", "2"),
        ("candidate_count", "6"),
        ("candidate_count", '"5"'),
        ("nadeshiko_take", "0"),
        ("nadeshiko_take", "21"),
        ("nadeshiko_take", '"5"'),
    ),
)
def test_rejects_invalid_search_settings(tmp_path: Path, field: str, value: str) -> None:
    work_data_dir = tmp_path / "work-data"
    work_data_dir.mkdir()
    settings_file = tmp_path / "settings.toml"
    overrides = {field: value}
    _write_settings(
        settings_file,
        work_data_dir=_toml_string(work_data_dir),
        **overrides,
    )

    with pytest.raises(ConfigurationError, match=f"search.{field}"):
        load_settings(settings_file)


def test_rejects_missing_work_data_directory(tmp_path: Path) -> None:
    settings_file = tmp_path / "settings.toml"
    missing_directory = tmp_path / "missing"
    _write_settings(settings_file, work_data_dir=_toml_string(missing_directory))

    with pytest.raises(ConfigurationError, match="존재하지 않습니다"):
        load_settings(settings_file)


def test_python_source_has_no_hard_coded_user_path() -> None:
    source_directory = Path(config_module.__file__).resolve().parent
    absolute_windows_path = re.compile(r"(?i)(?:[a-z]:[\\/]|\\\\[^\\])")

    for source_file in source_directory.glob("*.py"):
        assert absolute_windows_path.search(source_file.read_text(encoding="utf-8")) is None
    assert not config_module.DEFAULT_SETTINGS_FILE.is_absolute()
