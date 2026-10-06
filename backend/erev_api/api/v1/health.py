"""API-R-53 Health, OpenAPI and metrics: liveness and readiness (05 OPR-23; DG-API-08; BS1-D-10).

``healthz`` touches nothing outside the process. ``readyz`` runs every check and reports each
failure by name: ``SELECT 1`` as ``erev_app`` behind the role guard, the database revision against
the code head, a probe object in the file store and the security-event HMAC key.
"""

from __future__ import annotations

import io
from collections.abc import Callable
from typing import Final

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text

from erev_api.api.deps import API_PREFIX, GuardedRoute, problem_responses
from erev_api.auth import security_events
from erev_api.db.migration_ops import code_head
from erev_api.db.session import identity_session
from erev_api.logging import get_logger, register_logger_fields
from erev_api.problems import request_id_for
from erev_api.schemas.health import CheckName, HealthOut, NotReadyOut, ReadyChecksOut, ReadyOut

TAG: Final = "API-R-53 Health, OpenAPI and metrics"
PROBE_KEY: Final = "health/readiness-probe"
PROBE_BYTES: Final = b"eRev readiness probe\n"
_LOGGER: Final = "erev_api.api.v1.health"

register_logger_fields(_LOGGER, ("check",))

router = APIRouter(prefix=API_PREFIX, tags=[TAG], route_class=GuardedRoute)


def _database(request: Request) -> None:
    with identity_session(request_id=request_id_for(request)) as session:
        session.execute(text("SELECT 1")).one()


def _migrations(request: Request) -> None:
    with identity_session(request_id=request_id_for(request)) as session:
        applied = session.execute(text("SELECT version_num FROM erev.alembic_version")).scalars()
        if list(applied) != [code_head()]:
            raise RuntimeError("the database revision differs from the code head")


def _files(request: Request) -> None:
    request.app.state.file_store.put(PROBE_KEY, io.BytesIO(PROBE_BYTES))


def _keys(request: Request) -> None:
    # 05 KEY-03: the key provider serves exactly the pinned current platform security key, and
    # the pin is not behind the chain head (a stale writer is never ready, DG-KRN-AUD-08).
    keyring = request.app.state.keyring
    keyring.verify_current_security_key()
    with identity_session(request_id=request_id_for(request)) as session:
        head = security_events.chain_head(session)
    security_events.assert_writer_admissible(
        head,
        writer_key_id=keyring.current_security_key_id(),
        writer_form=security_events.CANONICAL_VERSION,
    )


CHECKS: Final[tuple[tuple[CheckName, Callable[[Request], None]], ...]] = (
    ("database", _database),
    ("migrations", _migrations),
    ("files", _files),
    ("keys", _keys),
)


@router.get(
    "/healthz",
    operation_id="healthz_get",
    response_model=HealthOut,
    responses=problem_responses(),
)
def healthz() -> HealthOut:
    """Liveness: 200 while the process runs, without a database call."""
    return HealthOut(status="ok")


@router.get(
    "/readyz",
    operation_id="readyz_get",
    response_model=ReadyOut,
    responses={503: {"model": NotReadyOut, "description": "A readiness check failed"}},
)
def readyz(request: Request) -> ReadyOut | JSONResponse:
    """Readiness: 200 when every check passes, otherwise 503 naming the failed checks."""
    failed: list[CheckName] = []
    for name, check in CHECKS:
        try:
            check(request)
        except Exception as exc:
            failed.append(name)
            get_logger(_LOGGER).warning(
                "health.check_failed", check=name, error_code=type(exc).__name__
            )
    if failed:
        body = NotReadyOut(status="not_ready", failed=failed)
        return JSONResponse(body.model_dump(), status_code=503)
    return ReadyOut(
        status="ready",
        checks=ReadyChecksOut(database="ok", migrations="ok", files="ok", keys="ok"),
    )
