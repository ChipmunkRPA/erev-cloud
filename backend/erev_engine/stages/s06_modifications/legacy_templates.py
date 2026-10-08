"""Stage 06 legacy templates (ENGINE_SPEC §6.5 S06-R-28 to S06-R-32; POLICIES ALG-04 §2.5.7; D-17).

Under POL-100 ``USER_SELECTED_TEMPLATE`` every obligation of the modified contract takes the parity
treatment of the upload mode (S06-R-28). The templates run on exact state, and cents appear only at
posting (D-17). Before the event, for each obligation i:

- E_i = E_before(d); RemAlloc_i = X_i − E_i; RemQty_i = Q_i − net delivered;
- RemSSP_i = ``remaining_ssp`` − the units delivered since the boundary × ``unit_ssp``;
- SSPDel_i = Σ over the segments in force so far of the units delivered under each × its
  ``unit_ssp`` (legacy ``SSP Delivered - Cumulative``);
- Plan_i = ``remaining_billing_plan`` − the net billing since the boundary.

The templates:

- ``LEGACY_PROSPECTIVE`` (legacy 03 §3.4 to §3.6; ENB-8): RemQty′_i = RemQty_i + ModQty_i;
  w_i = max(0, RemSSP_i + mod SSP_i), or 0 when RemQty′_i = 0 (DEV-055); Pool = Σ RemAlloc +
  Σ ModBilling; X′_i = E_i + Pool × w_i ÷ Σw. A nondistinct obligation takes the catch-up E′_i =
  CumDel_i ÷ (CumDel_i + RemQty′_i) × X′_i (units share, POL-107); a distinct one keeps E_i. When
  Σw = 0 the pool is satisfied performance (DEV-054).
- ``LEGACY_RETROSPECTIVE`` (legacy 04 §3.4 to §3.6; ENB-6): CRS_i = max(0, RemSSP_i + mod SSP_i);
  TP_c = Σ RemAlloc + Σ ModBilling + Σ E; SSP_c = Σ CRS + Σ SSPDel; r_c = TP_c ÷ SSP_c. On every
  obligation, distinct or not (DEV-071), E′_i = r_c × SSPDel_i and RemAlloc′_i = r_c × CRS_i.
- ``LEGACY_POB_VC`` (legacy 05 §3.4, §3.5; ENB-7): on the targeted obligation only (DEV-056), A1 =
  RemAlloc_t + M and CU_t = (A1 + E_t) ÷ (RemSSP_t + SSPDel_t) × SSPDel_t − E_t. The billing plan
  moves by M (DEV-083).

The modification SSP clamps the line billing into the file version's range for the line quantity
(legacy 03 §3.1, 04 §3.3; POL-081 ``CLAMPED_MOD_PRICE``). The legacy sign-aware branch selects the
same bound as the band [low, high], and a quantity of 0 gives 0. Every obligation then takes the
S06-R-29 segment: basis ``PROSPECTIVE``, measure ``UNITS_SINCE_BOUNDARY``, x = E′ + RemAlloc′, and
A = largest_remainder(TP_c, [X_j], keys).

Nodes: ``mod_ssp@<event key>:<ob>:-`` (``mod.legacy.mod_ssp.v1``); ``allocated_exact@<event
key>:<ob>:-`` and ``allocated_amount@<event key>:<ob>:-`` (``mod.legacy.prospective.v1``,
``mod.legacy.retrospective.v1`` or ``mod.legacy.pob_vc.v1``). Private to stage 06. Standard library
only (DG-ARC-02).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from fractions import Fraction
from types import MappingProxyType
from typing import Final

from erev_engine import money
from erev_engine.enums import Distinctness
from erev_engine.errors import EngineError
from erev_engine.formulas import rational_param
from erev_engine.money import format_exact
from erev_engine.stages import s05_allocation
from erev_engine.stages.s01_canonicalize import contract_subject_key
from erev_engine.stages.s02_contract_identification import IdentifiedState
from erev_engine.stages.s03_pob_builder import PobDraft, RawLine
from erev_engine.stages.s06_modifications import segments
from erev_engine.stages.s06_modifications.classify import ModificationLine, ModificationView
from erev_engine.stages.state import (
    AllocatedState,
    AllocationSegment,
    BookContext,
    EventView,
    Finding,
    LedgerPoint,
    ObligationState,
    ProgressBase,
    ProgressTotals,
    SegmentCause,
    SspResolution,
)
from erev_engine.trace import ABSENT_ZERO_TOTAL, SourceRef, TraceBuilder

__all__ = [
    "BY_TEMPLATE",
    "MEASURE",
    "MOD_SSP_FORMULA",
    "POB_VC_FORMULA",
    "POLICY_CODE",
    "PROSPECTIVE_FORMULA",
    "RETROSPECTIVE_FORMULA",
    "ModSsp",
    "Outcome",
    "Position",
    "added",
    "added_mod_ssp",
    "amounts",
    "assert_moved",
    "emit_amounts",
    "emit_exact",
    "emit_mod_ssp",
    "mod_ssp",
    "pob_vc",
    "position",
    "prospective",
    "retrospective",
    "segment",
]

MOD_SSP_FORMULA: Final = "mod.legacy.mod_ssp.v1"
PROSPECTIVE_FORMULA: Final = "mod.legacy.prospective.v1"
RETROSPECTIVE_FORMULA: Final = "mod.legacy.retrospective.v1"
POB_VC_FORMULA: Final = "mod.legacy.pob_vc.v1"
POLICY_CODE: Final = "mod.catch_up_progress_basis"  # POL-107
BY_TEMPLATE: Final = "LEGACY_BY_TEMPLATE"
MEASURE: Final = "UNITS_SINCE_BOUNDARY"  # legacy 01 §3.7: remaining allocation per remaining unit
SEPARATOR: Final = "|"
_STAGE: Final = 6
_RULE: Final = "S06-R-28"


def _invariant(message: str, ev: EventView, **detail: str) -> EngineError:
    return EngineError(
        "ENGINE_INVARIANT_VIOLATED",
        message,
        subject_key=ev.contract_key,
        detail={"event_key": ev.event_key, **detail},
    )


def _finding(
    code: str,
    mod: ModificationView,
    subject_key: str,
    obligation_key: str | None,
    **detail: str,
) -> Finding:
    members = {"modification_key": mod.modification_key, "rule": _RULE, **detail}
    if obligation_key is not None:
        members["obligation_key"] = obligation_key
    event_key = None if mod.event is None else mod.event.event_key
    return Finding(code, "ERROR", subject_key, members, _STAGE, event_key)


def _total(values: Iterable[Fraction]) -> Fraction:
    return sum(values, Fraction(0))


def _net_delivered(point: LedgerPoint) -> Fraction:
    return point.delivered_cum - point.returned_cum


def _net_billed(point: LedgerPoint) -> Fraction:
    return point.billed_cum - point.credited_cum


@dataclass(frozen=True, slots=True)
class Position:
    """One obligation measured before a template (ENGINE_SPEC §6.5 preamble)."""

    subject_key: str
    obligation_key: str
    before: segments.Measured | None  # None for an obligation the template adds
    is_vc_line: bool
    revenue: Fraction  # E_i
    remaining_allocation: Fraction  # RemAlloc_i = X_i − E_i
    remaining_quantity: Fraction  # RemQty_i
    remaining_ssp: Fraction  # RemSSP_i
    ssp_delivered: Fraction  # SSPDel_i
    billing_plan: Fraction  # Plan_i
    delivered: Fraction  # CumDel_i: net units delivered since inception
    nondistinct: bool  # E-105 ``nondistinct``: the catch-up scope of the prospective template
    original_posted: int  # original posted allocation: the weight of satisfied performance


def _boundary_point(
    st: AllocatedState, ob: ObligationState, seg: AllocationSegment, ev: EventView
) -> LedgerPoint:
    """The quantity ledger strictly before the boundary event of ``seg``; zero at inception."""
    if seg.event_key is None:
        return LedgerPoint.zero()
    boundary = next((item for item in st.events if item.event_key == seg.event_key), None)
    if boundary is None:
        raise _invariant(
            "the boundary event of a segment is absent",
            ev,
            rule="CV-60",
            obligation_key=ob.obligation_key,
        )
    return st.ledger.at(ob.subject_key, before=boundary)


def position(
    st: AllocatedState, ob: ObligationState, before: segments.Measured, ev: EventView
) -> Position:
    """E_i, RemAlloc_i, RemQty_i, RemSSP_i, SSPDel_i and Plan_i of ``ob`` before ``ev``.

    The templates measure progress by units (S06-R-29), so another measure fails closed, and so
    does an opening balance, whose SSP delivered before the cutover the ledger does not carry.
    """
    seg = before.segment
    if seg.progress_measure not in segments.UNIT_MEASURES:
        raise _invariant(
            "the legacy templates measure progress by units",
            ev,
            rule="S06-R-29",
            obligation_key=ob.obligation_key,
            progress_measure=seg.progress_measure,
        )
    order_keys = {item.event_key: item.order_key for item in st.events}
    chain: list[AllocationSegment] = []
    for item in ob.segments:
        if item.component != segments.FIXED or item.effective_date > ev.effective_date:
            continue
        if item.event_key is not None:
            order_key = order_keys.get(item.event_key)
            if order_key is None:
                raise _invariant(
                    "the boundary event of a segment is absent",
                    ev,
                    rule="CV-60",
                    obligation_key=ob.obligation_key,
                )
            if order_key >= ev.order_key:
                continue
        if item.cause == SegmentCause.OPENING_BALANCE:
            raise _invariant(
                "the SSP delivered before an opening balance is not carried",
                ev,
                rule="S06-R-28",
                obligation_key=ob.obligation_key,
            )
        chain.append(item)
    if not chain or chain[-1] != seg:
        raise _invariant(
            "the segment in force is not the last segment before the event",
            ev,
            rule="CV-60",
            obligation_key=ob.obligation_key,
        )
    delivered = Fraction(0)
    for index, item in enumerate(chain):
        start = _boundary_point(st, ob, item, ev)
        last = index == len(chain) - 1
        end = before.point if last else _boundary_point(st, ob, chain[index + 1], ev)
        units = _net_delivered(end) - _net_delivered(start)
        if units != 0:
            delivered += units * (item.unit_ssp or Fraction(0))
    boundary = _boundary_point(st, ob, seg, ev)
    since = _net_delivered(before.point) - _net_delivered(boundary)
    billed = _net_billed(before.point) - _net_billed(boundary)
    return Position(
        subject_key=ob.subject_key,
        obligation_key=ob.obligation_key,
        before=before,
        is_vc_line=ob.is_vc_line,
        revenue=before.exact,
        remaining_allocation=seg.x_exact - before.exact,
        remaining_quantity=before.remaining_quantity,
        remaining_ssp=seg.remaining_ssp - since * (seg.unit_ssp or Fraction(0)),
        ssp_delivered=delivered,
        billing_plan=seg.remaining_billing_plan - billed,
        delivered=before.delivered,
        nondistinct=ob.distinctness == Distinctness.NONDISTINCT,
        original_posted=ob.original_allocation.a_posted,
    )


def added(draft: PobDraft) -> Position:
    """An obligation a template adds: nothing allocated, delivered or billed (S06-R-31)."""
    zero = Fraction(0)
    return Position(
        subject_key=draft.subject_key,
        obligation_key=draft.obligation_key,
        before=None,
        is_vc_line=draft.is_vc_line,
        revenue=zero,
        remaining_allocation=zero,
        remaining_quantity=zero,
        remaining_ssp=zero,
        ssp_delivered=zero,
        billing_plan=zero,
        delivered=zero,
        nondistinct=draft.distinctness == Distinctness.NONDISTINCT,
        original_posted=0,
    )


@dataclass(frozen=True, slots=True)
class ModSsp:
    """The modification SSP of one obligation's lines (``mod_ssp`` of S06-R-28)."""

    subject_key: str
    value: Fraction
    quantities: tuple[Fraction, ...]
    billings: tuple[Fraction, ...]
    lows: tuple[Fraction, ...]
    highs: tuple[Fraction, ...]
    sources: tuple[SourceRef, ...]
    resolution: SspResolution | None  # the band of the last resolved line (S06-R-31)


def _band(found: SspResolution) -> tuple[Fraction, Fraction]:
    if found.low is None or found.high is None:
        return found.selected, found.selected
    return min(found.low, found.high), max(found.low, found.high)


def _mod_ssp(
    subject_key: str,
    rows: Sequence[tuple[Fraction, Fraction, Fraction, Fraction]],
    sources: Sequence[SourceRef],
    resolution: SspResolution | None,
) -> ModSsp:
    value = _total(min(max(billing, low), high) for _, billing, low, high in rows)
    return ModSsp(
        subject_key,
        value,
        tuple(row[0] for row in rows),
        tuple(row[1] for row in rows),
        tuple(row[2] for row in rows),
        tuple(row[3] for row in rows),
        tuple(sources),
        resolution,
    )


def _reference(found: SspResolution, member: str) -> SourceRef:
    detail = {"member": member, "value": format_exact(found.selected)}
    return SourceRef(
        "ssp_range" if found.range_key is not None else "ssp_entry",
        found.range_key or found.entry_key or "-",
        detail,
    )


def mod_ssp(
    ctx: BookContext,
    identified: IdentifiedState,
    ob: ObligationState,
    lines: Sequence[ModificationLine],
    ev: EventView,
    findings: list[Finding],
) -> ModSsp | None:
    """The clamped modification SSP of the lines on an existing obligation (S06-R-28).

    Each line is priced with the upload's SSP version (POL-080 parity), else the obligation's. A
    ``VC_LINE`` obligation or a line of quantity 0 gives 0 without a lookup. ``None`` when a
    finding blocks.
    """
    d = ev.effective_date
    rows: list[tuple[Fraction, Fraction, Fraction, Fraction]] = []
    sources: list[SourceRef] = []
    resolution: SspResolution | None = None
    for index, line in enumerate(lines):
        quantity, billing = line.quantity_delta, line.consideration_delta
        if ob.is_vc_line or quantity == 0:
            rows.append((quantity, billing, Fraction(0), Fraction(0)))
            continue
        product_code = line.product_code or ob.product_code
        if product_code is None:
            raise ValueError(f"{ob.subject_key}: an obligation without a product has no SSP")
        stratification = line.members.get("stratification")
        label = line.members.get("ssp_version_label")
        stored_label = None if ob.ssp is None else ob.ssp.version_label
        raw = RawLine(
            contract_key=ob.contract_key,
            obligation_key=ob.obligation_key,
            product_code=product_code,
            stratification=(
                stratification if isinstance(stratification, str) else ob.stratification
            ),
            quantity=quantity,
            stated_price=billing,
            line_start_date=ob.start_date,
            line_end_date=ob.end_date,
            truncated_end_date=None,
            pricing_date=d,
            template_date=d,
            performing_entity=ob.performing_entity,
            ssp_version_label=label if isinstance(label, str) else stored_label,
            account_overrides=MappingProxyType({}),
            scope_flag=ob.scope_flag,
            out_of_scope_amount=None,
            bundle_parent_obligation_key=None,
            bundle_product_code=None,
            memos=MappingProxyType({}),
            price_basis="PRICE_LINE",
            split=None,
        )
        found = s05_allocation.resolve_ssp(
            ctx, raw, d, billing, findings=findings, identified=identified
        )
        if found is None:
            return None
        low, high = _band(found)
        rows.append((quantity, billing, low, high))
        sources.append(_reference(found, f"line:{index}"))
        resolution = found
    return _mod_ssp(ob.subject_key, rows, sources, resolution)


def added_mod_ssp(
    ctx: BookContext,
    identified: IdentifiedState,
    draft: PobDraft,
    ev: EventView,
    findings: list[Finding],
) -> ModSsp | None:
    """The clamped modification SSP of an obligation a template adds (S06-R-28, S06-R-31)."""
    quantity, billing = draft.quantity, draft.stated_price
    if draft.is_vc_line or quantity == 0:
        return _mod_ssp(
            draft.subject_key, [(quantity, billing, Fraction(0), Fraction(0))], (), None
        )
    found = s05_allocation.resolve_ssp(
        ctx, draft, ev.effective_date, billing, findings=findings, identified=identified
    )
    if found is None:
        return None
    low, high = _band(found)
    rows = [(quantity, billing, low, high)]
    return _mod_ssp(draft.subject_key, rows, (_reference(found, "added"),), found)


@dataclass(frozen=True, slots=True)
class Outcome:
    """One obligation after a template."""

    position: Position
    quantity_change: Fraction  # Σ ModQty
    consideration_change: Fraction  # Σ ModBilling
    mod_ssp: Fraction
    remaining_quantity: Fraction  # RemQty′
    remaining_ssp: Fraction  # RemSSP′
    billing_plan: Fraction  # Plan′
    revenue: Fraction  # E′
    x_exact: Fraction  # E′ + RemAlloc′
    targeted: bool  # a line names the obligation


def _check_remaining(
    mod: ModificationView,
    item: Position,
    remaining_quantity: Fraction,
    billing_plan: Fraction,
    findings: list[Finding],
) -> None:
    """``MOD_REMAINING_NEGATIVE``: RemQty < 0, or Plan < 0 on a line other than a VC line."""
    if remaining_quantity < 0 or (billing_plan < 0 and not item.is_vc_line):
        findings.append(
            _finding(
                "MOD_REMAINING_NEGATIVE",
                mod,
                item.subject_key,
                item.obligation_key,
                remaining_quantity=format_exact(remaining_quantity),
                remaining_billing_plan=format_exact(billing_plan),
            )
        )


def _blocking(findings: Sequence[Finding]) -> bool:
    return any(finding.severity == "ERROR" for finding in findings)


def retrospective(
    mod: ModificationView,
    positions: Sequence[Position],
    lines_on: Mapping[str, Sequence[ModificationLine]],
    ssp: Mapping[str, ModSsp],
    findings: list[Finding],
) -> tuple[Outcome, ...] | None:
    """``legacy_retrospective`` of S06-R-28 over every obligation; ``None`` when a finding blocks.

    SSP_c = 0 yields ``NON_FINITE_AMOUNT``. An obligation with CRS_i + SSPDel_i = 0 but E_i ≠ 0
    has no progress share, and the template would reverse its revenue: ``MOD_PROGRESS_UNDEFINED``
    (DEV-059).
    """
    staged: list[tuple[Position, Fraction, Fraction, Fraction, Fraction, Fraction, Fraction]] = []
    for item in positions:
        lines = lines_on.get(item.obligation_key, ())
        quantity = _total(line.quantity_delta for line in lines)
        billing = _total(line.consideration_delta for line in lines)
        found = ssp.get(item.subject_key)
        clamped = Fraction(0) if found is None else found.value
        remaining_quantity = item.remaining_quantity + quantity
        current_ssp = max(Fraction(0), item.remaining_ssp + clamped)
        plan = item.billing_plan + billing
        _check_remaining(mod, item, remaining_quantity, plan, findings)
        staged.append((item, quantity, billing, clamped, remaining_quantity, current_ssp, plan))
    price = _total(row[0].remaining_allocation + row[2] + row[0].revenue for row in staged)
    total_ssp = _total(row[5] + row[0].ssp_delivered for row in staged)
    if total_ssp == 0:
        findings.append(
            _finding(
                "NON_FINITE_AMOUNT",
                mod,
                contract_subject_key(mod.contract_key),
                None,
                transaction_price=format_exact(price),
            )
        )
    for row in staged:
        if row[5] + row[0].ssp_delivered == 0 and row[0].revenue != 0:
            findings.append(
                _finding(
                    "MOD_PROGRESS_UNDEFINED",
                    mod,
                    row[0].subject_key,
                    row[0].obligation_key,
                    revenue=format_exact(row[0].revenue),
                )
            )
    if _blocking(findings):
        return None
    ratio = price / total_ssp
    return tuple(
        Outcome(
            position=item,
            quantity_change=quantity,
            consideration_change=billing,
            mod_ssp=clamped,
            remaining_quantity=remaining_quantity,
            remaining_ssp=current_ssp,
            billing_plan=plan,
            revenue=ratio * item.ssp_delivered,
            x_exact=ratio * (current_ssp + item.ssp_delivered),
            targeted=item.obligation_key in lines_on,
        )
        for item, quantity, billing, clamped, remaining_quantity, current_ssp, plan in staged
    )


def prospective(
    mod: ModificationView,
    positions: Sequence[Position],
    lines_on: Mapping[str, Sequence[ModificationLine]],
    ssp: Mapping[str, ModSsp],
    findings: list[Finding],
) -> tuple[Outcome, ...] | None:
    """``legacy_prospective`` of S06-R-28 over every obligation; ``None`` when a finding blocks.

    RemQty′ = RemQty + ModQty and Plan′ = Plan + ModBilling. The weight w = max(0, RemSSP + mod
    SSP), set to 0 when RemQty′ = 0 (DEV-055), is RemSSP′, and X′ = E + Pool × w ÷ Σw. A
    nondistinct obligation takes E′ = CumDel ÷ (CumDel + RemQty′) × X′; with a zero divisor it keeps
    E, which must be 0 (``MOD_PROGRESS_UNDEFINED``; DEV-059). A distinct obligation keeps E. When
    Σw = 0 the pool is satisfied performance and no catch-up is taken (DEV-054): the obligations
    complete after the event (RemQty′ = 0) with an original posted allocation receive Pool × that
    allocation ÷ its sum, with E′ = X′, and a non-zero pool nothing absorbs yields
    ``NON_FINITE_AMOUNT``. A negative X′ yields ``VC_ALLOCATION_NEGATIVE`` (S06-R-22).
    """
    staged: list[tuple[Position, Fraction, Fraction, Fraction, Fraction, Fraction, Fraction]] = []
    for item in positions:
        lines = lines_on.get(item.obligation_key, ())
        quantity = _total(line.quantity_delta for line in lines)
        billing = _total(line.consideration_delta for line in lines)
        found = ssp.get(item.subject_key)
        clamped = Fraction(0) if found is None else found.value
        remaining_quantity = item.remaining_quantity + quantity
        weight = max(Fraction(0), item.remaining_ssp + clamped)
        if remaining_quantity == 0:
            weight = Fraction(0)  # DEV-055: stranded SSP joins the pool with weight 0
        plan = item.billing_plan + billing
        _check_remaining(mod, item, remaining_quantity, plan, findings)
        staged.append((item, quantity, billing, clamped, remaining_quantity, weight, plan))
    pool = _total(row[0].remaining_allocation + row[2] for row in staged)
    total_weight = _total(row[5] for row in staged)
    shares: dict[str, Fraction] = {}
    receivers: set[str] = set()
    if total_weight != 0:
        shares = {row[0].subject_key: pool * row[5] / total_weight for row in staged}
    else:
        members = [row[0] for row in staged if row[4] == 0 and row[0].original_posted > 0]
        basis = sum(item.original_posted for item in members)
        if basis != 0:
            receivers = {item.subject_key for item in members}
            shares = {item.subject_key: pool * item.original_posted / basis for item in members}
        elif pool != 0:
            findings.append(
                _finding(
                    "NON_FINITE_AMOUNT",
                    mod,
                    contract_subject_key(mod.contract_key),
                    None,
                    pool=format_exact(pool),
                )
            )
    outcomes: list[Outcome] = []
    for item, quantity, billing, clamped, remaining_quantity, weight, plan in staged:
        x_exact = item.revenue + shares.get(item.subject_key, Fraction(0))
        divisor = item.delivered + remaining_quantity
        if item.subject_key in receivers:
            revenue = x_exact  # complete after the event (S06-R-09)
        elif total_weight == 0 or not item.nondistinct:
            revenue = item.revenue
        elif divisor != 0:
            revenue = item.delivered / divisor * x_exact
        else:
            revenue = item.revenue
            if item.revenue != 0:
                findings.append(
                    _finding(
                        "MOD_PROGRESS_UNDEFINED",
                        mod,
                        item.subject_key,
                        item.obligation_key,
                        revenue=format_exact(item.revenue),
                    )
                )
        if x_exact < 0:
            findings.append(
                _finding(
                    "VC_ALLOCATION_NEGATIVE",
                    mod,
                    item.subject_key,
                    item.obligation_key,
                    allocation=format_exact(x_exact),
                    rule="S06-R-22",
                )
            )
        outcomes.append(
            Outcome(
                position=item,
                quantity_change=quantity,
                consideration_change=billing,
                mod_ssp=clamped,
                remaining_quantity=remaining_quantity,
                remaining_ssp=weight,
                billing_plan=plan,
                revenue=revenue,
                x_exact=x_exact,
                targeted=item.obligation_key in lines_on,
            )
        )
    if _blocking(findings):
        return None
    return tuple(outcomes)


def pob_vc(
    mod: ModificationView,
    positions: Sequence[Position],
    lines_on: Mapping[str, Sequence[ModificationLine]],
    findings: list[Finding],
) -> tuple[Outcome, ...] | None:
    """``legacy_pob_vc`` of S06-R-28 on the targeted obligations; ``None`` when a finding blocks.

    A line with a quantity yields ``VC_QUANTITY_NOT_ALLOWED``, a VC line target
    ``VC_TARGET_INVALID``, and A1 + E_t < 0 ``VC_ALLOCATION_NEGATIVE`` (DEV-040). Untargeted
    obligations keep E and the remaining allocation, with no latent true-up (DEV-056).
    """
    outcomes: list[Outcome] = []
    for item in positions:
        lines = lines_on.get(item.obligation_key, ())
        if not lines:
            _check_remaining(mod, item, item.remaining_quantity, item.billing_plan, findings)
            outcomes.append(
                Outcome(
                    position=item,
                    quantity_change=Fraction(0),
                    consideration_change=Fraction(0),
                    mod_ssp=Fraction(0),
                    remaining_quantity=item.remaining_quantity,
                    remaining_ssp=item.remaining_ssp,
                    billing_plan=item.billing_plan,
                    revenue=item.revenue,
                    x_exact=item.revenue + item.remaining_allocation,
                    targeted=False,
                )
            )
            continue
        quantity = _total(line.quantity_delta for line in lines)
        if any(line.quantity_delta != 0 for line in lines):
            findings.append(
                _finding(
                    "VC_QUANTITY_NOT_ALLOWED",
                    mod,
                    item.subject_key,
                    item.obligation_key,
                    quantity_delta=format_exact(quantity),
                )
            )
        if item.is_vc_line:
            findings.append(
                _finding("VC_TARGET_INVALID", mod, item.subject_key, item.obligation_key)
            )
        change = _total(line.consideration_delta for line in lines)
        allocation = item.remaining_allocation + change  # A1
        plan = item.billing_plan + change  # DEV-083: the billing plan moves with the price
        total = allocation + item.revenue
        if total < 0:
            findings.append(
                _finding(
                    "VC_ALLOCATION_NEGATIVE",
                    mod,
                    item.subject_key,
                    item.obligation_key,
                    allocation=format_exact(total),
                )
            )
        _check_remaining(mod, item, item.remaining_quantity, plan, findings)
        current_ssp = max(Fraction(0), item.remaining_ssp)
        weight = current_ssp + item.ssp_delivered  # W
        revenue = item.revenue if weight == 0 else total / weight * item.ssp_delivered
        outcomes.append(
            Outcome(
                position=item,
                quantity_change=Fraction(0),
                consideration_change=change,
                mod_ssp=Fraction(0),
                remaining_quantity=item.remaining_quantity,
                remaining_ssp=current_ssp,
                billing_plan=plan,
                revenue=revenue,
                x_exact=total,
                targeted=True,
            )
        )
    if _blocking(findings):
        return None
    return tuple(outcomes)


def amounts(outcomes: Sequence[Outcome], tp_minor: int) -> dict[str, int]:
    """A_i = largest_remainder(TP_c in minor units, [X_j], keys)[i] (S06-R-29; PJR-1)."""
    keys = [item.position.subject_key for item in outcomes]
    values = [item.x_exact for item in outcomes]
    if tp_minor == 0 and _total(values) == 0:
        return dict.fromkeys(keys, 0)
    return dict(zip(keys, money.largest_remainder(tp_minor, values, keys), strict=True))


def segment(
    ctx: BookContext,
    ev: EventView,
    outcome: Outcome,
    a_posted: int,
    *,
    point: LedgerPoint,
    source: AllocationSegment | None,
    totals: ProgressTotals,
) -> AllocationSegment:
    """The S06-R-29 segment of one obligation after a template.

    ``base_revenue_posted`` is C at the boundary per CV-63: ``cumulative_posted``(X, A, E′ ÷ X).
    ``modification_boundary_no`` is carried, because no template is recorded as a 25-13(a)
    boundary (L2-3-Q-37).
    """
    x_exact, revenue = outcome.x_exact, outcome.revenue
    obligation_key = outcome.position.obligation_key
    if x_exact == 0:
        if a_posted != 0:
            raise _invariant(
                "a zero exact allocation carries a posted allocation",
                ev,
                rule="CV-63",
                obligation_key=obligation_key,
            )
        base_posted = 0
    else:
        ratio = revenue / x_exact
        if not 0 <= ratio <= 1:
            raise _invariant(
                "the revenue after a template lies outside its allocation",
                ev,
                rule="CV-63",
                obligation_key=obligation_key,
            )
        base_posted = money.cumulative_posted(x_exact, a_posted, ratio, segments.minor_unit(ctx))
    quantity = outcome.remaining_quantity
    return AllocationSegment(
        component=segments.FIXED,
        effective_date=ev.effective_date,
        event_key=ev.event_key,
        cause=SegmentCause.MODIFICATION,
        basis=segments.PROSPECTIVE,
        x_exact=x_exact,
        a_posted=a_posted,
        base_revenue_posted=base_posted,
        base_revenue_exact=revenue,
        base_progress=ProgressBase(
            _net_delivered(point), point.costs_cum, point.hours_cum, ev.effective_date
        ),
        totals=totals,
        progress_measure=MEASURE,
        unit_ssp=Fraction(0) if quantity == 0 else outcome.remaining_ssp / quantity,
        remaining_ssp=outcome.remaining_ssp,
        remaining_billing_plan=outcome.billing_plan,
        estimate_pair=(None, None),
        modification_boundary_no=0 if source is None else source.modification_boundary_no,
    )


def assert_moved(ev: EventView, outcomes: Sequence[Outcome], consideration: Fraction) -> None:
    """S06-INV-04 for templates: Σ (x′ − x) = TP_c after − TP_c before = Σ ModBilling, exactly."""
    moved = _total(
        item.x_exact
        - (Fraction(0) if item.position.before is None else item.position.before.segment.x_exact)
        for item in outcomes
    )
    if moved != consideration:
        raise _invariant(
            "the exact allocations moved by the template differ from its consideration",
            ev,
            invariant="S06-INV-04",
            moved=format_exact(moved),
            expected=format_exact(consideration),
        )


def _join(values: Iterable[Fraction]) -> str:
    return SEPARATOR.join(rational_param(value) for value in values)


def emit_mod_ssp(tb: TraceBuilder, ev: EventView, item: ModSsp, currency: str) -> str:
    """``mod_ssp@<event key>:<ob>:-``: Σ clamp(billing, low, high) over the lines."""
    params = {
        "as_of": ev.effective_date.isoformat(),
        "billings": _join(item.billings),
        "highs": _join(item.highs),
        "lows": _join(item.lows),
        "quantities": _join(item.quantities),
        "sources": str(len(item.sources)),
    }
    return tb.node(
        measure=f"mod_ssp@{ev.event_key}",
        subject_key=item.subject_key,
        period_key=None,
        value=item.value,
        currency=currency,  # an exact amount in transaction currency (lane ENG-T1F)
        minor_unit=None,
        formula_id=MOD_SSP_FORMULA,
        inputs=list(item.sources),
        params=params,
        narrative_key=MOD_SSP_FORMULA.rsplit(".v", 1)[0],
    )


def emit_total_and_weight(
    tb: TraceBuilder,
    ev: EventView,
    formula_id: str,
    outcomes: Sequence[Outcome],
    ssp_nodes: Mapping[str, str],
    currency: str,
    subject: str,
) -> tuple[str, str]:
    """``original_total_contract_ssp@<event key>:<ob>:-`` and ``allocation_weight@<event
    key>:<ob>:-`` of an obligation the template CREATES (CV-50 rev 1.29; D-98 candidate 124):
    the template formula re-evaluating from the same per-key parameters as its
    ``allocated_exact@`` nodes — role ``total_ssp`` (Σ RemSSP′, the stored total) and role
    ``weight`` (the template's own ratio basis: retrospective (CRS + SSPDel) ÷ SSP_c, prospective
    w ÷ Σw — never the stored total); the ``mod_ssp`` nodes of ``line_keys`` as lineage. A
    prospective template with Σw = 0 (DEV-054: pool 0 / completed receivers) has NO ratio: the
    total node (0) is emitted and ``trace.ABSENT_ZERO_TOTAL`` is returned in place of a
    weight node — an explicit contract-permitted absence, never a manufactured 0 ÷ 0."""
    if formula_id not in (PROSPECTIVE_FORMULA, RETROSPECTIVE_FORMULA):
        raise ValueError(f"{formula_id}: the template creates no obligation")
    as_of = ev.effective_date.isoformat()
    keys = [item.position.subject_key for item in outcomes]
    line_keys = [key for key in keys if key in ssp_nodes]
    common: dict[str, str] = {
        "as_of": as_of,
        "billing": _join(item.consideration_change for item in outcomes),
        "keys": SEPARATOR.join(keys),
        "line_keys": SEPARATOR.join(line_keys),
        "mod_ssp": _join(item.mod_ssp for item in outcomes),
        "remaining_allocation": _join(item.position.remaining_allocation for item in outcomes),
        "remaining_ssp": _join(item.position.remaining_ssp for item in outcomes),
        "revenue": _join(item.position.revenue for item in outcomes),
    }
    if formula_id == PROSPECTIVE_FORMULA:
        common.update(
            {
                "delivered": _join(item.position.delivered for item in outcomes),
                "nondistinct": SEPARATOR.join(
                    "true" if item.position.nondistinct else "false" for item in outcomes
                ),
                "original_posted": SEPARATOR.join(
                    str(item.position.original_posted) for item in outcomes
                ),
                "quantity": _join(item.quantity_change for item in outcomes),
                "remaining_quantity": _join(item.position.remaining_quantity for item in outcomes),
            }
        )
        total = sum((item.remaining_ssp for item in outcomes), Fraction(0))
        own = next(item.remaining_ssp for item in outcomes if item.position.subject_key == subject)
        ratio = None if total == 0 else own / total  # DEV-054: Σw = 0 → no ratio (no 0 ÷ 0)
    else:
        common["ssp_delivered"] = _join(item.position.ssp_delivered for item in outcomes)
        total = sum((item.remaining_ssp for item in outcomes), Fraction(0))
        basis = sum(
            (item.remaining_ssp + item.position.ssp_delivered for item in outcomes), Fraction(0)
        )
        own_item = next(item for item in outcomes if item.position.subject_key == subject)
        ratio = (own_item.remaining_ssp + own_item.position.ssp_delivered) / basis
    inputs = [ssp_nodes[name] for name in line_keys]
    total_node = tb.node(
        measure=f"original_total_contract_ssp@{ev.event_key}",
        subject_key=subject,
        period_key=None,
        value=total,
        currency=currency,
        minor_unit=None,
        formula_id=formula_id,
        inputs=inputs,
        params={**common, "key": subject, "role": "total_ssp"},
        narrative_key=formula_id.rsplit(".v", 1)[0],
    )
    if ratio is None:
        return total_node, ABSENT_ZERO_TOTAL
    weight_node = tb.node(
        measure=f"allocation_weight@{ev.event_key}",
        subject_key=subject,
        period_key=None,
        value=ratio,
        currency=None,
        minor_unit=None,
        formula_id=formula_id,
        inputs=inputs,
        params={**common, "key": subject, "role": "weight"},
        narrative_key=formula_id.rsplit(".v", 1)[0],
    )
    return total_node, weight_node


def emit_exact(
    tb: TraceBuilder,
    ev: EventView,
    formula_id: str,
    outcomes: Sequence[Outcome],
    ssp_nodes: Mapping[str, str],
    currency: str,
) -> dict[str, str]:
    """``allocated_exact@<event key>:<ob>:-``: X′ of every obligation under the prospective and
    retrospective templates, or of each targeted obligation under the POB-specific template."""
    as_of = ev.effective_date.isoformat()
    nodes: dict[str, str] = {}
    if formula_id == PROSPECTIVE_FORMULA:
        keys = [item.position.subject_key for item in outcomes]
        line_keys = [key for key in keys if key in ssp_nodes]
        common = {
            "as_of": as_of,
            "billing": _join(item.consideration_change for item in outcomes),
            "delivered": _join(item.position.delivered for item in outcomes),
            "keys": SEPARATOR.join(keys),
            "line_keys": SEPARATOR.join(line_keys),
            "mod_ssp": _join(item.mod_ssp for item in outcomes),
            "nondistinct": SEPARATOR.join(
                "true" if item.position.nondistinct else "false" for item in outcomes
            ),
            "original_posted": SEPARATOR.join(
                str(item.position.original_posted) for item in outcomes
            ),
            "quantity": _join(item.quantity_change for item in outcomes),
            "remaining_allocation": _join(item.position.remaining_allocation for item in outcomes),
            "remaining_quantity": _join(item.position.remaining_quantity for item in outcomes),
            "remaining_ssp": _join(item.position.remaining_ssp for item in outcomes),
            "revenue": _join(item.position.revenue for item in outcomes),
            "role": "exact",
        }
        for item in outcomes:
            key = item.position.subject_key
            nodes[key] = tb.node(
                measure=f"allocated_exact@{ev.event_key}",
                subject_key=key,
                period_key=None,
                value=item.x_exact,
                currency=currency,
                minor_unit=None,
                formula_id=formula_id,
                inputs=[ssp_nodes[name] for name in line_keys],
                params={**common, "key": key, "revenue_after": rational_param(item.revenue)},
                narrative_key=formula_id.rsplit(".v", 1)[0],
            )
        return nodes
    if formula_id == RETROSPECTIVE_FORMULA:
        keys = [item.position.subject_key for item in outcomes]
        line_keys = [key for key in keys if key in ssp_nodes]
        common = {
            "as_of": as_of,
            "billing": _join(item.consideration_change for item in outcomes),
            "keys": SEPARATOR.join(keys),
            "line_keys": SEPARATOR.join(line_keys),
            "mod_ssp": _join(item.mod_ssp for item in outcomes),
            "remaining_allocation": _join(item.position.remaining_allocation for item in outcomes),
            "remaining_ssp": _join(item.position.remaining_ssp for item in outcomes),
            "revenue": _join(item.position.revenue for item in outcomes),
            "role": "exact",
            "ssp_delivered": _join(item.position.ssp_delivered for item in outcomes),
        }
        for item in outcomes:
            key = item.position.subject_key
            nodes[key] = tb.node(
                measure=f"allocated_exact@{ev.event_key}",
                subject_key=key,
                period_key=None,
                value=item.x_exact,
                currency=currency,
                minor_unit=None,
                formula_id=formula_id,
                inputs=[ssp_nodes[name] for name in line_keys],
                params={**common, "key": key},
                narrative_key=formula_id.rsplit(".v", 1)[0],
            )
        return nodes
    if formula_id != POB_VC_FORMULA:
        raise ValueError(f"{formula_id} is not a built template formula")
    for item in outcomes:
        if not item.targeted:
            continue
        key = item.position.subject_key
        params = {
            "as_of": as_of,
            "billing": rational_param(item.consideration_change),
            "remaining_allocation": rational_param(item.position.remaining_allocation),
            "remaining_ssp": rational_param(item.remaining_ssp),
            "revenue": rational_param(item.position.revenue),
            "revenue_after": rational_param(item.revenue),
            "role": "exact",
            "ssp_delivered": rational_param(item.position.ssp_delivered),
        }
        nodes[key] = tb.node(
            measure=f"allocated_exact@{ev.event_key}",
            subject_key=key,
            period_key=None,
            value=item.x_exact,
            currency=currency,
            minor_unit=None,
            formula_id=formula_id,
            inputs=[],
            params=params,
            narrative_key=formula_id.rsplit(".v", 1)[0],
        )
    return nodes


def emit_amounts(
    ctx: BookContext,
    tb: TraceBuilder,
    ev: EventView,
    formula_id: str,
    outcomes: Sequence[Outcome],
    posted: Mapping[str, int],
    tp_minor: int,
    exact_nodes: Mapping[str, str],
) -> dict[str, str]:
    """``allocated_amount@<event key>:<ob>:-``: largest_remainder(TP_c, [X_j], keys)[i]."""
    keys = [item.position.subject_key for item in outcomes]
    common = {
        "as_of": ev.effective_date.isoformat(),
        "keys": SEPARATOR.join(keys),
        "role": "amount",
        "tp_posted": str(tp_minor),
        "weights": _join(item.x_exact for item in outcomes),
    }
    nodes: dict[str, str] = {}
    for item in outcomes:
        key = item.position.subject_key
        nodes[key] = tb.node(
            measure=f"allocated_amount@{ev.event_key}",
            subject_key=key,
            period_key=None,
            value=posted[key],
            currency=ctx.txn_currency,
            minor_unit=segments.minor_unit(ctx),
            formula_id=formula_id,
            inputs=[exact_nodes[key]] if key in exact_nodes else [],
            params={**common, "key": key},
            exact=item.x_exact,
            narrative_key=formula_id.rsplit(".v", 1)[0],
        )
    return nodes
