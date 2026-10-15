"""Administrator-authored AI policy statements; category and scope are fixed by the route."""

from datetime import datetime
from typing import Any, Literal

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


class AISettingsStatusOut(BaseModel):
    """Runtime availability and published settings, excluding credentials and provider clients."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)

    provider: Literal["fake", "anthropic"]
    enabled: bool
    registry_enabled: bool
    tenant_disabled_at: datetime | None
    platform_disabled: bool
    workspace_active: bool
    model: str
    monthly_token_budget: int
    send_contract_text: bool
    redact_contact_details: bool


class AISettingsValuesOut(BaseModel):
    """Effective and reset values for the fixed AI catalogue only."""

    model_config = ConfigDict(extra="forbid")

    values: dict[str, Any]
    defaults: dict[str, Any]
