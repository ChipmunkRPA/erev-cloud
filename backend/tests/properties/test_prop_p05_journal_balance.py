"""PROP:P5 journal balance, engine part (dev-guide §9.7; ENGINE_SPEC_B §14.4 S14-INV-01; D-16).

Over generated groups of principal, agent and intercompany obligations with revenue relief paths
(negative movements included), concessions settled by credit, netting reclass attributions and
closed-period prefixes, two computations run in each of the compute and netting reclass passes, the
second over the intents of the first. Every intent entry balances per (entity, book, posting period,
entry, transaction currency) in transaction amounts and per (entity, book, posting period, entry) in
functional amounts; no entry posts into a closed period (S14-INV-03); line amounts are non-negative.
The stage 09 to 11 producers are generated directly (D-81 integration after merge; L2-5-Q-24) and
stage 12 runs for real. Every trace re-evaluates node for node.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from fractions import Fraction

import pytest
from erev_engine import ENGINE_VERSION
from erev_engine.bundle import AccountMappingInput, MappingRuleInput, PostedAmountInput
from erev_engine.dates import month_end
from erev_engine.enums import AccountRole, BookCode, PrincipalAgent
from erev_engine.money import format_money
from erev_engine.stages import s12_fx_entities, s14_posting
from erev_engine.stages.s12_fx_entities import ControlFlow, FxFlows
from erev_engine.stages.s14_posting import PartInputs, PostingState
from erev_engine.stages.state import (
    AllocatedState,
    BookContext,
    PolicyResolver,
    PostedIndex,
    RateIndex,
    Target,
)
from erev_engine.trace import SourceRef, TraceBuilder, reevaluate
from hypothesis import example, given
from hypothesis import strategies as st
from support import bundles, oracle, platform_props, strategies
from support.prop_worlds import INCEPTION, LineSpec, MeasureSpec, bundle
from support.prop_worlds import WorldSpec as prop_worlds_spec
from support.recognition import allocated_state, book_context, obligation, segment

pytestmark = pytest.mark.property

US, UK = bundles.ENTITY_CODE, "UK01"
PURPOSES = ("AP_SUPPLIER", "BILLING", "EQUITY", "INVENTORY", "INVESTMENTS", "UNAPPLIED_CASH")
RECLASS_ROLES = ("UNBILLED_RECEIVABLE", "CONTRACT_ASSET")


@dataclass(frozen=True, slots=True)
class _Costs:
    allocated: AllocatedState
    fx_flows: FxFlows
    part_inputs: PartInputs


@dataclass(frozen=True, slots=True)
class Spec:
    key: str
    agent_rate: Fraction | None  # None for a principal
    movements: tuple[int, ...]  # relief movement per period (minor units)
    concessions: tuple[int, ...]  # JET-05c created per period (non-negative)
    reclass_role: str
    reclass: tuple[int, ...]  # attribution at each period end (non-negative)


@dataclass(frozen=True, slots=True)
class Case:
    months: int
    first_horizon: int  # periods of the first computation
    closed: int  # closed periods before the second computation
    specs: tuple[Spec, ...]
    performed: tuple[int, ...]  # releases of the obligation performed by UK01 (may be empty)


@st.composite
def cases(draw: st.DrawFn) -> Case:
    months = draw(st.integers(min_value=1, max_value=6))
    first_horizon = draw(st.integers(min_value=1, max_value=months))
    closed = draw(st.integers(min_value=0, max_value=months - 1))
    amounts = st.lists(
        st.integers(min_value=-50000, max_value=90000), min_size=months, max_size=months
    )
    positive = st.lists(st.integers(min_value=0, max_value=40000), min_size=months, max_size=months)
    specs = []
    for index in range(draw(st.integers(min_value=1, max_value=3))):
        agent = draw(st.booleans())
        rate = Fraction(draw(st.integers(min_value=0, max_value=20)), 20) if agent else None
        specs.append(
            Spec(
                key=f"P{index + 1}",
                agent_rate=rate,
                movements=tuple(draw(amounts)),
                concessions=tuple(draw(positive)) if draw(st.booleans()) else (0,) * months,
                reclass_role=draw(st.sampled_from(RECLASS_ROLES)),
                reclass=tuple(draw(positive)),
            )
        )
    performed = tuple(draw(positive)) if draw(st.booleans()) else ()
    return Case(months, first_horizon, closed, tuple(specs), performed)


def _period(month: int) -> str:
    return f"FY2026-P{month:02d}"


def _mapping() -> AccountMappingInput:
    rules = []
    for index, role in enumerate(sorted(AccountRole)):
        if role in ("RETAINED_EARNINGS", "FINANCING_OBLIGATION"):
            continue
        for offset, purpose in enumerate(PURPOSES if role == "BILLING_CLEARING" else (None,)):
            code = str(1000 + 10 * index + offset)
            rules.append(MappingRuleInput(role, purpose, None, None, None, None, code, {}, 0, 0))
    return AccountMappingInput("MAP-P05@v1", bundles.ZERO_SHA256, tuple(rules))


def _context(months: int, horizon: int, closed: int, trigger: str) -> BookContext:
    states = {_period(month): "closed" for month in range(1, closed + 1)}
    calendars = [
        bundles.entity(US, months=months, states=states),
        bundles.entity(UK, months=months),
    ]
    ctx = book_context(calendars[0])
    resolved = {(p.code, p.scope, p.subject_key): p for p in ctx.policies.all()}
    for policy in bundles.policy_set(entity=calendars[1]):
        resolved.setdefault((policy.code, policy.scope, policy.subject_key), policy)
    return dataclasses.replace(
        ctx,
        entities={calendar.code: calendar for calendar in calendars},
        horizon={calendar.code: _period(horizon) for calendar in calendars},
        policies=PolicyResolver(tuple(resolved[key] for key in sorted(resolved))),
        mapping=_mapping(),
        trigger=trigger,
    )


def _target(measure: str, subject: str, month: int, value: int, cause: str | None = None) -> Target:
    period_key = _period(month)
    node = f"{measure}:{subject}" + ("" if cause is None else f"#{cause}") + f":{period_key}"
    return Target(BookCode.ASC606, US, subject, measure, period_key, cause, value, None, node)


def _group(case: Case) -> tuple[AllocatedState, PartInputs, tuple[ControlFlow, ...]]:
    start, end = date(2026, 1, 1), date(2026, 12, 31)
    obligations = []
    relief: list[Target] = []
    concessions: list[Target] = []
    refunds: list[Target] = []
    reclass: list[Target] = []
    for spec in case.specs:
        ob = obligation(spec.key, [segment(Fraction(1000), 100000, start=start, end=end)])
        if spec.agent_rate is not None:
            rate = Decimal(spec.agent_rate.numerator * 5) / Decimal(100)  # twentieths as a decimal
            basis = {"gross_to_net_basis": "COMMISSION_RATE", "rate": str(rate)}
            ob = dataclasses.replace(ob, principal_agent=PrincipalAgent.AGENT, gross_to_net=basis)
        obligations.append(ob)
        cumulative = created = 0
        for month in range(1, case.months + 1):
            cumulative += spec.movements[month - 1]
            created += spec.concessions[month - 1]
            # D-88 L7-5-Q-4: relief = revenue_cum + the concessions created; JET-04b nets the
            # concession whose cause names its component.
            relief.append(
                _target("revenue_relief_cum", ob.subject_key, month, cumulative + created)
            )
            if created:
                component = f"CG-1@{US}/CONCESSION/{ob.subject_key}"
                concessions.append(
                    _target("concession_created_cum", ob.subject_key, month, created, component)
                )
                refunds.append(
                    _target("refund_liability", component, month, created // 2, "CONCESSION")
                )
            if spec.reclass[month - 1]:
                reclass.append(
                    _target(
                        "netting_reclass_amount",
                        ob.subject_key,
                        month,
                        spec.reclass[month - 1],
                        spec.reclass_role,
                    )
                )
    flows: list[ControlFlow] = []
    if case.performed:
        performed = dataclasses.replace(
            obligation("X9", [segment(Fraction(1000), 100000, start=start, end=end)]),
            performing_entity=UK,
        )
        obligations.append(performed)
        cumulative = 0
        for month in range(1, case.months + 1):
            amount = case.performed[month - 1]
            cumulative += amount
            relief.append(_target("revenue_relief_cum", performed.subject_key, month, cumulative))
            if amount:
                on = month_end(date(2026, month, 1))
                key = f"{performed.subject_key}@{_period(month)}"
                flows.append(
                    ControlFlow("REVENUE", US, performed.subject_key, key, on, None, amount)
                )
    inputs = PartInputs(
        relief=tuple(relief),
        refund_liabilities=tuple(refunds),
        concessions=tuple(concessions),
        reclass=tuple(reclass),
    )
    return allocated_state(obligations), inputs, tuple(flows)


def _compute(
    ctx: BookContext,
    group: tuple[AllocatedState, PartInputs, tuple[ControlFlow, ...]],
    posted: Sequence[PostedAmountInput],
    pass_name: str | None,
) -> PostingState:
    allocated, inputs, flows = group
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    # Relief cites its revenue node and the concession nodes (D-88 L7-5-Q-4 (1)): the faked relief
    # node holds revenue_cum alone.
    created = {(item.subject_key, item.period_key): item.value for item in inputs.concessions}
    for target in (
        *inputs.relief,
        *inputs.refund_liabilities,
        *inputs.concessions,
        *inputs.reclass,
    ):
        measure, subject, period_key = target.node_id.rsplit(":", 2)
        value = target.value
        if target.measure == "revenue_relief_cum":
            value -= created.get((target.subject_key, target.period_key), 0)
        detail = {"value": format_money(value, 2)}
        tb.node(
            measure=measure,
            subject_key=subject,
            period_key=period_key,
            value=value,
            currency="USD",
            minor_unit=2,
            formula_id="rec.catch_up.sum.v1",
            inputs=[SourceRef("source_record", target.node_id, detail)],
            narrative_key="rec.catch_up.sum",
        )
    costs = _Costs(allocated, FxFlows(flows), inputs)
    fx = s12_fx_entities.run(ctx, costs, tb, rates=RateIndex(()))
    state = s14_posting.run(ctx, fx, tb, posted=PostedIndex(tuple(posted)), pass_name=pass_name)
    trace = tb.build(root_measures={})
    assert reevaluate(trace) == {node.id: node.value for node in trace.nodes}
    return state


def _posted(states: Iterable[PostingState]) -> list[PostedAmountInput]:
    return [
        PostedAmountInput(
            book_code=intent.book_code,
            entity_code=intent.entity,
            subject_key=intent.subject_key,
            entry_kind=intent.entry_kind,
            account_role=line.account_role,
            clearing_purpose=line.clearing_purpose,
            counterparty_entity_code=line.counterparty_entity,
            period_key=intent.posting_period_key,
            origin_period_key=intent.origin_period_key,
            posting_class=intent.posting_class,
            txn_currency=line.txn_currency,
            functional_currency=line.functional_currency,
            amount_txn=line.amount_txn if line.side == "D" else -line.amount_txn,
            amount_functional=(
                line.amount_functional if line.side == "D" else -line.amount_functional
            ),
        )
        for state in states
        for intent in state.posting_intents
        for line in intent.lines
    ]


def _check(ctx: BookContext, state: PostingState) -> None:
    assert state.findings == ()
    for intent in state.posting_intents:
        by_currency: dict[str, int] = {}
        functional = 0
        for line in intent.lines:
            assert line.amount_txn >= 0 and line.amount_functional >= 0
            assert line.amount_txn or line.amount_functional
            sign = 1 if line.side == "D" else -1
            by_currency[line.txn_currency] = (
                by_currency.get(line.txn_currency, 0) + sign * line.amount_txn
            )
            functional += sign * line.amount_functional
        assert all(total == 0 for total in by_currency.values()), intent
        assert functional == 0, intent
        calendar = ctx.entities[intent.entity]
        period = next(p for p in calendar.periods if p.period_key == intent.posting_period_key)
        assert dict(period.states)["ASC606"] in ("open", "closing", "reopened")


@given(cases())
def test_p05_engine_entries_balance(case: Case) -> None:
    group = _group(case)
    posted: list[PostedAmountInput] = []
    for horizon, closed in ((case.first_horizon, 0), (case.months, case.closed)):
        for trigger, pass_name in (("COMMAND", None), ("CLOSE_RELEASE", "NETTING_RECLASS")):
            ctx = _context(case.months, horizon, closed, trigger)
            state = _compute(ctx, group, posted, pass_name)
            _check(ctx, state)
            posted += _posted([state])
    # A repeated compute over the sealed intents posts nothing (S14-INV-02).
    for trigger, pass_name in (("COMMAND", None), ("CLOSE_RELEASE", "NETTING_RECLASS")):
        ctx = _context(case.months, case.months, case.closed, trigger)
        assert _compute(ctx, group, posted, pass_name).posting_intents == ()


# --- platform part (BUILD_SPEC PRP-4; DB-16) ----------------------------------------------------


def _line_end(line: LineSpec) -> date:
    start = oracle.add_months(INCEPTION, line.start_offset)
    return start if line.kind == "PIT" else oracle.term_end(start, line.term_months)


def _expects_posting(spec: prop_worlds_spec) -> bool:
    """Engine-independent (``support.oracle``): the world posts a journal line iff some obligation's
    cumulative posted revenue reaches one minor unit. A ratable line posts iff its GROUP-LEVEL
    largest-remainder allocation is at least 1 minor unit (its cumulative posted revenue equals
    the allocation at the term end, inside the calendar); a point-in-time line iff the half-up
    bounded share of its delivered units is at least 1 minor unit. Billings post no engine line
    (the ERP side) and a pure liability position needs no netting reclass. Batch #8 (thorough)
    found the world where a ratable line exists but this predicate is False: T = 2 minor units
    split 1.5 / 0.5 by weights 3 / 1, the tie to the larger weight gives 2 / 0 (ALG-01 §2.1.2;
    ``money.largest_remainder``)."""
    reference = oracle.Oracle(minor_unit=spec.minor_unit, inception=INCEPTION)
    for contract, lines in spec.contracts:
        reference.add_contract(
            contract,
            [
                oracle.Line(
                    contract,
                    line.key,
                    line.kind,
                    line.price,
                    line.ssp,
                    line.quantity,
                    oracle.add_months(INCEPTION, line.start_offset),
                    _line_end(line),
                )
                for line in lines
            ],
        )
    allocation, exact = reference.allocation(), reference.allocation_exact()
    for line in reference.lines:
        if line.kind != "PIT":
            if allocation[line.subject] >= 1:
                return True
            continue
        delivered = sum(
            m.amount
            for m in spec.measures
            if (m.contract, m.line, m.kind) == (line.contract, line.key, "DELIVERY")
        )
        share = oracle.cumulative_posted(
            exact[line.subject],
            allocation[line.subject],
            oracle.units_fraction(delivered, line.quantity),
            spec.minor_unit,
        )
        if share >= 1:
            return True
    return False


# DG-PROP-02: the batch-#8 world (thorough profile, main 0091cc21) — a ratable line allocated 0
# minor units beside a heavier point-in-time line without a delivery posts nothing.
BATCH_8_ZERO_ALLOCATION_EXAMPLE: prop_worlds_spec = prop_worlds_spec(
    currency="BHD",
    contracts=(
        (
            "K-1",
            (
                LineSpec("POB-01", "PIT", 1, 1, 3, 0, 0),
                LineSpec("POB-02", "DAILY", 1, 1, 1, 0, 1),
            ),
        ),
    ),
    measures=(),
)
# and its neighbour that does post: one delivered unit of the point-in-time line (share 1 of 2).
BATCH_8_DELIVERED_EXAMPLE: prop_worlds_spec = prop_worlds_spec(
    currency="BHD",
    contracts=BATCH_8_ZERO_ALLOCATION_EXAMPLE.contracts,
    measures=(MeasureSpec("K-1", "POB-01", "DELIVERY", 3, 1),),
)


@platform_props.platform_settings()
@example(spec=BATCH_8_ZERO_ALLOCATION_EXAMPLE)
@example(spec=BATCH_8_DELIVERED_EXAMPLE)
@given(spec=strategies.world_specs())
def test_p05_platform_batches_balance(spec: prop_worlds_spec) -> None:
    """PROP:P5 platform part: a generated world driven as the platform drives it — the engine
    computed over the world, then the close-run passes (``FX_REMEASUREMENT``, ``CLOSE_RELEASE``,
    ``NETTING_RECLASS``) over the intents posted so far — gives journal batches per (entity,
    period, mode) that balance per currency in transaction AND functional amounts, at the landed
    platform runner's grain (``summarise_intents`` nets per account and transaction currency;
    ``journal_totals`` flags each currency). ``GROSS`` is the primary book, ``DELTA`` the primary
    plus ``LEGACY`` book. In memory this is evidence; the database platform's own journal runs are
    the DB-bound part (reported not run until the lane databases exist)."""
    run = platform_props.close_run(bundle(spec, books=("ASC606", "LEGACY")))
    posted = platform_props.periods_posted(run, platform_props.PRIMARY, platform_props.LEGACY)
    # the oracle says whether any obligation's cumulative posted revenue reaches one minor unit
    # (a ratable line allocated 0 minor units posts nothing — batch #8, DG-PROP-02 pin above)
    expects_posting = _expects_posting(spec)
    assert bool(posted) == expects_posting, (posted, spec)
    if not posted:
        # consistency: no batch ⇒ the engine recognised nothing anywhere
        book = run.primary()
        assert all(v.columns["revenue_cum"] == 0 for v in book.obligation_versions), spec
    for entity, period_key in posted:
        for mode in platform_props.modes(run):
            lines = platform_props.batch(run, entity, period_key, mode)
            assert platform_props.unbalanced(lines) == [], (entity, period_key, mode, lines)
            functional = platform_props.functional_batch(run, entity, period_key, mode)
            assert platform_props.unbalanced(functional) == [], (
                entity,
                period_key,
                mode,
                functional,
            )
            # every summarised line nets a non-zero amount in the world's one currency (POL-006)
            assert all(line.net != 0 for line in lines)
            assert {line.currency for line in lines} <= {spec.currency}
