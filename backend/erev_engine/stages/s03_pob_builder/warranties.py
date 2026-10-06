"""Stage 03 warranties: service-type obligations and assurance-type accrual definitions.

ENGINE_SPEC S03-R-08; 606-10-55-30 to 55-35; POLICIES POL-022 (pin P), JET-16; 03 REQ-POB-008
(warranty split). Stage 04 measures the accrual targets (S04-R-19). Private to stage 03. Standard
library only (DG-ARC-02).
"""

from __future__ import annotations

import dataclasses
from collections.abc import Sequence
from dataclasses import dataclass
from fractions import Fraction
from typing import Final

from erev_engine import dates
from erev_engine.enums import ObligationKind, RecognitionMethod, SatisfactionPattern, WarrantyType
from erev_engine.money import to_fraction
from erev_engine.stages.s02_contract_identification import IdentifiedState
from erev_engine.stages.s03_pob_builder.distinct import obligation_judgement
from erev_engine.stages.s03_pob_builder.templates import PobDraft
from erev_engine.stages.state import BookContext

__all__ = ["ACCRUAL_POLICY", "ENGINE", "NO_COST_RATE", "WarrantyAccrual", "accruals", "split"]

ACCRUAL_POLICY: Final = "pob.assurance_warranty_accrual"  # POL-022, pin P
ENGINE: Final = "ENGINE"
NO_COST_RATE: Final = "NO_COST_RATE"
_OVER_TIME_DEFAULT: Final = "OT_A"  # 606-10-25-27(a): coverage consumed as it is provided


@dataclass(frozen=True, slots=True)
class WarrantyAccrual:
    """An assurance-type warranty accrual definition on a product obligation (S03-R-08)."""

    subject_key: str  # the product obligation that carries the accrual target (S04-R-19)
    product_code: str
    assurance_cost_per_unit: Fraction | None  # T-REF-20 column; None accrues nothing
    reason: str | None  # NO_COST_RATE when the product has no cost rate


def split(ctx: BookContext, st: IdentifiedState, draft: PobDraft) -> PobDraft | None:
    """S03-R-08 for one line: the warranty type and the obligation it creates.

    ``warranty_type`` = the reviewed ``WARRANTY_TYPE`` outcome for the line, else the template
    value. ``SERVICE``: an obligation of kind ``SERVICE_WARRANTY`` recognised over its coverage
    period (``OVER_TIME``, ``TIME_ELAPSED``); a coverage period without start and end dates raises
    ``ValueError`` (CV-45). ``ASSURANCE`` on a warranty line (template kind ``SERVICE_WARRANTY``):
    no obligation (``None``). ``ASSURANCE`` on a product line: the product obligation stays, and its
    accrual definition comes from :func:`accruals`. An outcome outside E-91 raises ``ValueError``.
    """
    header = st.canonical.contracts[draft.contract_key].header
    record = obligation_judgement(header, "WARRANTY_TYPE", ctx.book_code, draft.obligation_key)
    literal = draft.warranty_type
    if record is not None:
        value = record.outcome.get("warranty_type")
        if value is None:
            raise ValueError(f"{record.judgement_key}: outcome member warranty_type is required")
        literal = WarrantyType(value)
    if literal == WarrantyType.SERVICE:
        if draft.start_date is None or draft.end_date is None:
            raise ValueError(f"{draft.subject_key}: a service warranty needs its coverage period")
        criterion = draft.over_time_criterion
        return dataclasses.replace(
            draft,
            obligation_kind=ObligationKind.SERVICE_WARRANTY,
            warranty_type=literal,
            satisfaction_pattern=SatisfactionPattern.OVER_TIME,
            recognition_method=RecognitionMethod.TIME_ELAPSED,
            over_time_criterion=_OVER_TIME_DEFAULT if criterion == "NOT_APPLICABLE" else criterion,
        )
    if (
        literal == WarrantyType.ASSURANCE
        and draft.obligation_kind == ObligationKind.SERVICE_WARRANTY
    ):
        return None
    return dataclasses.replace(draft, warranty_type=literal)


def accruals(
    ctx: BookContext,
    st: IdentifiedState,
    obligations: Sequence[PobDraft],
    assurance_lines: Sequence[PobDraft],
) -> tuple[WarrantyAccrual, ...]:
    """The accrual definitions of POL-022 ``ENGINE`` (JET-16), by subject key.

    A product obligation (not a warranty) carries a definition when its warranty type is
    ``ASSURANCE``, when an assurance-type warranty line names it as bundle parent, or when its
    product has ``assurance_cost_per_unit``. The policy is read in the period of the group
    inception for the contracting entity (pin P). A product without a cost rate accrues nothing,
    with reason ``NO_COST_RATE``. ``EXTERNAL`` yields no definition.
    """
    parents = {
        (line.contract_key, line.bundle_parent_obligation_key)
        for line in assurance_lines
        if line.bundle_parent_obligation_key is not None
    }
    found: list[WarrantyAccrual] = []
    for ob in obligations:
        if ob.obligation_kind in (ObligationKind.SERVICE_WARRANTY, ObligationKind.VC_LINE):
            continue
        product = st.canonical.group.products.get(ob.product_code)
        cost = (
            None
            if product is None or product.assurance_cost_per_unit is None
            else to_fraction(product.assurance_cost_per_unit)
        )
        assured = (
            ob.warranty_type == WarrantyType.ASSURANCE
            or (ob.contract_key, ob.obligation_key) in parents
            or cost is not None
        )
        if not assured or _policy(ctx, st, ob) != ENGINE:
            continue
        reason = NO_COST_RATE if cost is None else None
        found.append(WarrantyAccrual(ob.subject_key, ob.product_code, cost, reason))
    return tuple(sorted(found, key=lambda accrual: accrual.subject_key))


def _policy(ctx: BookContext, st: IdentifiedState, ob: PobDraft) -> object:
    entity = ob.contracting_entity
    period = dates.period_of(ctx.entities[entity], st.inception_date).period_key
    return ctx.policies.value(ACCRUAL_POLICY, entity=entity, period=period)
