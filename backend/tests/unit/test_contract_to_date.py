"""The to-date reader ``erev_api.domain.contracts.to_date`` (CTR-ASOF-KPI-1; 04 API-C-10 rev
1.132; ENGINE_SPEC S04-R-02; ENGINE_SPEC_B S09-R-23, S09-R-26, S09-R-46, S10-R-26; supervisor
rulings R-76 (a) and R-85). No database.

Two kinds of trace are read. The small ones are written out here, node by node, to pin where a
date falls among the periods a series carries and every named refusal. The others are the
engine's own traces of approved answer keys, computed here, against figures the reader does not
produce:

- ``RET-CHK-029-S3-EX22`` states the version at the expiry of a return window (transaction price
  and revenue 9,800.00 on 31 March, after 9,700.00 on 28 February, with no event between);
- for ``CPC-CHK-120-OVER-TIME-QUARTERLY`` the revenue the December computation posted through
  December is the contract's revenue at that date.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

import erev_engine
import pytest
from erev_api.domain.contracts import to_date
from erev_api.domain.reports import tie_outs
from erev_engine.bundle import BookOutput, InputBundle
from support.answer_keys.loader import ANSWER_KEY_ROOT, load
from support.answer_keys.runners import CheckpointBundles, _build_checkpoint_bundles

CONTRACT = uuid5(NAMESPACE_URL, "C-1")
JANUARY, FEBRUARY, MARCH, APRIL = (
    date(2026, 1, 31),
    date(2026, 2, 28),
    date(2026, 3, 31),
    date(2026, 4, 30),
)
ENDS = {"P01": JANUARY, "P02": FEBRUARY, "P03": MARCH, "P04": APRIL}
STARTS = {("P01", JANUARY): (date(2026, 1, 1),)}
VERSION = {"id": uuid5(NAMESPACE_URL, "version"), "version_no": 3}


def node(measure: str, subject: str, slot: str, value: str, **params: str) -> to_date.Node:
    dated = {"as_of": ENDS[slot].isoformat()} if slot in ENDS and "as_of" not in params else {}
    return to_date.Node(f"{measure}:{subject}:{slot}", measure, value, {**dated, **params})


def series(measure: str, subject: str, values: Mapping[str, str]) -> list[to_date.Node]:
    return [node(measure, subject, slot, value) for slot, value in values.items()]


def trace(
    *extra: to_date.Node,
    horizon: Sequence[str] = ("P01", "P02", "P03"),
    pattern: tuple[str, str] | None = ("DETERMINISTIC", "false"),
) -> list[Any]:
    """C-1 of entity E1: O1 recognised 100.00 a month to April, billed 250.00 in February, its
    balances measured to the horizon (March), its RPO of 950.00 at d_v included by stage 15 and
    its remainder at d_v called ``pattern`` by stage 09: the (``pattern``, ``held``) parameters of
    the version-state ``scheduled_amount`` node, which the engine emits for every obligation it
    measures (ENGINE_SPEC_B §9.5). None leaves that node out."""
    stated = (
        []
        if pattern is None
        else [
            node("scheduled_amount", "C-1/O1", "-", "950.00", pattern=pattern[0], held=pattern[1])
        ]
    )
    return [
        *series("contract_asset", "C-1@E1", dict.fromkeys(horizon, "0.00")),
        *series(
            "revenue_cum",
            "C-1/O1",
            {"P01": "100.00", "P02": "200.00", "P03": "300.00", "P04": "400.00"},
        ),
        *series(
            "progress_ratio", "C-1/O1", {"P01": "0.1", "P02": "0.2", "P03": "0.3", "P04": "0.4"}
        ),
        *series("billed_cum", "C-1/O1", {"P01": "0.00", "P02": "250.00", "P03": "250.00"}),
        node("rpo_amount", "C-1/O1", "-", "950.00", included="true"),
        *stated,
        *extra,
    ]


def row(**changes: Any) -> dict[str, Any]:
    """O1 at d_v, 15 January: 1,000.00 allocated and recognised by time, 50.00 of it so far —
    the remainder is scheduled (ENGINE_SPEC_B S09-R-45) — and nothing billed."""
    return {
        "id": uuid5(NAMESPACE_URL, "C-1/O1"),
        "contract_id": CONTRACT,
        "obligation_key": "O1",
        "txn_currency": "USD",
        "effective_date": date(2026, 1, 15),
        "recognition_method": "TIME_ELAPSED",
        "hold_types": [],
        "allocated_amount": Decimal("1000.00"),
        "revenue_cum": Decimal("50.00"),
        "scheduled_amount": Decimal("950.00"),
        "awaiting_trigger_amount": Decimal("0.00"),
        "billed_cum": Decimal("0.00"),
        "progress_ratio": Decimal("0.05"),
        "satisfaction_status": "PARTIALLY_SATISFIED",
        "trace_nodes": {"revenue_cum": "revenue_cum:C-1/O1:-"},
        **changes,
    }


def read(
    as_of: date,
    nodes: Sequence[Any] | None = None,
    *,
    rows: Sequence[Mapping[str, Any]] | None = None,
    starts: to_date.Starts = STARTS,
    external_ids: Mapping[UUID, str] | None = None,
) -> to_date.VersionAt:
    return to_date.version_at(
        VERSION,
        [row()] if rows is None else rows,
        nodes=to_date.nodes_of(trace() if nodes is None else nodes, starts),
        external_ids={CONTRACT: "C-1"} if external_ids is None else external_ids,
        as_of=as_of,
    )


def refusal(as_of: date, *arguments: Any, **members: Any) -> tuple[str | None, str | None, str]:
    with pytest.raises(to_date.Unreadable) as caught:
        read(as_of, *arguments, **members)
    (error,) = caught.value.errors
    return error.field, error.rule_id, error.message


# --- where a date falls --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("as_of", "revenue", "billed", "period"),
    [
        (date(2026, 2, 10), "200.00", "250.00", "P02"),  # inside a period: its end
        (date(2026, 2, 28), "200.00", "250.00", "P02"),  # a period end
        (date(2026, 1, 10), "100.00", "0.00", "P01"),  # before d_v, inside the first period
        (date(2026, 1, 1), "100.00", "0.00", "P01"),  # the first day of the first period
        (date(2026, 3, 31), "300.00", "250.00", "P03"),  # the horizon
        (date(2026, 6, 30), "300.00", "250.00", "P03"),  # beyond it: the horizon, not April's 400
    ],
)
def test_the_cut_is_the_end_of_the_period_of_as_of_capped_at_the_horizon(
    as_of: date, revenue: str, billed: str, period: str
) -> None:
    found = read(as_of)
    (at,) = found.obligations.values()
    moved = Decimal(revenue) - Decimal("50.00")
    assert (at.revenue, at.billed, at.delta, at.billed_delta) == (
        Decimal(revenue),
        Decimal(billed),
        moved,
        Decimal(billed),
    )
    assert at.measured == to_date.Measured(period, ENDS[period])
    assert at.billed_measured == to_date.Measured(period, ENDS[period])
    assert at.satisfaction_status == "PARTIALLY_SATISFIED"
    # the scheduled amount and the RPO fall by what revenue rose; nothing else moves
    assert (found.revenue_moved, found.billed_moved, found.rpo_moved) == (
        moved,
        Decimal(billed),
        moved,
    )
    assert (found.returns_moved, found.release_moved) == (0, 0)
    # a time-elapsed remainder is scheduled: the movement leaves it, and DB-17 holds at the cut
    assert (at.scheduled, at.awaiting) == (Decimal("950.00") - moved, 0)
    assert (found.scheduled_moved, found.awaiting_moved) == (moved, 0)
    assert at.revenue + at.scheduled + at.awaiting == Decimal("1000.00")


def test_before_the_first_period_nothing_is_measured() -> None:
    found = read(date(2025, 12, 31))
    (at,) = found.obligations.values()
    assert (at.revenue, at.billed, at.progress_ratio, at.measured, at.billed_measured) == (
        0,
        0,
        0,
        None,
        None,
    )
    assert at.satisfaction_status == "UNSATISFIED"  # S09-R-46: no revenue and no progress
    assert found.revenue_moved == Decimal("-50.00")


def test_an_obligation_satisfied_at_the_cut_leaves_the_rpo() -> None:
    """S09-R-46 at the cut: progress 1 is SATISFIED, and stage 15's RPO of the obligation goes."""
    nodes = [item for item in trace() if item.measure != "progress_ratio"]
    nodes += series("progress_ratio", "C-1/O1", {"P01": "0.5", "P02": "1", "P03": "1"})
    found = read(date(2026, 2, 28), nodes)
    (at,) = found.obligations.values()
    assert (at.satisfaction_status, found.rpo_moved) == ("SATISFIED", Decimal("950.00"))
    cancelled = read(date(2026, 2, 28), nodes, rows=[row(satisfaction_status="CANCELLED")])
    assert next(iter(cancelled.obligations.values())).satisfaction_status == "CANCELLED"


def _satisfied_in_march(**state: str) -> tuple[list[Any], dict[str, Any]]:
    """O1 recognised by output: 40% at the end of January, complete on 20 March — the version's
    date, at which stage 15 leaves a satisfied obligation out of the RPO (``included`` false; its
    node's value 0.00). ``state`` are further parameters of that node. Stage 09 calls an
    obligation measured by output event-driven."""
    nodes = [
        *series("contract_asset", "C-1@E1", dict.fromkeys(("P01", "P02", "P03"), "0.00")),
        *series("revenue_cum", "C-1/O1", {"P01": "400.00", "P02": "400.00", "P03": "1000.00"}),
        *series("progress_ratio", "C-1/O1", {"P01": "0.4", "P02": "0.4", "P03": "1"}),
        *series("billed_cum", "C-1/O1", {"P01": "0.00", "P02": "0.00", "P03": "0.00"}),
        node("rpo_amount", "C-1/O1", "-", "0.00", included="false", **state),
        node("scheduled_amount", "C-1/O1", "-", "0.00", pattern="EVENT_DRIVEN", held="false"),
    ]
    stored = row(
        effective_date=date(2026, 3, 20),
        recognition_method="OUTPUT_PERCENT",
        revenue_cum=Decimal("1000.00"),
        scheduled_amount=Decimal("0.00"),
        awaiting_trigger_amount=Decimal("0.00"),
        progress_ratio=Decimal("1"),
        satisfaction_status="SATISFIED",
    )
    return nodes, stored


def test_an_obligation_satisfied_only_later_is_in_the_rpo_of_an_earlier_cut() -> None:
    """04 API-C-10 rev 1.213 (item RPT-RPO-ROLLFWD-1; supervisor ruling R-121 (g)): the
    remainder AT THE CUT decides. O1 is satisfied at d_v, 20 March, so the version's RPO holds
    nothing of it. At 31 January it was 40% complete: 600.00 of its 1,000.00 remained, awaiting
    its trigger, and that remainder is the contract's RPO of that date — ``rpo_moved`` −600.00 on
    a stored 0.00 — as the RPO report states it there (ENGINE_SPEC_B S15-R-08). At d_v and after
    nothing moves.

    Fail-first: ``rpo_moved`` was 0 at the earlier cut — the obligation's remainder showed as
    awaiting trigger and was missing from the RPO beside it (K-01 at 31 January 2026, through the
    product: 108,710.14 where the report states 118,430.14)."""
    nodes, stored = _satisfied_in_march()
    january = read(JANUARY, nodes, rows=[stored])
    (at,) = january.obligations.values()
    assert (at.satisfaction_status, at.scheduled, at.awaiting) == (
        "PARTIALLY_SATISFIED",
        Decimal("0.00"),
        Decimal("600.00"),
    )
    assert january.rpo_moved == Decimal("-600.00")
    for later in (MARCH, date(2026, 6, 30)):
        found = read(later, nodes, rows=[stored])
        (at,) = found.obligations.values()
        assert (at.satisfaction_status, found.rpo_moved) == ("SATISFIED", 0), later


@pytest.mark.parametrize(
    ("state", "changes"),
    [
        # stage 15 left it out for a reason of its own: the contract is no contract in the book
        ({"excluded": "NOT_A_CONTRACT"}, {}),
        # left out, and not satisfied at d_v: no satisfaction to look back before
        ({}, {"satisfaction_status": "CANCELLED"}),
    ],
)
def test_an_obligation_left_out_for_another_reason_stays_out_at_an_earlier_cut(
    state: dict[str, str], changes: dict[str, Any]
) -> None:
    """The look-back brings back only what satisfaction alone had removed: an obligation of a
    contract that is not a contract in the book (D-91 (vii)), or a cancelled one, has no RPO at
    any cut."""
    nodes, stored = _satisfied_in_march(**state)
    found = read(JANUARY, nodes, rows=[{**stored, **changes}])
    assert found.rpo_moved == 0


def test_the_first_period_is_placed_by_the_tenants_calendars() -> None:
    """The start of the first period a series measures is not in the trace. Where two calendars
    give a period of that key and end date different starts, a date between them is refused."""
    two = {("P01", JANUARY): (date(2026, 1, 1), date(2026, 1, 15))}
    assert next(iter(read(date(2026, 1, 20), starts=two).obligations.values())).revenue == 100
    assert next(iter(read(date(2025, 12, 20), starts=two).obligations.values())).revenue == 0
    assert refusal(date(2026, 1, 10), starts=two) == (
        "obligations[C-1/O1].revenue_cum",
        "API-C-10",
        "Contract C-1, obligation O1: 2026-01-10 cannot be placed against P01, the first period "
        "contract version 3 measures revenue_cum for; the tenant's calendars give that period the "
        "start dates 2026-01-01 and 2026-01-15. Nothing is answered from the version's figure at "
        "2026-01-15.",
    )
    field, rule, message = refusal(date(2026, 1, 10), starts={})
    assert (field, rule) == ("obligations[C-1/O1].revenue_cum", "API-C-10")
    assert "the tenant's calendars give that period no start date" in message
    # a date after the first period needs no calendar at all
    assert next(iter(read(date(2026, 2, 10), starts={}).obligations.values())).revenue == 200


# --- refusals by name ----------------------------------------------------------------------------


def test_a_figure_without_a_period_node_is_refused_and_a_zero_one_stays() -> None:
    nodes = [item for item in trace() if item.measure not in ("revenue_cum", "progress_ratio")]
    assert refusal(date(2026, 2, 28), nodes) == (
        "obligations[C-1/O1].revenue_cum",
        "API-C-10",
        "Contract C-1, obligation O1: the calculation trace of contract version 3 holds no "
        "revenue_cum node per period, so the figure at 2026-02-28 cannot be read. Nothing is "
        "answered from the version's figure at 2026-01-15.",
    )
    # S09-INV-05, S09-R-13: an obligation outside Topic 606, or routed to Topic 842, has no
    # revenue target. Its figure is 0 at every date, its status is the version's, and the RPO
    # stage 15 stated for it does not move.
    unmeasured = row(
        revenue_cum=Decimal(0), progress_ratio=Decimal(0), satisfaction_status="SATISFIED"
    )
    found = read(date(2026, 2, 28), nodes, rows=[unmeasured])
    (at,) = found.obligations.values()
    assert (at.revenue, at.delta, at.measured, at.satisfaction_status) == (0, 0, None, "SATISFIED")
    assert (at.billed, at.billed_measured) == (250, to_date.Measured("P02", FEBRUARY))
    assert (found.revenue_moved, found.rpo_moved) == (0, 0)


def test_a_period_node_without_its_end_date_is_refused() -> None:
    undated = to_date.Node("revenue_cum:C-1/O1:P05", "revenue_cum", "500.00", {})
    field, rule, message = refusal(date(2026, 2, 28), trace(undated))
    assert (field, rule) == ("obligations[C-1/O1].revenue_cum", "API-C-10")
    assert message.startswith(
        "Contract C-1, obligation O1: a revenue_cum period node of contract version 3 carries no "
        "period end date, so the period that contains 2026-02-28 cannot be found."
    )


def test_a_version_without_member_balance_nodes_has_no_horizon() -> None:
    assert refusal(date(2026, 2, 28), trace(horizon=())) == (
        "balances[C-1@]",
        "API-C-10",
        "Contract C-1: the calculation trace of contract version 3 holds no dated member-balance "
        "node of the contract, so the period its figures reach cannot be read. Nothing is answered "
        "from the version's stored figures.",
    )


def test_a_member_contract_outside_the_readers_entities_is_read_through_its_bound_node() -> None:
    """``contract`` is RLS-TE: the external id of another member of the group may be absent. The
    obligation version names its subject in a node it binds: the revenue node, or, for an
    obligation without a revenue target, its billing node."""
    found = read(date(2026, 2, 28), external_ids={})
    assert next(iter(found.obligations.values())).revenue == 200
    billed_only = row(trace_nodes={"billed_cum": "billed_cum:C-1/O1:-"})
    found = read(date(2026, 2, 28), rows=[billed_only], external_ids={})
    assert next(iter(found.obligations.values())).billed == 250
    field, rule, message = refusal(date(2026, 2, 28), rows=[row(trace_nodes={})], external_ids={})
    assert (field, rule) == ("obligations[O1].revenue_cum", "API-C-10")
    assert message.startswith("Obligation O1 of a member contract outside your entities:")


def test_an_obligation_the_engine_measures_nothing_for_stays_as_the_version_holds_it() -> None:
    """A line outside Topic 606 that was never billed (a contribution routed to Topic 958) has no
    period node at all and binds none: its figures are 0 at every date, its status is the
    version's, and it needs no horizon — for the reader of its contract and for the reader of
    another member of its group alike."""
    routed_out = row(
        revenue_cum=Decimal(0),
        billed_cum=Decimal(0),
        progress_ratio=Decimal(0),
        satisfaction_status="UNSATISFIED",
        trace_nodes={},
    )
    for external_ids in ({CONTRACT: "C-1"}, {}):
        found = read(date(2026, 2, 28), [], rows=[routed_out], external_ids=external_ids)
        (at,) = found.obligations.values()
        assert (at.revenue, at.billed, at.delta, at.measured, at.satisfaction_status) == (
            0,
            0,
            0,
            None,
            "UNSATISFIED",
        )
        assert (found.revenue_moved, found.billed_moved, found.rpo_moved) == (0, 0, 0)


# --- the contract's revenue is net of the release of the cut ------------------------------------


def test_the_release_of_the_cut_replaces_the_release_of_the_version() -> None:
    """ENGINE_SPEC S04-R-02: the version's revenue is net of ``incentive_release_cum`` at the
    period of d_v (January: 0.00). Read at February it is net of February's 10.00."""
    release = [
        to_date.Node(f"incentive_release_cum:C-1@E1:{slot}", "incentive_release_cum", value, {})
        for slot, value in (("P01", "0.00"), ("P02", "10.00"), ("P03", "10.00"))
    ]
    assert read(date(2026, 1, 20), trace(*release)).release_moved == 0
    assert read(date(2026, 2, 10), trace(*release)).release_moved == Decimal("10.00")
    assert read(date(2026, 6, 30), trace(*release)).release_moved == Decimal("10.00")
    late = [row(effective_date=date(2026, 3, 5))]  # a version dated in March, read back at January
    assert read(date(2026, 1, 20), trace(*release), rows=late).release_moved == Decimal("-10.00")


# --- balances ------------------------------------------------------------------------------------

ENTITY = uuid5(NAMESPACE_URL, "E1")


def balance(as_of: date, nodes: Sequence[Any], moved: str = "0.00") -> to_date.BalanceAt:
    """The row of C-1 in E1: its stored balances are those of March, the latest period, and its
    net position, billed less revenue, is that of d_v."""
    stored = {
        "contract_id": CONTRACT,
        "entity_id": ENTITY,
        "entity_code": "E1",
        "txn_currency": "USD",
        "net_position_txn": Decimal("-50.00"),
        **{f"{name}_txn": Decimal(0) for name in tie_outs.BALANCE_MEASURES},
        "contract_asset_txn": Decimal("300.00"),
    }
    return to_date.balance_at(
        stored,
        version=VERSION,
        nodes=to_date.nodes_of(nodes, STARTS),
        external_id="C-1",
        moved=Decimal(moved),
        as_of=as_of,
    )


def test_balances_are_those_of_the_cut() -> None:
    nodes = series("contract_asset", "C-1@E1", {"P01": "100.00", "P02": "200.00", "P03": "300.00"})
    february = balance(date(2026, 2, 10), nodes, moved="-150.00")
    assert (
        february.values["contract_asset"],
        february.net_position,
        february.latest,
        february.measured,
    ) == (Decimal("200.00"), Decimal("-200.00"), False, to_date.Measured("P02", FEBRUARY))
    latest = balance(date(2026, 9, 30), nodes, moved="-250.00")
    assert (latest.values["contract_asset"], latest.net_position, latest.latest) == (
        Decimal("300.00"),
        Decimal("-300.00"),
        True,
    )
    before = balance(date(2025, 12, 1), nodes, moved="50.00")
    assert (set(before.values.values()), before.net_position, before.measured) == ({0}, 0, None)
    # An untraced subject keeps the refusal of the S15-R-07a reader.
    with pytest.raises(tie_outs.BalanceUnreadable):
        balance(date(2026, 2, 10), [])


def test_the_net_position_of_a_row_moves_with_its_own_obligations() -> None:
    """04 T-CON-09: a row summarises the obligations of its contract whose contracting entity is
    the row's. Billing of 250.00 and revenue of 150.00 since d_v move its net position by 100.00;
    an obligation of another contract of the group, or contracted by another entity, does not."""
    at = read(date(2026, 2, 28)).obligations
    (moved,) = at.values()
    own = row(contracting_entity_id=ENTITY)
    elsewhere = uuid5(NAMESPACE_URL, "E2")
    other = uuid5(NAMESPACE_URL, "C-2")
    balance_row = {"contract_id": CONTRACT, "entity_id": ENTITY}
    assert (moved.billed_delta, moved.delta) == (Decimal("250.00"), Decimal("150.00"))
    assert to_date.net_moved([own], at, balance_row) == Decimal("100.00")
    assert to_date.net_moved([row(contracting_entity_id=elsewhere)], at, balance_row) == 0
    assert (
        to_date.net_moved([row(contract_id=other, contracting_entity_id=ENTITY)], at, balance_row)
        == 0
    )


# --- the nodes a read at given dates keeps (RPT-ASOF-FIGURES-1) -----------------------------------


def ids(nodes: Sequence[Any]) -> list[str]:
    return sorted(item.id for item in nodes)


def test_a_read_at_a_date_keeps_the_neighbours_of_the_date_in_every_series() -> None:
    """``nodes_at``: of each period series the first and the last node, and around the date — and
    around the horizon, which caps it — the last node before and the first on or after. O1 has a
    node for the 28th of every month of 2026 and its contract is measured to 31 March: a read at
    10 February keeps five of the twelve."""
    months = {f"P{month:02d}": date(2026, month, 28) for month in range(1, 13)}
    year = [
        to_date.Node(
            f"revenue_cum:C-1/O1:{key}", "revenue_cum", f"{index}00.00", {"as_of": str(end)}
        )
        for index, (key, end) in enumerate(months.items(), start=1)
    ]
    member = series("contract_liability", "C-1@E1", dict.fromkeys(("P01", "P02", "P03"), "0.00"))
    kept = to_date.nodes_at([*year, *member], [date(2026, 2, 10)])
    assert ids(kept) == [
        "contract_liability:C-1@E1:P01",
        "contract_liability:C-1@E1:P02",
        "contract_liability:C-1@E1:P03",
        "revenue_cum:C-1/O1:P01",  # the first node, and the last before 10 February
        "revenue_cum:C-1/O1:P02",  # the first on or after 10 February
        "revenue_cum:C-1/O1:P03",  # the last before the horizon, 31 March
        "revenue_cum:C-1/O1:P04",  # the first on or after the horizon
        "revenue_cum:C-1/O1:P12",  # the last node
    ]
    # a date beyond every node, and one before every node: the first and the last
    for day in (date(2030, 1, 1), date(2020, 1, 1)):
        assert ids(to_date.nodes_at(year, [day])) == [
            "revenue_cum:C-1/O1:P01",
            "revenue_cum:C-1/O1:P12",
        ]


def test_a_read_at_a_date_keeps_what_is_no_period_series_and_drops_what_no_date_reaches() -> None:
    """A version state and a node of an obligation's series without an end date stay; a returns
    target stays when the reader takes it (scope ``REDUCE_CONTRACT_QUANTITY``); the release of a
    consideration payable and a node of a measure the reader does not take go."""
    state = node("rpo_amount", "C-1/O1", "-", "950.00", included="true")
    undated = to_date.Node("revenue_cum:C-1/O1:P09", "revenue_cum", "9.00", {})
    target = {"unit_rate": "10", "returned": "0", "expected": "2"}
    reduce = node(
        "revenue_target_exact", "C-1/O1#FIXED", "P01", "1.00", scope=to_date.REDUCE, **target
    )
    other = node("revenue_target_exact", "C-1/O1#FIXED", "P02", "1.00", scope="ESTIMATE", **target)
    release = to_date.Node("incentive_release_cum:C-1@E1:P01", "incentive_release_cum", "5.00", {})
    foreign = node("allocated_amount", "C-1/O1", "P01", "1000.00")
    kept = to_date.nodes_at([state, undated, reduce, other, release, foreign], [JANUARY])
    assert ids(kept) == ids([state, undated, reduce])


def member_sums(subject: str, slots: Sequence[str]) -> list[to_date.Node]:
    """The member sums of stage 10: one node per period, naming the period key and no date."""
    return [
        to_date.Node(
            f"refund_liability:{subject}:{slot}", "refund_liability", f"{index}.00", {"as_of": slot}
        )
        for index, slot in enumerate(slots, start=1)
    ]


def test_a_member_keeps_its_undated_balances_by_period_key() -> None:
    """A member sum carries its period key and no date; its periods are dated by the member's
    other nodes. Of such a measure the latest node at or before each kept period stays — here a
    measure that has no node in March keeps February's for the read at the horizon."""
    dated = series("contract_liability", "C-1@E1", dict.fromkeys(("P01", "P02", "P03"), "0.00"))
    sums = member_sums("C-1@E1", ["P01", "P02"])
    assert ids(to_date.nodes_at([*dated, *sums], [date(2026, 3, 20)])) == [
        "contract_liability:C-1@E1:P01",
        "contract_liability:C-1@E1:P02",
        "contract_liability:C-1@E1:P03",
        "refund_liability:C-1@E1:P01",  # at or before P01, the member's first period
        "refund_liability:C-1@E1:P02",  # at or before P02 and P03
    ]
    # a period that no node dates: the reader refuses the member, and nothing of it is dropped
    orphan = member_sums("C-1@E1", ["P01", "P02", "P07"])
    assert len(to_date.nodes_at([*dated, *orphan], [JANUARY])) == 6


TRACES: dict[str, list[Any]] = {
    "measured to April, its contract to March": trace(),
    "a member measured to April as well": trace(horizon=("P01", "P02", "P03", "P04")),
    "a member measured for February only": trace(horizon=("P02",)),
    "member sums by period key": trace(*member_sums("C-1@E1", ["P01", "P02", "P03"])),
    "a member sum with no node in the last period": trace(*member_sums("C-1@E1", ["P01"])),
    "a member sum in February only, its member measured to April": trace(
        *member_sums("C-1@E1", ["P02"]), horizon=("P01", "P02", "P03", "P04")
    ),
    "a member sum of a period that no node dates": trace(*member_sums("C-1@E1", ["P01", "P07"])),
    "a dated balance in one period only": trace(node("contract_asset", "C-1@E1", "P02", "70.00")),
    "a second entity measured one period further": trace(
        *series("contract_liability", "C-1@E2", dict.fromkeys(("P02", "P03", "P04"), "0.00"))
    ),
    "a node of the series without an end date": trace(
        to_date.Node("revenue_cum:C-1/O1:P09", "revenue_cum", "9.00", {})
    ),
    "no billing node": [item for item in trace() if item.measure != "billed_cum"],
    "no node at all": [],
}


@pytest.mark.parametrize("name", sorted(TRACES))
def test_the_kept_nodes_answer_every_date_as_the_whole_trace_does(name: str) -> None:
    """On every day from December 2025 to July 2026 — before the first period, inside and at the
    end of each, at and beyond the horizon — the obligation and the balance row read from the
    nodes kept for that day are those read from the whole trace, or both refuse with one
    message."""
    nodes = TRACES[name]
    whole = to_date.nodes_of(nodes, STARTS)
    stored = {
        "contract_id": CONTRACT,
        "entity_id": ENTITY,
        "entity_code": "E1",
        "txn_currency": "USD",
        "net_position_txn": Decimal("-50.00"),
        **{f"{measure}_txn": Decimal(0) for measure in tie_outs.BALANCE_MEASURES},
    }

    def answers(found: to_date.Nodes, day: date) -> list[tuple[str, Any]]:
        reads = (
            lambda: (
                to_date.version_at(
                    VERSION, [row()], nodes=found, external_ids={CONTRACT: "C-1"}, as_of=day
                ).obligations
            ),
            lambda: to_date.balance_at(
                stored, version=VERSION, nodes=found, external_id="C-1", moved=Decimal(0), as_of=day
            ),
            lambda: to_date.measured_at(
                VERSION, nodes=found, external_id="C-1", entity_code="E1", as_of=day
            ),
        )
        results: list[tuple[str, Any]] = []
        for read_one in reads:
            try:
                results.append(("read", read_one()))
            except (to_date.Unreadable, tie_outs.BalanceUnreadable) as refused:
                results.append(("refused", refused.errors[0].message))
        return results

    day = date(2025, 12, 1)
    while day <= date(2026, 7, 31):
        kept = to_date.nodes_of(to_date.nodes_at(nodes, [day]), STARTS)
        assert answers(kept, day) == answers(whole, day), day
        day = date.fromordinal(day.toordinal() + 1)


def test_the_kept_nodes_hold_no_release() -> None:
    """The release of a consideration payable is measured from the version's own date, which is
    no date of a report's read: the kept nodes hold none, and the reports take the obligations
    and the balance rows of a read only (``reports.cuts.Versions``)."""
    release = [
        to_date.Node(f"incentive_release_cum:C-1@E1:{slot}", "incentive_release_cum", value, {})
        for slot, value in (("P01", "0.00"), ("P02", "10.00"), ("P03", "10.00"))
    ]
    kept = to_date.nodes_of(to_date.nodes_at(trace(*release), [FEBRUARY]), STARTS)
    assert kept.keyed == {}
    found = to_date.version_at(
        VERSION, [row()], nodes=kept, external_ids={CONTRACT: "C-1"}, as_of=FEBRUARY
    )
    assert found.obligations == read(FEBRUARY, trace(*release)).obligations
    assert (found.release_moved, read(FEBRUARY, trace(*release)).release_moved) == (0, 10)


# --- the engine's traces of approved answer keys --------------------------------------------------


def checkpoint(key_id: str, name: str) -> tuple[CheckpointBundles, InputBundle, BookOutput]:
    loaded = load(ANSWER_KEY_ROOT / key_id.split("-", 1)[0].lower() / f"{key_id}.yaml")
    found = next(item for item in _build_checkpoint_bundles(loaded) if item.name == name)
    (bundle,) = found.bundles
    output = erev_engine.compute(bundle)
    (book,) = [item for item in output.books if item.book_code == found.book]
    return found, bundle, book


def major(value: object) -> Decimal:
    assert isinstance(value, int)
    return Decimal(value).scaleb(-2)


def product_read(
    bundle: InputBundle, book: BookOutput, as_of: date
) -> tuple[dict[str, Decimal], to_date.VersionAt, list[dict[str, Any]]]:
    """The version of ``book`` at the cut of ``as_of``, as the contract read moves it: the stored
    figures are the engine's columns and the nodes the engine's own trace."""
    assert book.contract_version is not None
    starts: dict[tuple[str, date], set[date]] = {}
    for entity in bundle.entities:
        for period in entity.periods:
            starts.setdefault((period.period_key, period.end_date), set()).add(period.start_date)
    nodes = to_date.nodes_of(
        book.trace.nodes, {pair: tuple(sorted(found)) for pair, found in starts.items()}
    )
    rows = [
        {
            "id": uuid5(NAMESPACE_URL, item.subject_key),
            "contract_id": uuid5(NAMESPACE_URL, item.subject_key.split("/")[0]),
            "obligation_key": item.columns["obligation_key"],
            "txn_currency": "USD",
            "effective_date": item.columns["effective_date"],
            "revenue_cum": major(item.columns["revenue_cum"]),
            "billed_cum": major(item.columns["billed_cum"]),
            "recognition_method": item.columns["recognition_method"],
            "hold_types": item.columns.get("hold_types") or (),
            "allocated_amount": major(item.columns["allocated_amount"]),
            "scheduled_amount": major(item.columns["scheduled_amount"]),
            "awaiting_trigger_amount": major(item.columns["awaiting_trigger_amount"]),
            "progress_ratio": Decimal(str(float(item.columns["progress_ratio"]))),  # type: ignore[arg-type]
            "satisfaction_status": item.columns["satisfaction_status"],
            "trace_nodes": dict(item.trace_nodes),
        }
        for item in book.obligation_versions
    ]
    columns = book.contract_version.columns
    at = to_date.version_at(
        {"id": uuid5(NAMESPACE_URL, "v"), "version_no": 1},
        rows,
        nodes=nodes,
        external_ids={},
        as_of=as_of,
    )
    moved = {
        "transaction_price": major(columns["transaction_price"]) - at.returns_moved,
        "revenue_cum": major(columns["revenue_cum"]) + at.revenue_moved - at.release_moved,
        "scheduled_amount": major(columns["scheduled_amount"]) - at.scheduled_moved,
        "awaiting_trigger_amount": major(columns["awaiting_trigger_amount"]) - at.awaiting_moved,
    }
    return moved, at, rows


def test_the_returns_reduction_is_measured_at_the_cut() -> None:
    """Supervisor ruling R-85 (a): the version of 10 February (transaction price and revenue
    9,700.00, as the key states for 28 February) read at 31 March, after the return window
    expired with no event, is the key's ``window-expired`` version: 9,800.00 and 9,800.00. The
    obligation's reported allocation follows, and 04 DB-17 holds at the cut, where no key speaks
    of the scheduled amount."""
    _, bundle, book = checkpoint("RET-CHK-029-S3-EX22", "end-of-february")
    assert book.contract_version is not None
    emitted = book.contract_version.columns
    assert (major(emitted["transaction_price"]), major(emitted["revenue_cum"])) == (9700, 9700)

    february, _, _ = product_read(bundle, book, date(2026, 2, 28))
    assert (february["transaction_price"], february["revenue_cum"]) == (9700, 9700)

    march, at, rows = product_read(bundle, book, date(2026, 3, 31))
    assert (march["transaction_price"], march["revenue_cum"]) == (9800, 9800)
    assert (at.returns_moved, march["scheduled_amount"]) == (-100, 0)
    (stored,) = rows
    (moved,) = at.obligations.values()
    allocated = stored["allocated_amount"] - moved.shift
    assert (allocated, moved.revenue, moved.scheduled, moved.awaiting) == (9800, 9800, 0, 0)
    assert allocated == moved.revenue + moved.scheduled + moved.awaiting
    assert march["awaiting_trigger_amount"] == 0


def test_the_contracts_revenue_at_the_cut_is_what_the_computation_posted() -> None:
    """``CPC-CHK-120-OVER-TIME-QUARTERLY``: warrants of 50,000.00 reduce revenue as the service is
    performed. Its December computation, whose latest event is of 31 October, holds revenue
    957,808.21: the obligations' 999,452.05 less the release of October, 41,643.84. Read at 31
    December the contract's revenue is what that computation posted through December,
    1,150,000.00, the transaction price: the obligations' 1,200,000.00 less December's 50,000.00."""
    found, bundle, book = checkpoint("CPC-CHK-120-OVER-TIME-QUARTERLY", "december")
    assert found.as_of == date(2026, 12, 31)
    assert book.contract_version is not None
    assert major(book.contract_version.columns["revenue_cum"]) == Decimal("957808.21")
    posted = sum(
        line.amount_txn if line.side == "C" else -line.amount_txn
        for intent in book.posting_intents
        for line in intent.lines
        if line.account_role == "REVENUE"
    )
    assert major(posted) == Decimal("1150000.00")

    moved, at, _ = product_read(bundle, book, found.as_of)
    assert at.release_moved == Decimal("50000.00") - Decimal("41643.84")
    assert (moved["revenue_cum"], moved["transaction_price"], moved["scheduled_amount"]) == (
        major(posted),
        Decimal("1150000.00"),
        0,
    )
    # and at the version's own date the read is the version
    october, _, _ = product_read(bundle, book, date(2026, 10, 31))
    assert october["revenue_cum"] == Decimal("957808.21")


# --- the remainder at the cut: scheduled and awaiting trigger (CTR-TODATE-AWAITING-1; R-118 (a)) --

USAGE: dict[str, Any] = {
    # a remainder that awaits a trigger whole and that time recognises all the same: the fixed fee
    # of a usage obligation as a version computed before ENGINE_SPEC_B rev 1.126 stores it (since
    # that revision S09-R-45 calls it scheduled)
    "recognition_method": "USAGE",
    "scheduled_amount": Decimal("0.00"),
    "awaiting_trigger_amount": Decimal("950.00"),
}
# a remainder the engine split in two: 850.00 that time alone recognises, 100.00 that waits
MIXED: dict[str, Any] = {
    "scheduled_amount": Decimal("850.00"),
    "awaiting_trigger_amount": Decimal("100.00"),
}


@pytest.mark.parametrize(
    ("changes", "as_of", "scheduled", "awaiting"),
    [
        # recognised since the version, at 31 March 250.00: it leaves what the engine scheduled
        ({}, date(2026, 3, 31), "700.00", "0.00"),
        # nothing is scheduled: it leaves the awaiting-trigger amount (as built: scheduled -250.00)
        (USAGE, date(2026, 3, 31), "0.00", "700.00"),
        ({**USAGE, "recognition_method": "POINT_IN_TIME"}, date(2026, 2, 28), "0.00", "800.00"),
        # a held time-elapsed target awaits its release (S09-R-44): nothing is scheduled either
        (
            {**USAGE, "recognition_method": "TIME_ELAPSED", "hold_types": ["recognition"]},
            date(2026, 3, 31),
            "0.00",
            "700.00",
        ),
        ({"hold_types": ["journal_export"]}, date(2026, 3, 31), "700.00", "0.00"),
        # the scheduled amount first, whatever the pattern (R-118 (a)): time passed, no trigger
        (MIXED, date(2026, 3, 31), "600.00", "100.00"),
        ({**USAGE, **MIXED}, date(2026, 3, 31), "600.00", "100.00"),
        ({**MIXED, "recognition_method": "POINT_IN_TIME"}, date(2026, 3, 31), "600.00", "100.00"),
        # and the awaiting-trigger amount for what the scheduled one cannot cover
        (
            {"scheduled_amount": Decimal("100.00"), "awaiting_trigger_amount": Decimal("850.00")},
            date(2026, 3, 31),
            "0.00",
            "700.00",
        ),
        (
            {
                **USAGE,
                "scheduled_amount": Decimal("100.00"),
                "awaiting_trigger_amount": Decimal("850.00"),
            },
            date(2026, 3, 31),
            "0.00",
            "700.00",
        ),
    ],
)
def test_the_movement_since_the_version_leaves_the_scheduled_amount_first(
    changes: Mapping[str, Any], as_of: date, scheduled: str, awaiting: str
) -> None:
    """04 API-C-10 (rev 1.174 and 1.179; CTR-TODATE-AWAITING-1; ruling R-118 (a)): revenue
    recognised since the version leaves the scheduled amount first and the awaiting-trigger
    amount for the rest. No pattern is asked for that — the trace read here states none (rev
    1.178) — and the row's method and holds are not read. At the cut the allocation is still
    revenue plus the scheduled amount plus the awaiting-trigger amount (04 DB-17), and neither
    part is negative."""
    found = read(as_of, trace(pattern=None), rows=[row(**changes)])
    (at,) = found.obligations.values()
    assert (at.scheduled, at.awaiting) == (Decimal(scheduled), Decimal(awaiting))
    assert at.revenue + at.scheduled + at.awaiting == Decimal("1000.00")
    stored = row(**changes)
    assert (found.scheduled_moved, found.awaiting_moved) == (
        stored["scheduled_amount"] - at.scheduled,
        stored["awaiting_trigger_amount"] - at.awaiting,
    )
    assert found.scheduled_moved + found.awaiting_moved == found.revenue_moved


DETERMINISTIC, EVENT_DRIVEN, HELD = (
    ("DETERMINISTIC", "false"),
    ("EVENT_DRIVEN", "false"),
    ("DETERMINISTIC", "true"),
)


@pytest.mark.parametrize(
    ("changes", "pattern", "scheduled", "awaiting"),
    [
        # time alone places the remainder: the 50.00 a look-back gives back had left the
        # scheduled amount
        ({}, DETERMINISTIC, "1000.00", "0.00"),
        (MIXED, DETERMINISTIC, "900.00", "100.00"),
        # so it had for the fixed fee of a usage obligation, which the engine schedules
        # (ENGINE_SPEC_B S09-R-45 rev 1.126): the node says so and the row's method is not asked
        # — by the method this case read 850.00 and 150.00
        ({**USAGE, **MIXED}, DETERMINISTIC, "900.00", "100.00"),
        # an event-driven remainder waited
        (USAGE, EVENT_DRIVEN, "0.00", "1000.00"),
        # and so did that of a time-elapsed obligation the engine does not call scheduled at d_v
        # (its contract is not a contract in the book, its custodial term has not begun): the
        # node, not the method — by the method this case would read 50.00 and 950.00
        ({**USAGE, "recognition_method": "TIME_ELAPSED"}, EVENT_DRIVEN, "0.00", "1000.00"),
        # a held remainder awaits its release (S09-R-44): ``held`` of the node
        ({**MIXED, "hold_types": ["recognition"]}, HELD, "850.00", "150.00"),
        # the row's own method and holds are not asked at all
        (
            {**MIXED, "recognition_method": "POINT_IN_TIME", "hold_types": ["recognition"]},
            DETERMINISTIC,
            "900.00",
            "100.00",
        ),
    ],
)
def test_a_look_back_returns_the_revenue_to_the_part_the_versions_own_node_names(
    changes: Mapping[str, Any], pattern: tuple[str, str], scheduled: str, awaiting: str
) -> None:
    """04 API-C-10 rev 1.178 (item ENG-USAGE-FIXED-SCHEDULE-1; supervisor rulings R-116 (a) and
    R-118 (a)): at a cut before d_v — here before the first period, where the 50.00 recognised by
    d_v is given back — the revenue returns to the part the engine's own word names: the
    (``pattern``, ``held``) parameters of the version-state ``scheduled_amount`` node. It is the
    scheduled amount for ``DETERMINISTIC`` and not held, the awaiting-trigger amount otherwise.
    The reader repeats no predicate of the engine. The identities of the test above hold."""
    stored = row(**changes)
    found = read(date(2025, 12, 31), trace(pattern=pattern), rows=[stored])
    (at,) = found.obligations.values()
    assert (at.scheduled, at.awaiting) == (Decimal(scheduled), Decimal(awaiting))
    assert at.revenue + at.scheduled + at.awaiting == Decimal("1000.00")
    assert (found.scheduled_moved, found.awaiting_moved) == (
        stored["scheduled_amount"] - at.scheduled,
        stored["awaiting_trigger_amount"] - at.awaiting,
    )
    assert found.scheduled_moved + found.awaiting_moved == found.revenue_moved == Decimal("-50.00")


def test_a_look_back_returns_the_usage_fees_reported_since_to_the_scheduled_amount() -> None:
    """Rev 1.178: a look-back returns all the revenue it gives back to one part, and the
    allocation stays the version's. O1 measured by usage with a fixed fee of 1,000.00, read from
    its version of 31 March, whose allocation and revenue hold 60.00 of usage fees reported that
    month: at 31 January the fee's own remainder was 900.00, and the read states 960.00 scheduled
    — the fees reported between the cut and d_v count as scheduled at the cut. It is what the
    version's schedule lines after January add up to, which ``reports.cuts.scheduled_after``
    requires; a finer split would be refused there."""
    replaced = ("revenue_cum", "rpo_amount", "scheduled_amount")
    nodes = [item for item in trace() if item.measure not in replaced]
    nodes += series("revenue_cum", "C-1/O1", {"P01": "100.00", "P02": "200.00", "P03": "360.00"})
    nodes += [
        node("rpo_amount", "C-1/O1", "-", "700.00", included="true"),
        node("scheduled_amount", "C-1/O1", "-", "700.00", pattern="DETERMINISTIC", held="false"),
    ]
    stored = row(
        effective_date=MARCH,
        recognition_method="USAGE",
        allocated_amount=Decimal("1060.00"),
        revenue_cum=Decimal("360.00"),
        scheduled_amount=Decimal("700.00"),
        progress_ratio=Decimal("0.3"),
    )
    found = read(JANUARY, nodes, rows=[stored])
    (at,) = found.obligations.values()
    assert (at.revenue, at.scheduled, at.awaiting) == (
        Decimal("100.00"),
        Decimal("960.00"),
        Decimal("0.00"),
    )
    assert at.revenue + at.scheduled + at.awaiting == stored["allocated_amount"]
    assert (found.revenue_moved, found.rpo_moved) == (Decimal("-260.00"), Decimal("-260.00"))


def test_a_look_back_without_the_versions_pattern_node_is_refused_by_name() -> None:
    """Rev 1.178: the revenue a look-back gives back cannot be placed without the engine's word
    for the obligation's pattern, and the row's method does not stand in: no figure is served. The
    group's sum of the scheduled amounts (stage 13) states no pattern and is not taken for the
    obligation's node. A cut at d_v or after asks for none."""
    group = node("scheduled_amount", "CG-1", "-", "950.00", signs="+")
    for nodes in (trace(pattern=None), trace(group, pattern=None)):
        assert refusal(date(2025, 12, 31), nodes) == (
            "obligations[O1].scheduled_amount",
            "API-C-10",
            "Contract C-1, obligation O1: the calculation trace of contract version 3 holds no "
            "scheduled_amount node of the obligation, so the part of its remainder that the "
            "revenue recognised after 2025-12-31 had left cannot be named. Nothing is answered "
            "from the version's figure at 2026-01-15.",
        )
        (at,) = read(MARCH, nodes).obligations.values()
        assert (at.scheduled, at.awaiting) == (Decimal("700.00"), 0)
    # the node states the pattern with both parameters or not at all
    half = node("scheduled_amount", "C-1/O1", "-", "950.00", pattern="DETERMINISTIC")
    field, rule, _ = refusal(date(2025, 12, 31), trace(half, pattern=None))
    assert (field, rule) == ("obligations[O1].scheduled_amount", "API-C-10")


def test_a_remainder_below_zero_is_refused_by_name() -> None:
    """Revenue at the cut beyond what the version allocates cannot be split: no figure is served."""
    short = row(scheduled_amount=Decimal("100.00"), awaiting_trigger_amount=Decimal("50.00"))
    assert refusal(date(2026, 3, 31), rows=[short]) == (
        "obligations[O1].scheduled_amount",
        "API-C-10",
        "Contract C-1, obligation O1: at 2026-03-31 the revenue read from the calculation trace "
        "of contract version 3 leaves a scheduled amount of 0 and an awaiting-trigger amount of "
        "-100.00; neither can be below zero (04 DB-17). Nothing is answered from the version's "
        "figure at 2026-01-15.",
    )


def test_a_transfer_dated_after_the_version_leaves_the_awaiting_trigger_amount() -> None:
    """``REC-FS-06-TERM-LICENCE-RENEWAL-START-GATE``, checkpoint ``renewal-period-starts``: the
    renewal licence transfers when its term starts, after the version's date. The version holds
    55,000.00 awaiting trigger and nothing scheduled; at the cut the revenue is 55,000.00 and
    both parts are 0.00. As built the scheduled amount read -55,000.00."""
    key = "REC-FS-06-TERM-LICENCE-RENEWAL-START-GATE"
    loaded = load(ANSWER_KEY_ROOT / "rec" / f"{key}.yaml")
    found = next(
        item for item in _build_checkpoint_bundles(loaded) if item.name == "renewal-period-starts"
    )
    # the key holds the original licence and its renewal as two contracts: the renewal's group
    bundle = next(
        item for item in found.bundles if "FS-06-RENEWAL" in item.group.member_contract_keys
    )
    (book,) = [item for item in erev_engine.compute(bundle).books if item.book_code == found.book]
    shown, at, rows = product_read(bundle, book, found.as_of)
    renewal = next(item for item in rows if item["obligation_key"].endswith("TLIC-R"))
    assert (
        renewal["recognition_method"],
        renewal["scheduled_amount"],
        renewal["awaiting_trigger_amount"],
    ) == ("POINT_IN_TIME", 0, 55000)
    moved = at.obligations[renewal["id"]]
    assert (moved.revenue, moved.delta, moved.scheduled, moved.awaiting) == (55000, 55000, 0, 0)
    for item in rows:
        part = at.obligations[item["id"]]
        assert min(part.scheduled, part.awaiting) >= 0, item["obligation_key"]
        assert (
            item["allocated_amount"] - part.shift == part.revenue + part.scheduled + part.awaiting
        )
    assert min(shown["scheduled_amount"], shown["awaiting_trigger_amount"]) >= 0


@pytest.mark.parametrize("day, expected", [(JANUARY, "900.00"), (MARCH, "850.00")])
def test_realized_fees_enter_the_remainder_only_at_their_period(day: date, expected: str) -> None:
    nodes = trace(
        node("realised_allocation", "C-1/O1", "-", "150.00"),
        *series("realised_allocation", "C-1/O1", {"P01": "0.00", "P02": "0.00", "P03": "150.00"}),
        pattern=("EVENT_DRIVEN", "false"),
    )
    stored = row(
        effective_date=MARCH,
        revenue_cum=Decimal("300.00"),
        scheduled_amount=Decimal(0),
        awaiting_trigger_amount=Decimal("850.00"),
    )
    result = read(day, nodes, rows=[stored])
    at = result.obligations[stored["id"]]
    assert at.scheduled + at.awaiting == Decimal(expected)
    assert at.realised == (Decimal(0) if day == JANUARY else Decimal("150.00"))
    assert at.realised_stored == Decimal("150.00")
    assert result.returns_moved == (Decimal("150.00") if day == JANUARY else Decimal(0))


@pytest.mark.parametrize("stored", ["0.00", "150.00"])
def test_realized_state_requires_explicit_dated_evidence_even_when_zero(stored: str) -> None:
    with pytest.raises(to_date.Unreadable, match="1 field needs attention"):
        read(JANUARY, trace(node("realised_allocation", "C-1/O1", "-", stored)))


def test_realized_series_requires_its_version_state() -> None:
    with pytest.raises(to_date.Unreadable, match="1 field needs attention"):
        read(JANUARY, trace(*series("realised_allocation", "C-1/O1", {"P01": "0.00"})))


def test_trimming_preserves_fixed_schedule_sources_beyond_the_requested_cut() -> None:
    extra = [
        node(
            "scheduled_fixed_amount",
            "C-1/O1",
            period,
            "100.00",
            source_node=f"revenue_by_cause:C-1/O1/NORMAL:{period}",
        )
        for period in ENDS
    ]
    whole = trace(*extra)
    kept = to_date.nodes_of(to_date.nodes_at(whole, [JANUARY]), STARTS)
    assert kept.fixed_schedule == to_date.nodes_of(whole, STARTS).fixed_schedule
    assert len((kept.fixed_schedule or {})["C-1/O1"]) == 4


def test_explicit_no_realization_state_is_distinct_from_missing_history() -> None:
    result = read(
        JANUARY, trace(node("realised_allocation", "C-1/O1", "-", "0.00", realisation_mode="NONE"))
    )
    at = result.obligations[row()["id"]]
    assert at.realised_traced
    assert at.realised == at.realised_stored == 0
    assert at.fixed_schedule is None
    assert at.scheduled == Decimal("900.00")


@pytest.mark.parametrize("amount, dated", [("1.00", False), ("0.00", True)])
def test_no_realization_marker_cannot_hide_a_value_or_dated_series(
    amount: str, dated: bool
) -> None:
    nodes = [node("realised_allocation", "C-1/O1", "-", amount, realisation_mode="NONE")]
    if dated:
        nodes.append(node("realised_allocation", "C-1/O1", "P01", "0.00"))
    with pytest.raises(to_date.Unreadable) as caught:
        read(JANUARY, trace(*nodes))
    assert caught.value.errors[0].field.endswith(".realised_allocation")
