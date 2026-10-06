"""Stage 14 manual adjustment lines (ENGINE_SPEC_B §14.1 input row "Approved manual adjustments",
Table 14-A "Manual adjustment", S14-R-09a; §9.2.11 S09-R-41; 04 T-SL-05, E-93, E-29; 05 RCP-05;
supervisor ruling R-51 (a)).

The approved lines of a ``MANUAL_JOURNAL`` or ``ACCOUNT_RECLASS`` adjustment arrive in the payload
of ``MANUAL_ADJUSTMENT_APPLIED`` and are role targets of entry kind ``MANUAL_ADJUSTMENT``: a ledger
that holds them gets nothing from a computation, a ledger that lacks them gets them, and a ledger
that holds the lines of a voided adjustment gets their reversal. Stages 10 and 11 are faked as in
``test_s14_deltas`` (D-81 integration after merge); every trace re-evaluates node for node
(DG-ENG-04).
"""

from __future__ import annotations

import dataclasses
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date

import pytest
from erev_engine import ENGINE_VERSION
from erev_engine.bundle import PostedAmountInput
from erev_engine.errors import EngineError
from erev_engine.stages import s12_fx_entities, s14_posting
from erev_engine.stages.s12_fx_entities import FxFlows
from erev_engine.stages.s14_posting import PartInputs, PostingState, RoleKey
from erev_engine.stages.s14_posting import manual as manual_lines
from erev_engine.stages.state import AllocatedState, BookContext, EventView, PostedIndex, RateIndex
from erev_engine.trace import Trace, TraceBuilder, reevaluate
from support import bundles
from support.recognition import (
    CONTRACT_KEY,
    allocated_state,
    book_context,
    event_view,
    obligation,
    segment,
    usd,
)

ENTITY = bundles.ENTITY_CODE
KIND = "MANUAL_ADJUSTMENT"  # E-29 entry kind and E-31 posting kind
CL, REVENUE, CA = "CONTRACT_LIABILITY", "REVENUE", "CONTRACT_ASSET"
P1 = f"{CONTRACT_KEY}/P1"
AT_ENTITY = f"{CONTRACT_KEY}@{ENTITY}"
JOURNAL = (("CONTRACT_LIABILITY", "2400.00"), ("REVENUE", "-2400.00"))


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


def _period(month: int) -> str:
    return f"FY2026-P{month:02d}"


def _context(months: int = 4, states: Mapping[str, str] | None = None) -> BookContext:
    return book_context(bundles.entity(months=months, states=states))


def _state(*events: EventView) -> AllocatedState:
    minor = usd("3000.00")
    start, end = date(2026, 1, 1), date(2026, 12, 31)
    ob = obligation(
        "P1", [segment(minor // 100, minor, start=start, end=end)], start=start, end=end
    )
    return allocated_state([ob], events=events)


def _adjustment(
    version: int,
    when: date,
    period_key: str,
    pairs: Sequence[tuple[str, str]] = JOURNAL,
    *,
    kind: str = "MANUAL_JOURNAL",
    obligation_key: str | None = "P1",
    changes: Mapping[str, object] | None = None,
) -> EventView:
    """``MANUAL_ADJUSTMENT_APPLIED`` as the bundle builder resolves a T-SL-05 row (L1-3-Q-14);
    ``changes`` replaces payload members."""
    payload: dict[str, object] = {
        "manual_adjustment_id": f"ADJ-{version:06d}",
        "kind": kind,
        "book_code": "ASC606",
        "entity_code": ENTITY,
        "period_key": period_key,
        "lines": [{"account_role": role, "amount_txn": amount} for role, amount in pairs],
    }
    keys = []
    if obligation_key is not None:
        payload["obligation_key"] = obligation_key
        keys.append(obligation_key)
    payload.update(changes or {})
    return event_view(
        CONTRACT_KEY, version, manual_lines.EVENT_TYPE, when, payload, obligation_keys=keys
    )


def _compute(
    ctx: BookContext,
    allocated: AllocatedState,
    *,
    posted: Iterable[PostedAmountInput] = (),
    pass_name: str | None = None,
) -> _Run:
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    fx = s12_fx_entities.run(
        ctx, _Costs(allocated, FxFlows(()), PartInputs()), tb, rates=RateIndex(())
    )
    posting = s14_posting.run(ctx, fx, tb, posted=PostedIndex(tuple(posted)), pass_name=pass_name)
    trace = tb.build(root_measures={})
    assert reevaluate(trace) == {node.id: node.value for node in trace.nodes}
    return _Run(posting, trace)


def _held(
    subject: str,
    role: str,
    period_key: str,
    amount: int,
    *,
    origin: str | None = None,
    reason: str | None = None,
) -> PostedAmountInput:
    """A sealed manual line as RCP-05 reads it back: posting kind ``MANUAL_ADJUSTMENT`` is class
    ``EVENT``; the account is no member of the grain."""
    return PostedAmountInput(
        "ASC606",
        ENTITY,
        subject,
        KIND,
        role,
        None,
        None,
        period_key,
        origin,
        s14_posting.posting_class(KIND),
        "USD",
        "USD",
        amount,
        amount,
        reason,
    )


def _rows(run: _Run) -> list[tuple[object, ...]]:
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
        for delta in run.posting.deltas
    ]


def _targets(run: _Run, role: str, subject: str = P1) -> list[tuple[str, int, int, int]]:
    key = RoleKey("ASC606", ENTITY, subject, KIND, role, None, None)
    return [
        (t.period_key, t.amount_txn, t.amount_functional, t.time_txn)
        for t in run.posting.role_targets
        if t.key == key
    ]


def test_s14_r09a_approved_lines_are_role_targets_and_post_on_a_ledger_without_them() -> None:
    """Table 14-A "Manual adjustment": the approved lines, entry kind MANUAL_ADJUSTMENT, roles as
    approved, class EVENT. On a ledger that does not hold them (a replay from an empty ledger)
    stage 14 posts them in the adjustment period, account by T-REF-15."""
    ctx = _context()
    run = _compute(ctx, _state(_adjustment(2, date(2026, 3, 15), _period(3))))
    # cumulative from the adjustment period through the horizon; no TIME share, no pass
    assert _targets(run, CL) == [(_period(3), 240000, 240000, 0), (_period(4), 240000, 240000, 0)]
    assert _targets(run, REVENUE) == [
        (_period(3), -240000, -240000, 0),
        (_period(4), -240000, -240000, 0),
    ]
    manual = [t for t in run.posting.role_targets if t.key.entry_kind == KIND]
    assert {t.passes for t in manual} == {()} and {t.rates for t in manual} == {()}
    node = next(n for n in run.trace.nodes if n.id == manual[0].node_id)
    assert (node.formula_id, node.value, node.params["signs"], node.params["time"]) == (
        "post.role_target.v1",
        "2400.00",
        "1",
        "0",
    )
    [cited] = node.inputs
    assert not isinstance(cited, str)
    assert (cited.ref_type, cited.ref_id, dict(cited.detail)) == (
        "contract_event",
        f"{CONTRACT_KEY}/EV-000002",
        {"member": "lines[0].amount_txn", "value": "2400.00"},
    )
    assert _rows(run) == [
        (P1, KIND, CL, _period(3), None, "EVENT", None, 240000),
        (P1, KIND, REVENUE, _period(3), None, "EVENT", None, -240000),
    ]
    [intent] = run.posting.posting_intents
    assert (intent.entry_kind, intent.subject_key, intent.posting_period_key) == (
        KIND,
        P1,
        _period(3),
    )
    assert (intent.posting_class, intent.origin_period_key, intent.reason_code) == (
        "EVENT",
        None,
        None,
    )
    assert [
        (line.side, line.account_role, line.account_code, line.amount_txn) for line in intent.lines
    ] == [
        ("D", CL, "2400", 240000),
        ("C", REVENUE, "4000", 240000),
    ]
    assert run.posting.findings == () and run.posting.posting_kind == "ENGINE_COMPUTE"


def test_s14_r09a_a_ledger_that_holds_the_lines_gets_nothing() -> None:
    """Ruling R-51 (a): the platform posts the approved lines when the adjustment is approved
    (posting kind MANUAL_ADJUSTMENT, the accounts as approved); the computation of the same
    transaction and every later one find posted = target and emit nothing — neither a second
    posting nor a reversal (S14-INV-02)."""
    ctx = _context()
    state = _state(_adjustment(2, date(2026, 3, 15), _period(3)))
    posted = [_held(P1, CL, _period(3), 240000), _held(P1, REVENUE, _period(3), -240000)]
    run = _compute(ctx, state, posted=posted)
    assert _targets(run, CL)[0] == (_period(3), 240000, 240000, 0)
    assert run.posting.deltas == () and run.posting.posting_intents == ()
    # a close run over the same ledger posts no manual amount either: the lines have no TIME share
    release = dataclasses.replace(ctx, trigger="CLOSE_RELEASE")
    closing = _compute(release, state, posted=posted, pass_name="CLOSE_RELEASE")
    assert closing.posting.deltas == ()
    # and a close run never posts an approved line the ledger lacks (EVENT amounts post at compute)
    assert _compute(release, state, pass_name="CLOSE_RELEASE").posting.deltas == ()


def test_s14_r09a_posted_lines_without_their_adjustment_are_reversed() -> None:
    """The delta rule as it stood before the part existed, and as it stays for a voided
    adjustment: posted manual lines whose event the bundle no longer includes have no target, so
    the next computation reverses them (the reason the part is needed at all, R-51 (a))."""
    ctx = _context()
    posted = [_held(P1, CL, _period(3), 240000), _held(P1, REVENUE, _period(3), -240000)]
    run = _compute(ctx, _state(), posted=posted)
    assert [t for t in run.posting.role_targets if t.key.entry_kind == KIND] == []
    assert _rows(run) == [
        (P1, KIND, CL, _period(3), None, "EVENT", None, -240000),
        (P1, KIND, REVENUE, _period(3), None, "EVENT", None, 240000),
    ]


def test_s14_r09a_lines_of_one_role_net_to_no_delta() -> None:
    """An ACCOUNT_RECLASS between two accounts of ONE role (S14-R-09: balances moved after a
    mapping change) has a role target of 0: stage 14 never derives it, and the two posted lines —
    the platform's, with their accounts — sum to 0 on the role key and are left alone."""
    ctx = _context()
    reclass = _adjustment(
        2,
        date(2026, 3, 15),
        _period(3),
        (("REVENUE", "500.00"), ("REVENUE", "-500.00")),
        kind="ACCOUNT_RECLASS",
    )
    run = _compute(ctx, _state(reclass))
    assert _targets(run, REVENUE) == [(_period(3), 0, 0, 0), (_period(4), 0, 0, 0)]
    node = next(n for n in run.trace.nodes if n.id == run.posting.role_targets[0].node_id)
    assert (node.value, node.params["signs"], len(node.inputs)) == ("0.00", "1|1", 2)
    assert run.posting.deltas == () and run.posting.posting_intents == ()
    posted = [_held(P1, REVENUE, _period(3), 0)]
    assert _compute(ctx, _state(reclass), posted=posted).posting.deltas == ()
    assert _compute(ctx, _state(), posted=posted).posting.deltas == ()


def test_s14_r09a_two_adjustments_accumulate_per_role_key() -> None:
    """The cumulative target of a role key through a period end is the signed sum of the lines of
    the adjustments whose period is on or before it; each period posts its own movement."""
    ctx = _context()
    first = _adjustment(2, date(2026, 2, 10), _period(2))
    second = _adjustment(
        3, date(2026, 3, 20), _period(3), ((CA, "100.00"), (CL, "150.00"), (REVENUE, "-250.00"))
    )
    run = _compute(ctx, _state(first, second))
    assert _targets(run, CL) == [
        (_period(2), 240000, 240000, 0),
        (_period(3), 255000, 255000, 0),
        (_period(4), 255000, 255000, 0),
    ]
    assert _targets(run, CA) == [(_period(3), 10000, 10000, 0), (_period(4), 10000, 10000, 0)]
    assert _rows(run) == [
        (P1, KIND, CA, _period(3), None, "EVENT", None, 10000),
        (P1, KIND, CL, _period(2), None, "EVENT", None, 240000),
        (P1, KIND, CL, _period(3), None, "EVENT", None, 15000),
        (P1, KIND, REVENUE, _period(2), None, "EVENT", None, -240000),
        (P1, KIND, REVENUE, _period(3), None, "EVENT", None, -25000),
    ]
    # the first adjustment is in the ledger: only the second posts
    posted = [_held(P1, CL, _period(2), 240000), _held(P1, REVENUE, _period(2), -240000)]
    assert [row[3] for row in _rows(_compute(ctx, _state(first, second), posted=posted))] == [
        _period(3)
    ] * 3


def test_s14_r09a_a_closed_adjustment_period_posts_late_with_its_origin() -> None:
    """An adjustment deferred past the lock and approved afterwards (R-51 (c)): its period is
    closed, so the lines post in the first open period with the adjustment period as their origin
    (S08-R-08; ``LATE_EVENT``). The platform's lines carry the same origin, and the computation
    then emits nothing."""
    ctx = _context(states={_period(1): "closed", _period(2): "closed"})
    state = _state(_adjustment(2, date(2026, 2, 27), _period(2)))
    run = _compute(ctx, state)
    assert _rows(run) == [
        (P1, KIND, CL, _period(3), _period(2), "EVENT", "LATE_EVENT", 240000),
        (P1, KIND, REVENUE, _period(3), _period(2), "EVENT", "LATE_EVENT", -240000),
    ]
    posted = [
        _held(P1, CL, _period(3), 240000, origin=_period(2), reason="LATE_EVENT"),
        _held(P1, REVENUE, _period(3), -240000, origin=_period(2), reason="LATE_EVENT"),
    ]
    assert _compute(ctx, state, posted=posted).posting.deltas == ()


def test_s14_r09a_subject_book_and_kind() -> None:
    """Without an obligation the lines belong to ``<contract>@<entity>`` (Table 14-A "contract or
    obligation"; the RCP-05 read-back of a line without an obligation). An adjustment applies in
    the book it names, and the three schedule kinds carry no lines (S09-R-38 to R-40)."""
    ctx = _context()
    contract_level = _adjustment(2, date(2026, 3, 15), _period(3), obligation_key=None)
    run = _compute(ctx, _state(contract_level))
    assert _targets(run, CL, AT_ENTITY) == [
        (_period(3), 240000, 240000, 0),
        (_period(4), 240000, 240000, 0),
    ]
    assert {delta.key.subject_key for delta in run.posting.deltas} == {AT_ENTITY}
    other_book = _adjustment(2, date(2026, 3, 15), _period(3), changes={"book_code": "IFRS15"})
    assert _compute(ctx, _state(other_book)).posting.role_targets == ()
    every_book = _adjustment(2, date(2026, 3, 15), _period(3), changes={"book_code": None})
    assert len(_compute(ctx, _state(every_book)).posting.deltas) == 2
    release = event_view(
        CONTRACT_KEY,
        2,
        manual_lines.EVENT_TYPE,
        date(2026, 3, 15),
        {
            "manual_adjustment_id": "ADJ-000002",
            "kind": "MANUAL_RELEASE",
            "book_code": "ASC606",
            "obligation_key": "P1",
            "period_key": _period(3),
            "amount": "100.00",
        },
        obligation_keys=["P1"],
    )
    assert _compute(ctx, _state(release)).posting.role_targets == ()


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"lines": [{"account_role": "REVENUE", "amount_txn": "10.00"}]}, "fewer than two lines"),
        (
            {
                "lines": [
                    {"account_role": CL, "amount_txn": "2400.00"},
                    {"account_role": REVENUE, "amount_txn": "-2399.99"},
                ]
            },
            "do not balance",
        ),
        (
            {
                "lines": [
                    {"account_role": CL, "amount_txn": "10.005"},
                    {"account_role": REVENUE, "amount_txn": "-10.005"},
                ]
            },
            "below the minor unit",
        ),
        (
            {
                "lines": [
                    {"account_role": "RETAINED_EARNINGS", "amount_txn": "10.00"},
                    {"account_role": REVENUE, "amount_txn": "-10.00"},
                ]
            },
            "a role it cannot carry",
        ),
        (
            {
                "lines": [
                    {"account_role": "BILLING_CLEARING", "amount_txn": "10.00"},
                    {"account_role": REVENUE, "amount_txn": "-10.00"},
                ]
            },
            "a role it cannot carry",
        ),
        (
            {
                "lines": [
                    {"account_role": CL, "amount_txn": "0.00"},
                    {"account_role": REVENUE, "amount_txn": "0.00"},
                ]
            },
            "carries no amount",
        ),
        (
            {"lines": [{"account_role": CL, "amount_txn": 10.0}, {"account_role": REVENUE}]},
            "amount is malformed",
        ),
        ({"period_key": "FY2031-P01"}, "no period of the calendar"),
        ({"entity_code": "XX99"}, "an entity the bundle lacks"),
        ({"entity_code": None}, "names no entity_code"),
    ],
)
def test_s14_r09a_malformed_adjustments_fail_closed(
    change: Mapping[str, object], message: str
) -> None:
    """A payload the platform's validation should never produce stops the computation by name
    (``ENGINE_INVARIANT_VIOLATED``, rule S14-R-09a): nothing is posted on a guess."""
    event = _adjustment(2, date(2026, 3, 15), _period(3), changes=change)
    with pytest.raises(EngineError) as refused:
        _compute(_context(), _state(event))
    assert refused.value.code == "ENGINE_INVARIANT_VIOLATED"
    assert message in str(refused.value) and refused.value.detail["rule"] == "S14-R-09a"
    assert refused.value.detail["event_key"] == f"{CONTRACT_KEY}/EV-000002"


def test_s14_r09a_a_foreign_currency_adjustment_is_refused_by_name() -> None:
    """1.0 limit (ruling R-51): a manual journal needs a contract in the entity's functional
    currency. The T-SL-05 line states one amount and no rate reference, so a foreign-currency line
    could not name its rate (S14-INV-08) — the adjustment is refused by name, whatever a payload
    states beside the amount, and no line without a rate reference is ever derived from it."""
    calendar = bundles.entity(months=4, functional_currency="EUR")
    ctx = dataclasses.replace(
        book_context(calendar, currency="USD"), currencies=bundles.currencies("USD", "EUR")
    )
    stated = {
        "lines": [
            {"account_role": CL, "amount_txn": "2400.00", "amount_functional": "2160.00"},
            {"account_role": REVENUE, "amount_txn": "-2400.00", "amount_functional": "-2160.00"},
        ]
    }
    for changes in ({}, stated):
        event = _adjustment(2, date(2026, 3, 15), _period(3), changes=changes)
        with pytest.raises(EngineError) as refused:
            manual_lines.role_targets(
                ctx, _state(event), TraceBuilder(engine_version=ENGINE_VERSION)
            )
        assert refused.value.code == "ENGINE_INVARIANT_VIOLATED"
        assert "needs a contract in the entity's functional currency" in str(refused.value)
        assert refused.value.detail == {
            "rule": "S14-R-09a",
            "event_key": f"{CONTRACT_KEY}/EV-000002",
            "functional_currency": "EUR",
            "txn_currency": "USD",
        }


def test_s14_r09a_no_table_14a_part_carries_the_manual_entry_kind() -> None:
    """The entry kind belongs to the manual part alone, so its role keys never meet a Table 14-A
    part's (``manual.merged`` refuses the combination) and the merged targets stay in role-key
    order."""
    assert all(part.entry_kind != KIND for part in s14_posting.JET_PARTS.values())
    ctx = _context()
    run = _compute(ctx, _state(_adjustment(2, date(2026, 3, 15), _period(3))))
    keys = [target.key.sort_key() for target in run.posting.role_targets]
    assert keys == sorted(keys)
    with pytest.raises(ValueError, match="S14-R-09a"):
        manual_lines.merged(run.posting.role_targets, ())
