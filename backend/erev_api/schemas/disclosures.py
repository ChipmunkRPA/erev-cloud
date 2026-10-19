"""API-R-42 immutable disclosure snapshot metadata and verified detail."""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel

from erev_api.enums import BookCode, DisclosureKind


class DisclosureSnapshotSummaryOut(BaseModel):
    id: UUID
    disclosure_kind: DisclosureKind
    entity_id: UUID
    entity_code: str
    book: BookCode
    period_id: UUID
    period_key: str
    period_lock_id: UUID | None
    report_run_id: UUID
    source: Literal["DRAFT", "LOCKED"]
    data_sha256: str
    created_at: datetime


class DisclosureSnapshotOut(DisclosureSnapshotSummaryOut):
    data: dict[str, Any]
