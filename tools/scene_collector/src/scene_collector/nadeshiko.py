"""공식 Nadeshiko SDK를 애플리케이션 설정에 연결한다."""

from nadeshiko import Nadeshiko

from scene_collector.config import AppSettings, ConfigurationError


def create_nadeshiko_client(settings: AppSettings) -> Nadeshiko:
    """검증된 설정의 API 키로 공식 SDK 클라이언트를 만든다."""
    secret = settings.nadeshiko_api_key
    if secret is None or not secret.get_secret_value().strip():
        raise ConfigurationError(
            "Nadeshiko 연결에는 .env 또는 환경변수의 NADESHIKO_API_KEY가 필요합니다."
        )

    return Nadeshiko(api_key=secret.get_secret_value().strip())
