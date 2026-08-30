"""Instructor와 애플리케이션 AI 설정을 연결한다.

응답을 캐시하지 않는다. 저장할 가치가 있는 결과(표현 자산·장면 번역)는
호출한 쪽이 사용자 작업물로 DB에 저장한다.
"""

from __future__ import annotations

from typing import TypeVar

import instructor
from pydantic import BaseModel

from scene_collector.config import AppSettings

StructuredResponse = TypeVar("StructuredResponse", bound=BaseModel)


class AIError(RuntimeError):
    """AI 호출이 실패했을 때 화면에 보여줄 오류.

    provider나 Instructor가 내는 예외는 종류가 제각각이고 메시지에 모델의 원본
    응답이 실려 오기도 한다. 화면에는 원본을 싣지 않고 이 오류로 바꿔 전달한다.
    원래 예외는 __cause__로 남는다.
    """


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
    """동일한 호출 경로로 서비스의 구조화 응답을 받는다."""
    try:
        client = create_ai_client(settings)
        response = client.create(
            response_model=response_model,
            messages=[{"role": "user", "content": prompt}],
        )
    except Exception as error:  # provider·Instructor 예외는 종류가 정해져 있지 않다
        raise AIError(
            f"AI 응답을 받지 못했습니다 ({type(error).__name__}). "
            "AI 서비스·모델 설정과 API 키, 네트워크 상태를 확인하세요."
        ) from error
    if not isinstance(response, response_model):
        raise TypeError("AI 응답이 요청한 Pydantic 자료형이 아닙니다.")
    return response
