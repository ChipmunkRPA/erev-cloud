"""API-R-15 Webhooks schemas (04 §15.3 API-R-15, T-PLT-35, T-PLT-36; 05 NTR-10; BUILD_SPEC
PLF-24)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from erev_api.enums import WebhookDeliveryStatus


class WebhookEndpointIn(BaseModel):
    """``POST /webhook-endpoints``: an https URL and the event kinds it receives."""

    model_config = ConfigDict(extra="forbid")

    url: str
    description: str | None = None
    event_kinds: list[str]


class WebhookEndpointUpdateIn(BaseModel):
    """``PATCH /webhook-endpoints/{id}``: any of the editable members; ``is_active`` false stops
    deliveries."""

    model_config = ConfigDict(extra="forbid")

    url: str | None = None
    description: str | None = None
    event_kinds: list[str] | None = None
    is_active: bool | None = None


class WebhookEndpointOut(BaseModel):
    """API-S-WebhookEndpoint: the T-PLT-35 row without the sealed secret (SPEC-Q-189)."""

    id: uuid.UUID
    url: str
    description: str | None
    event_kinds: list[str]
    is_active: bool
    created_at: datetime
    updated_at: datetime
    row_version: int


class WebhookEndpointCreatedOut(WebhookEndpointOut):
    """The created endpoint with its signing secret, which no later response shows."""

    signing_secret: str | None = Field(
        description=(
            "HMAC-SHA256 key of the X-Erev-Signature header (05 NTR-11); shown once. A replay with"
            " the same Idempotency-Key carries null (D-80)"
        )
    )


class WebhookDeliveryOut(BaseModel):
    """API-S-WebhookDelivery: the T-PLT-36 row with ``created_at`` (SPEC-Q-189)."""

    id: uuid.UUID
    webhook_endpoint_id: uuid.UUID
    event_kind: str
    payload: dict[str, Any]
    payload_sha256: str
    status: WebhookDeliveryStatus
    attempt_count: int
    next_attempt_at: datetime | None
    abandon_at: datetime
    last_response_status: int | None
    last_error: str | None
    succeeded_at: datetime | None
    created_at: datetime
