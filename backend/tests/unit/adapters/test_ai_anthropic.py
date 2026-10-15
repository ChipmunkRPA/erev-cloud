"""AIA-04/05 request mapping and failures through mocked SDK clients only."""

from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from erev_api.adapters.ai import anthropic as adapter
from erev_api.adapters.ai.provider import AIRequest, ProviderError
from pydantic import SecretStr
from support import ai_sdk

REQUEST = AIRequest(
    template_id="contract-review",
    template_version=1,
    model="configured-test-model",
    parameters={},
    system="Synthetic system prompt",
    messages=({"role": "user", "content": "Synthetic document"},),
    input_sha256="a" * 64,
    max_tokens=16000,
)


def client_result(*, stop_reason: str | None = "end_turn") -> MagicMock:
    client = MagicMock(spec=adapter.anthropic.Anthropic)
    client.__enter__.return_value = client
    client.messages = MagicMock()
    client.messages.create.return_value = SimpleNamespace(
        content=[
            SimpleNamespace(type="thinking", thinking="excluded"),
            SimpleNamespace(type="text", text="Proposed café "),
            SimpleNamespace(type="text", text="fields"),
        ],
        usage=SimpleNamespace(input_tokens=1200, output_tokens=300),
        model=REQUEST.model,
        stop_reason=stop_reason,
    )
    return client


def test_client_construction(monkeypatch: pytest.MonkeyPatch) -> None:
    constructor = MagicMock()
    monkeypatch.setattr(adapter.anthropic, "Anthropic", constructor)
    store = adapter.ConfiguredAIKey(SecretStr("synthetic-key"))
    adapter.build_client(store)
    constructor.assert_called_once_with(
        api_key="synthetic-key",
        base_url="https://api.anthropic.com",
        timeout=60.0,
        max_retries=0,
        open_telemetry=False,
    )
    assert "synthetic-key" not in repr(store)
    with pytest.raises(KeyError):
        store.get("UNRELATED_SECRET")


def test_request_and_response_mapping() -> None:
    client = client_result()
    ticks = iter((10.0, 10.125))
    result = adapter.AnthropicProvider(lambda: client, monotonic=lambda: next(ticks)).complete(
        REQUEST
    )
    client.messages.create.assert_called_once_with(
        model=REQUEST.model,
        max_tokens=16000,
        system=REQUEST.system,
        messages=list(REQUEST.messages),
    )
    client.__exit__.assert_called_once()
    assert result.text == "Proposed café fields"
    assert result.response_sha256 == sha256(result.text.encode()).hexdigest()
    assert (result.input_tokens, result.output_tokens, result.latency_ms) == (1200, 300, 125)
    assert (result.model, result.stop_reason) == (REQUEST.model, "end_turn")


def test_refusal_stop_reason() -> None:
    client = client_result(stop_reason="refusal")
    assert adapter.AnthropicProvider(lambda: client).complete(REQUEST).stop_reason == "refusal"


@pytest.mark.parametrize(
    ("name", "status", "code", "retryable"),
    [
        ("NotFoundError", 404, "AI_MODEL_NOT_FOUND", False),
        ("RateLimitError", 429, "AI_RATE_LIMIT", True),
        ("InternalServerError", 500, "AI_PROVIDER_UNAVAILABLE", True),
        ("BadRequestError", 400, "AI_BAD_REQUEST", False),
        ("AuthenticationError", 401, "AI_AUTHENTICATION", False),
        ("PermissionDeniedError", 403, "AI_PERMISSION", False),
        ("UnprocessableEntityError", 422, "AI_PROVIDER_ERROR", False),
        ("APITimeoutError", 0, "AI_TIMEOUT", True),
        ("APIConnectionError", 0, "AI_CONNECTION", True),
    ],
)
def test_exception_classification(name: str, status: int, code: str, retryable: bool) -> None:
    kind = getattr(adapter.anthropic, name)
    error = (
        kind("sensitive provider detail", response=ai_sdk.response(status), body={})
        if status
        else kind(request=ai_sdk.request())
    )
    client = client_result()
    client.messages.create.side_effect = error
    with pytest.raises(ProviderError) as caught:
        adapter.AnthropicProvider(lambda: client).complete(REQUEST)
    assert caught.value.code == code
    assert caught.value.retryable is retryable
    assert str(caught.value) == code
    assert caught.value.__suppress_context__
    client.messages.create.assert_called_once()
    client.__exit__.assert_called_once()


def test_unexpected_failure_is_not_misclassified() -> None:
    client = client_result()
    client.messages.create.side_effect = ValueError("programming failure")
    with pytest.raises(ValueError, match="programming failure"):
        adapter.AnthropicProvider(lambda: client).complete(REQUEST)
    client.__exit__.assert_called_once()


def test_missing_stop_reason_is_refused() -> None:
    client = client_result(stop_reason=None)
    with pytest.raises(ProviderError, match="AI_INVALID_RESPONSE"):
        adapter.AnthropicProvider(lambda: client).complete(REQUEST)


@pytest.mark.parametrize("message", [{"role": "system", "content": "x"}, {"role": "user"}])
def test_invalid_message_does_not_construct_client(message: dict[str, str]) -> None:
    factory = MagicMock()
    with pytest.raises(ValueError):
        adapter.AnthropicProvider(factory).complete(replace(REQUEST, messages=(message,)))
    factory.assert_not_called()
