"""API-R-17 entity and book schemas (04 §15.3 API-R-17, T-REF-01 to T-REF-03, E-02; SCREENS_B
SF-15:entities; BUILD_SPEC RFD-2).

04 §16 defines no entity or book schema. The members follow the table columns plus ``created_at``,
``updated_at`` and ``row_version``, as the calendar and account schemas do; an entity also lists
the books it keeps with their first period keys (L1-1-Q-13). ``code`` and ``calendar_id`` do not
change after creation.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field

from erev_api.enums import BookCode
from erev_api.schemas.roles import CODE_LENGTH
from erev_api.schemas.users import LABEL_LENGTH

PostingTarget = Literal["GL_PRIMARY", "GL_SECONDARY", "NONE"]
TIME_ZONE_LENGTH: Final = 64
PERIOD_KEY_LENGTH: Final = 16


class EntityIn(BaseModel):
    """``POST /entities``: a T-REF-01 legal entity; it keeps the primary book from creation."""

    model_config = ConfigDict(extra="forbid")

    code: str = Field(max_length=CODE_LENGTH)
    name: str = Field(max_length=LABEL_LENGTH)
    functional_currency: str = Field(max_length=3, description="ISO 4217 code")
    time_zone: str = Field(max_length=TIME_ZONE_LENGTH, description="IANA time zone")
    calendar_id: uuid.UUID
    parent_entity_id: uuid.UUID | None = Field(default=None, description="Reporting hierarchy only")
    country_code: str | None = Field(default=None, max_length=2, description="ISO 3166-1 alpha-2")
    tax_id: str | None = Field(default=None, max_length=LABEL_LENGTH)
    is_active: bool = True
    first_period_key: str | None = Field(
        default=None,
        max_length=PERIOD_KEY_LENGTH,
        description="First period of the primary book; by default the calendar's earliest period",
    )


class EntityUpdateIn(BaseModel):
    """``PATCH /entities/{id}``: the members sent replace the stored values."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, max_length=LABEL_LENGTH)
    functional_currency: str | None = Field(default=None, max_length=3)
    time_zone: str | None = Field(default=None, max_length=TIME_ZONE_LENGTH)
    parent_entity_id: uuid.UUID | None = None
    country_code: str | None = Field(default=None, max_length=2)
    tax_id: str | None = Field(default=None, max_length=LABEL_LENGTH)
    is_active: bool | None = None


class EntityBookIn(BaseModel):
    """``PUT /entities/{id}/books/{code}``."""

    model_config = ConfigDict(extra="forbid")

    is_enabled: bool
    first_period_key: str | None = Field(
        default=None,
        max_length=PERIOD_KEY_LENGTH,
        description="First period of a newly kept book; by default the calendar's earliest period",
    )


class EntityBookOut(BaseModel):
    """A T-REF-03 row: a book the entity keeps."""

    id: uuid.UUID
    entity_id: uuid.UUID
    book_code: BookCode
    first_period_id: uuid.UUID
    first_period_key: str
    is_enabled: bool
    created_at: datetime
    updated_at: datetime
    row_version: int


class EntityOut(BaseModel):
    """A T-REF-01 entity with the books it keeps (L1-1-Q-13)."""

    id: uuid.UUID
    code: str
    name: str
    functional_currency: str
    time_zone: str
    calendar_id: uuid.UUID
    parent_entity_id: uuid.UUID | None
    country_code: str | None
    tax_id: str | None
    is_active: bool
    books: list[EntityBookOut]
    created_at: datetime
    updated_at: datetime
    row_version: int


class BookOut(BaseModel):
    """A T-REF-02 book."""

    id: uuid.UUID
    code: BookCode
    name: str
    is_primary: bool
    is_enabled: bool
    posting_target: PostingTarget
    created_at: datetime
    updated_at: datetime
    row_version: int


class BookUpdateIn(BaseModel):
    """``PATCH /books/{code}``: the members sent replace the stored values; ``code`` and
    ``is_primary`` do not change."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, max_length=LABEL_LENGTH)
    is_enabled: bool | None = None
    posting_target: PostingTarget | None = None
