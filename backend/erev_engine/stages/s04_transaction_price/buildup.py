"""Stage 04 build-up: fixed consideration, realised variable amounts, members and trace.

ENGINE_SPEC §4.2; §4.3 S04-R-01 to S04-R-03, S04-R-06, S04-R-08 to S04-R-18, S04-R-20; §4.4
S04-INV-01, S04-INV-03 and the version-state nodes named as T-CON-08 columns; formulas
``tp.buildup.v1``, ``tp.fixed.v1``, ``tp.realised_usage.v1``. Expected returns, implicit price
concessions, the financing adjustment, consideration payable, noncash consideration and sales taxes
come from ``returns``, ``concessions``, ``financing``, ``customer_consideration``, ``noncash`` and
``taxes``. Private to stage 04. Standard library only (DG-ARC-02).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import date
from fractions import Fraction
from typing import Final

from erev_engine import dates, royalties, usage
from erev_engine.bundle import EstimateVersionInput
from erev_engine.enums import RecognitionMethod
from erev_engine.errors import EngineError
from erev_engine.money import format_exact, round_half_up
from erev_engine.stages.s01_canonicalize import (
    encode_key,
    payload_date,
)
from erev_engine.stages.s03_pob_builder import PobDraft, PobState
from erev_engine.stages.s04_transaction_price import (
    concessions,
    customer_consideration,
    financing,
    noncash,
    returns,
    specialist,
    taxes,
    vc,
)
from erev_engine.stages.state import BookContext, EventView, Quota1, TpBuildUp, VcElementView
from erev_engine.trace import SourceRef, TraceBuilder

__all__ = [
    "IN_TP",
    "Accrual",
    "Realised",
    "out_of_scope_lines",
    "price",
    "realised",
    "royalty_accruals",
    "targets",
]

# S04-R-03: flags whose obligations carry fixed consideration (PT-09 keeps LEASE_842).
IN_TP: Final = specialist.IN_TP
BUILDUP: Final = "tp.buildup.v1"
FIXED: Final = "tp.fixed.v1"
REALISED: Final = "tp.realised_usage.v1"
FIXED_ON_LICENCE_PATTERN: Final = "FIXED_ON_LICENCE_PATTERN"
ROYALTY_ACCRUAL: Final = "ROYALTY_ACCRUAL"  # E-09
ACCRUE_ESTIMATE: Final = "ACCRUE_ESTIMATE"  # POL-056
UNREPORTED_SALES_POLICY: Final = "royalty.unreported_sales"  # POL-056
ZERO: Final = Fraction(0)


@dataclass(frozen=True, slots=True)
class Accrual:
    """A contract-wide ``ROYALTY_ACCRUAL`` pin counted as constrained VC (D-88 L7-5-Q-8)."""

    version: EstimateVersionInput
    member: str  # the version member that gives the amount
    amount: Fraction


@dataclass(frozen=True, slots=True)
class Realised:
    """Realised usage fees or royalties of one obligation (S04-R-06)."""

    obligation: PobDraft
    amount: Fraction
    reported: tuple[tuple[EventView, Fraction], ...]  # (USAGE_REPORTED, rated amount)
    guarantee: Fraction  # the minimum guarantee netted under POL-057, else 0
    # ENC-8: the ROYALTY_ACCRUAL versions counted for ended usage periods no statement covers
    # (version, member, amount), under POL-056 ACCRUE_ESTIMATE (S04-R-06; S09-R-32).
    accrued: tuple[tuple[EstimateVersionInput, str, Fraction], ...] = ()


def _royalty_bearing(st: PobState, ob: PobDraft) -> bool:
    """ENGINE_SPEC_B S09-R-01: the obligation carries the ``ROYALTY`` component (the predicate
    stage 05 opens the component with; ``erev_engine.royalties``)."""
    canonical = st.identified.canonical
    return royalties.bearing(
        str(ob.recognition_method),
        ob.contract_key,
        ob.obligation_key,
        ob.subject_key,
        canonical.measure_events,
        canonical.estimates,
    )


def _accrues(ctx: BookContext, st: PobState, contract: str, at: date) -> bool:
    """POL-056 ``ACCRUE_ESTIMATE`` at the contracting entity's period of ``at`` (pin P)."""
    entity = st.identified.canonical.contracts[contract].header.contracting_entity_code
    period = dates.period_of(ctx.entities[entity], at).period_key
    return ctx.policies.value(UNREPORTED_SALES_POLICY, entity=entity, period=period) == (
        ACCRUE_ESTIMATE
    )


def realised(
    ctx: BookContext, st: PobState, at: date, before: EventView | None
) -> tuple[Realised, ...]:
    """S04-R-06 for obligations measured by ``USAGE`` or ``RIGHT_TO_INVOICE`` (component
    ``PERIOD_VC``; ``erev_engine.usage``, ENC-6) and for royalty-bearing obligations (component
    ``ROYALTY``, ENGINE_SPEC_B S09-R-01; ``erev_engine.royalties``).

    Usage: the ``rated_amount`` of the obligation's non-royalty ``USAGE_REPORTED`` events before
    ``before`` whose ``usage_period_end`` is on or before ``at`` (S09-R-19); under POL-240
    ``ESTIMATE_MEASUREMENT_PERIOD_TP`` a usage obligation is priced by its VC element instead.
    Right to invoice: rated usage, else the net delivered quantity × the booking line's
    ``unit_price`` (D-87 L6-5-Q-16), else invoiced amounts net of taxes and credit memos
    (S09-R-18).
    Royalties: the latest statement per ended usage period plus, under POL-056
    ``ACCRUE_ESTIMATE``, the ``ROYALTY_ACCRUAL`` version in force for every ended period no
    statement covers, the realisation stage 09 recognises (S09-R-02, S09-R-32). Under POL-057
    ``FIXED_ON_LICENCE_PATTERN`` the stated price of a ``ROYALTY``-method licence is the guarantee,
    and only royalties above it are realised (S09-R-33).
    """
    canonical = st.identified.canonical
    measure_events = canonical.measure_events
    found: list[Realised] = []
    for ob in st.obligations:
        method = ob.recognition_method
        contract = ob.contract_key
        if method in (RecognitionMethod.RIGHT_TO_INVOICE, RecognitionMethod.USAGE):
            # ENC-6 (S04-R-06; S09-R-01, S09-R-02): the realised amounts of the PERIOD_VC component
            # from the one source rule stage 09 recognises (``erev_engine.usage``, DG-ENG-07): the
            # right to invoice for performance to date (S09-R-18; D-87 L6-5-Q-16), or POL-240
            # DERIVED usage fees at the end of their usage period (S09-R-19). Under
            # ESTIMATE_MEASUREMENT_PERIOD_TP a usage obligation is priced by its VC element (PT-01).
            if method == RecognitionMethod.USAGE:
                policy = ctx.policies.value(usage.TIER_MINIMUM_POLICY, contract=contract)
                if policy == usage.ESTIMATE_MEASUREMENT_PERIOD_TP:
                    continue
                usage_realisation = usage.derived_usage(
                    measure_events,
                    contract_key=contract,
                    obligation_key=ob.obligation_key,
                    subject_key=ob.subject_key,
                    at=at,
                    admits=lambda ev: before is None or ev.order_key < before.order_key,
                )
            else:
                usage_realisation = usage.right_to_invoice(
                    measure_events,
                    contract_key=contract,
                    obligation_key=ob.obligation_key,
                    subject_key=ob.subject_key,
                    booking=canonical.contracts[contract].booking,
                    at=at,
                    admits=lambda ev: before is None or ev.order_key < before.order_key,
                )
                # S04-R-06 rev 1.21 (D-98 candidate 28): the right to invoice up to the stated
                # price P is the FIXED consideration already priced; only the part above P is
                # realised here (S09-R-18 rev 1.14: the FIXED component's progress is R ÷ P).
                usage_realisation = replace(
                    usage_realisation,
                    items=usage.above_stated(usage_realisation.items, ob.stated_price),
                )
            by_key = {event.event_key: event for event in measure_events}
            found.append(
                Realised(
                    ob,
                    usage_realisation.amount,
                    tuple(
                        (by_key[item.event_key], item.amount) for item in usage_realisation.items
                    ),
                    ZERO,
                )
            )
            continue
        if not _royalty_bearing(st, ob):
            continue
        realisation = royalties.realised(
            measure_events,
            canonical.estimates,
            contract,
            ob.obligation_key,
            ob.subject_key,
            at=at,
            cutoff=None if before is None else before.order_key,
            inclusive=False,
            accrue=_accrues(ctx, st, contract, at),
        )
        amount = realisation.total
        guarantee = ZERO
        if method == RecognitionMethod.ROYALTY:
            policy = ctx.policies.value("royalty.minimum_guarantee", contract=contract)
            if policy == FIXED_ON_LICENCE_PATTERN:
                guarantee = ob.stated_price
                amount = max(ZERO, amount - guarantee)
        found.append(
            Realised(
                ob,
                amount,
                tuple((item.event, item.amount) for item in realisation.statements),
                guarantee,
                tuple((item.version, item.member, item.amount) for item in realisation.accruals),
            )
        )
    return tuple(found)


def royalty_accruals(
    ctx: BookContext, st: PobState, at: date, before: EventView | None
) -> tuple[Accrual, ...]:
    """S04-R-06 extension (D-88 L7-5-Q-8): contract-wide royalty accruals of VC.

    A ``ROYALTY_ACCRUAL`` element with ``allocation_target = CONTRACT`` on a contract none of whose
    obligations is measured by ``ROYALTY`` or ``USAGE`` (components ``ROYALTY``, ``PERIOD_VC``) is
    variable consideration of the contract. Under POL-056 ``ACCRUE_ESTIMATE`` its pin at ``at``
    before ``before`` whose ``usage_period_end_date`` is on or before ``at``, with no royalty
    statement for that period, enters ``vc_constrained``: its ``constrained_amount``, else its
    ``expected_total_amount``. Royalty-component obligations keep S04-R-06 as written.
    """
    pins = st.identified.canonical.estimates
    measure_events = st.identified.canonical.measure_events
    found: list[Accrual] = []
    for key in sorted(pins.pins):
        version = pins.pin(key, at, before)
        if version is None or version.estimate_kind != ROYALTY_ACCRUAL:
            continue
        if version.allocation_target != "CONTRACT":
            continue
        contract = vc._contract_of(st, key)
        if any(
            ob.contract_key == contract
            and (ob.recognition_method == RecognitionMethod.USAGE or _royalty_bearing(st, ob))
            for ob in st.obligations
        ):
            continue
        entity = st.identified.canonical.contracts[contract].header.contracting_entity_code
        period = dates.period_of(ctx.entities[entity], at).period_key
        policy = ctx.policies.value(UNREPORTED_SALES_POLICY, entity=entity, period=period)
        if policy != ACCRUE_ESTIMATE:
            continue
        period_end = payload_date(version.parameters, "usage_period_end_date")
        if period_end is None or period_end > at:
            continue
        stated = any(
            event.event_type == "USAGE_REPORTED"
            and event.contract_key == contract
            and (before is None or event.order_key < before.order_key)
            and event.payload.get("is_royalty_statement") in (True, "true")
            and payload_date(event.payload, "usage_period_end") == period_end
            for event in measure_events
        )
        if stated:
            continue
        if version.constrained_amount is not None:
            member, raw = "constrained_amount", version.constrained_amount
        elif version.expected_total_amount is not None:
            member, raw = "expected_total_amount", version.expected_total_amount
        else:
            continue
        found.append(Accrual(version, member, Fraction(raw)))
    return tuple(found)


def _quota(ctx: BookContext, exact: Fraction) -> Quota1:
    return Quota1(exact, round_half_up(exact, ctx.currencies[ctx.txn_currency].minor_unit))


def out_of_scope_lines(st: PobState) -> tuple[PobDraft, ...]:
    """The routed-out lines whose ``out_of_scope_amount`` S04-R-03 sums, by subject key.

    Two kinds (S03-R-11): lines excluded from obligations by their scope flag, and ``LEASE_842``
    allocation targets, which stay obligations with ``routed_out = true`` (PT-09). A lease target
    keeps its stated price in fixed consideration and also reports its amount in the memo member,
    as the ALC-CHK-118 and REC-S5-EX62-CASEB keys state (L3-1-Q-44).
    """
    leases = (obligation for obligation in st.obligations if obligation.routed_out)
    return tuple(sorted((*st.routed_out, *leases), key=lambda draft: draft.subject_key))


def price(
    ctx: BookContext,
    st: PobState,
    at: date,
    before: EventView | None,
    tb: TraceBuilder | None,
    suffix: str,
    *,
    rates: Mapping[str, Fraction] | None = None,
    added: Sequence[tuple[SourceRef, Fraction]] = (),
) -> TpBuildUp:
    """The build-up at ``at`` before ``before`` (§4.2); nodes take ``suffix`` on their measure.

    ``rates`` maps returnable obligations to r = x_exact ÷ Q of the segment in force; an obligation
    without a rate contributes nothing to ``expected_returns`` (the pending inception build-up of
    ``run``, completed by stage 05).

    ``added`` is the consideration that boundary events before the position add to the booking
    lines, one source reference and amount per addition (S06-R-07, S06-R-23). It enters ``fixed``,
    and the fixed node cites each reference with its value (CV-53; L5-3-Q-17).
    """
    minor_unit = ctx.currencies[ctx.txn_currency].minor_unit
    scale: int = 10**minor_unit
    fixed_lines = list(specialist.fixed_lines(st))
    fixed = sum((ob.stated_price for ob in fixed_lines), ZERO) + sum(
        (amount for _, amount in added), ZERO
    )
    routed = [
        (
            draft,
            draft.stated_price if draft.out_of_scope_amount is None else draft.out_of_scope_amount,
        )
        for draft in out_of_scope_lines(st)
    ]
    out_of_scope = sum((amount for _, amount in routed), ZERO)
    measured = vc.elements(ctx, st, at, before)
    usage = realised(ctx, st, at, before)
    accrued = royalty_accruals(ctx, st, at, before)
    implicit = concessions.measure(ctx, st, at, before, fixed_lines)
    returned = returns.measure(ctx, st, returns.returnable(ctx, st), at, before, rates or {})
    financed = financing.measure(ctx, st, at, before, fixed_lines)
    payable = customer_consideration.reduction(ctx, st, at, before)
    received = noncash.measure(ctx, st, at, before)
    collected = taxes.excluded(ctx, st, at, before)
    vc_constrained = (
        sum((e.constrained for e in measured), ZERO)
        + sum((r.amount for r in usage), ZERO)
        + sum((a.amount for a in accrued), ZERO)
        + sum((c.exact for c in implicit), ZERO)
    )
    vc_excluded = sum((e.unconstrained - e.constrained for e in measured), ZERO)
    expected_returns = sum((Fraction(m.posted, scale) for m in returned), ZERO)
    consideration_payable = payable.exact
    adjustment = financed.exact
    noncash_amount = received.exact
    sales_tax = sum((t.amount for t in collected), ZERO)
    total = (
        fixed
        + vc_constrained
        + expected_returns
        + consideration_payable
        + adjustment
        + noncash_amount
    )
    basis = total - expected_returns - consideration_payable
    views = [
        VcElementView(
            estimate_key=e.version.estimate_key,
            element_code=e.version.element_code,
            version_key=e.version.version_key,
            amount=_quota(ctx, e.constrained),
            allocation_target=e.version.allocation_target,
            obligation_keys=targets(e),
        )
        for e in measured
    ]
    views.extend(
        VcElementView(
            estimate_key=c.version.estimate_key,
            element_code=c.version.element_code,
            version_key=c.version.version_key,
            amount=Quota1(c.exact, c.posted),
            allocation_target=c.version.allocation_target,
            obligation_keys=tuple(ob.obligation_key for ob in c.affected),
        )
        for c in implicit
    )
    buildup = TpBuildUp(
        at=at,
        before_event_key=None if before is None else before.event_key,
        fixed=_quota(ctx, fixed),
        vc_constrained=_quota(ctx, vc_constrained),
        vc_excluded=_quota(ctx, vc_excluded),
        expected_returns=_quota(ctx, expected_returns),
        consideration_payable=_quota(ctx, consideration_payable),
        financing_adjustment=_quota(ctx, adjustment),
        noncash=_quota(ctx, noncash_amount),
        sales_tax_excluded=_quota(ctx, sales_tax),
        out_of_scope=_quota(ctx, out_of_scope),
        total=_quota(ctx, total),
        allocation_basis=_quota(ctx, basis),
        elements=tuple(sorted(views, key=lambda view: view.estimate_key)),
        realised=_quota(ctx, sum((r.amount for r in usage), ZERO)),
    )
    members = (
        buildup.fixed,
        buildup.vc_constrained,
        buildup.expected_returns,
        buildup.consideration_payable,
        buildup.financing_adjustment,
        buildup.noncash,
    )
    if buildup.total.exact != sum((member.exact for member in members), ZERO):
        raise _invariant(st, "S04-INV-01", "the transaction price is not the sum of its members")
    identity = (
        buildup.total.exact - buildup.expected_returns.exact - buildup.consideration_payable.exact
    )
    if buildup.allocation_basis.exact != identity:
        raise _invariant(st, "S04-INV-03", "the allocation basis is not total less the memos")
    if tb is not None:
        parts = _trace(
            ctx,
            st,
            tb,
            buildup,
            fixed_lines,
            routed,
            measured,
            usage,
            suffix,
            added=added,
            accrued=accrued,
        )
        reductions = _Reductions(implicit, returned, financed, payable, received, collected)
        _trace_reductions(ctx, st, tb, buildup, parts, reductions, suffix)
    return buildup


def targets(element: vc.Element) -> tuple[str, ...]:
    """The obligation keys an element names (allocation targets for stage 05)."""
    version = element.version
    if version.target_obligation_keys:
        return version.target_obligation_keys
    return () if version.obligation_key is None else (version.obligation_key,)


def _invariant(st: PobState, invariant: str, message: str) -> EngineError:
    return EngineError(
        "ENGINE_INVARIANT_VIOLATED",
        message,
        subject_key=st.group_key,
        detail={"invariant": invariant},
    )


def _node(
    ctx: BookContext,
    tb: TraceBuilder,
    measure: str,
    subject_key: str,
    quota: Quota1,
    formula: str,
    inputs: Sequence[str | SourceRef],
    params: dict[str, str],
) -> str:
    return tb.node(
        measure=measure,
        subject_key=subject_key,
        period_key=None,
        value=quota.posted,
        currency=ctx.txn_currency,
        minor_unit=ctx.currencies[ctx.txn_currency].minor_unit,
        formula_id=formula,
        inputs=inputs,
        params=params,
        exact=quota.exact,
        narrative_key=formula.rsplit(".v", 1)[0],
    )


def _signed(parts: Sequence[tuple[str, str]]) -> tuple[list[str | SourceRef], dict[str, str]]:
    inputs: list[str | SourceRef] = [node_id for node_id, _ in parts]
    return inputs, {"signs": ",".join(sign for _, sign in parts)}


def _trace(
    ctx: BookContext,
    st: PobState,
    tb: TraceBuilder,
    buildup: TpBuildUp,
    fixed_lines: Sequence[PobDraft],
    routed: Sequence[tuple[PobDraft, Fraction]],
    measured: Sequence[vc.Element],
    usage: Sequence[Realised],
    suffix: str,
    *,
    added: Sequence[tuple[SourceRef, Fraction]] = (),
    accrued: Sequence[Accrual] = (),
) -> list[tuple[str, str]]:
    """Element, realised, fixed and out-of-scope nodes (§4.4; CV-50, CV-51); the signed inputs of
    ``vc_constrained_amount`` so far."""
    group = encode_key(st.group_key)
    element_ids = [vc.emit(ctx, tb, element, suffix) for element in measured]
    usage_ids = [
        _node(
            ctx,
            tb,
            f"realised_royalty_accrual{suffix}",
            accrual.version.estimate_key,
            _quota(ctx, accrual.amount),
            REALISED,
            [
                SourceRef(
                    "estimate_version",
                    accrual.version.version_key,
                    {"member": accrual.member, "value": format_exact(accrual.amount)},
                )
            ],
            {"guarantee": format_exact(ZERO)},
        )
        for accrual in accrued
    ]
    for item in usage:
        inputs: list[str | SourceRef] = [
            SourceRef("contract_event", event.event_key, {"value": format_exact(rated)})
            for event, rated in item.reported
        ]
        inputs.extend(
            SourceRef(
                "estimate_version",
                version.version_key,
                {"member": member, "value": format_exact(amount)},
            )
            for version, member, amount in item.accrued
        )
        params = {"guarantee": format_exact(item.guarantee)}
        usage_ids.append(
            _node(
                ctx,
                tb,
                f"realised_usage{suffix}",
                item.obligation.subject_key,
                _quota(ctx, item.amount),
                REALISED,
                inputs,
                params,
            )
        )
    fixed_inputs: list[str | SourceRef] = [f"stated_price:{ob.subject_key}:-" for ob in fixed_lines]
    fixed_inputs.extend(ref for ref, _ in added)
    _node(ctx, tb, f"fixed_consideration{suffix}", group, buildup.fixed, FIXED, fixed_inputs, {})
    parts = [pair for u, k in element_ids for pair in ((u, "+"), (k, "-"))]
    inputs, params = _signed(parts)
    _node(
        ctx, tb, f"vc_excluded_amount{suffix}", group, buildup.vc_excluded, BUILDUP, inputs, params
    )
    booking = {
        event.contract_key: event.event_key
        for event in st.identified.canonical.events
        if event.event_type == "CONTRACT_BOOKED"
    }
    routed_inputs: list[str | SourceRef] = [
        SourceRef(
            "contract_event",
            booking.get(draft.contract_key, draft.contract_key),
            {"line": draft.obligation_key, "value": format_exact(amount)},
        )
        for draft, amount in routed
    ]
    signs = {"signs": ",".join("+" for _ in routed)}
    _node(
        ctx,
        tb,
        f"out_of_scope_amount{suffix}",
        group,
        buildup.out_of_scope,
        BUILDUP,
        routed_inputs,
        signs,
    )
    return [(k, "+") for _, k in element_ids] + [(u, "+") for u in usage_ids]


@dataclass(frozen=True, slots=True)
class _Reductions:
    """The measured members that ``_trace_reductions`` emits."""

    implicit: Sequence[concessions.Concession]
    returned: Sequence[returns.Measured]
    financed: financing.Adjustment
    payable: customer_consideration.Reduction
    received: noncash.Noncash
    collected: Sequence[taxes.Tax]


def _trace_reductions(
    ctx: BookContext,
    st: PobState,
    tb: TraceBuilder,
    buildup: TpBuildUp,
    constrained: Sequence[tuple[str, str]],
    reductions: _Reductions,
    suffix: str,
) -> None:
    """Concession, memo, financing, consideration payable, noncash, aggregate and allocation-basis
    nodes (§4.4; S04-R-08 to S04-R-18, S04-R-20)."""
    group = encode_key(st.group_key)
    parts = [
        *constrained,
        *((concessions.emit(ctx, tb, item, suffix), "+") for item in reductions.implicit),
    ]
    inputs, params = _signed(parts)
    constrained_id = _node(
        ctx,
        tb,
        f"vc_constrained_amount{suffix}",
        group,
        buildup.vc_constrained,
        BUILDUP,
        inputs,
        params,
    )
    returns_id = returns.emit(
        ctx,
        tb,
        f"expected_returns_amount{suffix}",
        group,
        buildup.expected_returns,
        reductions.returned,
    )
    taxes.emit(
        ctx,
        tb,
        f"sales_tax_excluded_amount{suffix}",
        group,
        buildup.sales_tax_excluded,
        reductions.collected,
    )
    payable_id = customer_consideration.emit(
        ctx,
        tb,
        f"consideration_payable_amount{suffix}",
        group,
        buildup.consideration_payable,
        reductions.payable,
    )
    financing_id = financing.emit(
        ctx,
        tb,
        f"financing_adjustment_amount{suffix}",
        group,
        buildup.financing_adjustment,
        reductions.financed,
        suffix,
    )
    noncash_id = noncash.emit(
        ctx,
        tb,
        f"noncash_consideration_amount{suffix}",
        group,
        buildup.noncash,
        reductions.received,
    )
    fixed_id = f"fixed_consideration{suffix}:{group}:-"
    parts = [
        (fixed_id, "+"),
        (constrained_id, "+"),
        (returns_id, "+"),
        (payable_id, "+"),
        (financing_id, "+"),
        (noncash_id, "+"),
    ]
    inputs, params = _signed(parts)
    total_id = _node(
        ctx, tb, f"transaction_price{suffix}", group, buildup.total, BUILDUP, inputs, params
    )
    parts = [
        (total_id, "+"),
        (returns_id, "-"),
        (payable_id, "-"),
    ]
    inputs, params = _signed(parts)
    _node(
        ctx,
        tb,
        f"tp_allocation_basis{suffix}",
        group,
        buildup.allocation_basis,
        BUILDUP,
        inputs,
        params,
    )
