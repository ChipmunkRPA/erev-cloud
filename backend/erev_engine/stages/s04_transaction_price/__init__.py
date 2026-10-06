"""Stage 04 transaction price: build-up, variable consideration, returns, concessions, financing,
consideration payable, noncash consideration, taxes and the specialist targets.

ENGINE_SPEC §4.1 and §4.2; §4.3 S04-R-01 to S04-R-21 (S04-R-12a); §4.4 S04-INV-01 to S04-INV-04,
findings ``RETURN_ESTIMATE_MISSING``, ``SFC_REVIEW_REQUIRED``, ``SFC_RATE_MISSING``,
``SFC_SCHEDULE_UNSETTLED``, the version-state nodes named as T-CON-08 columns and the formulas of
``FORMULA_IDS``. ``run`` measures the inception price and the specialist targets (EMOD-18, EMOD-21,
EMOD-22, EMOD-23); ``price_at`` measures the price at any date and ENG-06 position for stages 06
and 08; ``complete_returns`` adds the expected-returns memo once stage 05 has allocated.
Submodules are private (DG-ENG-07). Standard library only (DG-ARC-02).
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from fractions import Fraction
from types import MappingProxyType
from typing import Final

from erev_engine.stages.s02_contract_identification import DepositRecognition
from erev_engine.stages.s02_contract_identification.deposits import END_OF_DAY
from erev_engine.stages.s03_pob_builder import PobState
from erev_engine.stages.s04_transaction_price import (
    buildup,
    customer_consideration,
    financing,
    noncash,
    returns,
    specialist,
    unconstrained,
)
from erev_engine.stages.s04_transaction_price.unconstrained import UnconstrainedView
from erev_engine.stages.state import (
    BookContext,
    DepositRelease,
    EventView,
    Finding,
    OrderKey,
    ReturnPath,
    SpecialistTargets,
    TpBuildUp,
    TpView,
)
from erev_engine.trace import SourceRef, TraceBuilder

__all__ = [
    "FORMULA_IDS",
    "OPTIONAL_POLICY_KEYS",
    "POLICY_KEYS",
    "TP_COMPONENTS",
    "PricedState",
    "UnconstrainedView",
    "complete_returns",
    "first_boundary",
    "price_at",
    "run",
]

# ENGINE_SPEC Table 0.10-A row 04 (STAGE_POLICY_KEYS), sorted.
POLICY_KEYS: Final[tuple[str, ...]] = (
    "billing.posting",
    "claims.recognition_gate",
    "cpc.incentive_asset_release_basis",
    "cpc.share_based_timing",
    "noncash.measurement_date",
    "returns.model",
    "royalty.minimum_guarantee",
    "sfc.discount_rate_basis",
    "sfc.one_year_expedient",
    "tp.sales_tax_exclusion",
    "usage.tier_minimum_method",
    "vc.constraint",
    "vc.estimation_method",
)
# POL-040 has no framework default ("by VC type"): the method is the element's version method.
OPTIONAL_POLICY_KEYS: Final = frozenset({"vc.estimation_method"})
# ENGINE_SPEC §4.4 formula ids, sorted.
FORMULA_IDS: Final[tuple[str, ...]] = (
    "sfc.accretion.v1",
    "sfc.cash_selling_price.v1",
    "sfc.effective_interest.annual.v1",
    "sfc.effective_interest.monthly.v1",
    "sfc.gap_test.v1",
    "tp.buildup.v1",
    "tp.concession_implicit.v1",
    "tp.cpc_reduction.v1",
    "tp.cpc_release.v1",
    "tp.fixed.v1",
    "tp.noncash.v1",
    "tp.realised_usage.v1",
    "tp.returns_expected.v1",
    "tp.tax_excluded.v1",
    "tp.vc_constrained.v1",
    "tp.vc_entered.v1",
    "tp.vc_expected_value.v1",
    "tp.vc_most_likely.v1",
    "tp.warranty_accrual.v1",
)
# ENGINE_SPEC §0.10 TP_COMPONENTS: ordered build-up members of S04-R-02 as (TpBuildUp member,
# T-CON-08 column and trace measure). ``total`` = fixed + vc_constrained + expected_returns +
# consideration_payable + financing_adjustment + noncash; the memo members are excluded.
TP_COMPONENTS: Final = (
    ("fixed", "fixed_consideration"),
    ("vc_constrained", "vc_constrained_amount"),
    ("vc_excluded", "vc_excluded_amount"),
    ("expected_returns", "expected_returns_amount"),
    ("consideration_payable", "consideration_payable_amount"),
    ("financing_adjustment", "financing_adjustment_amount"),
    ("noncash", "noncash_consideration_amount"),
    ("sales_tax_excluded", "sales_tax_excluded_amount"),
    ("out_of_scope", "out_of_scope_amount"),
    ("total", "transaction_price"),
    ("allocation_basis", "tp_allocation_basis"),
)


@dataclass(frozen=True, slots=True)
class PricedState:
    """Stage 04 output for one book (ENGINE_SPEC §4.1), consumed by stage 05."""

    book_code: str
    group_key: str
    inception_date: date
    pob: PobState  # stage 03 state, with the stage 02 state and the canonical bundle
    tp: TpBuildUp  # at inception, before the first boundary (S04-R-01)
    tp_unconstrained: Mapping[str, TpView]  # S04-R-21: an UnconstrainedView per member contract
    specialist_targets: SpecialistTargets  # deposit (stage 02); S04-R-13, S04-R-17 to S04-R-19
    return_paths: Mapping[str, ReturnPath]  # S04-R-08b by subject key; r published by stage 05
    findings: tuple[Finding, ...]  # CV-43 order
    # True while returnable obligations await their allocation: ``tp`` holds no expected-returns
    # memo, its version-state nodes and ``tp_unconstrained`` are not built, and stage 05 calls
    # ``complete_returns`` (L2-2-Q-5).
    returns_pending: bool = False


def first_boundary(st: PobState) -> EventView | None:
    """The first boundary event of the group that the inception price precedes (§4.2).

    An ``ESTIMATE_CHANGED`` effective on or before the group inception applies a version in force
    at inception, so it belongs to the inception measurement and is not a boundary here.
    """
    for event in st.identified.canonical.boundary_events:
        if event.event_type == "ESTIMATE_CHANGED" and event.effective_date <= st.inception_date:
            continue
        return event
    return None


def price_at(
    ctx: BookContext,
    st: PobState,
    at: date,
    tb: TraceBuilder | None,
    *,
    before: EventView | None = None,
    rates: Mapping[str, Fraction] | None = None,
    boundary: EventView | None = None,
    added: Sequence[tuple[SourceRef, Fraction]] = (),
) -> TpBuildUp:
    """The price of the group at ``at`` and ENG-06 position ``before`` (S04-R-01).

    ``boundary`` names the nodes after the boundary event whose price this is, ``<column>@<its event
    key>``, when that differs from ``before`` (the price after a boundary is measured before the
    next event; CV-50; L5-3-Q-2).

    ``added`` is the consideration the boundary events before the position add to the booking
    lines, as source references with their amounts; it enters ``fixed`` (``buildup.price``;
    L5-3-Q-17).

    ``before`` is the boundary event being applied, or ``None`` for the end of the stream. ``rates``
    maps every returnable obligation (S04-R-08a) to r = x_exact ÷ Q of the segment in force at
    ``at``; a returnable obligation without a rate raises ``ValueError`` (L2-2-Q-6). Nodes take the
    measure ``<column>@<event key>`` for a boundary position (CV-50) and the version-state names
    otherwise. A position already traced is measured with ``tb = None``, because a node id is
    emitted once (``TRACE_DUPLICATE_NODE``).
    """
    missing = sorted(
        item.obligation.subject_key
        for item in returns.returnable(ctx, st)
        if rates is None or item.obligation.subject_key not in rates
    )
    if missing:
        raise ValueError(
            f"price_at needs the unit rate of returnable obligations {', '.join(missing)} "
            "(S04-R-08)"
        )
    named = before if boundary is None else boundary
    suffix = "" if named is None else f"@{named.event_key}"
    return buildup.price(ctx, st, at, before, tb, suffix, rates=rates, added=added)


def run(ctx: BookContext, st: PobState, tb: TraceBuilder) -> PricedState:
    """The inception price with version-state nodes and the specialist targets (§4.2; CV-10).

    Returnable obligations get their return paths (S04-R-08b) and ``RETURN_ESTIMATE_MISSING``
    findings here; their memo needs the allocation, so the build-up stays pending until stage 05
    calls ``complete_returns``. The financing targets and findings come from the schedule in force
    at the end of the stream (S04-R-10 to S04-R-13; L2-2-Q-17). Findings are returned in CV-43
    order; ``compute`` raises CV-15 for any ``ERROR``. A malformed estimate version raises
    ``ValueError``, and a failed invariant raises ``EngineError("ENGINE_INVARIANT_VIOLATED")``
    (CV-45, CV-46).
    """
    ctx.policies.require(key for key in POLICY_KEYS if key not in OPTIONAL_POLICY_KEYS)
    boundary = first_boundary(st)
    items = returns.returnable(ctx, st)
    paths = {item.obligation.subject_key: returns.path(ctx, st, item) for item in items}
    pending = bool(items)
    tp = buildup.price(ctx, st, st.inception_date, boundary, None if pending else tb, "")
    views = {} if pending else unconstrained.views(ctx, st, boundary, {})
    stream = financing.measure(
        ctx, st, specialist.stream_end(ctx, st), None, specialist.fixed_lines(st)
    )
    targets = SpecialistTargets(
        deposit=st.identified.deposit_targets,
        deposit_releases=tuple(
            DepositRelease(
                contract_key=item.contract_key,
                entity=st.identified.canonical.contracts[
                    item.contract_key
                ].header.contracting_entity_code,
                reason=item.reason,
                effective_date=item.effective_date,
                order_key=_release_order_key(st, item),
                amount=item.amount,
                node_id=item.node_id,
                timed=item.timed,
            )
            for item in st.identified.recognitions
        ),
        financing=financing.targets(ctx, st, stream, tb),
        warranty=specialist.warranty_targets(ctx, st, tb),
        customer_consideration=customer_consideration.targets(ctx, st, tb),
        noncash=noncash.targets(ctx, st, tb),
    )
    found = (*returns.findings(ctx, st, items), *financing.findings(ctx, st, stream))
    return PricedState(
        book_code=st.book_code,
        group_key=st.group_key,
        inception_date=st.inception_date,
        pob=st,
        tp=tp,
        tp_unconstrained=MappingProxyType(views),
        specialist_targets=targets,
        return_paths=MappingProxyType(dict(sorted(paths.items()))),
        findings=tuple(sorted(found, key=Finding.sort_key)),
        returns_pending=pending,
    )


def complete_returns(
    ctx: BookContext, st: PricedState, rates: Mapping[str, Fraction], tb: TraceBuilder
) -> PricedState:
    """The inception build-up with the expected-returns memo (S04-R-08, S04-R-08b; L2-2-Q-5).

    Stage 05 calls it after the allocation with r = x_exact ÷ Q of each returnable obligation. It
    measures the inception price again, emits the version-state nodes that ``run`` deferred,
    publishes r on every return path from the group inception and builds the unconstrained view. A
    state without pending returns is returned unchanged; a missing rate raises ``ValueError``.
    """
    if not st.returns_pending:
        return st
    missing = sorted(set(st.return_paths) - set(rates))
    if missing:
        raise ValueError(f"complete_returns needs the unit rate of {', '.join(missing)}")
    pob = st.pob
    boundary = first_boundary(pob)
    tp = buildup.price(ctx, pob, pob.inception_date, boundary, tb, "", rates=rates)
    paths = {
        key: dataclasses.replace(path, r=((pob.inception_date, rates[key]),))
        for key, path in st.return_paths.items()
    }
    return dataclasses.replace(
        st,
        tp=tp,
        tp_unconstrained=MappingProxyType(unconstrained.views(ctx, pob, boundary, rates)),
        return_paths=MappingProxyType(paths),
        returns_pending=False,
    )


def _release_order_key(st: PobState, item: DepositRecognition) -> OrderKey:
    """The ENG-06 position of a 25-7 recognition: its event's order key, or the end of its date
    for a dated point without an event (ENGINE_SPEC S02-R-07 rev 1.6; L1-2-Q-7)."""
    if item.event_key is None:
        return (item.effective_date, END_OF_DAY, "")
    event = next(e for e in st.identified.canonical.events if e.event_key == item.event_key)
    return event.order_key
