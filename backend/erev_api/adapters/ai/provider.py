"""AI provider boundary and deterministic fixtures (DG-AI-02; 05 AIA-01, AIA-03).

This adapter performs no database writes. Gateway/job integration remains separate
work; a fixture result is never an accepted accounting input.
"""

from __future__ import annotations

import json
import re
from hashlib import sha256
from pathlib import Path
from typing import TYPE_CHECKING

from erev_api.domain.ai.ports import (
    AIProvider as AIProvider,
)
from erev_api.domain.ai.ports import (
    AIRequest as AIRequest,
)
from erev_api.domain.ai.ports import (
    AIResponse as AIResponse,
)
from erev_api.domain.ai.ports import (
    AIUsage as AIUsage,
)
from erev_api.domain.ai.ports import (
    ProviderError as ProviderError,
)

if TYPE_CHECKING:
    from erev_api.config import Settings


class FakeProvider:
    """Read an exact input fixture, or the template/version's explicit default.

    Fixtures contain text, input_tokens, output_tokens, latency_ms and stop_reason.
    The model comes from the request and the response digest from the exact UTF-8
    text, so neither can be accidentally stale in a fixture. No network or sleep.
    """

    def __init__(self, fixture_root: Path | None = None) -> None:
        self.fixture_root = (
            fixture_root
            if fixture_root is not None
            else Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "ai"
        )

    def complete(self, request: AIRequest) -> AIResponse:
        # Identifiers select files; never allow prompt data to become a path.
        if re.fullmatch(r"[a-z][a-z0-9-]*", request.template_id) is None:
            raise ValueError("Invalid AI fixture template identifier")
        if type(request.template_version) is not int or request.template_version < 1:
            raise ValueError("AI fixture template version must be a positive integer")
        if re.fullmatch(r"[0-9a-f]{64}", request.input_sha256) is None:
            raise ValueError("AI fixture input digest must be lowercase SHA-256")
        directory = self.fixture_root / request.template_id / f"v{request.template_version}"
        exact = directory / f"{request.input_sha256}.json"
        try:
            raw = exact.read_text(encoding="utf-8")
        except FileNotFoundError:
            raw = (directory / "default.json").read_text(encoding="utf-8")
        value = json.loads(raw)
        fields = {"text", "input_tokens", "output_tokens", "latency_ms", "stop_reason"}
        if not isinstance(value, dict) or set(value) != fields:
            raise ValueError("Invalid AI fixture response fields")
        for name in ("text", "stop_reason"):
            if not isinstance(value[name], str):
                raise ValueError(f"AI fixture {name} must be text")
        for name in ("input_tokens", "output_tokens", "latency_ms"):
            if type(value[name]) is not int or value[name] < 0:
                raise ValueError(f"AI fixture {name} must be a nonnegative integer")
        return AIResponse(
            text=value["text"],
            response_sha256=sha256(value["text"].encode("utf-8")).hexdigest(),
            input_tokens=value["input_tokens"],
            output_tokens=value["output_tokens"],
            latency_ms=value["latency_ms"],
            model=request.model,
            stop_reason=value["stop_reason"],
        )


def get_provider(settings: Settings, *, tenant_ai_enabled: bool) -> AIProvider | None:
    """Disabled means no provider construction or secret resolution (DG-AI-01)."""
    if settings.ai_kill_switch or not tenant_ai_enabled:
        return None
    if settings.ai_provider == "fake":
        return FakeProvider()
    from erev_api.adapters.ai.anthropic import AnthropicProvider, ConfiguredAIKey, build_client

    if settings.anthropic_api_key is None:
        raise ValueError("ANTHROPIC_API_KEY is required for the configured AI provider")
    store = ConfiguredAIKey(settings.anthropic_api_key)
    return AnthropicProvider(lambda: build_client(store))
