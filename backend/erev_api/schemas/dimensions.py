"""API-R-21 dimension schemas (04 §15.3 API-R-21, T-REF-16, T-REF-17, DB-12; SCREENS_B §9.5;
BUILD_SPEC RFD-6).

04 §16 defines no dimension schema. The members follow the T-REF-16 and T-REF-17 columns plus
``created_at``, ``updated_at`` and ``row_version`` (L1-1-Q-6). A dimension created through the API
is never built in, and a value's ``code`` does not change after creation (L1-1-Q-8).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Final

from pydantic import BaseModel, ConfigDict, Field

from erev_api.schemas.roles import CODE_LENGTH
from erev_api.schemas.users import LABEL_LENGTH

DIMENSION_CODE_LENGTH: Final = 32  # T-REF-16 ck_dimension_definition__code
POSITION_MAX: Final = 32767  # smallint


class DimensionIn(BaseModel):
    """``POST /dimensions``: a tenant-defined dimension (T-REF-16)."""

    model_config = ConfigDict(extra="forbid")

    code: str = Field(
        max_length=DIMENSION_CODE_LENGTH,
        description="2 to 32 lowercase letters, digits or underscores, starting with a letter",
    )
    name: str = Field(max_length=LABEL_LENGTH)
    position: int | None = Field(
        default=None,
        ge=1,
        le=POSITION_MAX,
        description="Display and export order; by default after the last dimension",
    )
    is_active: bool = True


class DimensionOut(BaseModel):
    """A T-REF-16 dimension (L1-1-Q-6)."""

    id: uuid.UUID
    code: str
    name: str
    is_builtin: bool
    position: int
    is_active: bool
    created_at: datetime
    updated_at: datetime
    row_version: int


class DimensionValueIn(BaseModel):
    """``POST /dimensions/{code}/values``: an allowed value (T-REF-17)."""

    model_config = ConfigDict(extra="forbid")

    code: str = Field(max_length=CODE_LENGTH)
    name: str = Field(max_length=LABEL_LENGTH)
    parent_value_id: uuid.UUID | None = Field(
        default=None, description="A value of the same dimension"
    )
    is_active: bool = True


class DimensionValueUpdateIn(BaseModel):
    """``PATCH /dimensions/{code}/values/{id}``: the members sent replace the stored values."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, max_length=LABEL_LENGTH)
    parent_value_id: uuid.UUID | None = Field(
        default=None, description="A value of the same dimension; null removes the parent"
    )
    is_active: bool | None = None


class DimensionValueOut(BaseModel):
    """A T-REF-17 value (L1-1-Q-6)."""

    id: uuid.UUID
    dimension_definition_id: uuid.UUID
    code: str
    name: str
    parent_value_id: uuid.UUID | None
    is_active: bool
    created_at: datetime
    updated_at: datetime
    row_version: int
