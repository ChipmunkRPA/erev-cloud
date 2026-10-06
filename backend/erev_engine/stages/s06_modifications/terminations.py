"""Stage 06 terminations (ENGINE_SPEC §6.4 S06-R-21; POLICIES §5.3 PT-03, POL-242; REQ-MOD-011).

``CONTRACT_TERMINATED`` with ``termination_kind = FULL`` ends every unsatisfied obligation of the
contract, and ``PARTIAL`` ends the payload ``obligation_keys``. The approved modification named by
``modification_id`` carries ``REMOVE`` lines with ΔC = −(consideration forgone), so the scope
reduction is applied by §6.3 and is never a separate contract (DART 9.2.2.7).

An ended obligation joins the pool with its remaining allocation and weight 0. It takes a
``TERMINATION`` segment with basis ``INCEPTION``: ``x_exact`` = E_before(d_T) + its shares,
``a_posted`` = C_before(d_T) + its posted shares, and totals that give f = 1 from d_T (ENGINE_SPEC_B
S09-R-06). A non-zero pool with no remaining obligation is satisfied performance, which the ended
obligations recognise (S06-R-09).

``refund_amount`` creates a ``TERMINATION`` refund-liability component dated d_T under POL-242
``REFUND_LIABILITY_UNTIL_CREDIT_MEMO`` (JET-04b), which stage 10 consumes by credit memos
(ENGINE_SPEC_B §10.2.4). The stage 02 status machine sets the ``TERMINATED`` status of a ``FULL``
termination in every book (Table 2.2-A). Cost-asset acceleration is stage 11 (POL-145).

Nodes ``allocated_amount@<event key>:<ob>:-`` and ``refund_component@<event key>:<contract>:-``
(formula ``mod.termination.v1``). Private to stage 06. Standard library only (DG-ARC-02).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from fractions import Fraction
from types import MappingProxyType
from typing import Final

from erev_engine.formulas import rational_param
from erev_engine.stages.s01_canonicalize import contract_subject_key, payload_fraction, payload_text
from erev_engine.stages.s06_modifications import segments, weights
from erev_engine.stages.s06_modifications.classify import ModificationView
from erev_engine.stages.state import (
    AllocationSegment,
    BookContext,
    EventView,
    ObligationState,
    ProgressBase,
    ProgressTotals,
    SegmentCause,
)
from erev_engine.trace import TraceBuilder

__all__ = [
    "COMPONENT",
    "FORMULA_ID",
    "FULL",
    "PARTIAL",
    "POLICY_CODE",
    "REFUND_LIABILITY_UNTIL_CREDIT_MEMO",
    "check_lines",
    "component_key",
    "emit_allocation",
    "emit_refund",
    "ended",
    "refund",
    "segment",
    "weight",
]

FORMULA_ID: Final = "mod.termination.v1"
POLICY_CODE: Final = "termination.refund_settlement"
REFUND_LIABILITY_UNTIL_CREDIT_MEMO: Final = "REFUND_LIABILITY_UNTIL_CREDIT_MEMO"
FULL: Final = "FULL"
PARTIAL: Final = "PARTIAL"
COMPONENT: Final = "TERMINATION"
REMOVE: Final = "REMOVE"


def _kind(ev: EventView) -> str:
    value = payload_text(ev.payload, "termination_kind")
    if value not in (FULL, PARTIAL):
        raise ValueError(f"{ev.event_key}: termination_kind is FULL or PARTIAL (04 §16.3)")
    return value


def _named(ev: EventView) -> tuple[str, ...]:
    raw = ev.payload.get("obligation_keys")
    if raw is None:
        return ()
    if not isinstance(raw, tuple | list) or not all(isinstance(item, str) for item in raw):
        raise ValueError(f"{ev.event_key}: obligation_keys lists obligation keys (04 §16.3)")
    return tuple(sorted(set(raw)))


def ended(
    ev: EventView, existing: Sequence[ObligationState], progress: Mapping[str, Fraction]
) -> frozenset[str]:
    """The obligation keys the termination ends (S06-R-21).

    ``FULL``: every obligation of the contract with f_p(d_T) < 1. ``PARTIAL``: the payload
    ``obligation_keys``, each an unsatisfied obligation of the contract; an unknown or satisfied
    obligation raises ``ValueError`` (CV-45). ``progress`` maps obligation keys to f_p(d_T).
    """
    keys = {ob.obligation_key for ob in existing}
    if _kind(ev) == FULL:
        return frozenset(key for key in keys if progress[key] < 1)
    names = _named(ev)
    if not names:
        raise ValueError(f"{ev.event_key}: a PARTIAL termination names obligation_keys (S06-R-21)")
    unknown = sorted(set(names) - keys)
    if unknown:
        raise ValueError(f"{ev.event_key}: {unknown[0]} is not an obligation of the contract")
    satisfied = sorted(key for key in names if progress[key] == 1)
    if satisfied:
        raise ValueError(f"{ev.event_key}: {satisfied[0]} is satisfied and cannot be terminated")
    return frozenset(names)


def refund(ctx: BookContext, ev: EventView) -> int:
    """``refund_amount`` in minor units, 0 when absent (04 §16.3: non-negative Money)."""
    amount = payload_fraction(ev.payload, "refund_amount")
    if amount is None:
        return 0
    if amount < 0:
        raise ValueError(f"{ev.event_key}: refund_amount is not negative (04 §16.3)")
    return segments.to_minor(ctx, amount, "refund_amount")


def check_lines(
    ctx: BookContext, mod: ModificationView, ended_keys: frozenset[str], refund_minor: int
) -> None:
    """The lines on ended obligations remove goods: ``REMOVE``, ΔQ ≤ 0 and ΔC ≤ 0; and the
    consideration forgone, −Σ ΔC of those lines, covers the refund (S06-R-21). ``ValueError``
    otherwise (CV-45)."""
    forgone = 0
    for line in mod.lines:
        if line.obligation_key not in ended_keys:
            continue
        if line.action != REMOVE or line.quantity_delta > 0 or line.consideration_delta > 0:
            raise ValueError(
                f"{mod.modification_key}: the line on ended obligation {line.obligation_key} is "
                "not a REMOVE line with non-positive deltas (S06-R-21)"
            )
        forgone -= segments.to_minor(
            ctx, line.consideration_delta, f"{line.obligation_key} consideration_delta"
        )
    if forgone < refund_minor:
        raise ValueError(
            f"{mod.modification_key}: the consideration forgone is less than refund_amount "
            "(S06-R-21)"
        )


def weight(ob: ObligationState, *, inception_all: bool) -> weights.Weight:
    """w_p = 0 of an ended obligation: nothing remains to transfer (S06-R-11, S06-R-21)."""
    unit = "u0" if inception_all else "unit_price"
    params = {"remaining_quantity": "0", "terminated": "true", unit: "0"}
    return weights.Weight(
        ob.subject_key,
        "D",
        Fraction(0),
        (),
        (),
        None,
        MappingProxyType(dict(sorted(params.items()))),
    )


def segment(
    ctx: BookContext,
    ev: EventView,
    before: segments.Measured,
    *,
    x_exact: Fraction,
    a_posted: int,
    billing_plan: Fraction,
) -> AllocationSegment:
    """The ``TERMINATION`` segment of an ended obligation (S06-R-21; ENGINE_SPEC_B S09-R-06).

    Units measures take the net delivered units as the total, so f = 1 from d_T; stage 09 gives
    f = 1 to a ``TERMINATION`` segment of a time-elapsed obligation from its effective date. The
    term ends on d_T − 1, the last day performed.
    """
    seg = before.segment
    quantity = (
        before.delivered if seg.progress_measure in segments.UNIT_MEASURES else seg.totals.quantity
    )
    totals = ProgressTotals(
        quantity, seg.totals.eac_element_code, seg.totals.start_date, segments.boundary_as_of(ev)
    )
    return AllocationSegment(
        component=segments.FIXED,
        effective_date=ev.effective_date,
        event_key=ev.event_key,
        cause=SegmentCause.TERMINATION,
        basis=segments.INCEPTION,
        x_exact=x_exact,
        a_posted=a_posted,
        base_revenue_posted=0,
        base_revenue_exact=Fraction(0),
        base_progress=ProgressBase.zero(),
        totals=totals,
        progress_measure=seg.progress_measure,
        unit_ssp=None,
        remaining_ssp=Fraction(0),
        remaining_billing_plan=billing_plan,
        estimate_pair=(None, None),
        modification_boundary_no=seg.modification_boundary_no,
    )


def emit_allocation(
    ctx: BookContext,
    tb: TraceBuilder,
    ev: EventView,
    subject_key: str,
    before: segments.Measured,
    *,
    posted: int,
    exact: Fraction,
    inputs: Sequence[str],
) -> str:
    """``allocated_amount@<event key>:<ob>:-``: C_before(d_T) + the shares the obligation takes."""
    params = {
        "as_of": ev.effective_date.isoformat(),
        "exact_before": rational_param(before.exact),
        "revenue_before": str(before.posted),
        "role": "allocation",
    }
    return tb.node(
        measure=f"allocated_amount@{ev.event_key}",
        subject_key=subject_key,
        period_key=None,
        value=posted,
        currency=ctx.txn_currency,
        minor_unit=segments.minor_unit(ctx),
        formula_id=FORMULA_ID,
        inputs=list(inputs),
        params=params,
        exact=exact,
        narrative_key=FORMULA_ID.rsplit(".v", 1)[0],
    )


def component_key(contract_key: str, ev: EventView) -> str:
    """The ``refund_components`` key of a termination refund: ``<contract>#TERMINATION@<event>``.

    The component has a contract-level subject; stage 10 attributes it to obligations by posted
    allocation at its creation date (ENGINE_SPEC_B S10-R-15).
    """
    return f"{contract_subject_key(contract_key)}#{COMPONENT}@{ev.event_key}"


def emit_refund(
    ctx: BookContext, tb: TraceBuilder, ev: EventView, contract_key: str, amount: int
) -> str:
    """``refund_component@<event key>:<contract>:-``: the ``TERMINATION`` component at d_T."""
    mu = segments.minor_unit(ctx)
    params = {
        "as_of": ev.effective_date.isoformat(),
        "component": COMPONENT,
        "refund_amount": str(amount),
        "role": "refund",
    }
    return tb.node(
        measure=f"refund_component@{ev.event_key}",
        subject_key=contract_subject_key(contract_key),
        period_key=None,
        value=amount,
        currency=ctx.txn_currency,
        minor_unit=mu,
        formula_id=FORMULA_ID,
        inputs=[],
        params=params,
        exact=Fraction(amount, 10**mu),
        narrative_key=FORMULA_ID.rsplit(".v", 1)[0],
    )
