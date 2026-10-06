"""API-R-30 event schemas (04 §15.3 API-R-30; §16.0; §16.3 API-S-EventAppend, API-S-Event; T-CON-24;
§16 API-S-ImpactSummary; table 3.4-R; BUILD_SPEC CTR-5).

Class names drop the ``API-S-`` prefix and append ``In`` or ``Out`` (DG-API-03). An append item
names ``effective_date`` or ``effective_at`` (an instant with an offset, converted to the
contracting entity's date, 05 TZ-03) and a ``payload`` validated as the latest payload model of its
type.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Annotated, Any

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StringConstraints

from erev_api.enums import (
    ComputationStatus,
    ContractEventType,
    HoldType,
    ModificationStatus,
    ReasonCode,
    Step1GateReason,
)
from erev_api.money import MoneyOut
from erev_api.schemas.common import ActorOut, RefOut
from erev_api.schemas.contracts import ContractOut

__all__ = [
    "AppendComputationOut",
    "EventAppendIn",
    "EventAppendItemIn",
    "EventComputationOut",
    "EventOut",
    "EventSourceRowOut",
    "EventSubmissionOut",
    "EventVoidRequestIn",
    "EventsAppendedOut",
    "HoldApplyIn",
    "HoldReleaseIn",
    "ImpactBalanceOut",
    "ImpactCatchUpOut",
    "ImpactJournalLineOut",
    "ImpactObligationAmountOut",
    "ImpactRevenuePeriodOut",
    "ImpactSummaryOut",
    "MemosUpdateIn",
    "SubmissionCreatedOut",
    "SubmissionWithdrawIn",
]

Key = Annotated[str, StringConstraints(min_length=1, max_length=255)]
Memo = Annotated[str, StringConstraints(min_length=1, max_length=4000)]
MAX_EVENTS = 500  # API-S-EventAppend: 1 to 500 events


class EventAppendItemIn(BaseModel):
    """One API-S-EventAppend item."""

    model_config = ConfigDict(extra="forbid")

    event_type: ContractEventType
    effective_date: date | None = None
    effective_at: AwareDatetime | None = Field(
        default=None, description="An instant with an offset; converted to the entity's date"
    )
    obligation_key: Key | None = None
    payload: dict[str, Any] = Field(description="Per the §16.3 payload table of event_type")


class EventAppendIn(BaseModel):
    """API-S-EventAppend (``POST /contracts/{id}/events`` and ``…/events/preview``)."""

    model_config = ConfigDict(extra="forbid")

    events: list[EventAppendItemIn] = Field(min_length=1, max_length=MAX_EVENTS)
    comment: Memo | None = None
    evidence_file_ids: list[uuid.UUID] = Field(default_factory=list)


class EventComputationOut(BaseModel):
    """The computation that first included an event."""

    id: uuid.UUID
    status: ComputationStatus


class EventSourceRowOut(BaseModel):
    import_upload_id: uuid.UUID
    sheet: str | None
    row_number: int


# The ONE model of an event of a contract's stream (04 rev 1.273): ``GET /contracts/{id}/events``,
# ``GET /events/{id}``, the answer of an append and ``GET /obligations/{id}/events`` answer it, all
# built by ``events.event_outs`` — pinned by ``tests/architecture/test_api_s_event_one_model.py``.
class EventOut(BaseModel):
    """API-S-Event."""

    id: uuid.UUID
    contract_id: uuid.UUID
    stream_version: int
    event_type: ContractEventType
    schema_version: int
    effective_date: date
    recorded_at: datetime
    record_seq: int
    origin: str
    is_manual: bool
    obligation_keys: list[str]
    payload: dict[str, Any]
    payload_sha256: str
    supersedes_event_id: uuid.UUID | None
    approval_request_id: uuid.UUID | None
    modification_id: uuid.UUID | None
    estimate_version_id: uuid.UUID | None
    manual_adjustment_id: uuid.UUID | None
    import_upload_id: uuid.UUID | None
    source_record_id: uuid.UUID | None
    source_row: EventSourceRowOut | None
    created_by: ActorOut
    # 04 API-S-Event rev 1.194 (BUILD_SPEC CTR-6; PRD J-08-AC-3): who prepared the approval
    # request the event names and whose decision approved it; null without a request.
    prepared_by: ActorOut | None
    approved_by: ActorOut | None
    # 04 API-S-Event rev 1.273 (§16.3 "Voids on this route"): the sentence
    # ``POST /events/{id}/request-void`` would answer for this event, or null where the route
    # would take it — the value of ``events.void_refusals``, so that a screen offers the void
    # only where it can be requested and keeps no list of voidable types of its own.
    void_refusal: str | None
    computation: EventComputationOut | None


class AppendComputationOut(BaseModel):
    """``computation`` of a 201 append: the command's computation and its versions per book."""

    id: uuid.UUID
    status: ComputationStatus
    contract_version_ids: dict[str, uuid.UUID]


class Step1GateOut(BaseModel):
    """What became of the not-a-contract gate of a request that assesses a DRAFT contract as not
    probable (04 §16.3 (c); supervisor rulings R-77 (6), R-84 (b)). ``appended``: the gate follows
    the assessment and the contract is NOT_A_CONTRACT. Otherwise the assessment is recorded, the
    contract stays DRAFT and ``reason`` (E-132) says why; the copy is the screen's."""

    appended: bool
    reason: Step1GateReason | None


class EventsAppendedOut(BaseModel):
    """201 of ``POST /contracts/{id}/events``. ``step1_gate`` is null for a request that decides
    no not-a-contract gate."""

    contract: ContractOut
    events: list[EventOut]
    computation: AppendComputationOut
    step1_gate: Step1GateOut | None


class EventVoidRequestIn(BaseModel):
    """``POST /events/{id}/request-void``: a reason of the table 3.4-R subset and a comment."""

    model_config = ConfigDict(extra="forbid")

    reason_code: ReasonCode
    comment: Memo


class SubmissionCreatedOut(BaseModel):
    event_submission_id: uuid.UUID
    approval_request_id: uuid.UUID


class SubmissionWithdrawIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    comment: Memo | None = None


# --- holds and memos (04 §16.1 contract commands; BUILD_SPEC CTR-10) ------------------------------

Comment = Annotated[str, StringConstraints(min_length=10, max_length=4000)]  # PRD BR-PLT-08
MemoText = Annotated[str, StringConstraints(max_length=4000)]


class HoldApplyIn(BaseModel):
    """``POST /contracts/{id}/apply-hold``."""

    model_config = ConfigDict(extra="forbid")

    hold_type: HoldType
    obligation_key: Key | None = Field(default=None, description="None holds the contract")
    reason: Comment


class HoldReleaseIn(BaseModel):
    """``POST /contracts/{id}/release-hold``."""

    model_config = ConfigDict(extra="forbid")

    hold_id: uuid.UUID
    comment: Comment


class MemosUpdateIn(BaseModel):
    """``POST /contracts/{id}/update-memos``: the members sent replace the stored values."""

    model_config = ConfigDict(extra="forbid")

    obligation_key: Key | None = None
    memo_1: MemoText | None = None
    memo_2: MemoText | None = None
    memo_3: MemoText | None = None
    custom_attributes: dict[str, Any] | None = None
    dimensions: dict[str, str] | None = None
    comment: Memo


class EventSubmissionOut(BaseModel):
    """T-CON-24 ``event_submission`` (04 defines no API-S schema; L4-1-Q-6)."""

    id: uuid.UUID
    contract_id: uuid.UUID
    contracting_entity_id: uuid.UUID
    events: list[dict[str, Any]]
    status: ModificationStatus
    comment: str | None
    content_sha256: str | None
    approval_request_id: uuid.UUID | None
    applied_event_ids: list[uuid.UUID]
    created_by: ActorOut
    created_at: datetime
    updated_at: datetime


class ImpactCatchUpOut(BaseModel):
    obligation_key: str
    treatment: str | None
    amount: MoneyOut


class ImpactObligationAmountOut(BaseModel):
    obligation_key: str
    amount: MoneyOut


class ImpactRevenuePeriodOut(BaseModel):
    period_key: str
    before: MoneyOut
    after: MoneyOut
    change: MoneyOut


class ImpactBalanceOut(BaseModel):
    balance: str
    amount: MoneyOut


class ImpactJournalLineOut(BaseModel):
    gl_account: RefOut | None
    account_role: str
    debit: MoneyOut
    credit: MoneyOut


class ImpactSummaryOut(BaseModel):
    """API-S-ImpactSummary (rev 1.2; SCREENS R-16): money in the contract currency."""

    transaction_price_before: MoneyOut
    transaction_price_after: MoneyOut
    catch_up_total: MoneyOut
    catch_up_by_obligation: list[ImpactCatchUpOut]
    remaining_allocation_before: list[ImpactObligationAmountOut]
    remaining_allocation_after: list[ImpactObligationAmountOut]
    revenue_by_period: list[ImpactRevenuePeriodOut]
    rpo_before: MoneyOut
    rpo_after: MoneyOut
    rpo_date: date
    balances_before: list[ImpactBalanceOut]
    balances_after: list[ImpactBalanceOut]
    journal_lines: list[ImpactJournalLineOut]
    progress_before: str | None
    progress_after: str | None
    replay_from_date: date
    posting_period_key: str | None
    origin_period_key: str | None
    # Item MOD-PREVIEW-JOURNAL-RULE-1 (04 API-S-ImpactSummary): ``journal_lines`` are the entries
    # the approval would post if its computation ran at ``computed_at`` — the application instant
    # of the dry run — whose last postable period was ``computed_period_key``. None in a summary
    # stored before the members existed.
    computed_at: datetime | None = None
    computed_period_key: str | None = None
