"""Official provider adapter (05 AIA-04/05); jobs own retries and retained evidence."""

from __future__ import annotations

import re
from collections.abc import Callable
from hashlib import sha256
from typing import cast

import anthropic as anthropic
from pydantic import SecretStr

from erev_api.adapters.ai.provider import AIRequest, AIResponse, AIUsage, ProviderError
from erev_api.adapters.secrets.store import SecretStore
from erev_api.clock import monotonic as monotonic_seconds


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


def _reported_usage(value: object) -> AIUsage:
    # Cache counters are separate input components, not subsets of input_tokens.
    # Optional absent/null cache counts mean no cache usage. Required counts never
    # default to zero, and any malformed component makes the complete total unknown.
    counters = [getattr(value, "input_tokens", None), getattr(value, "output_tokens", None)]
    for name in ("cache_creation_input_tokens", "cache_read_input_tokens"):
        cached = getattr(value, name, None)
        counters.append(0 if cached is None else cached)
    if any(type(count) is not int or not 0 <= count <= 2147483647 for count in counters):
        raise ProviderError("AI_INVALID_RESPONSE", retryable=False)
    validated = cast(list[int], counters)
    total_input = validated[0] + validated[2] + validated[3]
    if total_input > 2147483647:
        raise ProviderError("AI_INVALID_RESPONSE", retryable=False)
    return AIUsage(total_input, validated[1])


class AnthropicProvider:
    def __init__(
        self,
        client_factory: Callable[[], anthropic.Anthropic],
        *,
        monotonic: Callable[[], float] = monotonic_seconds,
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
        usage = _reported_usage(getattr(response, "usage", None))
        try:
            if (
                not isinstance(response.stop_reason, str)
                or not response.stop_reason
                or not isinstance(response.model, str)
                or re.fullmatch(r"[A-Za-z0-9._:-]{1,256}", response.model) is None
            ):
                raise ValueError("invalid response metadata")
            text = "".join(block.text for block in response.content if block.type == "text")
            digest = sha256(text.encode("utf-8")).hexdigest()
        except (AttributeError, TypeError, ValueError, UnicodeEncodeError):
            # A malformed result does not erase valid provider-reported usage.
            raise ProviderError("AI_INVALID_RESPONSE", retryable=False, usage=usage) from None
        return AIResponse(
            text=text,
            response_sha256=digest,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            latency_ms=max(0, round((self._monotonic() - started) * 1000)),
            model=response.model,
            stop_reason=response.stop_reason,
        )
