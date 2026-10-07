"""Stage 04 unconstrained, credit-adjusted transaction price view.

ENGINE_SPEC S04-R-21 (EMOD-17); ENGINE_SPEC_B §11.2.5, S11-R-11a; 605-35-25-46A, 340-40-35-4.
Stage 04 measurement, also bound by the book fold. Standard library only (DG-ARC-02).
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from fractions import Fraction
from typing import Final

from erev_engine.money import round_half_up
from erev_engine.stages.s01_canonicalize import payload_fraction, payload_text
from erev_engine.stages.s03_pob_builder import PobState
from erev_engine.stages.s04_transaction_price import (
    buildup,
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

__all__ = ["UnconstrainedView", "measure", "views"]

COLLECTIBILITY: Final = "COLLECTIBILITY_ASSESSED"
ZERO: Final = Fraction(0)


class UnconstrainedView(tuple[TpBuildUp, ...]):
    """``tp_unconstrained[contract]`` (S04-R-21): build-ups ascending by date (a ``TpView``).

    One build-up at the group inception and one at each ``COLLECTIBILITY_ASSESSED`` of the book
    that carries ``expected_collectible_amount``. :meth:`at` selects the latest build-up measured
    on or before ``d`` (L2-2-Q-10).
    """

    __slots__ = ()

    def at(self, d: date) -> TpBuildUp:
        """The latest build-up with ``at`` on or before ``d``; the first before any of them."""
        if not self:
            raise ValueError("the unconstrained view holds no build-up")
        found = self[0]
        for build in self:
            if build.at <= d:
                found = build
        return found


def views(
    ctx: BookContext,
    st: PobState,
    inception_before: EventView | None,
    rates: Mapping[str, Fraction],
) -> dict[str, UnconstrainedView]:
    """The unconstrained view of every member contract, by contract key (S04-R-21)."""
    found: dict[str, UnconstrainedView] = {}
    for contract_key in st.identified.member_contract_keys:
        positions: list[tuple[date, EventView | None]] = [(st.inception_date, inception_before)]
        for event in st.identified.canonical.boundary_events:
            if event.event_type != COLLECTIBILITY or event.contract_key != contract_key:
                continue
            if payload_text(event.payload, "book") != ctx.book_code:
                continue
            if payload_fraction(event.payload, "expected_collectible_amount") is None:
                continue
            if event.effective_date > positions[-1][0]:
                positions.append((event.effective_date, None))
        found[contract_key] = UnconstrainedView(
            measure(ctx, st, contract_key, at, before, rates) for at, before in positions
        )
    return found


def measure(
    ctx: BookContext,
    st: PobState,
    contract_key: str,
    at: date,
    before: EventView | None,
    rates: Mapping[str, Fraction],
    added: Fraction = ZERO,
) -> TpBuildUp:
    """``tp_unconstrained[contract].at(d)``: fixed + Σ U + realised + concession + financing
    adjustment + noncash − Σ R + expected-returns memo, replaced by the latest
    ``COLLECTIBILITY_ASSESSED.expected_collectible_amount`` of the book when lower.

    ``added`` is the owning contract's approved boundary consideration, included in fixed
    before the collection cap. The book fold supplies it for dated loss/impairment measurements.

    ``vc_constrained`` holds the unconstrained VC with realised amounts and the concession, and
    ``vc_excluded`` is 0.
    """
    minor_unit = ctx.currencies[ctx.txn_currency].minor_unit

    def quota(exact: Fraction) -> Quota1:
        return Quota1(exact, round_half_up(exact, minor_unit))

    scale: int = 10**minor_unit
    fixed_lines = specialist.fixed_lines(st, contract_key)
    fixed = sum((ob.stated_price for ob in fixed_lines), ZERO) + added
    elements = [e for e in vc.elements(ctx, st, at, before) if e.contract_key == contract_key]
    unconstrained_vc = sum((e.unconstrained for e in elements), ZERO)
    realised = sum(
        (
            item.amount
            for item in buildup.realised(ctx, st, at, before)
            if item.obligation.contract_key == contract_key
        ),
        ZERO,
    )
    concession = sum((c.exact for c in concessions.measure(ctx, st, at, before, fixed_lines)), ZERO)
    items = [i for i in returns.returnable(ctx, st) if i.obligation.contract_key == contract_key]
    memo = sum(
        (Fraction(m.posted, scale) for m in returns.measure(ctx, st, items, at, before, rates)),
        ZERO,
    )
    adjustment = financing.measure(ctx, st, at, before, fixed_lines).exact
    payable = customer_consideration.reduction(ctx, st, at, before, contract_key=contract_key).exact
    received = noncash.measure(ctx, st, at, before, contract_key=contract_key).exact
    total = (
        fixed + unconstrained_vc + realised + concession + adjustment + received + payable + memo
    )
    collectible = _collectible(ctx, st, contract_key, at, before)
    if collectible is not None and collectible < total:
        total = collectible
    tax = sum(
        (t.amount for t in taxes.excluded(ctx, st, at, before, contract_key=contract_key)), ZERO
    )
    out_of_scope = sum(
        (
            draft.stated_price if draft.out_of_scope_amount is None else draft.out_of_scope_amount
            for draft in buildup.out_of_scope_lines(st)
            if draft.contract_key == contract_key
        ),
        ZERO,
    )
    return TpBuildUp(
        at=at,
        before_event_key=None if before is None else before.event_key,
        fixed=quota(fixed),
        vc_constrained=quota(unconstrained_vc + realised + concession),
        vc_excluded=quota(ZERO),
        expected_returns=quota(memo),
        consideration_payable=quota(payable),
        financing_adjustment=quota(adjustment),
        noncash=quota(received),
        sales_tax_excluded=quota(tax),
        out_of_scope=quota(out_of_scope),
        total=quota(total),
        allocation_basis=quota(total - memo - payable),
        elements=tuple(
            VcElementView(
                estimate_key=e.version.estimate_key,
                element_code=e.version.element_code,
                version_key=e.version.version_key,
                amount=quota(e.unconstrained),
                allocation_target=e.version.allocation_target,
                obligation_keys=buildup.targets(e),
            )
            for e in elements
        ),
    )


def _collectible(
    ctx: BookContext, st: PobState, contract_key: str, at: date, before: EventView | None
) -> Fraction | None:
    """The latest ``expected_collectible_amount`` of the book's assessments to the position."""
    found: Fraction | None = None
    for event in st.identified.canonical.boundary_events:
        if before is not None and event.order_key >= before.order_key:
            break
        if event.event_type != COLLECTIBILITY or event.contract_key != contract_key:
            continue
        if event.effective_date > at or payload_text(event.payload, "book") != ctx.book_code:
            continue
        amount = payload_fraction(event.payload, "expected_collectible_amount")
        if amount is not None:
            found = amount
    return found
