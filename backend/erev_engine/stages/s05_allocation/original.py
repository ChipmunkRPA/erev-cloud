"""Stage 05 original columns and the first allocation segment of each obligation.

ENGINE_SPEC §5.2 (``AllocationSegment`` component ``FIXED``, cause ``INCEPTION``), S05-R-16
(original columns, REQ-ALC-008 ``allocation_adjustment``, REQ-SSP-014 revenue account snapshot),
trace node ``allocation_adjustment:<ob>:-``. Private to stage 05. Standard library only
(DG-ARC-02).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from fractions import Fraction
from types import MappingProxyType
from typing import Final

from erev_engine import royalties, usage
from erev_engine.bundle import SspEntryInput, SspRangeInput, ssp_range_key
from erev_engine.enums import ObligationKind, SspMethod, SspValueBasis
from erev_engine.errors import EngineError
from erev_engine.money import format_exact, round_half_up, to_fraction
from erev_engine.stages.s03_pob_builder import PobDraft
from erev_engine.stages.s04_transaction_price import PricedState
from erev_engine.stages.s05_allocation import provenance, targeted
from erev_engine.stages.s05_allocation.relative import REMAINDER, Resolved
from erev_engine.stages.state import (
    AllocationSegment,
    BookContext,
    MaterialRightTerms,
    ObligationState,
    ProgressBase,
    ProgressTotals,
    Quota,
    SegmentCause,
    SspResolution,
    disaggregation_tags,
)
from erev_engine.trace import SourceRef, TraceBuilder

__all__ = ["build", "emit_snapshot_nodes"]

REVENUE_ROLE: Final = "REVENUE"
ECHO: Final = "input.echo.v1"
UNIT_SSP: Final = "alloc.unit_ssp.v1"
LEGACY_RANGE: Final = "ssp.legacy_range.v1"
EXTEND: Final = "ssp.extend.v1"
CONVERT: Final = "ssp.convert.v1"
# T-CON-11 SSP range columns (SspResolution member → column → band-row member).
RANGE_COLUMNS: Final = (
    ("mid", "original_ssp_mid", "mid_value"),
    ("high", "original_ssp_high", "high_value"),
    ("low", "original_ssp_low", "low_value"),
)


def _realised_component(ctx: BookContext, draft: PobDraft) -> bool:
    """Whether stage 05 opens a ``PERIOD_VC`` marker segment for ``draft`` (S09-R-01; ENC-6): a
    ``RIGHT_TO_INVOICE`` obligation always (S09-R-18), a ``USAGE`` obligation under POL-240
    ``DERIVED`` (S09-R-19) — under ``ESTIMATE_MEASUREMENT_PERIOD_TP`` the fees are priced by the VC
    element and the obligation is a ``FIXED`` component alone (S09-R-20)."""
    method = str(draft.recognition_method)
    if method not in usage.REALISED_METHODS:
        return False
    if method == usage.USAGE:
        policy = ctx.policies.value(usage.TIER_MINIMUM_POLICY, contract=draft.contract_key)
        return policy != usage.ESTIMATE_MEASUREMENT_PERIOD_TP
    return True


def build(
    ctx: BookContext,
    st: PricedState,
    items: Sequence[Resolved],
    quotas: Sequence[Quota],
    tb: TraceBuilder,
    *,
    pools: Sequence[targeted.Pool] = (),
    weights: Mapping[str, Fraction] | None = None,
) -> tuple[ObligationState, ...]:
    """S05-R-16: one ``ObligationState`` per allocated obligation, with its snapshot and segment.

    ``quotas`` are the inception totals: the share of T plus the targeted shares of ``pools``
    (S05-R-14). ``weights`` maps each subject key to its S08-R-04 ``inception_weight`` (the
    selected SSP, or the residual R of the residual candidate; D-91); absent, the selected SSP.
    ``original_total_contract_price`` is ``total.posted`` of the inception build-up and
    ``original_total_contract_ssp`` Σ selected SSP, both over the combination group (the unit of
    account of 606-10-25-9). The first segment opens at the S02-R-04 basis and start of the
    contract; its unit SSP is SSP ÷ Q, its remaining SSP the SSP and its billing plan the stated
    price. ``allocation_adjustment`` = a_p − stated price (posted), with residue x_p − a_p; it reads
    the obligation's ``original_allocated_amount`` and targeted share nodes.
    """
    identified = st.pob.identified
    cb = identified.canonical
    minor_unit = ctx.currencies[ctx.txn_currency].minor_unit
    scale: int = 10**minor_unit
    total_price = Fraction(st.tp.total.posted, scale)
    total_ssp = sum((item.ssp.selected for item in items), Fraction(0))
    obligations: list[ObligationState] = []
    for item, quota in zip(items, quotas, strict=True):
        draft, resolution = item.draft, item.ssp
        header = cb.contracts[draft.contract_key].header
        basis, start = identified.inception_basis(draft.contract_key)
        segment = AllocationSegment(
            component="FIXED",
            effective_date=st.inception_date if basis == "INCEPTION" else start,
            event_key=None,
            cause=SegmentCause.INCEPTION,
            basis=basis,
            x_exact=quota.x_exact,
            a_posted=quota.a_posted,
            base_revenue_posted=0,
            base_revenue_exact=Fraction(0),
            base_progress=ProgressBase.zero(),
            totals=ProgressTotals(draft.quantity, None, draft.start_date, draft.end_date),
            progress_measure=draft.recognition_method.value,
            unit_ssp=resolution.selected / draft.quantity,
            remaining_ssp=resolution.selected,
            remaining_billing_plan=draft.stated_price,
            estimate_pair=(None, None),
            modification_boundary_no=0,
        )
        segments: tuple[AllocationSegment, ...] = (segment,)
        if royalties.bearing(
            str(draft.recognition_method),
            draft.contract_key,
            draft.obligation_key,
            draft.subject_key,
            cb.measure_events,
            cb.estimates,
        ):
            # ENGINE_SPEC_B S09-R-01 (ENC-8): the ROYALTY component opens with the obligation as an
            # empty marker segment; stage 09 realises its amounts from the statements and accrual
            # pins (X = A = the realised amount, S09-R-02), the amounts stage 04 prices (S04-R-06).
            segments = (
                segment,
                AllocationSegment(
                    component="ROYALTY",
                    effective_date=segment.effective_date,
                    event_key=None,
                    cause=SegmentCause.INCEPTION,
                    basis=basis,
                    x_exact=Fraction(0),
                    a_posted=0,
                    base_revenue_posted=0,
                    base_revenue_exact=Fraction(0),
                    base_progress=ProgressBase.zero(),
                    totals=segment.totals,
                    progress_measure=draft.recognition_method.value,
                    unit_ssp=None,
                    remaining_ssp=Fraction(0),
                    remaining_billing_plan=Fraction(0),
                    estimate_pair=(None, None),
                    modification_boundary_no=0,
                ),
            )
        if _realised_component(ctx, draft):
            # ENGINE_SPEC_B S09-R-01 (ENC-6): right-to-invoice amounts and POL-240 DERIVED usage
            # fees ride the PERIOD_VC component, opened with the obligation as an empty marker
            # segment; stage 09 realises them from the events (X = A = the amount, S09-R-02;
            # S09-R-18, S09-R-19), the amounts stage 04 prices (S04-R-06). The FIXED segment keeps
            # the stand-ready fee or minimum, measured by time elapsed.
            segments = (
                *segments,
                AllocationSegment(
                    component="PERIOD_VC",
                    effective_date=segment.effective_date,
                    event_key=None,
                    cause=SegmentCause.INCEPTION,
                    basis=basis,
                    x_exact=Fraction(0),
                    a_posted=0,
                    base_revenue_posted=0,
                    base_revenue_exact=Fraction(0),
                    base_progress=ProgressBase.zero(),
                    totals=segment.totals,
                    progress_measure=draft.recognition_method.value,
                    unit_ssp=None,
                    remaining_ssp=Fraction(0),
                    remaining_billing_plan=Fraction(0),
                    estimate_pair=(None, None),
                    modification_boundary_no=0,
                ),
            )
        overrides = dict(draft.account_overrides)
        if item.revenue_account is not None:
            overrides.setdefault(REVENUE_ROLE, item.revenue_account)
        terms = next(
            (
                right
                for right in header.material_rights
                if right.obligation_key == draft.obligation_key
            ),
            None,
        )
        product = cb.group.products.get(draft.product_code)
        cost = None if product is None else product.assurance_cost_per_unit
        shares = [
            targeted.share_node(pool.element.view.estimate_key, draft.subject_key)
            for pool in pools
            if pool.share(draft.subject_key) is not None
        ]
        links: tuple[str, str] | None = None
        if shares:
            # CV-50 (D-98 candidate 121): the columns publish the S05-R-10 total, summed over the
            # relative node and the targeted shares — the sum nodes are emitted here, under the
            # booking event, and the assembler links them (never the partial relative node).
            booking = provenance.booking_event_key(cb.events, draft.contract_key)
            if booking is None:
                raise EngineError(
                    "ENGINE_INVARIANT_VIOLATED",
                    "an allocated obligation has no CONTRACT_BOOKED event",
                    subject_key=draft.subject_key,
                    detail={"rule": "S05-R-10"},
                )
            links = provenance.emit_original_allocation(
                ctx,
                tb,
                booking,
                draft.subject_key,
                quota,
                exact_inputs=[f"original_allocated_exact:{draft.subject_key}:-", *shares],
                amount_inputs=[f"original_allocated_amount:{draft.subject_key}:-", *shares],
                rule="S05-R-10",
            )
        obligations.append(
            ObligationState(
                subject_key=draft.subject_key,
                contract_key=draft.contract_key,
                obligation_key=draft.obligation_key,
                obligation_kind=draft.obligation_kind,
                distinctness=draft.distinctness,
                satisfaction_pattern=draft.satisfaction_pattern,
                recognition_method=draft.recognition_method,
                ratable_convention=draft.ratable_convention,
                principal_agent=draft.principal_agent,
                licence_nature=draft.licence_nature,
                scope_flag=draft.scope_flag,
                start_date=draft.start_date,
                end_date=draft.end_date,
                recognition_start_date=draft.recognition_start_date,
                contracting_entity=draft.contracting_entity,
                performing_entity=draft.performing_entity,
                quantity=draft.quantity,
                resolved_ssp=resolution.selected,
                revenue_category=draft.revenue_category,
                dimensions=disaggregation_tags(
                    cb,
                    contract_key=draft.contract_key,
                    template_version_key=draft.template_version_key,
                    product_code=draft.product_code,
                    performing_entity=draft.performing_entity,
                    satisfaction_pattern=str(draft.satisfaction_pattern),
                    revenue_category=draft.revenue_category,
                ),
                account_overrides=MappingProxyType(dict(sorted(overrides.items()))),
                segments=segments,
                opening=None,
                terminated_on=None,
                template_version_key=draft.template_version_key,
                product_code=draft.product_code,
                sku_number=draft.sku_number,
                stratification=draft.stratification,
                series_increment_unit=draft.series_increment_unit,
                over_time_criterion=draft.over_time_criterion,
                warranty_type=draft.warranty_type,
                material_right=None
                if terms is None or draft.obligation_kind != ObligationKind.MATERIAL_RIGHT
                else MaterialRightTerms(terms, resolution.selected),
                ssp=resolution,
                original_quantity=draft.original_quantity,
                original_stated_price=draft.original_stated_price,
                stated_price=draft.stated_price,
                original_allocation=quota,
                # CV-47 (b): the producers of the inception quota — the relative node and the
                # targeted shares (S05-R-10 totals; D-98 candidate 117).
                original_allocation_nodes=(
                    f"original_allocated_exact:{draft.subject_key}:-",
                    *shares,
                ),
                original_allocation_links=links,  # CV-50 (D-98 121): the sum pair, or None
                original_total_contract_price=total_price,
                original_total_contract_ssp=total_ssp,
                is_vc_line=draft.is_vc_line,
                gross_to_net=draft.gross_to_net,
                lineage_pre_modification=(),
                assurance_cost_per_unit=None if cost is None else to_fraction(cost),
                last_modification_key=None,
                inception_weight=(
                    resolution.selected if weights is None else weights[draft.subject_key]
                ),
            )
        )
        # A merged obligation's stated price is the host's plus each merged candidate's (S03-R-13).
        prices = [f"stated_price:{key}:-" for key in (draft.subject_key, *item.merged)]
        signs = ["+", *("+" for _ in shares), *("-" for _ in prices)]
        tb.node(
            measure="allocation_adjustment",
            subject_key=draft.subject_key,
            period_key=None,
            value=quota.a_posted - round_half_up(draft.stated_price, minor_unit),
            currency=ctx.txn_currency,
            minor_unit=minor_unit,
            formula_id=REMAINDER,
            inputs=[f"original_allocated_amount:{draft.subject_key}:-", *shares, *prices],
            params={"role": "adjustment", "signs": ",".join(signs)},
            exact=quota.x_exact - draft.stated_price,
            narrative_key="alloc.largest_remainder",
        )
    emit_snapshot_nodes(ctx, st, items, tb)
    return tuple(obligations)


def emit_snapshot_nodes(
    ctx: BookContext, st: PricedState, items: Sequence[Resolved], tb: TraceBuilder
) -> None:
    """The version-state nodes of the T-CON-11 SSP snapshot and inception-total columns
    (DG-KRN-EXP-01; ENGINE_SPEC CV-50 links; D-97 (8)), one per obligation:

    ``ssp_midpoint_discount_ratio``, ``ssp_range_ratio``: ``input.echo.v1`` over the canonical
    ``ssp_entry`` member (CV-53). ``ssp_unit_list_price``: the echo of the canonical list price, or
    ``ssp.convert.v1`` over it and the POL-079 ``fx_rate`` source when a conversion applied.
    ``original_ssp_mid`` / ``_high`` / ``_low``: real calculation nodes over their canonical
    sources (Codex T1F-R1) — ``ssp.legacy_range.v1`` over the ``original_quantity`` node, the
    entry's list price, discount and range ratio (and the rate) for a ``legacy_range`` entry;
    ``ssp.extend.v1`` over the quantity node, the band row's ``<bound>_value`` (``SourceRef
    ssp_range`` ``<entry key>/<band_dimension>/<band_from>``), the list price for
    ``PERCENT_OF_LIST`` and the rate for a range entry; none for point, cost-plus or residual
    entries (the columns are NULL) and none for a merged obligation (S03-R-13 sums over parts; a
    documented exception). Absent members emit no node (the column is NULL).
    ``original_stated_price``: ``input.echo.v1`` over the stage 03 inception ``stated_price`` node.
    ``original_total_contract_price``: ``input.echo.v1`` over the group's inception build-up node
    ``transaction_price:<group>:-`` (S05-R-16). ``original_total_contract_ssp``: Σ of the
    obligations' ``original_ssp_selected`` nodes (``alloc.relative_ssp.v1`` role ``total``).
    ``original_unit_ssp``: ``alloc.unit_ssp.v1`` over the selected SSP node (the residual R node
    for a residual candidate, S05-R-12) and ``original_quantity``; none when Q = 0 (NULL).
    """
    minor_unit = ctx.currencies[ctx.txn_currency].minor_unit
    price_node = f"transaction_price:{st.group_key}:-"
    selected_nodes = [f"original_ssp_selected:{item.draft.subject_key}:-" for item in items]
    for item in items:
        draft, resolution = item.draft, item.ssp
        subject = draft.subject_key
        _emit_ssp_snapshot(ctx, tb, item, subject)
        if tb.value(f"stated_price:{subject}:-") is not None:
            tb.node(
                measure="original_stated_price",
                subject_key=subject,
                period_key=None,
                value=round_half_up(draft.original_stated_price, minor_unit),
                currency=ctx.txn_currency,
                minor_unit=minor_unit,
                formula_id=ECHO,
                inputs=[f"stated_price:{subject}:-"],
                params={"member": "stated_price"},
                exact=draft.original_stated_price,
                narrative_key=ECHO.rsplit(".v", 1)[0],
            )
        tb.node(
            measure="original_total_contract_price",
            subject_key=subject,
            period_key=None,
            value=st.tp.total.posted,
            currency=ctx.txn_currency,
            minor_unit=minor_unit,
            formula_id=ECHO,
            inputs=[price_node],
            params={"member": "transaction_price"},
            exact=st.tp.total.exact,
            narrative_key=ECHO.rsplit(".v", 1)[0],
        )
        tb.node(
            measure="original_total_contract_ssp",
            subject_key=subject,
            period_key=None,
            value=sum((other.ssp.selected for other in items), Fraction(0)),
            currency=ctx.txn_currency,
            minor_unit=None,
            formula_id="alloc.relative_ssp.v1",
            inputs=selected_nodes,
            params={"role": "total"},
            narrative_key="alloc.relative_ssp",
        )
        if draft.original_quantity != 0 and resolution.entry_key:
            selected = (
                f"residual_ssp:{subject}:-"
                if resolution.residual_candidate
                and tb.value(f"residual_ssp:{subject}:-") is not None
                else f"original_ssp_selected:{subject}:-"
            )
            chosen = tb.exact(selected)
            if chosen is not None:
                tb.node(
                    measure="original_unit_ssp",
                    subject_key=subject,
                    period_key=None,
                    value=chosen / draft.original_quantity,
                    currency=ctx.txn_currency,
                    minor_unit=None,
                    formula_id=UNIT_SSP,
                    inputs=[selected, f"original_quantity:{subject}:-"],
                    narrative_key=UNIT_SSP.rsplit(".v", 1)[0],
                )


def _entry_source(entry: SspEntryInput, member: str) -> SourceRef:
    value = getattr(entry, member)
    return SourceRef(
        "ssp_entry", entry.entry_key, {"member": member, "value": format_exact(to_fraction(value))}
    )


def _emit_ssp_snapshot(ctx: BookContext, tb: TraceBuilder, item: Resolved, subject: str) -> None:
    """The SSP snapshot nodes of one obligation (see ``emit_snapshot_nodes``)."""
    resolution, source = item.ssp, item.source
    if source is None or item.merged or not resolution.entry_key:
        return
    entry = source.entry
    quantity_node = f"original_quantity:{subject}:-"

    def node(
        column: str,
        value: Fraction,
        formula: str,
        inputs: list[str | SourceRef],
        params: dict[str, str],
    ) -> None:
        tb.node(
            measure=column,
            subject_key=subject,
            period_key=None,
            value=value,
            currency=None
            if column == "ssp_range_ratio" or column == "ssp_midpoint_discount_ratio"
            else ctx.txn_currency,
            minor_unit=None,
            formula_id=formula,
            inputs=inputs,
            params=params,
            narrative_key=formula.rsplit(".v", 1)[0],
        )

    for member, column in (
        ("midpoint_discount_ratio", "ssp_midpoint_discount_ratio"),
        ("range_ratio", "ssp_range_ratio"),
    ):
        value = getattr(resolution, member)
        if value is not None and getattr(entry, member) is not None:
            node(column, value, ECHO, [_entry_source(entry, member)], {"member": member})
    converted = source.factor != 1 and source.rate_source is not None
    if resolution.unit_list_price is not None and entry.unit_list_price is not None:
        list_source = _entry_source(entry, "unit_list_price")
        if converted and source.rate_source is not None:
            node(
                "ssp_unit_list_price",
                resolution.unit_list_price,
                CONVERT,
                [list_source, source.rate_source],
                {"rate_key": source.rate_source.ref_id},
            )
        else:
            node(
                "ssp_unit_list_price",
                resolution.unit_list_price,
                ECHO,
                [list_source],
                {"member": "unit_list_price"},
            )
    if tb.value(quantity_node) is None:
        return
    rate_inputs: list[str | SourceRef] = (
        [source.rate_source] if converted and source.rate_source is not None else []
    )
    row = source.row
    if (
        row is None
        and entry.ranges
        and len(entry.ranges) == 1
        and entry.ranges[0].band_dimension == "NONE"
    ):
        row = entry.ranges[0]  # a legacy_range entry that also carries its T-REF-31 row (S05-R-06)
    if row is not None and _row_matches(
        row, resolution, item.draft.line.quantity * source.factor, entry
    ):
        _emit_row_bounds(ctx, tb, item, subject, node, row, rate_inputs)
        return
    if entry.method == str(SspMethod.LEGACY_RANGE):
        if entry.unit_list_price is None or entry.midpoint_discount_ratio is None:
            return
        has_range = entry.range_ratio is not None
        for member, column, _ in RANGE_COLUMNS:
            value = getattr(resolution, member)
            if value is None or (member != "mid" and not has_range):
                continue
            inputs: list[str | SourceRef] = [
                quantity_node,
                _entry_source(entry, "unit_list_price"),
                _entry_source(entry, "midpoint_discount_ratio"),
            ]
            if has_range:
                inputs.append(_entry_source(entry, "range_ratio"))
            inputs.extend(rate_inputs)
            params = {
                "bound": member,
                "converted": "true" if rate_inputs else "false",
                "has_range": "true" if has_range else "false",
            }
            node(column, value, LEGACY_RANGE, inputs, params)
        return
    if source.row is not None:
        _emit_row_bounds(ctx, tb, item, subject, node, source.row, rate_inputs)


def _row_scale(entry: SspEntryInput, quantity_factor: Fraction) -> Fraction | None:
    scale = quantity_factor
    if entry.value_basis == str(SspValueBasis.PERCENT_OF_LIST):
        if entry.unit_list_price is None:
            return None
        scale *= to_fraction(entry.unit_list_price)
    return scale


def _row_matches(
    row: SspRangeInput, resolution: SspResolution, quantity_factor: Fraction, entry: SspEntryInput
) -> bool:
    """True when every stored bound equals a band-row member scaled by Q × factor (× list price
    under ``PERCENT_OF_LIST``): the T-REF-31 row is then the canonical source (Codex T1F-R1)."""
    scale = _row_scale(entry, quantity_factor)
    if scale is None:
        return False
    members = [getattr(row, name) for name in ("low_value", "mid_value", "high_value")]
    scaled = {scale * to_fraction(value) for value in members if value is not None}
    bounds = [
        value for value in (resolution.low, resolution.mid, resolution.high) if value is not None
    ]
    return bool(bounds) and all(value in scaled for value in bounds)


def _emit_row_bounds(
    ctx: BookContext,
    tb: TraceBuilder,
    item: Resolved,
    subject: str,
    node: Callable[[str, Fraction, str, list[str | SourceRef], dict[str, str]], None],
    row: SspRangeInput,
    rate_inputs: list[str | SourceRef],
) -> None:
    """``ssp.extend.v1`` over the quantity node, the band row's member (``SourceRef ssp_range``),
    the list price under ``PERCENT_OF_LIST`` and the rate: the operation over the canonical T-REF-31
    row (golden hardware: 8 × 90.0 = 720; Codex T1F-R1)."""
    resolution, source = item.ssp, item.source
    assert source is not None
    entry = source.entry
    quantity_node = f"original_quantity:{subject}:-"
    ref_id = ssp_range_key(entry.entry_key, row.band_dimension, row.band_from)
    scale = _row_scale(entry, item.draft.line.quantity * source.factor)
    if scale is None:
        return
    percent = entry.value_basis == str(SspValueBasis.PERCENT_OF_LIST)
    for member, column, _ in RANGE_COLUMNS:
        value = getattr(resolution, member)
        if value is None:
            continue
        # The band row member whose scaled value is the stored bound (a negative quantity swaps
        # low and high, S05-R-06).
        chosen = next(
            (
                row_member
                for row_member in ("low_value", "mid_value", "high_value")
                if getattr(row, row_member) is not None
                and scale * to_fraction(getattr(row, row_member)) == value
            ),
            None,
        )
        if chosen is None:
            raise EngineError(
                "ENGINE_INVARIANT_VIOLATED",
                "a SSP range snapshot value matches no band-row member",
                subject_key=subject,
                detail={"rule": "S05-R-06", "column": column, "entry_key": entry.entry_key},
            )
        row_value = to_fraction(getattr(row, chosen))
        inputs: list[str | SourceRef] = [
            quantity_node,
            SourceRef("ssp_range", ref_id, {"member": chosen, "value": format_exact(row_value)}),
        ]
        if percent:
            inputs.append(_entry_source(entry, "unit_list_price"))
        inputs.extend(rate_inputs)
        node(column, value, EXTEND, inputs, {"bound": member, "row_member": chosen})
