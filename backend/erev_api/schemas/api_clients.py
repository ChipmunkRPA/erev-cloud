"""API-R-02 OAuth token and API-R-08 API clients schemas (04 §15.3 API-R-02, API-R-08, T-PLT-15;
SCREENS_B §9.15; BUILD_SPEC PLF-25)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from erev_api.enums import ApiClientStatus
from erev_api.schemas.users import MEMO_LENGTH


class ApiClientIn(BaseModel):
    """``POST /api-clients``: a name, non-approval permission codes and the optional limits."""

    model_config = ConfigDict(extra="forbid")

    name: str
    scopes: list[str]
    is_all_entities: bool = True
    entity_codes: list[str] = Field(default_factory=list)
    expires_at: AwareDatetime | None = Field(default=None, description="Default: 365 days")
    rate_limit_per_minute: int | None = Field(default=None, description="Default: 600")


class ApiClientRevokeIn(BaseModel):
    """``POST /api-clients/{id}/revoke``: the reason, at least 10 characters (SB-R-05)."""

    model_config = ConfigDict(extra="forbid")

    reason: str | None = Field(default=None, max_length=MEMO_LENGTH)


class ApiClientOut(BaseModel):
    """API-S-ApiClient: the T-PLT-15 row without the secret hash and the stamps (SPEC-Q-190)."""

    id: uuid.UUID
    name: str
    client_id: str
    scopes: list[str]
    is_all_entities: bool
    entity_ids: list[uuid.UUID]
    status: ApiClientStatus
    expires_at: datetime
    rate_limit_per_minute: int
    last_used_at: datetime | None
    secret_rotated_at: datetime | None = Field(
        description="When the current secret was issued; null while none has been issued"
    )
    has_secret: bool = Field(
        description=(
            "Whether a secret was ever issued. False while the client waits for approval, after"
            " a rejection, and for an approved client whose first secret has not been issued:"
            " such a client cannot authenticate (REQ-PLT-033)"
        )
    )
    approval_request_id: uuid.UUID | None = Field(
        description=(
            "The approval request that grants the client its scopes, when the reader may read"
            " it (REQ-PLT-033; routing of ROLE_ASSIGNMENT)"
        )
    )
    created_at: datetime
    updated_at: datetime
    row_version: int


class ApiClientSecretOut(ApiClientOut):
    """The client with its secret, which no later response shows."""

    client_secret: str | None = Field(
        description=(
            "HTTP Basic password of POST /oauth/token; shown once (REQ-PLT-033). Null from"
            " POST /api-clients while the client waits for approval — rotate-secret issues the"
            " first secret after the approval — and in a replay with the same Idempotency-Key"
            " (D-80)"
        )
    )


class TokenOut(BaseModel):
    """``POST /oauth/token`` (RFC 6749 §5.1): a bearer token of 3,600 seconds."""

    access_token: str
    token_type: Literal["Bearer"]
    expires_in: int
    scope: str = Field(description="The granted permission codes, space-separated")
