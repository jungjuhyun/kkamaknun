"""로컬 설정 파일과 비밀정보를 검증해 읽는다."""

import os
import tomllib
from pathlib import Path

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    ValidationError,
    field_validator,
    model_validator,
)
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    TomlConfigSettingsSource,
)
from pydantic_settings import SettingsError as PydanticSettingsError

DEFAULT_SETTINGS_FILE = Path("settings.toml")


class ConfigurationError(ValueError):
    """설정 파일이나 설정값이 올바르지 않을 때 발생한다."""


class StorageSettings(BaseModel):
    """사용자가 지정하는 작업 데이터 위치."""

    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    work_data_dir: Path

    @field_validator("work_data_dir", mode="before")
    @classmethod
    def reject_empty_work_data_dir(cls, value: object) -> object:
        if not isinstance(value, (str, Path)):
            raise ValueError("작업 데이터 위치는 경로 문자열이어야 합니다.")
        if isinstance(value, str) and not value.strip():
            raise ValueError("작업 데이터 위치를 입력해야 합니다.")
        return value.strip() if isinstance(value, str) else value

    @field_validator("work_data_dir")
    @classmethod
    def validate_work_data_dir(cls, value: Path) -> Path:
        if not value.is_absolute():
            raise ValueError("작업 데이터 위치는 절대경로여야 합니다.")
        try:
            if not value.exists():
                raise ValueError("작업 데이터 위치가 존재하지 않습니다.")
            if not value.is_dir():
                raise ValueError("작업 데이터 위치는 디렉터리여야 합니다.")
        except OSError as error:
            raise ValueError("작업 데이터 위치를 확인할 수 없습니다.") from error
        return value


class AISettings(BaseModel):
    """나중의 AI 연결에서 사용할 서비스와 모델 식별자."""

    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    service: str
    model: str

    @field_validator("service", "model", mode="before")
    @classmethod
    def validate_required_text(cls, value: object) -> str:
        if not isinstance(value, str):
            raise ValueError("문자열이어야 합니다.")
        if not value.strip():
            raise ValueError("비어 있을 수 없습니다.")
        return value.strip()


#: 의미가 달라져 값을 승계하지 않는 옛 검색 설정 키.
LEGACY_SEARCH_KEYS = ("candidate_count", "nadeshiko_take")


class SearchSettings(BaseModel):
    """일본어 표현 생성 상한과 화면에 표시할 장면 수."""

    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    expression_generation_limit: int = Field(default=20, strict=True, ge=1, le=20)
    """AI가 한 번에 만들 표현 수의 상한."""

    scene_result_limit: int = Field(default=5, strict=True, ge=1, le=20)
    """정확 일치로 판정된 장면을 화면에 몇 개까지 보여줄지.

    이 수는 API에서 한 번에 받아올 후보 수가 아니다. 검색은 이 수를 채울 때까지
    다음 페이지를 넘겨 가며 후보를 훑고, 채우면 즉시 멈춘다.
    """

    @model_validator(mode="before")
    @classmethod
    def ignore_legacy_search_keys(cls, data: object) -> object:
        """옛 검색 키는 의미가 달라졌으므로 값을 승계하지 않고 무시한다.

        `candidate_count`는 표현 생성 상한으로, `nadeshiko_take`는 표시할 장면
        수로 뜻이 바뀌었다. 구 설정 파일이 오류를 내지 않게 키만 받아 버리고
        새 설정값 또는 기본값을 쓴다.
        """
        if isinstance(data, dict) and any(key in data for key in LEGACY_SEARCH_KEYS):
            return {key: value for key, value in data.items() if key not in LEGACY_SEARCH_KEYS}
        return data


class AppSettings(BaseSettings):
    """장면 수집기의 현재 설정 자료형."""

    model_config = SettingsConfigDict(
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        env_prefix="SCENE_COLLECTOR_",
        extra="forbid",
        hide_input_in_errors=True,
    )

    storage: StorageSettings
    ai: AISettings
    search: SearchSettings
    nadeshiko_api_key: SecretStr | None = Field(
        default=None,
        validation_alias="NADESHIKO_API_KEY",
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            TomlConfigSettingsSource(settings_cls),
            file_secret_settings,
        )


def load_settings(
    settings_file: str | Path = DEFAULT_SETTINGS_FILE,
    *,
    env_file: str | Path | None = None,
) -> AppSettings:
    """TOML 설정과 같은 위치의 선택적 dotenv 비밀정보를 읽는다."""
    try:
        settings_path = Path(settings_file).expanduser().resolve()
    except (OSError, RuntimeError) as error:
        raise ConfigurationError("설정 파일 경로가 올바르지 않습니다.") from error

    if not settings_path.exists():
        raise ConfigurationError(f"설정 파일을 찾을 수 없습니다: {settings_path}")
    if not settings_path.is_file():
        raise ConfigurationError(f"설정 파일 경로가 파일이 아닙니다: {settings_path}")

    dotenv_path = _resolve_env_file(settings_path, env_file)
    configured_settings = _settings_type(settings_path)

    try:
        return configured_settings(_env_file=dotenv_path)
    except tomllib.TOMLDecodeError as error:
        raise ConfigurationError(f"설정 파일 형식이 올바르지 않습니다: {error}") from error
    except ValidationError as error:
        raise ConfigurationError(_format_validation_error(error)) from error
    except (OSError, PydanticSettingsError) as error:
        raise ConfigurationError(f"설정 파일을 읽을 수 없습니다: {error}") from error


def atomic_write_text(path: Path, content: str, *, encoding: str = "utf-8") -> None:
    """임시 파일에 쓴 뒤 원자적으로 교체한다. 중간에 실패해도 원본이 남는다."""
    temp_path = path.with_name(path.name + ".tmp")
    try:
        temp_path.write_text(content, encoding=encoding, newline="")
        os.replace(temp_path, path)
    finally:
        temp_path.unlink(missing_ok=True)


def save_search_settings(
    settings_file: str | Path,
    *,
    expression_generation_limit: int,
    scene_result_limit: int,
    env_file: str | Path | None = None,
) -> AppSettings:
    """설정 파일의 [search] 값 두 개만 바꿔 저장하고 다시 읽어 돌려준다.

    알려진 키의 값 줄만 바꾸고 다른 값·섹션·주석·줄바꿈 문자는 그대로 둔다.
    사용자가 손으로 편집하는 파일이라 전체를 다시 쓰지 않는다.

    저장 뒤 다시 읽지 못하면 원본 원문을 되돌린다.
    """
    path = Path(settings_file).expanduser().resolve()
    if not path.is_file():
        raise ConfigurationError(f"설정 파일을 찾을 수 없습니다: {path}")

    # 값 검증을 먼저 해서 잘못된 값이면 파일을 열지도 않는다.
    try:
        SearchSettings(
            expression_generation_limit=expression_generation_limit,
            scene_result_limit=scene_result_limit,
        )
    except ValidationError as error:
        raise ConfigurationError(_format_validation_error(error)) from error

    original = _read_preserving_newlines(path)
    updated = _replace_table_values(
        original,
        "search",
        {
            "expression_generation_limit": expression_generation_limit,
            "scene_result_limit": scene_result_limit,
        },
    )

    if updated == original:
        return load_settings(path, env_file=env_file)

    atomic_write_text(path, updated)
    try:
        reloaded = load_settings(path, env_file=env_file)
    except ConfigurationError:
        atomic_write_text(path, original)
        raise

    if (
        reloaded.search.expression_generation_limit != expression_generation_limit
        or reloaded.search.scene_result_limit != scene_result_limit
    ):
        # 파일은 제대로 저장됐지만 환경변수가 그 값을 덮어쓰고 있다.
        # 원본을 되돌리면 오히려 사용자 설정을 잃으므로 그대로 두고 사실만 알린다.
        raise ConfigurationError(
            "설정 파일에는 저장했지만 환경변수가 그 값을 덮어쓰고 있어 적용되지 않습니다. "
            "SCENE_COLLECTOR_로 시작하는 환경변수를 확인하세요."
        )
    return reloaded


def _read_preserving_newlines(path: Path) -> str:
    """줄바꿈 문자를 바꾸지 않고 읽는다.

    Path.read_text에는 newline 인자가 없어 CRLF가 LF로 번역된다. 그대로 되쓰면
    값 두 개만 바꾸려다 파일 전체 줄바꿈이 조용히 바뀐다.
    """
    try:
        with path.open("r", encoding="utf-8", newline="") as file:
            return file.read()
    except OSError as error:
        raise ConfigurationError(f"설정 파일을 읽을 수 없습니다: {error}") from error


def _replace_table_values(source: str, table: str, values: dict[str, int]) -> str:
    """TOML 원문에서 지정한 표의 알려진 키 값 줄만 바꾼다.

    구조가 조금이라도 애매하면 추측하지 않고 거절한다. 사용자가 직접 쓴 설정
    파일을 잘못 고치는 것보다 저장을 거절하는 편이 낫다.
    """
    if '"""' in source or "'''" in source:
        raise ConfigurationError(
            "여러 줄 문자열이 있는 설정 파일은 화면에서 저장할 수 없습니다. "
            "파일을 직접 수정하세요."
        )

    lines = source.splitlines(keepends=True)
    current_table = ""
    positions: dict[str, int] = {}
    table_end = len(lines)
    seen_table = False

    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("[["):
            current_table = ""  # 표 배열은 다루지 않는다.
            if seen_table and table_end == len(lines):
                table_end = index
            continue
        if stripped.startswith("["):
            if seen_table and table_end == len(lines):
                table_end = index
            current_table = stripped.strip("[]").strip()
            if current_table == table:
                seen_table = True
            continue
        name = stripped.partition("=")[0].strip()
        if current_table == "" and (name == table or name.startswith(f"{table}.")):
            raise ConfigurationError(
                "점 표기나 inline table로 쓴 설정은 화면에서 저장할 수 없습니다. "
                "파일을 직접 수정하세요."
            )
        if current_table != table or name not in values:
            continue
        if name in positions:
            raise ConfigurationError(
                f"설정 파일에 {name} 항목이 여러 번 있습니다. 파일을 직접 수정하세요."
            )
        positions[name] = index

    line_ending = "\r\n" if "\r\n" in source else "\n"
    updated = list(lines)
    for name, index in positions.items():
        original_line = updated[index]
        indent = original_line[: len(original_line) - len(original_line.lstrip())]
        ending = "\r\n" if original_line.endswith("\r\n") else "\n"
        updated[index] = f"{indent}{name} = {values[name]}{ending}"

    missing = [name for name in values if name not in positions]
    if not missing:
        return "".join(updated)

    added = [f"{name} = {values[name]}{line_ending}" for name in missing]
    if not seen_table:
        # 표 자체가 없으면 파일 끝에 새로 만든다.
        prefix = "" if not updated or updated[-1].endswith(("\n", "\r")) else line_ending
        return "".join(updated) + prefix + f"[{table}]{line_ending}" + "".join(added)
    return "".join(updated[:table_end]) + "".join(added) + "".join(updated[table_end:])


def _resolve_env_file(settings_path: Path, env_file: str | Path | None) -> Path:
    if env_file is None:
        return settings_path.with_name(".env")

    dotenv_path = Path(env_file).expanduser()
    if not dotenv_path.is_absolute():
        dotenv_path = settings_path.parent / dotenv_path
    return dotenv_path.resolve()


def _settings_type(settings_path: Path) -> type[AppSettings]:
    configured_model = AppSettings.model_config | {"toml_file": settings_path}

    class ConfiguredAppSettings(AppSettings):
        model_config = SettingsConfigDict(**configured_model)

    return ConfiguredAppSettings


def _format_validation_error(error: ValidationError) -> str:
    issues = []
    for detail in error.errors(include_url=False, include_context=False, include_input=False):
        location = ".".join(str(part) for part in detail["loc"]) or "settings"
        issues.append(f"{location}: {detail['msg']}")
    return "설정이 올바르지 않습니다.\n- " + "\n- ".join(issues)
