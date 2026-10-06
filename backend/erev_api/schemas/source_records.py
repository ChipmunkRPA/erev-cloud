"""API-R-56 source record schemas (04 §15.3 API-R-56, §16.14 API-S-SourceRecord; T-SRC-01;
BUILD_SPEC DIN-2)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel

from erev_api.enums import SourceObjectType, SourceSystem

__all__ = ["ContractSourceOut", "SourceRecordApiClientOut", "SourceRecordOut"]


class ContractSourceOut(BaseModel):
    """One item of ``GET /contracts/{id}/sources`` (04 API-R-28, T-CON-02; SCREENS §6.6; BUILD_SPEC
    DIN-4, BS3-D-04): a link of the contract to a source record, with the record's identity and the
    import row it came from. [J] L5-1-Q-18: 04 §16 names no item schema; the members are the
    T-CON-02 columns, the T-SRC-01 identity and the T-IMP-03 sheet and row number."""

    id: uuid.UUID
    link_role: str
    contract_event_id: uuid.UUID | None
    source_record_id: uuid.UUID
    source_system: SourceSystem
    object_type: SourceObjectType
    external_id: str
    external_version: str
    received_at: datetime
    import_upload_id: uuid.UUID | None
    import_row_id: uuid.UUID | None
    sheet_name: str | None
    row_number: int | None
    created_at: datetime


class SourceRecordApiClientOut(BaseModel):
    """The API client that delivered a record: ``{id, name}``."""

    id: uuid.UUID
    name: str


class SourceRecordOut(BaseModel):
    """API-S-SourceRecord (``GET /source-records/{id}``); contact members read ``"[redacted]"``."""

    id: uuid.UUID
    source_system: SourceSystem
    object_type: SourceObjectType
    external_id: str
    external_version: str
    received_at: datetime
    api_client: SourceRecordApiClientOut | None
    idempotency_key: str | None
    request_id: str | None
    payload_sha256: str
    payload: dict[str, Any]
    import_upload_id: uuid.UUID | None
    import_row_id: uuid.UUID | None
    sync_run_id: uuid.UUID | None
