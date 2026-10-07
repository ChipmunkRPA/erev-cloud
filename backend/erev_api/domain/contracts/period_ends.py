"""The period ends of a contract group: the engine's close-run passes over a bundle, the periods
whose period-end amounts are still to post, and the group's mark of them (04 T-CON-03
``period_ends_open``; 05 RCP-08; ENGINE_SPEC_B §14.2 S14-R-04, S14-R-05; supervisor rulings R-79
(c), R-114 (a), (b) and R-116 (e); BUILD_SPEC CLO-20, CLO-GATE-RUN-1).

``engine_pass`` is the engine entry of a pass (R-79 (c)): stages 01 to 14 over the framework books
of a ``CLOSE_RELEASE`` bundle with stage 14 bound to the pass, under the guards, the CV-15 stop and
the identities of ``erev_engine.compute``. Item ENG-COMPUTE-PASS-1 moves it into the engine as
``erev_engine.compute_pass``; this function then becomes that call.

``unposted`` is the rule of an unposted period end (R-114 (a)): the ``TIME`` intents of an entity
and period that do not net to zero in some account role and currency, transaction or functional.

The mark. ``combination_group.period_ends_open`` maps ``"<entity code>|<book>"`` to a date: the
group's period-end amounts of that entity and book are posted for every period that ends before
the date. It has two writers, both under the group's row lock:

- a close run (``passed``): the first period-end step of a run of an entity, book and period sets
  the entry of a group it passes to the day after the period's last day. The run's three
  steps seal every net of the period for that scope and refuse over an earlier one, and the
  lock's gate ``CLOSE_RUN_COMPLETED`` asks for the run ``SUCCEEDED`` as well;
- a computation (``after_computation``, in the statement of ``computation.persist`` that writes
  the group's head): only inside a window — a close run of one of the group's entities has a
  ``SUCCEEDED`` first period-end step for a period that is still postable — the three passes run
  dry over the computation's own bundle and each entry is lowered to the first day of the
  earliest period whose ``TIME`` intents do not net to zero. A dry pass the engine refuses lowers
  to the first day of the earliest postable period. Outside a window nothing is written.

An entry moves forward one period at a time (item CLO-GATE-RUN-2; 04 T-CON-03 rev 1.228; review
findings F1 and F3 of 2026-10-01). An absent entry says nothing more than the closed periods do:
the group's period ends count as posted up to the first day of the earliest postable period.
The same holds of an entry that lies in a closed period (second part of rev 1.228): a close run
posts nothing into a closed period — what it lacks is the engine's to carry into a later open
one — so such an entry says no more than the closed periods do. ``passed`` therefore marks a
group only when its period ends are recorded as posted up to the run's period: every group the
step passed when the run's period is the earliest postable one — with an entry or without —
and otherwise a group that holds an entry on or after the period's first day. While an earlier
period is postable it never raises an entry that lies before the run's period start, and the
step is refused over such an entry before it gets here (``close.period_end``). Until rev 1.228
it set the entry of every group it passed, whatever the group held and whatever was postable:
the first step of a later period's run wrote a lowered entry forward, and the earlier period
was locked with that period end unposted.

And a computation inside a window gives a scope WITHOUT an entry its entry — what its dry passes
leave unposted, at most the day after the window's last period, and that day when they leave
nothing: the gate counts a group of the entity that holds none, so that a group no run passed
and no computation judged holds it, and without this every contract booked during a soft close
would hold it too.

The window and the lock decision (``window_held``; 04 DB-07; dev-guide DG-KRN-DB-08 (1c);
supervisor ruling of 2026-10-01 02:35 on item CLO-GATE-RUN-1). The read that finds the window
takes the state rows of the window's periods ``FOR SHARE``, in the order period start, then id,
and ``computation.persist`` makes it before it writes anything — what a posting into such a
period holds through the DB-07 guards, also for a computation that posts no line there. The lock
decision takes its period's state row ``FOR UPDATE`` before it reads the gates, so it waits for
every computation in flight inside the window and then reads the mark that computation wrote; a
computation that arrives while the lock is decided waits and, once the period is closed, finds
no window, runs no pass and writes no mark — a fact recorded after the lock. Without it a
computation that lowered a mark and posted no line into the period could commit between the
decision's gate read and its commit, and the period was locked with that period end unposted
(measured on the head before this read locked: the approval answered 200 while such a
computation was in flight).

Why the computation's own bundle serves (05 RCP-08). The trigger is read by stage 14 alone; the
role targets come from stages 01 to 13, which read events, rates and policies and never a posted
amount; and a ``TIME`` delta is the target's time share less the posted amounts of class ``TIME``
(S14-R-04). A computation posts class ``EVENT`` only (S14-R-05), so its own posting moves no
``TIME`` net. The dry bundle is therefore the computation's with the trigger ``CLOSE_RELEASE`` and
every event counted as included — what a close run's bundle holds once the computation is the
group's head — and no second bundle is read.

[J] Inside a window a computation costs three engine runs more, in its transaction (05 PERF-03),
and one read of the window's frontier (rev 1.167); outside one it costs the read of the group row
and of the window, which returns no row and so locks nothing and waits for nothing.

[J] The share lock is taken by every computation inside a window, not only by one that lowers a
mark: whether a mark is lowered is known after the three dry passes, and the lock has to come
before the first posting (the order is group row, state rows, chain head). A decision therefore
also waits for a computation of the entity's contracts that posts only into a later period, and
such a computation waits while the lock is decided.

[J] On a refused dry pass the entries lowered are those the group already holds and those of its
contracting entities: a close run of such a scope passes over the group (``close.period_end``),
so the entry is set again; an entry no run would pass over would hold its gate for good.
"""

from __future__ import annotations

import dataclasses
import decimal
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from typing import TYPE_CHECKING, Any, Final
from uuid import UUID

from erev_engine import (
    ENGINE_VERSION,
    assemble_output,
    assert_identities,
    dates,
    findings_json,
    guards,
    money,
    stages,
)
from erev_engine.bundle import InputBundle, OutputBundle, PostingIntent
from erev_engine.errors import EngineError
from erev_engine.stages import StageSpec, s01_canonicalize, s13_books
from erev_engine.trace import TraceBuilder
from sqlalchemy import Date, Select, and_, cast, exists, func, select, update
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.exc import DBAPIError
from sqlalchemy.sql.expression import bindparam

from erev_api.db import errors as db_errors
from erev_api.db import locking
from erev_api.db.session import system_entity_scope
from erev_api.db.tables import (
    close_run,
    combination_group,
    combination_group_member,
    contract,
    contract_event,
    legal_entity,
    period,
    period_lock,
    period_state,
)
from erev_api.domain.contracts import bundles, repo
from erev_api.enums import BookCode, CloseRunStatus, ComputationTrigger, ContractStatus
from erev_api.problems import period_lock_in_flight, period_state_moved

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from erev_api.uow import UnitOfWork

__all__ = [
    "CLOSE_RELEASE",
    "FX_REMEASUREMENT",
    "NETTING_RECLASS",
    "PASSES",
    "Held",
    "after_computation",
    "engine_pass",
    "hold_windows",
    "passed",
    "refuse_appends_a_lock_met",
    "refuse_policy_change_a_lock_met",
    "scope_key",
    "unposted",
    "window_held",
]

# ENGINE_SPEC_B S14-R-05: the passes of a CLOSE_RELEASE computation, in the order a period close
# runs them (05 RCP-08 rev 1.9; D-94 (3)).
FX_REMEASUREMENT: Final = "FX_REMEASUREMENT"
CLOSE_RELEASE: Final = "CLOSE_RELEASE"
NETTING_RECLASS: Final = "NETTING_RECLASS"
PASSES: Final = (FX_REMEASUREMENT, CLOSE_RELEASE, NETTING_RECLASS)
TIME: Final = "TIME"  # 05 RCP-07 posting class of a period-end amount
DEBIT: Final = "D"  # ``IntentLine.side`` (S14-R-13)
LEGACY: Final = BookCode.LEGACY.value
_ERROR: Final = "ERROR"
_BOOK_RANK: Final[Mapping[str, int]] = {"ASC606": 0, "IFRS15": 1, "LEGACY": 2}
# A window: the first period-end step of a close run — the step code of ``PASSES[0]`` in 04
# T-CLS-01 ``steps`` — ended SUCCEEDED for a period that is still postable.
_FIRST_STEP_DONE: Final = [{"step_code": PASSES[0], "status": CloseRunStatus.SUCCEEDED.value}]
_CHUNK: Final = 10_000  # group ids per statement


# --- the engine entry (R-79 (c)) -----------------------------------------------------------------


class _Blocking:
    """CV-15, CV-42 as ``erev_engine.compute`` applies them: any ``ERROR`` finding a stage
    collected stops the pass with that finding's code."""

    __slots__ = ("_found",)

    def __init__(self) -> None:
        self._found: dict[tuple[Any, int], tuple[str | None, Any]] = {}

    def check(self, book: str | None, state: object) -> None:
        findings = getattr(state, "findings", ())
        for finding in findings if isinstance(findings, tuple) else ():
            rank = -1 if book is None else _BOOK_RANK.get(book, len(_BOOK_RANK))
            self._found.setdefault((finding.sort_key(), rank), (book, finding))
        ordered = [self._found[key] for key in sorted(self._found)]
        first = next((item for _, item in ordered if item.severity == _ERROR), None)
        if first is not None:
            raise EngineError(
                first.code,
                "a stage collected a blocking finding (CV-15)",
                subject_key=first.subject_key,
                detail={"findings": findings_json(ordered)},
            )


def _bound(spec: StageSpec, pass_name: str) -> StageSpec:
    """Stage 14 bound to the pass (S14-R-05; ENGINE_SPEC_B L2-5-Q-28: ``pass_name`` is a keyword
    of the stage, required under ``CLOSE_RELEASE``)."""
    entry: Callable[..., object] = spec.entry

    def run(ctx: object, state: object, tb: object, **bound: object) -> object:
        return entry(ctx, state, tb, **bound, pass_name=pass_name)

    return dataclasses.replace(spec, entry=run)


def engine_pass(bundle: InputBundle, pass_name: str) -> OutputBundle:
    """One close-run pass of the engine over the framework books of a ``CLOSE_RELEASE`` bundle
    (module docstring). ``EngineError`` as ``erev_engine.compute`` raises it."""
    if pass_name not in PASSES:
        raise ValueError(f"unknown close-run pass {pass_name!r} (S14-R-05)")
    if bundle.trigger != ComputationTrigger.CLOSE_RELEASE.value:
        raise ValueError("a close-run pass runs over a CLOSE_RELEASE bundle (S14-R-05)")
    guards.no_floats(bundle)  # FLOAT_DETECTED before any stage runs (DG-ENG-03)
    if bundle.engine_version != ENGINE_VERSION:
        raise EngineError(
            "ENGINE_VERSION_MISMATCH",
            "bundle engine version differs",
            detail={"bundle": bundle.engine_version, "engine": ENGINE_VERSION},
        )
    framework = tuple(book for book in bundle.books if book.book_code != LEGACY)
    value = dataclasses.replace(bundle, books=framework)
    specs = tuple(_bound(spec, pass_name) if spec.stage == "14" else spec for spec in stages.STAGES)
    with decimal.localcontext(money.DECIMAL_CONTEXT):  # ENG-03; restored on exit
        blocking = _Blocking()
        cb = s01_canonicalize.run(value, TraceBuilder(engine_version=ENGINE_VERSION))
        blocking.check(None, cb)
        results = s13_books.run_books(cb, specs, check=blocking.check)
        output = assemble_output(value, cb, results)
        assert_identities(output, results)
    guards.no_floats(output)
    return output


# --- the rule of an unposted period end (R-114 (a)) ----------------------------------------------


def unposted(intents: Iterable[PostingIntent]) -> frozenset[tuple[str, str]]:
    """(entity code, period key) of the ``TIME`` intents that do not net to zero in some account
    role and currency, transaction or functional (debits less credits, in minor units). A set that
    nets to zero in every role — a posted amount the engine emits again with its own reversal —
    is no unposted period end (supervisor ruling R-114 (a))."""
    nets: dict[tuple[str, str, str, str, str], int] = {}
    for intent in intents:
        if intent.posting_class != TIME:
            continue
        for line in intent.lines:
            sign = 1 if line.side == DEBIT else -1
            for basis, currency, amount in (
                ("txn", line.txn_currency, line.amount_txn),
                ("functional", line.functional_currency, line.amount_functional),
            ):
                key = (intent.entity, intent.posting_period_key, line.account_role, basis, currency)
                nets[key] = nets.get(key, 0) + sign * amount
    return frozenset(
        (entity, period_key) for (entity, period_key, _, _, _), net in nets.items() if net
    )


# --- the mark (04 T-CON-03 ``period_ends_open``) -------------------------------------------------


def scope_key(entity_code: str, book_code: str) -> str:
    """The member of ``period_ends_open`` of an entity and book."""
    return f"{entity_code}|{book_code}"


def _dry(bundle: InputBundle) -> InputBundle:
    """The bundle a close run would read once the computation of ``bundle`` is the group's head:
    the trigger ``CLOSE_RELEASE`` and every event counted as included."""
    heads: dict[str, int] = {}
    for event in bundle.events:
        heads[event.contract_key] = max(heads.get(event.contract_key, 0), event.stream_version)
    group = dataclasses.replace(bundle.group, previous_stream_heads=tuple(sorted(heads.items())))
    return dataclasses.replace(bundle, trigger=ComputationTrigger.CLOSE_RELEASE.value, group=group)


def _first_unposted(bundle: InputBundle) -> dict[str, date]:
    """Per ``scope_key``: the first day of the earliest period whose ``TIME`` intents do not net
    to zero, over the three passes run dry on ``bundle``. ``EngineError`` when a pass is refused."""
    days = {
        entity.code: {item.period_key: item.start_date for item in entity.periods}
        for entity in bundle.entities
    }
    dry = _dry(bundle)
    found: dict[str, date] = {}
    for pass_name in PASSES:
        output = engine_pass(dry, pass_name)
        for book in output.books:
            for entity_code, period_key in unposted(book.posting_intents):
                key = scope_key(entity_code, book.book_code)
                first = days[entity_code][period_key]
                found[key] = min(found.get(key, first), first)
    return found


def _earliest_postable(bundle: InputBundle, held: Iterable[str]) -> dict[str, date]:
    """Per ``scope_key`` the group holds or one of its contracting entities keeps: the first day
    of the earliest postable period of that entity and book (module docstring, second [J])."""
    contracting = {item.contracting_entity_code for item in bundle.contracts}
    entities = {entity.code: entity for entity in bundle.entities}
    keys = set(held)
    found: dict[str, date] = {}
    for book in bundle.books:
        if book.book_code == LEGACY:
            continue
        for entity_code in book.entity_codes:
            key = scope_key(entity_code, book.book_code)
            entity = entities.get(entity_code)
            if entity is None or (key not in keys and entity_code not in contracting):
                continue
            starts = [
                item.start_date
                for item in entity.periods
                if dates.period_state(item, book.book_code) in dates.POSTABLE_STATES
            ]
            if starts:
                found[key] = min(starts)
    return found


def _window_rows(entity_codes: Sequence[str]) -> tuple[Any, tuple[Any, ...]]:
    """The state rows of the window's periods, as a join and its conditions: the periods of
    ``entity_codes`` that are still postable and have a close run whose first period-end step is
    ``SUCCEEDED``."""
    run, state = close_run.c, period_state.c
    closed_by_a_run = exists().where(
        run.tenant_id == state.tenant_id,
        run.entity_id == state.entity_id,
        run.book_code == state.book_code,
        run.period_id == state.period_id,
        run.steps.contains(_FIRST_STEP_DONE),
    )
    joined = period_state.join(
        legal_entity,
        and_(legal_entity.c.tenant_id == state.tenant_id, legal_entity.c.id == state.entity_id),
    ).join(period, and_(period.c.tenant_id == state.tenant_id, period.c.id == state.period_id))
    conditions = (
        legal_entity.c.code.in_(sorted(entity_codes)),
        state.state.in_(sorted(dates.POSTABLE_STATES)),
        closed_by_a_run,
    )
    return joined, conditions


def _window_statement(entity_codes: Sequence[str], *, nowait: bool = False) -> Select[tuple[UUID]]:
    """The state rows of the window's periods (``_window_rows``), locked ``FOR SHARE`` in the
    order period start, then id (dev-guide DG-KRN-DB-08 (1c)). A row a lock decision holds is
    waited for and read again: once that period is closed it is no row of a window. With
    ``nowait`` — under a ledger chain head (rev 1.218) — such a row is not waited for: the
    statement fails at once (SQLSTATE 55P03)."""
    joined, conditions = _window_rows(entity_codes)
    return (
        select(period_state.c.id)
        .select_from(joined)
        .where(*conditions)
        .order_by(period.c.start_date, period_state.c.id)
        .with_for_update(read=True, of=period_state, nowait=nowait)
    )


def _frontier_statement(entity_codes: Sequence[str]) -> Select[tuple[str, str, date]]:
    """Per entity and book that has a window: the last day of its latest window period. The rows
    are those of ``_window_statement``, read without a lock — the computation holds them."""
    joined, conditions = _window_rows(entity_codes)
    return (
        select(legal_entity.c.code, period_state.c.book_code, func.max(period.c.end_date))
        .select_from(joined)
        .where(*conditions)
        .group_by(legal_entity.c.code, period_state.c.book_code)
    )


def _first_window_row_at_once(session: Session, entity_codes: Sequence[str]) -> Any:
    """``_window_statement`` asked NOWAIT, inside a savepoint: a row a lock decision holds fails
    the statement (SQLSTATE 55P03), the savepoint gives the transaction back in a state that can
    still answer, and the command is refused by name (PRD ERR-98) — nothing was waited for, so
    the kernel's ``LOCK_TIMEOUT`` sentence would be untrue of it. The rows the statement did
    take stay shared when the savepoint is released."""
    try:
        with session.begin_nested():
            return session.execute(_window_statement(entity_codes, nowait=True)).first()
    except DBAPIError as error:
        if db_errors.sqlstate(error) != db_errors.LOCK_NOT_AVAILABLE:
            raise
        raise period_lock_in_flight() from error


def _window_rows_held(uow: UnitOfWork, entity_codes: Sequence[str]) -> Mapping[str, date] | None:
    """None outside a window. Inside one — ``_window_statement`` found, and now holds, a row —
    the frontier of each scope that has a window: the day after the last day of its latest
    window period (item CLO-GATE-RUN-2; one read more, and only inside a window). Read under the
    scope of the computation that asks — the tenant's every entity, and ``computation._persist``
    refuses any other (05 TXN-10) — so what a computation marks does not depend on whose command
    computed it (supervisor ruling R-42 (d)). The read widens nothing itself (dev-guide rev
    1.245): it is as wide as its caller. Its callers are a computation (``window_held``) and the
    two functions below, each of which opens the tenant's scope around it first (rev 1.218).

    Dev-guide DG-KRN-DB-08 (1c) rev 1.218 (finding F4 of the independent review of 2026-10-01):
    a transaction that holds a ledger chain head waits for no state row. Under one the read is
    NOWAIT: a row a lock decision holds ends the command at once — 409 ``lock-conflict`` under
    rule ``PERIOD_LOCK_IN_FLIGHT`` (PRD ERR-98), the head released and nothing waited for."""
    if not entity_codes:
        return None
    if locking.holds_chain_head(uow.session):
        first = _first_window_row_at_once(uow.session, entity_codes)
    else:
        first = uow.session.execute(_window_statement(entity_codes)).first()
    if first is None:
        return None
    return {
        scope_key(str(code), str(getattr(book, "value", book))): last + timedelta(days=1)
        for code, book, last in uow.session.execute(_frontier_statement(entity_codes))
    }


def hold_windows(uow: UnitOfWork, group_ids: Iterable[UUID]) -> None:
    """The window rows of ``group_ids``, taken BEFORE the transaction takes a ledger chain head
    (dev-guide DG-KRN-DB-08 (1c) rev 1.218; 04 DB-07 rev 1.229; finding F4 of the independent
    review of 2026-10-01).

    ``computation.persist`` reads the window before ITS first write. A command that posts before
    it computes — the approval of a manual adjustment — or that computes a second group after
    the first one posted — a combination's leave, a legacy import of progress or of modifications
    — reached that read with the book's chain head held: while a lock decision held a state row
    the command waited up to ``lock_timeout``, and every posting of the book in the workspace
    queued behind it. Called first, this read waits with no head held, and the reads inside
    ``persist`` then find their rows held.

    The entities are those a bundle of the groups names (``bundles.entity_codes``: contracting
    and performing). Both reads run under the tenant's scope whoever calls — a person of one
    entity, an approval's hook, an import narrowed to its uploader's scope: which rows a
    transaction shares with a lock decision must not depend on who asked. Nothing is returned."""
    wanted = sorted(set(group_ids))
    if not wanted:
        return
    with system_entity_scope(uow.session):
        _window_rows_held(uow, bundles.entity_codes(uow.session, wanted))


def refuse_policy_change_a_lock_met(uow: UnitOfWork, group_id: UUID) -> None:
    """Serialize an approved policy change with locks of the group's entities.

    An override has no stream append, so the appender's check cannot see it. Share the
    close windows before publishing the approval. A lock decided after this transaction's
    record cutoff makes the decision stale; retry records the approval after the lock.
    The caller holds the group and contract rows, and skips contracts still in DRAFT.
    """
    session = uow.session
    with system_entity_scope(session):
        codes = bundles.entity_codes(session, [group_id])
        _window_rows_held(uow, codes)
        met = session.execute(
            select(period_lock.c.id)
            .join(
                legal_entity,
                (legal_entity.c.tenant_id == period_lock.c.tenant_id)
                & (legal_entity.c.id == period_lock.c.entity_id),
            )
            .where(
                legal_entity.c.code.in_(codes),
                period_lock.c.cutoff_known_at > bundles.record_cutoff(session, uow.now),
            )
            .limit(1)
        ).first()
    if met is not None:
        raise period_state_moved()


def refuse_appends_a_lock_met(uow: UnitOfWork, group_ids: Iterable[UUID]) -> None:
    """PRD ERR-72, rule ``PERIOD_STATE_MOVED``, for a transaction that records events and stores
    no computation of them (04 §14.1 "A command recorded before a lock" rev 1.229; supervisor
    ruling R-122 (j); item PIN-WINDOW-APPENDER-1).

    The pin stands where a computation is stored (``computation._refuse_a_lock_met``). A
    transaction that appends to a stream and stores no computation never gets there: a command
    whose group is over the obligation budget, or whose engine ran over its time, defers the
    computation; a computation the engine refused, or that crashed, is stored without a version;
    an import of recorded facts and an adapter's document append and leave the group to a later
    computation; an approved SSP override appends its line attributes. The event keeps the stamp
    of this transaction. A period lock decided after that stamp froze its datasets without the
    event, and the computation that reads it later — a job, which records nothing and is not
    judged — would write a version that counts as known at the lock's cutoff.

    So such a transaction asks at its end, for the groups it names: those whose stream ends in an
    event recorded in THIS transaction (the stream is held, so what it appended is the head);
    their window rows, shared as a computation shares them — a lock decision in flight is waited
    for, or, under a ledger chain head, refused at once (``_window_rows_held``); then the LOCK
    records of the groups' entities, and one whose cutoff is later than this transaction's record
    cutoff ends it 409 ``lock-conflict`` before it commits. Sent again, the events are recorded
    after the lock. A transaction that recorded nothing in these groups reads one statement and
    is not judged; nor is what it recorded on a DRAFT — nothing of a draft is in a frozen dataset
    or in the ledger, and its activation records events of its own.

    The reads run under the tenant's scope whoever calls, as those of ``hold_windows`` do."""
    wanted = sorted(set(group_ids))
    if not wanted:
        return
    session = uow.session
    member = combination_group_member
    with system_entity_scope(session):
        heads = (
            member.join(
                contract,
                and_(
                    contract.c.tenant_id == member.c.tenant_id,
                    contract.c.id == member.c.contract_id,
                ),
            )
        ).join(
            contract_event,
            and_(
                contract_event.c.tenant_id == contract.c.tenant_id,
                contract_event.c.contract_id == contract.c.id,
                contract_event.c.stream_version == contract.c.head_stream_version,
            ),
        )
        appended = sorted(
            set(
                session.execute(
                    select(member.c.combination_group_id)
                    .select_from(heads)
                    .where(
                        member.c.combination_group_id.in_(wanted),
                        member.c.valid_to_known_at.is_(None),
                        contract.c.status != ContractStatus.DRAFT.value,
                        contract_event.c.recorded_at == func.transaction_timestamp(),
                    )
                ).scalars()
            )
        )
        if not appended:
            return
        codes = bundles.entity_codes(session, appended)
        _window_rows_held(uow, codes)
        met = session.execute(
            select(period_lock.c.id)
            .select_from(
                period_lock.join(
                    legal_entity,
                    and_(
                        legal_entity.c.tenant_id == period_lock.c.tenant_id,
                        legal_entity.c.id == period_lock.c.entity_id,
                    ),
                )
            )
            .where(
                legal_entity.c.code.in_(codes),
                period_lock.c.cutoff_known_at > bundles.record_cutoff(session, uow.now),
            )
            .limit(1)
        ).first()
    if met is not None:
        raise period_state_moved()


@dataclass(frozen=True, slots=True)
class Held:
    """What a computation holds before it writes (``window_held``): the group's mark, read under
    the group's row lock, whether the computation is inside a window, and inside one the
    frontier of each scope that has a window."""

    mark: Mapping[str, str]
    in_window: bool
    frontier: Mapping[str, date] = dataclasses.field(default_factory=dict)


def window_held(uow: UnitOfWork, bundle: InputBundle, group_id: UUID) -> Held:
    """The locks of a computation of ``bundle`` that concern the mark, taken before it writes
    (module docstring): the group row ``FOR UPDATE`` — a close run's step and a computation of one
    group never read each other half done — and, inside a window, the state rows of the window's
    periods ``FOR SHARE``. Both are held to the end of the transaction.

    Called by ``computation._persist`` alone (dev-guide DG-ARC-16 (3), rev 1.245): the window
    read is as wide as its caller's scope, and only a computation runs under the tenant's. A
    caller outside a computation would hold the rows its own scope shows and no more; it decides
    its scope first, and the architecture test fails until it is listed."""
    mark = dict(repo.lock_group(uow.session, group_id)["period_ends_open"] or {})
    frontier = _window_rows_held(uow, [entity.code for entity in bundle.entities])
    return Held(mark, frontier is not None, frontier or {})


def after_computation(bundle: InputBundle, held: Held) -> dict[str, str] | None:
    """``period_ends_open`` of the group once the computation of ``bundle`` is its head, or None
    when it stays as it is (module docstring). ``held`` is what ``window_held`` returned before
    the computation wrote: outside a window no pass runs and nothing is read. An entry that
    exists is only ever lowered; a scope without an entry is given one — what the dry passes
    leave unposted, at most the scope's frontier, and the frontier when they leave nothing (item
    CLO-GATE-RUN-2). A refused dry pass proves nothing posted, so it sets no entry at a
    frontier."""
    if not held.in_window:
        return None
    frontier = held.frontier
    try:
        found = _first_unposted(bundle)
    except EngineError:
        found = _earliest_postable(bundle, held.mark)
        frontier = {}
    lowered = dict(held.mark)
    for key, first in found.items():
        if key in lowered:
            if first.isoformat() < str(lowered[key]):
                lowered[key] = first.isoformat()
        else:
            lowered[key] = min(first, frontier.get(key, first)).isoformat()
    for key, day in frontier.items():
        # nothing of this scope is unposted: its period ends are posted through its window
        lowered.setdefault(key, day.isoformat())
    return None if lowered == held.mark else lowered


def passed(
    uow: UnitOfWork,
    group_ids: Sequence[UUID],
    key: str,
    period_start: date,
    period_end: date,
    *,
    earliest_postable: bool,
) -> None:
    """The first period-end step of a close run of the period ``period_start`` to ``period_end``
    passed over ``group_ids`` — rows it holds locked: their entry ``key`` is the day after
    ``period_end`` (module docstring), for a group whose period ends are recorded as posted up
    to the period (item CLO-GATE-RUN-2). When the period is the ``earliest_postable`` one of
    the entity and book that is every group: one without an entry, and one whose entry lies
    in a closed period. Otherwise it is a group that holds an entry on or after
    ``period_start``: while an earlier period is postable an entry before ``period_start`` is
    never raised, whoever calls, and a group without an entry stays unmarked."""
    principal = uow.principal
    entry = {key: (period_end + timedelta(days=1)).isoformat()}
    column = combination_group.c.period_ends_open
    markable = (
        ()
        if earliest_postable
        else (and_(column.has_key(key), cast(column[key].astext, Date) >= period_start),)
    )
    for start in range(0, len(group_ids), _CHUNK):
        uow.session.execute(
            update(combination_group)
            .where(combination_group.c.id.in_(group_ids[start : start + _CHUNK]), *markable)
            .values(
                period_ends_open=combination_group.c.period_ends_open.op("||")(
                    bindparam("entry", entry, type_=JSONB)
                ),
                updated_at=uow.now,
                updated_by=principal.id,
                updated_by_kind=principal.kind.value,
                row_version=combination_group.c.row_version + 1,
            )
        )
