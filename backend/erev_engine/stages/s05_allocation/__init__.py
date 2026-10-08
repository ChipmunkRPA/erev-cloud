"""Stage 05 SSP resolution and allocation.

ENGINE_SPEC §5.1 and §5.2; §5.3 S05-R-01 to S05-R-08 (book, version, entry, currency, extended
values, SSP points, bypasses); §5.4 S05-R-09 to S05-R-17 (targeted VC, discount exception, residual
approach, relative SSP, largest remainder, negative allocation, original columns, parity preset);
§5.5 S05-INV-01 to S05-INV-03, findings ``SSP_KEY_NOT_FOUND``, ``FX_RATE_MISSING``,
``OBSERVABLE_POINT_MISSING``, ``TOTAL_SSP_ZERO``, ``RESIDUAL_REJECTED``,
``VC_TARGET_TOLERANCE_EXCEEDED``, ``VC_ALLOCATION_NEGATIVE``; ``DISCOUNT_EXCEPTION`` proposals
(CV-16); the S03-R-13 merge step. ``resolve_ssp`` prices one draft or line at a pricing date for
stages 03, 06 and 08; ``allocate`` apportions the allocation basis by relative SSP after targeted
VC; ``run`` builds the inception ``AllocatedState``. Submodules are private (DG-ENG-07). Standard
library only (DG-ARC-02).
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from fractions import Fraction
from types import MappingProxyType
from typing import Final

from erev_engine.bundle import MaterialRightInput, ProposalOut, ssp_range_key
from erev_engine.enums import ObligationKind
from erev_engine.errors import EngineError
from erev_engine.money import format_exact, to_fraction
from erev_engine.stages.s01_canonicalize import check_selected_quantity_unit, encode_key
from erev_engine.stages.s02_contract_identification import IdentifiedState
from erev_engine.stages.s03_pob_builder import PobDraft, RawLine
from erev_engine.stages.s04_transaction_price import PricedState, complete_returns
from erev_engine.stages.s05_allocation import (
    convert,
    exceptions,
    original,
    points,
    relative,
    ssp_books,
    targeted,
)
from erev_engine.stages.s05_allocation.points import SSP_POINT_POLICIES
from erev_engine.stages.s05_allocation.relative import Resolved, SnapshotSource
from erev_engine.stages.s05_allocation.ssp_books import Record
from erev_engine.stages.state import (
    AllocatedState,
    AllocationSegment,
    BookContext,
    Finding,
    ObligationState,
    Quota,
    SspResolution,
    TpBuildUp,
)
from erev_engine.trace import SourceRef, TraceBuilder

__all__ = [
    "FORMULA_IDS",
    "PARITY_PRESET_VALUES",
    "POLICY_KEYS",
    "SSP_POINT_POLICIES",
    "Record",
    "allocate",
    "assert_contract_version_identity",
    "resolve_ssp",
    "run",
]

# ENGINE_SPEC Table 0.10-A row 05 (STAGE_POLICY_KEYS), sorted.
POLICY_KEYS: Final[tuple[str, ...]] = (
    "alloc.discount_exception",
    "alloc.negative_booking_lines",
    "alloc.zero_total_ssp",
    "migration.split_upload_allocation",
    "rounding.apportionment",
    "ssp.currency_conversion",
    "ssp.inside_range_point",
    "ssp.method_hierarchy",
    "ssp.outside_range_point",
    "ssp.residual_failure",
    "ssp.version_basis",
    "vc.targeted_allocation_tolerance",
)
# ENGINE_SPEC §5.5 formula ids, sorted.
FORMULA_IDS: Final[tuple[str, ...]] = (
    "alloc.discount_exception.v1",
    "alloc.largest_remainder.v1",
    "alloc.original_total.v1",
    "alloc.original_total_amount.v1",
    "alloc.original_weight.v1",
    "alloc.relative_ssp.v1",
    "alloc.residual.v1",
    "alloc.targeted_vc.v1",
    "alloc.unit_ssp.v1",
    "input.echo.v1",
    "ssp.convert.v1",
    "ssp.extend.v1",
    "ssp.legacy_range.v1",
    "ssp.point.v1",
    "ssp.select_version.v1",
)
# S05-R-17: the parity preset values that reproduce legacy L682 to L717 in rationals.
PARITY_PRESET_VALUES: Final[Mapping[str, str]] = MappingProxyType(
    {
        "alloc.discount_exception": "DISABLED",  # POL-076
        "ssp.inside_range_point": "CONTRACT_PRICE",  # POL-071
        "ssp.outside_range_point": "NEAREST_BOUND",  # POL-072
        "ssp.range_validation": "NOT_ENFORCED",  # POL-073
        "ssp.version_basis": "NAMED_VERSION",  # POL-070
        "vc.targeted_allocation_tolerance": "NOT_ENFORCED",  # POL-044
    }
)
STAGE: Final = 5
ZERO_TOTAL_POLICY: Final = "alloc.zero_total_ssp"
REJECT: Final = "REJECT"


def resolve_ssp(
    ctx: BookContext,
    draft: PobDraft | RawLine,
    at: date,
    price: Fraction | None = None,
    tb: TraceBuilder | None = None,
    findings: list[Finding] | None = None,
    *,
    identified: IdentifiedState,
    allocation_basis: Fraction | None = None,
    event_key: str | None = None,
    record: Record | None = None,
) -> SspResolution | None:
    """The SSP snapshot of ``draft`` priced at ``at`` (ENGINE_SPEC §5.2; S05-R-01 to S05-R-08).

    ``record`` names the pricing a caller makes, so that the version recorded for it is read
    (S05-R-03): the own pricing of an obligation in the event that adds it, or the weight of an
    existing obligation in a modification (S06-R-11). Without a record the version is selected
    at ``at``.

    ``price = None`` returns the point or the midpoint (S03-R-03 bundle weights). A ``PobDraft`` is
    resolved per weighted member line at the member's own stated price, and the values sum
    (S03-R-05); ``VC_LINE`` drafts and options under ``ENTERED_AMOUNT`` or
    ``DISCOUNT_X_LIKELIHOOD`` bypass the range test (S05-R-08). ``identified`` carries the
    canonical bundle (SSP books, rule sets, rates, pins), which ``BookContext`` does not;
    ``allocation_basis`` selects ``DEAL_SIZE`` bands. With ``tb`` the node
    ``original_ssp_selected:<subject>:-`` is emitted. Findings are appended to ``findings``; without
    that list an ``ERROR`` finding raises ``EngineError`` with its code. ``None`` when an ``ERROR``
    blocks the resolution.
    """
    collected: list[Finding] = [] if findings is None else findings
    if isinstance(draft, RawLine):
        found = _resolve_line(
            ctx, identified, draft, at, price, allocation_basis, collected, record=record
        )
        subject = draft.subject_key
        priced = None if found is None else (found[0], found[1])
    else:
        item = _resolve(
            ctx, identified, draft, at, price, allocation_basis, collected, record=record
        )
        subject = draft.subject_key
        priced = None if item is None else (item.ssp, item.sources)
    if findings is None:
        _raise_first_error(collected)
    if priced is None:
        return None
    if tb is not None:
        # ``event_key``: the boundary's ``original_ssp_selected@<event key>`` node (CV-50 rev 1.29)
        points.emit(ctx, tb, subject, priced[0], price, priced[1], event_key=event_key)
    return priced[0]


def allocate(
    ctx: BookContext,
    tp: TpBuildUp,
    weights: Sequence[Fraction],
    keys: Sequence[str],
    tb: TraceBuilder | None = None,
    *,
    group_key: str,
    findings: list[Finding] | None = None,
    targets: Mapping[str, Sequence[str]] | None = None,
) -> tuple[Quota, ...]:
    """S05-R-10, S05-R-13 and S05-R-14 over ``tp.allocation_basis.posted``: one ``Quota`` per key.

    ``targets`` maps the estimate key of a targeted element of ``tp.elements`` to the subject keys
    of its targets. The element's posted K is apportioned over those keys by relative SSP, T = the
    basis less every K over every key, and each quota sums the key's shares (CV-34 holds per pool).
    Σw = 0, over every key or over an element's targets, yields ``TOTAL_SSP_ZERO`` (``ERROR``;
    POL-077 ``REJECT``) and ``()``; without a findings list it raises
    ``EngineError("TOTAL_SSP_ZERO")``. A negative weight raises ``NEGATIVE_WEIGHT``. With ``tb`` the
    §5.5 nodes ``total_ssp``, ``allocation_weight``, ``original_allocated_exact`` and
    ``original_allocated_amount`` are emitted over ``tp_allocation_basis:<group>:-``, or over
    ``allocation_remainder:<group>:-`` with ``targeted_vc_allocated`` nodes after targeted VC.
    """
    if ctx.policies.value(ZERO_TOTAL_POLICY) != REJECT:
        raise ValueError(f"{ZERO_TOTAL_POLICY} is FORCED to {REJECT} (POL-077)")
    chosen = targets or {}
    by_key = dict(zip(keys, weights, strict=True))
    elements = tuple(
        targeted.Element(view, None, tuple(sorted(chosen[view.estimate_key])))
        for view in tp.elements
        if view.estimate_key in chosen
    )
    pools = targeted.apportion(ctx, elements, by_key, group_key, findings)
    if pools is None:
        return ()
    group = encode_key(group_key)
    remainder = targeted.remainder(tp, pools)
    pool_node = _pool_node(ctx, tb, group, pools, remainder)
    shares = _relative(ctx, remainder, weights, keys, tb, group, pool_node, findings)
    if not shares:
        return ()
    if tb is not None:
        targeted.emit(ctx, tb, pools, {})
    return targeted.totals(keys, shares, pools)


def run(ctx: BookContext, st: PricedState, tb: TraceBuilder) -> AllocatedState:
    """The inception allocation of every obligation of the group (ENGINE_SPEC §5.2; CV-10).

    Every obligation is resolved at its pricing date and stated price; candidates of S03-R-13 are
    merged; the allocation basis is allocated over every obligation, routed-out lease components
    included (S05-R-09, PT-09), in the S05-R-09 order: targeted VC, discount exception, residual,
    relative SSP and largest remainder. Each obligation takes its original columns and a first
    ``AllocationSegment`` holding its whole inception allocation (S05-R-16); targeted shares are
    published in ``targeted_vc_quotas``. A priced state with pending returns is completed by the
    stage 04 ``complete_returns`` with r = x_exact ÷ Q of each returnable obligation (S04-R-08b).
    Findings are returned in CV-43 order; ``compute`` raises CV-15 for any ``ERROR``, and such a
    state holds no obligations. Discount-exception proposals are returned whatever the findings
    (CV-16).
    """
    ctx.policies.require(POLICY_KEYS)
    identified = st.pob.identified
    basis = st.tp.allocation_basis
    if not st.pob.obligations and basis.posted == 0:
        # D-88 L7-5-Q-10 (1): every line is excluded by S03-R-11 and nothing is priced; S01-R-13:
        # a voided member has no line at all. Nothing to allocate and no TOTAL_SSP_ZERO; T ≠ 0
        # with no obligation still raises.
        return _state(st, (), ())
    findings: list[Finding] = []
    resolved: list[Resolved] = []
    for draft in st.pob.obligations:
        item = _resolve(
            ctx,
            identified,
            draft,
            draft.pricing_date,
            draft.stated_price,
            basis.exact,
            findings,
            record=Record(draft.subject_key),  # S05-R-03: the booking pricing's own record
        )
        if item is not None:
            resolved.append(item)
    if _blocking(findings):
        return _state(st, (), findings)
    items = relative.merge_immaterial(resolved)
    for item in items:
        points.emit(
            ctx,
            tb,
            item.draft.subject_key,
            item.ssp,
            item.draft.stated_price,
            item.sources,
            item.merged,
        )
    proposals: list[ProposalOut] = []
    allocation = _allocate(ctx, st, items, tb, findings, proposals)
    if allocation is None or _blocking(findings):
        return _state(st, (), findings, proposals)
    quotas = allocation.quotas
    if st.returns_pending:  # S04-R-08b: r = x_exact ÷ Q once the allocation exists (L2-2-Q-5)
        rates = {
            item.draft.subject_key: quota.x_exact / item.draft.quantity
            for item, quota in zip(items, quotas, strict=True)
            if item.draft.subject_key in st.return_paths
        }
        st = complete_returns(ctx, st, rates, tb)
    # S08-R-04 (rev 1.6; D-91): the routing weight fixed at inception is the selected SSP, or the
    # inception residual R of the residual candidate (its 32-34(c) SSP estimate; S05-R-12).
    weights = {item.draft.subject_key: item.ssp.selected for item in items}
    if allocation.residual is not None:
        weights[allocation.residual.key] = allocation.residual.amount
    obligations = original.build(
        ctx, st, items, quotas, tb, pools=allocation.pools, weights=weights
    )
    state = _state(st, obligations, findings, proposals, allocation.pools)
    _assert_allocation_sum(state)
    return state


def assert_contract_version_identity(st: AllocatedState) -> None:
    """DG-ENG-05 fail-closed check of 04 DB-17 V1 on an allocated state (CTL-012).

    Σ allocated amount = ``transaction_price`` − ``consideration_payable_amount`` of the group's
    latest build-up, where each obligation's allocated amount is its latest ``FIXED`` segment,
    returns-adjusted by the posted ``expected_returns`` memo (ENGINE_SPEC S04-R-02; ENGINE_SPEC_B
    S09-R-23). A violation raises ``EngineError("ENGINE_INVARIANT_VIOLATED")`` naming ``DB-17 V1``.
    A state with an ``ERROR`` finding holds no obligations, ``compute`` refuses it (CV-15), and it
    is not checked.
    """
    if _blocking(st.findings) or not st.tp_history:
        return
    tp = st.tp_history[-1]
    allocated = sum(_latest_fixed(ob).a_posted for ob in st.obligations)
    allocated += tp.expected_returns.posted
    expected = tp.total.posted - tp.consideration_payable.posted
    if allocated != expected:
        raise EngineError(
            "ENGINE_INVARIANT_VIOLATED",
            "DB-17 V1: Σ allocated_amount differs from transaction_price − "
            "consideration_payable_amount",
            subject_key=encode_key(st.group_code),
            detail={
                "allocated": str(allocated),
                "expected": str(expected),
                "invariant": "DB-17 V1",
            },
        )


def _assert_allocation_sum(st: AllocatedState) -> None:
    """S05-INV-01 before ``run`` returns (PROP:P1; CTL-012): Σ a_p = ``allocation_basis.posted``."""
    basis = st.tp_history[0].allocation_basis.posted
    allocated = sum(ob.original_allocation.a_posted for ob in st.obligations)
    if allocated != basis:
        raise EngineError(
            "ENGINE_INVARIANT_VIOLATED",
            "posted allocations do not sum to the allocation basis",
            subject_key=encode_key(st.group_code),
            detail={"allocated": str(allocated), "basis": str(basis), "invariant": "S05-INV-01"},
        )


def _latest_fixed(ob: ObligationState) -> AllocationSegment:
    fixed = [segment for segment in ob.segments if segment.component == "FIXED"]
    if not fixed:
        raise ValueError(f"{ob.subject_key} holds no FIXED allocation segment (CV-60)")
    return fixed[-1]


@dataclass(frozen=True, slots=True)
class _Allocation:
    quotas: tuple[Quota, ...]  # per item: its share of T plus its targeted shares
    pools: tuple[targeted.Pool, ...]
    residual: exceptions.Residual | None  # the residual candidate and R (S05-R-12)


def _allocate(
    ctx: BookContext,
    st: PricedState,
    items: Sequence[Resolved],
    tb: TraceBuilder,
    findings: list[Finding],
    proposals: list[ProposalOut],
) -> _Allocation | None:
    """The S05-R-09 order over the group; ``None`` when a finding blocks.

    (1) targeted VC (S05-R-14), then T = the basis less every K; (2) the discount exception
    (S05-R-11); (3) the residual approach (S05-R-12); (4) relative SSP (S05-R-10), or the exact
    amounts of (2) and (3) (S05-R-13); (5) largest remainder per pool. Negative targeted allocations
    (S05-R-15) and the POL-044 test follow.
    """
    if ctx.policies.value(ZERO_TOTAL_POLICY) != REJECT:
        raise ValueError(f"{ZERO_TOTAL_POLICY} is FORCED to {REJECT} (POL-077)")
    identified = st.pob.identified
    minor_unit = ctx.currencies[ctx.txn_currency].minor_unit
    group = encode_key(st.group_key)
    weights = [item.ssp.selected for item in items]
    keys = [item.draft.subject_key for item in items]
    by_key = dict(zip(keys, weights, strict=True))
    elements = targeted.select(identified, st.tp, items)
    pools = targeted.apportion(ctx, elements, by_key, st.group_key, findings)
    if pools is None:
        return None
    remainder = targeted.remainder(st.tp, pools)
    pool_node = _pool_node(ctx, tb, group, pools, remainder)
    units = Fraction(remainder, 10**minor_unit)

    def resolve(
        line: RawLine,
    ) -> tuple[SspResolution, tuple[SourceRef, ...], str | None, SnapshotSource] | None:
        basis = st.tp.allocation_basis.exact
        return _resolve_line(
            ctx,
            identified,
            line,
            st.inception_date,
            None,
            basis,
            None,
            record=Record(line.subject_key),
        )

    found = exceptions.bundles(ctx, identified, items, units, st.inception_date, resolve)
    proposals.extend(exceptions.proposals(found))
    bundle = exceptions.applied(found)
    residual = exceptions.residual(ctx, items, units, bundle, findings, identified)
    if _blocking(findings):
        return None
    if bundle is None and residual is None:
        shares = _relative(ctx, remainder, weights, keys, tb, group, pool_node, findings)
    else:
        amounts = exceptions.exact(items, units, bundle, residual)
        sources = exceptions.emit(ctx, tb, pool_node, items, units, bundle, residual)
        shares = _relative(
            ctx,
            remainder,
            amounts,
            keys,
            tb,
            group,
            pool_node,
            findings,
            sources=sources,
            path="exceptions",
        )
    if not shares:
        return None
    quotas = targeted.totals(keys, shares, pools)
    targeted.negative(pools, keys, quotas, findings)
    basis_posted = st.tp.allocation_basis.posted
    tested = targeted.tolerance(ctx, identified, pools, by_key, basis_posted, findings)
    targeted.emit(ctx, tb, pools, tested)
    return _Allocation(quotas, pools, residual)


def _relative(
    ctx: BookContext,
    total_minor: int,
    weights: Sequence[Fraction],
    keys: Sequence[str],
    tb: TraceBuilder | None,
    group: str,
    basis_node: str,
    findings: list[Finding] | None,
    *,
    sources: Sequence[str] | None = None,
    path: str = "relative",
) -> tuple[Quota, ...]:
    """S05-R-10 over ``total_minor``; Σw = 0 yields ``TOTAL_SSP_ZERO`` (POL-077 ``REJECT``)."""
    if sum(weights, Fraction(0)) == 0:
        finding = Finding(
            "TOTAL_SSP_ZERO",
            "ERROR",
            group,
            {"obligation_count": str(len(keys)), "rule": "S05-R-10"},
            STAGE,
            None,
        )
        if findings is None:
            raise EngineError(finding.code, "every obligation has SSP 0", subject_key=group)
        findings.append(finding)
        return ()
    minor_unit = ctx.currencies[ctx.txn_currency].minor_unit
    quotas = relative.apportion(total_minor, minor_unit, weights, keys)
    if tb is not None:
        relative.emit(ctx, tb, group, basis_node, weights, keys, quotas, sources=sources, path=path)
    return quotas


def _pool_node(
    ctx: BookContext,
    tb: TraceBuilder | None,
    group: str,
    pools: Sequence[targeted.Pool],
    remainder: int,
) -> str:
    """The node of the pool apportioned by relative SSP: the basis, or the basis less K."""
    basis_node = f"tp_allocation_basis:{group}:-"
    if tb is None or not pools:
        return basis_node
    return targeted.emit_remainder(ctx, tb, group, basis_node, pools, remainder)


def _resolve(
    ctx: BookContext,
    identified: IdentifiedState,
    draft: PobDraft,
    at: date,
    price: Fraction | None,
    allocation_basis: Fraction | None,
    findings: list[Finding],
    *,
    record: Record | None = None,
) -> Resolved | None:
    """S05-R-08 bypasses, then the weighted member lines of a draft (S03-R-05 sums). ``record``:
    the pricing made, whose recorded version every member line reads (S05-R-03)."""
    if draft.is_vc_line:
        silent = _resolve_line(
            ctx, identified, draft.line, at, None, allocation_basis, None, record=record
        )
        return _bypass(draft, silent, Fraction(0), points.VC_LINE, ())
    terms = _option_terms(identified, draft)
    if draft.obligation_kind == ObligationKind.MATERIAL_RIGHT and terms is not None:
        if terms.ssp_method == "ENTERED_AMOUNT":
            found = _resolve_line(
                ctx, identified, draft.line, at, None, allocation_basis, findings, record=record
            )
            if found is None:
                return None
            return _bypass(draft, found, found[0].selected, terms.ssp_method, ())
        if terms.ssp_method == "DISCOUNT_X_LIKELIHOOD":
            option = points.option_ssp(identified, terms, at)
            if option is None:
                detail = {"obligation_key": draft.obligation_key, "rule": "S03-R-07"}
                findings.append(
                    Finding("NON_FINITE_AMOUNT", "ERROR", draft.subject_key, detail, STAGE, None)
                )
                return None
            silent = _resolve_line(
                ctx, identified, draft.line, at, None, allocation_basis, None, record=record
            )
            return _bypass(draft, silent, option[0], terms.ssp_method, (option[1],))
    members = [member for member in draft.members if member.weighted]
    parts: list[tuple[SspResolution, tuple[SourceRef, ...], str | None, SnapshotSource]] = []
    for member in members:
        member_price = None if price is None else member.stated_price
        found = _resolve_line(
            ctx,
            identified,
            member.line,
            at,
            member_price,
            allocation_basis,
            findings,
            record=record,
        )
        if found is not None:
            parts.append(found)
    if len(parts) != len(members) or not parts:
        return None
    return Resolved(
        draft=draft,
        ssp=points.combine([part[0] for part in parts]),
        sources=tuple(source for part in parts for source in part[1]),
        revenue_account=parts[0][2],
        merged=(),
        source=parts[0][3] if len(parts) == 1 else None,
    )


def _resolve_line(
    ctx: BookContext,
    identified: IdentifiedState,
    line: RawLine,
    at: date,
    price: Fraction | None,
    allocation_basis: Fraction | None,
    findings: list[Finding] | None,
    *,
    record: Record | None = None,
) -> tuple[SspResolution, tuple[SourceRef, ...], str | None, SnapshotSource] | None:
    """S05-R-02 to S05-R-07 for one line; ``findings = None`` resolves silently (bypass keys)."""
    cb = identified.canonical
    header = cb.contracts[line.contract_key].header
    book = ssp_books.select_book(ctx, identified, line, at, record=record)
    version = (
        None
        if book is None
        else ssp_books.select_version(ctx, identified, line, book, at, record=record)
    )
    entry = (
        None if version is None else ssp_books.select_entry(version, line, header, ctx.txn_currency)
    )
    if book is None or version is None or entry is None:
        _not_found(findings, line, "S05-R-02" if book is None else "S05-R-03", book)
        return None
    conversion = convert.rate(ctx, identified, line, entry.currency, at)
    if conversion.factor is None:
        if findings is not None and conversion.finding == "FX_RATE_MISSING":
            detail = {
                "base_currency": entry.currency,
                "entry_key": entry.entry_key,
                "pricing_date": at.isoformat(),
                "quote_currency": ctx.txn_currency,
                "rule": "S05-R-05",
            }
            findings.append(
                Finding("FX_RATE_MISSING", "ERROR", line.subject_key, detail, STAGE, None)
            )
        else:
            _not_found(findings, line, "S05-R-05", book)
        return None
    extended = points.extend(entry, line, conversion.factor, allocation_basis)
    if extended is None:
        _not_found(findings, line, "S05-R-06", book)
        return None
    entity = header.contracting_entity_code
    scope = {"contract": line.contract_key, "obligation": line.subject_key, "entity": entity}
    inside = ctx.policies.value(points.INSIDE_POLICY, **scope)
    outside = ctx.policies.value(points.OUTSIDE_POLICY, **scope)
    point = points.select(extended, price, inside, outside, entry.entry_key)
    if point.observable_missing and findings is not None:
        detail = {"entry_key": entry.entry_key, "rule": "S05-R-07"}
        findings.append(
            Finding("OBSERVABLE_POINT_MISSING", "WARNING", line.subject_key, detail, STAGE, None)
        )
    # D-97 (3): the selected dated entry carries its own quantity_unit declaration and agrees with
    # every entry of its product in its book (CV-45; never reinterpreted by a later declaration).
    check_selected_quantity_unit(cb.bundle, book, entry)
    row = (
        points.band_row(entry, line, allocation_basis)
        if entry.ranges and entry.method != "legacy_range"
        else None
    )
    range_key = (
        None if row is None else ssp_range_key(entry.entry_key, row.band_dimension, row.band_from)
    )
    resolution = SspResolution(
        range_key=range_key,
        book_code=book,
        version_key=version.version_key,
        version_label=version.legacy_version_label,
        entry_key=entry.entry_key,
        method=entry.method,
        rate_key=conversion.rate_key,
        unit_list_price=extended.unit_list_price,
        midpoint_discount_ratio=_ratio(entry.midpoint_discount_ratio),
        range_ratio=_ratio(entry.range_ratio),
        low=extended.low,
        mid=extended.mid,
        high=extended.high,
        selected=point.selected,
        in_range=point.in_range,
        point_policy=point.policy,
        residual_candidate=extended.residual,
        value_basis=entry.value_basis,
        quantity_unit=entry.quantity_unit,
    )
    sources: list[SourceRef] = [
        SourceRef(
            "ssp_entry" if range_key is None else "ssp_range",
            entry.entry_key if range_key is None else range_key,
            {"value": format_exact(point.selected)},
        )
    ]
    rate_source: SourceRef | None = None
    if conversion.rate_key is not None:
        factor = format_exact(conversion.factor)
        rate_source = SourceRef("fx_rate", conversion.rate_key, {"value": factor})
        sources.append(rate_source)
    snapshot = SnapshotSource(
        entry=entry,
        factor=conversion.factor,
        rate_source=rate_source,
        row=row,
    )
    return resolution, tuple(sources), entry.revenue_account_code, snapshot


def _bypass(
    draft: PobDraft,
    found: tuple[SspResolution, tuple[SourceRef, ...], str | None, SnapshotSource] | None,
    selected: Fraction,
    policy: str,
    extra: tuple[SourceRef, ...],
) -> Resolved:
    """S05-R-08: the keys and extended values of the entry when one resolves; SSP ``selected``."""
    if found is None:
        resolution = SspResolution(
            book_code="",
            version_key="",
            version_label=None,
            entry_key="",
            method="",
            rate_key=None,
            unit_list_price=None,
            midpoint_discount_ratio=None,
            range_ratio=None,
            low=None,
            mid=None,
            high=None,
            selected=selected,
            in_range=None,
            point_policy=policy,
            residual_candidate=False,
        )
        sources: tuple[SourceRef, ...] = extra
        account = None
    else:
        resolution = dataclasses.replace(
            found[0], selected=selected, in_range=None, point_policy=policy, range_key=None
        )
        sources = extra or tuple(
            SourceRef("ssp_entry", found[0].entry_key, {"value": format_exact(selected)})
            if source.ref_type in {"ssp_entry", "ssp_range"}
            else source
            for source in found[1]
        )
        account = found[2]
    return Resolved(draft, resolution, sources, account, (), None if found is None else found[3])


def _option_terms(identified: IdentifiedState, draft: PobDraft) -> MaterialRightInput | None:
    header = identified.canonical.contracts[draft.contract_key].header
    return next(
        (right for right in header.material_rights if right.obligation_key == draft.obligation_key),
        None,
    )


def _ratio(value: Decimal | None) -> Fraction | None:
    return None if value is None else to_fraction(value)


def _not_found(
    findings: list[Finding] | None,
    line: RawLine,
    rule: str,
    book: str | None,
) -> None:
    if findings is None:
        return
    detail = {
        "product_code": line.product_code,
        "rule": rule,
        "ssp_book_code": book or "",
        "ssp_version_label": line.ssp_version_label or "",
        "stratification": line.stratification or "",
    }
    findings.append(Finding("SSP_KEY_NOT_FOUND", "ERROR", line.subject_key, detail, STAGE, None))


def _blocking(findings: Sequence[Finding]) -> bool:
    return any(finding.severity == "ERROR" for finding in findings)


def _raise_first_error(findings: Sequence[Finding]) -> None:
    errors = sorted((f for f in findings if f.severity == "ERROR"), key=Finding.sort_key)
    if errors:
        first = errors[0]
        raise EngineError(
            first.code,
            "the SSP of a line is blocked by a stage 05 finding",
            subject_key=first.subject_key,
            detail=first.detail,
        )


def _state(
    st: PricedState,
    obligations: Sequence[ObligationState],
    findings: Sequence[Finding],
    proposals: Sequence[ProposalOut] = (),
    pools: Sequence[targeted.Pool] = (),
) -> AllocatedState:
    identified = st.pob.identified
    cb = identified.canonical
    by_element: dict[str, dict[str, Quota]] = {}
    for pool in pools:
        by_element.setdefault(pool.element.view.estimate_key, {}).update(
            zip(pool.element.keys, pool.quotas, strict=True)
        )
    return AllocatedState(
        group_code=identified.group_code,
        inception_date=st.inception_date,
        contracts=identified.contracts,
        obligations=tuple(sorted(obligations, key=lambda ob: ob.subject_key)),
        events=cb.events,
        measure_events=cb.measure_events,
        ledger=cb.ledger,
        return_paths=st.return_paths,
        estimates=cb.estimates,
        tp_unconstrained=st.tp_unconstrained,
        specialist_targets=st.specialist_targets,
        proposals=tuple(
            sorted(proposals, key=lambda proposal: (proposal.kind, proposal.subject_key))
        ),
        time_triggers=st.pob.time_triggers,
        tp_history=(st.tp,),
        targeted_vc_quotas=MappingProxyType(
            {
                estimate_key: MappingProxyType(dict(sorted(quotas.items())))
                for estimate_key, quotas in sorted(by_element.items())
            }
        ),
        # S05-R-14 (rev 1.6; D-91): the inception quota opens each element's dated history.
        targeted_vc_quota_history=MappingProxyType(
            {
                estimate_key: MappingProxyType(
                    {
                        subject_key: ((st.inception_date, quota),)
                        for subject_key, quota in sorted(quotas.items())
                    }
                )
                for estimate_key, quotas in sorted(by_element.items())
            }
        ),
        refund_components=MappingProxyType({}),
        findings=tuple(sorted(findings, key=Finding.sort_key)),
    )
