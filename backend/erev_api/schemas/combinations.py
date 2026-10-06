"""API-R-28 combination schemas (04 §15.3 API-R-28, §16.14 combination suggestions, T-CON-03,
T-CON-04, E-95, table 3.4-R; BUILD_SPEC CTR-8).

04 defines the suggestion read model and the dismiss body. [J] L4-1-Q-16: the group create and
submit bodies, and ``CombinationGroupDetailOut`` (the T-CON-03 columns with the current members and
the pending proposal), are this item's choices.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from erev_api.enums import CombinationStatus, ExceptionStatus, JudgementStatus, ReasonCode
from erev_api.schemas.common import RefOut

__all__ = [
    "CODIFICATION_CRITERIA",
    "CombinationGroupCreateIn",
    "CombinationGroupDetailOut",
    "CombinationGroupSubmitIn",
    "CombinationProposalOut",
    "CombinationSuggestionOut",
    "SuggestionDismissIn",
]

Memo = Annotated[str, StringConstraints(min_length=1, max_length=4000)]
Rationale = Annotated[str, StringConstraints(min_length=10, max_length=4000)]
# 606-10-25-9 criteria as the codification names them → T-CON-03 ``criterion`` literals.
CODIFICATION_CRITERIA: dict[str, str] = {
    "606-10-25-9(a)": "25_9_A",
    "606-10-25-9(b)": "25_9_B",
    "606-10-25-9(c)": "25_9_C",
}
Criterion = Literal["606-10-25-9(a)", "606-10-25-9(b)", "606-10-25-9(c)"]


class CombinationGroupCreateIn(BaseModel):
    """``POST /combination-groups``: a PROPOSED group of two or more contracts (REQ-CON-009)."""

    model_config = ConfigDict(extra="forbid")

    contract_ids: list[uuid.UUID] = Field(min_length=2, max_length=100)
    criterion: Criterion
    rationale: Memo


class CombinationGroupSubmitIn(BaseModel):
    """``POST /combination-groups/{id}/submit``: a PROPOSED group routes its combination; an
    APPLIED group routes ``leave_contract_ids`` leaving it as an error correction."""

    model_config = ConfigDict(extra="forbid")

    comment: Memo | None = None
    reason_code: ReasonCode | None = None
    leave_contract_ids: list[uuid.UUID] | None = Field(default=None, min_length=1, max_length=100)


class CombinationProposalOut(BaseModel):
    """The pending proposal of a group: the ``COMBINATION`` judgement record that records it."""

    action: Literal["JOIN", "LEAVE"]
    contract_ids: list[uuid.UUID] = Field(
        description="The contracts of the proposal the caller reads (REQ-PLT-012)"
    )
    contract_count: int = Field(
        description=(
            "How many contracts the proposal names in all: greater than the length of "
            "`contract_ids` when some are contracts the caller does not read"
        )
    )
    judgement_record_id: uuid.UUID
    status: JudgementStatus


class CombinationGroupDetailOut(BaseModel):
    """A T-CON-03 group with its current members (T-CON-04) and pending proposal (L4-1-Q-16)."""

    id: uuid.UUID
    code: str
    is_singleton: bool
    status: CombinationStatus
    transaction_currency: str
    criterion: str | None
    rationale: str | None
    judgement_record_id: uuid.UUID | None
    approval_request_id: uuid.UUID | None
    inception_date: date
    head_computation_id: uuid.UUID | None
    dirty_since: datetime | None
    member_contract_ids: list[uuid.UUID] = Field(
        description="The current members the caller reads (REQ-PLT-012)"
    )
    member_count: int = Field(
        description=(
            "How many current members the group has in all: greater than the length of "
            "`member_contract_ids` when some are contracts the caller does not read"
        )
    )
    proposal: CombinationProposalOut | None
    created_at: datetime
    updated_at: datetime


class CombinationSuggestionOut(BaseModel):
    """04 §16.14 combination suggestion: an exception item of code ``COMBINATION_SUGGESTED``."""

    id: uuid.UUID
    contract_ids: list[uuid.UUID]
    contract_external_ids: list[str]
    related_party_group: RefOut | None
    inception_dates: list[date]
    detection_window_days: int
    status: ExceptionStatus
    created_at: datetime


class SuggestionDismissIn(BaseModel):
    """``POST /combination-suggestions/{id}/dismiss`` (PRD WLD-K-11)."""

    model_config = ConfigDict(extra="forbid")

    rationale: Rationale
