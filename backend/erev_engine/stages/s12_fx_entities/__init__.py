"""Stage 12: foreign currency and multi-entity (ENGINE_SPEC_B §12; BUILD_SPEC END-1 to END-3).

``run`` gives the flows of one book their functional-currency amounts per ASC 830 and IAS 21 with
IFRIC 22 (D-25, D-25a, D-25b; POLICIES ALG-08). Per (combination group, contracting entity) it
processes the control-role, monetary-liability and ``ENGINE`` mode receivable flows in ENG-06
order by effective date: time-driven releases first on a date, and monetary flows before the
control-role flows of the same event (ALG-08 §2.9.1). At every period end through the horizon it
remeasures the monetary positions to the closing rate (§12.2.3). It publishes the T-CON-18
movements, the open layers at each period end, the cumulative functional targets, the cumulative
JET-10 remeasurement targets and the cumulative FX gain or loss (§12.1; S12-R-01 to S12-R-13,
S12-R-19 to S12-R-21). Balances and layers belong to the contracting entity; the revenue of an
obligation performed by another entity also yields an intercompany pair (§12.2.5; S12-R-14 to
S12-R-17). ``translate_to_reporting`` is the reporting-currency view of the RPS reports (S12-R-18).

Integration after merge (D-81; L2-5-Q-10, L2-5-Q-11, L2-5-Q-21): ENGINE_SPEC_B §12.1 names the
flows that stages 09 to 11 produce, but no published member of ``CostLossState`` (ENC-15, lane
L2-4) carries them, and neither ``AllocatedState`` nor ``BookContext`` carries the pinned rates.
``run`` therefore reads the stage 12 input records through the ``FxSource`` protocol
(``allocated`` and ``fx_flows``), and the book loop binds ``rates`` from ``CanonicalBundle.fx`` as
it binds ``price_at`` (L1-3-Q-26) and ``posted`` (L2-5-Q-4). The ``STAGES`` entry is registered
(END-3); the adapter that derives ``FxFlows`` from the merged stage 09 to 11 states belongs to the
book loop. Submodules are private (DG-ENG-07). Standard library only (DG-ARC-02).
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date
from typing import Final, Protocol

from erev_engine import dates
from erev_engine.errors import EngineError
from erev_engine.stages.s01_canonicalize import (
    contract_entity_subject_key,
    group_entity_subject_key,
)
from erev_engine.stages.s12_fx_entities import monetary, receivables, reclass, remeasure
from erev_engine.stages.s12_fx_entities.balances import functional_member_targets, release_targets
from erev_engine.stages.s12_fx_entities.intercompany import IcPair, PairBook
from erev_engine.stages.s12_fx_entities.layers import (
    ControlFlow,
    FxTarget,
    LayerBalance,
    LayerMovement,
    RateRef,
    Running,
    UnitBook,
    UnitResult,
)
from erev_engine.stages.s12_fx_entities.monetary import MonetaryFlow
from erev_engine.stages.s12_fx_entities.rates import RateMissing, Rates
from erev_engine.stages.s12_fx_entities.remeasure import ReceivableFlow
from erev_engine.stages.s12_fx_entities.reporting import (
    FunctionalLine,
    ReportingLine,
    ReportingTranslation,
    translate_to_reporting,
)
from erev_engine.stages.state import AllocatedState, BookContext, Finding, RateIndex, Target
from erev_engine.trace import TraceBuilder

__all__ = [
    "FORMULA_IDS",
    "POLICY_KEYS",
    "ControlFlow",
    "FunctionalLine",
    "FxFlows",
    "FxSource",
    "FxState",
    "FxTarget",
    "IcPair",
    "LayerBalance",
    "LayerMovement",
    "MonetaryFlow",
    "RateRef",
    "ReceivableFlow",
    "ReportingLine",
    "ReportingTranslation",
    "run",
    "translate_to_reporting",
]

# ENGINE_SPEC_B Table 13-A row 12 (STAGE_POLICY_KEYS), sorted.
POLICY_KEYS: Final[tuple[str, ...]] = (
    "fx.cl_historical_layering",
    "fx.cl_layer_consumption",
    "fx.cl_layer_date",
    "fx.monetary_remeasurement",
    "fx.unbilled_revenue_rate",
    "ic.pair_amount",
    "ic.revenue_entity",
    "late_events.fx_rates",
)
# The registered formulas stage 12 emits so far (§12.5), sorted.
FORMULA_IDS: Final[tuple[str, ...]] = (
    "alloc.largest_remainder.v1",
    "ent.pair.v1",
    "ent.performing_revenue_rate.v1",
    "fx.asset_layer.create.v1",
    "fx.credit_memo_difference.v1",
    "fx.functional_member.v1",
    "fx.gain_loss.sum.v1",
    "fx.layer.consume.fifo.v1",
    "fx.layer.consume.pro_rata.v1",
    "fx.layer.create.v1",
    "fx.monetary_liability.create.v1",
    "fx.monetary_liability.recognition_difference.v1",
    "fx.monetary_liability.remeasure.closing.v1",
    "fx.monetary_liability.settle.v1",
    "fx.remeasure.closing.v1",
    "fx.revenue_functional.v1",
    "fx.settlement.spot.v1",
)


@dataclass(frozen=True, slots=True)
class FxFlows:
    """The dated inputs stage 12 reads from stages 09 to 11 (ENGINE_SPEC_B §12.1; L2-5-Q-10)."""

    control: tuple[ControlFlow, ...]
    # (contracting entity, period key) -> NP of S10-INV-05 in transaction minor units (S12-INV-03)
    positions: Mapping[tuple[str, str], int] = field(default_factory=dict)
    monetary: tuple[MonetaryFlow, ...] = ()  # refund liabilities, deposits, consideration payable
    receivables: tuple[ReceivableFlow, ...] = ()  # ENGINE billing mode only (S10-R-19)


class FxSource(Protocol):
    """The consumed state as stage 12 reads it (integration after merge, L2-5-Q-10)."""

    @property
    def allocated(self) -> AllocatedState: ...

    @property
    def fx_flows(self) -> FxFlows: ...


@dataclass(frozen=True, slots=True)
class FxState:
    """Stage 12 output (ENGINE_SPEC_B §12.1), members built so far."""

    allocated: AllocatedState  # consumed state, unchanged (§0.4)
    costs: FxSource  # the consumed stage 11 state, for stage 14
    layer_movements: tuple[LayerMovement, ...]  # T-CON-18 rows, processing order per entity
    layer_balances: tuple[LayerBalance, ...]  # open layers at every period end
    functional_targets: tuple[FxTarget, ...]  # cumulative, per subject and period end
    remeasurement_targets: tuple[FxTarget, ...]  # cumulative JET-10 parts per group@entity
    gain_loss_targets: tuple[FxTarget, ...]  # cumulative net FX gain per group@entity
    ic_pairs: tuple[IcPair, ...]  # per obligation performed by another entity and period (§12.2.5)
    findings: tuple[Finding, ...]  # CV-43 order
    # T-CON-09 ``_functional`` columns of foreign-currency entities per member and period with their
    # nodes (D-97 (8) T1F-Q-4; ``balances.functional_member_targets``); () without a foreign entity.
    functional_member_balances: tuple[Target, ...] = ()


Flow = ControlFlow | MonetaryFlow | ReceivableFlow


@dataclass(frozen=True, slots=True)
class _Dated:
    when: date
    order: tuple[int, int, str, int, str, str]
    flow: Flow


def run(
    ctx: BookContext, st: FxSource, tb: TraceBuilder, *, rates: RateIndex | None = None
) -> FxState:
    """Layers, functional targets and remeasurements of one book (ENGINE_SPEC_B §12.2)."""
    flows = st.fx_flows
    allocated = st.allocated
    movements: list[LayerMovement] = []
    balances: list[LayerBalance] = []
    functional: list[FxTarget] = []
    remeasurement: list[FxTarget] = []
    gain_loss: list[FxTarget] = []
    ic_pairs: list[IcPair] = []
    findings: list[Finding] = []
    entities = {flow.entity for flow in flows.control}
    entities |= {flow.entity for flow in flows.monetary}
    entities |= {flow.entity for flow in flows.receivables}
    for entity in sorted(entities):
        view = ctx.entities.get(entity)
        if view is None:
            raise ValueError(f"flows name the entity {entity!r}, absent from the book (CV-45)")
        if view.functional_currency != ctx.txn_currency and rates is None:
            raise EngineError(
                "ENGINE_INVARIANT_VIOLATED",
                "stage 12 converts a foreign currency without a bound rate index",
                subject_key=group_entity_subject_key(allocated.group_code, entity),
                detail={"rule": "S12-R-01"},
            )
        pair = Rates(
            (() if rates is None else rates.rates), ctx.txn_currency, view.functional_currency
        )
        book = UnitBook(ctx, pair, tb, group=allocated.group_code, entity=entity)
        pairs = PairBook(ctx, allocated, rates, book)
        try:
            result = _measure(book, pairs, allocated.inception_date, flows, _attributions(st))
        except RateMissing as missing:
            # S12-R-01; CV-42: the unit stops, the other units continue.
            findings.append(
                Finding(
                    "FX_RATE_MISSING",
                    "ERROR",
                    book.unit_key,
                    missing.detail,
                    12,
                    missing.event_key,
                )
            )
            continue
        movements.extend(result.movements)
        balances.extend(result.balances)
        functional.extend(result.functional_targets)
        # D-88 L7-6-Q-6 as amended by D-91: the functional JET-14 release (the posted ordinary
        # release of the stage 10 set) at historical carrying (POL-164).
        functional.extend(release_targets(book, _consideration(st), result.functional_targets))
        remeasurement.extend(result.remeasurement_targets)
        gain_loss.extend(result.gain_loss_targets)
        ic_pairs.extend(pairs.publish())
        findings.extend(result.findings)
    state = FxState(
        allocated=allocated,
        costs=st,
        layer_movements=tuple(movements),
        layer_balances=tuple(balances),
        functional_targets=tuple(functional),
        remeasurement_targets=tuple(remeasurement),
        gain_loss_targets=tuple(gain_loss),
        ic_pairs=tuple(ic_pairs),
        findings=tuple(sorted(findings, key=lambda finding: finding.sort_key())),
    )
    return dataclasses.replace(
        state, functional_member_balances=_functional_member_balances(ctx, st, state, tb)
    )


def _functional_member_balances(
    ctx: BookContext, st: FxSource, fx: FxState, tb: TraceBuilder
) -> tuple[Target, ...]:
    """D-97 (8) T1F-Q-4: the ``_functional`` member columns of foreign-currency entities with their
    nodes, from the stage 10 member balances the consumed state carries (none without them)."""
    # The book loop hands stage 12 a ``CostsView`` (allocated, costs, fx_flows, part_inputs); the
    # stage 10 state is ``costs.balances`` (a bare stage 10 or 11 state exposes ``balances``).
    costs = getattr(st, "costs", None)
    balances = getattr(costs, "balances", None)
    if balances is None:
        balances = getattr(st, "balances", None)
    members = getattr(balances, "member_balances", ())
    if not members:
        return ()
    functional = {code: view.functional_currency for code, view in ctx.entities.items()}
    periods = {
        code: tuple(
            period.period_key for period in sorted(view.periods, key=lambda p: p.start_date)
        )
        for code, view in ctx.entities.items()
    }
    member_of = {
        ob.subject_key: contract_entity_subject_key(ob.contract_key, ob.contracting_entity)
        for ob in fx.allocated.obligations
    }
    sums = getattr(balances, "member_sums", ())
    receivable_members = frozenset(
        (item.subject_key, item.period_key)
        for item in sums
        if item.measure == "accounts_receivable"
    )
    payable_txn = {
        (item.subject_key, item.period_key): item.value
        for item in sums
        if item.measure == "consideration_payable"
    }
    return functional_member_targets(
        ctx,
        fx,
        members=members,
        txn_currency=ctx.txn_currency,
        functional=functional,
        periods=periods,
        member_of=member_of,
        receivable_members=receivable_members,
        payable_txn=payable_txn,
        tb=tb,
    )


def _order(
    record_seq: int | None, source_key: str, stream: int, key: str, kind: str
) -> tuple[int, int, str, int, str, str]:
    # Time-driven releases first on a date, then ENG-06 order; monetary before control-role flows
    # before receivables of the same event (ALG-08 §2.9.1).
    return (0 if record_seq is None else 1, record_seq or 0, source_key, stream, key, kind)


def _consideration(st: FxSource) -> tuple[Target, ...]:
    """The EMOD-22 targets the book loop binds for stage 14 (``PartInputs.customer_consideration``,
    the stage 10 set of ENGINE_SPEC_B S10-R-26), which stage 12 reads for the JET-14 release."""
    inputs = getattr(st, "part_inputs", None)
    found = getattr(inputs, "customer_consideration", ())
    return tuple(item for item in found if isinstance(item, Target))


def _attributions(st: FxSource) -> tuple[Target, ...]:
    """The stage 10 reclass attributions the book loop binds for stage 14 (S12-R-09; §10.2.7),
    and the ``ENGINE`` mode billing and tax targets of JET-03 (S12-R-02; L6-5)."""
    inputs = getattr(st, "part_inputs", None)
    found = (
        *getattr(inputs, "reclass", ()),
        *getattr(inputs, "invoices", ()),
        *getattr(inputs, "invoice_tax", ()),
    )
    return tuple(item for item in found if isinstance(item, Target))


def _measure(
    book: UnitBook,
    pairs: PairBook,
    inception: date,
    flows: FxFlows,
    attributions: tuple[Target, ...] = (),
) -> UnitResult:
    """Process every flow through the horizon and close each period (S12-R-13). A unit whose
    replay would begin after the horizon — the group's inception lies after it and no flow is dated
    inside it — has no period to close: nothing is processed (S12-R-13 rev 1.100; C-05)."""
    reclass_running: dict[tuple[str, str], Running] = {}
    horizon = book.horizon()
    items: list[_Dated] = []
    for control in flows.control:
        when = book.layer_date(control) if control.entity == book.entity else None
        if when is not None:
            order = _order(
                control.record_seq, control.source_key, 1, control.subject_key, control.kind
            )
            items.append(_Dated(when, order, control))
    for mflow in flows.monetary:
        if mflow.entity == book.entity:
            order = _order(
                mflow.record_seq, mflow.source_key, 0, mflow.component_key, mflow.direction
            )
            items.append(_Dated(mflow.effective_date, order, mflow))
    for rflow in flows.receivables:
        if rflow.entity == book.entity:
            order = _order(rflow.record_seq, rflow.source_key, 2, rflow.invoice_key, rflow.kind)
            items.append(_Dated(rflow.effective_date, order, rflow))
    items = sorted(
        (item for item in items if item.when <= horizon.end_date),
        key=lambda item: (item.when, item.order),
    )
    keys = [item.flow.flow_key for item in items]
    if len(set(keys)) != len(keys):
        raise EngineError(
            "ENGINE_INVARIANT_VIOLATED",
            "two stage 12 flows share a source, kind and subject",
            subject_key=book.unit_key,
            detail={"rule": "S12-R-03"},
        )
    start = min([inception, *(item.when for item in items)])
    if start > horizon.end_date:
        return book.result()
    index = 0
    billing = receivables.Billing()  # JET-03 functional amounts in ENGINE mode (L6-5)
    for period in dates.covering_periods(book.calendar.periods, start, horizon.end_date):
        while index < len(items) and items[index].when <= period.end_date:
            item = items[index]
            try:
                _dispatch(book, pairs, item)
            except RateMissing as missing:
                missing.event_key = None if item.flow.record_seq is None else item.flow.source_key
                raise
            index += 1
        remeasure.period_end(book, period)
        book.close_period(period, flows.positions)
        reclass.close_period(book, period, attributions, reclass_running)
        receivables.close_period(book, period, attributions, billing)
    return book.result()


def _dispatch(book: UnitBook, pairs: PairBook, item: _Dated) -> None:
    flow = item.flow
    if isinstance(flow, ControlFlow):
        pairs.revenue(flow, item.when, book.control(flow, item.when))
    elif isinstance(flow, MonetaryFlow):
        monetary.apply(book, flow, item.when)
    else:
        remeasure.receivable(book, flow, item.when)
