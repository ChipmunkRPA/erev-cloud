"""Stage 13 LEGACY book: the pre-standard revenue fold (ENGINE_SPEC_B §13.2.4; END-8).

``run`` folds only ``PRE_STANDARD_REVENUE_RECORDED`` events: per obligation and period of its
contracting entity through the horizon, the cumulative pre-standard revenue L_p is the sum of the
signed event amounts effective on or before the period end, traced as ``pre_standard_revenue_cum``
(formula ``books.legacy_fold.v1``). No stage 02 to 12 runs for the book (S13-R-07; RCP-14). POL-008
selects where the events come from (progress uploads or the ERP revenue feed); both arrive as the
same event type, so the fold only checks the literal. When the stage list holds stage 14, the book
posts its own ``JET-15`` lines through stage 14, reversing the pre-standard revenue the ERP booked:
Dr ``PRE_STANDARD_REVENUE`` / Cr ``CONTRACT_LIABILITY``, the period change of L_p less what the
LEGACY subledger already holds, in the obligation's contracting entity (S13-R-08; D-89
L7-6-Q-8). The DELTA view is primary lines plus LEGACY lines (S13-INV-03). The lines resolve
accounts through the obligations of the primary book, because the revenue string belongs to the
obligation (POLICIES JET-15;
L3-2-Q-13). The LEGACY result carries no contract version, obligation versions, balances or
schedules (S13-R-11; ``book_output``).

``version_measures`` gives the primary book's obligation versions ``pre_standard_revenue_cum``, the
LEGACY fold at the version date, and ``pre_standard_revenue_amount``, the amounts of the events
first included in the version, so a modification or estimate version carries 0 while the
cumulative rolls (S13-R-10; DEV-050, DEV-051). Standard library only (DG-ARC-02).
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from types import MappingProxyType
from typing import Final

from erev_engine.bundle import BookOutput, PostingIntent
from erev_engine.money import format_money
from erev_engine.stages.s01_canonicalize import (
    booking_lines,
    obligation_subject_key,
    payload_fraction,
)
from erev_engine.stages.s12_fx_entities import FxFlows, FxState
from erev_engine.stages.s14_posting import PartInputs, PostingState
from erev_engine.stages.state import (
    AllocatedState,
    BookContext,
    CanonicalBundle,
    EventView,
    Finding,
    SpecialistTargets,
    Target,
)
from erev_engine.trace import SourceRef, Trace, TraceBuilder

__all__ = [
    "AMOUNT_MEASURE",
    "EVENT_TYPE",
    "FORMULA_ID",
    "MEASURE",
    "LegacyState",
    "PreStandard",
    "book_output",
    "empty_state",
    "fold_at",
    "revenue_strings",
    "run",
    "version_date",
    "version_measures",
]

EVENT_TYPE: Final = "PRE_STANDARD_REVENUE_RECORDED"
SOURCE_CODE: Final = "legacy_book.source"  # POL-008
SOURCES: Final = frozenset({"PRE_STANDARD_EVENTS", "ERP_REVENUE_FEED"})
MEASURE: Final = "pre_standard_revenue_cum"  # §13.5
AMOUNT_MEASURE: Final = "pre_standard_revenue_amount"  # T-CON-11 activity of the version
FORMULA_ID: Final = "books.legacy_fold.v1"
_NARRATIVE: Final = "books.legacy_fold"
_REVENUE_ROLE: Final = "REVENUE"
_PRE_STANDARD_ROLE: Final = "PRE_STANDARD_REVENUE"

Amounts = Mapping[str, tuple[tuple[EventView, int], ...]]  # obligation -> (event, minor units)


@dataclass(frozen=True, slots=True)
class LegacyState:
    """The LEGACY book of one computation (§13.1; S13-R-11)."""

    allocated: AllocatedState  # the contracts and obligations the lines resolve accounts through
    targets: tuple[Target, ...]  # pre_standard_revenue_cum per obligation and period, book LEGACY
    posting: PostingState | None  # stage 14 over the targets; None without stage 14 in the list
    findings: tuple[Finding, ...]  # CV-43 order

    @property
    def posting_intents(self) -> tuple[PostingIntent, ...]:
        return () if self.posting is None else self.posting.posting_intents


@dataclass(frozen=True, slots=True)
class PreStandard:
    """The T-CON-11 pre-standard measures of one primary-book obligation version (S13-R-10)."""

    subject_key: str
    as_of: date  # d_v, the version date
    cumulative: int  # pre_standard_revenue_cum, minor units
    amount: int  # pre_standard_revenue_amount: events first included in the version
    trace_nodes: Mapping[str, str]  # measure -> node id


@dataclass(frozen=True, slots=True)
class _Source:
    """The LEGACY targets as stage 14 reads its consumed state (``FxSource``, ``PartSource``)."""

    allocated: AllocatedState
    fx_flows: FxFlows
    part_inputs: PartInputs


def run(
    ctx: BookContext,
    cb: CanonicalBundle,
    tb: TraceBuilder,
    *,
    allocated: AllocatedState | None = None,
    post: Callable[[FxState], object] | None = None,
) -> LegacyState:
    """The LEGACY fold and, with ``post`` (stage 14 bound by the book loop), its JET-15 lines."""
    base = empty_state(cb) if allocated is None else allocated
    amounts = _amounts(ctx, cb)
    minor_unit = ctx.currencies[ctx.txn_currency].minor_unit
    targets: list[Target] = []
    for subject_key, entity in sorted(_obligations(cb, base, amounts).items()):
        calendar = ctx.entities.get(entity)
        if calendar is None or entity not in ctx.horizon:
            raise ValueError(f"{subject_key}: the LEGACY book keeps no calendar of {entity!r}")
        horizon = ctx.horizon[entity]
        events = amounts.get(subject_key, ())
        for period in sorted(calendar.periods, key=lambda item: item.start_date):
            source = ctx.policies.value(SOURCE_CODE, entity=entity, period=period.period_key)
            if source not in SOURCES:
                raise ValueError(f"{SOURCE_CODE} holds no POL-008 option at {period.period_key}")
            included = [item for item in events if item[0].effective_date <= period.end_date]
            node_id = _node(ctx, tb, subject_key, period.period_key, included, minor_unit)
            value = sum(amount for _, amount in included)
            targets.append(
                Target(ctx.book_code, entity, subject_key, MEASURE, period.period_key, None, value,
                       None, node_id)
            )  # fmt: skip
            if period.period_key == horizon:
                break
    ordered = tuple(targets)
    posting: PostingState | None = None
    if post is not None:
        strings = revenue_strings(base)
        source_state = _Source(strings, FxFlows(()), PartInputs(pre_standard=ordered))
        found = post(_fx_state(strings, source_state))
        posting = found if isinstance(found, PostingState) else None
    findings = () if posting is None else posting.findings
    return LegacyState(allocated=base, targets=ordered, posting=posting, findings=findings)


def fold_at(ctx: BookContext, cb: CanonicalBundle, subject_key: str, at: date) -> int:
    """L at a date: the pre-standard revenue of an obligation effective on or before ``at``."""
    events = _amounts(ctx, cb).get(subject_key, ())
    return sum(amount for event, amount in events if event.effective_date <= at)


def version_date(st: AllocatedState) -> date:
    """d_v: the latest effective date the version includes (04 T-CON-11 ``effective_date``)."""
    latest = max((event.effective_date for event in st.events), default=st.inception_date)
    return max(latest, st.inception_date)


def version_measures(
    ctx: BookContext, cb: CanonicalBundle, st: AllocatedState, tb: TraceBuilder
) -> tuple[PreStandard, ...]:
    """S13-R-10: the pre-standard measures of every obligation version of the primary book."""
    amounts = _amounts(ctx, cb)
    minor_unit = ctx.currencies[ctx.txn_currency].minor_unit
    as_of = version_date(st)
    out: list[PreStandard] = []
    for ob in sorted(st.obligations, key=lambda item: item.subject_key):
        included = [
            item for item in amounts.get(ob.subject_key, ()) if item[0].effective_date <= as_of
        ]
        new = [item for item in included if item[0].is_new]
        cumulative = _node(ctx, tb, ob.subject_key, None, included, minor_unit)
        amount = _node(ctx, tb, ob.subject_key, None, new, minor_unit, measure=AMOUNT_MEASURE)
        out.append(
            PreStandard(
                subject_key=ob.subject_key,
                as_of=as_of,
                cumulative=sum(value for _, value in included),
                amount=sum(value for _, value in new),
                trace_nodes=MappingProxyType({AMOUNT_MEASURE: amount, MEASURE: cumulative}),
            )
        )
    return tuple(out)


def zero_measures(
    ctx: BookContext, st: AllocatedState, tb: TraceBuilder
) -> tuple[PreStandard, ...]:
    """The pre-standard measures of a framework book that keeps none (no LEGACY book in the bundle,
    or not the primary book): 0 with its own ``books.legacy_fold.v1`` nodes citing no event, so
    the T-CON-11 zero columns link a node (DG-KRN-EXP-01; D-97 (8); lane ENG-T1F)."""
    minor_unit = ctx.currencies[ctx.txn_currency].minor_unit
    as_of = version_date(st)
    out: list[PreStandard] = []
    for ob in sorted(st.obligations, key=lambda item: item.subject_key):
        cumulative = _node(ctx, tb, ob.subject_key, None, [], minor_unit)
        amount = _node(ctx, tb, ob.subject_key, None, [], minor_unit, measure=AMOUNT_MEASURE)
        out.append(
            PreStandard(
                subject_key=ob.subject_key,
                as_of=as_of,
                cumulative=0,
                amount=0,
                trace_nodes=MappingProxyType({AMOUNT_MEASURE: amount, MEASURE: cumulative}),
            )
        )
    return tuple(out)


def book_output(book_code: str, state: LegacyState, trace: Trace) -> BookOutput:
    """S13-R-11: the LEGACY ``BookOutput``, posting intents and trace only (§0.5; D-76)."""
    return BookOutput(
        book_code=book_code,
        contract_version=None,
        status_in_book=(),
        obligation_versions=(),
        balances=(),
        schedules=(),
        cost_asset_versions=(),
        loss_provision_versions=(),
        fx_layer_movements=(),
        posting_intents=state.posting_intents,
        proposals=(),
        time_triggers=(),
        trace=trace,
    )


def revenue_strings(st: AllocatedState) -> AllocatedState:
    """The obligations as the JET-15 lines resolve accounts: ``PRE_STANDARD_REVENUE`` takes the
    obligation's revenue string (POLICIES JET-15; S13-R-08; L3-2-Q-20).

    An obligation whose account overrides name ``REVENUE`` (the SSP entry's revenue account,
    REQ-SSP-014) and not ``PRE_STANDARD_REVENUE`` gains that override for the second role; an
    obligation without a revenue override resolves both roles through the mapping version.
    """
    changed = []
    for ob in st.obligations:
        overrides = ob.account_overrides
        revenue = overrides.get(_REVENUE_ROLE)
        if revenue is None or _PRE_STANDARD_ROLE in overrides:
            changed.append(ob)
            continue
        merged = dict(sorted({**overrides, _PRE_STANDARD_ROLE: revenue}.items()))
        changed.append(dataclasses.replace(ob, account_overrides=MappingProxyType(merged)))
    return dataclasses.replace(st, obligations=tuple(changed))


def empty_state(cb: CanonicalBundle) -> AllocatedState:
    """The group without obligations, posted over when the bundle keeps no framework book."""
    group = cb.group.group
    return AllocatedState(
        group_code=group.group_key,
        inception_date=group.inception_date,
        contracts=tuple(cb.contracts[key] for key in sorted(cb.contracts)),
        obligations=(),
        events=cb.events,
        measure_events=cb.measure_events,
        ledger=cb.ledger,
        return_paths=MappingProxyType({}),
        estimates=cb.estimates,
        tp_unconstrained=MappingProxyType({}),
        specialist_targets=SpecialistTargets((), (), (), (), ()),
        proposals=(),
        time_triggers=(),
        tp_history=(),
        targeted_vc_quotas=MappingProxyType({}),
        targeted_vc_quota_history=MappingProxyType({}),
        refund_components=MappingProxyType({}),
        findings=(),
    )


def _amounts(ctx: BookContext, cb: CanonicalBundle) -> Amounts:
    """The signed minor-unit amount of every pre-standard event, per obligation in ENG-06 order."""
    minor_unit = ctx.currencies[ctx.txn_currency].minor_unit
    found: dict[str, list[tuple[EventView, int]]] = {}
    for event in cb.events:
        if event.event_type != EVENT_TYPE:
            continue
        if len(event.obligation_subject_keys) != 1:
            raise ValueError(
                f"{event.event_key}: a pre-standard event names one obligation (§16.3)"
            )
        value = payload_fraction(event.payload, "amount")
        if value is None:
            raise ValueError(f"{event.event_key}: a pre-standard event carries its amount (§16.3)")
        scaled = value * 10**minor_unit
        if scaled.denominator != 1:
            raise ValueError(f"{event.event_key}: the amount is below the minor unit (CV-45)")
        found.setdefault(event.obligation_subject_keys[0], []).append((event, scaled.numerator))
    return MappingProxyType({key: tuple(items) for key, items in sorted(found.items())})


def _obligations(cb: CanonicalBundle, st: AllocatedState, amounts: Amounts) -> dict[str, str]:
    """Obligation subject key -> contracting entity: the framework book's obligations, the booking
    lines and the obligations the pre-standard events name."""
    found = {ob.subject_key: ob.contracting_entity for ob in st.obligations}
    entities = {key: view.header.contracting_entity_code for key, view in cb.contracts.items()}
    for key in sorted(cb.contracts):
        for line in booking_lines(cb.contracts[key]):
            subject_key = obligation_subject_key(key, str(line["obligation_key"]))
            found.setdefault(subject_key, entities[key])
    for subject_key, items in amounts.items():
        contract_key = items[0][0].contract_key
        found.setdefault(subject_key, entities[contract_key])
    return found


def _node(
    ctx: BookContext,
    tb: TraceBuilder,
    subject_key: str,
    period_key: str | None,
    included: Sequence[tuple[EventView, int]],
    minor_unit: int,
    *,
    measure: str = MEASURE,
) -> str:
    inputs = [
        SourceRef("contract_event", event.event_key, {"value": format_money(amount, minor_unit)})
        for event, amount in included
    ]
    return tb.node(
        measure=measure,
        subject_key=subject_key,
        period_key=period_key,
        value=sum(amount for _, amount in included),
        currency=ctx.txn_currency,
        minor_unit=minor_unit,
        formula_id=FORMULA_ID,
        inputs=inputs,
        narrative_key=_NARRATIVE,
    )


def _fx_state(allocated: AllocatedState, source: _Source) -> FxState:
    """A stage 12 state without flows: the LEGACY book converts nothing (S13-R-07)."""
    return FxState(
        allocated=allocated,
        costs=source,
        layer_movements=(),
        layer_balances=(),
        functional_targets=(),
        remeasurement_targets=(),
        gain_loss_targets=(),
        ic_pairs=(),
        findings=(),
    )
