"""API-R-22 customer schemas (04 §15.3 API-R-22, §16.14 list additions, T-REF-18, T-REF-19, E-38;
SCREENS §9.4, §9.5; BUILD_SPEC RFD-8).

04 §16 defines no customer schema. The members follow the T-REF-18 and T-REF-19 columns plus
``created_at``, ``updated_at`` and ``row_version``, as the other reference schemas do (L1-1-Q-38).
A related-party group adds ``member_count`` (§16.14). A customer adds its group as API-S-Ref for the
grid's "Related-party group" column. ``source_system`` and ``external_id`` are set at creation only.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Final

from pydantic import BaseModel, ConfigDict, Field

from erev_api.enums import SourceSystem
from erev_api.schemas.common import RefOut
from erev_api.schemas.roles import CODE_LENGTH
from erev_api.schemas.users import LABEL_LENGTH, MEMO_LENGTH

EXTERNAL_ID_LENGTH: Final = 255


class RelatedPartyGroupIn(BaseModel):
    """``POST /related-party-groups``: a T-REF-18 group."""

    model_config = ConfigDict(extra="forbid")

    code: str = Field(max_length=CODE_LENGTH)
    name: str = Field(max_length=LABEL_LENGTH)
    description: str | None = Field(default=None, max_length=MEMO_LENGTH)


class RelatedPartyGroupUpdateIn(BaseModel):
    """``PATCH /related-party-groups/{id}``: the members sent replace the stored values."""

    model_config = ConfigDict(extra="forbid")

    code: str | None = Field(default=None, max_length=CODE_LENGTH)
    name: str | None = Field(default=None, max_length=LABEL_LENGTH)
    description: str | None = Field(default=None, max_length=MEMO_LENGTH)


class RelatedPartyGroupOut(BaseModel):
    """A T-REF-18 group with ``member_count`` (04 §16.14; L1-1-Q-38)."""

    id: uuid.UUID
    code: str
    name: str
    description: str | None
    member_count: int = Field(description="The customers of the group, active or not")
    created_at: datetime
    updated_at: datetime
    row_version: int


class CustomerIn(BaseModel):
    """``POST /customers``: a T-REF-19 customer."""

    model_config = ConfigDict(extra="forbid")

    code: str = Field(max_length=CODE_LENGTH, description="Tenant customer number")
    name: str = Field(max_length=LABEL_LENGTH)
    related_party_group_id: uuid.UUID | None = Field(
        default=None, description="At most one related-party group (REQ-REF-011)"
    )
    parent_customer_id: uuid.UUID | None = None
    credit_grade: str | None = Field(default=None, max_length=LABEL_LENGTH)
    segment: str | None = Field(default=None, max_length=LABEL_LENGTH)
    country_code: str | None = Field(default=None, description="ISO 3166-1 alpha-2, such as DE")
    source_system: SourceSystem | None = Field(
        default=None,
        description="E-38; by default API for an API client, otherwise MANUAL_UI",
    )
    external_id: str | None = Field(
        default=None,
        max_length=EXTERNAL_ID_LENGTH,
        description="The customer's id in its source system; unique per source system",
    )
    is_active: bool = True


class CustomerUpdateIn(BaseModel):
    """``PATCH /customers/{id}``: the members sent replace the stored values. ``source_system``
    and ``external_id`` are not members (L1-1-Q-40)."""

    model_config = ConfigDict(extra="forbid")

    code: str | None = Field(default=None, max_length=CODE_LENGTH)
    name: str | None = Field(default=None, max_length=LABEL_LENGTH)
    related_party_group_id: uuid.UUID | None = None
    parent_customer_id: uuid.UUID | None = None
    credit_grade: str | None = Field(default=None, max_length=LABEL_LENGTH)
    segment: str | None = Field(default=None, max_length=LABEL_LENGTH)
    country_code: str | None = None
    is_active: bool | None = None


class CustomerOut(BaseModel):
    """A T-REF-19 customer with its related-party group as API-S-Ref (L1-1-Q-38)."""

    id: uuid.UUID
    code: str
    name: str
    related_party_group_id: uuid.UUID | None
    related_party_group: RefOut | None
    parent_customer_id: uuid.UUID | None
    credit_grade: str | None
    segment: str | None
    country_code: str | None
    source_system: SourceSystem
    external_id: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime
    row_version: int
