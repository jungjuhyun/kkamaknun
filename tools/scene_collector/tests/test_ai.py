from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel, ValidationError

import scene_collector.ai as ai_module
from scene_collector.ai import create_structured_response
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

    with pytest.raises(ValidationError):
        create_structured_response(
            _settings(tmp_path, service="provider-one", model="model-one"),
            prompt="Return the neutral connectivity probe.",
            response_model=ConnectivityProbe,
        )


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
