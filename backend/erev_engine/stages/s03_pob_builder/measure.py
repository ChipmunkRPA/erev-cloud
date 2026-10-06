"""Stage 03 measure of progress and time convention (ENGINE_SPEC S03-R-17; POL-090, POL-091).

Private to stage 03. One measure per obligation version (REQ-REC-018): an obligation-level
``recognition.measure_of_progress`` override (level O) replaces the template method with its E-11
literal, and a ``TIME_ELAPSED`` obligation takes the resolved ``recognition.time_convention``,
pinned at inception (pin K). Standard library only (DG-ARC-02).
"""

from __future__ import annotations

import dataclasses
from typing import Final

from erev_engine.bundle import ResolvedPolicyInput
from erev_engine.enums import RatableConvention, RecognitionMethod
from erev_engine.stages.s03_pob_builder.templates import PobDraft
from erev_engine.stages.state import BookContext

__all__ = ["CONVENTION_CODE", "MEASURE_CODE", "MEASURE_OPTIONS", "apply"]

MEASURE_CODE: Final = "recognition.measure_of_progress"
CONVENTION_CODE: Final = "recognition.time_convention"
# POL-091 options; each is its own E-11 literal.
MEASURE_OPTIONS: Final = frozenset(
    {
        "TIME_ELAPSED",
        "UNITS_DELIVERED",
        "MILESTONE",
        "COST_TO_COST",
        "LABOUR_HOURS",
        "RIGHT_TO_INVOICE",
        "COST_RECOVERY",
    }
)


def apply(ctx: BookContext, draft: PobDraft) -> PobDraft:
    """S03-R-17: the measure and, for ``TIME_ELAPSED``, the ratable convention of one draft.

    Only an override at level O replaces the template method. A value outside POL-091 raises
    ``ValueError`` (CV-45). Without a resolved convention the template value applies, else
    ``DAILY`` (POL-090 default); any other method carries no convention (T-REF-23 check).
    """
    method = draft.recognition_method
    override = _resolved(ctx, MEASURE_CODE, draft)
    if override is not None and override.level == "O":
        if not isinstance(override.value, str) or override.value not in MEASURE_OPTIONS:
            raise ValueError(f"{draft.subject_key}: {MEASURE_CODE} is not a POL-091 option")
        method = RecognitionMethod(override.value)
    convention: RatableConvention | None = None
    if method == RecognitionMethod.TIME_ELAPSED:
        resolved = _resolved(ctx, CONVENTION_CODE, draft)
        if resolved is None:
            convention = draft.ratable_convention or RatableConvention.DAILY
        elif isinstance(resolved.value, str):
            convention = RatableConvention(resolved.value)
        else:
            raise ValueError(f"{draft.subject_key}: {CONVENTION_CODE} holds one POL-090 option")
    return dataclasses.replace(draft, recognition_method=method, ratable_convention=convention)


def _resolved(ctx: BookContext, code: str, draft: PobDraft) -> ResolvedPolicyInput | None:
    try:
        return ctx.policies.resolved(
            code,
            contract=draft.contract_key,
            obligation=draft.subject_key,
            entity=draft.performing_entity,
        )
    except ValueError:  # no framework default and no level sets it (POLICIES §0.4)
        return None
