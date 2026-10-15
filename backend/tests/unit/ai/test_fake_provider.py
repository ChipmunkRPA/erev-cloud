"""Deterministic AI fixtures, with exact-input precedence and no external work."""

from __future__ import annotations

import json
import time
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from typing import Any

import pytest
from erev_api.adapters.ai.provider import AIProvider, AIRequest, FakeProvider

REQUEST = AIRequest(
    template_id="contract-review",
    template_version=1,
    model="test-model",
    parameters={},
    system="Synthetic review",
    messages=(),
    input_sha256="a" * 64,
    max_tokens=100,
)


def fixture(root: Path, name: str, **overrides: Any) -> Path:
    directory = root / "contract-review" / "v1"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{name}.json"
    path.write_text(
        json.dumps(
            {
                "text": "Synthetic café proposal",
                "input_tokens": 10,
                "output_tokens": 5,
                "latency_ms": 0,
                "stop_reason": "end_turn",
                **overrides,
            }
        ),
        encoding="utf-8",
    )
    return path


def test_fixture_lookup_by_input_hash(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*args: Any, **kwargs: Any) -> None:
        pytest.fail("Fake provider attempted network access or sleeping")

    monkeypatch.setattr("socket.socket", forbidden)
    monkeypatch.setattr(time, "sleep", forbidden)
    fixture(tmp_path, "default", text="Fallback")
    exact = fixture(tmp_path, REQUEST.input_sha256)
    provider: AIProvider = FakeProvider(tmp_path)
    result = provider.complete(REQUEST)
    assert result == provider.complete(REQUEST)
    assert result.text == "Synthetic café proposal"
    assert result.response_sha256 == sha256(result.text.encode("utf-8")).hexdigest()
    assert (result.input_tokens, result.output_tokens, result.latency_ms) == (10, 5, 0)
    assert (result.model, result.stop_reason) == (REQUEST.model, "end_turn")
    exact.unlink()
    assert provider.complete(REQUEST).text == "Fallback"
    with pytest.raises(FileNotFoundError):
        provider.complete(replace(REQUEST, template_version=2))
    with pytest.raises(FileNotFoundError):
        provider.complete(replace(REQUEST, template_id="explain-narrative"))
    (exact.parent / "default.json").unlink()
    with pytest.raises(FileNotFoundError):
        provider.complete(REQUEST)


def test_bad_exact_fixture_does_not_fall_back(tmp_path: Path) -> None:
    fixture(tmp_path, "default")
    exact = fixture(tmp_path, REQUEST.input_sha256)
    exact.write_text("{", encoding="utf-8")
    with pytest.raises(json.JSONDecodeError):
        FakeProvider(tmp_path).complete(REQUEST)


@pytest.mark.parametrize(
    "change",
    [
        {"template_id": "../escape"},
        {"template_id": "/absolute"},
        {"template_version": 0},
        {"template_version": True},
        {"input_sha256": "../escape"},
        {"input_sha256": "A" * 64},
    ],
)
def test_fixture_identifiers_cannot_escape_root(tmp_path: Path, change: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        FakeProvider(tmp_path).complete(replace(REQUEST, **change))


@pytest.mark.parametrize(
    "change",
    [
        {"input_tokens": True},
        {"output_tokens": -1},
        {"latency_ms": 0.5},
        {"text": []},
        {"stop_reason": None},
        {"extra": "unexpected"},
    ],
)
def test_malformed_fixture_is_refused(tmp_path: Path, change: dict[str, Any]) -> None:
    fixture(tmp_path, "default", **change)
    with pytest.raises(ValueError):
        FakeProvider(tmp_path).complete(REQUEST)


def test_refusal_stop_reason_is_preserved(tmp_path: Path) -> None:
    fixture(tmp_path, "default", text="", stop_reason="refusal")
    assert FakeProvider(tmp_path).complete(REQUEST).stop_reason == "refusal"
