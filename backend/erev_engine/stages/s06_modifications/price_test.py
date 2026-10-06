"""Stage 06 25-12 price test of an added line (ENGINE_SPEC S06-R-04; POL-101; mod.price_test.v1).

Private to stage 06. The SSP of the line at d and quantity ΔQ_m comes from the stage 03 reader
``s03_pob_builder.ssp_values``, coded against S05-R-02 to S05-R-06 until stage 05 ``resolve_ssp``
exists (ENA-10). Standard library only (DG-ARC-02).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from fractions import Fraction
from typing import Final

from erev_engine.money import format_exact, to_fraction
from erev_engine.stages.s02_contract_identification import IdentifiedState
from erev_engine.stages.s03_pob_builder import PobDraft, SspValues, ssp_values
from erev_engine.stages.s06_modifications.classify import ModificationView
from erev_engine.stages.state import BookContext
from erev_engine.trace import SourceRef, TraceBuilder

__all__ = ["FORMULA_ID", "POLICY_CODE", "PriceTest", "run", "tolerance"]

FORMULA_ID: Final = "mod.price_test.v1"
NARRATIVE_KEY: Final = "mod.price_test"
POLICY_CODE: Final = "mod.separate_contract_price_test"
OPTION: Final = "WITHIN_MOD_DATE_RANGE"
ATTESTED: Final = "ATTESTED"
POINT: Final = "POINT"
RANGE: Final = "RANGE"
NO_SSP: Final = "NO_SSP"


@dataclass(frozen=True, slots=True)
class PriceTest:
    """The S06-R-04 price test of one added draft."""

    draft: PobDraft
    passed: bool
    basis: str  # ATTESTED | POINT | RANGE | NO_SSP
    values: SspValues | None
    tolerance: Fraction  # point_tolerance_pct as a ratio


def tolerance(ctx: BookContext, contract_key: str) -> Fraction:
    """POL-101 ``point_tolerance_pct`` (default 0.00); another option raises ``ValueError``."""
    value = ctx.policies.value(POLICY_CODE, contract=contract_key)
    option: object
    ratio: object
    if isinstance(value, str):
        option, ratio = value, "0"
    elif isinstance(value, Mapping):
        option, ratio = value.get("option"), value.get("point_tolerance_pct", "0")
    else:
        raise ValueError(f"{POLICY_CODE} holds an unknown value shape (CV-17)")
    if option != OPTION or not isinstance(ratio, str):
        raise ValueError(f"{POLICY_CODE} holds an unknown option {option!r} (CV-17)")
    exact = to_fraction(ratio)
    if not 0 <= exact <= 1:
        raise ValueError(f"{POLICY_CODE} point_tolerance_pct must lie in [0, 1]")
    return exact


def run(
    ctx: BookContext,
    identified: IdentifiedState,
    mod: ModificationView,
    draft: PobDraft,
    tolerance_ratio: Fraction,
    tb: TraceBuilder,
) -> PriceTest:
    """S06-R-04 for ΔC_m = the draft's stated price, with node ``mod_price_test@<position>``.

    Passes with the approved questionnaire attestation ``priced_at_ssp = true``; otherwise, for a
    point entry when |ΔC_m − point| ≤ tolerance × |point|, and for a range entry when
    low ≤ ΔC_m ≤ high (inclusive). No resolvable SSP fails the test.
    """
    values = ssp_values(ctx, identified, draft.line)
    price = draft.stated_price
    attested = mod.answer(draft.line.obligation_key, "priced_at_ssp")
    if attested is None and draft.obligation_key != draft.line.obligation_key:
        attested = mod.answer(draft.obligation_key, "priced_at_ssp")
    if attested:
        passed, basis = True, ATTESTED
    elif values is None:
        passed, basis = False, NO_SSP
    elif values.point is not None:
        passed, basis = abs(price - values.point) <= tolerance_ratio * abs(values.point), POINT
    elif values.low is not None and values.high is not None:
        low, high = sorted((values.low, values.high))
        passed, basis = low <= price <= high, RANGE
    else:
        passed, basis = False, NO_SSP
    test = PriceTest(draft, passed, basis, values, tolerance_ratio)
    _emit(ctx, tb, mod, test)
    return test


def _text(value: Fraction | None) -> str:
    return "" if value is None else format_exact(value)


def _emit(ctx: BookContext, tb: TraceBuilder, mod: ModificationView, test: PriceTest) -> None:
    values = test.values
    params = {
        "basis": test.basis,
        "entry_key": "" if values is None else values.entry.entry_key,
        "high": "" if values is None else _text(values.high),
        "low": "" if values is None else _text(values.low),
        "mid": "" if values is None else _text(values.mid),
        "passed": "true" if test.passed else "false",
        "point": "" if values is None else _text(values.point),
        "point_tolerance_pct": format_exact(test.tolerance),
        "value": format_exact(test.draft.stated_price),
        "version_key": "" if values is None else values.version_key,
    }
    inputs: list[str | SourceRef] = []
    if values is not None:
        selected = values.point if values.point is not None else values.mid
        detail = {} if selected is None else {"value": format_exact(selected)}
        inputs.append(SourceRef("ssp_entry", values.entry.entry_key, detail))
    tb.node(
        measure=f"mod_price_test@{mod.position}",
        subject_key=test.draft.subject_key,
        period_key=None,
        value=test.draft.stated_price,
        currency=ctx.txn_currency,
        minor_unit=None,
        formula_id=FORMULA_ID,
        inputs=inputs,
        params=params,
        narrative_key=NARRATIVE_KEY,
    )
