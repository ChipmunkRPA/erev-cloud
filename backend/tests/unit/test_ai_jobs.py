"""AI queue dispatch validates selectors and delegates retry ownership to the gateway."""

from __future__ import annotations

from datetime import timedelta
from typing import Any
from unittest.mock import Mock
from uuid import uuid4

import pytest
from erev_api.domain.ai import jobs
from erev_api.domain.ai.gateway import AiGateway
from erev_api.enums import JobKind
from erev_api.jobs.context import JobContext
from erev_api.jobs.registry import HANDLERS


def payload() -> dict[str, Any]:
    return {
        "operation": "narrative",
        "object_type": "schedule_line",
        "object_id": str(uuid4()),
        "measure": "revenue",
        "max_tokens": 1024,
    }


def test_dispatch_preserves_context_source_and_retry_ownership(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gateway = Mock(spec=AiGateway)
    context = Mock(spec=JobContext)
    wait = Mock()
    proposal_id = uuid4()
    gateway.run_narrative.return_value = proposal_id
    monkeypatch.setattr(jobs, "_gateway", gateway)
    monkeypatch.setattr(jobs, "_wait", wait)
    params = payload()
    outcome = HANDLERS[JobKind.AI_TASK].handler(context, params)
    gateway.run_narrative.assert_called_once_with(
        context, jobs.NarrativeTask.model_validate(params).source(), max_tokens=1024, wait=wait
    )
    assert outcome.result == {"proposal_id": str(proposal_id)}
    assert HANDLERS[JobKind.AI_TASK].retry.max_attempts == 1
    wait.assert_not_called()


@pytest.mark.parametrize(
    "changes",
    [
        {"operation": "extract"},
        {"prompt": "private text"},
        {"max_tokens": True},
        {"max_tokens": "1024"},
        {"max_tokens": 0},
        {"object_id": "private text"},
        {"object_type": "tenant"},
        {"known_at": "2026-10-15T00:00:00"},
        {"measure": ""},
    ],
)
def test_invalid_payload_never_reaches_gateway(
    changes: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    gateway = Mock(spec=AiGateway)
    monkeypatch.setattr(jobs, "_gateway", gateway)
    monkeypatch.setattr(jobs, "_wait", Mock())
    with pytest.raises(ValueError, match="^AI_INVALID_TASK$"):
        jobs.run(Mock(spec=JobContext), payload() | changes)
    gateway.run_narrative.assert_not_called()


def test_configuration_is_explicit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(jobs, "_gateway", None)
    monkeypatch.setattr(jobs, "_wait", None)
    with pytest.raises(RuntimeError, match="AI_WORKER_NOT_CONFIGURED"):
        jobs.run(Mock(spec=JobContext), payload())
    gateway = Mock(spec=AiGateway)

    def wait(delay: timedelta) -> None:
        assert delay.total_seconds() >= 0

    jobs.configure(gateway, wait)
    assert jobs._gateway is gateway
    assert jobs._wait is wait
