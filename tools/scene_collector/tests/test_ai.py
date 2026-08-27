from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel, ValidationError

import scene_collector.ai as ai_module
from scene_collector.ai import create_structured_response
from scene_collector.config import AISettings, AppSettings, StorageSettings


class ConnectivityProbe(BaseModel):
    text: str
    number: int


def _settings(work_data_dir: Path, *, service: str, model: str) -> AppSettings:
    return AppSettings(
        storage=StorageSettings(work_data_dir=work_data_dir),
        ai=AISettings(service=service, model=model),
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
