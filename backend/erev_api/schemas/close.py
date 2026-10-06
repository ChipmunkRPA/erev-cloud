"""Close cockpit schemas: API-S-PeriodCockpit, the checklist commands and the tenant-defined close
tasks (04 §16.8 API-S-PeriodCockpit, "Period commands"; §15.3 API-R-18
``/close-checklist-templates`` rev 1.3; T-CLS-02, T-CLS-03, T-CLS-08; E-60, E-61, E-122;
BUILD_SPEC CLO-4, BS4-D-06, BS4-D-07)."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from erev_api.enums import (
    AccountRole,
    ApprovalSubjectType,
    ChecklistGateKind,
    ChecklistStatus,
    DerivedBlockerCode,
)
from erev_api.money import MoneyOut
from erev_api.schemas.common import ActorOut
from erev_api.schemas.periods import MEMO_LENGTH, PeriodOut
from erev_api.schemas.roles import CODE_LENGTH
from erev_api.schemas.users import LABEL_LENGTH

DUE_OFFSET_MAX = 366  # T-CLS-02 ``due_offset_days``: business days after period end


class ChecklistResultOut(BaseModel):
    """T-CLS-03 ``result`` of an automatic gate: ``{count, detail, evaluated_at}``."""

    count: int | None
    detail: str | None
    evaluated_at: datetime


class ChecklistSignoffOut(BaseModel):
    """The T-CLS-08 sign-off of a manual close task."""

    signer: ActorOut
    signed_at: datetime


class ChecklistItemOut(BaseModel):
    """One API-S-PeriodCockpit ``checklist`` row: a T-CLS-03 item with its template's code, name
    and kind. ``gate_check_code`` names the SCREENS_B §1.1 gate label and test hook; ``is_blocking``
    and ``row_version`` are the item's own columns. ``is_waivable`` is false for the gates no
    waiver clears — journal balancing, journal completeness, the close run and the controller
    certification (04 §16.8 rev 1.106, 1.172; supervisor rulings R-55 (c), R-114 (b)) — and true
    for every other gate and task."""

    id: uuid.UUID
    code: str
    name: str
    gate_kind: ChecklistGateKind
    gate_check_code: str | None
    is_blocking: bool
    status: ChecklistStatus
    owner: ActorOut | None
    due_date: date | None
    result: ChecklistResultOut | None
    signoff: ChecklistSignoffOut | None
    waiver_approval_request_id: uuid.UUID | None
    is_waivable: bool
    row_version: int


class JournalPreviewRoleOut(BaseModel):
    """The period's subledger lines of one account role, in functional currency."""

    account_role: AccountRole
    debit: MoneyOut
    credit: MoneyOut


class JournalPreviewOut(BaseModel):
    """API-S-PeriodCockpit ``journal_preview``: the Dr = Cr check of the period (REQ-CLS-008).
    ``difference_functional`` (debits less credits) is the SCREENS_B §1.1 "Journal difference" KPI
    and the §1.3 check strip, so the screen never subtracts money (DG-FE-08). [J] L7-2-Q-12."""

    debit_functional: MoneyOut
    credit_functional: MoneyOut
    difference_functional: MoneyOut
    balanced: bool
    by_account_role: list[JournalPreviewRoleOut]


class DaysToCloseOut(BaseModel):
    """One period of ``kpis.days_to_close_last_three``; ``days`` is null while it is not locked
    (SCREENS_B §1.1 "In progress"; REQ-CLS-020)."""

    period_key: str
    days: int | None


class ReconciliationsReviewedOut(BaseModel):
    """SCREENS_B §1.1 KPI "Reconciliations reviewed" ``<reviewed> of <required>``: the required
    kinds (T-PLT-31) with a reconciliation of the period in ``REVIEWED``, ``AUTO_CERTIFIED`` or
    ``CERTIFIED``. [J] L7-2-Q-12."""

    reviewed: int
    required: int


class CockpitKpisOut(BaseModel):
    days_to_close_last_three: list[DaysToCloseOut]
    reconciliations_reviewed: ReconciliationsReviewedOut


class DerivedBlockerOut(BaseModel):
    """E-122: a derived close blocker with its count; both codes are always present."""

    code: DerivedBlockerCode
    count: int


class PendingRequestCountOut(BaseModel):
    """04 API-S-PeriodCockpit ``pending_requests`` (rev 1.8; D-90a QA-L9-7): the ``PENDING``
    approval requests of the entity of one E-08 type; ``JUDGEMENT_RECORD`` then
    ``MANUAL_ADJUSTMENT``, both always present. Counts only, the same for every reader
    (SCREENS_B §1.1 BLK-06, BLK-15)."""

    subject_type: ApprovalSubjectType
    count: int


class PeriodCockpitOut(BaseModel):
    """API-S-PeriodCockpit (``GET /periods/{id}/cockpit``)."""

    period: PeriodOut
    checklist: list[ChecklistItemOut]
    journal_preview: JournalPreviewOut
    kpis: CockpitKpisOut
    derived_blockers: list[DerivedBlockerOut]
    pending_requests: list[PendingRequestCountOut]


class ChecklistSignIn(BaseModel):
    """``POST /periods/{id}/checklist/{item_id}/sign`` (MFA-verified session)."""

    model_config = ConfigDict(extra="forbid")

    statement_accepted: bool


class ChecklistWaiveIn(BaseModel):
    """``POST /periods/{id}/checklist/{item_id}/waive``."""

    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=1, max_length=MEMO_LENGTH)


class ChecklistWaiverOut(BaseModel):
    """The ``EXCEPTION_WAIVER`` request a checklist waiver opened (BS4-D-07)."""

    approval_request_id: uuid.UUID
    request_no: str


class CloseChecklistTemplateOut(BaseModel):
    """T-CLS-02: a system gate or a tenant-defined close task."""

    id: uuid.UUID
    code: str
    name: str
    description: str | None
    gate_kind: ChecklistGateKind
    gate_check_code: str | None
    is_blocking: bool
    is_system: bool
    owner_role_id: uuid.UUID | None
    due_offset_days: int | None
    sequence: int
    is_active: bool
    created_at: datetime
    updated_at: datetime
    row_version: int


class CloseChecklistTemplateCreateIn(BaseModel):
    """``POST /close-checklist-templates``: a tenant-defined close task (REQ-CLS-021)."""

    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=1, max_length=CODE_LENGTH)
    name: str = Field(min_length=1, max_length=LABEL_LENGTH)
    description: str | None = Field(default=None, max_length=MEMO_LENGTH)
    gate_kind: ChecklistGateKind
    is_blocking: bool = True
    owner_role_id: uuid.UUID | None = None
    due_offset_days: int | None = Field(default=None, ge=0, le=DUE_OFFSET_MAX)
    is_active: bool = True


class CloseChecklistTemplateUpdateIn(BaseModel):
    """``PATCH /close-checklist-templates/{id}`` (``If-Match``). A system gate changes only in
    ``owner_role_id`` and ``due_offset_days`` (T-CLS-02 IM-M)."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=LABEL_LENGTH)
    description: str | None = Field(default=None, max_length=MEMO_LENGTH)
    is_blocking: bool | None = None
    owner_role_id: uuid.UUID | None = None
    due_offset_days: int | None = Field(default=None, ge=0, le=DUE_OFFSET_MAX)
    is_active: bool | None = None
