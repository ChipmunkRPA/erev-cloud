"""F-RPS-CUTOFF-R1 (record §43; Codex packet 1845): the runner's checkpoint report run validates
its record-time ``known_at`` on the record-time clock.

A checkpoint's ``known_at`` is the ledger's server stamp — ``SELECT clock_timestamp()`` read once
after the last item committed (``WorkspaceAdapter._record``, DB-08) — while the workspace clock is
the application ``FrozenClock`` still set to that item's business time (DG-AK-41).
``framework._resolve`` refuses a supplied ``known_at`` later than ``uow.now`` (the 422 finding
``KNOWN_AT_FUTURE``), so a unit of work opened on the business clock would refuse every checkpoint
report — the condition Codex 1845 named on the registered path. ``WorkspaceJobs.report_run``
therefore opens the run's unit of work, and runs its job, on a clock fixed at one server read: the
business clock is not substituted for the cutoff, the cutoff is not advanced, the check is not
bypassed, and the workspace clock stays where the plan put it. Shape: POS-CHK-117's March
checkpoint (item 7 effective 2026-03-31, ``after_seq`` 7). ``framework.create_run`` and
``jobs.registry.run_job`` are database commands and stand in for the collaborator tests; the REAL
validation boundary is exercised below through ``framework._resolve`` itself (its entity-scope read
standing in), and end to end by the DB-bound ``tests/domain/reports/test_report_run_clock_db.py``
(not run — databases not provisioned). The POS-117 database test calls the builder directly and
does not cover ``create_run`` → job → registered execution (Codex 1952).
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import pytest
from erev_api.clock import FrozenClock
from erev_api.domain.reports import framework
from erev_api.problems import Problem
from support.answer_keys.workspace_adapter import JOURNAL_PERSONA, REPORT_PERSONA, WorkspaceJobs

BUSINESS_AT = datetime(2026, 3, 31, 12, 0, tzinfo=UTC)  # the last item's business clock
SERVER_AT = datetime(2026, 9, 20, 19, 0, 0, tzinfo=UTC)  # the record-time clock at the run
STAMP = SERVER_AT - timedelta(seconds=1)  # the checkpoint's known_at: the stamp after item 7
PRINCIPAL = SimpleNamespace(permissions=frozenset({"report.run", "journal.run"}))
BLOCK = SimpleNamespace(
    report_code="balance_aging", parameters={"entity_codes": ["US01"], "as_of": "2026-03-31"}
)
JOURNAL_RUN = SimpleNamespace(
    entity="US01",
    period_key="FY2026-P03",
    mode="GROSS",
    grain="ENTITY_BOOK_CURRENCY_PERIOD_ACCOUNT_DIMENSIONS",
)


class _Workspace:
    """The runner workspace's surface the jobs collaborator uses: the application clock, the
    server clock read (``scalar``) and ``uow(principal, clock=)``."""

    def __init__(self) -> None:
        self.clock = FrozenClock(BUSINESS_AT)
        self.keyring = None
        self.files = None
        self.tenant_id = uuid4()
        self.uow_clocks: list[datetime] = []
        self.server_reads = 0

    def scalar(self, statement: Any) -> datetime:
        assert "clock_timestamp" in str(statement)
        self.server_reads += 1
        return SERVER_AT

    @contextmanager
    def uow(self, principal: Any = None, *, clock: Any = None) -> Iterator[Any]:
        at = self.clock if clock is None else clock
        now = at.now()
        self.uow_clocks.append(now)
        yield SimpleNamespace(now=now, principal=principal, commit=lambda: None)


class _Seen:
    """Stand-ins for the two database commands, recording what they were given."""

    def __init__(self) -> None:
        self.run_id = uuid4()
        self.job_id = uuid4()
        self.body: Any = None
        self.uow_now: datetime | None = None
        self.job_clock: datetime | None = None

    def create_run(self, uow: Any, body: Any) -> tuple[UUID, Any]:
        """``framework.create_run`` as far as ``known_at`` goes: ``_resolve`` parses a supplied
        ``known_at`` and refuses one later than ``uow.now`` with ``KNOWN_AT_FUTURE``."""
        self.body = body
        self.uow_now = uow.now
        supplied = (getattr(body, "parameters", None) or {}).get(framework.KNOWN_AT)
        if supplied is not None:  # the journal body has no parameters and no such rule
            parsed = datetime.fromisoformat(str(supplied).replace("Z", "+00:00"))
            if parsed > uow.now:
                field = f"parameters.{framework.KNOWN_AT}"
                raise framework._invalid([framework._finding(field, framework.KNOWN_AT_FUTURE)])
        return self.run_id, SimpleNamespace(id=self.job_id)

    def run_job(self, job_id: UUID, tenant_id: UUID, *, attempt: int, runtime: Any) -> None:
        assert (job_id, attempt) == (self.job_id, 1)
        self.job_clock = runtime.clock.now()


def _resolve_at(monkeypatch: pytest.MonkeyPatch, now: datetime, given: dict[str, Any]) -> Any:
    """The real ``framework._resolve`` at ``uow.now = now`` (the entity-scope read stands in)."""
    monkeypatch.setattr(
        framework, "_in_scope_entities", lambda session, principal, permission: {"US01": uuid4()}
    )
    schema = framework.catalogue.DEFINITIONS_BY_CODE[BLOCK.report_code].parameters_schema
    uow = SimpleNamespace(session=None, principal=None, now=now)
    return framework._resolve(uow, schema, given, code=BLOCK.report_code)


def test_the_real_resolver_refuses_the_stamp_on_the_business_clock_and_accepts_it_on_record_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Codex 1845 / 1952: ``framework._resolve`` itself, with the POS-117 clock shape — the
    checkpoint stamp is "later than now" on the business clock and a valid historical cutoff on
    the record-time clock; the cutoff value is never substituted or advanced."""
    given = {**BLOCK.parameters, framework.KNOWN_AT: framework.utc_text(STAMP)}
    _, errors = _resolve_at(monkeypatch, BUSINESS_AT, given)
    assert [(e.field, e.message) for e in errors] == [
        (f"parameters.{framework.KNOWN_AT}", framework.KNOWN_AT_FUTURE)
    ]
    resolved, errors = _resolve_at(monkeypatch, SERVER_AT, given)
    assert errors == []
    assert resolved.known_at == STAMP and resolved.historical is True
    assert resolved.parameters[framework.KNOWN_AT] == framework.utc_text(STAMP)
    assert resolved.parameters[framework.KNOWN_AT_BASIS] == framework.HISTORICAL_BASIS


def test_the_business_clock_would_refuse_the_record_time_stamp() -> None:
    """Codex 1845's condition in the framework's own terms: on the business clock the checkpoint
    stamp is "later than now"."""
    seen = _Seen()
    body = SimpleNamespace(parameters={framework.KNOWN_AT: framework.utc_text(STAMP)})
    with pytest.raises(Problem) as refused:
        seen.create_run(SimpleNamespace(now=BUSINESS_AT), body)
    (finding,) = refused.value.errors
    assert (finding.field, finding.message) == ("parameters.known_at", framework.KNOWN_AT_FUTURE)


def test_checkpoint_report_run_validates_known_at_on_the_record_time_clock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace, seen = _Workspace(), _Seen()
    monkeypatch.setattr(framework, "create_run", seen.create_run)
    monkeypatch.setattr("erev_api.jobs.registry.run_job", seen.run_job)
    jobs = WorkspaceJobs(workspace, {REPORT_PERSONA: PRINCIPAL})

    run_id = jobs.report_run(BLOCK, STAMP)

    assert run_id == seen.run_id
    # The cutoff is the checkpoint's stamp, unchanged; the basis is the framework's to resolve.
    assert seen.body.parameters[framework.KNOWN_AT] == framework.utc_text(STAMP)
    assert framework.KNOWN_AT_BASIS not in seen.body.parameters
    assert dict(seen.body.parameters, known_at=None) == dict(BLOCK.parameters, known_at=None)
    # Validated on the record-time clock — one server read — and the job runs on the same clock.
    assert workspace.server_reads == 1
    assert (seen.uow_now, workspace.uow_clocks) == (SERVER_AT, [SERVER_AT])
    assert seen.job_clock == SERVER_AT
    # The workspace's application clock is not advanced: the plan's next item finds it in place.
    assert workspace.clock.now() == BUSINESS_AT


class _NoRuns:
    """The reads the journal step asks: no run stands before the create, the created one after."""

    def __init__(self, seen: _Seen) -> None:
        self.seen = seen

    def journal_runs(self, entity: str, book: str, period_key: str) -> list[dict[str, Any]]:
        if self.seen.body is None:
            return []
        return [{"id": self.seen.run_id, "state": "draft", "run_no": "JR-000001"}]

    def sealed_to(self, book: str) -> int:
        return 0

    def journal_lines(self, run_id: UUID, *, per_contract: bool) -> tuple[Any, ...]:
        assert (run_id, per_contract) == (self.seen.run_id, False)
        return ()


def test_journal_runs_keep_the_application_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    """The journal run of a journals block is created and calculated on the plan's business
    clock, and gives no cutoff of its own: ``journals.commands.create_run`` then takes
    ``uow.now``, and ``summarise.covered_to`` compares a cutoff with ``sealed_at``, which the
    product stamps with that same clock. No server clock is read for it.

    STALE EXPECTATION under item AK-JOURNAL-RUN-PLAN-1: until it the run was made when the
    checkpoint was read (``WorkspaceJobs.journal_run``) and this test pinned the checkpoint's
    server stamp as ``cutoff_known_at``. Measured in POS-012's world: a run made at the end of
    the plan with the stamp taken before the close run held the reclass the close run posted
    after that stamp — every seal's business instant lies before a server stamp of today."""
    from erev_api.domain.journals import commands
    from erev_api.enums import BookCode, JournalRunGrain, JournalRunMode
    from erev_api.schemas.journals import JournalRunCreateIn
    from support.answer_keys.platform_plan import JOURNAL, H, Step
    from support.answer_keys.workspace_adapter import Call, JournalAnswer, _journal_block

    workspace, seen = _Workspace(), _Seen()
    monkeypatch.setattr(commands, "create_run", seen.create_run)
    monkeypatch.setattr("erev_api.jobs.registry.run_job", seen.run_job)
    subject = f"journals {JOURNAL_RUN.entity} {JOURNAL_RUN.period_key} {JOURNAL_RUN.mode}"
    step = Step(JOURNAL, JOURNAL_PERSONA, H["journal_create"], subject)
    body = JournalRunCreateIn(
        entity_code=JOURNAL_RUN.entity,
        book=BookCode.ASC606,
        period_key=JOURNAL_RUN.period_key,
        mode=JournalRunMode(JOURNAL_RUN.mode),
        grain=JournalRunGrain(JOURNAL_RUN.grain),
    )
    call = Call(step.handler, step.actor, {}, step)

    answer = _journal_block(workspace, PRINCIPAL, call, body, _NoRuns(seen), [])  # type: ignore[arg-type]

    assert answer == JournalAnswer(seen.run_id, False, (), ())
    assert seen.body is body and seen.body.cutoff_known_at is None
    assert (seen.uow_now, workspace.uow_clocks, seen.job_clock) == (
        BUSINESS_AT,
        [BUSINESS_AT],
        BUSINESS_AT,
    )
    assert workspace.server_reads == 0
