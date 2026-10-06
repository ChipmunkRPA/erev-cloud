"""The mark of a contract group's period ends, without a database (item CLO-GATE-RUN-1; supervisor
rulings R-114 (b) and R-116 (e); 04 T-CON-03 rev 1.172 "Period-end mark"; 05 RCP-08 rev 1.111;
``erev_api.domain.contracts.period_ends``).

A computation moves the mark only inside a window, by the three passes run dry over its own
bundle; outside one it runs no pass and writes nothing. The engine is a stub here — the rule
under test is what the function does with a pass's intents; the real passes run in the database
witnesses, ``tests/domain/close/test_close_run_gate.py``. The read that finds the window is
compiled here and never run: it locks the state rows of the window's periods ``FOR SHARE`` in
one order (dev-guide DG-KRN-DB-08 (1c)); the waits it causes are witnessed on PostgreSQL.

Item CLO-GATE-RUN-2 (04 T-CON-03 rev 1.228; 05 RCP-08 rev 1.167): a mark moves forward only by
the run of the period it stands at. The writer of a close run's first period-end step marks a
group that holds an entry on or after the period's first day, and one that holds none only for
the earliest postable period; a computation inside a window gives a scope without an entry its
entry, at most at the window's frontier, and never raises one that exists."""

from __future__ import annotations

import dataclasses
from datetime import UTC, date, datetime
from types import SimpleNamespace
from typing import Any
from uuid import UUID

import pytest
from erev_api.db import locking
from erev_api.domain.contracts import period_ends
from erev_api.domain.platform import snapshot_dataset
from erev_engine.bundle import InputBundle, IntentLine, PostingIntent
from erev_engine.errors import EngineError
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session
from support import bundles

ENTITY = bundles.ENTITY_CODE  # "US01": the entity of ``bundles.minimal_contract``
BOOK = "ASC606"
KEY = f"{ENTITY}|{BOOK}"
AUGUST, SEPTEMBER, OCTOBER = "FY2026-P08", "FY2026-P09", "FY2026-P10"
GROUP_ID = UUID(int=7)


def _line(side: str, role: str, amount: int) -> IntentLine:
    return IntentLine(
        line_key=f"{side}:{role}",
        side=side,
        account_role=role,
        clearing_purpose=None,
        counterparty_entity=None,
        account_code="0000",
        amount_txn=amount,
        amount_functional=amount,
        txn_currency="USD",
        functional_currency="USD",
        dimensions={},
        source_event_key=None,
        trace_node_id="node",
    )


def _intent(
    period_key: str, *lines: IntentLine, entity: str = ENTITY, posting_class: str = "TIME"
) -> PostingIntent:
    return PostingIntent(
        entry_key=f"{entity}/{period_key}/{posting_class}/{len(lines)}",
        book_code=BOOK,
        entity=entity,
        posting_period_key=period_key,
        origin_period_key=None,
        entry_kind="LOSS_PROVISION",
        posting_class=posting_class,
        subject_key="subject",
        reason_code=None,
        lines=tuple(lines),
    )


def _provision(period_key: str, amount: int = 307_692, *, entity: str = ENTITY) -> PostingIntent:
    return _intent(
        period_key,
        _line("D", "LOSS_EXPENSE", amount),
        _line("C", "LOSS_PROVISION", amount),
        entity=entity,
    )


def _output(*intents: PostingIntent) -> Any:
    return SimpleNamespace(books=(SimpleNamespace(book_code=BOOK, posting_intents=intents),))


def _with_calendar(bundle: InputBundle, calendar: Any) -> InputBundle:
    return dataclasses.replace(bundle, entities=(calendar,))


class _World:
    """``window_held`` and ``after_computation`` over a stubbed group row, window and engine:
    what each pass emits is ``emitted[pass name]``; the calls are recorded."""

    def __init__(
        self,
        monkeypatch: pytest.MonkeyPatch,
        *,
        held: dict[str, str],
        window: bool,
        emitted: dict[str, tuple[PostingIntent, ...]] | None = None,
        refused: str | None = None,
        frontier: dict[str, date] | None = None,
    ) -> None:
        self.passes: list[tuple[str, str, tuple[tuple[str, int], ...]]] = []
        self.locked: list[UUID] = []
        self.windows: list[list[str]] = []
        emitted = emitted or {}

        def lock_group(session: object, group_id: UUID) -> dict[str, Any]:
            self.locked.append(group_id)
            return {"id": group_id, "period_ends_open": dict(held)}

        def engine_pass(bundle: InputBundle, pass_name: str) -> Any:
            self.passes.append((pass_name, bundle.trigger, bundle.group.previous_stream_heads))
            if pass_name == refused:
                raise EngineError("FX_RATE_MISSING", "no closing rate")
            return _output(*emitted.get(pass_name, ()))

        def window_rows_held(uow: object, codes: list[str]) -> dict[str, date] | None:
            """None outside a window; inside one, the frontier of each scope that has a window
            (none here unless the test names one)."""
            self.windows.append(list(codes))
            return dict(frontier or {}) if window else None

        monkeypatch.setattr(period_ends.repo, "lock_group", lock_group)
        monkeypatch.setattr(period_ends, "_window_rows_held", window_rows_held)
        monkeypatch.setattr(period_ends, "engine_pass", engine_pass)

    def after(self, bundle: InputBundle | None = None) -> dict[str, str] | None:
        """What ``computation.persist`` does: the locks before it writes, the mark at its end."""
        uow: Any = SimpleNamespace(session=object())
        value = bundles.minimal_contract() if bundle is None else bundle
        held = period_ends.window_held(uow, value, GROUP_ID)
        assert self.passes == []  # no pass runs before the computation has written
        return period_ends.after_computation(value, held)


def test_the_member_is_named_by_entity_and_book() -> None:
    assert period_ends.scope_key("AVM-US", "ASC606") == "AVM-US|ASC606"
    assert period_ends.PASSES == ("FX_REMEASUREMENT", "CLOSE_RELEASE", "NETTING_RECLASS")


def test_unposted_names_the_entity_and_the_period_of_a_net() -> None:
    """R-114 (a): a period end is unposted where the ``TIME`` intents of an entity and period do
    not net to zero in some role and currency; a set that cancels in every role, and an ``EVENT``
    intent, name nothing."""
    cancelled = (_provision(AUGUST), _provision(AUGUST, -307_692))
    found = period_ends.unposted(
        (
            *cancelled,
            _provision(SEPTEMBER),
            _provision(OCTOBER, entity="UK01"),
            _intent(AUGUST, _line("D", "REVENUE", 5), posting_class="EVENT"),
        )
    )
    assert found == {(ENTITY, SEPTEMBER), ("UK01", OCTOBER)}
    assert period_ends.unposted(cancelled) == frozenset()


def test_the_dry_bundle_is_the_computations_own_as_a_close_run_reads_it() -> None:
    """05 RCP-08 rev 1.111: the dry bundle is the computation's with the trigger ``CLOSE_RELEASE``
    and every event counted as included; nothing else of it changes."""
    bundle = bundles.minimal_contract()
    assert (bundle.trigger, bundle.group.previous_stream_heads) == ("COMMAND", ())
    dry = period_ends._dry(bundle)
    (contract_key,) = {event.contract_key for event in bundle.events}
    assert dry.trigger == "CLOSE_RELEASE"
    assert dry.group.previous_stream_heads == ((contract_key, 1),)
    assert (dry.events, dry.posted, dry.entities, dry.books, dry.fx_rates, dry.known_at) == (
        bundle.events,
        bundle.posted,
        bundle.entities,
        bundle.books,
        bundle.fx_rates,
        bundle.known_at,
    )


def test_outside_a_window_a_computation_runs_no_pass_and_writes_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    world = _World(
        monkeypatch,
        held={KEY: "2026-09-01"},
        window=False,
        emitted={"CLOSE_RELEASE": (_provision(AUGUST),)},
    )
    assert world.after() is None
    assert world.passes == []
    assert world.locked == [GROUP_ID]  # the group row is read under its lock either way
    assert world.windows == [[ENTITY]]  # the window is read once, for the bundle's entities


def test_inside_a_window_the_entry_is_lowered_to_the_earliest_unposted_period(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The three passes run dry, in the order a close runs them, over the dry bundle; the entry
    becomes the first day of the earliest period with a net over all three."""
    world = _World(
        monkeypatch,
        held={KEY: "2026-10-01"},
        window=True,
        emitted={
            "FX_REMEASUREMENT": (_provision(OCTOBER),),
            "CLOSE_RELEASE": (_provision(SEPTEMBER),),
            "NETTING_RECLASS": (_provision(AUGUST), _provision(AUGUST, -307_692)),
        },
    )
    assert world.after() == {KEY: "2026-09-01"}
    assert [name for name, _, _ in world.passes] == list(period_ends.PASSES)
    assert {trigger for _, trigger, _ in world.passes} == {"CLOSE_RELEASE"}
    assert all(heads != () for _, _, heads in world.passes)


def test_inside_a_window_a_later_periods_amounts_move_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The period under close is posted (the entry is the day after its last day): amounts of the
    next period, which its own run will post, leave the entry where it is."""
    world = _World(
        monkeypatch,
        held={KEY: "2026-10-01"},
        window=True,
        emitted={"NETTING_RECLASS": (_provision(OCTOBER),)},
    )
    assert world.after() is None
    assert len(world.passes) == 3


def test_a_computation_never_raises_an_entry(monkeypatch: pytest.MonkeyPatch) -> None:
    """Only a close run's first period-end step sets an entry forward: nets that begin later than
    the entry, or no net at all, leave it."""
    later = _World(
        monkeypatch,
        held={KEY: "2026-08-01"},
        window=True,
        emitted={"CLOSE_RELEASE": (_provision(SEPTEMBER),)},
    )
    assert later.after() is None
    none = _World(monkeypatch, held={KEY: "2026-08-01"}, window=True)
    assert none.after() is None


def test_a_scope_without_an_entry_gains_one(monkeypatch: pytest.MonkeyPatch) -> None:
    """A group no run of the scope has passed — a contract activated inside the window — is
    marked from the first day of its earliest unposted period, and another scope's entry stays."""
    world = _World(
        monkeypatch,
        held={"UK01|ASC606": "2026-10-01"},
        window=True,
        emitted={"CLOSE_RELEASE": (_provision(SEPTEMBER),)},
    )
    assert world.after() == {"UK01|ASC606": "2026-10-01", KEY: "2026-09-01"}


def test_a_refused_dry_pass_lowers_to_the_earliest_postable_period(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A pass the engine refuses says nothing about what is posted: the entries the group holds,
    and those of its contracting entities, go to the first day of the earliest postable period of
    their entity and book. Periods before it are closed and no pass posts into them."""
    calendar = bundles.entity(states={f"FY2026-P{month:02d}": "closed" for month in range(1, 9)})
    bundle = _with_calendar(bundles.minimal_contract(), calendar)
    world = _World(
        monkeypatch,
        held={KEY: "2026-10-01", "UK01|ASC606": "2026-10-01"},
        window=True,
        refused="CLOSE_RELEASE",
    )
    # UK01 is no entity of the bundle: its entry cannot be judged here and stays
    assert world.after(bundle) == {KEY: "2026-09-01", "UK01|ASC606": "2026-10-01"}
    assert [name for name, _, _ in world.passes] == ["FX_REMEASUREMENT", "CLOSE_RELEASE"]
    unmarked = _World(monkeypatch, held={}, window=True, refused="FX_REMEASUREMENT")
    assert unmarked.after(bundle) == {KEY: "2026-09-01"}  # the contracting entity's scope


# --- item CLO-GATE-RUN-2: a scope without an entry, and the writer of a run's first step ----------

FRONTIER = date(2026, 10, 1)  # the day after the last day of the window's latest period, September


def test_inside_a_window_a_scope_without_an_entry_is_set_at_its_frontier(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A group no run has passed is computed inside a window and its dry passes leave nothing
    unposted: its period ends are posted through the window, and the entry says so — the gate
    counts a group of the entity without one. A scope without a window gains nothing."""
    world = _World(monkeypatch, held={}, window=True, frontier={KEY: FRONTIER})
    assert world.after() == {KEY: "2026-10-01"}
    assert len(world.passes) == 3
    elsewhere = _World(monkeypatch, held={}, window=True, frontier={"UK01|ASC606": FRONTIER})
    assert elsewhere.after() == {"UK01|ASC606": "2026-10-01"}
    none = _World(monkeypatch, held={}, window=True)
    assert none.after() is None


def test_a_scope_without_an_entry_is_set_no_further_than_its_frontier(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """What the dry passes leave unposted decides the entry up to the frontier: an unposted
    period inside the window is named; one beyond it is not — the entry never says more than
    "posted through the window"."""
    inside = _World(
        monkeypatch,
        held={},
        window=True,
        frontier={KEY: FRONTIER},
        emitted={"CLOSE_RELEASE": (_provision(SEPTEMBER),)},
    )
    assert inside.after() == {KEY: "2026-09-01"}
    beyond = _World(
        monkeypatch,
        held={},
        window=True,
        frontier={KEY: date(2026, 9, 1)},
        emitted={"NETTING_RECLASS": (_provision(OCTOBER),)},
    )
    assert beyond.after() == {KEY: "2026-09-01"}


def test_an_entry_that_exists_is_never_set_at_the_frontier(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Only a close run's first period-end step moves an entry forward: a computation that finds
    nothing unposted leaves an entry that lies before the frontier where it is."""
    world = _World(monkeypatch, held={KEY: "2026-08-01"}, window=True, frontier={KEY: FRONTIER})
    assert world.after() is None


def test_a_refused_dry_pass_sets_no_entry_at_the_frontier(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A pass the engine refuses proves nothing posted: the contracting entity's scope goes to
    the first day of the earliest postable period, and no scope is set at a frontier."""
    calendar = bundles.entity(states={f"FY2026-P{month:02d}": "closed" for month in range(1, 9)})
    bundle = _with_calendar(bundles.minimal_contract(), calendar)
    world = _World(
        monkeypatch,
        held={},
        window=True,
        refused="CLOSE_RELEASE",
        frontier={KEY: date(2026, 11, 1), "UK01|ASC606": date(2026, 11, 1)},
    )
    assert world.after(bundle) == {KEY: "2026-09-01"}


def test_the_frontier_is_read_over_the_windows_rows_without_a_lock() -> None:
    """One read more inside a window (05 PERF-03 rev 1.167): per entity and book the last day of
    the latest window period — the rows of the locking read, which the computation holds, so
    this one locks nothing."""
    statement = period_ends._frontier_statement(["UK01", "US01"])
    sql = " ".join(str(statement.compile(dialect=postgresql.dialect())).split())
    assert sql.startswith(
        "SELECT erev.legal_entity.code, erev.period_state.book_code, "
        "max(erev.period.end_date) AS max_1 FROM erev.period_state JOIN "
    )
    assert sql.endswith("GROUP BY erev.legal_entity.code, erev.period_state.book_code")
    assert "EXISTS (SELECT * FROM erev.close_run WHERE" in sql
    assert "erev.close_run.steps @> " in sql
    assert "erev.period_state.state IN " in sql and "erev.legal_entity.code IN " in sql
    assert "FOR " not in sql


def _marking(*, earliest_postable: bool) -> str:
    """The statement ``passed`` writes, compiled."""
    statements: list[Any] = []
    uow: Any = SimpleNamespace(
        principal=SimpleNamespace(id=UUID(int=1), kind=SimpleNamespace(value="SYSTEM")),
        now=datetime(2026, 10, 5, tzinfo=UTC),
        session=SimpleNamespace(execute=statements.append),
    )
    period_ends.passed(
        uow,
        [GROUP_ID],
        KEY,
        date(2026, 9, 1),
        date(2026, 9, 30),
        earliest_postable=earliest_postable,
    )
    (statement,) = statements
    return " ".join(str(statement.compile(dialect=postgresql.dialect())).split())


def test_the_writer_marks_only_a_group_recorded_as_posted_up_to_the_period() -> None:
    """04 T-CON-03 rev 1.228, rule (1): while an earlier period is postable the first period-end
    step sets the entry of a group it passed only where the group holds an entry on or after
    the period's first day — an entry before it is never raised, whoever calls, and a group
    without one stays unmarked. For the earliest postable period it sets the entry of every
    group it passed: one without an entry, and one whose entry lies in a closed period, which
    says no more than the closed periods do. Before the rule, the statement set the entry of
    every group it was given, whatever the period."""
    holds = "(erev.combination_group.period_ends_open ? %(period_ends_open_1)s)"
    on_or_after = (
        "CAST((erev.combination_group.period_ends_open ->> %(period_ends_open_2)s) AS DATE) "
        ">= %(param_1)s"
    )
    groups = "WHERE erev.combination_group.id IN (__[POSTCOMPILE_id_1])"
    later = _marking(earliest_postable=False)
    assert "period_ends_open=(erev.combination_group.period_ends_open || %(entry)s::JSONB)" in later
    assert later.endswith(f"{groups} AND {holds} AND {on_or_after}")
    earliest = _marking(earliest_postable=True)
    assert (
        "period_ends_open=(erev.combination_group.period_ends_open || %(entry)s::JSONB)" in earliest
    )
    assert earliest.endswith(groups)


def test_the_read_that_finds_the_window_locks_its_state_rows_in_one_order() -> None:
    """Dev-guide DG-KRN-DB-08 (1c) (supervisor ruling of 2026-10-01 02:35 on item
    CLO-GATE-RUN-1): one statement takes the state rows of the window's periods ``FOR SHARE`` —
    the row lock a posting's DB-07 guard holds, which a lock decision's ``FOR UPDATE`` waits for
    — and only those rows (``OF period_state``), ordered by period start and then id, so that
    several windows are taken in one order. The rows are the postable periods of the bundle's
    entities with a close run whose first period-end step is ``SUCCEEDED``."""
    statement = period_ends._window_statement(["UK01", "US01"])
    sql = " ".join(str(statement.compile(dialect=postgresql.dialect())).split())
    assert sql.startswith("SELECT erev.period_state.id FROM erev.period_state JOIN ")
    assert sql.endswith(
        "ORDER BY erev.period.start_date, erev.period_state.id FOR SHARE OF period_state"
    )
    assert "EXISTS (SELECT * FROM erev.close_run WHERE" in sql
    assert "erev.close_run.steps @> " in sql
    assert "erev.period_state.state IN " in sql and "erev.legal_entity.code IN " in sql
    assert sql.count("FOR ") == 1 and "NOWAIT" not in sql and "SKIP LOCKED" not in sql
    assert period_ends._FIRST_STEP_DONE == [
        {"step_code": "FX_REMEASUREMENT", "status": "SUCCEEDED"}
    ]


def _text(statement: Any) -> str:
    return " ".join(str(statement.compile(dialect=postgresql.dialect())).split())


def test_under_a_ledger_chain_head_the_window_statement_does_not_wait() -> None:
    """Dev-guide DG-KRN-DB-08 (1c) rev 1.218 (finding F4 of the independent review of
    2026-10-01): asked ``nowait``, the window statement is the statement pinned above with
    ``NOWAIT`` — the same rows, the same order, the same lock. The default is unchanged."""
    waiting = period_ends._window_statement(["UK01", "US01"])
    at_once = period_ends._window_statement(["UK01", "US01"], nowait=True)
    assert _text(at_once) == _text(waiting) + " NOWAIT"
    assert _text(at_once).count("FOR ") == 1 and "SKIP LOCKED" not in _text(at_once)


def test_the_chain_head_mark_ends_with_its_transaction() -> None:
    """``locking.mark_chain_head`` marks the transaction, not the session: a savepoint inside it
    sees the mark, the next transaction of the same session does not."""
    session = Session()
    assert not locking.holds_chain_head(session)
    with session.begin():
        assert not locking.holds_chain_head(session)
        locking.mark_chain_head(session)
        assert locking.holds_chain_head(session)
        with session.begin_nested():
            assert locking.holds_chain_head(session)
        assert locking.holds_chain_head(session)
    assert not locking.holds_chain_head(session)
    with session.begin():
        assert not locking.holds_chain_head(session)


@pytest.mark.parametrize("under_a_head", [False, True])
def test_the_window_read_waits_only_while_no_chain_head_is_held(under_a_head: bool) -> None:
    """Finding F4, the backstop: ``_window_rows_held`` — the read of ``window_held`` and of
    ``hold_windows`` — asks its rows ``NOWAIT`` once the transaction holds a ledger chain head,
    and waits for them as before while it holds none. Fail-first: the read waited in both
    cases, with the head held and every posting of the book queued behind it."""
    statements: list[Any] = []

    class _Found:
        def first(self) -> None:
            return None

    def execute(statement: Any) -> _Found:
        statements.append(statement)
        return _Found()

    session = Session()
    with session.begin():
        if under_a_head:
            locking.mark_chain_head(session)
        session.execute = execute  # type: ignore[method-assign]
        uow: Any = SimpleNamespace(
            session=session,
            principal=SimpleNamespace(db_context=SimpleNamespace(entity_scope="*")),
        )
        assert period_ends._window_rows_held(uow, ["UK01", "US01"]) is None
    (read,) = statements
    assert _text(read).endswith("FOR SHARE OF period_state NOWAIT") is under_a_head
    assert _text(read).endswith("FOR SHARE OF period_state") is not under_a_head


def test_the_snapshot_copies_the_mark_with_its_group() -> None:
    """Supervisor ruling R-116 (e); 05 SBX-03 rev 1.111: the inventory classes ``combination_group``
    as a copied fact table and decides by table; the mark is neither a reference nor a credential
    column, so it travels as it is — entity codes are the same in the copy — while the head
    computation, a regenerated row, is nulled as before."""
    inventory = snapshot_dataset.inventory()
    rule = snapshot_dataset.RULES["combination_group"]
    assert rule.snapshot_class is snapshot_dataset.SnapshotClass.COPIED
    assert "combination_group" in inventory.names
    group = inventory.dataset("combination_group")
    assert "period_ends_open" not in group.nulled_on_export
    assert "period_ends_open" not in snapshot_dataset.EXCLUDED_COLUMNS.get(
        "combination_group", frozenset()
    )
    assert not [
        found
        for found in snapshot_dataset.references()
        if (found.table, found.column) == ("combination_group", "period_ends_open")
    ]
    mark = {"AVM-US|ASC606": "2026-10-01", "AVM-US|IFRS15": "2026-09-01"}
    row = {
        "id": GROUP_ID,
        "created_at": datetime(2026, 9, 30, 12, tzinfo=UTC),
        "head_computation_id": UUID(int=9),
        "inception_date": date(2026, 1, 1),
        "period_ends_open": mark,
    }
    exported = snapshot_dataset.export_row(group, row)
    assert exported["period_ends_open"] == mark
    assert exported["head_computation_id"] is None
    (decoded,) = snapshot_dataset.decode_rows(snapshot_dataset.encode_rows(group, [row]).content)
    assert decoded["period_ends_open"] == mark
