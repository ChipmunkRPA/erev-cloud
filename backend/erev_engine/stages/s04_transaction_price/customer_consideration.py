"""Stage 04 consideration payable to a customer: the promise memo, the ordinary release and the
incentive asset.

ENGINE_SPEC S04-R-14 to S04-R-16; §4.4 S04-INV-04 (released incentive), trace nodes
``consideration_payable:<contract>@<entity>:<period>``,
``incentive_release_ordinary_cum:<contract>@<entity>:<period>`` and
``customer_incentive_asset:<contract>@<entity>:<period>``; formulas ``tp.cpc_reduction.v1`` and
``tp.cpc_release.v1``; POLICIES POL-049, JET-14 (CHK-133); 04 API-S-ConsiderationPayable and the
T-CON-13 parameters of ``EXPECTED_PURCHASES``. The share-based reduction of S04-R-17 (PT-10,
CHK-120) is driven by posted related revenue, which exists only after stage 09, so stage 10
measures it and composes ``incentive_release_cum`` (ENGINE_SPEC_B S10-R-26; D-91 C606-03); stage
04 keeps the ``SHARE_BASED_CONSIDERATION`` pins in the series start so the EMOD-22 series opens at
the earlier of the promise date and the first pin. Private to stage 04. Standard library only
(DG-ARC-02).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from fractions import Fraction
from typing import Final

from erev_engine.bundle import EstimateVersionInput, PayableInput
from erev_engine.errors import EngineError
from erev_engine.money import format_exact, round_half_up, to_fraction
from erev_engine.stages.s01_canonicalize import (
    contract_entity_subject_key,
    contract_subject_key,
    payload_date,
    payload_fraction,
    payload_text,
)
from erev_engine.stages.s03_pob_builder import PobState
from erev_engine.stages.s04_transaction_price import specialist
from erev_engine.stages.state import BookContext, EventView, Quota1, Target
from erev_engine.trace import SourceRef, TraceBuilder

__all__ = [
    "ASSET",
    "KIND_SHARE_BASED",
    "ORDINARY_RELEASE",
    "PAYABLE",
    "Promise",
    "Reduction",
    "Release",
    "emit",
    "promises",
    "reduction",
    "targets",
]

REDUCTION_FORMULA: Final = "tp.cpc_reduction.v1"
RELEASE_FORMULA: Final = "tp.cpc_release.v1"
BASIS: Final = "cpc.incentive_asset_release_basis"  # POL-049
COMMITTED_PURCHASES: Final = "COMMITTED_PURCHASES"
KIND_PURCHASES: Final = "EXPECTED_PURCHASES"
KIND_SHARE_BASED: Final = "SHARE_BASED_CONSIDERATION"
MEMBER: Final = "consideration_payable"
ORDINARY_RELEASE: Final = "incentive_release_ordinary_cum"  # S04-R-16 (D-91)
ASSET: Final = "customer_incentive_asset"
PAYABLE: Final = "consideration_payable"
ZERO: Final = Fraction(0)


@dataclass(frozen=True, slots=True)
class Promise:
    """One payable promise of the list in force (API-S-ConsiderationPayable) with R (S04-R-14)."""

    contract_key: str
    index: int  # position in the list in force
    amount: Fraction
    promise_date: date
    related_obligation_keys: tuple[str, ...]  # empty = every obligation
    distinct_good_fair_value: Fraction | None  # None: no distinct good, or not estimable
    committed_purchases: Fraction | None  # POL-049 COMMITTED_PURCHASES release base
    share_based: bool  # measured by a SHARE_BASED_CONSIDERATION element (PT-10)
    reduction: Fraction  # R
    source_event_key: str | None  # the booking or amendment carrying the list


@dataclass(frozen=True, slots=True)
class Reduction:
    """The consideration-payable memo at a position (S04-R-14)."""

    promises: tuple[Promise, ...]  # dated on or before the position
    exact: Fraction  # −Σ R


@dataclass(frozen=True, slots=True)
class Release:
    """The release of one non-share-based promise at a date (S04-R-15, S04-R-16)."""

    promise: Promise
    released: Fraction  # exact release, at most R (S04-INV-04)
    rate: Fraction | None  # ρ′ in force; None after revenue, for R = 0 or before any base
    invoiced: Fraction  # related purchases invoiced from the promise date
    after_revenue: bool  # released in full at the promise date (606-10-32-27)


def promises(
    st: PobState, contract_key: str, at: date, before: EventView | None
) -> tuple[Promise, ...]:
    """Every promise of the list in force at the position, whatever its promise date (S01-R-20).

    The list is the ``consideration_payable`` member of the latest booking or amendment payload
    carrying it, else the header projection. A malformed item raises ``ValueError`` (CV-45).
    """
    value, source = specialist.in_force(st, contract_key, MEMBER, at, before)
    items: Sequence[object]
    if value is None:
        items = st.identified.canonical.contracts[contract_key].header.consideration_payable
    elif isinstance(value, list | tuple):
        items = value
    else:
        raise ValueError(f"{contract_key}: consideration_payable is not a list (CV-45)")
    return tuple(_promise(contract_key, index, item, source) for index, item in enumerate(items))


def reduction(
    ctx: BookContext,
    st: PobState,
    at: date,
    before: EventView | None,
    *,
    contract_key: str | None = None,
) -> Reduction:
    """S04-R-14: ``consideration_payable`` = −Σ R of the promises dated on or before ``at``, of
    every member contract or of ``contract_key``. R is the amount without a distinct good (or with
    a fair value that is not estimable), else max(0, amount − fair value)."""
    found: list[Promise] = []
    for key in st.identified.member_contract_keys:
        if contract_key is not None and key != contract_key:
            continue
        found.extend(p for p in promises(st, key, at, before) if p.promise_date <= at)
    return Reduction(tuple(found), -sum((p.reduction for p in found), ZERO))


def emit(
    ctx: BookContext,
    tb: TraceBuilder,
    measure_name: str,
    subject_key: str,
    quota: Quota1,
    item: Reduction,
) -> str:
    """Node ``consideration_payable_amount`` (§4.4; ``tp.cpc_reduction.v1``); its id."""
    listed = item.promises
    inputs: list[str | SourceRef] = [_source(p, p.reduction) for p in listed]
    params = {
        "amounts": ",".join(format_exact(p.amount) for p in listed),
        "distinct_good_fair_values": ",".join(
            "-" if p.distinct_good_fair_value is None else format_exact(p.distinct_good_fair_value)
            for p in listed
        ),
        "promise_dates": ",".join(p.promise_date.isoformat() for p in listed),
        "share_based": ",".join("true" if p.share_based else "false" for p in listed),
        "signs": ",".join("-" for _ in listed),
    }
    return tb.node(
        measure=measure_name,
        subject_key=subject_key,
        period_key=None,
        value=quota.posted,
        currency=ctx.txn_currency,
        minor_unit=ctx.currencies[ctx.txn_currency].minor_unit,
        formula_id=REDUCTION_FORMULA,
        inputs=inputs,
        params=params,
        exact=quota.exact,
        narrative_key=REDUCTION_FORMULA.rsplit(".v", 1)[0],
    )


def targets(ctx: BookContext, st: PobState, tb: TraceBuilder) -> tuple[Target, ...]:
    """EMOD-22 targets per contract and period end of the contracting entity (JET-14 owner), from
    the earliest promise or share-based pin through the horizon.

    - ``consideration_payable``: Σ R of the non-share-based promises dated on or before t
      (``tp.cpc_reduction.v1``).
    - ``incentive_release_ordinary_cum``: Σ release of those promises (S04-R-15, S04-R-16;
      ``tp.cpc_release.v1``), the JET-14 release part on its own.
    - ``customer_incentive_asset``: posted payable − posted ordinary release, the signed sum of the
      two nodes (S04-R-16 rev 1.6; ENGINE_SPEC_B S14-R-11: no independent rounding of the asset).

    The share-based reduction (S04-R-17) and the composed ``incentive_release_cum`` are stage 10
    measures driven by posted related revenue (ENGINE_SPEC_B S10-R-26; D-91). A contract with only a
    share-based element (no promise) still opens the series at the element's pins.
    """
    minor_unit = ctx.currencies[ctx.txn_currency].minor_unit
    end = specialist.stream_end(ctx, st)
    pins = st.identified.canonical.estimates
    found: list[Target] = []
    for contract_key in st.identified.member_contract_keys:
        header = st.identified.canonical.contracts[contract_key].header
        entity = header.contracting_entity_code
        listed = promises(st, contract_key, end, None)
        elements = _share_based_keys(st, contract_key)
        if not listed and not elements:
            continue
        subject = contract_entity_subject_key(contract_key, entity)
        basis = str(ctx.policies.value(BASIS, contract=contract_key, entity=entity))
        starts = [p.promise_date for p in listed]
        starts.extend(
            applied.version.effective_date for key in elements for applied in pins.pins[key]
        )
        for period in specialist.periods(ctx, entity, min(starts)):
            t = period.end_date
            ordinary = [p for p in listed if p.promise_date <= t and not p.share_based]
            releases = [_release(ctx, st, p, basis, t) for p in ordinary]
            for item in releases:
                if not ZERO <= item.released <= item.promise.reduction:
                    raise EngineError(
                        "ENGINE_INVARIANT_VIOLATED",
                        "the released incentive lies outside [0, R]",
                        subject_key=subject,
                        detail={"invariant": "S04-INV-04", "promise": str(item.promise.index)},
                    )
            payable = sum((p.reduction for p in ordinary), ZERO)
            released = sum((r.released for r in releases), ZERO)
            payable_node = _emit(
                ctx,
                tb,
                found,
                entity,
                subject,
                period.period_key,
                PAYABLE,
                payable,
                REDUCTION_FORMULA,
                [_source(p, p.reduction) for p in ordinary],
                {"signs": ",".join("+" for _ in ordinary)},
            )
            ordinary_node = _emit(
                ctx,
                tb,
                found,
                entity,
                subject,
                period.period_key,
                ORDINARY_RELEASE,
                released,
                RELEASE_FORMULA,
                [_source(r.promise, r.released) for r in releases],
                {
                    "after_revenue": ",".join(
                        "true" if r.after_revenue else "false" for r in releases
                    ),
                    "basis": basis,
                    "invoiced": ",".join(format_exact(r.invoiced) for r in releases),
                    "rates": ",".join(
                        "-" if r.rate is None else format_exact(r.rate) for r in releases
                    ),
                },
            )
            # The asset is the identity posted payable − posted ordinary release (D-91 (5)).
            asset = Fraction(found[-2].value - found[-1].value, 10**minor_unit)
            _emit(
                ctx,
                tb,
                found,
                entity,
                subject,
                period.period_key,
                ASSET,
                asset,
                RELEASE_FORMULA,
                [payable_node, ordinary_node],
                {"signs": "+,-"},
            )
    return tuple(found)


def _emit(
    ctx: BookContext,
    tb: TraceBuilder,
    found: list[Target],
    entity: str,
    subject: str,
    period_key: str,
    measure_name: str,
    exact: Fraction,
    formula: str,
    inputs: Sequence[str | SourceRef],
    params: Mapping[str, str],
) -> str:
    """Emit one posted EMOD-22 node and append its target; the node id."""
    minor_unit = ctx.currencies[ctx.txn_currency].minor_unit
    posted = round_half_up(exact, minor_unit)
    node_id = tb.node(
        measure=measure_name,
        subject_key=subject,
        period_key=period_key,
        value=posted,
        currency=ctx.txn_currency,
        minor_unit=minor_unit,
        formula_id=formula,
        inputs=list(inputs),
        params=params,
        exact=exact,
        narrative_key=formula.rsplit(".v", 1)[0],
    )
    found.append(
        Target(
            book_code=ctx.book_code,
            entity=entity,
            subject_key=subject,
            measure=measure_name,
            period_key=period_key,
            cause=None,
            value=posted,
            exact=exact,
            node_id=node_id,
        )
    )
    return node_id


def _promise(contract_key: str, index: int, item: object, source: str | None) -> Promise:
    if isinstance(item, PayableInput):
        amount = to_fraction(item.amount)
        on = item.promise_date
        keys = tuple(item.related_obligation_keys)
        fair = (
            None
            if item.distinct_good_fair_value is None
            else to_fraction(item.distinct_good_fair_value)
        )
        committed = (
            None if item.committed_purchases is None else to_fraction(item.committed_purchases)
        )
        share_based = item.share_based
    elif isinstance(item, Mapping):
        found_amount = payload_fraction(item, "amount")
        found_on = payload_date(item, "promise_date")
        if found_amount is None or found_on is None:
            raise ValueError(f"{contract_key}: a payable promise needs amount and promise_date")
        amount, on = found_amount, found_on
        raw = item.get("related_obligation_keys") or ()
        if not isinstance(raw, list | tuple) or not all(isinstance(k, str) for k in raw):
            raise ValueError(f"{contract_key}: related_obligation_keys is not a list of keys")
        keys = tuple(str(k) for k in raw)
        fair = payload_fraction(item, "distinct_good_fair_value")
        committed = payload_fraction(item, "committed_purchases")
        share_based = item.get("share_based") in (True, "true")
    else:
        raise ValueError(f"{contract_key}: a payable promise is not an object (CV-45)")
    reduced = amount if fair is None else max(ZERO, amount - fair)
    return Promise(
        contract_key, index, amount, on, keys, fair, committed, share_based, reduced, source
    )


def _source(promise: Promise, value: Fraction) -> SourceRef:
    detail = {"line": str(promise.index), "value": format_exact(value)}
    return SourceRef("contract_event", promise.source_event_key or promise.contract_key, detail)


def _release(ctx: BookContext, st: PobState, promise: Promise, basis: str, t: date) -> Release:
    """S04-R-15 and S04-R-16 for a promise dated on or before ``t``.

    A promise dated after a related transfer (a ``DELIVERY_RECORDED`` of a related obligation
    effective before the promise date) is released in full at the promise date. Otherwise the
    release is min(R, released at the latest rate change + ρ′ × related purchases invoiced since),
    with ρ = R ÷ committed purchases (``COMMITTED_PURCHASES``) or R ÷ the ``expected_total_amount``
    of the contract's ``EXPECTED_PURCHASES`` pin; a later pin changes the rate prospectively:
    ρ′ = (R − released) ÷ (purchases′ − invoiced to date), and releases the remainder when no
    purchases remain. An invoice without a release base raises ``NON_FINITE_AMOUNT`` (CV-32).
    """
    total = promise.reduction
    if _after_revenue(st, promise):
        return Release(promise, total, None, ZERO, True)
    bills = specialist.invoices(
        st, promise.contract_key, promise.related_obligation_keys, promise.promise_date, t
    )
    invoiced = sum((amount for _, amount in bills), ZERO)
    if total == 0:
        return Release(promise, ZERO, None, invoiced, False)
    if basis == COMMITTED_PURCHASES:
        purchases = promise.committed_purchases
        if purchases is None or purchases <= 0:
            if invoiced == 0:
                return Release(promise, ZERO, None, ZERO, False)
            raise _non_finite(promise.contract_key)
        rate = total / purchases
        return Release(promise, min(total, rate * invoiced), rate, invoiced, False)
    key = _purchases_key(st, promise.contract_key)
    pins = st.identified.canonical.estimates
    current: Fraction | None = None
    initial = None if key is None else pins.pin(key, promise.promise_date)
    if initial is not None:
        current = _base_rate(total, ZERO, _expected(initial), ZERO)
    steps: list[tuple[tuple[date, int, str], EstimateVersionInput | None, Fraction]] = []
    for applied in () if key is None else pins.pins[key]:
        version = applied.version
        if promise.promise_date < version.effective_date <= t:
            order = applied.event_order_key
            steps.append(((version.effective_date, order[1], order[2]), version, ZERO))
    steps.extend((event.order_key, None, amount) for event, amount in bills)
    released = base = since = to_date = ZERO
    for _, pinned, amount in sorted(steps, key=lambda step: step[0]):
        if pinned is not None:
            base, since = released, ZERO
            current = _base_rate(total, released, _expected(pinned), to_date)
            if current is None:
                released = base = total
                current = ZERO
            continue
        if current is None:
            raise _non_finite(promise.contract_key)
        to_date += amount
        since += amount
        released = min(total, base + current * since)
    return Release(promise, released, current, invoiced, False)


def _base_rate(
    total: Fraction, released: Fraction, purchases: Fraction, invoiced: Fraction
) -> Fraction | None:
    """ρ′ = (R − released) ÷ (purchases − invoiced to date); None when no purchases remain."""
    remaining = purchases - invoiced
    return None if remaining <= 0 else (total - released) / remaining


def _expected(version: EstimateVersionInput) -> Fraction:
    if version.expected_total_amount is None:
        raise ValueError(f"{version.version_key}: EXPECTED_PURCHASES needs expected_total_amount")
    return to_fraction(version.expected_total_amount)


def _after_revenue(st: PobState, promise: Promise) -> bool:
    keys = promise.related_obligation_keys
    for event in st.identified.canonical.events:
        if event.event_type != "DELIVERY_RECORDED" or event.contract_key != promise.contract_key:
            continue
        if event.effective_date >= promise.promise_date:
            continue
        if not keys or payload_text(event.payload, "obligation_key") in keys:
            return True
    return False


def _purchases_key(st: PobState, contract_key: str) -> str | None:
    """The first ``EXPECTED_PURCHASES`` element of the contract (L2-2-Q-24)."""
    keys = _element_keys(st, contract_key, KIND_PURCHASES)
    return keys[0] if keys else None


def _share_based_keys(st: PobState, contract_key: str) -> tuple[str, ...]:
    """The contract's ``SHARE_BASED_CONSIDERATION`` elements: they open the EMOD-22 series (the
    measurement itself is stage 10's, ENGINE_SPEC_B S10-R-26)."""
    return _element_keys(st, contract_key, KIND_SHARE_BASED)


def _element_keys(st: PobState, contract_key: str, kind: str) -> tuple[str, ...]:
    pins = st.identified.canonical.estimates.pins
    head = contract_subject_key(contract_key)
    return tuple(
        key
        for key in sorted(pins)
        if pins[key]
        and pins[key][-1].version.estimate_kind == kind
        and key.split("/", 1)[0] == head
    )


def _non_finite(subject_key: str) -> EngineError:
    return EngineError(
        "NON_FINITE_AMOUNT",
        "the consideration-payable release has no purchases base",
        subject_key=subject_key,
        formula_id=RELEASE_FORMULA,
        detail={"formula_id": RELEASE_FORMULA, "subject_key": subject_key},
    )
