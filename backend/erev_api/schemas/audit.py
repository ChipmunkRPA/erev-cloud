"""API-R-10 audit schemas (04 T-PLT-19, T-PLT-23; SCREENS_B §6.3, §6.4, RPT-44).

04 names no API-S schema for this resource, so the shapes carry the table columns: an event without
``tenant_id``, with its actor as API-S-Actor and ``on_behalf_of_id`` as the API-S-Actor
``on_behalf_of`` (04 API-R-10, rev 1.139), and a verification without ``tenant_id`` and SC-C
(SPEC-Q-188). Two members of an event are read with its row and are no column (04 §16.14, rev
1.154): ``object_label``, the business identifier of the object, and ``actor_membership_id``, the
key the user screen takes.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel

from erev_api.enums import AuditOutcome, ControlResult
from erev_api.schemas.common import ActorOut


class AuditEventOut(BaseModel):
    """API-S-AuditEvent: one T-PLT-19 event; JSON values are redacted per ``audit.REDACT``."""

    id: uuid.UUID
    chain_seq: int
    occurred_at: datetime
    actor: ActorOut
    actor_membership_id: uuid.UUID | None
    actor_roles: list[str]
    auth_method: str | None
    mfa_verified: bool | None
    on_behalf_of: ActorOut | None
    api_client_id: uuid.UUID | None
    support_grant_id: uuid.UUID | None
    source_ip: str | None
    request_id: str
    action: str
    object_type: str
    object_id: uuid.UUID | None
    object_label: str | None
    object_version: str | None
    before: dict[str, Any] | None
    after: dict[str, Any] | None
    diff: list[dict[str, Any]] | None
    reason_code: str | None
    comment: str | None
    approval_request_id: uuid.UUID | None
    outcome: AuditOutcome
    detail: dict[str, Any]
    prev_hmac: str | None
    hmac: str
    hmac_key_id: str


class AuditActorsOut(BaseModel):
    """The principals with an id that acted in a range of the log (04 §16.14, rev 1.154)."""

    items: list[ActorOut]
    is_truncated: bool


class AuditChainVerificationOut(BaseModel):
    """API-S-AuditChainVerification: one T-PLT-23 run."""

    id: uuid.UUID
    trigger: Literal["SCHEDULED", "ON_DEMAND"]
    from_chain_seq: int
    to_chain_seq: int
    events_checked: int
    result: ControlResult
    first_failure_seq: int | None
    failure_detail: dict[str, Any] | None
    digest_last_hmac: str | None
    digest_file_id: uuid.UUID | None
    job_id: uuid.UUID | None
    started_at: datetime
    finished_at: datetime
