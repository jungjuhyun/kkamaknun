"""Instructor와 애플리케이션 AI 설정을 연결한다."""

from __future__ import annotations

from typing import TYPE_CHECKING, TypeVar

import instructor
from pydantic import BaseModel

from scene_collector.config import AppSettings

if TYPE_CHECKING:
    from scene_collector.database import SceneCollectorDatabase

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
    cache: SceneCollectorDatabase | None = None,
    instruction_version: str | None = None,
) -> StructuredResponse:
    """동일한 호출 경로로 provider의 구조화 응답을 받는다."""
    cache_input = {
        "messages": [{"role": "user", "content": prompt}],
        "response_model": response_model.model_json_schema(),
    }
    if cache is not None:
        if instruction_version is None or not instruction_version.strip():
            raise ValueError("AI cache에는 비어 있지 않은 지시문 version이 필요합니다.")
        cached = cache.get_ai_cache(
            service=settings.ai.service,
            model=settings.ai.model,
            instruction_version=instruction_version,
            input_content=cache_input,
            response_model=response_model,
        )
        if cached is not None:
            return cached

    client = create_ai_client(settings)
    response = client.create(
        response_model=response_model,
        messages=cache_input["messages"],
    )
    if not isinstance(response, response_model):
        raise TypeError("AI 응답이 요청한 Pydantic 자료형이 아닙니다.")
    if cache is not None:
        cache.put_ai_cache(
            service=settings.ai.service,
            model=settings.ai.model,
            instruction_version=instruction_version,
            input_content=cache_input,
            response=response,
        )
    return response
