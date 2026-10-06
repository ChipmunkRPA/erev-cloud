"""Close runs through the API-R-39 routes (BUILD_SPEC CLO-19, CLO-20; dev-guide DG-TST-16).

Tests start, resume and cancel close runs as the product does: ``POST /close-runs`` answers 202
with the ``CLOSE_RUN`` job, which ``work`` runs as the worker runs it (``jobs.registry.run_job``
after the task is fetched).

While a close-run job waits for the child ``CONTRACT_COMPUTE`` jobs of ``RECOMPUTE_DIRTY`` it
pauses between two polls (05 RCP-19). A test stands for the rest of the worker pool in that pause:

- ``Workers`` runs every ``QUEUED`` child job as a second worker would, so the children end as
  jobs of their own;
- ``unattended`` lets the pause pass at once with no other worker, so the close-run job takes its
  children over at its second poll and computes their chunks itself.

``closed`` runs a whole close run to its end; ``summary`` renders a step as SCREENS_B §1.2 words
it from the step's ``counts``; ``posted`` reads the ledger lines a run sealed and ``by_role`` sums
them; ``journal_posted`` takes the run's journal run through approval, export and acknowledgement
(PRD SM-08).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Final
from uuid import UUID

import pytest
from erev_api.clock import FrozenClock
from erev_api.db import new_id
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import (
    gl_account,
    job,
    obligation,
    period,
    subledger_line,
    subledger_posting,
)
from erev_api.db.transitions import apply
from erev_api.domain.close import close_runs
from erev_api.domain.journals import ports
from erev_api.enums import GlAdapter, JobKind, JobState, PrincipalKind
from erev_api.jobs.context import JobRuntime
from erev_api.jobs.registry import fail_attempt, run_job
from erev_api.problems import Problem
from fastapi import FastAPI
from sqlalchemy import and_, select, text
from support import worlds
from support.http import HttpResponse
from support.principals import Actor
from support.reference import approve, get, post

CLOSE_RUNS: Final = "/api/v1/close-runs"
ID_HEADER: Final = "X-Erev-Close-Run-Id"
_TASK_FETCHED: Final = text("UPDATE procrastinate_jobs SET status = 'doing' WHERE id = :id")
# 04 T-CLS-01: the fourteen steps in the order of the ``steps`` array.
STEP_CODES: Final = (
    "CUTOFF",
    "INTERFACE_COMPLETENESS",
    "EXCEPTION_CHECK",
    "RECOMPUTE_DIRTY",
    "RELEASE_SCHEDULES",
    "FX_REMEASUREMENT",
    "NETTING_RECLASS",
    "INVARIANTS",
    "JOURNAL_SUMMARIZATION",
    "EXPORT",
    "ACKNOWLEDGEMENT_WAIT",
    "GL_TIE_OUT",
    "DATASET_FREEZE",
    "LOCK",
)


def _context(tenant_id: UUID) -> DbContext:
    return DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")


def new_row_id() -> UUID:
    """An id for a row a test inserts by hand."""
    return new_id()


def start(
    app: FastAPI, actor: Actor, *, entity_code: str, period_key: str, book: str | None = None
) -> HttpResponse:
    """``POST /close-runs``."""
    body: dict[str, Any] = {"entity_code": entity_code, "period_key": period_key}
    if book is not None:
        body["book"] = book
    return post(app, CLOSE_RUNS, actor, body)


def shown(app: FastAPI, actor: Actor, run_id: str) -> dict[str, Any]:
    """``GET /close-runs/{id}``."""
    found = get(app, f"{CLOSE_RUNS}/{run_id}", actor)
    assert found.status_code == 200, found.text
    return dict(found.json())


def listed(app: FastAPI, actor: Actor, **filters: str) -> list[dict[str, Any]]:
    """``GET /close-runs`` with ``filters``, oldest first."""
    found = get(app, CLOSE_RUNS, actor, {"sort": "id", **filters})
    assert found.status_code == 200, found.text
    return list(found.json()["items"])


def resume(app: FastAPI, actor: Actor, run_id: str) -> HttpResponse:
    """``POST /close-runs/{id}/resume``."""
    return post(app, f"{CLOSE_RUNS}/{run_id}/resume", actor, {})


def cancel(app: FastAPI, actor: Actor, run_id: str, reason: str) -> HttpResponse:
    """``POST /close-runs/{id}/cancel``."""
    return post(app, f"{CLOSE_RUNS}/{run_id}/cancel", actor, {"reason": reason})


def step(run: dict[str, Any], code: str) -> dict[str, Any]:
    """The ``steps`` element of ``code``."""
    (found,) = [item for item in run["steps"] if item["step_code"] == code]
    return dict(found)


def job_row(tenant_id: UUID, job_id: UUID) -> dict[str, Any]:
    with tenant_session(_context(tenant_id), read_only=True) as session:
        return dict(session.execute(select(job).where(job.c.id == job_id)).mappings().one())


def work(
    tenant_id: UUID, runtime: JobRuntime, job_id: UUID, *, concurrency: int | None = None
) -> dict[str, Any]:
    """The worker fetches the job's task and runs its one attempt (a close run has no automatic
    retry, 05 §5.6); the job row afterwards. ``concurrency`` stands for
    ``platform.job_concurrency``."""
    with tenant_session(_context(tenant_id)) as session:
        task_id = session.execute(
            select(job.c.procrastinate_job_id).where(job.c.id == job_id)
        ).scalar_one()
        session.execute(_TASK_FETCHED, {"id": task_id})
    run_job(job_id, tenant_id, attempt=1, runtime=runtime, concurrency=concurrency)
    return job_row(tenant_id, job_id)


def dead_lettered(tenant_id: UUID, runtime: JobRuntime, job_id: UUID) -> dict[str, Any]:
    """A worker takes the job and dies: the job is ``RUNNING`` and silent, and the sweeper
    settles its last attempt ``FAILED`` with problem ``job-stalled`` (05 JOB-06), which calls the
    kind's failure hook. The job row afterwards."""
    now = runtime.clock.now()
    with tenant_session(_context(tenant_id)) as session:
        task_id = session.execute(
            select(job.c.procrastinate_job_id).where(job.c.id == job_id)
        ).scalar_one()
        session.execute(_TASK_FETCHED, {"id": task_id})
        apply(
            session,
            "job",
            job_id,
            to_status=JobState.RUNNING.value,
            set_values={
                "started_at": now,
                "updated_at": now,
                "updated_by": None,
                "updated_by_kind": PrincipalKind.SYSTEM.value,
            },
            expected_status=JobState.QUEUED.value,
        )
    settled = fail_attempt(
        job_id,
        tenant_id,
        attempt=1,
        error=Problem("job-stalled", "no heartbeat for 10 minutes"),
        runtime=runtime,
    )
    assert settled is JobState.FAILED, settled
    return job_row(tenant_id, job_id)


def started(app: FastAPI, actor: Actor, *, entity_code: str, period_key: str) -> tuple[str, UUID]:
    """A close run as started — ``PENDING``, its job ``QUEUED``: (run id, job id)."""
    response = start(app, actor, entity_code=entity_code, period_key=period_key)
    assert response.status_code == 202, response.text
    body = response.json()
    assert (body["kind"], body["state"]) == ("CLOSE_RUN", "QUEUED")
    assert response.headers["Location"] == f"/api/v1/jobs/{body['id']}"
    return str(response.headers[ID_HEADER]), UUID(str(body["id"]))


def children(tenant_id: UUID, parent_job_id: UUID) -> list[dict[str, Any]]:
    """The child jobs a close-run job deferred, oldest first."""
    with tenant_session(_context(tenant_id), read_only=True) as session:
        return [
            dict(row)
            for row in session.execute(
                select(job)
                .where(job.c.parent_job_id == parent_job_id)
                .order_by(job.c.created_at, job.c.id)
            ).mappings()
        ]


@dataclass
class Workers:
    """The rest of the worker pool while a close-run job pauses: every ``QUEUED``
    ``CONTRACT_COMPUTE`` job of the tenant is delivered and run once per pause, oldest first.
    ``before`` is called first in each pause (a test acts there "while the step runs")."""

    tenant_id: UUID
    runtime: JobRuntime
    concurrency: int | None = None
    before: Callable[[], None] | None = None
    delivered: list[UUID] = field(default_factory=list)
    pauses: int = 0

    def __call__(self, seconds: float) -> None:
        assert seconds == close_runs.POLL_SECONDS
        self.pauses += 1
        assert self.pauses < 50, "the close-run job is waiting for a child that never ends"
        if self.before is not None:
            self.before()
        with tenant_session(_context(self.tenant_id), read_only=True) as session:
            queued = [
                UUID(str(value))
                for value in session.scalars(
                    select(job.c.id)
                    .where(
                        job.c.kind == JobKind.CONTRACT_COMPUTE.value,
                        job.c.state == JobState.QUEUED.value,
                    )
                    .order_by(job.c.created_at, job.c.id)
                )
            ]
        for job_id in queued:
            self.delivered.append(job_id)
            work(self.tenant_id, self.runtime, job_id, concurrency=self.concurrency)


def attended(monkeypatch: pytest.MonkeyPatch, workers: Workers) -> Workers:
    """``workers`` run the children while the close-run job pauses."""
    monkeypatch.setattr(close_runs, "_pause", workers)
    return workers


def unattended(
    monkeypatch: pytest.MonkeyPatch, before: Callable[[], None] | None = None
) -> list[float]:
    """No other worker: each pause passes at once (after ``before``), so the close-run job takes
    its children over. Returns the pauses taken."""
    pauses: list[float] = []

    def pause(seconds: float) -> None:
        pauses.append(seconds)
        assert len(pauses) < 50, "the close-run job is waiting for a child that never ends"
        if before is not None:
            before()

    monkeypatch.setattr(close_runs, "_pause", pause)
    return pauses


# --- a whole run and what it left (BUILD_SPEC CLO-20) ---------------------------------------------


def closed(
    world: worlds.ReportWorld,
    monkeypatch: pytest.MonkeyPatch,
    *,
    entity_code: str,
    period_key: str,
) -> dict[str, Any]:
    """A close run of the entity and period started by Maya and worked to its end with no other
    worker; API-S-CloseRun afterwards."""
    unattended(monkeypatch)
    run_id, job_id = started(world.app, world.maya, entity_code=entity_code, period_key=period_key)
    work(world.tenant_id, world.runtime, job_id)
    return shown(world.app, world.maya, run_id)


def resumed(
    world: worlds.ReportWorld, monkeypatch: pytest.MonkeyPatch, run_id: str
) -> dict[str, Any]:
    """``resume`` by Maya and the new job worked to its end; API-S-CloseRun afterwards."""
    unattended(monkeypatch)
    response = resume(world.app, world.maya, run_id)
    assert response.status_code == 202, response.text
    work(world.tenant_id, world.runtime, UUID(str(response.json()["id"])))
    return shown(world.app, world.maya, run_id)


def summary(run: Mapping[str, Any], code: str) -> str:
    """The "Summary when finished" of a step as SCREENS_B §1.2 words it, from ``steps[].counts``."""
    counts = step(dict(run), code)["counts"]
    if code == "CUTOFF":
        return str(run["cutoff_known_at"])
    if code == "INTERFACE_COMPLETENESS":
        return f"{counts['interface_runs_complete']} interface runs complete"
    if code == "EXCEPTION_CHECK":
        return f"{counts['blocking_exceptions']} blocking exceptions"
    if code == "RECOMPUTE_DIRTY":
        return (
            f"{counts['groups_recomputed']} groups recomputed, "
            f"{counts['groups_quarantined']} quarantined"
        )
    if code == "RELEASE_SCHEDULES":
        return f"{counts['postings']} postings, {counts['lines']} lines"
    if code in ("FX_REMEASUREMENT", "NETTING_RECLASS"):
        return f"{counts['lines']} lines"
    if code == "INVARIANTS":
        failures = counts["invariant_failures"]
        return "All invariants pass" if failures == 0 else f"{failures} invariant failures"
    if code == "JOURNAL_SUMMARIZATION":
        return f"{counts['batches']} batches"
    if code == "EXPORT":
        return f"{counts['batches_exported']} batches exported"
    if code == "ACKNOWLEDGEMENT_WAIT":
        return f"{counts['batches_acknowledged']} of {counts['batches']} batches acknowledged"
    if code == "GL_TIE_OUT":
        if not counts["trial_balance_attached"]:
            return "No trial balance attached"
        return f"Difference {counts['currency']} {counts['difference']}"
    if code == "DATASET_FREEZE":
        return f"{counts['datasets_frozen']} datasets frozen"
    if code == "LOCK":
        return f"Locked by {counts['locked_by']['display_name']}"
    raise ValueError(f"unknown step {code}")


def posted(tenant_id: UUID, run_id: str) -> list[dict[str, Any]]:
    """The subledger lines sealed under the close run, with their posting, period, account and
    obligation key, in (posting, entry, account) order."""
    line, posting = subledger_line, subledger_posting
    statement = (
        select(
            posting.c.id.label("posting_id"),
            posting.c.posting_kind,
            posting.c.idempotency_key,
            posting.c.combination_group_id,
            posting.c.contract_computation_id,
            period.c.period_key,
            line.c.entry_no,
            line.c.entry_kind,
            line.c.account_role,
            gl_account.c.code.label("account_code"),
            obligation.c.obligation_key,
            line.c.txn_currency,
            line.c.amount_txn,
            line.c.functional_currency,
            line.c.amount_functional,
            line.c.effective_date,
            line.c.contract_version_id,
            line.c.calc_trace_id,
            line.c.trace_node_id,
        )
        .select_from(
            line.join(
                posting,
                and_(
                    posting.c.tenant_id == line.c.tenant_id,
                    posting.c.id == line.c.subledger_posting_id,
                ),
            )
            .join(
                period,
                and_(period.c.tenant_id == line.c.tenant_id, period.c.id == line.c.period_id),
            )
            .join(
                gl_account,
                and_(
                    gl_account.c.tenant_id == line.c.tenant_id,
                    gl_account.c.id == line.c.gl_account_id,
                ),
            )
            .outerjoin(
                obligation,
                and_(
                    obligation.c.tenant_id == line.c.tenant_id,
                    obligation.c.id == line.c.obligation_id,
                ),
            )
        )
        .where(posting.c.close_run_id == UUID(run_id))
        .order_by(posting.c.idempotency_key, line.c.entry_no, gl_account.c.code)
    )
    with tenant_session(_context(tenant_id), read_only=True) as session:
        return [dict(row) for row in session.execute(statement).mappings()]


def by_role(
    lines: Iterable[Mapping[str, Any]],
    *,
    period_key: str,
    entry_kind: str,
    amount: str = "amount_functional",
) -> dict[str, Decimal]:
    """Σ ``amount`` (debit positive) per account role of the lines of one period and entry kind."""
    found: dict[str, Decimal] = {}
    for line in lines:
        if line["period_key"] != period_key or str(line["entry_kind"]) != entry_kind:
            continue
        role = str(line["account_role"])
        found[role] = found.get(role, Decimal(0)) + Decimal(line[amount])
    return found


def journal_posted(
    world: worlds.ReportWorld, clock: FrozenClock, journal_run_id: str
) -> worlds.ReportWorld:
    """The journal run a close run calculated, through its life (PRD SM-08): Maya submits it, Priya
    (Revenue Reviewer, fresh TOTP) approves it, Maya exports it and the ERP ledger of
    ``worlds.ErpLedger`` acknowledges it. Returns the world with Priya's verified session."""
    runs = worlds.JOURNAL_RUNS
    submitted = post(world.app, f"{runs}/{journal_run_id}/submit", world.maya, {})
    assert submitted.status_code == 200, submitted.text
    world = worlds.verified(world, clock, "priya")
    decided = approve(world.app, str(submitted.json()["approval_request_id"]), world.priya)
    assert (decided.status_code, decided.json()["status"]) == (200, "APPROVED"), decided.text
    slot = GlAdapter.CSV
    kept = ports.GL_ADAPTERS.get(slot)
    ports.GL_ADAPTERS[slot] = worlds.ErpLedger().factory
    try:
        exported = post(
            world.app, f"{runs}/{journal_run_id}/export", world.maya, {"adapter": slot.value}
        )
        assert exported.status_code == 202, exported.text
        finished = worlds.run_now(world, UUID(str(exported.json()["id"])))
    finally:
        if kept is None:
            ports.GL_ADAPTERS.pop(slot, None)
        else:
            ports.GL_ADAPTERS[slot] = kept
    assert finished["state"] == "SUCCEEDED", finished
    after = get(world.app, f"{runs}/{journal_run_id}", world.maya)
    assert (after.status_code, after.json()["state"]) == (200, "acknowledged"), after.text
    return world
