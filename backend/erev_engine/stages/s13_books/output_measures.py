"""Stage 13 output measures: the T-CON-08 figures the assembler used to compute after the trace
was built, now computed WITH their nodes before ``TraceBuilder.build`` (D-97 (8), supervisor ruling
T1F-Q-1 (A); dev-guide DG-KRN-EXP-01; ENGINE_SPEC CV-50 links; lane ENG-T1F).

Per book: the five contract sums ``revenue_cum`` (Σ obligation ``revenue_cum`` less the cumulative
JET-14 release of the period holding d_v, S04-R-02 rev 1.6), ``billed_cum``, ``scheduled_amount``,
``awaiting_trigger_amount`` (Σ obligation nodes) and ``net_position`` (Σ ``position_obligation``),
each a ``books.contract_sum.v1`` node ``<column>:<group>:-`` citing the obligation nodes; and the
version-date re-measurements of the build-up — the returns memo (S04-R-08, S09-R-23: −Σ
round(r × (Y + E)) replaces ``expected_returns_amount`` and moves ``transaction_price``), the
routed-out ``LEASE_842`` allocation (D-88 L7-5-Q-6) and ``sales_tax_excluded_amount`` at d_v
(S04-R-20) — each a ``books.version_adjustment.v1`` node ``<column>@<event key>:<group>:-`` citing
the last build-up node, where the event is the latest event the version includes (it dates d_v).
When the re-measured value equals the last build-up the build-up node is the link and no node is
emitted. The assembler reads ``OutputMeasures`` from the published states under ``OUTPUT_KEY``,
checks its own figures against it and links; without stage 09 the sums are 0 and unlinked (the
assembler's defaults, reduced stage lists only). Standard library only (DG-ARC-02).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date
from fractions import Fraction
from functools import partial
from types import MappingProxyType
from typing import Final

from erev_engine import money
from erev_engine.enums import ScopeFlag
from erev_engine.errors import EngineError
from erev_engine.formulas import binds_encoded, rational_param
from erev_engine.stages.s04_transaction_price import TP_COMPONENTS
from erev_engine.stages.s04_transaction_price.taxes import collected_tax
from erev_engine.stages.s09_recognition import RecognitionState
from erev_engine.stages.s09_recognition.schedule import ObligationMeasures
from erev_engine.stages.s10_billing_balances import BalanceState
from erev_engine.stages.state import AllocatedState, AllocationSegment, BookContext, ObligationState
from erev_engine.trace import TraceBuilder

__all__ = [
    "OUTPUT_KEY",
    "SUM_FORMULA",
    "ADJUSTMENT_FORMULA",
    "OutputMeasures",
    "publish",
    "returns_memo",
    "routed_out_lease_allocation",
    "version_date",
]

OUTPUT_KEY: Final = "13/output_measures"  # the published-state key (like ``08/late_events``)
SUM_FORMULA: Final = "books.contract_sum.v1"
ADJUSTMENT_FORMULA: Final = "books.version_adjustment.v1"
UNIT_RATE_FORMULA: Final = "books.unit_revenue_rate.v1"  # CV-47 (b); D-98 candidate 88
# CV-50 / DG-KRN-EXP-02: the period slot of a version-date re-measurement beside a boundary node
# of the same event and measure that holds a different value.
RETURNS_QUALIFIER: Final = "returns"
RELEASE: Final = "incentive_release_cum"  # the stage 10 JET-14 release (S10-R-26; D-91)
SUMS: Final = (
    ("revenue_cum", "09", "revenue_cum"),
    ("scheduled_amount", "09", "scheduled_amount"),
    ("awaiting_trigger_amount", "09", "awaiting_trigger_amount"),
    ("billed_cum", "10", "billed_cum"),
    ("net_position", "10", "position_obligation"),
)


@dataclass(frozen=True, slots=True)
class OutputMeasures:
    """The T-CON-08 figures stage 13 computed with nodes: column → (value, node id)."""

    values: Mapping[str, int]
    nodes: Mapping[str, str]
    # CV-47 (b) (D-98 candidate 88): per obligation subject key, the exact unit revenue rates
    # ``original_unit_revenue_rate`` / ``remaining_unit_revenue_rate`` with their node ids.
    obligation_values: Mapping[str, Mapping[str, Fraction]] = MappingProxyType({})
    obligation_nodes: Mapping[str, Mapping[str, str]] = MappingProxyType({})


def version_date(st: AllocatedState) -> date:
    """d_v: the latest effective date the version includes (04 T-CON-11 ``effective_date``)."""
    latest = max((event.effective_date for event in st.events), default=st.inception_date)
    return max(latest, st.inception_date)


def returns_memo(
    st: AllocatedState, measures: Mapping[str, ObligationMeasures] | None
) -> int | None:
    """``expected_returns_amount`` at d_v: −Σ round(r_p × (Y_p + E_p)) that stage 09 nets from
    each returnable obligation's ``allocated_amount`` (S04-R-08, S09-R-23; D-77 decision 2). None
    unless every obligation with a return path publishes its reduction."""
    if not st.return_paths or not measures:
        return None
    total = 0
    for subject_key in st.return_paths:
        found = measures.get(subject_key)
        if found is None or found.returns_reduction is None:
            return None
        total += found.returns_reduction
    return -total


def _current(ob: ObligationState) -> dict[str, AllocationSegment]:
    found: dict[str, AllocationSegment] = {}
    for segment in ob.segments:
        found[segment.component] = segment
    return found


def routed_out_lease_allocation(st: AllocatedState) -> int:
    """Σ a_posted of the routed-out ``LEASE_842`` obligations (S03-R-11, PT-09) over their
    segments in force at the version date (D-88 L7-5-Q-6)."""
    return sum(
        segment.a_posted
        for ob in st.obligations
        if ob.scope_flag == ScopeFlag.LEASE_842
        for segment in _current(ob).values()
    )


def _holding_periods(ctx: BookContext, on: date) -> dict[str, str]:
    holding: dict[str, str] = {}
    for code, view in ctx.entities.items():
        for period in view.periods:
            if period.start_date <= on <= period.end_date:
                holding[code] = period.period_key
    return holding


def boundary_build_up_node(
    column: str, group: str, st: AllocatedState, holds: Callable[[str], bool]
) -> str | None:
    """CV-50 links (T1-F-2): the ``<column>@<event key>:<group>:-`` build-up node of the latest
    boundary event whose node holds the value. A boundary in between that appended no price (a
    RETURN_RATE re-pin) or whose build-up was not traced has no node and is passed over, so the
    boundary is read from the trace, never from the previous build-up's ``before_event_key``."""
    for event in sorted(st.events, key=lambda item: item.order_key, reverse=True):
        node_id = f"{column}@{event.event_key}:{group}:-"
        if holds(node_id):
            return node_id
    return None


def _holds(tb: TraceBuilder, node_id: str, value: int, scale: int) -> bool:
    existing = tb.value(node_id)
    return existing is not None and money.to_fraction(existing) * scale == value


def unit_revenue_rates(
    ctx: BookContext, st: AllocatedState, tb: TraceBuilder
) -> tuple[Mapping[str, Mapping[str, Fraction]], Mapping[str, Mapping[str, str]]]:
    """CV-47 (b) (D-98 candidates 88 and 117; legacy 01 §3.6 / §3.7): per obligation the exact unit
    revenue rates as version-state nodes — ``original_unit_revenue_rate`` = RAW x_p ÷ RAW Q
    (S05-R-16, CV-34; no value and no node when Q = 0) and ``remaining_unit_revenue_rate`` = exact
    remaining allocation ÷ remaining quantity (0 when the remaining quantity is 0) — each citing the
    two producing nodes as its inputs and carrying its operands as rational params (P14 replay)."""
    values: dict[str, dict[str, Fraction]] = {}
    nodes: dict[str, dict[str, str]] = {}
    for ob in sorted(st.obligations, key=lambda item: item.subject_key):
        subject = ob.subject_key
        for column, numerator, denominator, zero, raw in (
            # The ORIGINAL rate divides the RAW quota by the RAW quantity (S05-R-16, CV-34,
            # CV-47 (b); D-98 candidate 117): the encoded nodes are cited for lineage, but their
            # 18-place values are not the operands — a quota such as 1/3 would lose its tail.
            (
                "original_unit_revenue_rate",
                "original_allocated_exact",
                "original_quantity",
                None,
                (ob.original_allocation.x_exact, ob.original_quantity),
            ),
            # The REMAINING rate keeps its trace reconstruction: the posted remaining allocation's
            # exact value (value + residue) over the remaining quantity node (lane T1's matter).
            (
                "remaining_unit_revenue_rate",
                "remaining_allocation",
                "remaining_quantity",
                "0",
                None,
            ),
        ):
            bottom_id = f"{denominator}:{subject}:-"
            # The sources: the node(s) that produced the CURRENT original allocation (the state's
            # stamped producers — the inception relative node with the targeted shares, or the
            # S06-R-26 repin's share; D-98 candidate 117 F1), else the measure's own node.
            sources = (
                tuple(ob.original_allocation_nodes) or (f"{numerator}:{subject}:-",)
                if raw is not None
                else (f"{numerator}:{subject}:-",)
            )
            cited = [tb.exact(source) for source in sources]
            bottom = tb.exact(bottom_id)
            if any(item is None for item in cited) or bottom is None:
                continue  # no producing node (a routed-out line): the column stays NULL
            held_values = [item for item in cited if item is not None]
            top = sum(held_values, Fraction(0))
            if raw is not None:
                # The governing operands; each must bind to the EXACT values (value + residue,
                # DG-KRN-EXP-03) of its cited source(s) within the CV-51 encoding bound — half a
                # unit at 18 places per cited node, the whole contract — the raw quota to the sum
                # of the producers, the raw quantity to the quantity node; else the citation is
                # stale (an invariant, never a silent substitution). ``binds_encoded`` states the
                # bound; ``reevaluate`` feeds the same exact values (EXACT_INPUT_FORMULAS).
                for operand, held, cited_values, cited_ids in (
                    (raw[0], top, held_values, sources),
                    (raw[1], bottom, [bottom], (bottom_id,)),
                ):
                    if not binds_encoded(operand, cited_values):
                        raise EngineError(
                            "ENGINE_INVARIANT_VIOLATED",
                            "the raw operand of the original unit revenue rate is not the exact "
                            "value of its cited producing node(s) within the CV-51 encoding bound",
                            subject_key=subject,
                            detail={
                                "rule": "CV-47",
                                "column": column,
                                "node_id": ",".join(cited_ids),
                                "operand": rational_param(operand),
                                "cited": rational_param(held),
                            },
                        )
                top, bottom = raw  # the governing operands; the nodes stay the cited sources
            if bottom == 0:
                if zero is None:
                    continue  # x_p ÷ 0: NULL, no node (legacy NaN / inf)
                value = Fraction(0)
            else:
                value = top / bottom
            node_id = tb.node(
                measure=column,
                subject_key=subject,
                period_key=None,
                value=value,
                currency=ctx.txn_currency,
                minor_unit=None,
                formula_id=UNIT_RATE_FORMULA,
                inputs=[*sources, bottom_id],
                params={
                    **({} if zero is None else {"zero": zero}),
                    # the raw operands travel in params so the rate re-evaluates exactly (P14):
                    # both for the original rate, the exact allocation alone for the remaining one
                    **(
                        {"allocation": rational_param(top), "quantity": rational_param(bottom)}
                        if raw is not None
                        else {"allocation": rational_param(top)}
                    ),
                },
                narrative_key=UNIT_RATE_FORMULA.rsplit(".v", 1)[0],
            )
            values.setdefault(subject, {})[column] = value
            nodes.setdefault(subject, {})[column] = node_id
    return (
        MappingProxyType({k: MappingProxyType(v) for k, v in values.items()}),
        MappingProxyType({k: MappingProxyType(v) for k, v in nodes.items()}),
    )


def publish(
    ctx: BookContext, published: Mapping[str, object], st: AllocatedState, tb: TraceBuilder
) -> OutputMeasures | None:
    """The output measures of one book, or None without a stage 09 state (see module)."""
    recognition = published.get("09")
    if not isinstance(recognition, RecognitionState):
        return None
    balances = published.get("10")
    balances = balances if isinstance(balances, BalanceState) else None
    group = st.group_code
    minor_unit = ctx.currencies[ctx.txn_currency].minor_unit
    scale: int = 10**minor_unit
    as_of = version_date(st)
    values: dict[str, int] = {}
    nodes: dict[str, str] = {}
    recognised = recognition.obligation_measures
    billed = {} if balances is None else balances.obligation_measures
    for column, stage, measure_name in SUMS:
        source: Mapping[str, object] = recognised if stage == "09" else billed
        inputs: list[str] = []
        signs: list[str] = []
        total = 0
        params = {"as_of": as_of.isoformat()}
        for subject_key in sorted(source):
            item = source[subject_key]
            value = getattr(item, measure_name)
            node_id = getattr(item, "trace_nodes", {}).get(measure_name)
            total += int(value)
            if node_id is not None:
                inputs.append(node_id)
                signs.append("+")
        if column == "awaiting_trigger_amount":
            # An obligation without stage 09 measures (a routed-out line, S03-R-11) publishes its
            # whole allocation as awaiting trigger (the assembler's T-CON-11 default); its
            # allocation node is the lineage, the amount the params ``default_allocations``.
            default = 0
            for ob in sorted(st.obligations, key=lambda item: item.subject_key):
                if ob.subject_key in recognised:
                    continue
                for segment in _current(ob).values():
                    default += segment.a_posted
                    node_id = (
                        f"original_allocated_amount:{ob.subject_key}:-"
                        if segment.event_key is None
                        else f"allocated_amount@{segment.event_key}:{ob.subject_key}:-"
                    )
                    if tb.value(node_id) is not None:
                        inputs.append(node_id)
                        signs.append("+")
                        default -= segment.a_posted  # cited: the node carries the amount
            total += sum(
                segment.a_posted
                for ob in st.obligations
                if ob.subject_key not in recognised
                for segment in _current(ob).values()
            )
            if default:
                params["default_allocations"] = str(default)
        if column == "revenue_cum" and balances is not None:
            holding = _holding_periods(ctx, as_of)
            for target in balances.customer_consideration:
                if target.measure == RELEASE and holding.get(target.entity) == target.period_key:
                    total -= target.value
                    inputs.append(target.node_id)
                    signs.append("-")
        node_id = f"{column}:{group}:-"
        if tb.value(node_id) is not None:
            raise EngineError(
                "ENGINE_INVARIANT_VIOLATED",
                "a contract-version sum node id is already emitted",
                subject_key=group,
                detail={"rule": "CV-50", "column": column},
            )
        values[column] = total
        nodes[column] = tb.node(
            measure=column,
            subject_key=group,
            period_key=None,
            value=total,
            currency=ctx.txn_currency,
            minor_unit=minor_unit,
            formula_id=SUM_FORMULA,
            inputs=inputs,
            params={**params, "signs": ",".join(signs)},
            narrative_key=SUM_FORMULA.rsplit(".v", 1)[0],
        )
    rates = unit_revenue_rates(ctx, st, tb)  # CV-47 (b): per-obligation unit revenue rates
    tp = st.tp_history[-1] if st.tp_history else None
    if tp is None:
        return OutputMeasures(MappingProxyType(values), MappingProxyType(nodes), *rates)
    latest = max(st.events, key=lambda event: event.order_key, default=None)
    members = {view.header.external_id for view in st.contracts}
    price = tp.total.posted
    expected_returns = tp.expected_returns.posted
    memo = returns_memo(st, recognised)
    adjustments: dict[str, int] = {}
    if memo is not None and memo != expected_returns:
        adjustments["expected_returns_amount"] = memo - expected_returns
        adjustments["transaction_price"] = memo - expected_returns
        price += memo - expected_returns
    leased = routed_out_lease_allocation(st)
    if leased:
        adjustments["transaction_price"] = adjustments.get("transaction_price", 0) - leased
        price -= leased
    tax = money.round_half_up(collected_tax(st.measure_events, members, as_of), minor_unit)
    if tax != tp.sales_tax_excluded.posted:
        adjustments["sales_tax_excluded_amount"] = tax - tp.sales_tax_excluded.posted
    for member, column in TP_COMPONENTS:
        if column == "tp_allocation_basis":
            continue
        base_value = getattr(tp, member).posted
        base = boundary_build_up_node(
            column, group, st, partial(_holds, tb, value=base_value, scale=scale)
        )
        if base is None and tb.value(f"{column}:{group}:-") is not None:
            base = f"{column}:{group}:-"
        delta = adjustments.get(column, 0)
        final = base_value + delta
        if column == "vc_constrained_amount":
            final = abs(final)  # R-SGN-01 magnitude (L4-3-Q-33)
        values[column] = final
        if base is None:
            continue
        if delta == 0:
            nodes[column] = base
            continue
        if latest is None:
            raise EngineError(
                "ENGINE_INVARIANT_VIOLATED",
                "a version-date re-measurement without an event dating the version",
                subject_key=group,
                detail={"rule": "CV-50", "column": column},
            )
        node_id = f"{column}@{latest.event_key}:{group}:-"
        existing = tb.value(node_id)
        period_key: str | None = None
        if existing is not None:
            if money.to_fraction(existing) * scale == final:
                nodes[column] = node_id
                continue
            if "expected_returns_amount" not in adjustments:
                raise EngineError(
                    "ENGINE_INVARIANT_VIOLATED",
                    "a version-date re-measurement collides with the boundary build-up node",
                    subject_key=group,
                    detail={"rule": "CV-50", "column": column, "event_key": latest.event_key},
                )
            # The boundary's build-up holds the expected returns at the rate in force before the
            # event while the memo at d_v stands at the new one: the returns-netted figure takes
            # the CV-50 qualifier ``returns`` in the period slot (Codex T1F-R3 ruling).
            period_key = RETURNS_QUALIFIER
        nodes[column] = tb.node(
            measure=f"{column}@{latest.event_key}",
            subject_key=group,
            period_key=period_key,
            value=final,
            currency=ctx.txn_currency,
            minor_unit=minor_unit,
            formula_id=ADJUSTMENT_FORMULA,
            inputs=[base],
            params={"adjustment": str(delta), "as_of": as_of.isoformat()},
            narrative_key=ADJUSTMENT_FORMULA.rsplit(".v", 1)[0],
        )
    return OutputMeasures(MappingProxyType(values), MappingProxyType(nodes), *rates)
