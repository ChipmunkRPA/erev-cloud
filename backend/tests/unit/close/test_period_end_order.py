"""Which earlier period refuses a close run's period-end step (supervisor rulings R-112 (a) and
R-114 (a); 04 T-CLS-01 "Period-end steps"; 05 RCP-08; ``period_end._earlier``), without a database.

A step seals the ``TIME`` amounts of the run's own period. An earlier period refuses it when a
group's ``TIME`` intents for that period do not net to zero in some account role and currency,
transaction or functional; a set that nets to zero in every role — a posted amount the engine
emits again with its own reversal — is no unposted period end.

The first period-end step is refused over a mark as well (item CLO-GATE-RUN-2; 04 T-CLS-01 rev
1.228; ``period_end._group_lines``, ``period_end._postable_from``): a mark before the run's period
names the earliest POSTABLE period that ends on or after it and starts before the run's period. A
mark with no such period lies in a closed period and says no more than the closed periods do.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, date, datetime
from types import SimpleNamespace
from typing import Any
from uuid import UUID

import pytest
from erev_api.domain.close import period_end, run_inputs
from erev_api.domain.close.gates import PeriodScope
from erev_api.domain.contracts import computation
from erev_engine.bundle import IntentLine, PostingIntent
from sqlalchemy.dialects import postgresql

ENTITY = "AVM-US"
JULY, AUGUST, SEPTEMBER, OCTOBER = "FY2026-P07", "FY2026-P08", "FY2026-P09", "FY2026-P10"
DAYS = {
    JULY: (date(2026, 7, 1), date(2026, 7, 31)),
    AUGUST: (date(2026, 8, 1), date(2026, 8, 31)),
    SEPTEMBER: (date(2026, 9, 1), date(2026, 9, 30)),
    OCTOBER: (date(2026, 10, 1), date(2026, 10, 31)),
}
NIL = UUID(int=0)
SCOPE = PeriodScope(
    state_id=NIL,
    entity_id=NIL,
    entity_code=ENTITY,
    functional_currency="USD",
    book_code="ASC606",
    period_id=NIL,
    period_key=SEPTEMBER,
    period_name="Sep 2026",
    start_date=date(2026, 9, 1),
    end_date=date(2026, 9, 30),
    state="open",
    current_lock_id=None,
    row_version=1,
)


def _line(
    side: str, role: str, amount: int, *, txn: int | None = None, currency: str = "USD"
) -> IntentLine:
    """One intent line of ``amount`` functional minor units (and as many transaction ones, or
    ``txn``)."""
    return IntentLine(
        line_key=f"{side}:{role}",
        side=side,
        account_role=role,
        clearing_purpose=None,
        counterparty_entity=None,
        account_code="0000",
        amount_txn=amount if txn is None else txn,
        amount_functional=amount,
        txn_currency=currency,
        functional_currency="USD",
        dimensions={},
        source_event_key=None,
        trace_node_id="node",
    )


def _intent(
    period_key: str,
    *lines: IntentLine,
    kind: str = "LOSS_PROVISION",
    posting_class: str = "TIME",
    entity: str = ENTITY,
    subject: str = "PRJ-CB-2026-01@AVM-US",
) -> PostingIntent:
    return PostingIntent(
        entry_key=f"{period_key}:{kind}:{subject}",
        book_code="ASC606",
        entity=entity,
        posting_period_key=period_key,
        origin_period_key=None,
        entry_kind=kind,
        posting_class=posting_class,
        subject_key=subject,
        reason_code=None,
        lines=lines,
    )


def _provision(period_key: str, amount: int, subject: str) -> PostingIntent:
    return _intent(
        period_key,
        _line("D", "LOSS_EXPENSE", amount),
        _line("C", "LOSS_PROVISION", amount),
        subject=subject,
    )


def _reversal(period_key: str, amount: int, subject: str) -> PostingIntent:
    return _intent(
        period_key,
        _line("D", "LOSS_PROVISION", amount),
        _line("C", "LOSS_EXPENSE", amount),
        subject=subject,
    )


def test_an_amount_of_an_earlier_period_names_it() -> None:
    """R-112 (a): a period end no close run has posted — August's reclass of a contract asset."""
    reclass = _intent(
        AUGUST,
        _line("D", "CONTRACT_ASSET", 5_000_000),
        _line("C", "CONTRACT_LIABILITY", 5_000_000),
        kind="NETTING_RECLASS",
    )
    assert period_end._earlier([reclass], SCOPE, DAYS) == (date(2026, 8, 31), AUGUST)


def test_a_set_that_nets_to_zero_in_every_role_is_no_unposted_period_end() -> None:
    """R-114 (a): the provision of August, posted, which the engine emits again under the loss
    unit's key together with the reversal of the posted one (the R-11 gap): 3,076.92 each way."""
    again = _provision(AUGUST, 307_692, "PRJ-CB-2026-01#LOSS")
    undone = _reversal(AUGUST, 307_692, "PRJ-CB-2026-01@AVM-US")
    assert period_end._earlier([again, undone], SCOPE, DAYS) is None
    # ... and a pair that does not cancel does: 3,076.92 emitted, 3,000.00 reversed
    partly = _reversal(AUGUST, 300_000, "PRJ-CB-2026-01@AVM-US")
    assert period_end._earlier([again, partly], SCOPE, DAYS) == (date(2026, 8, 31), AUGUST)


def test_the_functional_amount_counts_beside_the_transaction_amount() -> None:
    """A remeasurement moves the functional carrying only (JET-10a): its transaction amounts are
    zero, and it is a period end all the same. Two currencies never net against each other."""
    remeasured = _intent(
        AUGUST,
        _line("D", "CONTRACT_LIABILITY", 5_000, txn=0, currency="EUR"),
        _line("C", "FX_GAIN_LOSS", 5_000, txn=0, currency="EUR"),
        kind="FX_REMEASUREMENT",
    )
    assert period_end._earlier([remeasured], SCOPE, DAYS) == (date(2026, 8, 31), AUGUST)
    euros = _intent(AUGUST, _line("D", "LOSS_EXPENSE", 0, txn=100, currency="EUR"))
    dollars = _intent(AUGUST, _line("C", "LOSS_EXPENSE", 0, txn=100, currency="USD"))
    assert period_end._earlier([euros, dollars], SCOPE, DAYS) == (date(2026, 8, 31), AUGUST)


def test_only_earlier_time_amounts_of_the_runs_entity_count() -> None:
    own = _provision(SEPTEMBER, 100, "S")  # the run's own period: sealed, not refused
    later = _provision(OCTOBER, 100, "S")  # left to its own run
    event = _intent(AUGUST, _line("D", "LOSS_EXPENSE", 100), posting_class="EVENT")
    other = _intent(AUGUST, _line("D", "LOSS_EXPENSE", 100), entity="AVM-UK")
    unknown = _intent("FY2025-P12", _line("D", "LOSS_EXPENSE", 100))  # no period of the calendar
    assert period_end._earlier([own, later, event, other, unknown], SCOPE, DAYS) is None


def test_the_earliest_such_period_is_named() -> None:
    """The closes are run in order, so the refusal names the first period that needs one; a
    period whose set nets to zero is passed over."""
    july = _provision(JULY, 100, "A")
    august = _provision(AUGUST, 200, "B")
    assert period_end._earlier([august, july], SCOPE, DAYS) == (date(2026, 7, 31), JULY)
    settled = [_provision(JULY, 100, "A"), _reversal(JULY, 100, "A2"), august]
    assert period_end._earlier(settled, SCOPE, DAYS) == (date(2026, 8, 31), AUGUST)


# --- the mark the first period-end step meets (item CLO-GATE-RUN-2) -------------------------------

KEY = "AVM-US|ASC606"
WAITED_FOR = (date(2026, 8, 31), AUGUST)  # (last day, period key) of the postable period named


class _FirstStep:
    """``period_end._group_lines`` over stubs: the group rows as the step locks them, the
    postable period each mark waits for (None: every period from the mark to the run's is
    closed), a pass that has nothing to post — and, since item CLOSE-PASS-BEHIND-GROUP-1, the
    index of the bundle and the ways the bundle is behind its group (``behind``: none unless a
    test names them)."""

    def __init__(
        self,
        monkeypatch: pytest.MonkeyPatch,
        marks: Mapping[UUID, Mapping[str, str]],
        waits_for: Mapping[date, tuple[date, str] | None],
        behind: Mapping[UUID, tuple[str, ...]] | None = None,
    ) -> None:
        self.asked: list[date] = []
        self.built: list[UUID] = []
        self.questioned: list[tuple[UUID, UUID]] = []  # (bundle's group, index's group)
        self.engine: list[UUID] = []
        self._read: dict[date, tuple[date, str] | None] = {}

        def lock_group(session: object, group_id: UUID) -> dict[str, Any]:
            mark = dict(marks[group_id])
            return {"code": f"G-{group_id.int}", "dirty_since": None, "period_ends_open": mark}

        def postable_from(session: object, scope: PeriodScope, day: date) -> Any:
            self.asked.append(day)
            return waits_for[day]

        def build(session: object, group_id: UUID, *rest: object) -> Any:
            self.built.append(group_id)
            return SimpleNamespace(entities=(), group_id=group_id, trigger="CLOSE_RELEASE")

        def index(session: object, bundle: Any) -> Any:
            return SimpleNamespace(of=bundle.group_id)

        def behind_its_group(uow: object, bundle: Any, found: Any) -> tuple[str, ...]:
            self.questioned.append((bundle.group_id, found.of))
            return tuple((behind or {}).get(bundle.group_id, ()))

        def nothing_to_post(bundle: Any, pass_name: str) -> Any:
            self.engine.append(bundle.group_id)
            return SimpleNamespace(books=())

        monkeypatch.setattr(period_end.repo, "lock_group", lock_group)
        monkeypatch.setattr(period_end, "_postable_from", postable_from)
        monkeypatch.setattr(period_end.bundles, "build", build)
        monkeypatch.setattr(period_end.bundles, "index", index)
        monkeypatch.setattr(period_end.computation, "behind_its_group", behind_its_group)
        monkeypatch.setattr(period_end, "engine_pass", nothing_to_post)

    def over(self, group_id: UUID, pass_name: str = period_end.PASSES[0]) -> Any:
        uow: Any = SimpleNamespace(session=object(), now=datetime(2026, 10, 5, tzinfo=UTC))
        return period_end._group_lines(
            uow,
            SCOPE,
            group_id,
            pass_name,
            None,
            first_entry_no=1,
            waited_for=self._read if pass_name == period_end.PASSES[0] else None,
        )


def test_a_mark_before_the_period_refuses_the_first_step_by_the_postable_period_it_waits_for(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Review finding F1: a mark of 1 Jul 2026 while August is postable refuses September's first
    period-end step naming August — before the group's bundle is built — and the period a mark
    waits for is read once in the step, however many groups hold that mark."""
    one, two = UUID(int=1), UUID(int=2)
    july = {KEY: "2026-07-01"}
    step = _FirstStep(monkeypatch, {one: july, two: july}, {date(2026, 7, 1): WAITED_FOR})
    assert step.over(one) == period_end._GroupPass(
        code="G-1", lines=[], entries=0, earlier=WAITED_FOR
    )
    assert step.over(two) == period_end._GroupPass(
        code="G-2", lines=[], entries=0, earlier=WAITED_FOR
    )
    assert step.built == []
    assert step.asked == [date(2026, 7, 1)]


def test_a_mark_in_a_closed_period_does_not_refuse_the_first_step(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A mark of 1 Jul 2026 with every period from July to the run's closed — the mark a waived
    quarantine leaves when its period locks — says no more than the closed periods do: the group
    is passed like one without a mark. Until the second part of rev 1.228 the step was refused
    naming the closed period, for which no close run can be started."""
    one = UUID(int=1)
    step = _FirstStep(monkeypatch, {one: {KEY: "2026-07-01"}}, {date(2026, 7, 1): None})
    assert step.over(one) == period_end._GroupPass(code="G-1", lines=[], entries=0, earlier=None)
    assert step.built == [one]
    assert step.asked == [date(2026, 7, 1)]


def test_a_mark_that_does_not_lie_before_the_period_is_not_asked_about(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A mark on the period's first day or later, no mark, and a mark of another entity or book:
    each is passed and no period is read for it."""
    marks: dict[UUID, dict[str, str]] = {
        UUID(int=1): {KEY: "2026-09-01"},
        UUID(int=2): {KEY: "2026-10-01"},
        UUID(int=3): {},
        UUID(int=4): {"AVM-UK|ASC606": "2026-01-01", "AVM-US|IFRS15": "2026-01-01"},
    }
    step = _FirstStep(monkeypatch, marks, {})
    for group_id in marks:
        assert step.over(group_id).earlier is None
    assert step.built == list(marks)
    assert step.asked == []


def test_the_release_and_the_reclass_read_no_mark(monkeypatch: pytest.MonkeyPatch) -> None:
    """Only the first period-end step is refused over a mark: it is the step that writes it."""
    one = UUID(int=1)
    step = _FirstStep(monkeypatch, {one: {KEY: "2026-07-01"}}, {date(2026, 7, 1): WAITED_FOR})
    for pass_name in period_end.PASSES[1:]:
        assert step.over(one, pass_name).earlier is None
    assert step.built == [one, one]
    assert step.asked == []


def test_a_group_its_bundle_is_behind_is_left_out_before_the_engine_runs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Item CLOSE-PASS-BEHIND-GROUP-1 (04 T-CLS-01 "Period-end steps" rev 1.304): under the
    group's row lock, with the bundle built at the step's cutoff, each pass asks the
    computation's own question — ``computation.behind_its_group``, over the bundle and ITS index
    — and for a group the bundle is behind, in any of the three ways, it answers None, as for a
    group that became dirty: the engine does not run and nothing is posted. A group the bundle
    is not behind is passed as before, and asked once."""
    late, level = UUID(int=1), UUID(int=2)
    for way in (computation.BEHIND_EVENT, computation.BEHIND_MARK, computation.BEHIND_HEAD):
        for pass_name in period_end.PASSES:
            step = _FirstStep(monkeypatch, {late: {}, level: {}}, {}, behind={late: (way,)})
            assert step.over(late, pass_name) is None, (way, pass_name)
            assert step.over(level, pass_name) == period_end._GroupPass(
                code="G-2", lines=[], entries=0, earlier=None
            )
            assert step.built == [late, level]
            assert step.questioned == [(late, late), (level, level)]
            assert step.engine == [level]


def test_a_mark_before_the_period_still_refuses_before_the_bundle_is_asked_about(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The order of the locked row is unchanged: the refusal of a mark before the run's period
    (rev 1.228) comes before any bundle, so before the question whether one is behind."""
    one = UUID(int=1)
    step = _FirstStep(
        monkeypatch,
        {one: {KEY: "2026-07-01"}},
        {date(2026, 7, 1): WAITED_FOR},
        behind={one: (computation.BEHIND_HEAD,)},
    )
    assert step.over(one).earlier == WAITED_FOR
    assert (step.built, step.questioned, step.engine) == ([], [], [])


def test_a_group_left_out_is_counted_as_skipped_and_is_not_marked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``post_pass``: of two clean groups the second is behind its bundle. Every pass counts one
    group passed and one skipped, and the first step hands the writer of the mark the group it
    passed alone — the mark a computation left on the other stands, and the gate reads it."""
    passed_group, late = UUID(int=7), UUID(int=8)
    written: list[list[UUID]] = []

    def group_lines(
        uow: Any, scope: Any, group: UUID, pass_name: str, *rest: Any, **named: Any
    ) -> Any:
        if group == late:
            return None
        return period_end._GroupPass(code="G-7", lines=[], entries=0, earlier=None)

    monkeypatch.setattr(
        period_end.run_inputs,
        "read",
        lambda session, scope, known_at: run_inputs.RunInputs(rates="r" * 64, registry="p" * 64),
    )
    monkeypatch.setattr(
        period_end, "_groups", lambda session, scope: [(passed_group, False), (late, False)]
    )
    monkeypatch.setattr(period_end, "_group_lines", group_lines)
    monkeypatch.setattr(period_end, "_next_period", lambda session, scope: OCTOBER)
    monkeypatch.setattr(period_end, "_no_earlier_postable", lambda session, scope: True)
    monkeypatch.setattr(
        period_end.period_ends,
        "passed",
        lambda uow, groups, key, first, last, **named: written.append(list(groups)),
    )
    uow: Any = SimpleNamespace(session=object(), now=datetime(2026, 10, 5, tzinfo=UTC))
    for pass_name in period_end.PASSES:
        result = period_end.post_pass(
            uow, close_run_id=NIL, close_run_no="CLS-000001", scope=SCOPE, pass_name=pass_name
        )
        assert (result.groups, result.groups_skipped, result.lines) == (1, 1, 0)
    assert written == [[passed_group]]  # the first step alone, and the passed group alone


@pytest.mark.parametrize("earliest_postable", [True, False])
def test_only_the_first_period_end_step_meets_the_mark_and_writes_it(
    monkeypatch: pytest.MonkeyPatch, earliest_postable: bool
) -> None:
    """``post_pass``: the first period-end step alone hands ``_group_lines`` the marks it met —
    one record for the whole step — and alone calls the writer, for the groups it passed, with
    the period's days and whether an earlier period is postable. The release and the reclass
    read no mark and write none.

    The first step alone also reads what the run's passes can read beside the contracts (item
    CLO-RATE-AFTER-RUN-1; 04 T-CLS-01 "What a run read", rev 1.291) — FIRST, before it lists a
    group, at the step's own instant — and answers it; the other two read nothing of it."""
    group_id = UUID(int=7)
    handed: dict[str, list[Any]] = {}
    written: list[tuple[Any, ...]] = []
    order: list[str] = []
    read = run_inputs.RunInputs(rates="r" * 64, registry="p" * 64)

    def inputs(session: Any, scope: Any, known_at: datetime) -> Any:
        assert (scope, known_at) == (SCOPE, datetime(2026, 10, 5, tzinfo=UTC))
        order.append("read")
        return read

    def groups(session: Any, scope: Any) -> Any:
        order.append("groups")
        return [(group_id, False)] * 2

    def group_lines(
        uow: Any, scope: Any, group: UUID, pass_name: str, *rest: Any, **named: Any
    ) -> Any:
        handed.setdefault(pass_name, []).append(named["waited_for"])
        return period_end._GroupPass(code="G-7", lines=[], entries=0, earlier=None)

    def passed(uow: Any, groups: Any, key: str, first: date, last: date, **named: Any) -> None:
        written.append((list(groups), key, first, last, named))

    monkeypatch.setattr(period_end.run_inputs, "read", inputs)
    monkeypatch.setattr(period_end, "_groups", groups)
    monkeypatch.setattr(period_end, "_group_lines", group_lines)
    monkeypatch.setattr(period_end, "_next_period", lambda session, scope: OCTOBER)
    monkeypatch.setattr(
        period_end, "_no_earlier_postable", lambda session, scope: earliest_postable
    )
    monkeypatch.setattr(period_end.period_ends, "passed", passed)
    uow: Any = SimpleNamespace(session=object(), now=datetime(2026, 10, 5, tzinfo=UTC))
    for pass_name in period_end.PASSES:
        result = period_end.post_pass(
            uow, close_run_id=NIL, close_run_no="CLS-000001", scope=SCOPE, pass_name=pass_name
        )
        assert (result.groups, result.groups_skipped, result.lines) == (2, 0, 0)
        assert result.inputs == (read if pass_name == period_end.PASSES[0] else None)
    assert order == ["read", "groups", "groups", "groups"]
    first, release, reclass = period_end.PASSES
    assert handed[first][0] == {} and handed[first][0] is handed[first][1]
    assert handed[release] == [None, None] and handed[reclass] == [None, None]
    assert written == [
        (
            [group_id, group_id],
            KEY,
            SCOPE.start_date,
            SCOPE.end_date,
            {"earliest_postable": earliest_postable},
        )
    ]


def test_a_mark_lists_a_group_only_while_the_group_holds_a_member() -> None:
    """``_groups`` (item CLO-GROUPS-EMPTY-MEMBER-1; 04 T-CLS-01 rev 1.255): a computed group is
    listed when a member contract is the entity's or carries ledger lines of the entity in the
    book, or when it holds a mark of the scope AND a contract. The group a combination left
    empty holds a mark and no contract: a bundle cannot be built of it, so no step reads it."""
    statements: list[Any] = []

    class _Session:
        def execute(self, statement: Any) -> Any:
            statements.append(statement)
            return []

    session: Any = _Session()
    assert period_end._groups(session, SCOPE) == []
    sql = " ".join(str(statements[0].compile(dialect=postgresql.dialect())).split())
    holds_a_member = (
        "EXISTS (SELECT * FROM erev.contract WHERE erev.contract.tenant_id = "
        "erev.combination_group.tenant_id AND erev.contract.combination_group_id = "
        "erev.combination_group.id)"
    )
    marked = "(erev.combination_group.period_ends_open ? %(period_ends_open_1)s)"
    assert sql.startswith(
        "SELECT erev.combination_group.id, erev.combination_group.dirty_since "
        "FROM erev.combination_group WHERE erev.combination_group.head_computation_id IS NOT NULL "
        "AND ((EXISTS (SELECT * FROM erev.contract WHERE "
    )
    assert sql.endswith(f" OR {marked} AND ({holds_a_member})) ORDER BY erev.combination_group.id")
    assert sql.count(marked) == 1


def test_the_period_a_mark_waits_for_is_the_earliest_postable_one_before_the_runs() -> None:
    """``_postable_from``: of the run's entity and book, the periods that are ``open``,
    ``closing`` or ``reopened``, end on or after the mark and start before the run's period —
    the earliest of them; None when there is none."""
    statements: list[Any] = []
    found: list[Any] = [(date(2026, 8, 31), AUGUST)]

    class _Session:
        def execute(self, statement: Any) -> Any:
            statements.append(statement)
            return SimpleNamespace(first=lambda: found[0])

    session: Any = _Session()
    assert period_end._postable_from(session, SCOPE, date(2026, 7, 1)) == WAITED_FOR
    found[0] = None
    assert period_end._postable_from(session, SCOPE, date(2026, 7, 1)) is None
    compiled = statements[0].compile(dialect=postgresql.dialect())
    sql = " ".join(str(compiled).split())
    assert sql.startswith(
        "SELECT erev.period.end_date, erev.period.period_key "
        "FROM erev.period_state JOIN erev.period ON "
    )
    assert "erev.period_state.entity_id = " in sql and "erev.period_state.book_code = " in sql
    assert "erev.period_state.state IN (__[POSTCOMPILE_state_1])" in sql
    assert "erev.period.end_date >= " in sql and "erev.period.start_date < " in sql
    assert sql.endswith("ORDER BY erev.period.start_date LIMIT %(param_1)s")
    values = list(compiled.params.values())
    assert ["closing", "open", "reopened"] in values
    assert date(2026, 7, 1) in values and SCOPE.start_date in values
    assert "FOR " not in sql
