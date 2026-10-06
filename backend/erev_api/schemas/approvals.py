"""API-R-09 Approvals schemas: API-S-Approval, the approval commands and delegations (04 §15.3
API-R-09, §16.10, T-PLT-21; SCREENS §15.3 to §15.7 bindings; PRD BR-PLT-07)."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any, Final

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from erev_api.enums import (
    ApprovalDecisionKind,
    ApprovalRequestStatus,
    ApprovalStepStatus,
    ApprovalSubjectType,
    BookCode,
)
from erev_api.schemas.common import ActorOut, MoneyOut, ProblemOut, RefOut

SHA256_PATTERN: Final = r"^[0-9a-f]{64}$"
MEMO_LENGTH: Final = 4000


class ApprovalSubjectOut(BaseModel):
    type: ApprovalSubjectType
    id: uuid.UUID
    display: str
    href: str | None
    content_sha256: str
    row_version: int | None


class ApprovalRoutingOut(BaseModel):
    """The routing rule the steps came from; both null for the subject's default step."""

    rule_set_version_id: uuid.UUID | None
    rule_key: str | None


class ApprovalDecisionOut(BaseModel):
    id: uuid.UUID
    decision: ApprovalDecisionKind
    approver: ActorOut
    on_behalf_of: ActorOut | None
    decided_at: datetime
    # The decider's own words, both content (04 §16.10 rev 1.208 and rev 1.252): ``reason_code``
    # is free text of up to 100 characters, bound to no code table.
    comment: str | None
    reason_code: str | None
    auto_rule_key: str | None


class ApprovalStepOut(BaseModel):
    step_no: int
    name: str
    required_permission: str
    min_approvers: int
    status: ApprovalStepStatus
    decisions: list[ApprovalDecisionOut]


class ImpactCriteriaMetOut(BaseModel):
    """One book a criteria-met activation moves, with its POL-013 catch-up (04 §16.10 rev
    1.126)."""

    book: BookCode
    effective_date: date
    judgement_record_id: uuid.UUID
    catch_up_total: MoneyOut | None


class ImpactPreviewSummaryOut(BaseModel):
    """The before and after figures of the stored preview (REQ-PLT-015). ``catch_up_total`` and
    ``criteria_met`` are the preview's ``after`` members of those names, null when it states none
    (04 §16.10 rev 1.126; supervisor ruling R-61 (f))."""

    revenue_by_period_before: Any
    revenue_by_period_after: Any
    balances_before: Any
    balances_after: Any
    journal_lines: Any
    catch_up_total: MoneyOut | None
    criteria_met: list[ImpactCriteriaMetOut] | None


class ImpactPreviewOut(BaseModel):
    file_id: uuid.UUID
    sha256: str
    summary: ImpactPreviewSummaryOut


class ApprovalAttachmentOut(BaseModel):
    file_id: uuid.UUID
    original_filename: str | None


class ApprovalOut(BaseModel):
    """API-S-Approval."""

    id: uuid.UUID
    request_no: str
    subject: ApprovalSubjectOut
    summary: str
    status: ApprovalRequestStatus
    entity: RefOut | None
    # 04 §16.10 rev 1.104 (R-41 (8)): every legal entity the request names that the reader may
    # read; how many it names in all; and whether it spans every entity of the workspace.
    entities: list[RefOut]
    entity_count: int
    all_entities: bool
    amount: MoneyOut | None
    flags: list[str]
    routing: ApprovalRoutingOut
    preparer: ActorOut
    submitted_at: datetime
    # 04 §16.10 rev 1.252 (item APR-REQUEST-REASON-1; supervisor rulings R-83 (d), R-104 (a)): the
    # reason code and the comment the request was SUBMITTED with (T-PLT-17) — a decision's own two
    # are under its step. Content: null on a withheld answer, except to the preparer, who reads
    # the two she wrote.
    reason_code: str | None
    comment: str | None
    decided_at: datetime | None
    voided_at: datetime | None
    void_reason: str | None
    current_step_no: int
    steps: list[ApprovalStepOut]
    impact_preview: ImpactPreviewOut | None
    attachments: list[ApprovalAttachmentOut]
    can_decide: bool
    # 04 §16.10 rev 1.208 (item APR-CONTENT-SCOPE-1): true for a reader who covers only some of
    # the request's entities. ``summary`` and ``subject.display`` then read the subject type's
    # name and the request's number, ``amount`` and ``impact_preview`` are null, ``flags`` and
    # ``attachments`` are empty and no decision carries its comment — nor, since rev 1.252, its
    # reason code (item APR-DECISION-CODE-CONTENT-1).
    content_withheld: bool


class ApprovalApproveIn(BaseModel):
    """``POST /approvals/{id}/approve``: the hashes the approver reviewed (REQ-PLT-014)."""

    model_config = ConfigDict(extra="forbid")

    subject_content_sha256: str = Field(pattern=SHA256_PATTERN)
    impact_preview_sha256: str | None = Field(default=None, pattern=SHA256_PATTERN)
    comment: str | None = Field(default=None, max_length=MEMO_LENGTH)
    reason_code: str | None = Field(default=None, max_length=100)


class ApprovalRejectIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    comment: str = Field(min_length=1, max_length=MEMO_LENGTH)
    reason_code: str | None = Field(default=None, max_length=100)


class ApprovalWithdrawIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    comment: str | None = Field(default=None, max_length=MEMO_LENGTH)


class BulkApproveItemIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    approval_request_id: uuid.UUID
    subject_content_sha256: str = Field(pattern=SHA256_PATTERN)
    impact_preview_sha256: str | None = Field(default=None, pattern=SHA256_PATTERN)


class BulkApproveIn(BaseModel):
    """1 to 200 items; the approval engine refuses another count with rule REQ-PLT-017."""

    model_config = ConfigDict(extra="forbid")

    items: list[BulkApproveItemIn] = Field(json_schema_extra={"minItems": 1, "maxItems": 200})
    comment: str | None = Field(default=None, max_length=MEMO_LENGTH)


class BulkApproveResultOut(BaseModel):
    approval_request_id: uuid.UUID
    status: ApprovalRequestStatus | None
    problem: ProblemOut | None


class BulkApproveOut(BaseModel):
    results: list[BulkApproveResultOut]


class ApprovalDelegationIn(BaseModel):
    """``POST /approval-delegations`` (T-PLT-21; BR-PLT-07)."""

    model_config = ConfigDict(extra="forbid")

    delegate_membership_id: uuid.UUID
    permissions: list[str] = Field(min_length=1, max_length=50)
    valid_from: AwareDatetime
    valid_to: AwareDatetime
    reason: str = Field(min_length=1, max_length=MEMO_LENGTH)


class ApprovalDelegationRevokeIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str | None = Field(default=None, max_length=MEMO_LENGTH)


class ApprovalDelegationOut(BaseModel):
    """One T-PLT-21 delegation with the people it names."""

    id: uuid.UUID
    delegator_membership_id: uuid.UUID
    delegator: ActorOut
    delegate_membership_id: uuid.UUID
    delegate: ActorOut
    permissions: list[str]
    valid_from: datetime
    valid_to: datetime
    reason: str
    revoked_at: datetime | None
    revoked_by: ActorOut | None
    created_at: datetime
    created_by: ActorOut
