"""AI queue dispatch validates selectors and delegates retry ownership to the gateway."""

from __future__ import annotations

from datetime import timedelta
from typing import Any
from unittest.mock import ANY, Mock
from uuid import uuid4

import pytest
from erev_api.domain.ai import jobs
from erev_api.domain.ai.extraction_gateway import ExtractionGateway
from erev_api.domain.ai.gateway import AICancelled, AiGateway
from erev_api.enums import JobKind
from erev_api.jobs.context import JobContext, JobLost
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
        context, jobs.NarrativeTask.model_validate(params).source(), max_tokens=1024, wait=ANY
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


def test_retry_wait_notices_cancellation_between_chunks() -> None:
    context = Mock(spec=JobContext)
    context.cancel_requested.side_effect = [False, True]
    wait = Mock()
    with pytest.raises(AICancelled, match="AI_CANCELLED"):
        jobs.retry_wait(context, timedelta(seconds=5), wait)
    wait.assert_called_once_with(timedelta(seconds=1))
    assert context.heartbeat.call_count == 2


def test_retry_wait_preserves_fractional_remaining_delay() -> None:
    context = Mock(spec=JobContext)
    context.cancel_requested.return_value = False
    waits: list[timedelta] = []
    jobs.retry_wait(context, timedelta(seconds=2.5), waits.append)
    assert waits == [timedelta(seconds=1), timedelta(seconds=1), timedelta(seconds=0.5)]
    assert context.heartbeat.call_count == 4


def test_handler_returns_cancellation_for_registry_settlement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gateway = Mock(spec=AiGateway)
    gateway.run_narrative.side_effect = AICancelled("AI_CANCELLED")
    monkeypatch.setattr(jobs, "_gateway", gateway)
    monkeypatch.setattr(jobs, "_wait", Mock())
    assert jobs.run(Mock(spec=JobContext), payload()).result == {"cancelled": True}


def test_retry_wait_stops_when_attempt_loses_job() -> None:
    context = Mock(spec=JobContext)
    context.heartbeat.side_effect = JobLost(uuid4())
    wait = Mock()
    with pytest.raises(JobLost):
        jobs.retry_wait(context, timedelta(seconds=5), wait)
    wait.assert_not_called()


def extraction_payload() -> dict[str, Any]:
    return {
        "operation": "extraction",
        "file_id": str(uuid4()),
        "file_sha256": "a" * 64,
        "allowed_paths": ["amount"],
        "max_tokens": 1024,
    }


def test_extraction_dispatch_preserves_source_and_context(monkeypatch: pytest.MonkeyPatch) -> None:
    gateway = Mock(spec=ExtractionGateway)
    proposal_id = uuid4()
    gateway.run_extraction.return_value = proposal_id
    monkeypatch.setattr(jobs, "_gateway", gateway)
    monkeypatch.setattr(jobs, "_wait", Mock())
    context = Mock(spec=JobContext)
    params = extraction_payload()
    outcome = jobs.run(context, params)
    assert outcome.result == {"proposal_id": str(proposal_id)}
    gateway.run_extraction.assert_called_once_with(
        context, jobs.ExtractionTask.model_validate(params).source(), max_tokens=1024, wait=ANY
    )
    gateway.run_narrative.assert_not_called()


@pytest.mark.parametrize(
    "changes",
    [
        {"file_sha256": "private text"},
        {"allowed_paths": []},
        {"allowed_paths": [""]},
        {"max_tokens": True},
        {"model": "unapproved"},
        {"text": "private text"},
    ],
)
def test_invalid_extraction_payload_is_sanitized(
    changes: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    gateway = Mock(spec=ExtractionGateway)
    monkeypatch.setattr(jobs, "_gateway", gateway)
    monkeypatch.setattr(jobs, "_wait", Mock())
    with pytest.raises(ValueError, match="^AI_INVALID_TASK$"):
        jobs.run(Mock(spec=JobContext), extraction_payload() | changes)
    gateway.run_extraction.assert_not_called()
    gateway.run_narrative.assert_not_called()
