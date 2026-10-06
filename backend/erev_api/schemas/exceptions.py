"""API-R-44 exception queue schemas (04 §15.3 API-R-44, T-IMP-05, §16.14 exception item additions,
E-42 to E-44, E-106, E-117; SCREENS §13.4, §13.5; BUILD_SPEC DIN-11).

``ExceptionItemOut`` carries every T-IMP-05 column except ``tenant_id`` and the SC-C and SC-M actor
columns, plus ``available_actions`` and ``dismiss_blocked_reason`` (04 §16.14) and
``contract_external_id``, which the SF-11 master row shows (SCREENS §13.4), and
``combination_group_code``, the code of the contract group the item names (04 §16.14, rev 1.206):
the item of a group of several contracts names no contract. ``resolved_by`` is
API-S-Actor in place of the ``resolved_by`` and ``resolved_by_kind`` columns, and ``owner`` is the
API-S-Actor of ``owner_membership_id`` — read-only beside the id, which stays because it is the key
``assign`` takes and answers (04 §16.14, rev 1.139; supervisor ruling on API-ACTOR-MEMBERS-1 J3).

[J] L6-1-Q-12: 04 defines no command bodies for API-R-44, so the bodies take the SCREENS §13.5
fields ``owner_membership_id``, ``resolution`` and ``comment`` (at least 10 characters each).
``request-waiver`` answers ``{approval_request_id, request_no}``, as the checklist waiver answers
``{approval_request_id}`` (04 §16.8), with the number that the SCREENS banner shows.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, StringConstraints

from erev_api.enums import (
    ExceptionAction,
    ExceptionDisposition,
    ExceptionSeverity,
    ExceptionSource,
    ExceptionStatus,
)
from erev_api.schemas.common import ActorOut

__all__ = [
    "ExceptionAssignIn",
    "ExceptionCommentIn",
    "ExceptionItemOut",
    "ExceptionResolveIn",
    "WaiverRequestedOut",
]

Remark = Annotated[str, StringConstraints(strip_whitespace=True, min_length=10, max_length=4000)]


class ExceptionItemOut(BaseModel):
    """T-IMP-05 ``exception_item`` with the 04 §16.14 actions."""

    id: uuid.UUID
    exception_no: str
    source: ExceptionSource
    code: str
    severity: ExceptionSeverity
    disposition: ExceptionDisposition
    status: ExceptionStatus
    priority: int
    title: str
    message: str
    suggestion: str | None
    field: str | None
    business_key: str | None
    source_payload: dict[str, Any] | None
    import_upload_id: uuid.UUID | None
    import_row_id: uuid.UUID | None
    sync_run_id: uuid.UUID | None
    source_record_id: uuid.UUID | None
    contract_id: uuid.UUID | None
    contract_external_id: str | None
    obligation_id: uuid.UUID | None
    combination_group_id: uuid.UUID | None
    combination_group_code: str | None
    entity_id: uuid.UUID | None
    period_id: uuid.UUID | None
    close_run_id: uuid.UUID | None
    journal_run_id: uuid.UUID | None
    owner_membership_id: uuid.UUID | None
    owner: ActorOut | None
    dedupe_key: str
    occurrence_count: int
    last_seen_at: datetime
    resolution: str | None
    resolved_at: datetime | None
    resolved_by: ActorOut | None
    waiver_approval_request_id: uuid.UUID | None
    reprocessed_at: datetime | None
    created_at: datetime
    updated_at: datetime
    row_version: int
    available_actions: list[ExceptionAction]
    dismiss_blocked_reason: Literal["INPUT_COMMITTED"] | None


class ExceptionAssignIn(BaseModel):
    """``POST /exceptions/{id}/assign``: the owner's membership (SCREENS §13.5 Owner)."""

    model_config = ConfigDict(extra="forbid")

    owner_membership_id: uuid.UUID


class ExceptionResolveIn(BaseModel):
    """``POST /exceptions/{id}/resolve`` (SCREENS §13.5 "Mark resolved")."""

    model_config = ConfigDict(extra="forbid")

    resolution: Remark


class ExceptionCommentIn(BaseModel):
    """``POST /exceptions/{id}/dismiss`` and ``/request-waiver`` (PRD BR-DAT-04, SM-06)."""

    model_config = ConfigDict(extra="forbid")

    comment: Remark


class WaiverRequestedOut(BaseModel):
    """The ``EXCEPTION_WAIVER`` request a waiver request opened."""

    approval_request_id: uuid.UUID
    request_no: str
