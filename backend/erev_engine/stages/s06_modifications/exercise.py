"""Stage 06 material-right exercise (ENGINE_SPEC §6.4 S06-R-23, S06-R-24; POLICIES ALG-05 §2.6.2,
§2.6.3; POL-028; REQ-POB-007).

``MATERIAL_RIGHT_EXERCISED`` at x names the option obligation o, the ``additional_consideration``
C_add and the ``new_lines``, which are the optioned goods G.

Under POL-028 ``CONTINUATION`` (the default), M = A_o − R_o in minor units and M_x = X_o − E_o. The
option takes a ``TERMINATION``-shaped segment (x′ = E_o(x), a′ = C_o(x), f = 1; cause
``MATERIAL_RIGHT_EXERCISE``). ``build_lines(new_lines, at = x)`` creates G. M + C_add is
apportioned over G by ``largest_remainder`` over their SSPs at x, and the exact allocations are
(M_x + C_add) × w ÷ Σw. Other obligations keep their segments and no catch-up arises.

Under ``MODIFICATION`` the exercise is a modification effective at x. A ``REMOVE`` line on the
option lets its remaining allocation join the pool, and ``ADD`` lines add G with Σ ΔC = C_add. The
engine classifies and pools them per §6.2 and §6.3, and the route is never ``SEPARATE_CONTRACT``
because the consideration includes M.

An option recognised by redemption pattern only records the redemption quantity for stage 09
(FASB Example 52). Nodes ``allocated_amount@<event key>:<ob>:-`` (formula
``mod.exercise.continuation.v1``) and ``mod_exercise@<event key>:<option>:-`` (formula
``mod.exercise.modification.v1``). Private to stage 06. Standard library only (DG-ARC-02).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from fractions import Fraction
from types import MappingProxyType
from typing import Final

from erev_engine import ENGINE_VERSION, money
from erev_engine.enums import ModificationTreatment, ObligationKind
from erev_engine.formulas import rational_param
from erev_engine.stages.s01_canonicalize import payload_fraction, payload_text
from erev_engine.stages.s02_contract_identification import IdentifiedState
from erev_engine.stages.s03_pob_builder import PobDraft, build_lines
from erev_engine.stages.s06_modifications import classify, segments
from erev_engine.stages.s06_modifications.classify import ModificationLine, ModificationView
from erev_engine.stages.state import (
    AllocatedState,
    AllocationSegment,
    BookContext,
    EventView,
    Finding,
    ObligationState,
    ProgressBase,
    ProgressTotals,
    SegmentCause,
)
from erev_engine.trace import TraceBuilder

__all__ = [
    "CONTINUATION",
    "CONTINUATION_FORMULA",
    "MODIFICATION",
    "MODIFICATION_FORMULA",
    "POLICY_CODE",
    "additional",
    "closed",
    "emit_goods",
    "emit_modification",
    "emit_option",
    "goods",
    "modification",
    "new_lines",
    "option",
    "quotas",
    "treatments",
]

CONTINUATION_FORMULA: Final = "mod.exercise.continuation.v1"
MODIFICATION_FORMULA: Final = "mod.exercise.modification.v1"
POLICY_CODE: Final = "material_right.exercise"
CONTINUATION: Final = "CONTINUATION"
MODIFICATION: Final = "MODIFICATION"
SEPARATOR: Final = "|"
_BY_CLASS: Final = MappingProxyType(
    {
        classify.DISTINCT: ModificationTreatment.PROSPECTIVE,
        classify.NONDISTINCT: ModificationTreatment.CUMULATIVE_CATCH_UP,
    }
)


def option(st: AllocatedState, ev: EventView) -> ObligationState:
    """The option obligation the event exercises; anything else raises ``ValueError`` (CV-45)."""
    key = payload_text(ev.payload, "obligation_key")
    if key is None:
        raise ValueError(f"{ev.event_key}: MATERIAL_RIGHT_EXERCISED needs obligation_key (§16.3)")
    found = next(
        (
            ob
            for ob in st.obligations
            if ob.contract_key == ev.contract_key and ob.obligation_key == key
        ),
        None,
    )
    if found is None:
        raise ValueError(f"{ev.event_key}: {key} is not an obligation of the contract (CV-45)")
    if found.obligation_kind != ObligationKind.MATERIAL_RIGHT:
        raise ValueError(f"{ev.event_key}: {key} is not a material right (S06-R-23)")
    if found.terminated_on is not None and found.terminated_on <= ev.effective_date:
        raise ValueError(f"{ev.event_key}: {key} is terminated before the exercise (S06-R-23)")
    return found


def additional(ctx: BookContext, ev: EventView) -> int:
    """C_add in minor units, 0 when absent (04 §16.3: non-negative Money)."""
    amount = payload_fraction(ev.payload, "additional_consideration")
    if amount is None:
        return 0
    if amount < 0:
        raise ValueError(f"{ev.event_key}: additional_consideration is not negative (§16.3)")
    return segments.to_minor(ctx, amount, "additional_consideration")


def new_lines(st: AllocatedState, ev: EventView) -> tuple[Mapping[str, object], ...]:
    """The API-S-ContractLine members of G; each names a new obligation key (CV-45)."""
    raw = ev.payload.get("new_lines")
    if not isinstance(raw, tuple | list) or not raw:
        raise ValueError(f"{ev.event_key}: an exercise names the optioned goods in new_lines")
    known = {ob.obligation_key for ob in st.obligations if ob.contract_key == ev.contract_key}
    rows: list[Mapping[str, object]] = []
    for row in raw:
        if not isinstance(row, Mapping):
            raise ValueError(f"{ev.event_key}: new_lines holds API-S-ContractLine objects")
        key = payload_text(row, "obligation_key")
        if key is None or key in known:
            raise ValueError(f"{ev.event_key}: a new line names a new obligation_key (CV-45)")
        rows.append(row)
    return tuple(rows)


def goods(
    ctx: BookContext,
    identified: IdentifiedState,
    ev: EventView,
    rows: Sequence[Mapping[str, object]],
    findings: list[Finding],
) -> tuple[PobDraft, ...]:
    """G priced at x by stage 03 ``build_lines`` (D-18); the drafts trace into a scratch builder."""
    scratch = TraceBuilder(engine_version=ENGINE_VERSION)
    return build_lines(
        ctx,
        identified,
        rows,
        ev.effective_date,
        scratch,
        contract_key=ev.contract_key,
        findings=findings,
    )


def closed(ev: EventView, before: segments.Measured) -> AllocationSegment:
    """The option's ``TERMINATION``-shaped segment: x′ = E_o(x), a′ = C_o(x), f = 1 (S06-R-23).

    The total is the net delivered units, so a units measure gives f = 1 from x.
    """
    seg = before.segment
    totals = ProgressTotals(
        before.delivered,
        seg.totals.eac_element_code,
        seg.totals.start_date,
        segments.boundary_as_of(ev),
    )
    return AllocationSegment(
        component=segments.FIXED,
        effective_date=ev.effective_date,
        event_key=ev.event_key,
        cause=SegmentCause.MATERIAL_RIGHT_EXERCISE,
        basis=segments.INCEPTION,
        x_exact=before.exact,
        a_posted=before.posted,
        base_revenue_posted=0,
        base_revenue_exact=Fraction(0),
        base_progress=ProgressBase.zero(),
        totals=totals,
        progress_measure=seg.progress_measure,
        unit_ssp=None,
        remaining_ssp=Fraction(0),
        remaining_billing_plan=seg.remaining_billing_plan,
        estimate_pair=(None, None),
        modification_boundary_no=seg.modification_boundary_no,
    )


def quotas(
    before: segments.Measured,
    add: int,
    weights: Sequence[tuple[str, Fraction]],
    minor_unit: int,
) -> Mapping[str, tuple[int, Fraction]]:
    """(A_G, X_G) per optioned good: largest_remainder(M + C_add, SSP at x, keys) and
    (M_x + C_add) × w ÷ Σw (S06-R-23)."""
    keys = [key for key, _ in weights]
    values = [value for _, value in weights]
    total_weight = sum(values, Fraction(0))
    seg = before.segment
    posted_total = seg.a_posted - before.posted + add
    exact_total = seg.x_exact - before.exact + Fraction(add, 10**minor_unit)
    posted = money.largest_remainder(posted_total, values, keys)
    return MappingProxyType(
        {
            key: (amount, exact_total * value / total_weight)
            for key, value, amount in zip(keys, values, posted, strict=True)
        }
    )


def emit_option(
    ctx: BookContext, tb: TraceBuilder, ev: EventView, subject_key: str, before: segments.Measured
) -> str:
    """``allocated_amount@<event key>:<option>:-``: the option closes at C_o(x)."""
    params = {
        "as_of": ev.effective_date.isoformat(),
        "exact_before": rational_param(before.exact),
        "option_allocation": str(before.segment.a_posted),
        "revenue_before": str(before.posted),
        "role": "option",
    }
    return tb.node(
        measure=f"allocated_amount@{ev.event_key}",
        subject_key=subject_key,
        period_key=None,
        value=before.posted,
        currency=ctx.txn_currency,
        minor_unit=segments.minor_unit(ctx),
        formula_id=CONTINUATION_FORMULA,
        inputs=[],
        params=params,
        exact=before.exact,
        narrative_key=CONTINUATION_FORMULA.rsplit(".v", 1)[0],
    )


def emit_goods(
    ctx: BookContext,
    tb: TraceBuilder,
    ev: EventView,
    before: segments.Measured,
    add: int,
    weight_nodes: Sequence[tuple[str, str]],
    found: Mapping[str, tuple[int, Fraction]],
) -> Mapping[str, str]:
    """``allocated_amount@<event key>:<G>:-``: M + C_add over G by the SSP at x (``mod_weight``)."""
    seg = before.segment
    keys = [key for key, _ in weight_nodes]
    params = {
        "additional": str(add),
        "as_of": ev.effective_date.isoformat(),
        "keys": SEPARATOR.join(keys),
        "option_allocation": str(seg.a_posted),
        "option_exact": rational_param(seg.x_exact),
        "option_exact_revenue": rational_param(before.exact),
        "option_revenue": str(before.posted),
        "role": "goods",
    }
    inputs = [node for _, node in weight_nodes]
    nodes: dict[str, str] = {}
    for key in keys:
        posted, exact = found[key]
        nodes[key] = tb.node(
            measure=f"allocated_amount@{ev.event_key}",
            subject_key=key,
            period_key=None,
            value=posted,
            currency=ctx.txn_currency,
            minor_unit=segments.minor_unit(ctx),
            formula_id=CONTINUATION_FORMULA,
            inputs=inputs,
            params={**params, "key": key},
            exact=exact,
            narrative_key=CONTINUATION_FORMULA.rsplit(".v", 1)[0],
        )
    return MappingProxyType(nodes)


def modification(
    ctx: BookContext,
    ev: EventView,
    option_ob: ObligationState,
    before: segments.Measured,
    rows: Sequence[Mapping[str, object]],
    add: int,
) -> ModificationView:
    """The modification an exercise is under POL-028 ``MODIFICATION`` (S06-R-24).

    A ``REMOVE`` line takes the option's remaining units with ΔC = 0, and an ``ADD`` line per
    optioned good carries ΔC = its ``total_price``; Σ ΔC must equal C_add (``ValueError``). The
    view is keyed by the event, because the exercise names no T-CON-06 object.
    """
    removed = -before.remaining_quantity
    remove = ModificationLine(
        obligation_key=option_ob.obligation_key,
        action="REMOVE",
        product_code=option_ob.product_code,
        quantity_delta=removed,
        consideration_delta=Fraction(0),
        members=MappingProxyType(
            {
                "action": "REMOVE",
                "consideration_delta": Fraction(0),
                "obligation_key": option_ob.obligation_key,
                "quantity_delta": removed,
            }
        ),
    )
    added: list[ModificationLine] = []
    total = Fraction(0)
    for row in rows:
        key, product = payload_text(row, "obligation_key"), payload_text(row, "product_code")
        quantity, price = payload_fraction(row, "quantity"), payload_fraction(row, "total_price")
        if key is None or quantity is None or price is None:
            raise ValueError(f"{ev.event_key}: a new line needs obligation_key, quantity, price")
        members = dict(row)
        if row.get("performing_entity_code") is not None:
            members["selling_entity_code"] = row["performing_entity_code"]
        if row.get("account_overrides") is not None:
            members["account_codes"] = row["account_overrides"]
        members.update({"action": "ADD", "consideration_delta": price, "quantity_delta": quantity})
        added.append(
            ModificationLine(key, "ADD", product, quantity, price, MappingProxyType(members))
        )
        total += price
    if segments.to_minor(ctx, total, "new_lines total_price") != add:
        raise ValueError(
            f"{ev.event_key}: the new lines' total_price differs from additional_consideration "
            "(S06-R-24)"
        )
    return ModificationView(
        contract_key=ev.contract_key,
        modification_key=ev.event_key,
        effective_date=ev.effective_date,
        kind="OTHER",
        template_mode=None,
        questionnaire=MappingProxyType({}),
        lines=(remove, *added),
        price_change_amount=None,
        event=ev,
    )


def treatments(
    ctx: BookContext,
    st: AllocatedState,
    mod: ModificationView,
    identified: IdentifiedState,
    findings: list[Finding],
) -> Mapping[str, ModificationTreatment]:
    """The engine's classes as the treatments of an exercise: D ``PROSPECTIVE``, N
    ``CUMULATIVE_CATCH_UP``, S none (§6.2 S06-R-05; S06-R-24). The proposal nodes trace into a
    scratch builder: an exercise records no proposal (CV-16)."""
    scratch = TraceBuilder(engine_version=ENGINE_VERSION)
    existing = classify.contract_obligations(st, mod)
    added = classify.added_lines(ctx, identified, mod, existing, findings)
    classes = classify.classify(ctx, st, mod, existing, added, findings, scratch)
    return MappingProxyType(
        {
            item.obligation_key: _BY_CLASS[item.label]
            for item in classes
            if item.label != classify.SATISFIED
        }
    )


def emit_modification(
    ctx: BookContext,
    tb: TraceBuilder,
    ev: EventView,
    option_ob: ObligationState,
    before: segments.Measured,
    mod: ModificationView,
    add: int,
) -> str:
    """``mod_exercise@<event key>:<option>:-``: the lines built from the exercise, Σ ΔC = C_add."""
    mu = segments.minor_unit(ctx)
    lines = [line for line in mod.lines if line.action == "ADD"]
    params = {
        "additional": str(add),
        "as_of": ev.effective_date.isoformat(),
        "consideration": SEPARATOR.join(
            str(segments.to_minor(ctx, line.consideration_delta, "ΔC")) for line in lines
        ),
        "keys": SEPARATOR.join(line.obligation_key for line in lines),
        "option_allocation": str(before.segment.a_posted),
        "option_revenue": str(before.posted),
        "removed_quantity": rational_param(before.remaining_quantity),
    }
    return tb.node(
        measure=f"mod_exercise@{ev.event_key}",
        subject_key=option_ob.subject_key,
        period_key=None,
        value=add,
        currency=ctx.txn_currency,
        minor_unit=mu,
        formula_id=MODIFICATION_FORMULA,
        inputs=[],
        params=params,
        exact=Fraction(add, 10**mu),
        narrative_key=MODIFICATION_FORMULA.rsplit(".v", 1)[0],
    )
