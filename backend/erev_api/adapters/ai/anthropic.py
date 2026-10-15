"""Official provider adapter (05 AIA-04/05); jobs own retries and retained evidence."""

from __future__ import annotations

import time
from collections.abc import Callable
from hashlib import sha256
from typing import cast

import anthropic as anthropic
from pydantic import SecretStr

from erev_api.adapters.ai.provider import AIRequest, AIResponse, ProviderError
from erev_api.adapters.secrets.store import SecretStore


class ConfiguredAIKey:
    """Expose only the configured AI key through the secret-store boundary."""

    def __init__(self, key: SecretStr) -> None:
        self._key = key

    def get(self, name: str) -> SecretStr:
        if name != "ANTHROPIC_API_KEY":
            raise KeyError(name)
        return self._key


def build_client(store: SecretStore) -> anthropic.Anthropic:
    """Resolve KEY-10 lazily. No SDK retries or prompt/completion telemetry."""
    return anthropic.Anthropic(
        api_key=store.get("ANTHROPIC_API_KEY").get_secret_value(),
        base_url="https://api.anthropic.com",
        timeout=60.0,
        max_retries=0,
        open_telemetry=False,
    )


class AnthropicProvider:
    def __init__(
        self,
        client_factory: Callable[[], anthropic.Anthropic],
        *,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._client_factory = client_factory
        self._monotonic = monotonic

    def complete(self, request: AIRequest) -> AIResponse:
        messages: list[anthropic.types.MessageParam] = []
        for message in request.messages:
            if set(message) != {"role", "content"} or message["role"] not in {"user", "assistant"}:
                raise ValueError("AI messages require a user/assistant role and text content")
            messages.append(cast(anthropic.types.MessageParam, dict(message)))
        started = self._monotonic()
        try:
            with self._client_factory() as client:
                response = client.messages.create(
                    model=request.model,
                    max_tokens=request.max_tokens,
                    system=request.system,
                    messages=messages,
                )
        except anthropic.NotFoundError:
            raise ProviderError("AI_MODEL_NOT_FOUND", retryable=False) from None
        except anthropic.APITimeoutError:
            raise ProviderError("AI_TIMEOUT", retryable=True) from None
        except anthropic.RateLimitError:
            raise ProviderError("AI_RATE_LIMIT", retryable=True) from None
        except anthropic.InternalServerError:
            raise ProviderError("AI_PROVIDER_UNAVAILABLE", retryable=True) from None
        except anthropic.APIConnectionError:
            raise ProviderError("AI_CONNECTION", retryable=True) from None
        except anthropic.BadRequestError:
            raise ProviderError("AI_BAD_REQUEST", retryable=False) from None
        except anthropic.AuthenticationError:
            raise ProviderError("AI_AUTHENTICATION", retryable=False) from None
        except anthropic.PermissionDeniedError:
            raise ProviderError("AI_PERMISSION", retryable=False) from None
        except anthropic.APIError:
            raise ProviderError("AI_PROVIDER_ERROR", retryable=False) from None
        if response.stop_reason is None:
            raise ProviderError("AI_INVALID_RESPONSE", retryable=False)
        text = "".join(block.text for block in response.content if block.type == "text")
        return AIResponse(
            text=text,
            response_sha256=sha256(text.encode("utf-8")).hexdigest(),
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            latency_ms=max(0, round((self._monotonic() - started) * 1000)),
            model=response.model,
            stop_reason=response.stop_reason,
        )
