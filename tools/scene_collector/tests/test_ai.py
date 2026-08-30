from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel, ValidationError

import scene_collector.ai as ai_module
from scene_collector.ai import AIError, create_structured_response
from scene_collector.config import AISettings, AppSettings, SearchSettings, StorageSettings
from scene_collector.models import (
    EXPRESSION_GENERATION_HARD_LIMIT,
    ExpressionCandidate,
    GeneratedExpressions,
)


class ConnectivityProbe(BaseModel):
    text: str
    number: int


def _candidates(count: int) -> list[ExpressionCandidate]:
    return [
        ExpressionCandidate(
            japanese=f"表現{index}",
            reading=f"よみかた{index}",
            meaning_ko=f"의미 {index}",
            register=f"말투 {index}",
        )
        for index in range(1, count + 1)
    ]


def _settings(work_data_dir: Path, *, service: str, model: str) -> AppSettings:
    return AppSettings(
        storage=StorageSettings(work_data_dir=work_data_dir),
        ai=AISettings(service=service, model=model),
        search=SearchSettings(expression_generation_limit=5, nadeshiko_take=5),
    )


def test_switches_provider_and_model_only_through_settings(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider_models: list[str] = []
    requests: list[tuple[type[BaseModel], list[dict[str, str]]]] = []

    class FakeClient:
        def create(
            self,
            *,
            response_model: type[BaseModel],
            messages: list[dict[str, str]],
        ) -> BaseModel:
            requests.append((response_model, messages))
            return response_model.model_validate({"text": "connection-ok", "number": 7})

    def fake_from_provider(provider_model: str) -> FakeClient:
        provider_models.append(provider_model)
        return FakeClient()

    monkeypatch.setattr(ai_module.instructor, "from_provider", fake_from_provider)
    prompt = "Return the neutral connectivity probe."

    results = [
        create_structured_response(
            _settings(tmp_path, service=service, model=model),
            prompt=prompt,
            response_model=ConnectivityProbe,
        )
        for service, model in (("provider-one", "model-one"), ("provider-two", "model-two"))
    ]

    assert provider_models == ["provider-one/model-one", "provider-two/model-two"]
    assert requests == [
        (ConnectivityProbe, [{"role": "user", "content": prompt}]),
        (ConnectivityProbe, [{"role": "user", "content": prompt}]),
    ]
    assert all(result == ConnectivityProbe(text="connection-ok", number=7) for result in results)
    assert all(type(result.number) is int for result in results)


def test_response_model_rejects_invalid_structured_data(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class InvalidFakeClient:
        def create(self, **kwargs: Any) -> BaseModel:
            response_model = kwargs["response_model"]
            return response_model.model_validate({"text": "connection-ok", "number": "not-an-int"})

    monkeypatch.setattr(ai_module.instructor, "from_provider", lambda _: InvalidFakeClient())

    # 화면에는 AIError로만 전달하고, 원본 응답이 실린 예외는 __cause__로만 남긴다.
    with pytest.raises(AIError) as failure:
        create_structured_response(
            _settings(tmp_path, service="provider-one", model="model-one"),
            prompt="Return the neutral connectivity probe.",
            response_model=ConnectivityProbe,
        )
    assert isinstance(failure.value.__cause__, ValidationError)
    assert "not-an-int" not in str(failure.value)


def test_provider_failure_is_reported_as_a_user_facing_ai_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """provider가 어떤 예외를 내든 화면이 잡을 수 있는 오류로 바꾼다.

    instructor나 provider의 예외는 RuntimeError도 ValueError도 아닐 수 있어서,
    그대로 두면 화면의 오류 처리에 걸리지 않고 상태 표시가 멈춘 채로 남는다.
    """

    class ProviderSpecificError(Exception):
        """instructor·openai가 내는 자체 예외처럼 표준 예외 계층 밖에 있는 오류."""

    def explode(_: str) -> object:
        raise ProviderSpecificError("응답 원본이 실려 있을 수 있는 메시지")

    monkeypatch.setattr(ai_module.instructor, "from_provider", explode)

    with pytest.raises(AIError) as failure:
        create_structured_response(
            _settings(tmp_path, service="provider-one", model="model-one"),
            prompt="Return the neutral connectivity probe.",
            response_model=ConnectivityProbe,
        )
    # app이 잡는 오류 갈래에 들어가야 화면에 표시된다.
    assert isinstance(failure.value, RuntimeError)
    assert isinstance(failure.value.__cause__, ProviderSpecificError)
    assert "ProviderSpecificError" in str(failure.value)
    assert "응답 원본이 실려 있을 수 있는 메시지" not in str(failure.value)


def test_rejects_response_of_unrequested_type(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """요청한 자료형이 아닌 응답은 그대로 통과시키지 않는다."""

    class OtherModel(BaseModel):
        text: str

    class WrongTypeFakeClient:
        def create(self, **kwargs: Any) -> BaseModel:
            return OtherModel(text="connection-ok")

    monkeypatch.setattr(ai_module.instructor, "from_provider", lambda _: WrongTypeFakeClient())

    with pytest.raises(TypeError, match="Pydantic 자료형"):
        create_structured_response(
            _settings(tmp_path, service="provider-one", model="model-one"),
            prompt="Return the neutral connectivity probe.",
            response_model=ConnectivityProbe,
        )


def test_generated_expressions_accepts_an_empty_list() -> None:
    """더 붙일 표현이 없다는 응답은 오류가 아니라 정상 결과다."""
    assert GeneratedExpressions(expressions=[]).expressions == []
    assert GeneratedExpressions.model_validate({"expressions": []}).expressions == []


def test_generated_expressions_keeps_the_upper_bound() -> None:
    """하한만 사라졌고 상한 20개는 그대로다."""
    assert EXPRESSION_GENERATION_HARD_LIMIT == 20
    assert len(GeneratedExpressions(expressions=_candidates(20)).expressions) == 20

    with pytest.raises(ValidationError):
        GeneratedExpressions(expressions=_candidates(21))


def test_structured_response_passes_an_empty_expression_list_through(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AI가 빈 표현 목록을 돌려줘도 구조화 응답 경로가 막지 않는다."""

    class EmptyExpressionsClient:
        def create(self, **kwargs: Any) -> BaseModel:
            return kwargs["response_model"].model_validate({"expressions": []})

    monkeypatch.setattr(ai_module.instructor, "from_provider", lambda _: EmptyExpressionsClient())

    result = create_structured_response(
        _settings(tmp_path, service="provider-one", model="model-one"),
        prompt="이미 저장된 표현 외에 덧붙일 표현을 만들어 주세요.",
        response_model=GeneratedExpressions,
    )

    assert result.expressions == []
