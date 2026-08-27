"""장면 수집기 로컬 설정 로딩과 검증."""

from pathlib import Path
from typing import Annotated

from pydantic import (
    BaseModel,
    Field,
    SecretStr,
    StringConstraints,
    ValidationError,
    field_validator,
)
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    TomlConfigSettingsSource,
)

NonEmptyStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class SettingsLoadError(ValueError):
    """사용자가 수정할 수 있는 설정 오류."""


class StorageSettings(BaseModel):
    """영구 작업 자료 위치 설정."""

    work_data_dir: Path

    @field_validator("work_data_dir", mode="before")
    @classmethod
    def reject_blank_work_data_dir(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            raise ValueError("작업 데이터 위치를 비워둘 수 없습니다.")
        return value


class AISettings(BaseModel):
    """선택한 AI 서비스와 모델 설정."""

    service: NonEmptyStr
    model: NonEmptyStr


class AppSettings(BaseSettings):
    """장면 수집기 실행 설정."""

    storage: StorageSettings
    ai: AISettings
    nadeshiko_api_key: SecretStr | None = Field(
        default=None,
        validation_alias="NADESHIKO_API_KEY",
    )

    model_config = SettingsConfigDict(
        env_prefix="SCENE_COLLECTOR_",
        env_nested_delimiter="__",
        env_file_encoding="utf-8",
        extra="forbid",
        populate_by_name=True,
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
    settings_path: str | Path = "settings.toml",
    env_file: str | Path | None = ".env",
) -> AppSettings:
    """TOML 설정을 읽고 환경변수와 dotenv 값으로 필요한 항목을 덮어쓴다."""

    resolved_settings_path = Path(settings_path)
    if not resolved_settings_path.is_file():
        raise SettingsLoadError(f"설정 파일을 찾을 수 없습니다: {resolved_settings_path}")

    runtime_config = {**AppSettings.model_config, "toml_file": resolved_settings_path}

    class RuntimeSettings(AppSettings):
        model_config = SettingsConfigDict(**runtime_config)

    try:
        return RuntimeSettings(_env_file=env_file, _env_file_encoding="utf-8")
    except ValidationError as exc:
        problems = "; ".join(
            f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}"
            for error in exc.errors()
        )
        raise SettingsLoadError(
            f"설정이 올바르지 않습니다 ({resolved_settings_path}): {problems}"
        ) from exc
