"""API-R-56 Source records: the raw payload behind imported and synchronised objects.

04 §15.3 API-R-56, §16.14 API-S-SourceRecord; T-SRC-01; SCREENS R-22; BUILD_SPEC DIN-2. The read
needs ``contract.read`` for all entities, or a contract the caller reads that names the record
(supervisor ruling R-28); otherwise 404. Contact members of the payload read ``"[redacted]"``
(REQ-SEC-007).
"""

from __future__ import annotations

import uuid
from typing import Annotated, Final

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from erev_api.api.deps import API_PREFIX, GuardedRoute, problem_responses
from erev_api.auth.dependencies import require
from erev_api.auth.principal import RequestContext
from erev_api.domain.integrations import normalise
from erev_api.schemas.source_records import SourceRecordOut

TAG: Final = "API-R-56 Source records"
READ: Final = "contract.read"
_READ_PROBLEMS: Final = ("unauthenticated", "session-expired", "forbidden", "not-found")

type ReadContext = Annotated[RequestContext, Depends(require(READ))]

router = APIRouter(prefix=API_PREFIX, tags=[TAG], route_class=GuardedRoute)


@router.get(
    "/source-records/{source_record_id}",
    operation_id="source_records_get",
    response_model=SourceRecordOut,
    responses=problem_responses(*_READ_PROBLEMS),
)
def source_records_get(source_record_id: uuid.UUID, ctx: ReadContext) -> SourceRecordOut:
    """One stored source record with its lineage; contact members redacted."""

    def found(session: Session) -> SourceRecordOut:
        return normalise.get_source_record(session, ctx.principal, source_record_id)

    return normalise.read(ctx, found)
