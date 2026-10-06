"""API-R-32 estimate schemas (04 §15.3 API-R-32; T-CON-12, T-CON-13; E-09, E-10, E-12; §16.14
estimates; SCREENS §8.4 to §8.6, R-16, R-24; BUILD_SPEC CTR-12).

04 defines no API-S schema for estimates. [J] L5-2-Q-2: the create bodies are the T-CON-12 and
T-CON-13 columns a preparer enters, with obligations named by key; amounts are decimal strings in
the version's ``currency`` (the magnitudes of 04 B3-D16), and the outputs are the columns plus the
§16.14 additions, whose money members (``excluded_amount``, ``costs_incurred_to_date``) are
API-S-Money.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StringConstraints

from erev_api.enums import ConfigStatus, EstimateKind, EstimateMethod
from erev_api.money import CurrencyCode, DecimalStr, MoneyOut
from erev_api.schemas.common import ActorOut

__all__ = [
    "VC_ELEMENT_TYPES",
    "AllocationTarget",
    "ConstraintChecklistIn",
    "Direction",
    "EstimateCreateIn",
    "EstimateOut",
    "EstimateVersionCreateIn",
    "EstimateVersionOut",
    "EstimateVersionSubmitIn",
    "EstimateVersionSummaryOut",
    "EstimateVersionUpdateIn",
    "EstimateVersionWithdrawIn",
    "ScenarioIn",
    "VcElementType",
]

Memo = Annotated[str, StringConstraints(min_length=1, max_length=4000)]
Code = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9][A-Za-z0-9._\-]{0,63}$")]
Key = Annotated[str, StringConstraints(min_length=1, max_length=200)]
# 04 T-CON-12 ``ck_estimate__vc_element_type``.
VcElementType = Literal[
    "BONUS",
    "PENALTY",
    "PERFORMANCE_INCENTIVE",
    "REBATE",
    "VOLUME_TIER",
    "PRICE_PROTECTION",
    "SLA_CREDIT",
    "DISCOUNT",
    "RETURN",
    "REFUND",
    "IMPLICIT_PRICE_CONCESSION",
    "CLAIM",
    "UNPRICED_CHANGE_ORDER",
    "USAGE",
    "ROYALTY",
    "MILESTONE",
]
VC_ELEMENT_TYPES: tuple[str, ...] = (
    "BONUS",
    "PENALTY",
    "PERFORMANCE_INCENTIVE",
    "REBATE",
    "VOLUME_TIER",
    "PRICE_PROTECTION",
    "SLA_CREDIT",
    "DISCOUNT",
    "RETURN",
    "REFUND",
    "IMPLICIT_PRICE_CONCESSION",
    "CLAIM",
    "UNPRICED_CHANGE_ORDER",
    "USAGE",
    "ROYALTY",
    "MILESTONE",
)
Direction = Literal["INCREASE", "DECREASE"]
AllocationTarget = Literal["CONTRACT", "OBLIGATIONS", "INCREMENTS"]


class EstimateCreateIn(BaseModel):
    """``POST /contracts/{id}/estimates``: an estimated element (T-CON-12)."""

    model_config = ConfigDict(extra="forbid")

    estimate_kind: EstimateKind
    element_code: Code
    obligation_key: Key | None = Field(default=None, description="The obligation the element names")
    vc_element_type: VcElementType | None = Field(
        default=None, description="Required for VARIABLE_CONSIDERATION"
    )
    direction: Direction | None = Field(
        default=None,
        description="Default: DECREASE for price concessions and the reducing element types of "
        "B3-DG-17, otherwise INCREASE",
    )
    method: EstimateMethod
    allocation_target: AllocationTarget = "CONTRACT"
    target_obligation_keys: list[Key] = Field(default_factory=list, max_length=500)
    allocation_criteria_evidence: Memo | None = Field(
        default=None, description="606-10-32-40 evidence; required unless the target is CONTRACT"
    )


class ScenarioIn(BaseModel):
    """One outcome of a version's scenario table (T-CON-13 ``scenarios``)."""

    model_config = ConfigDict(extra="forbid")

    outcome: Memo
    amount: DecimalStr
    probability: DecimalStr | None = Field(
        default=None, description="Required for EXPECTED_VALUE; the probabilities sum to 1"
    )


class ConstraintChecklistIn(BaseModel):
    """T-CON-13 ``constraint_checklist`` (04 rev 1.210; item EST-CONSTRAINT-KEYS-1): the factors
    of ASC 606-10-32-12 that increase the likelihood or the magnitude of a revenue reversal, one
    boolean each — true: the factor is present; false: considered and not present. A checklist
    holds all five or is not sent; a version stored before the keys were named answers what it
    stored."""

    model_config = ConfigDict(extra="forbid")

    susceptible_to_outside_factors: StrictBool = Field(description="606-10-32-12(a)")
    long_resolution_period: StrictBool = Field(description="606-10-32-12(b)")
    limited_experience: StrictBool = Field(description="606-10-32-12(c)")
    price_concession_practice: StrictBool = Field(description="606-10-32-12(d)")
    broad_range_of_amounts: StrictBool = Field(description="606-10-32-12(e)")


class EstimateVersionCreateIn(BaseModel):
    """``POST /estimates/{id}/versions``: a DRAFT version (T-CON-13). ``method`` repeats the
    element's method, which is fixed after version 1 (POL-040)."""

    model_config = ConfigDict(extra="forbid")

    method: EstimateMethod | None = None
    effective_date: date
    scenarios: list[ScenarioIn] = Field(default_factory=list, max_length=100)
    parameters: dict[str, Any] = Field(default_factory=dict)
    unconstrained_amount: DecimalStr | None = None
    most_conservative_amount: DecimalStr | None = None
    constrained_amount: DecimalStr | None = None
    rate: DecimalStr | None = None
    expected_total_amount: DecimalStr | None = None
    expected_quantity: DecimalStr | None = None
    amortization_months: int | None = Field(default=None, ge=0, le=1200)
    currency: CurrencyCode | None = Field(
        default=None, description="Defaults to the contract's transaction currency"
    )
    constraint_checklist: ConstraintChecklistIn | None = Field(
        default=None, description="The five 606-10-32-12 factors, or null"
    )
    rationale: Memo
    judgement_record_id: uuid.UUID | None = None
    modification_id: uuid.UUID | None = Field(
        default=None,
        description="A DRAFT modification of the estimate's contract: the version is created "
        "inside it and is approved before that modification is submitted (PRD BR-MOD-02)",
    )


class EstimateVersionUpdateIn(BaseModel):
    """``PATCH /estimate-versions/{id}``: the members sent replace the stored values of a DRAFT
    version; a REJECTED or WITHDRAWN version returns to DRAFT (E-12)."""

    model_config = ConfigDict(extra="forbid")

    method: EstimateMethod | None = None
    effective_date: date | None = None
    scenarios: list[ScenarioIn] | None = Field(default=None, max_length=100)
    parameters: dict[str, Any] | None = None
    unconstrained_amount: DecimalStr | None = None
    most_conservative_amount: DecimalStr | None = None
    constrained_amount: DecimalStr | None = None
    rate: DecimalStr | None = None
    expected_total_amount: DecimalStr | None = None
    expected_quantity: DecimalStr | None = None
    amortization_months: int | None = Field(default=None, ge=0, le=1200)
    currency: CurrencyCode | None = None
    constraint_checklist: ConstraintChecklistIn | None = None
    rationale: Memo | None = None
    judgement_record_id: uuid.UUID | None = None


class EstimateVersionSubmitIn(BaseModel):
    """``POST /estimate-versions/{id}/submit``."""

    model_config = ConfigDict(extra="forbid")

    comment: Memo | None = None


class EstimateVersionWithdrawIn(BaseModel):
    """``POST /estimate-versions/{id}/withdraw``."""

    model_config = ConfigDict(extra="forbid")

    comment: Memo | None = None


class EstimateVersionSummaryOut(BaseModel):
    """``current_version`` and ``latest_version`` of an estimate list item (04 §16.14)."""

    id: uuid.UUID
    version_no: int
    status: ConfigStatus
    effective_date: date
    approver: ActorOut | None
    approved_at: datetime | None


class EstimateOut(BaseModel):
    """A T-CON-12 element with its version summaries (04 §16.14; SCREENS §8.6)."""

    id: uuid.UUID
    contract_id: uuid.UUID | None
    portfolio_id: uuid.UUID | None
    obligation_id: uuid.UUID | None
    obligation_key: str | None
    estimate_kind: EstimateKind
    element_code: str
    vc_element_type: str | None
    direction: Direction
    method: EstimateMethod
    allocation_target: AllocationTarget
    target_obligation_ids: list[uuid.UUID]
    target_obligation_keys: list[str]
    allocation_criteria_evidence: str | None
    current_version: EstimateVersionSummaryOut | None
    latest_version: EstimateVersionSummaryOut | None
    created_by: ActorOut
    created_at: datetime


class EstimateVersionOut(BaseModel):
    """A T-CON-13 version with the 04 §16.14 additions."""

    id: uuid.UUID
    estimate_id: uuid.UUID
    version_no: int
    status: ConfigStatus
    effective_date: date
    scenarios: list[dict[str, Any]]
    parameters: dict[str, Any]
    unconstrained_amount: str | None
    most_conservative_amount: str | None
    constrained_amount: str | None
    rate: str | None
    expected_total_amount: str | None
    expected_quantity: str | None
    amortization_months: int | None
    currency: str | None
    constraint_checklist: dict[str, Any] | None
    rationale: str
    judgement_record_id: uuid.UUID | None
    content_sha256: str | None
    approval_request_id: uuid.UUID | None
    applied_event_ids: list[uuid.UUID]
    supersedes_version_id: uuid.UUID | None
    modification_id: uuid.UUID | None = Field(
        default=None,
        description="The modification the version was created inside (T-CON-13); never changed",
    )
    approver: ActorOut | None
    approved_at: datetime | None
    excluded_amount: MoneyOut | None = Field(
        default=None, description="VARIABLE_CONSIDERATION: max(0, unconstrained − constrained)"
    )
    costs_incurred_to_date: MoneyOut | None = Field(
        default=None, description="EAC: COST_INCURRED progress inputs through effective_date"
    )
    progress_ratio: str | None = Field(
        default=None, description="EAC: costs incurred to date ÷ expected total costs"
    )
    created_by: ActorOut
    created_at: datetime
    updated_at: datetime
    row_version: int
