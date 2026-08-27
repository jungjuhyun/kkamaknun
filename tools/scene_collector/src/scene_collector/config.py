"""로컬 설정 파일과 비밀정보를 검증해 읽는다."""

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, SecretStr, ValidationError, field_validator
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


class SearchSettings(BaseModel):
    """표현 후보 생성과 Nadeshiko 1회 검색 범위."""

    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    candidate_count: int = Field(strict=True, ge=3, le=5)
    nadeshiko_take: int = Field(strict=True, ge=1, le=20)


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
    except ValidationError as error:
        raise ConfigurationError(_format_validation_error(error)) from error
    except (OSError, PydanticSettingsError) as error:
        raise ConfigurationError(f"설정 파일을 읽을 수 없습니다: {error}") from error


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
