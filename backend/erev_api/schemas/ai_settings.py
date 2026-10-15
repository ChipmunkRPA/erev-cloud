"""Administrator-authored AI policy statements; category and scope are fixed by the route."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from erev_api.schemas.policies import MAX_VALUES, PolicyBasis


class AISettingsVersionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    values: dict[str, Any] = Field(max_length=MAX_VALUES)
    unset: list[str] = Field(default_factory=list, max_length=MAX_VALUES)
    basis: PolicyBasis | None = None


class AISettingsVersionUpdateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    values: dict[str, Any] | None = Field(default=None, max_length=MAX_VALUES)
    unset: list[str] | None = Field(default=None, max_length=MAX_VALUES)
    basis: PolicyBasis | None = None
