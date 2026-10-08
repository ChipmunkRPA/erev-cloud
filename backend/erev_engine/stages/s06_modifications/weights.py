"""Stage 06 weights of a native modification (ENGINE_SPEC S06-R-06, S06-R-11; ALG-04 §2.5.4).

POL-080 ``D18_DEFAULT`` with POL-081 ``CARRIED_UNIT_SSP``:

- a class D existing obligation weighs ρ_p × ``resolve_ssp(at = d, quantity = RQ⁰_p, price = RQ⁰_p
  × ū_p).selected``, where RQ⁰_p is the remaining existing units after removals and ū_p the
  original stated unit price, plus ``resolve_ssp(at = d, ΔQ_m, ΔC_m).selected`` of every added-unit
  line on it, not scaled. ρ_p is the remaining service of ``segments.remaining_scale`` (D-90b) when
  ``segments.eligible`` admits the obligation (not a VC line, not ``series``, a ``FIXED`` segment
  in force measuring ``TIME_ELAPSED`` with a cause other than ``TERMINATION``), else 1; the parts
  and their ``ssp_entry`` sources stay unscaled and the node params record the layers. A ``series``
  obligation whose entry declares ``PER_INCREMENT`` or ``PER_BOOKED_TERM`` (04 E-49) is priced over
  its remaining increments by ``segments.series_basis_scale`` (D-93 (4); S06-R-11 series row);
  ``AMOUNT`` is the remaining-increments reading, taken as is;
- a class N obligation weighs (1 − f_p(d)) × SSP0_p + Σ over its added goods ``resolve_ssp(at = d,
  ΔQ_m, ΔC_m).selected`` − removed goods × u0_p (the same under ``INCEPTION_ALL``);
- an obligation the modification adds weighs ``resolve_ssp(at = d, ΔQ_m, ΔC_m).selected``.

The SSP version is the one effective at d, or the approved per-obligation override named in the
``CONTRACT_AMENDED`` member ``ssp_basis`` (D-18). At a later computation of the same event the
weight of an existing obligation is priced from the version recorded for it then, which the
orchestrator hands back (S05-R-03 ``recorded@<event key>``): a version approved afterwards does
not weigh an applied modification again. A ``VC_LINE`` obligation weighs 0 (S05-R-08), and no
unit SSP is computed for a remaining quantity of 0. Node ``mod_weight@<event key>:<ob>:-``
(formula ``mod.weights.d18.v1``, or ``mod.weights.inception_all.v1`` from ``inception_basis``)
records every part. Private to stage 06. Standard library only (DG-ARC-02).
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from fractions import Fraction
from types import MappingProxyType
from typing import Final

from erev_engine.bundle import ResolvedPolicyInput
from erev_engine.enums import Distinctness
from erev_engine.formulas import rational_param
from erev_engine.money import format_exact
from erev_engine.stages import s05_allocation
from erev_engine.stages.s01_canonicalize import payload_bool, payload_text
from erev_engine.stages.s02_contract_identification import IdentifiedState
from erev_engine.stages.s03_pob_builder import PobDraft, RawLine
from erev_engine.stages.s06_modifications import segments
from erev_engine.stages.s06_modifications.classify import ModificationLine
from erev_engine.stages.s06_modifications.segments import Measured
from erev_engine.stages.state import (
    BookContext,
    EventView,
    Finding,
    ObligationState,
    PolicyResolver,
    SspResolution,
)
from erev_engine.trace import SourceRef, TraceBuilder

__all__ = [
    "D18_FORMULA",
    "Weight",
    "added",
    "added_parts",
    "corrected",
    "emit",
    "existing",
    "inception_ssp",
    "nondistinct",
    "removed",
]

D18_FORMULA: Final = "mod.weights.d18.v1"
VERSION_POLICY: Final = "ssp.version_basis"
NAMED_VERSION: Final = "NAMED_VERSION"
SEPARATOR: Final = "|"


@dataclass(frozen=True, slots=True)
class Weight:
    """w_p of one obligation with the SSP resolutions it sums (S06-R-11)."""

    subject_key: str
    label: str  # "D" | "N"
    value: Fraction
    parts: tuple[Fraction, ...]
    sources: tuple[SourceRef, ...]
    resolution: SspResolution | None  # remaining units or the added line
    params: Mapping[str, str]


def inception_ssp(ob: ObligationState) -> tuple[Fraction, Fraction]:
    """SSP0_p, the selected inception SSP of stage 05, and u0_p = SSP0_p ÷ Q_p (§6.1)."""
    ssp0 = ob.resolved_ssp if ob.ssp is None else ob.ssp.selected
    unit = Fraction(0) if ob.original_quantity == 0 else ssp0 / ob.original_quantity
    return ssp0, unit


def removed(lines: Sequence[ModificationLine]) -> Fraction:
    """The units the lines remove from an obligation, as a positive number."""
    return -sum((line.quantity_delta for line in lines if line.quantity_delta < 0), Fraction(0))


def _override(
    ctx: BookContext, subject_key: str, basis: Mapping[str, object] | None
) -> BookContext:
    """The book context with an approved ``ssp_basis`` override as POL-070 level O (D-18)."""
    if basis is None or not payload_bool(basis, "is_override"):
        return ctx
    version_key = payload_text(basis, "ssp_version_key")
    if not version_key:
        raise ValueError(f"{subject_key}: an ssp_basis override names no ssp_version_key (D-18)")
    named = ResolvedPolicyInput(
        VERSION_POLICY,
        "OBLIGATION",
        subject_key,
        MappingProxyType({"option": NAMED_VERSION, "version_key": version_key}),
        "O",
        "SSP_BASIS",
        "K",
    )
    kept = [
        policy
        for policy in ctx.policies.all()
        if (policy.code, policy.scope, policy.subject_key)
        != (VERSION_POLICY, "OBLIGATION", subject_key)
    ]
    ordered = sorted([*kept, named], key=lambda p: (p.code, p.scope, p.subject_key))
    return dataclasses.replace(ctx, policies=PolicyResolver(tuple(ordered)))


def _raw(
    ob: ObligationState,
    d: date,
    quantity: Fraction,
    price: Fraction,
    *,
    product_code: str | None,
    stratification: str | None,
    ssp_version_label: str | None,
) -> RawLine:
    if product_code is None:
        raise ValueError(f"{ob.subject_key}: an obligation without a product has no SSP (S05-R-02)")
    return RawLine(
        contract_key=ob.contract_key,
        obligation_key=ob.obligation_key,
        product_code=product_code,
        stratification=stratification,
        quantity=quantity,
        stated_price=price,
        line_start_date=ob.start_date,
        line_end_date=ob.end_date,
        truncated_end_date=None,
        pricing_date=d,
        template_date=d,
        performing_entity=ob.performing_entity,
        ssp_version_label=ssp_version_label,
        account_overrides=MappingProxyType({}),
        scope_flag=ob.scope_flag,
        out_of_scope_amount=None,
        bundle_parent_obligation_key=None,
        bundle_product_code=None,
        memos=MappingProxyType({}),
        price_basis="PRICE_LINE",
        split=None,
    )


def _reference(resolution: SspResolution, member: str) -> SourceRef:
    detail = {"member": member, "value": format_exact(resolution.selected)}
    return SourceRef(
        "ssp_range" if resolution.range_key is not None else "ssp_entry",
        resolution.range_key or resolution.entry_key or "-",
        detail,
    )


def added_parts(
    ctx: BookContext,
    identified: IdentifiedState,
    ob: ObligationState,
    lines: Sequence[ModificationLine],
    ev: EventView,
    basis: Mapping[str, object] | None,
    findings: list[Finding],
) -> tuple[list[Fraction], list[SourceRef]] | None:
    """The d SSP of every added-unit line on ``ob``; ``None`` when a finding blocks."""
    scoped = _override(ctx, ob.subject_key, basis)
    record = s05_allocation.Record(ob.subject_key, ev.event_key)  # the weight in this event
    label = None if ob.ssp is None else ob.ssp.version_label
    parts: list[Fraction] = []
    sources: list[SourceRef] = []
    if ob.is_vc_line:
        return parts, sources
    for index, item in enumerate(lines):
        if item.quantity_delta <= 0:
            continue
        stratification = item.members.get("stratification")
        version_label = item.members.get("ssp_version_label")
        line = _raw(
            ob,
            ev.effective_date,
            item.quantity_delta,
            item.consideration_delta,
            product_code=item.product_code or ob.product_code,
            stratification=stratification if isinstance(stratification, str) else ob.stratification,
            ssp_version_label=version_label if isinstance(version_label, str) else label,
        )
        found = s05_allocation.resolve_ssp(
            scoped,
            line,
            line.pricing_date,
            line.stated_price,
            findings=findings,
            identified=identified,
            record=record,
        )
        if found is None:
            return None
        parts.append(found.selected)
        sources.append(_reference(found, f"added:{index}"))
    return parts, sources


def existing(
    ctx: BookContext,
    identified: IdentifiedState,
    ob: ObligationState,
    before: Measured,
    lines: Sequence[ModificationLine],
    ev: EventView,
    basis: Mapping[str, object] | None,
    findings: list[Finding],
) -> Weight | None:
    """w_p of a class D existing obligation (``D18_DEFAULT``); ``None`` when a finding blocks.

    The remaining units' resolution is scaled by ρ_p of ``segments.remaining_scale`` when the
    obligation is eligible (S06-R-11; D-90b); added-unit parts are not scaled.
    """
    d = ev.effective_date
    gone = removed(lines)
    remaining = before.remaining_quantity - gone
    unit_price = (
        Fraction(0)
        if ob.original_quantity == 0
        else ob.original_stated_price / ob.original_quantity
    )
    parts: list[Fraction] = []
    sources: list[SourceRef] = []
    resolution: SspResolution | None = None
    if not ob.is_vc_line and remaining > 0:
        line = _raw(
            ob,
            d,
            remaining,
            remaining * unit_price,
            product_code=ob.product_code,
            stratification=ob.stratification,
            ssp_version_label=None if ob.ssp is None else ob.ssp.version_label,
        )
        resolution = s05_allocation.resolve_ssp(
            _override(ctx, ob.subject_key, basis),
            line,
            d,
            line.stated_price,
            findings=findings,
            identified=identified,
            # S06-R-11: the version this weight was priced from when the event was computed
            record=s05_allocation.Record(ob.subject_key, ev.event_key),
        )
        if resolution is None:
            return None
        parts.append(resolution.selected)
        sources.append(_reference(resolution, "remaining"))
    found = added_parts(ctx, identified, ob, lines, ev, basis, findings)
    if found is None:
        return None
    parts.extend(found[0])
    sources.extend(found[1])
    params = {
        "remaining_quantity": rational_param(remaining),
        "unit_price": rational_param(unit_price),
    }
    value = sum(parts, Fraction(0))
    if resolution is not None and segments.eligible(ob, before.segment):
        rho, scale = segments.remaining_scale(ctx, ob, before, ev, removed=gone)
        value = parts[0] * rho + sum(parts[1:], Fraction(0))
        params.update(scale)
    elif resolution is not None and ob.distinctness == Distinctness.SERIES:
        # D-93 (4): the series entry's declared basis prices the remaining increments at d.
        scaled = segments.series_basis_scale(
            ctx,
            ob,
            before,
            ev,
            basis=resolution.value_basis,
            quantity_unit=resolution.quantity_unit,
            removed=gone,
        )
        if scaled is not None:
            factor, scale = scaled
            value = parts[0] * factor + sum(parts[1:], Fraction(0))
            params.update(scale)
    return Weight(
        ob.subject_key,
        "D",
        value,
        tuple(parts),
        tuple(sources),
        resolution,
        MappingProxyType(params),
    )


def nondistinct(
    ctx: BookContext,
    identified: IdentifiedState,
    ob: ObligationState,
    before: Measured,
    lines: Sequence[ModificationLine],
    ev: EventView,
    basis: Mapping[str, object] | None,
    findings: list[Finding],
) -> Weight | None:
    """w_p of a class N obligation: (1 − f) × SSP0 + added goods at d − removed × u0 (S06-R-11)."""
    found = added_parts(ctx, identified, ob, lines, ev, basis, findings)
    if found is None:
        return None
    parts, sources = found
    ssp0, unit = inception_ssp(ob)
    gone = removed(lines)
    value = (1 - before.progress) * ssp0 + sum(parts, Fraction(0)) - gone * unit
    params = {
        "progress": rational_param(before.progress),
        "removed": rational_param(gone),
        "ssp0": rational_param(ssp0),
        "u0": rational_param(unit),
    }
    return Weight(
        ob.subject_key, "N", value, tuple(parts), tuple(sources), None, MappingProxyType(params)
    )


def added(
    ctx: BookContext,
    identified: IdentifiedState,
    draft: PobDraft,
    ev: EventView,
    basis: Mapping[str, object] | None,
    findings: list[Finding],
    *,
    tb: TraceBuilder | None = None,
) -> Weight | None:
    """w_p of an obligation the modification adds: its SSP at d for ΔQ_m and ΔC_m (S06-R-11).

    With ``tb`` stage 05 emits the added line's ``original_ssp_selected@<event key>:<ob>:-`` node
    with its canonical sources — the created obligation's selected-SSP producer (CV-50 rev 1.29,
    D-98 candidate 124)."""
    scoped = _override(ctx, draft.subject_key, basis)
    resolution = s05_allocation.resolve_ssp(
        scoped,
        draft,
        ev.effective_date,
        draft.stated_price,
        tb,
        findings=findings,
        identified=identified,
        event_key=None if tb is None else ev.event_key,
        record=s05_allocation.Record(draft.subject_key),  # the added obligation's own pricing
    )
    if resolution is None:
        return None
    params = {"remaining_quantity": rational_param(draft.quantity)}
    return Weight(
        draft.subject_key,
        "D",
        resolution.selected,
        (resolution.selected,),
        (_reference(resolution, "added"),),
        resolution,
        MappingProxyType(params),
    )


def corrected(
    ctx: BookContext,
    identified: IdentifiedState,
    ob: ObligationState,
    at: date,
    *,
    version_key: str | None,
    version_label: str | None,
    findings: list[Finding],
    tb: TraceBuilder | None = None,
    event_key: str | None = None,
) -> SspResolution | None:
    """The inception SSP of ``ob`` resolved again under a corrected version pin (S06-R-26).

    With ``tb`` and ``event_key`` stage 05 emits the corrected ``original_ssp_selected@<event
    key>:<ob>:-`` node with the corrected version's canonical sources — the target's selected-SSP
    producer after the repin (CV-50 rev 1.29, D-98 candidate 123).

    ``version_key`` names an approved version as POL-070 level O ``NAMED_VERSION`` (the
    ``ssp_book_version_id`` of an approved ``SSP_OVERRIDE``); ``version_label`` replaces the line's
    ``ssp_version_label``. The line is priced at ``at``, the group inception (CV-10), with the
    original quantity and stated price. ``None`` when a finding blocks.
    """
    basis = None if version_key is None else {"is_override": True, "ssp_version_key": version_key}
    label = (
        version_label
        if version_label is not None
        else (None if ob.ssp is None else ob.ssp.version_label)
    )
    line = _raw(
        ob,
        at,
        ob.original_quantity,
        ob.original_stated_price,
        product_code=ob.product_code,
        stratification=ob.stratification,
        ssp_version_label=label,
    )
    return s05_allocation.resolve_ssp(
        _override(ctx, ob.subject_key, basis),
        line,
        at,
        line.stated_price,
        tb,
        findings=findings,
        identified=identified,
        event_key=event_key,
    )


def emit(tb: TraceBuilder, ev: EventView, weight: Weight, *, basis: str, formula_id: str) -> str:
    """``mod_weight@<event key>:<ob>:-``."""
    params = {
        "as_of": ev.effective_date.isoformat(),
        "basis": basis,
        "class": weight.label,
        "parts": SEPARATOR.join(rational_param(part) for part in weight.parts),
        **weight.params,
    }
    return tb.node(
        measure=f"mod_weight@{ev.event_key}",
        subject_key=weight.subject_key,
        period_key=None,
        value=weight.value,
        currency=None,
        minor_unit=None,
        formula_id=formula_id,
        inputs=list(weight.sources),
        params=params,
        narrative_key=formula_id.rsplit(".v", 1)[0],
    )
