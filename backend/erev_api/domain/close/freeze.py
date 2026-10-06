"""The instant a period lock freezes at, and the guard over what it froze (supervisor rulings R-19,
R-40 (b) / (c) and R-42 of 2026-09-30; ENGINE_SPEC_B §15.2.7 S15-R-18, S15-R-18c; 04 DB-07,
T-CLS-04, T-CLS-05; 03 REQ-CLS-009, REQ-CLS-010; BUILD_SPEC CLO-6).

The lock decision freezes the twelve E-64 datasets on the historical basis (READ-1: rows at or
before a cutoff). The retained inputs carry two record clocks: subledger and journal rows the
APPLICATION clock, a contract version the later of that clock and its computation's transaction
timestamp (``contract_version.known_at``; ``bundles.record_cutoff``, L3-1-Q-25; DB-08). A freeze
at the application clock alone left out every version recorded on a server clock ahead of it, while
the line-based datasets kept the period's lines: the period closed certified with a contract
balance dataset that did not hold the contracts its journal population names.

- ``freeze_cutoff``: the cutoff is the later of the decision's application instant and its own
  transaction timestamp — the rule the versions are stamped by, so every version committed before
  the decision's transaction is at or before it. It is stored on the lock
  (``period_lock.cutoff_known_at``).
- ``coverage_findings`` (pure) over ``Coverage``: what the period holds beyond the cutoff, and
  whether its populations moved since the freeze began. A subledger line of the period recorded
  after the cutoff, a journal run of the period created after it, a contract whose lines of the
  period are within the cutoff while the contract version that posted them is known only after
  it, and a posting or journal run committed into the period while the lock was being decided
  (``Activity`` before the freeze against ``Activity`` now) are each named; the lock is refused
  and nothing is written. The decision asks twice: after the freeze, before any lock write, and
  again as its last read.
- ``system_reads``: the guard reads under the tenant's SYSTEM scope — every entity — in a
  read-only transaction of its own, never under the row-level scope of the person who decides
  (R-42 (d)): a line of the lock's entity whose contract belongs to another contracting entity is
  seen whoever decides.
- ``system_unit``: the same scope as a unit of work, for the producers of the twelve datasets
  (supervisor ruling R-94 (a); S15-R-18c rev 1.88): the frozen dataset of an entity, book and
  period is the same whoever decides. ``snapshots.freeze_datasets`` reads through it and writes
  through the decision's own unit of work.
- Serialisation (04 DB-07 rev 1.113; R-31, R-40 (b)): the two period guards read the period's
  state row ``FOR SHARE`` and the decision holds it ``FOR UPDATE`` from its first read, so no
  line of the period commits while the lock is decided — a posting in flight commits before that
  read and is seen, one that arrives later waits and is refused. The moved-lines finding therefore
  states an invariant of DB-07, and since 04 rev 1.205 (item JR-CLOSED-PERIOD-GUARD-1; revision
  0104) the runs' half does too: the calculation and the cancel of a journal run read the same
  row ``FOR SHARE``, so no run is inserted or cancelled beside the decision.
- ``dataset_refused`` / ``not_covered``: the named refusals, 409 ``invalid-transition``. A
  registry refusal at the decision (``SnapshotRefusal``: a dataset the F-RPS registry will not
  freeze) and a retained artefact the freeze will not reuse are refused by name, never as an
  unhandled error.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Sequence
from contextlib import AbstractContextManager, contextmanager, nullcontext
from dataclasses import dataclass, replace
from datetime import datetime
from typing import TYPE_CHECKING, Final

from sqlalchemy import ColumnElement, and_, exists, func, or_, select

from erev_api.auth.principal import system_principal
from erev_api.db.session import allow_idle_in_transaction, tenant_session
from erev_api.db.tables import book, contract, contract_version, journal_run, subledger_line
from erev_api.enums import BookCode
from erev_api.problems import Problem, ProblemError
from erev_api.uow import UnitOfWork

if TYPE_CHECKING:
    from uuid import UUID

    from sqlalchemy.orm import Session

    from erev_api.domain.close.gates import PeriodScope

RULE_FREEZE: Final = "S15-R-18"  # a dataset the registry refuses to freeze
RULE_COVERAGE: Final = "S15-R-18c"  # the freeze cutoff does not cover the period
CANCELLED_RUN: Final = "cancelled"
NOT_LOCKED: Final = "{period_key} of {entity} in book {book} is not locked: {reason}"
DATASET_REFUSED: Final = "the {kind} dataset cannot be frozen ({reason})."
ARTEFACT_REFUSED: Final = "a retained dataset cannot be reused ({reason})."
LINES_AFTER_CUTOFF: Final = (
    "{count} subledger line(s) of the period are recorded after the freeze cutoff {cutoff} (the "
    "latest at {latest}); the frozen datasets would not hold them."
)
RUNS_AFTER_CUTOFF: Final = (
    "{count} journal run(s) of the period are created after the freeze cutoff {cutoff} (the "
    "latest at {latest}); the frozen journal population would not hold them."
)
VERSION_AFTER_CUTOFF: Final = (
    "contract {external_id} has subledger lines of the period within the freeze cutoff {cutoff}, "
    "and the contract version that posted them is known only at {known_at}; the version-based "
    "datasets would not hold the contract."
)
POSTED_DURING_DECISION: Final = (
    "subledger lines were posted into the period while the lock was being decided ({before} at "
    "the freeze, {after} now); the frozen datasets do not hold them all."
)
RUNS_DURING_DECISION: Final = (
    "the journal runs of the period changed while the lock was being decided ({before} at the "
    "freeze, {after} now); the frozen journal population is not theirs."
)
SEVERAL: Final = "{count} findings; the first: {first}"
# the contracts a refusal names one by one; the detail gives the count of the rest
NAMED_CONTRACTS: Final = 20


def freeze_cutoff(session: Session, now: datetime) -> datetime:
    """The instant a lock's datasets are frozen at (S15-R-18c): the later of the decision's
    application instant ``now`` and the decision's transaction timestamp."""
    started = session.execute(select(func.transaction_timestamp())).scalar_one()
    if not isinstance(started, datetime):
        raise TypeError("transaction_timestamp() returned no timestamp")
    return max(now, started)


@dataclass(frozen=True, slots=True)
class LateVersion:
    """A contract whose lines of the period precede the cutoff and whose posting version does
    not."""

    external_id: str
    known_at: datetime


@dataclass(frozen=True, slots=True)
class Activity:
    """The size of the period's committed populations: its subledger lines (append-only) and its
    journal runs that are not cancelled."""

    lines: int
    runs: int


@dataclass(frozen=True, slots=True)
class Coverage:
    """What the period holds beyond the freeze cutoff, and its ``Activity`` before the freeze and
    now, read in the decision's transaction."""

    cutoff: datetime
    late_lines: int = 0
    latest_line_at: datetime | None = None
    late_runs: int = 0
    latest_run_at: datetime | None = None
    late_versions: tuple[LateVersion, ...] = ()
    at_freeze: Activity | None = None
    now: Activity | None = None


def _lines_of(scope: PeriodScope) -> ColumnElement[bool]:
    """The period's subledger lines; ``period_end_date`` names the partition. For a lock of the
    tenant's primary book they are the lines of the entity and period in that book AND in the
    LEGACY book: the LEGACY book has no close of its own, and its lines follow the primary book's
    lock (04 DB-07 rev 1.155; S15-R-18c rev 1.103; supervisor rulings R-112 (e) and R-114 (d)). A
    lock of another posting book reads its own lines alone."""
    of_primary_lock = and_(
        subledger_line.c.book_code == BookCode.LEGACY.value,
        exists().where(book.c.code == scope.book_code, book.c.is_primary.is_(True)),
    )
    return and_(
        subledger_line.c.period_end_date == scope.end_date,
        subledger_line.c.entity_id == scope.entity_id,
        or_(subledger_line.c.book_code == scope.book_code, of_primary_lock),
        subledger_line.c.period_id == scope.period_id,
    )


def _runs_of(scope: PeriodScope) -> ColumnElement[bool]:
    """The period's journal runs that are not cancelled (the runs a journal population draws on)."""
    return and_(
        journal_run.c.entity_id == scope.entity_id,
        journal_run.c.book_code == scope.book_code,
        journal_run.c.period_id == scope.period_id,
        journal_run.c.state != CANCELLED_RUN,
    )


@contextmanager
def system_reads(tenant_id: UUID) -> Iterator[Session]:
    """A read-only transaction under the tenant's SYSTEM scope — every entity (R-42 (d)). The
    guard's reads go through it, so their result is the entity's, not the decider's: row-level
    security hides a contract of another contracting entity from a decider scoped to the lock's
    entity alone, and the contract's lines of the lock's entity with it."""
    with tenant_session(system_principal(tenant_id).db_context, read_only=True) as session:
        yield session


@contextmanager
def system_unit(uow: UnitOfWork) -> Iterator[UnitOfWork]:
    """A unit of work of the tenant's SYSTEM principal over a read-only transaction of its own,
    with ``uow``'s instant, key ring and file store (supervisor ruling R-94 (a); S15-R-18c rev
    1.88; dev-guide DG-AK-60). The producers of a lock's datasets read through it, so a frozen
    dataset holds every row of the lock's entity whoever decides — row-level security hides a
    contract another entity concluded from a decider scoped to the lock's entity alone, and with it
    the obligation the lock's entity performs. It reads committed rows only and can write nothing:
    the transaction is read-only and the unit is discarded, never committed."""
    principal = system_principal(uow.principal.tenant_id)
    with tenant_session(principal.db_context, read_only=True) as session:
        reader = UnitOfWork(
            ctx=replace(uow.ctx, principal=principal),
            session=session,
            clock=uow.clock,
            keyring=uow.keyring,
            files=uow.files,
        )
        reader.now = uow.now
        try:
            yield reader
        finally:
            reader.discard()


def activity(session: Session, scope: PeriodScope) -> Activity:
    """The period's ``Activity`` as this statement sees it; the decision reads it before the first
    dataset is frozen."""
    lines = session.execute(
        select(func.count()).select_from(subledger_line).where(_lines_of(scope))
    ).scalar_one()
    runs = session.execute(
        select(func.count()).select_from(journal_run).where(_runs_of(scope))
    ).scalar_one()
    return Activity(lines=int(lines), runs=int(runs))


def coverage(
    session: Session, scope: PeriodScope, cutoff: datetime, at_freeze: Activity | None = None
) -> Coverage:
    """``Coverage`` of the lock's entity, book and period at ``cutoff``; with ``at_freeze`` also
    the period's ``Activity`` now."""
    of_period = _lines_of(scope)
    late_lines, latest_line_at = session.execute(
        select(func.count(), func.max(subledger_line.c.recorded_at)).where(
            of_period, subledger_line.c.recorded_at > cutoff
        )
    ).one()
    late_runs, latest_run_at = session.execute(
        select(func.count(), func.max(journal_run.c.created_at)).where(
            _runs_of(scope), journal_run.c.created_at > cutoff
        )
    ).one()
    versions = session.execute(
        select(contract.c.external_id, func.max(contract_version.c.known_at))
        .select_from(
            subledger_line.join(
                contract_version,
                and_(
                    contract_version.c.tenant_id == subledger_line.c.tenant_id,
                    contract_version.c.id == subledger_line.c.contract_version_id,
                ),
            ).join(
                contract,
                and_(
                    contract.c.tenant_id == subledger_line.c.tenant_id,
                    contract.c.id == subledger_line.c.contract_id,
                ),
            )
        )
        .where(
            of_period,
            subledger_line.c.recorded_at <= cutoff,
            contract_version.c.known_at > cutoff,
        )
        .group_by(contract.c.external_id)
        .order_by(contract.c.external_id)
    ).all()
    return Coverage(
        cutoff=cutoff,
        late_lines=int(late_lines),
        latest_line_at=latest_line_at,
        late_runs=int(late_runs),
        latest_run_at=latest_run_at,
        late_versions=tuple(
            LateVersion(external_id=str(external_id), known_at=known_at)
            for external_id, known_at in versions
        ),
        at_freeze=at_freeze,
        now=None if at_freeze is None else activity(session, scope),
    )


def coverage_findings(found: Coverage) -> tuple[str, ...]:
    """The reasons the freeze at ``found.cutoff`` does not cover the period; empty when it does.
    Pure."""
    cutoff = found.cutoff.isoformat()
    reasons: list[str] = []
    if found.late_lines:
        reasons.append(
            LINES_AFTER_CUTOFF.format(
                count=found.late_lines, cutoff=cutoff, latest=_instant(found.latest_line_at)
            )
        )
    if found.late_runs:
        reasons.append(
            RUNS_AFTER_CUTOFF.format(
                count=found.late_runs, cutoff=cutoff, latest=_instant(found.latest_run_at)
            )
        )
    reasons.extend(
        VERSION_AFTER_CUTOFF.format(
            external_id=item.external_id, cutoff=cutoff, known_at=item.known_at.isoformat()
        )
        for item in found.late_versions[:NAMED_CONTRACTS]
    )
    before, after = found.at_freeze, found.now
    if before is not None and after is not None:
        if after.lines != before.lines:
            reasons.append(POSTED_DURING_DECISION.format(before=before.lines, after=after.lines))
        if after.runs != before.runs:
            reasons.append(RUNS_DURING_DECISION.format(before=before.runs, after=after.runs))
    return tuple(reasons)


def _instant(value: datetime | None) -> str:
    return "an unknown instant" if value is None else value.isoformat()


def _refusal(scope: PeriodScope, rule_id: str, reasons: Sequence[str]) -> Problem:
    """409 ``invalid-transition``: the period stays in soft close and the request stays pending.
    The detail names the period and the first reason; every reason is an ``errors[]`` entry."""
    first = (
        reasons[0] if len(reasons) == 1 else SEVERAL.format(count=len(reasons), first=reasons[0])
    )
    detail = NOT_LOCKED.format(
        period_key=scope.period_key, entity=scope.entity_code, book=scope.book_code, reason=first
    )
    return Problem(
        "invalid-transition",
        detail,
        errors=[ProblemError(rule_id=rule_id, message=reason) for reason in reasons],
    )


def dataset_refused(scope: PeriodScope, kind: str, reason: str) -> Problem:
    """The registry refused to freeze ``kind`` (R-19 (c)): named, and nothing is written."""
    return _refusal(scope, RULE_FREEZE, (DATASET_REFUSED.format(kind=kind, reason=reason),))


def artefact_refused(scope: PeriodScope, reason: str) -> Problem:
    """A retained ``SNAPSHOT_DATASET`` row the freeze will not reuse (D-98 candidate 145 (A))."""
    return _refusal(scope, RULE_FREEZE, (ARTEFACT_REFUSED.format(reason=reason),))


def not_covered(scope: PeriodScope, reasons: Sequence[str]) -> Problem:
    """The freeze cutoff does not cover the period (R-19 (b))."""
    return _refusal(scope, RULE_COVERAGE, reasons)


def allow_idle(session: Session) -> None:
    """The idle bound of a dataset freeze, for the transaction of ``session`` (05 TXN-03 rev 1.121;
    supervisor rulings R-116 (h) and R-119 (d)). ``snapshots.freeze_datasets`` works on two
    connections: its caller's transaction is idle while the SYSTEM reader produces a dataset, and
    a reader the caller holds (``held``) is idle while the caller stores the files and writes.
    The 60 s every connection starts with ended either one when a dataset took longer. EVERY
    caller of ``freeze_datasets`` calls this for its own session before the freeze — the lock
    decision, the close run's DATASET_FREEZE step, the sandbox period replay — and for a reader
    it holds; a test over the package's source names a caller that does not. The freeze calls it
    for the reader it opens itself. The bound is ``EREV_DATASET_FREEZE_IDLE_SECONDS`` (05
    CFG-29), transaction-local."""
    allow_idle_in_transaction(session)


def held(reader: UnitOfWork) -> Callable[[UnitOfWork], AbstractContextManager[UnitOfWork]]:
    """``reader`` as the ``reader=`` of ``snapshots.freeze_datasets``: the SYSTEM unit a lock
    decision already holds open for its whole freeze phase (04 §14.1 rev 1.182, "The lock
    decision's two connections"; supervisor ruling R-116 (h); review finding F7 (c)). The producers
    read through it and it stays open when they are done — the decision closes it after its last
    coverage read."""

    def use(_: UnitOfWork) -> AbstractContextManager[UnitOfWork]:
        return nullcontext(reader)

    return use


def activity_before_freeze(
    tenant_id: UUID, scope: PeriodScope, *, reader: Session | None = None
) -> Activity:
    """The period's ``Activity`` under the tenant's SYSTEM scope, read before the first dataset is
    frozen — through ``reader``, the SYSTEM session a lock decision holds for its freeze phase, or
    through a session of its own when the caller holds none."""
    if reader is not None:
        return activity(reader, scope)
    with system_reads(tenant_id) as own:
        return activity(own, scope)


def assert_covered(
    tenant_id: UUID,
    scope: PeriodScope,
    cutoff: datetime,
    at_freeze: Activity,
    *,
    reader: Session | None = None,
) -> None:
    """Refuse by name unless the freeze at ``cutoff`` covers the period and the period's
    ``Activity`` is still what it was before the freeze; read under the tenant's SYSTEM scope —
    through ``reader`` when the caller holds that session (READ COMMITTED: each read sees what is
    committed when it runs), else through a session of its own."""
    if reader is not None:
        found = coverage(reader, scope, cutoff, at_freeze)
    else:
        with system_reads(tenant_id) as own:
            found = coverage(own, scope, cutoff, at_freeze)
    reasons = coverage_findings(found)
    if reasons:
        raise not_covered(scope, reasons)
