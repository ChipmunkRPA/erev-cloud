"""API-R-13 Policies (registry): catalogue parameters, registry versions, the legacy-parity preset
and resolution (04 §15.3 API-R-13, §16.5 API-S-RegistryParameter, API-S-Policy,
API-S-PolicyResolution; BUILD_SPEC RFD-11).

``PolicyOut`` adds to API-S-Policy the SC-V column ``supersedes_version_id``, ``entity_id``,
``pending_approval_request_id``, ``created_at`` and ``updated_at`` (L3-1-Q-8). ``published_at`` and
``published_by`` are rows of API-S-Policy since 04 rev 1.139; ``published_by`` is API-S-Actor.
``unset``, the request member ``basis`` and ``diff_against_current[].change`` are rows since 04 rev
1.183 (the whole value set; supervisor ruling R-117 (b)).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Final, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from erev_api.enums import BookCode, ConfigStatus, RegistryCategory, RegistryScope
from erev_api.schemas.common import ActorOut
from erev_api.schemas.rule_sets import ImpactSimulationOut
from erev_api.schemas.users import MEMO_LENGTH

ENTITY_CODE_LENGTH: Final = 128  # TY-06
MAX_VALUES: Final = 500

type ResolutionLevel = Literal[
    "TENANT", "ENTITY", "BOOK", "PRODUCT", "CONTRACT", "OBLIGATION", "FRAMEWORK_DEFAULT"
]
type SourceType = Literal[
    "registry_version", "pob_template_version", "product", "policy_override", "framework_default"
]
type PolicyBasis = Literal["PREDECESSOR", "DEFAULTS"]
type PolicyChange = Literal["CHANGED", "ADDED", "RETURNED_TO_DEFAULT"]


class RegistryParameterOut(BaseModel):
    """API-S-RegistryParameter: one T-PLT-31 row."""

    code: str
    pol_id: str | None
    category: RegistryCategory
    value_schema: dict[str, Any]
    default_asc606: Any
    default_ifrs15: Any
    legacy_parity_value: Any
    is_forced_asc606: bool
    is_forced_ifrs15: bool
    allowed_levels: list[RegistryScope]
    pin: Literal["K", "P"]
    approval_code: str
    description: str
    source_ref: str
    section: str


class PolicyIn(BaseModel):
    """``POST /policies``: a DRAFT version of one category at one scope."""

    model_config = ConfigDict(extra="forbid")

    category: RegistryCategory
    scope: RegistryScope
    entity_code: str | None = Field(default=None, min_length=1, max_length=ENTITY_CODE_LENGTH)
    book: BookCode | None = None
    values: dict[str, Any] = Field(max_length=MAX_VALUES)
    unset: list[str] = Field(default_factory=list, max_length=MAX_VALUES)
    basis: PolicyBasis | None = None  # absent or null: PREDECESSOR
    effective_from: AwareDatetime | None = None


class PolicyUpdateIn(BaseModel):
    """``PATCH /policies/{id}`` with ``If-Match`` while the version is DRAFT or TESTED."""

    model_config = ConfigDict(extra="forbid")

    values: dict[str, Any] | None = Field(default=None, max_length=MAX_VALUES)
    unset: list[str] | None = Field(default=None, max_length=MAX_VALUES)
    basis: PolicyBasis | None = None
    effective_from: AwareDatetime | None = None


class PolicyTestIn(BaseModel):
    """``POST /policies/{id}/test``."""

    model_config = ConfigDict(extra="forbid")

    run_simulation: bool = True


class PolicyCommentIn(BaseModel):
    """``POST /policies/{id}/submit`` and ``/withdraw``."""

    model_config = ConfigDict(extra="forbid")

    comment: str | None = Field(default=None, max_length=MEMO_LENGTH)


class LegacyParityPresetIn(BaseModel):
    """``POST /policies/presets/legacy-parity``; ``book`` names the book of a BOOK version and
    defaults to ``ASC606`` there."""

    model_config = ConfigDict(extra="forbid")

    scope: RegistryScope
    entity_code: str | None = Field(default=None, min_length=1, max_length=ENTITY_CODE_LENGTH)
    book: BookCode | None = None


class PolicyDiffOut(BaseModel):
    code: str
    before: Any
    after: Any
    change: PolicyChange


class PolicyOut(BaseModel):
    """API-S-Policy: a T-PLT-32 registry version."""

    id: uuid.UUID
    category: RegistryCategory
    scope: RegistryScope
    entity_id: uuid.UUID | None
    entity_code: str | None
    book: BookCode | None
    values: dict[str, Any]
    unset: list[str]
    preset_code: str | None
    version_no: int
    status: ConfigStatus
    effective_from: datetime | None
    effective_to: datetime | None
    test_evidence: dict[str, Any] | None
    impact_simulation: ImpactSimulationOut | None
    approval_request_id: uuid.UUID | None
    pending_approval_request_id: uuid.UUID | None
    content_sha256: str | None
    published_at: datetime | None
    published_by: ActorOut | None
    supersedes_version_id: uuid.UUID | None
    diff_against_current: list[PolicyDiffOut]
    created_by: ActorOut
    created_at: datetime
    updated_at: datetime
    row_version: int


class PolicySourceOut(BaseModel):
    type: SourceType
    id: uuid.UUID | None


class PolicyChainLinkOut(BaseModel):
    level: ResolutionLevel
    found: bool
    source_id: uuid.UUID | None


class PolicyResolutionOut(BaseModel):
    """API-S-PolicyResolution."""

    key: str
    value: Any
    level: ResolutionLevel
    source: PolicySourceOut
    is_forced: bool
    known_at: datetime
    chain: list[PolicyChainLinkOut]
