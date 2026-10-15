"""Provider-independent AI request, response and failure contracts (DG §6.7).

Adapters re-export these binding names; domain code never imports a network adapter.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class AIRequest:
    template_id: str
    template_version: int
    model: str
    parameters: Mapping[str, Any]
    system: str
    messages: tuple[Mapping[str, str], ...]
    input_sha256: str
    max_tokens: int


@dataclass(frozen=True, slots=True)
class AIResponse:
    text: str
    response_sha256: str
    input_tokens: int
    output_tokens: int
    latency_ms: int
    model: str
    stop_reason: str


class AIProvider(Protocol):
    def complete(self, request: AIRequest) -> AIResponse: ...


class ProviderError(RuntimeError):
    """A safe error code for gateway evidence; never retain the SDK response body."""

    def __init__(self, code: str, *, retryable: bool) -> None:
        super().__init__(code)
        self.code = code
        self.retryable = retryable
