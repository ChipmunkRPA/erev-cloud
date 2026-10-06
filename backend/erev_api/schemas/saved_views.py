"""API-R-16 Saved views schemas (04 §15.3 API-R-16, T-PLT-37; SCREENS SCR-IA-07, SCR-IA-08)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Final

from pydantic import BaseModel, ConfigDict, Field

from erev_api.schemas.users import LABEL_LENGTH

SCREEN_CODE_LENGTH: Final = 128
# SCR-IA-07: the screen id, optionally a sub-view and a grid name, e.g. SF-03:schedules#revenue.
SCREEN_CODE_PATTERN: Final = r"^SF-[0-9]{2}[A-Za-z0-9:#_-]*$"


class SavedViewIn(BaseModel):
    """``POST /saved-views``: a grid view or a favourite (SCR-IA-07, SCR-IA-08)."""

    model_config = ConfigDict(extra="forbid")

    screen_code: str = Field(max_length=SCREEN_CODE_LENGTH, pattern=SCREEN_CODE_PATTERN)
    name: str = Field(max_length=LABEL_LENGTH)
    config: dict[str, Any]
    is_shared: bool = False
    is_favourite: bool = False


class SavedViewUpdateIn(BaseModel):
    """``PATCH /saved-views/{id}``: any of the editable members."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, max_length=LABEL_LENGTH)
    config: dict[str, Any] | None = None
    is_shared: bool | None = None
    is_favourite: bool | None = None


class SavedViewOut(BaseModel):
    """API-S-SavedView: the T-PLT-37 row (SPEC-Q-186)."""

    id: uuid.UUID
    membership_id: uuid.UUID
    screen_code: str
    name: str
    config: dict[str, Any]
    is_shared: bool
    is_favourite: bool
    created_at: datetime
    updated_at: datetime
    row_version: int
