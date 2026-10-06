"""Stage 04 implicit price concessions.

ENGINE_SPEC S04-R-09; 606-10-25-1(e), 606-10-32-7; FASB Example 2; formula
``tp.concession_implicit.v1``; POLICIES POL-125, JET-04c (CHK-138). Private to stage 04. Standard
library only (DG-ARC-02).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from fractions import Fraction
from typing import Final

from erev_engine.bundle import EstimateVersionInput
from erev_engine.errors import EngineError
from erev_engine.money import format_exact, round_half_up, to_fraction
from erev_engine.stages.s03_pob_builder import PobDraft, PobState
from erev_engine.stages.s04_transaction_price import vc
from erev_engine.stages.state import BookContext, EventView
from erev_engine.trace import SourceRef, TraceBuilder

__all__ = [
    "CONSTRAINED_AMOUNT_BASIS",
    "EXPECTED_TOTAL_BASIS",
    "FORMULA",
    "KIND",
    "RATE_BASIS",
    "Concession",
    "emit",
    "measure",
]

KIND: Final = "IMPLICIT_PRICE_CONCESSION"
FORMULA: Final = "tp.concession_implicit.v1"
RATE_BASIS: Final = "RATE"
EXPECTED_TOTAL_BASIS: Final = "EXPECTED_TOTAL_AMOUNT"
CONSTRAINED_AMOUNT_BASIS: Final = "CONSTRAINED_AMOUNT"  # D-87 L6-5-Q-12 (ii)


@dataclass(frozen=True, slots=True)
class Concession:
    """One pinned implicit price concession measured at a position (S04-R-09)."""

    version: EstimateVersionInput
    contract_key: str
    affected: tuple[PobDraft, ...]  # obligations whose fixed consideration the concession reduces
    fixed: Fraction  # Σ fixed consideration of the affected obligations
    kappa: Fraction  # κ
    basis: str  # RATE | EXPECTED_TOTAL_AMOUNT | CONSTRAINED_AMOUNT
    posted: int  # −round(κ × fixed), or −round(constrained) under CONSTRAINED_AMOUNT; minor units
    exact: Fraction  # the posted component in currency units


def measure(
    ctx: BookContext,
    st: PobState,
    at: date,
    before: EventView | None,
    fixed_lines: Sequence[PobDraft],
) -> tuple[Concession, ...]:
    """Every ``IMPLICIT_PRICE_CONCESSION`` element with a pin at ``at`` before ``before``.

    The affected obligations are the element's ``target_obligation_keys``, else its
    ``obligation_key``, else every fixed-consideration obligation of its contract. κ = ``rate``, or
    (stated consideration − ``expected_total_amount``) ÷ stated consideration, with the stated
    consideration Σ fixed consideration of the affected obligations. The component
    −round(κ × fixed) is part of ``vc_constrained``. A version with neither carries a third form
    (D-87 L6-5-Q-12 (ii)): with only ``constrained_amount`` the component is −round(constrained)
    and κ = constrained ÷ stated fixed consideration. A version without any of the three raises
    ``ValueError`` (CV-45); κ outside [0, 1], or undefined, raises
    ``EngineError("NON_FINITE_AMOUNT")``. A fall in expected collection caused by credit
    deterioration is never a change to κ (POL-125): it is recorded outside revenue.
    """
    minor_unit = ctx.currencies[ctx.txn_currency].minor_unit
    scale: int = 10**minor_unit
    pins = st.identified.canonical.estimates
    found: list[Concession] = []
    for key in sorted(pins.pins):
        version = pins.pin(key, at, before)
        if version is None or version.estimate_kind != KIND:
            continue
        contract_key = vc._contract_of(st, key)
        targets = version.target_obligation_keys or (
            () if version.obligation_key is None else (version.obligation_key,)
        )
        affected = tuple(
            ob
            for ob in fixed_lines
            if ob.contract_key == contract_key and (not targets or ob.obligation_key in targets)
        )
        fixed = sum((ob.stated_price for ob in affected), Fraction(0))
        undefined = False
        constrained: Fraction | None = None
        if version.rate is not None:
            kappa, basis = to_fraction(version.rate), RATE_BASIS
        elif version.expected_total_amount is not None:
            expected = to_fraction(version.expected_total_amount)
            kappa = Fraction(0) if fixed == 0 else (fixed - expected) / fixed
            basis = EXPECTED_TOTAL_BASIS
        elif version.constrained_amount is not None:  # D-87 L6-5-Q-12 (ii)
            constrained = to_fraction(version.constrained_amount)
            undefined = fixed == 0 and constrained != 0
            kappa = Fraction(0) if fixed == 0 else constrained / fixed
            basis = CONSTRAINED_AMOUNT_BASIS
        else:
            raise ValueError(
                f"{version.version_key}: a concession needs rate, expected total or "
                "constrained amount"
            )
        if undefined or not 0 <= kappa <= 1:
            raise EngineError(
                "NON_FINITE_AMOUNT",
                "the implicit price concession ratio lies outside [0, 1]",
                subject_key=key,
                detail={
                    "estimate_version_key": version.version_key,
                    "kappa": "undefined" if undefined else format_exact(kappa),
                    "rule": "S04-R-09",
                },
            )
        component = kappa * fixed if constrained is None else constrained
        posted = -round_half_up(component, minor_unit)
        found.append(
            Concession(
                version,
                contract_key,
                affected,
                fixed,
                kappa,
                basis,
                posted,
                Fraction(posted, scale),
            )
        )
    return tuple(found)


def emit(ctx: BookContext, tb: TraceBuilder, item: Concession, suffix: str) -> str:
    """Node ``vc_constrained:<estimate key>:-`` of a concession (§4.4;
    ``tp.concession_implicit.v1``)."""
    version = item.version
    stored = {
        RATE_BASIS: version.rate,
        EXPECTED_TOTAL_BASIS: version.expected_total_amount,
        CONSTRAINED_AMOUNT_BASIS: version.constrained_amount,
    }[item.basis]
    detail = {"value": format_exact(to_fraction(stored) if stored is not None else item.kappa)}
    inputs: list[str | SourceRef] = [SourceRef("estimate_version", version.version_key, detail)]
    inputs.extend(f"stated_price:{ob.subject_key}:-" for ob in item.affected)
    return tb.node(
        measure=f"vc_constrained{suffix}",
        subject_key=version.estimate_key,
        period_key=None,
        value=item.posted,
        currency=ctx.txn_currency,
        minor_unit=ctx.currencies[ctx.txn_currency].minor_unit,
        formula_id=FORMULA,
        inputs=inputs,
        params={
            "basis": item.basis,
            "direction": vc.DECREASE,
            "fixed": format_exact(item.fixed),
            "kappa": format_exact(item.kappa),
            "sign": "-1",
            "version_key": version.version_key,
        },
        exact=item.exact,
        narrative_key=FORMULA.rsplit(".v", 1)[0],
    )
