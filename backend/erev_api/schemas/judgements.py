"""API-R-33 judgement schemas (04 §15.3 API-R-33; T-CON-19; E-56, E-57; BUILD_SPEC CTR-7).

04 defines no API-S schema for judgements; [J] L4-1-Q-13: the create body is the T-CON-19 columns a
preparer enters (``book`` names ``book_code``), and ``JudgementOut`` is the T-CON-19 columns with
``created_by`` and ``reviewer`` as API-S-Actor.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from erev_api.enums import BookCode, JudgementStatus, JudgementTopic
from erev_api.schemas.common import ActorOut

__all__ = [
    "SUBJECT_TYPES",
    "JudgementCreateIn",
    "JudgementOut",
    "JudgementRefOut",
    "JudgementSubmitIn",
    "JudgementUpdateIn",
    "SubjectType",
]

Memo = Annotated[str, StringConstraints(min_length=1, max_length=4000)]
CodificationRef = Annotated[str, StringConstraints(min_length=1, max_length=100)]
# 04 T-CON-19 ``ck_judgement_record__subject_type``.
SubjectType = Literal[
    "contract",
    "obligation",
    "combination_group",
    "modification",
    "estimate_version",
    "product",
    "registry_version",
    "migration_batch",
]
SUBJECT_TYPES: tuple[str, ...] = (
    "contract",
    "obligation",
    "combination_group",
    "modification",
    "estimate_version",
    "product",
    "registry_version",
    "migration_batch",
)


class JudgementCreateIn(BaseModel):
    """``POST /judgements``: a DRAFT record (T-CON-19)."""

    model_config = ConfigDict(extra="forbid")

    topic: JudgementTopic
    subject_type: SubjectType
    subject_id: uuid.UUID
    contract_id: uuid.UUID | None = Field(
        default=None, description="For cockpit blockers; defaults to the subject's contract"
    )
    book: BookCode | None = Field(default=None, description="None applies to every book")
    conclusion: Memo
    rationale: Memo
    alternatives_considered: Memo | None = None
    codification_refs: list[CodificationRef] = Field(default_factory=list, max_length=50)
    questionnaire: dict[str, Any] | None = Field(
        default=None, description="Structured outcome members per the topic schema (T-CON-19)"
    )
    supersedes_id: uuid.UUID | None = None


class JudgementUpdateIn(BaseModel):
    """``PATCH /judgements/{id}``: the members sent replace the stored values of a DRAFT record."""

    model_config = ConfigDict(extra="forbid")

    conclusion: Memo | None = None
    rationale: Memo | None = None
    alternatives_considered: Memo | None = None
    codification_refs: list[CodificationRef] | None = Field(default=None, max_length=50)
    questionnaire: dict[str, Any] | None = None
    book: BookCode | None = None


class JudgementSubmitIn(BaseModel):
    """``POST /judgements/{id}/submit``."""

    model_config = ConfigDict(extra="forbid")

    comment: Memo | None = None


class JudgementRefOut(BaseModel):
    """Another judgement record, named by its id and its number."""

    id: uuid.UUID
    judgement_no: str


class JudgementOut(BaseModel):
    """A T-CON-19 record (L4-1-Q-13). ``overtaken_by`` (item STEP1-CITE-LATEST-1) is derived,
    not stored: for a REVIEWED record of a Step 1 topic, the record of the other Step 1 topic —
    of the same subject and book — that was reviewed after it; null otherwise. An overtaken
    record keeps its status and is not cited by an assessment any more (04 §16.3 (b))."""

    id: uuid.UUID
    judgement_no: str
    topic: JudgementTopic
    subject_type: str
    subject_id: uuid.UUID
    contract_id: uuid.UUID | None
    book: BookCode | None
    conclusion: str
    rationale: str
    alternatives_considered: str | None
    codification_refs: list[str]
    questionnaire: dict[str, Any] | None
    status: JudgementStatus
    reviewer: ActorOut | None
    reviewed_at: datetime | None
    approval_request_id: uuid.UUID | None
    content_sha256: str | None
    supersedes_id: uuid.UUID | None
    # Derived at the read; the default keeps the member optional for a reader of the schema, as
    # the members ``ModificationOut`` gained later are.
    overtaken_by: JudgementRefOut | None = None
    created_by: ActorOut
    created_at: datetime
    updated_at: datetime
