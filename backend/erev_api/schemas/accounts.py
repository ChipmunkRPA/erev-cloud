"""API-R-20 chart of accounts schemas (04 §15.3 API-R-20, T-REF-13, E-38, E-52; SCREENS_B §9.5;
BUILD_SPEC RFD-6).

04 §16 defines no account schema. The members follow the T-REF-13 columns plus ``created_at``,
``updated_at`` and ``row_version``, as the calendar schemas do (L1-1-Q-6). ``source_system`` is set
by the command, never by the request, and ``code`` does not change after creation (L1-1-Q-8).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from erev_api.enums import AccountType, SourceSystem
from erev_api.schemas.roles import CODE_LENGTH
from erev_api.schemas.users import LABEL_LENGTH

NormalBalance = Literal["D", "C"]


class GlAccountIn(BaseModel):
    """``POST /gl-accounts``: a T-REF-13 account."""

    model_config = ConfigDict(extra="forbid")

    code: str = Field(max_length=CODE_LENGTH, description="Account number, stored as text")
    name: str = Field(max_length=LABEL_LENGTH)
    account_type: AccountType
    normal_balance: NormalBalance = Field(description="D (debit) or C (credit)")
    entity_ids: list[uuid.UUID] = Field(
        default_factory=list, description="The entities that may use the account; empty = all"
    )
    required_dimensions: list[str] = Field(
        default_factory=list,
        description="Dimension codes mandatory on lines to this account (REQ-REF-009)",
    )
    is_active: bool = True


class GlAccountUpdateIn(BaseModel):
    """``PATCH /gl-accounts/{id}``: the members sent replace the stored values."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, max_length=LABEL_LENGTH)
    account_type: AccountType | None = None
    normal_balance: NormalBalance | None = None
    entity_ids: list[uuid.UUID] | None = None
    required_dimensions: list[str] | None = None
    is_active: bool | None = None


class GlAccountOut(BaseModel):
    """A T-REF-13 account (L1-1-Q-6)."""

    id: uuid.UUID
    code: str
    name: str
    account_type: AccountType
    normal_balance: NormalBalance
    entity_ids: list[uuid.UUID]
    required_dimensions: list[str]
    source_system: SourceSystem
    is_active: bool
    created_at: datetime
    updated_at: datetime
    row_version: int
