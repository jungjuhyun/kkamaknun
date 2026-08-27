"""Instructor와 애플리케이션 AI 설정을 연결한다."""

from typing import TypeVar

import instructor
from pydantic import BaseModel

from scene_collector.config import AppSettings

StructuredResponse = TypeVar("StructuredResponse", bound=BaseModel)


def create_ai_client(settings: AppSettings) -> instructor.Instructor:
    """설정의 서비스와 모델로 동기 Instructor 클라이언트를 만든다."""
    provider_model = f"{settings.ai.service}/{settings.ai.model}"
    return instructor.from_provider(provider_model)


def create_structured_response(
    settings: AppSettings,
    *,
    prompt: str,
    response_model: type[StructuredResponse],
) -> StructuredResponse:
    """동일한 호출 경로로 provider의 구조화 응답을 받는다."""
    client = create_ai_client(settings)
    response = client.create(
        response_model=response_model,
        messages=[{"role": "user", "content": prompt}],
    )
    if not isinstance(response, response_model):
        raise TypeError("AI 응답이 요청한 Pydantic 자료형이 아닙니다.")
    return response
