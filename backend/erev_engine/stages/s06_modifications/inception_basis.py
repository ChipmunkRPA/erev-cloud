"""Stage 06 weights under POL-080 ``INCEPTION_ALL`` (ENGINE_SPEC S06-R-06, S06-R-11; ALG-04 §2.5.4).

Every existing obligation keeps its inception SSP (606-10-32-43): a class D existing obligation
weighs ρ_p × RQ⁰_p × u0_p plus the d SSP of every added-unit line on it, not scaled, where ρ_p is
the remaining service of ``segments.remaining_scale`` for an obligation ``segments.eligible``
admits (D-90b) and 1 otherwise, and a series obligation takes the inception SSP of its remaining
increments priced from the inception entry's declared basis (``segments.series_basis_scale``,
D-93 (4); ``AMOUNT`` as is); a class N obligation weighs as under ``D18_DEFAULT``
(``weights.nondistinct``); an added obligation weighs its SSP at d. Nodes
``mod_weight@<event key>:<ob>:-`` take formula ``mod.weights.inception_all.v1``. Private to stage
06. Standard library only (DG-ARC-02).
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping, Sequence
from fractions import Fraction
from types import MappingProxyType
from typing import Final

from erev_engine.enums import Distinctness
from erev_engine.formulas import rational_param
from erev_engine.stages.s02_contract_identification import IdentifiedState
from erev_engine.stages.s06_modifications import segments, weights
from erev_engine.stages.s06_modifications.classify import ModificationLine
from erev_engine.stages.s06_modifications.segments import Measured
from erev_engine.stages.state import BookContext, EventView, Finding, ObligationState

__all__ = ["INCEPTION_ALL_FORMULA", "added", "existing"]

INCEPTION_ALL_FORMULA: Final = "mod.weights.inception_all.v1"


def existing(
    ctx: BookContext,
    identified: IdentifiedState,
    ob: ObligationState,
    before: Measured,
    lines: Sequence[ModificationLine],
    ev: EventView,
    basis: Mapping[str, object] | None,
    findings: list[Finding],
) -> weights.Weight | None:
    """w_p of a class D existing obligation: ρ_p × RQ⁰_p × u0_p + added units at d
    (``INCEPTION_ALL``; S06-R-11, D-90b)."""
    found = weights.added_parts(ctx, identified, ob, lines, ev, basis, findings)
    if found is None:
        return None
    parts, sources = found
    gone = weights.removed(lines)
    remaining = before.remaining_quantity - gone
    carried = remaining if remaining > 0 and not ob.is_vc_line else Fraction(0)
    _, unit = weights.inception_ssp(ob)
    params = {"remaining_quantity": rational_param(carried), "u0": rational_param(unit)}
    value = carried * unit + sum(parts, Fraction(0))
    if carried > 0 and segments.eligible(ob, before.segment):
        rho, scale = segments.remaining_scale(ctx, ob, before, ev, removed=gone)
        value = carried * unit * rho + sum(parts, Fraction(0))
        params.update(scale)
    elif carried > 0 and ob.distinctness == Distinctness.SERIES:
        # D-93 (4): the inception entry's declared basis prices the remaining increments.
        entry_basis = None if ob.ssp is None else ob.ssp.value_basis
        entry_unit = None if ob.ssp is None else ob.ssp.quantity_unit
        scaled = segments.series_basis_scale(
            ctx, ob, before, ev, basis=entry_basis, quantity_unit=entry_unit, removed=gone
        )
        if scaled is not None:
            factor, scale = scaled
            value = carried * unit * factor + sum(parts, Fraction(0))
            params.update(scale)
    return weights.Weight(
        ob.subject_key,
        "D",
        value,
        tuple(parts),
        tuple(sources),
        None,
        MappingProxyType(params),
    )


def added(weight: weights.Weight) -> weights.Weight:
    """An added obligation's SSP at d, recorded with no carried inception units."""
    params = MappingProxyType({"remaining_quantity": "0", "u0": "0"})
    return dataclasses.replace(weight, params=params)
