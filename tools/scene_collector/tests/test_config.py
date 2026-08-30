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
    expression_generation_limit: str | None = "5",
    nadeshiko_take: str | None = "5",
    candidate_count: str | None = None,
) -> None:
    """설정 파일을 쓴다. 값이 None인 검색 항목은 아예 기록하지 않는다."""
    search_entries = (
        ("expression_generation_limit", expression_generation_limit),
        ("candidate_count", candidate_count),
        ("nadeshiko_take", nadeshiko_take),
    )
    lines = [
        "[storage]",
        f"work_data_dir = {work_data_dir}",
        "",
        "[ai]",
        f"service = {service}",
        f"model = {model}",
        "",
        "[search]",
    ]
    lines.extend(f"{key} = {value}" for key, value in search_entries if value is not None)
    lines.append("")
    settings_file.write_text("\n".join(lines), encoding="utf-8")


def _work_data_dir(tmp_path: Path) -> Path:
    work_data_dir = tmp_path / "work-data"
    work_data_dir.mkdir()
    return work_data_dir


def test_loads_valid_settings_from_toml(tmp_path: Path) -> None:
    work_data_dir = _work_data_dir(tmp_path)
    settings_file = tmp_path / "settings.toml"
    _write_settings(settings_file, work_data_dir=_toml_string(work_data_dir))

    settings = load_settings(settings_file)

    assert settings.storage.work_data_dir == work_data_dir
    assert settings.ai.service == "test-service"
    assert settings.ai.model == "test-model"
    assert settings.search.expression_generation_limit == 5
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
    work_data_dir = _work_data_dir(tmp_path)
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
    work_data_dir = _work_data_dir(tmp_path)
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
    work_data_dir = _work_data_dir(tmp_path)
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
    work_data_dir = _work_data_dir(tmp_path)
    settings_file = tmp_path / "settings.toml"
    _write_settings(
        settings_file,
        work_data_dir=_toml_string(work_data_dir),
        model="123",
    )

    with pytest.raises(ConfigurationError, match="ai.model"):
        load_settings(settings_file)


def test_legacy_candidate_count_is_ignored_and_not_inherited(tmp_path: Path) -> None:
    """옛 키만 남은 설정 파일도 오류 없이 읽히고, 그 값이 새 상한으로 승계되지 않는다."""
    work_data_dir = _work_data_dir(tmp_path)
    settings_file = tmp_path / "settings.toml"
    _write_settings(
        settings_file,
        work_data_dir=_toml_string(work_data_dir),
        expression_generation_limit=None,
        candidate_count="3",
    )

    settings = load_settings(settings_file)

    assert settings.search.expression_generation_limit == 20
    assert settings.search.nadeshiko_take == 5
    assert not hasattr(settings.search, "candidate_count")


def test_expression_generation_limit_wins_over_legacy_candidate_count(tmp_path: Path) -> None:
    """두 키가 함께 있으면 새 키 값을 쓰고 옛 키는 무시한다."""
    work_data_dir = _work_data_dir(tmp_path)
    settings_file = tmp_path / "settings.toml"
    _write_settings(
        settings_file,
        work_data_dir=_toml_string(work_data_dir),
        expression_generation_limit="12",
        candidate_count="3",
    )

    settings = load_settings(settings_file)

    assert settings.search.expression_generation_limit == 12


@pytest.mark.parametrize("value", ("1", "20"))
def test_accepts_expression_generation_limit_bounds(tmp_path: Path, value: str) -> None:
    work_data_dir = _work_data_dir(tmp_path)
    settings_file = tmp_path / "settings.toml"
    _write_settings(
        settings_file,
        work_data_dir=_toml_string(work_data_dir),
        expression_generation_limit=value,
    )

    settings = load_settings(settings_file)

    assert settings.search.expression_generation_limit == int(value)


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("expression_generation_limit", "0"),
        ("expression_generation_limit", "21"),
        ("expression_generation_limit", '"5"'),
        ("nadeshiko_take", "0"),
        ("nadeshiko_take", "21"),
        ("nadeshiko_take", '"5"'),
    ),
)
def test_rejects_invalid_search_settings(tmp_path: Path, field: str, value: str) -> None:
    work_data_dir = _work_data_dir(tmp_path)
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


def test_malformed_toml_raises_configuration_error(tmp_path: Path) -> None:
    broken = tmp_path / "settings.toml"
    broken.write_text("[storage\nwork_data_dir = ???", encoding="utf-8")

    with pytest.raises(ConfigurationError, match="설정 파일 형식이 올바르지 않습니다"):
        load_settings(broken)

    # raw TOML parser 예외가 밖으로 새지 않고, 설정 원문도 메시지에 노출되지 않는다
    import tomllib

    try:
        load_settings(broken)
    except ConfigurationError as error:
        assert not isinstance(error, tomllib.TOMLDecodeError)
        assert "work_data_dir = ???" not in str(error)
    else:  # pragma: no cover - 위 raises에서 이미 실패한다
        raise AssertionError("ConfigurationError가 발생해야 합니다")
