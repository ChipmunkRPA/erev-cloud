"""API-R-37 manual adjustment schemas (04 §15.3 API-R-37, §16.14 "API-R-37 shapes", T-SL-05, E-93,
E-94, E-110, API-C-06; BUILD_SPEC CLO-12).

The request payload is the kind-specific object of T-SL-05: a release or deferral names the
obligation and exactly one of ``amount``, ``ratio`` and ``remaining``; a schedule override names
the obligation and its ``periods``; a manual journal or an account reclassification carries
``lines`` and may name the obligation they belong to. Money members are API-S-Money and refuse a
bare JSON number with rule ``API-C-06``; ``ratio`` is a decimal string. The command validates the
payload against its kind and collects the findings (``domain.journals.adjustments``).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Any, Final, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, StringConstraints
from pydantic_core import PydanticCustomError

from erev_api.enums import (
    AccountRole,
    BookCode,
    ManualAdjustmentKind,
    ManualAdjustmentStatus,
    ReasonCode,
)
from erev_api.money import MONEY_MESSAGE, RULE_ID, DecimalStr, MoneyIn, MoneyOut
from erev_api.schemas.common import ActorOut, RefOut

__all__ = [
    "AdjustmentLineIn",
    "AdjustmentPayloadIn",
    "AdjustmentPeriodIn",
    "ManualAdjustmentCreateIn",
    "ManualAdjustmentDeferIn",
    "ManualAdjustmentDiscardIn",
    "ManualAdjustmentOut",
    "ManualAdjustmentSubmitIn",
    "ManualAdjustmentUpdateIn",
    "ManualAdjustmentWithdrawIn",
]

MAX_PERIODS: Final = 120
MAX_LINES: Final = 200
DIMENSION_LENGTH: Final = 64
Memo = Annotated[str, StringConstraints(min_length=1, max_length=4000)]
DimensionText = Annotated[str, StringConstraints(min_length=1, max_length=DIMENSION_LENGTH)]


def _reject_number(value: object) -> object:
    """API-C-06: a money member sent as a JSON number instead of an API-S-Money object."""
    if isinstance(value, int | float | Decimal) and not isinstance(value, bool):
        raise PydanticCustomError("api_c_06", MONEY_MESSAGE, {"rule_id": RULE_ID})
    return value


_NUMBER_REFUSED = BeforeValidator(_reject_number)
ApiMoney = Annotated[MoneyIn, _NUMBER_REFUSED]
OptionalApiMoney = Annotated[MoneyIn | None, _NUMBER_REFUSED]


class AdjustmentPeriodIn(BaseModel):
    """One period of a ``SCHEDULE_OVERRIDE``: the revenue the obligation recognises in it."""

    model_config = ConfigDict(extra="forbid")

    period_id: uuid.UUID
    amount: ApiMoney


class AdjustmentLineIn(BaseModel):
    """One line of a ``MANUAL_JOURNAL`` or ``ACCOUNT_RECLASS``; ``amount_txn`` is signed, a debit
    positive and a credit negative (T-SL-04)."""

    model_config = ConfigDict(extra="forbid")

    account_role: AccountRole
    gl_account_id: uuid.UUID
    amount_txn: ApiMoney
    dimensions: dict[DimensionText, DimensionText] = Field(default_factory=dict, max_length=20)


class AdjustmentPayloadIn(BaseModel):
    """The kind-specific payload of T-SL-05."""

    model_config = ConfigDict(extra="forbid")

    obligation_id: uuid.UUID | None = None
    amount: OptionalApiMoney = None
    ratio: DecimalStr | None = None
    remaining: Literal[True] | None = None
    periods: tuple[AdjustmentPeriodIn, ...] | None = Field(default=None, max_length=MAX_PERIODS)
    lines: tuple[AdjustmentLineIn, ...] | None = Field(default=None, max_length=MAX_LINES)


class ManualAdjustmentCreateIn(BaseModel):
    """API-S-ManualAdjustmentCreate: ``POST /manual-adjustments`` answers 201."""

    model_config = ConfigDict(extra="forbid")

    kind: ManualAdjustmentKind
    contract_id: uuid.UUID
    book: BookCode | None = Field(default=None, description="Default the primary book; not LEGACY")
    effective_date: date
    reason_code: ReasonCode
    memo: Memo
    payload: AdjustmentPayloadIn


class ManualAdjustmentUpdateIn(BaseModel):
    """``PATCH /manual-adjustments/{id}`` (If-Match): the members sent replace the stored ones; a
    ``REJECTED`` adjustment returns to ``DRAFT`` with them (04 T-SL-05)."""

    model_config = ConfigDict(extra="forbid")

    effective_date: date | None = None
    reason_code: ReasonCode | None = None
    memo: Memo | None = None
    payload: AdjustmentPayloadIn | None = None


class ManualAdjustmentSubmitIn(BaseModel):
    """``POST /manual-adjustments/{id}/submit``."""

    model_config = ConfigDict(extra="forbid")

    comment: Memo | None = None


class ManualAdjustmentWithdrawIn(BaseModel):
    """``POST /manual-adjustments/{id}/withdraw``."""

    model_config = ConfigDict(extra="forbid")

    comment: Memo | None = None


class ManualAdjustmentDiscardIn(BaseModel):
    """``POST /manual-adjustments/{id}/discard``: the reason is required (BR-PLT-08)."""

    model_config = ConfigDict(extra="forbid")

    reason: Memo


class ManualAdjustmentDeferIn(BaseModel):
    """``POST /manual-adjustments/{id}/request-defer-past-lock``: the reason is required."""

    model_config = ConfigDict(extra="forbid")

    comment: Memo


class AdjustmentContractOut(BaseModel):
    id: uuid.UUID
    external_id: str
    contract_no: str


class AdjustmentObligationOut(BaseModel):
    id: uuid.UUID
    obligation_key: str


class AdjustmentPeriodOut(BaseModel):
    id: uuid.UUID
    period_key: str
    name: str
    start_date: date
    end_date: date


class AdjustmentRequestOut(BaseModel):
    """The adjustment's ``PENDING`` approval request and what its approval does: ``POSTING``
    posts the adjustment, ``DEFER_PAST_LOCK`` marks it deferred past lock (REQ-JE-019)."""

    id: uuid.UUID
    purpose: Literal["POSTING", "DEFER_PAST_LOCK"]


class ManualAdjustmentOut(BaseModel):
    """API-S-ManualAdjustment (T-SL-05)."""

    id: uuid.UUID
    adjustment_no: str
    kind: ManualAdjustmentKind
    status: ManualAdjustmentStatus
    contract: AdjustmentContractOut
    obligation: AdjustmentObligationOut | None
    entity: RefOut
    book: BookCode
    period: AdjustmentPeriodOut
    effective_date: date
    payload: dict[str, Any]
    amount_functional_abs: MoneyOut
    currency: str
    reason_code: str
    memo: str
    impact_preview_file_id: uuid.UUID | None
    # 04 §16.10 "Who reads a stored preview" (rev 1.300; item MOD-PREVIEW-READ-SCOPE-1): true
    # when the adjustment retains a preview this caller is not answered, and
    # ``impact_preview_file_id`` is then null.
    impact_preview_withheld: bool = False
    content_sha256: str | None
    approval_request_id: uuid.UUID | None
    pending_request: AdjustmentRequestOut | None
    applied_event_id: uuid.UUID | None
    subledger_posting_id: uuid.UUID | None
    is_deferred_past_lock: bool
    attachment_count: int
    created_by: ActorOut
    created_at: datetime
    updated_at: datetime
    row_version: int
