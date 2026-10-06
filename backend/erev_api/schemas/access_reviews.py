"""API-R-51 access review schemas (04 §15.3 API-R-51, T-PLT-40, T-PLT-41, E-107, E-108; SCREENS_B
§9.13 SF-14:access-reviews and SF-14:access-review data bindings and grid columns; BUILD_SPEC
PLF-28)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Final, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from erev_api.enums import AccessReviewDecision, AccessReviewStatus
from erev_api.schemas.common import ActorOut
from erev_api.schemas.users import MEMO_LENGTH

LABEL_LENGTH: Final = 400  # 04 TY-07 erev.label
MAX_REVIEWERS: Final = 100


class AccessReviewCreateIn(BaseModel):
    """``POST /access-reviews``: a DRAFT campaign and its reviewers."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(max_length=LABEL_LENGTH)
    as_of: AwareDatetime
    reviewer_membership_ids: list[uuid.UUID] = Field(max_length=MAX_REVIEWERS)


class AccessReviewDecideIn(BaseModel):
    """``POST /access-reviews/{id}/items/{item_id}/decide``: a revocation needs a comment of at
    least 10 characters."""

    model_config = ConfigDict(extra="forbid")

    decision: Literal["CERTIFIED", "REVOKE_REQUESTED"]
    comment: str | None = Field(default=None, max_length=MEMO_LENGTH)


class AccessReviewReviewerOut(BaseModel):
    """A reviewer membership with the person's name."""

    membership_id: uuid.UUID
    user_id: uuid.UUID
    display_name: str


class AccessReviewCountsOut(BaseModel):
    """The SF-14:access-review KPI strip: items by decision."""

    members: int
    pending: int
    certified: int
    revoke_requested: int
    revoked: int


class AccessReviewOut(BaseModel):
    """API-S-AccessReview: the T-PLT-40 row with its reviewers and item counts."""

    id: uuid.UUID
    name: str
    status: AccessReviewStatus
    as_of: datetime
    reviewers: list[AccessReviewReviewerOut]
    counts: AccessReviewCountsOut
    snapshot_file_id: uuid.UUID | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    created_by: ActorOut
    updated_at: datetime
    row_version: int


class AccessReviewRoleOut(BaseModel):
    """One ``roles_snapshot`` entry: a role in force when the campaign started."""

    role_code: str
    is_all_entities: bool
    entity_codes: list[str]
    granted_at: datetime
    granted_by: str | None


class AccessReviewItemOut(BaseModel):
    """API-S-AccessReviewItem: the T-PLT-41 row with the member's current name and the reviewer."""

    id: uuid.UUID
    access_review_campaign_id: uuid.UUID
    membership_id: uuid.UUID
    user_email_snapshot: str
    display_name: str
    roles_snapshot: list[AccessReviewRoleOut]
    last_login_at: datetime | None
    decision: AccessReviewDecision
    reviewer: ActorOut | None
    decided_at: datetime | None
    comment: str | None
    revocation_completed_at: datetime | None
    row_version: int
