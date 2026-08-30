import json
import re
from pathlib import Path

import pytest

import scene_collector.config as config_module
from scene_collector.config import (
    AppSettings,
    ConfigurationError,
    load_settings,
    save_search_settings,
)


def _toml_string(value: str | Path) -> str:
    return json.dumps(str(value))


def _write_settings(
    settings_file: Path,
    *,
    work_data_dir: str,
    service: str = '"test-service"',
    model: str = '"test-model"',
    expression_generation_limit: str | None = "5",
    scene_result_limit: str | None = "5",
    candidate_count: str | None = None,
    nadeshiko_take: str | None = None,
) -> None:
    """설정 파일을 쓴다. 값이 None인 검색 항목은 아예 기록하지 않는다."""
    search_entries = (
        ("expression_generation_limit", expression_generation_limit),
        ("scene_result_limit", scene_result_limit),
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
    assert settings.search.scene_result_limit == 5


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
    assert settings.search.scene_result_limit == 5
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


def test_legacy_nadeshiko_take_is_ignored_and_not_inherited(tmp_path: Path) -> None:
    """옛 nadeshiko_take는 뜻이 달라졌으므로 값을 승계하지 않는다.

    옛 키는 API에서 한 번에 받아올 후보 수였고, 새 키는 화면에 보여줄 장면
    수다. 구 설정 파일이 오류를 내지는 않지만 그 숫자를 그대로 쓰지 않는다.
    """
    work_data_dir = _work_data_dir(tmp_path)
    settings_file = tmp_path / "settings.toml"
    _write_settings(
        settings_file,
        work_data_dir=_toml_string(work_data_dir),
        scene_result_limit=None,
        nadeshiko_take="3",
    )

    settings = load_settings(settings_file)

    assert settings.search.scene_result_limit == 5
    assert not hasattr(settings.search, "nadeshiko_take")


def test_scene_result_limit_wins_over_legacy_nadeshiko_take(tmp_path: Path) -> None:
    """두 키가 함께 있으면 새 키 값을 쓰고 옛 키는 무시한다."""
    work_data_dir = _work_data_dir(tmp_path)
    settings_file = tmp_path / "settings.toml"
    _write_settings(
        settings_file,
        work_data_dir=_toml_string(work_data_dir),
        scene_result_limit="7",
        nadeshiko_take="3",
    )

    assert load_settings(settings_file).search.scene_result_limit == 7


def test_only_the_legacy_handler_still_mentions_the_old_search_keys() -> None:
    """옛 키 이름이 코드에 남아 있으면 값이 조용히 기본값으로 바뀌는 회귀가 생긴다.

    옛 키는 mode="before" 검증기가 조용히 버리므로, 이름을 못 고친 자리는
    오류가 아니라 '뜻이 달라진 기본값'으로 넘어가 시험이 통과해 버린다.
    그래서 이름이 남은 자리를 문자열로 직접 막는다.
    """
    root = Path(__file__).resolve().parents[1]
    allowed = {root / "src" / "scene_collector" / "config.py", Path(__file__).resolve()}
    offenders = [
        path.relative_to(root).as_posix()
        for path in (*root.glob("src/**/*.py"), *root.glob("tests/**/*.py"))
        if path.resolve() not in allowed and "nadeshiko_take" in path.read_text(encoding="utf-8")
    ]
    assert offenders == []


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
        ("scene_result_limit", "0"),
        ("scene_result_limit", "21"),
        ("scene_result_limit", '"5"'),
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


# ----------------------------------------------------------------------
# 화면에서 설정을 저장한다 (실제 SSD 설정 파일은 절대 쓰지 않는다)
# ----------------------------------------------------------------------

SETTINGS_WITH_COMMENTS = """\
# 사용자가 직접 적어 둔 안내 주석이다. 저장해도 그대로 남아야 한다.
[storage]
work_data_dir = {work_data_dir}

[ai]
service = "test-service"  # 줄 끝 주석
model = "test-model"

# 검색 관련 설정
[search]
expression_generation_limit = 5
scene_result_limit = 5
"""


def _settings_with_comments(tmp_path: Path, *, line_ending: str = "\n") -> tuple[Path, Path]:
    work_data_dir = _work_data_dir(tmp_path)
    settings_file = tmp_path / "settings.toml"
    body = SETTINGS_WITH_COMMENTS.format(work_data_dir=_toml_string(work_data_dir))
    if line_ending != "\n":
        body = body.replace("\n", line_ending)
    with settings_file.open("w", encoding="utf-8", newline="") as file:
        file.write(body)
    return settings_file, work_data_dir


def _raw(path: Path) -> str:
    """줄바꿈 문자를 바꾸지 않고 원문 그대로 읽는다."""
    with path.open("r", encoding="utf-8", newline="") as file:
        return file.read()


def test_saving_changes_only_the_two_known_lines(tmp_path: Path) -> None:
    """알려진 값 줄만 바꾸고 주석과 다른 섹션은 글자 그대로 둔다."""
    settings_file, _ = _settings_with_comments(tmp_path)
    before = _raw(settings_file).splitlines(keepends=True)

    saved = save_search_settings(
        settings_file, expression_generation_limit=12, scene_result_limit=7
    )

    assert saved.search.expression_generation_limit == 12
    assert saved.search.scene_result_limit == 7
    after = _raw(settings_file).splitlines(keepends=True)
    assert len(after) == len(before)
    changed = [index for index, (old, new) in enumerate(zip(before, after)) if old != new]
    assert len(changed) == 2
    assert after[changed[0]].strip() == "expression_generation_limit = 12"
    assert after[changed[1]].strip() == "scene_result_limit = 7"
    # 다시 읽어도 유지된다.
    assert load_settings(settings_file).search.scene_result_limit == 7


def test_saving_preserves_windows_line_endings(tmp_path: Path) -> None:
    """CRLF 파일을 저장해도 줄바꿈 문자가 바뀌지 않는다."""
    settings_file, _ = _settings_with_comments(tmp_path, line_ending="\r\n")

    save_search_settings(settings_file, expression_generation_limit=3, scene_result_limit=4)

    raw = _raw(settings_file)
    assert "\r\n" in raw
    assert "\n" not in raw.replace("\r\n", "")


def test_missing_key_is_inserted_inside_its_table(tmp_path: Path) -> None:
    work_data_dir = _work_data_dir(tmp_path)
    settings_file = tmp_path / "settings.toml"
    _write_settings(
        settings_file,
        work_data_dir=_toml_string(work_data_dir),
        expression_generation_limit=None,
    )

    save_search_settings(settings_file, expression_generation_limit=9, scene_result_limit=6)

    settings = load_settings(settings_file)
    assert settings.search.expression_generation_limit == 9
    assert settings.search.scene_result_limit == 6


def test_missing_search_table_is_appended(tmp_path: Path) -> None:
    work_data_dir = _work_data_dir(tmp_path)
    settings_file = tmp_path / "settings.toml"
    settings_file.write_text(
        "[storage]\n"
        f"work_data_dir = {_toml_string(work_data_dir)}\n\n"
        "[ai]\n"
        'service = "s"\n'
        'model = "m"\n',
        encoding="utf-8",
    )

    save_search_settings(settings_file, expression_generation_limit=2, scene_result_limit=3)

    settings = load_settings(settings_file)
    assert settings.search.expression_generation_limit == 2
    assert settings.search.scene_result_limit == 3


def test_out_of_range_values_are_refused_before_writing(tmp_path: Path) -> None:
    """범위를 벗어난 값은 파일을 열지도 않고 거절한다."""
    settings_file, _ = _settings_with_comments(tmp_path)
    before = _raw(settings_file)

    for limit, result in ((0, 5), (21, 5), (5, 0), (5, 21)):
        with pytest.raises(ConfigurationError):
            save_search_settings(
                settings_file, expression_generation_limit=limit, scene_result_limit=result
            )
        assert _raw(settings_file) == before


def test_duplicate_key_is_refused_without_touching_the_file(tmp_path: Path) -> None:
    work_data_dir = _work_data_dir(tmp_path)
    settings_file = tmp_path / "settings.toml"
    settings_file.write_text(
        "[storage]\n"
        f"work_data_dir = {_toml_string(work_data_dir)}\n\n"
        "[ai]\n"
        'service = "s"\n'
        'model = "m"\n\n'
        "[search]\n"
        "scene_result_limit = 5\n"
        "scene_result_limit = 6\n",
        encoding="utf-8",
    )
    before = _raw(settings_file)

    with pytest.raises(ConfigurationError, match="여러 번"):
        save_search_settings(settings_file, expression_generation_limit=5, scene_result_limit=5)

    assert _raw(settings_file) == before


def test_multiline_string_settings_are_refused(tmp_path: Path) -> None:
    """여러 줄 문자열이 있으면 구조를 추측하지 않고 거절한다."""
    work_data_dir = _work_data_dir(tmp_path)
    settings_file = tmp_path / "settings.toml"
    triple = chr(34) * 3
    settings_file.write_text(
        "[storage]\n"
        f"work_data_dir = {_toml_string(work_data_dir)}\n\n"
        "[ai]\n"
        'service = "s"\n'
        f"model = {triple}여러\n줄{triple}\n\n"
        "[search]\n"
        "scene_result_limit = 5\n",
        encoding="utf-8",
    )
    before = _raw(settings_file)

    with pytest.raises(ConfigurationError, match="여러 줄 문자열"):
        save_search_settings(settings_file, expression_generation_limit=5, scene_result_limit=6)

    assert _raw(settings_file) == before


def test_dotted_search_key_is_refused(tmp_path: Path) -> None:
    """점 표기로 쓴 설정은 구조를 추측하지 않고 거절한다."""
    work_data_dir = _work_data_dir(tmp_path)
    settings_file = tmp_path / "settings.toml"
    # 점 표기 최상위 키는 어떤 표 머리말보다 앞에 와야 유효한 TOML이다.
    settings_file.write_text(
        "search.scene_result_limit = 5\n\n"
        "[storage]\n"
        f"work_data_dir = {_toml_string(work_data_dir)}\n\n"
        "[ai]\n"
        'service = "s"\n'
        'model = "m"\n',
        encoding="utf-8",
    )
    before = _raw(settings_file)

    with pytest.raises(ConfigurationError, match="점 표기"):
        save_search_settings(settings_file, expression_generation_limit=5, scene_result_limit=6)

    assert _raw(settings_file) == before


def test_failed_reload_restores_the_original_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """저장 뒤 다시 읽지 못하면 원본 원문을 되돌린다."""
    settings_file, _ = _settings_with_comments(tmp_path)
    before = _raw(settings_file)

    def broken_load(*args: object, **kwargs: object) -> AppSettings:
        raise ConfigurationError("일부러 실패시킨다")

    monkeypatch.setattr(config_module, "load_settings", broken_load)
    with pytest.raises(ConfigurationError):
        save_search_settings(settings_file, expression_generation_limit=9, scene_result_limit=9)

    assert _raw(settings_file) == before


def test_saving_the_same_values_leaves_the_file_untouched(tmp_path: Path) -> None:
    settings_file, _ = _settings_with_comments(tmp_path)
    before = _raw(settings_file)

    saved = save_search_settings(
        settings_file, expression_generation_limit=5, scene_result_limit=5
    )

    assert saved.search.scene_result_limit == 5
    assert _raw(settings_file) == before


def test_saving_does_not_create_a_missing_settings_file(tmp_path: Path) -> None:
    missing = tmp_path / "settings.toml"

    with pytest.raises(ConfigurationError, match="찾을 수 없습니다"):
        save_search_settings(missing, expression_generation_limit=5, scene_result_limit=5)

    assert not missing.exists()


def test_saving_keeps_a_legacy_key_line_and_still_ignores_it(tmp_path: Path) -> None:
    """옛 키 줄은 건드리지 않는다. 값은 여전히 승계되지 않는다."""
    work_data_dir = _work_data_dir(tmp_path)
    settings_file = tmp_path / "settings.toml"
    _write_settings(
        settings_file,
        work_data_dir=_toml_string(work_data_dir),
        scene_result_limit=None,
        nadeshiko_take="3",
    )

    saved = save_search_settings(
        settings_file, expression_generation_limit=5, scene_result_limit=8
    )

    assert saved.search.scene_result_limit == 8
    assert "nadeshiko_take = 3" in _raw(settings_file)


def test_saving_never_reads_or_writes_a_dotenv(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """설정 저장은 비밀 파일을 건드리지 않는다."""
    settings_file, _ = _settings_with_comments(tmp_path)
    env_file = tmp_path / ".env"
    env_file.write_text("NADESHIKO_API_KEY=stored-secret\n", encoding="utf-8")
    monkeypatch.delenv("NADESHIKO_API_KEY", raising=False)

    saved = save_search_settings(
        settings_file, expression_generation_limit=6, scene_result_limit=6
    )

    assert env_file.read_text(encoding="utf-8") == "NADESHIKO_API_KEY=stored-secret\n"
    # 저장 결과에도 비밀값 자체는 드러나지 않는다.
    assert "stored-secret" not in repr(saved)
