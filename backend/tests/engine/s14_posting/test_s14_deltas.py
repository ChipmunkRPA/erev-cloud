"""Stage 14 role targets and deltas: posting classes, period assignment, netting reclass, voids and
mapping changes.

ENGINE_SPEC_B §14.2.2 (S14-R-04 to S14-R-09), §14.4 (S14-INV-02, S14-INV-03); ENGINE_SPEC §0.4
``PostedAmountInput``, §8.4 S08-R-08 and S02-R-02; POLICIES ALG-09 (CHK-090); 04 E-31; 05 RCP-04 to
RCP-09. Stages 10 and 11 are built in lane L2-4, so the tests pass a fake consumed state carrying
``PartInputs`` and fake producer nodes (D-81 integration after merge; L2-5-Q-24); stage 12 runs for
real, CHK-090 measures its relief through stage 09, and every trace re-evaluates node for node
(DG-ENG-04).
"""

from __future__ import annotations

import dataclasses
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from fractions import Fraction

import pytest
from erev_engine import ENGINE_VERSION
from erev_engine.bundle import AccountMappingInput, MappingRuleInput, PostedAmountInput
from erev_engine.enums import BookCode
from erev_engine.money import format_money, largest_remainder
from erev_engine.stages import s12_fx_entities, s14_posting
from erev_engine.stages.s08_estimates_late_events import assign_posting_period
from erev_engine.stages.s09_recognition import run as recognise
from erev_engine.stages.s12_fx_entities import FxFlows
from erev_engine.stages.s14_posting import (
    POSTING_CLASSES,
    PartInputs,
    PostedTotals,
    PostingState,
    RoleDelta,
    RoleKey,
    classes_posted_by,
    posting_class,
)
from erev_engine.stages.state import (
    AllocatedState,
    BookContext,
    EventView,
    ObligationState,
    PostedIndex,
    RateIndex,
    Target,
)
from erev_engine.trace import SourceRef, Trace, TraceBuilder, TraceNode, reevaluate
from support import bundles
from support.recognition import (
    CONTRACT_KEY,
    INCEPTION,
    allocated_state,
    book_context,
    contract_view,
    event_view,
    obligation,
    segment,
    usd,
)

ENTITY = bundles.ENTITY_CODE
CL, REVENUE = "CONTRACT_LIABILITY", "REVENUE"
UR, CA = "UNBILLED_RECEIVABLE", "CONTRACT_ASSET"
JANUARY_2023 = date(2023, 1, 1)
YEAR_END_2023 = date(2023, 12, 31)
POSTABLE = frozenset({"open", "closing", "reopened"})
# Golden Contract 1 (legacy 02 §5.3): price 1,300.00; (POB, quantity, extended SSP).
GOLDEN_CONTRACT_1 = (
    ("POB #1", "5", 500),
    ("POB #2", "2", 368),
    ("POB #3", "1", 150),
    ("POB #4", "1000", 1000),
)


@dataclass(frozen=True, slots=True)
class _Costs:
    """A fake stage 11 output as stages 12 and 14 read it (L2-5-Q-10, L2-5-Q-24)."""

    allocated: AllocatedState
    fx_flows: FxFlows
    part_inputs: PartInputs


@dataclass(frozen=True, slots=True)
class _Run:
    posting: PostingState
    trace: Trace


def _period(month: int, year: int = 2026) -> str:
    return f"FY{year}-P{month:02d}"


def _target(
    measure: str, subject: str, period_key: str, value: int, *, cause: str | None = None
) -> Target:
    node = f"{measure}:{subject}" + ("" if cause is None else f"#{cause}") + f":{period_key}"
    return Target(BookCode.ASC606, ENTITY, subject, measure, period_key, cause, value, None, node)


def _relief(subject: str, values: Mapping[str, int]) -> tuple[Target, ...]:
    return tuple(
        _target("revenue_relief_cum", subject, key, value) for key, value in values.items()
    )


def _by_cause(subject: str, values: Mapping[tuple[str, str], int]) -> tuple[Target, ...]:
    return tuple(
        _target("revenue_relief", subject, key, value, cause=cause)
        for (key, cause), value in values.items()
    )


def _reclass(subject: str, role: str, values: Mapping[str, int]) -> tuple[Target, ...]:
    return tuple(
        _target("netting_reclass_amount", subject, key, value, cause=role)
        for key, value in values.items()
    )


def _emit(tb: TraceBuilder, targets: Iterable[Target], currency: str = "USD") -> None:
    """Fake producer nodes of stages 09 to 11 (D-81 integration after merge)."""
    mu = bundles.currencies(currency)[currency].minor_unit
    for target in targets:
        measure, subject, period_key = target.node_id.rsplit(":", 2)
        tb.node(
            measure=measure,
            subject_key=subject,
            period_key=period_key,
            value=target.value,
            currency=currency,
            minor_unit=mu,
            formula_id="rec.catch_up.sum.v1",
            inputs=[
                SourceRef(
                    "source_record", target.node_id, {"value": format_money(target.value, mu)}
                )
            ],
            narrative_key="rec.catch_up.sum",
        )


def _compute(
    ctx: BookContext,
    allocated: AllocatedState,
    inputs: PartInputs,
    *,
    posted: Iterable[PostedAmountInput] = (),
    pass_name: str | None = None,
    voided: Iterable[str] = (),
    tb: TraceBuilder | None = None,
    fake: bool = True,
) -> _Run:
    tb = TraceBuilder(engine_version=ENGINE_VERSION) if tb is None else tb
    if fake:
        _emit(
            tb, (*inputs.relief, *inputs.refund_liabilities, *inputs.concessions, *inputs.reclass)
        )
    fx = s12_fx_entities.run(ctx, _Costs(allocated, FxFlows(()), inputs), tb, rates=RateIndex(()))
    posting = s14_posting.run(
        ctx, fx, tb, posted=PostedIndex(tuple(posted)), pass_name=pass_name, voided=tuple(voided)
    )
    trace = tb.build(root_measures={})
    assert reevaluate(trace) == {node.id: node.value for node in trace.nodes}
    _assert_inv_03(ctx, posting.deltas)
    return _Run(posting, trace)


def _assert_inv_03(ctx: BookContext, deltas: Iterable[RoleDelta]) -> None:
    """S14-INV-03: no delta posts into a closed, locked or future period; origins carry reasons."""
    for delta in deltas:
        calendar = ctx.entities[delta.key.entity]
        period = next(p for p in calendar.periods if p.period_key == delta.posting_period_key)
        assert dict(period.states)[str(ctx.book_code)] in POSTABLE
        if delta.origin_period_key is not None:
            assert delta.reason_code in ("LATE_EVENT", "VOID")


def _posted(*runs: _Run) -> tuple[PostedAmountInput, ...]:
    """The posted amounts after sealing every delta of ``runs`` (RCP-05)."""
    items = [
        PostedAmountInput(
            book_code=delta.key.book_code,
            entity_code=delta.key.entity,
            subject_key=delta.key.subject_key,
            entry_kind=delta.key.entry_kind,
            account_role=delta.key.account_role,
            clearing_purpose=delta.key.clearing_purpose,
            counterparty_entity_code=delta.key.counterparty_entity,
            period_key=delta.posting_period_key,
            origin_period_key=delta.origin_period_key,
            posting_class=delta.posting_class,
            txn_currency=delta.txn_currency,
            functional_currency=delta.functional_currency,
            amount_txn=delta.amount_txn,
            amount_functional=delta.amount_functional,
            reason_code=delta.reason_code,
        )
        for run in runs
        for delta in run.posting.deltas
    ]
    return tuple(
        sorted(
            items,
            key=lambda item: (
                item.book_code,
                item.entity_code,
                item.subject_key,
                item.entry_kind,
                item.account_role,
                item.clearing_purpose or "",
                item.period_key,
                item.origin_period_key or "",
                item.posting_class,
            ),
        )
    )


def _rows(deltas: Iterable[RoleDelta]) -> list[tuple[object, ...]]:
    return [
        (
            delta.key.subject_key,
            delta.key.entry_kind,
            delta.key.account_role,
            delta.posting_period_key,
            delta.origin_period_key,
            delta.posting_class,
            delta.reason_code,
            delta.amount_txn,
        )
        for delta in deltas
    ]


def _node(trace: Trace, node_id: str) -> TraceNode:
    return next(node for node in trace.nodes if node.id == node_id)


def _obligation(key: str, amount: str = "3000.00") -> ObligationState:
    minor = usd(amount)
    start, end = date(2026, 1, 1), date(2026, 12, 31)
    return obligation(
        key, [segment(Fraction(minor, 100), minor, start=start, end=end)], start=start, end=end
    )


def _context(
    months: int, states: Mapping[str, str] | None = None, *, horizon: str | None = None
) -> BookContext:
    return book_context(bundles.entity(months=months, states=states), horizon=horizon)


def _posted_amount(
    subject: str,
    role: str,
    period_key: str,
    amount: int,
    *,
    kind: str,
    origin: str | None = None,
) -> PostedAmountInput:
    return PostedAmountInput(
        "ASC606",
        ENTITY,
        subject,
        "REVENUE_RECOGNITION",
        role,
        None,
        None,
        period_key,
        origin,
        posting_class(kind),
        "USD",
        "USD",
        amount,
        amount,
    )


def test_s14_r04_period_target_and_posted_by_origin() -> None:
    # 04 E-31: the posting class of a posted line follows its posting kind (RCP-05).
    assert dict(POSTING_CLASSES) == {
        "ENGINE_COMPUTE": "EVENT",
        "MANUAL_ADJUSTMENT": "EVENT",
        "VOID_REVERSAL": "EVENT",
        "CLOSE_RELEASE": "TIME",
        "FX_REMEASUREMENT": "TIME",
        "NETTING_RECLASS": "TIME",
    }
    with pytest.raises(ValueError, match="E-31"):
        posting_class("REVERSAL")
    p1 = f"{CONTRACT_KEY}/P1"
    ctx = _context(3, {_period(1): "closed"})
    # January closed; February open with a NORMAL release at close and a modification catch-up.
    inputs = PartInputs(
        relief=_relief(p1, {_period(1): 10000, _period(2): 25000, _period(3): 26000}),
        relief_by_cause=_by_cause(
            p1,
            {
                (_period(1), "NORMAL"): 10000,
                (_period(2), "NORMAL"): 4000,
                (_period(2), "MODIFICATION"): 11000,
                (_period(3), "MODIFICATION"): 1000,
            },
        ),
        released_at_close=(p1,),
    )
    posted = [
        # January: 90.00 released at close, then a carry of 10.00 with origin January in March.
        _posted_amount(p1, CL, _period(1), 9000, kind="CLOSE_RELEASE"),
        _posted_amount(p1, REVENUE, _period(1), -9000, kind="CLOSE_RELEASE"),
        _posted_amount(p1, CL, _period(3), 1000, kind="ENGINE_COMPUTE", origin=_period(1)),
        _posted_amount(p1, REVENUE, _period(3), -1000, kind="ENGINE_COMPUTE", origin=_period(1)),
        # February: 40.00 released at close and the 110.00 catch-up at compute.
        _posted_amount(p1, CL, _period(2), 4000, kind="CLOSE_RELEASE"),
        _posted_amount(p1, REVENUE, _period(2), -4000, kind="CLOSE_RELEASE"),
        _posted_amount(p1, CL, _period(2), 11000, kind="ENGINE_COMPUTE"),
        _posted_amount(p1, REVENUE, _period(2), -11000, kind="ENGINE_COMPUTE"),
    ]
    run = _compute(ctx, allocated_state([_obligation("P1")]), inputs, posted=posted)
    key = RoleKey("ASC606", ENTITY, p1, "REVENUE_RECOGNITION", CL, None, None)
    totals = PostedTotals.of(ctx, PostedIndex(tuple(posted)))
    assert totals.by_origin(key, _period(1), ("EVENT",)) == (1000, 1000)
    assert totals.by_origin(key, _period(1), ("TIME",)) == (9000, 9000)
    assert totals.by_origin(key, _period(1), ("EVENT", "TIME")) == (10000, 10000)
    assert totals.by_origin(key, _period(2), ("EVENT",)) == (11000, 11000)
    assert totals.by_origin(key, _period(2), ("TIME",)) == (4000, 4000)
    # Cumulative role targets and their TIME shares; period_target = C(p) − C(p − 1).
    targets = {t.period_key: t for t in run.posting.role_targets if t.key == key}
    assert [(t.amount_txn, t.time_txn, t.passes) for t in targets.values()] == [
        (10000, 10000, ("CLOSE_RELEASE",)),
        (25000, 14000, ("CLOSE_RELEASE",)),
        (26000, 14000, ("CLOSE_RELEASE",)),
    ]
    assert _node(run.trace, targets[_period(2)].node_id).value == "250.00"
    revenue = RoleKey("ASC606", ENTITY, p1, "REVENUE_RECOGNITION", REVENUE, None, None)
    assert [t.amount_txn for t in run.posting.role_targets if t.key == revenue] == [
        -10000,
        -25000,
        -26000,
    ]
    # January posted in full by origin; February's EVENT part equals its posted EVENT amount; only
    # March's 10.00 catch-up remains, and under COMMAND no TIME amount posts.
    assert _rows(run.posting.deltas) == [
        (p1, "REVENUE_RECOGNITION", CL, _period(3), None, "EVENT", None, 1000),
        (p1, "REVENUE_RECOGNITION", REVENUE, _period(3), None, "EVENT", None, -1000),
    ]
    march = run.posting.deltas[0]
    node = _node(run.trace, march.node_id)
    assert (node.formula_id, node.value, node.params["class"]) == (
        "post.delta.v1",
        "10.00",
        "EVENT",
    )
    assert node.id == f"posting_delta:{p1}/REVENUE_RECOGNITION/{CL}/EVENT:{_period(3)}"
    assert march.effective_date == date(2026, 3, 31)


def test_s14_r05_classes_posted_by_trigger() -> None:
    for trigger in ("COMMAND", "REPLAY_VERIFY", "RESTATE", "UPGRADE_VALIDATE", "FX_REPUBLISH"):
        assert classes_posted_by(trigger, None) == ("EVENT",)
    for trigger in ("POLICY_RERUN", "MIGRATION", "DRY_RUN"):
        assert classes_posted_by(trigger, None) == ("EVENT",)
    for pass_name in ("CLOSE_RELEASE", "FX_REMEASUREMENT", "NETTING_RECLASS"):
        assert classes_posted_by("CLOSE_RELEASE", pass_name) == ("TIME",)
    with pytest.raises(ValueError, match="runs no close-run pass"):
        classes_posted_by("COMMAND", "NETTING_RECLASS")
    with pytest.raises(ValueError, match="names its pass"):
        classes_posted_by("CLOSE_RELEASE", None)
    with pytest.raises(ValueError, match="E-87"):
        classes_posted_by("SCHEDULED", None)

    services, hardware = f"{CONTRACT_KEY}/S", f"{CONTRACT_KEY}/H"
    ctx = _context(2, {_period(1): "closed"})
    inputs = PartInputs(
        relief=(
            *_relief(services, {_period(1): 10000, _period(2): 20000}),
            *_relief(hardware, {_period(1): 5000, _period(2): 7500}),
        ),
        relief_by_cause=(
            *_by_cause(services, {(_period(1), "NORMAL"): 10000, (_period(2), "NORMAL"): 10000}),
            *_by_cause(hardware, {(_period(1), "NORMAL"): 5000, (_period(2), "NORMAL"): 2500}),
        ),
        released_at_close=(services,),  # time-elapsed services; hardware is delivery-driven
        reclass=_reclass(services, UR, {_period(1): 3000, _period(2): 4500}),
    )
    allocated = allocated_state([_obligation("S"), _obligation("H")])

    def rows(trigger: str, pass_name: str | None) -> tuple[str, list[tuple[object, ...]]]:
        run = _compute(
            dataclasses.replace(ctx, trigger=trigger), allocated, inputs, pass_name=pass_name
        )
        return run.posting.posting_kind, _rows(run.posting.deltas)

    # COMMAND: every amount of closed January carries into February; February's EVENT amounts post;
    # the reclass of the locked period never carries (S14-R-07).
    kind, command = rows("COMMAND", None)
    assert kind == "ENGINE_COMPUTE"
    assert command == [
        (hardware, "REVENUE_RECOGNITION", CL, _period(2), _period(1), "EVENT", "LATE_EVENT", 5000),
        (hardware, "REVENUE_RECOGNITION", CL, _period(2), None, "EVENT", None, 2500),
        (
            hardware,
            "REVENUE_RECOGNITION",
            REVENUE,
            _period(2),
            _period(1),
            "EVENT",
            "LATE_EVENT",
            -5000,
        ),
        (hardware, "REVENUE_RECOGNITION", REVENUE, _period(2), None, "EVENT", None, -2500),
        (services, "REVENUE_RECOGNITION", CL, _period(2), _period(1), "EVENT", "LATE_EVENT", 10000),
        (
            services,
            "REVENUE_RECOGNITION",
            REVENUE,
            _period(2),
            _period(1),
            "EVENT",
            "LATE_EVENT",
            -10000,
        ),
    ]
    # DRY_RUN computes the same deltas as COMMAND (RCP-08).
    assert rows("DRY_RUN", None) == ("ENGINE_COMPUTE", command)
    # CLOSE_RELEASE posts only the TIME amounts of open periods for the parts of its pass.
    assert rows("CLOSE_RELEASE", "CLOSE_RELEASE") == (
        "CLOSE_RELEASE",
        [
            (services, "REVENUE_RECOGNITION", CL, _period(2), None, "TIME", None, 10000),
            (services, "REVENUE_RECOGNITION", REVENUE, _period(2), None, "TIME", None, -10000),
        ],
    )
    assert rows("CLOSE_RELEASE", "NETTING_RECLASS") == (
        "NETTING_RECLASS",
        [
            (services, "NETTING_RECLASS", CL, _period(2), None, "TIME", None, -4500),
            (services, "NETTING_RECLASS", UR, _period(2), None, "TIME", None, 4500),
        ],
    )
    assert rows("CLOSE_RELEASE", "FX_REMEASUREMENT") == ("FX_REMEASUREMENT", [])


def _golden_contract_1() -> list[ObligationState]:
    """Inception segments: X = 1,300 × extended SSP ÷ 2,018, A by largest remainder (ALG-01)."""
    total = sum(ssp for *_, ssp in GOLDEN_CONTRACT_1)
    posted = largest_remainder(
        1300 * 100,
        [Fraction(ssp) for *_, ssp in GOLDEN_CONTRACT_1],
        [key for key, *_ in GOLDEN_CONTRACT_1],
    )
    obligations = []
    for (key, quantity, ssp), a_posted in zip(GOLDEN_CONTRACT_1, posted, strict=True):
        seg = segment(
            Fraction(1300 * ssp, total),
            a_posted,
            start=JANUARY_2023,
            end=YEAR_END_2023,
            quantity=Fraction(quantity),
            measure="UNITS_DELIVERED",
        )
        obligations.append(
            obligation(
                key,
                [seg],
                contract_key="Contract 1",
                method="UNITS_DELIVERED",
                convention=None,
                start=JANUARY_2023,
                quantity=Fraction(quantity),
            )
        )
    return obligations


def _late_deliveries() -> list[EventView]:
    """EX-08-A: deliveries effective 31 January 2023 and recorded on 5 February, after the lock."""
    events = []
    for version, key, quantity in ((5, "POB #1", "2"), (6, "POB #2", "1"), (7, "POB #3", "0.5")):
        ev = event_view(
            "Contract 1",
            version,
            "DELIVERY_RECORDED",
            date(2023, 1, 31),
            {"obligation_key": key, "quantity": Decimal(quantity), "trigger": "DELIVERY"},
            obligation_keys=[key],
        )
        events.append(dataclasses.replace(ev, recorded_at=datetime(2023, 2, 5, 15, tzinfo=UTC)))
    return events


def _chk_090(
    states: Mapping[str, str], posted: Sequence[PostedAmountInput] = ()
) -> tuple[BookContext, _Run]:
    ctx = book_context(
        bundles.entity(start=JANUARY_2023, months=12, states=states), preset="LEGACY_PARITY"
    )
    st = allocated_state(_golden_contract_1(), events=_late_deliveries(), inception=JANUARY_2023)
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    recognition = recognise(ctx, st, tb)
    relief = tuple(
        dataclasses.replace(target, measure="revenue_relief_cum")
        for target in recognition.revenue_targets
        if target.measure == "revenue_cum"
    )
    run = _compute(ctx, st, PartInputs(relief=relief), posted=posted, tb=tb, fake=False)
    return ctx, run


def test_chk_090_february_intents() -> None:
    ctx, run = _chk_090({_period(1, 2023): "closed"})
    assert assign_posting_period(ctx, ENTITY, date(2023, 1, 31)).posting_period_key == "FY2023-P02"
    deltas = run.posting.deltas
    # Dr CONTRACT_LIABILITY 295.69 / Cr REVENUE 128.84, 118.53 and 48.32 in February with origin
    # January and reason LATE_EVENT; nothing posts into January (CHK-090; S14-INV-03).
    assert {
        (d.posting_period_key, d.origin_period_key, d.reason_code, d.posting_class) for d in deltas
    } == {("FY2023-P02", "FY2023-P01", "LATE_EVENT", "EVENT")}
    revenue = {d.key.subject_key: d.amount_txn for d in deltas if d.key.account_role == REVENUE}
    assert revenue == {
        "Contract 1/POB #1": -usd("128.84"),
        "Contract 1/POB #2": -usd("118.53"),
        "Contract 1/POB #3": -usd("48.32"),
    }
    assert sum(d.amount_txn for d in deltas if d.key.account_role == CL) == usd("295.69")
    assert all(d.effective_date == date(2023, 1, 31) for d in deltas)
    # The carry cites the January target and the posted total with origin January.
    carry = next(d for d in deltas if d.key.account_role == CL)
    node = _node(run.trace, carry.node_id)
    assert node.id == (
        "posting_delta:Contract 1/POB #1/REVENUE_RECOGNITION/CONTRACT_LIABILITY/EVENT/FY2023-P01"
        ":FY2023-P02"
    )
    assert (node.params["class"], node.inputs[0]) == ("ALL", carry.target_node_id)
    assert carry.target_node_id.endswith(":FY2023-P01")
    # The February intents: one entry per obligation, Dr CONTRACT_LIABILITY / Cr REVENUE.
    intents = run.posting.posting_intents
    assert [
        (i.posting_period_key, i.origin_period_key, i.reason_code, i.entry_kind) for i in intents
    ] == [("FY2023-P02", "FY2023-P01", "LATE_EVENT", "REVENUE_RECOGNITION")] * 3
    lines = sorted(
        (intent.subject_key, line.side, line.account_role, line.account_code, line.amount_txn)
        for intent in intents
        for line in intent.lines
    )
    assert lines == [
        ("Contract 1/POB #1", "C", REVENUE, "4000", usd("128.84")),
        ("Contract 1/POB #1", "D", CL, "2400", usd("128.84")),
        ("Contract 1/POB #2", "C", REVENUE, "4000", usd("118.53")),
        ("Contract 1/POB #2", "D", CL, "2400", usd("118.53")),
        ("Contract 1/POB #3", "C", REVENUE, "4000", usd("48.32")),
        ("Contract 1/POB #3", "D", CL, "2400", usd("48.32")),
    ]
    assert {run.posting.effective_dates[intent.entry_key] for intent in intents} == {
        date(2023, 1, 31)
    }


def test_s14_inv_02_repeat_compute_emits_nothing() -> None:
    # A compute over a bundle whose posted amounts equal the previous intents emits nothing.
    states = {_period(1, 2023): "closed"}
    _, first = _chk_090(states)
    assert first.posting.deltas
    _, repeat = _chk_090(states, _posted(first))
    assert repeat.posting.deltas == ()
    # The same holds for the netting reclass pass and its reversals, and for released revenue.
    p1 = f"{CONTRACT_KEY}/P1"
    ctx = dataclasses.replace(_context(3), trigger="CLOSE_RELEASE")
    inputs = PartInputs(
        relief=_relief(p1, {_period(1): 10000, _period(2): 20000, _period(3): 30000}),
        relief_by_cause=_by_cause(p1, {(_period(m), "NORMAL"): 10000 for m in (1, 2, 3)}),
        released_at_close=(p1,),
        reclass=_reclass(p1, UR, {_period(1): 3000, _period(2): 1000, _period(3): 2000}),
    )
    allocated = allocated_state([_obligation("P1")])
    runs: list[_Run] = []
    for pass_name in ("CLOSE_RELEASE", "NETTING_RECLASS"):
        runs.append(_compute(ctx, allocated, inputs, posted=_posted(*runs), pass_name=pass_name))
        assert runs[-1].posting.deltas
        again = _compute(ctx, allocated, inputs, posted=_posted(*runs), pass_name=pass_name)
        assert again.posting.deltas == ()


def test_s14_r07_netting_reclass_and_reversal() -> None:
    p1, p2 = f"{CONTRACT_KEY}/P1", f"{CONTRACT_KEY}/P2"
    inputs = PartInputs(
        reclass=(
            *_reclass(p1, UR, {_period(m): 300000 for m in (1, 2, 3)}),
            *_reclass(p2, CA, {_period(m): 200000 for m in (1, 2, 3)}),
        )
    )
    allocated = allocated_state([_obligation("P1"), _obligation("P2")])

    def close(month: int, *previous: _Run) -> _Run:
        states = {_period(m): "closed" for m in range(1, month)}
        ctx = dataclasses.replace(
            _context(4, states, horizon=_period(month)), trigger="CLOSE_RELEASE"
        )
        return _compute(
            ctx, allocated, inputs, posted=_posted(*previous), pass_name="NETTING_RECLASS"
        )

    def lines(run: _Run) -> list[tuple[object, ...]]:
        return sorted(
            (
                d.key.entry_kind,
                d.effective_date,
                d.key.subject_key,
                d.key.account_role,
                d.amount_txn,
            )
            for d in run.posting.deltas
        )

    january = close(1)
    # EX-10-A: Dr UR 3,000.00 (P1) / Cr CL 3,000.00; Dr CA 2,000.00 (P2) / Cr CL 2,000.00 on 31 Jan.
    assert lines(january) == [
        ("NETTING_RECLASS", date(2026, 1, 31), p1, CL, -300000),
        ("NETTING_RECLASS", date(2026, 1, 31), p1, UR, 300000),
        ("NETTING_RECLASS", date(2026, 1, 31), p2, CA, 200000),
        ("NETTING_RECLASS", date(2026, 1, 31), p2, CL, -200000),
    ]
    february = close(2, january)
    # January is locked: its reclass is skipped; February reverses it on 1 Feb and reclasses anew.
    assert lines(february) == [
        ("NETTING_RECLASS", date(2026, 2, 28), p1, CL, -300000),
        ("NETTING_RECLASS", date(2026, 2, 28), p1, UR, 300000),
        ("NETTING_RECLASS", date(2026, 2, 28), p2, CA, 200000),
        ("NETTING_RECLASS", date(2026, 2, 28), p2, CL, -200000),
        ("NETTING_RECLASS_REVERSAL", date(2026, 2, 1), p1, CL, 300000),
        ("NETTING_RECLASS_REVERSAL", date(2026, 2, 1), p1, UR, -300000),
        ("NETTING_RECLASS_REVERSAL", date(2026, 2, 1), p2, CA, -200000),
        ("NETTING_RECLASS_REVERSAL", date(2026, 2, 1), p2, CL, 200000),
    ]
    march = close(3, january, february)
    # February is locked too: March reverses February's ACTUALLY POSTED reclass on 1 Mar and
    # reclasses anew on 31 Mar (S14-R-07; the dates the T1 PRP-PROPS one-cent regression cites —
    # Codex production-20260922-0133 W1).
    assert lines(march) == [
        ("NETTING_RECLASS", date(2026, 3, 31), p1, CL, -300000),
        ("NETTING_RECLASS", date(2026, 3, 31), p1, UR, 300000),
        ("NETTING_RECLASS", date(2026, 3, 31), p2, CA, 200000),
        ("NETTING_RECLASS", date(2026, 3, 31), p2, CL, -200000),
        ("NETTING_RECLASS_REVERSAL", date(2026, 3, 1), p1, CL, 300000),
        ("NETTING_RECLASS_REVERSAL", date(2026, 3, 1), p1, UR, -300000),
        ("NETTING_RECLASS_REVERSAL", date(2026, 3, 1), p2, CA, -200000),
        ("NETTING_RECLASS_REVERSAL", date(2026, 3, 1), p2, CL, 200000),
    ]
    april = close(4, january, february, march)
    # April has no attribution: no reclass, but the March reclass is still reversed on 1 April.
    assert lines(april) == [
        ("NETTING_RECLASS_REVERSAL", date(2026, 4, 1), p1, CL, 300000),
        ("NETTING_RECLASS_REVERSAL", date(2026, 4, 1), p1, UR, -300000),
        ("NETTING_RECLASS_REVERSAL", date(2026, 4, 1), p2, CA, -200000),
        ("NETTING_RECLASS_REVERSAL", date(2026, 4, 1), p2, CL, 200000),
    ]
    reversal = next(
        d
        for d in april.posting.deltas
        if d.key.entry_kind == "NETTING_RECLASS_REVERSAL" and d.key.account_role == UR
    )
    target = _node(april.trace, reversal.target_node_id)
    # Cumulative reversal through April: the February, March and April reversals of P1.
    assert (target.formula_id, target.value) == ("post.role_target.v1", "-9000.00")
    assert {
        d.posting_class for run in (january, february, march, april) for d in run.posting.deltas
    } == {"TIME"}
    # A computation never reverses or carries a reclass (COMMAND posts no TIME amount).
    command = _compute(
        _context(4, {_period(1): "closed"}), allocated, inputs, posted=_posted(january)
    )
    assert command.posting.deltas == ()


def test_s14_r08_void_delta() -> None:
    p1 = f"{CONTRACT_KEY}/P1"
    allocated = allocated_state([_obligation("P1")])
    # Two deliveries in January post 600.00; February posts a third of 300.00.
    posted_run = _compute(
        _context(2),
        allocated,
        PartInputs(relief=_relief(p1, {_period(1): 60000, _period(2): 90000})),
    )
    posted = _posted(posted_run)
    # The second January delivery is voided after January was locked, and the February delivery
    # is voided while February is open: the differences post in February with reason VOID.
    ctx = _context(2, {_period(1): "closed"})
    run = _compute(
        ctx,
        allocated,
        PartInputs(relief=_relief(p1, {_period(1): 30000, _period(2): 30000})),
        posted=posted,
        voided=[CONTRACT_KEY],
    )
    assert _rows(run.posting.deltas) == [
        (p1, "REVENUE_RECOGNITION", CL, _period(2), _period(1), "EVENT", "VOID", -30000),
        (p1, "REVENUE_RECOGNITION", CL, _period(2), None, "EVENT", "VOID", -30000),
        (p1, "REVENUE_RECOGNITION", REVENUE, _period(2), _period(1), "EVENT", "VOID", 30000),
        (p1, "REVENUE_RECOGNITION", REVENUE, _period(2), None, "EVENT", "VOID", 30000),
    ]
    assert run.posting.posting_kind == "VOID_REVERSAL"
    # A void of another contract of the group leaves the reason codes of this contract alone.
    other = _compute(
        ctx,
        allocated,
        PartInputs(relief=_relief(p1, {_period(1): 30000, _period(2): 30000})),
        posted=posted,
        voided=["K-99"],
    )
    assert {d.reason_code for d in other.posting.deltas} == {"LATE_EVENT", None}
    assert other.posting.posting_kind == "ENGINE_COMPUTE"


def test_l9_run_q4_multi_member_component_draft_and_void_follow_the_owning_member() -> None:
    """S02-R-02 drafts and the S14-R-08 void set of a multi-member group's refund component follow
    the owning member (D-90d L9-RUN-Q-4): the RETURN component of C-B posts nothing while C-B is
    DRAFT although C-A is ACTIVE, is voided with C-B and not with C-A. Before the fix the component
    belonged to every member: it posted while any member was ACTIVE and was voided with any member.
    A singleton group is unchanged."""
    seg = segment(Fraction(600), usd("600.00"), start=date(2026, 1, 1), end=date(2026, 1, 31))
    a, b = (obligation("POB-001", [seg], contract_key=key) for key in ("C-A", "C-B"))
    component = f"G@{ENTITY}/RETURN/{b.subject_key}"
    inputs = PartInputs(
        relief=(
            *_relief(a.subject_key, {_period(1): 60000}),
            *_relief(b.subject_key, {_period(1): 58000}),
        ),
        refund_liabilities=(
            _target("refund_liability", component, _period(1), 2000, cause="RETURN"),
        ),
    )
    ctx = _context(1)
    active = dataclasses.replace(allocated_state([a, b]), group_code="G")
    posted = _compute(ctx, active, inputs)
    subjects = {delta.key.subject_key for delta in posted.posting.deltas}
    assert {a.subject_key, b.subject_key, component} <= subjects
    # C-B DRAFT: its obligation and its component post nothing; C-A posts.
    drafted = dataclasses.replace(
        active,
        contracts=(
            contract_view("C-A", statuses=((INCEPTION, "ACTIVE"),)),
            contract_view("C-B", statuses=((INCEPTION, "DRAFT"),)),
        ),
    )
    held = _compute(ctx, drafted, inputs)
    assert {delta.key.subject_key for delta in held.posting.deltas} == {a.subject_key}
    # Voids: the component follows C-B, not C-A.
    for voided, expected in (
        (["C-B"], {b.subject_key: "VOID", component: "VOID", a.subject_key: None}),
        (["C-A"], {a.subject_key: "VOID", b.subject_key: None, component: None}),
    ):
        run = _compute(ctx, active, inputs, voided=voided)
        reasons = {
            subject: {
                delta.reason_code
                for delta in run.posting.deltas
                if delta.key.subject_key == subject
            }
            for subject in expected
        }
        assert reasons == {subject: {reason} for subject, reason in expected.items()}
    # A singleton group's component follows its one member as before.
    single = allocated_state([_obligation("P1")])
    p1 = f"{CONTRACT_KEY}/P1"
    single_component = f"CG-1@{ENTITY}/RETURN/{p1}"
    single_inputs = PartInputs(
        relief=_relief(p1, {_period(1): 60000}),
        refund_liabilities=(
            _target("refund_liability", single_component, _period(1), 2000, cause="RETURN"),
        ),
    )
    for voided, reason in (([CONTRACT_KEY], "VOID"), (["K-99"], None)):
        run = _compute(ctx, single, single_inputs, voided=voided)
        assert {
            delta.reason_code
            for delta in run.posting.deltas
            if delta.key.subject_key == single_component
        } == {reason}


def _mapping(version_key: str, revenue_account: str) -> AccountMappingInput:
    accounts = {**{role: code for role, _, code in bundles.ACCOUNTS}, REVENUE: revenue_account}
    rules = tuple(
        MappingRuleInput(role, purpose, None, None, None, None, accounts[role], {}, 0, 0)
        for role, purpose, _ in sorted(bundles.ACCOUNTS, key=lambda row: (row[0], row[1] or ""))
    )
    return AccountMappingInput(version_key, bundles.ZERO_SHA256, rules)


def test_s14_r09_mapping_change_never_reposts() -> None:
    p1 = f"{CONTRACT_KEY}/P1"
    allocated = allocated_state([_obligation("P1")])
    inputs = PartInputs(relief=_relief(p1, {_period(1): 40000, _period(2): 40000}))
    ctx = dataclasses.replace(_context(2), mapping=_mapping("MAP@v1", "4000"))
    first = _compute(ctx, allocated, inputs)
    assert first.posting.deltas
    # A new mapping version changes no posted period: the posted grain has no account (RCP-05).
    remapped = dataclasses.replace(ctx, mapping=_mapping("MAP@v2", "4100"))
    again = _compute(remapped, allocated, inputs, posted=_posted(first))
    assert again.posting.deltas == ()
    assert [t.amount_txn for t in again.posting.role_targets] == [
        t.amount_txn for t in first.posting.role_targets
    ]
    # A later delivery yields a new delta in February only.
    later = PartInputs(relief=_relief(p1, {_period(1): 40000, _period(2): 55000}))
    delta = _compute(remapped, allocated, later, posted=_posted(first))
    assert _rows(delta.posting.deltas) == [
        (p1, "REVENUE_RECOGNITION", CL, _period(2), None, "EVENT", None, 15000),
        (p1, "REVENUE_RECOGNITION", REVENUE, _period(2), None, "EVENT", None, -15000),
    ]
    # The first intents resolved REVENUE with v1; the new delta resolves with the pinned v2.
    revenue_codes = {
        line.account_code
        for intent in first.posting.posting_intents
        for line in intent.lines
        if line.account_role == REVENUE
    }
    assert revenue_codes == {"4000"}
    (intent,) = delta.posting.posting_intents
    line = next(line for line in intent.lines if line.account_role == REVENUE)
    assert (intent.posting_period_key, line.account_code) == (_period(2), "4100")
    node = _node(delta.trace, f"account_resolution:{line.line_key}:{_period(2)}")
    assert (node.value, node.params["mapping_version_key"]) == ("3", "MAP@v2")
    ((source),) = node.inputs
    assert isinstance(source, SourceRef) and source.ref_id.startswith("MAP@v2/REVENUE/")


def test_s02_r02_draft_contract_posts_nothing() -> None:
    p1 = f"{CONTRACT_KEY}/P1"
    inputs = PartInputs(relief=_relief(p1, {_period(1): 40000, _period(2): 55000}))
    draft = allocated_state([_obligation("P1")], statuses=((date(2026, 1, 1), "DRAFT"),))
    run = _compute(_context(2), draft, inputs)
    assert [t.amount_txn for t in run.posting.part_targets] == [40000, 55000]
    assert {t.key.account_role for t in run.posting.role_targets} == {CL, REVENUE}
    assert run.posting.deltas == ()
    assert run.posting.posting_intents == ()
    # After activation the targets from inception post (S02-R-02).
    active = allocated_state(
        [_obligation("P1")],
        statuses=((date(2026, 1, 1), "DRAFT"), (date(2026, 2, 3), "ACTIVE")),
    )
    posted = _compute(_context(2), active, inputs)
    assert sum(d.amount_txn for d in posted.posting.deltas if d.key.account_role == CL) == 55000


# --- S14-R-27 reason variants (D-98 candidate 19; lane ENG-C8 Q-1) --------------------------------

COST_SUBJECT = f"{CONTRACT_KEY}/EV-000004"
CAPITALIZATION = "CONTRACT_COST_CAPITALIZATION"
OBTAIN_ASSET, COST_CLEARING = "COST_TO_OBTAIN_ASSET", "CONTRACT_COST_CLEARING"


def _costs(capitalised: Mapping[str, int], clawback: Mapping[str, int]) -> tuple[Target, ...]:
    """Stage 11 cost measures of one cost to obtain (E-83 ``OBTAIN``): cumulative capitalised and
    clawed back per period end (S11-R-04, S11-R-12)."""
    return (
        *(
            _target("cost_capitalised", COST_SUBJECT, key, value, cause="OBTAIN")
            for key, value in capitalised.items()
        ),
        *(
            _target("cost_clawback_cum", COST_SUBJECT, key, value, cause="OBTAIN")
            for key, value in clawback.items()
        ),
    )


def _cost_run(
    ctx: BookContext,
    costs: tuple[Target, ...],
    *,
    posted: Iterable[PostedAmountInput] = (),
    voided: Iterable[str] = (),
) -> _Run:
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    _emit(tb, costs)
    return _compute(
        ctx,
        allocated_state([_obligation("P1")]),  # the K-01 view resolves the subject's contract
        PartInputs(cost_assets=costs),
        posted=posted,
        voided=voided,
        tb=tb,
        fake=False,
    )


def test_s14_r27_clawback_is_its_own_entry_with_reason_code() -> None:
    """A commission 10,000.00 capitalised in January and 2,000.00 clawed back in the same open
    month: JET-09a posts Dr COST_TO_OBTAIN_ASSET / Cr CONTRACT_COST_CLEARING 10,000.00 without a
    reason and JET-09f posts Dr CONTRACT_COST_CLEARING / Cr COST_TO_OBTAIN_ASSET 2,000.00 with
    reason_code CLAWBACK as a separate CONTRACT_COST_CAPITALIZATION entry (S14-R-12, S14-R-27;
    S11-R-12); the role totals are the netted 8,000.00 the engine posted before. Each variant has
    its own posting_target node whose amounts sum to the role target (§14.6), the two lines of
    one role carry distinct line keys (S14-R-15), and sealing the entries makes a recompute a
    no-op (RCP-05 round trip through PostedAmountInput.reason_code)."""
    costs = _costs({_period(1): 1000000}, {_period(1): 200000})
    run = _cost_run(_context(1), costs)
    assert _rows(run.posting.deltas) == [
        (COST_SUBJECT, CAPITALIZATION, COST_CLEARING, _period(1), None, "EVENT", None, -1000000),
        (
            COST_SUBJECT,
            CAPITALIZATION,
            COST_CLEARING,
            _period(1),
            None,
            "EVENT",
            "CLAWBACK",
            200000,
        ),
        (COST_SUBJECT, CAPITALIZATION, OBTAIN_ASSET, _period(1), None, "EVENT", None, 1000000),
        (
            COST_SUBJECT,
            CAPITALIZATION,
            OBTAIN_ASSET,
            _period(1),
            None,
            "EVENT",
            "CLAWBACK",
            -200000,
        ),
    ]
    intents = run.posting.posting_intents
    assert sorted(intent.reason_code or "" for intent in intents) == ["", "CLAWBACK"]
    clawback = next(intent for intent in intents if intent.reason_code == "CLAWBACK")
    assert {(line.side, line.account_role, line.amount_txn) for line in clawback.lines} == {
        ("D", COST_CLEARING, 200000),
        ("C", OBTAIN_ASSET, 200000),
    }
    assert len({line.line_key for intent in intents for line in intent.lines}) == 4
    net = {
        role: sum(d.amount_txn for d in run.posting.deltas if d.key.account_role == role)
        for role in (OBTAIN_ASSET, COST_CLEARING)
    }
    assert net == {OBTAIN_ASSET: 800000, COST_CLEARING: -800000}
    asset = next(t for t in run.posting.role_targets if t.key.account_role == OBTAIN_ASSET)
    assert [(v.reason, v.amount_txn) for v in asset.variants] == [
        (None, 1000000),
        ("CLAWBACK", -200000),
    ]
    subject = f"{COST_SUBJECT}/{CAPITALIZATION}/{OBTAIN_ASSET}"
    assert _node(run.trace, f"posting_target:{subject}:{_period(1)}").value == "8000.00"
    assert _node(run.trace, f"posting_target:{subject}/UNTAGGED:{_period(1)}").value == "10000.00"
    assert _node(run.trace, f"posting_target:{subject}/CLAWBACK:{_period(1)}").value == "-2000.00"
    assert (
        _node(run.trace, f"posting_delta:{subject}/CLAWBACK/EVENT:{_period(1)}").value == "-2000.00"
    )
    for line in clawback.lines:
        assert line.trace_node_id.endswith(f"/CLAWBACK:{_period(1)}")
    posted = _posted(run)
    assert {item.reason_code for item in posted} == {None, "CLAWBACK"}
    again = _cost_run(_context(1), costs, posted=posted)
    assert again.posting.deltas == ()


def test_s14_r27_posted_clawback_then_capitalisation_change_stays_attributed() -> None:
    """With the January entries sealed, a later change of the capitalised amount (10,500.00) in
    the still-open month posts 500.00 on the untagged variant only; a later clawback (3,000.00
    cumulative) posts the further 1,000.00 with reason CLAWBACK. Each variant is reconciled
    against the posted lines carrying its reason (S14-R-27)."""
    first = _cost_run(_context(1), _costs({_period(1): 1000000}, {_period(1): 200000}))
    posted = _posted(first)
    more = _cost_run(
        _context(1), _costs({_period(1): 1050000}, {_period(1): 200000}), posted=posted
    )
    assert _rows(more.posting.deltas) == [
        (COST_SUBJECT, CAPITALIZATION, COST_CLEARING, _period(1), None, "EVENT", None, -50000),
        (COST_SUBJECT, CAPITALIZATION, OBTAIN_ASSET, _period(1), None, "EVENT", None, 50000),
    ]
    clawed = _cost_run(
        _context(1), _costs({_period(1): 1000000}, {_period(1): 300000}), posted=posted
    )
    assert _rows(clawed.posting.deltas) == [
        (
            COST_SUBJECT,
            CAPITALIZATION,
            COST_CLEARING,
            _period(1),
            None,
            "EVENT",
            "CLAWBACK",
            100000,
        ),
        (
            COST_SUBJECT,
            CAPITALIZATION,
            OBTAIN_ASSET,
            _period(1),
            None,
            "EVENT",
            "CLAWBACK",
            -100000,
        ),
    ]


def test_s14_r27_void_pools_the_role_key_and_later_deltas_stay_untagged() -> None:
    """VOID wins as today (S14-R-08): a new void of the contract reverses the sealed clawback as
    one pooled delta per role with reason VOID and no variant tag. Because a VOID line cannot be
    attributed to a variant, later deltas of that origin post untagged (the whole role key, no
    split) and the recompute after the void is a no-op (S14-R-27)."""
    costs = _costs({_period(1): 1000000}, {_period(1): 200000})
    first = _cost_run(_context(1), costs)
    posted = _posted(first)
    unwound = _costs({_period(1): 1000000}, {_period(1): 0})
    void = _cost_run(_context(1), unwound, posted=posted, voided=[CONTRACT_KEY])
    assert _rows(void.posting.deltas) == [
        (COST_SUBJECT, CAPITALIZATION, COST_CLEARING, _period(1), None, "EVENT", "VOID", -200000),
        (COST_SUBJECT, CAPITALIZATION, OBTAIN_ASSET, _period(1), None, "EVENT", "VOID", 200000),
    ]
    assert void.posting.posting_kind == "VOID_REVERSAL"
    sealed = _posted(first, void)
    assert _cost_run(_context(1), unwound, posted=sealed).posting.deltas == ()
    later = _cost_run(_context(1), _costs({_period(1): 1050000}, {_period(1): 0}), posted=sealed)
    assert _rows(later.posting.deltas) == [
        (COST_SUBJECT, CAPITALIZATION, COST_CLEARING, _period(1), None, "EVENT", None, -50000),
        (COST_SUBJECT, CAPITALIZATION, OBTAIN_ASSET, _period(1), None, "EVENT", None, 50000),
    ]
    # A key with a VOID line but no tagged variant in the targets or postings is unchanged.
    plain = _cost_run(_context(1), _costs({_period(1): 1050000}, {}), posted=sealed)
    assert {d.reason_code for d in plain.posting.deltas} == {None}


def test_s14_r27_late_placed_clawback_keeps_late_event() -> None:
    """S08-R-08 with S14-R-27: January closed before anything posted — the capitalisation and the
    clawback carry into February as one pooled delta per role with reason LATE_EVENT and origin
    January (8,000.00 net), never re-tagged CLAWBACK; the recompute is a no-op and the trace
    carries no variant delta node for the closed period."""
    costs = _costs({_period(1): 1000000}, {_period(1): 200000})
    ctx = _context(2, {_period(1): "closed"})
    run = _cost_run(ctx, costs)
    assert _rows(run.posting.deltas) == [
        (
            COST_SUBJECT,
            CAPITALIZATION,
            COST_CLEARING,
            _period(2),
            _period(1),
            "EVENT",
            "LATE_EVENT",
            -800000,
        ),
        (
            COST_SUBJECT,
            CAPITALIZATION,
            OBTAIN_ASSET,
            _period(2),
            _period(1),
            "EVENT",
            "LATE_EVENT",
            800000,
        ),
    ]
    assert not any(
        node.id.startswith("posting_delta:") and "/CLAWBACK/" in node.id for node in run.trace.nodes
    )
    assert _cost_run(ctx, costs, posted=_posted(run)).posting.deltas == ()


def test_s14_r27_posted_totals_tag_template_reasons_only() -> None:
    """``PostedTotals.of`` keeps the pooled amounts (RCP-05) and, per template reason, the tagged
    share; a LATE_EVENT, VOID or manual reason marks the origin unattributable (S14-R-27)."""
    ctx = _context(2)
    key = RoleKey("ASC606", ENTITY, COST_SUBJECT, CAPITALIZATION, OBTAIN_ASSET, None, None)

    def item(period: str, origin: str | None, amount: int, reason: str | None) -> PostedAmountInput:
        return dataclasses.replace(
            _posted_amount(COST_SUBJECT, OBTAIN_ASSET, period, amount, kind="ENGINE_COMPUTE"),
            entry_kind=CAPITALIZATION,
            origin_period_key=origin,
            reason_code=reason,
        )

    totals = PostedTotals.of(
        ctx,
        PostedIndex(
            (
                item(_period(1), None, 1000000, None),
                item(_period(1), None, -200000, "CLAWBACK"),
                item(_period(2), _period(1), 300000, "LATE_EVENT"),
                item(_period(2), None, 500000, "CLAWBACK"),
                item(_period(2), None, -100000, "MANUAL_TRUE_UP"),
            )
        ),
    )
    assert totals.by_origin(key, _period(1), ("EVENT",)) == (1100000, 1100000)
    assert totals.by_reason(key, _period(1), ("EVENT",), "CLAWBACK") == (-200000, -200000)
    assert totals.reasons_at(key, _period(1), ("EVENT",)) == {"CLAWBACK"}
    assert not totals.attributable(key, _period(1), ("EVENT",))  # the LATE_EVENT carry
    assert totals.by_origin(key, _period(2), ("EVENT",)) == (400000, 400000)
    assert totals.by_reason(key, _period(2), ("EVENT",), "CLAWBACK") == (500000, 500000)
    assert not totals.attributable(key, _period(2), ("EVENT",))  # the manual reason
    clean = PostedTotals.of(ctx, PostedIndex((item(_period(2), None, 500000, "CLAWBACK"),)))
    assert clean.attributable(key, _period(2), ("EVENT",))
    assert clean.attributable(key, _period(1), ("EVENT",))
