"""AI provider boundary and deterministic fixtures (DG-AI-02; 05 AIA-01, AIA-03).

This adapter performs no database writes. Gateway/job integration and the live
provider are separate work; a fixture result is never an accepted accounting input.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
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
