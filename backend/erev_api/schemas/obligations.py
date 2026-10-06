"""API-R-29 obligation commands and events, and the API-R-13 policy-override schemas (04 §15.3
API-R-29, API-R-13; §16.2 obligation commands and API-S-Obligation ``material_right``; §16.3
API-S-Event; §16.5 API-S-PolicyOverride; BUILD_SPEC CTR-15, BS3-D-04).

API-S-Obligation and API-S-ScheduleLine live in ``schemas.contracts`` (CTR-4).
``GET /obligations/{id}/events`` answers API-S-Event as every other read of an event does:
``schemas.events.EventOut``, built by ``events.event_outs`` (04 rev 1.273). The model this module
held for that route (``ObligationEventOut``, L4-2-Q-6) had fallen behind the events resource of
CTR-5 — no ``prepared_by``, no ``approved_by``, ``source_row`` always null — and is removed.
``PolicyOverrideOut`` adds to API-S-PolicyOverride the T-CON-23 columns ``obligation_id``,
``level``, ``content_sha256``, ``supersedes_id``, ``created_at``, ``updated_at`` and
``row_version`` (as L3-1-Q-8 for API-S-Policy).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any, Final

from pydantic import BaseModel, ConfigDict, Field

from erev_api.enums import ConfigStatus, RegistryScope
from erev_api.schemas.users import MEMO_LENGTH

KEY_LENGTH: Final = 200

__all__ = [
    "MaterialRightOut",
    "PolicyOverrideCommentIn",
    "PolicyOverrideIn",
    "PolicyOverrideOut",
    "SspOverrideIn",
    "SspOverrideOut",
]


class SspOverrideIn(BaseModel):
    """``POST /obligations/{id}/request-ssp-override`` (04 §16.2; SCREENS R-26)."""

    model_config = ConfigDict(extra="forbid")

    ssp_book_version_id: uuid.UUID
    justification: str = Field(min_length=1, max_length=MEMO_LENGTH)


class SspOverrideOut(BaseModel):
    """200 of ``request-ssp-override``: the ``SSP_OVERRIDE`` request."""

    approval_request_id: uuid.UUID


class MaterialRightOut(BaseModel):
    """API-S-Obligation ``material_right`` (04 §16.2, T-CON-14; SCREENS R-25)."""

    option_type: str
    incremental_discount_ratio: str | None
    expected_purchase_amount: str | None
    expiry_date: date | None
    ssp_method: str | None
    likelihood_estimate_id: uuid.UUID | None
    status: str
    status_date: date | None


class PolicyOverrideIn(BaseModel):
    """``POST /policy-overrides``: a DRAFT override; ``obligation_key`` = level OBLIGATION."""

    model_config = ConfigDict(extra="forbid")

    contract_id: uuid.UUID
    obligation_key: str | None = Field(default=None, min_length=1, max_length=KEY_LENGTH)
    policy_key: str = Field(min_length=1, max_length=KEY_LENGTH)
    value: Any
    rationale: str = Field(min_length=1, max_length=MEMO_LENGTH)
    judgement_record_id: uuid.UUID | None = None


class PolicyOverrideCommentIn(BaseModel):
    """``POST /policy-overrides/{id}/submit``."""

    model_config = ConfigDict(extra="forbid")

    comment: str | None = Field(default=None, max_length=MEMO_LENGTH)


class PolicyOverrideOut(BaseModel):
    """API-S-PolicyOverride with the T-CON-23 columns named in the module docstring."""

    id: uuid.UUID
    contract_id: uuid.UUID
    obligation_id: uuid.UUID | None
    obligation_key: str | None
    level: RegistryScope
    policy_key: str
    value: Any
    rationale: str
    judgement_record_id: uuid.UUID | None
    status: ConfigStatus
    content_sha256: str | None
    approval_request_id: uuid.UUID | None
    approved_at: datetime | None
    supersedes_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime
    row_version: int
