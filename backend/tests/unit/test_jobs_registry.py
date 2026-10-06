"""Job registry (dev-guide §5.12 DG-KRN-JOB-01, 05, 09, 10; 05 §5.6; BUILD_SPEC PLF-9)."""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from typing import Any

import pytest
from erev_api.auth.principal import system_principal
from erev_api.clock import FrozenClock
from erev_api.config import WORKER_QUEUE_NAMES
from erev_api.enums import JobKind, PrincipalKind
from erev_api.jobs import registry
from erev_api.jobs.context import JobContext
from erev_api.jobs.registry import (
    JOB_QUEUE,
    QUEUES,
    HandlerSpec,
    JobOutcome,
    RetryPolicy,
    backoff_delay,
    failure_problem,
    run_inline,
)
from erev_api.problems import Problem, ProblemError


def test_krn_job_10_job_queue_equals_profile() -> None:
    assert QUEUES == (
        "compute",
        "imports",
        "close",
        "outbox",
        "reports",
        "maintenance",
        "integrations",
        "ai",
    )
    assert QUEUES == WORKER_QUEUE_NAMES
    # 04 E-14 rev 1.164: PERIOD_OPEN_REDIRTY (supervisor ruling R-101 (a); revision 0098)
    assert len(JobKind) == 27
    assert {kind.value: queue for kind, queue in JOB_QUEUE.items()} == {
        "CONTRACT_COMPUTE": "compute",
        "REPLAY_VERIFY": "compute",
        "POLICY_SIMULATION": "compute",
        "IMPORT_VALIDATE": "imports",
        "IMPORT_DIFF": "imports",
        "IMPORT_COMMIT": "imports",
        "MIGRATION_IMPORT": "imports",
        "MIGRATION_RECONCILE": "imports",
        "CLOSE_RUN": "close",
        "JOURNAL_RUN_CALCULATE": "close",
        "RECONCILIATION_GENERATE": "close",
        "PERIOD_OPEN_REDIRTY": "close",
        "JOURNAL_EXPORT": "outbox",
        "OUTBOX_RELAY": "outbox",
        "WEBHOOK_DELIVERY": "outbox",
        "EMAIL_DELIVERY": "outbox",
        "REPORT_RUN": "reports",
        "EVIDENCE_PACK": "reports",
        "FORECAST_RUN": "reports",
        "DEAL_PREVIEW": "reports",
        "SSP_CALCULATOR": "reports",
        "AUDIT_CHAIN_VERIFY": "maintenance",
        "TENANT_SNAPSHOT": "maintenance",
        "SANDBOX_RESET": "maintenance",
        "RETENTION_SWEEP": "maintenance",
        "SYNC_RUN": "integrations",
        "AI_TASK": "ai",
    }


def test_r_62_a_every_kind_is_audited_or_a_transport_kind() -> None:
    """04 T-PLT-27 rev 1.106 (supervisor rulings R-50 (a), R-62 (a)): the registry writes
    ``job.start`` and ``job.finish`` for every kind but the three transport kinds of the outbox.
    The two declared sets partition E-14, so a new kind cannot fall outside both; the queue table
    names the same kinds."""
    assert registry.TRANSPORT_KINDS == {
        JobKind.OUTBOX_RELAY,
        JobKind.EMAIL_DELIVERY,
        JobKind.WEBHOOK_DELIVERY,
    }
    assert not registry.AUDITED_KINDS & registry.TRANSPORT_KINDS
    assert registry.AUDITED_KINDS | registry.TRANSPORT_KINDS == set(JobKind) == set(JOB_QUEUE)
    # 24: PERIOD_OPEN_REDIRTY joins the audited kinds (ruling R-101 (a); 04 E-14 rev 1.164)
    assert len(registry.AUDITED_KINDS) == 24
    for kind in JobKind:
        assert registry.start_is_audited(kind) is (kind in registry.AUDITED_KINDS), kind
    # A business job of the outbox queue is audited: only the three deliveries are transport.
    assert JOB_QUEUE[JobKind.JOURNAL_EXPORT] == "outbox"
    assert JobKind.JOURNAL_EXPORT in registry.AUDITED_KINDS
    assert (registry.START_ACTION, registry.FINISH_ACTION, registry.CANCEL_ACTION) == (
        "job.start",
        "job.finish",
        "job.cancel",
    )


def test_r_50_a_job_event_payloads_name_no_params() -> None:
    """The ``after`` of ``job.start`` is what the job is and what it works on, never ``params``;
    the ``after`` of ``job.finish`` names the problem by its slug (``about:blank`` for an
    unexpected error, ``failure_problem``)."""
    job_id, subject = uuid.uuid4(), uuid.uuid4()
    row = {
        "id": job_id,
        "kind": "REPORT_RUN",
        "state": "QUEUED",
        "params": {"customer": "never audited"},
        "queue": "reports",
        "priority": 0,
        "parent_job_id": None,
        "subject_type": "report_run",
        "subject_id": subject,
    }
    assert registry.start_facts(row) == {
        "kind": "REPORT_RUN",
        "state": "QUEUED",
        "queue": "reports",
        "priority": 0,
        "parent_job_id": None,
        "subject_type": "report_run",
        "subject_id": subject,
    }
    unexpected = failure_problem(RuntimeError("customer name"), job_id)
    known = failure_problem(Problem("release-mismatch", "another release"), job_id)
    assert registry.problem_slug(None) is None
    assert registry.problem_slug(unexpected) == "about:blank"
    assert registry.problem_slug(known) == "release-mismatch"
    assert registry.finish_facts(JobKind.REPORT_RUN, registry.JobState.FAILED, known) == {
        "kind": "REPORT_RUN",
        "state": "FAILED",
        "problem": "release-mismatch",
    }


def test_krn_job_01_task_registers_one_handler(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(registry, "HANDLERS", {})
    policy = RetryPolicy(max_attempts=3)

    @registry.task(JobKind.AI_TASK, retry=policy)
    def handler(context: JobContext, params: Mapping[str, Any]) -> JobOutcome:
        return JobOutcome(state="SUCCEEDED", result={})

    assert registry.HANDLERS == {JobKind.AI_TASK: HandlerSpec(handler=handler, retry=policy)}
    with pytest.raises(ValueError, match="DG-KRN-JOB-01"):
        registry.task(JobKind.AI_TASK)(handler)
    assert RetryPolicy() == RetryPolicy(max_attempts=1, backoff_seconds=(30, 120, 600))


def test_krn_job_05_backoff_steps() -> None:
    policy = RetryPolicy(max_attempts=5)
    assert [backoff_delay(policy, attempt).total_seconds() for attempt in (1, 2, 3, 4)] == [
        30,
        120,
        600,
        600,
    ]


def test_krn_job_05_failure_problem_keeps_messages_out() -> None:
    job_id = uuid.uuid4()
    unexpected = failure_problem(RuntimeError("customer name"), job_id)
    assert "customer name" not in str(unexpected)
    assert (unexpected["status"], unexpected["instance"]) == (500, f"/api/v1/jobs/{job_id}")
    known = failure_problem(
        Problem("validation-failed", errors=[ProblemError(field="code", rule_id="R")]), job_id
    )
    assert (known["title"], known["errors"][0]["rule_id"]) == ("Check the highlighted fields", "R")


def test_krn_job_09_run_inline(monkeypatch: pytest.MonkeyPatch, clock: FrozenClock) -> None:
    seen: list[tuple[Any, ...]] = []

    def handler(context: JobContext, params: Mapping[str, Any]) -> JobOutcome:
        # Without a job row, progress, heartbeat and cancellation touch nothing.
        context.progress(1, 2)
        context.heartbeat()
        with pytest.raises(RuntimeError, match="no key ring or file store"):
            context.unit_of_work().__enter__()
        seen.append(
            (
                context.kind,
                context.principal.kind,
                dict(params),
                context.cancel_requested(),
                context.clock.now(),
            )
        )
        return JobOutcome(state="SUCCEEDED", result={"counts": {"rows": 1}})

    monkeypatch.setitem(
        registry.HANDLERS, JobKind.DEAL_PREVIEW, HandlerSpec(handler, RetryPolicy())
    )
    tenant_id = uuid.uuid4()
    outcome = run_inline(
        JobKind.DEAL_PREVIEW,
        {"deal": "probe"},
        tenant_id=tenant_id,
        principal=system_principal(tenant_id),
        clock=clock,
    )
    assert outcome == JobOutcome(state="SUCCEEDED", result={"counts": {"rows": 1}})
    assert seen == [
        (JobKind.DEAL_PREVIEW, PrincipalKind.SYSTEM, {"deal": "probe"}, False, clock.now())
    ]
    with pytest.raises(LookupError):
        run_inline(
            JobKind.SYNC_RUN,
            {},
            tenant_id=tenant_id,
            principal=system_principal(tenant_id),
            clock=clock,
        )
