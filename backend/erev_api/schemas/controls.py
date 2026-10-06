"""API-R-52 control evidence schemas (04 T-PLT-39, T-PLT-38; BUILD_SPEC SOP-1).

04 names no API-S schema for these resources, so the shapes carry the table columns without
``tenant_id``: one T-PLT-39 execution and one T-PLT-38 engine release with its gate results.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel

from erev_api.controls.evidence import RunRefType
from erev_api.enums import BookCode, ControlResult


class ControlExecutionOut(BaseModel):
    """One T-PLT-39 ``control_execution`` row."""

    id: uuid.UUID
    control_id: str
    run_ref_type: RunRefType
    run_ref_id: uuid.UUID
    entity_id: uuid.UUID | None
    book_code: BookCode | None
    period_id: uuid.UUID | None
    population_count: int
    exception_count: int
    result: ControlResult
    detail: dict[str, Any]
    exceptions_file_id: uuid.UUID | None
    engine_release_id: uuid.UUID
    executed_at: datetime


class ReleaseOut(BaseModel):
    """One T-PLT-38 ``engine_release`` row with its recorded gate results (REL-03, REL-04)."""

    id: uuid.UUID
    engine_version: str
    build_sha: str
    schema_revision: str
    control_impact_tags: list[str]
    gate_results: dict[str, dict[str, str | None]]
    deployed_at: datetime
