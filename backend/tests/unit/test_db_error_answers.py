"""What the API answers when the database, or the pool in front of it, says "not now" in a way the
503 set does not cover (04 §15.2 and API-C-05 rev 1.144; dev-guide DG-KRN-ERR-02, DG-KRN-ERR-03 and
DG-KRN-IDEM-03 rev 1.127; supervisor rulings R-97 (5), (6) and R-103 (c)).

- SQLSTATE 40001, a serialization failure, is the 409 ``lock-conflict`` of the deadlock;
- SQLSTATE 57014, a statement PostgreSQL cancelled, is the named 503 ``statement-timeout`` with
  ``Retry-After`` - it answered 500 with ``http.unhandled_error``;
- the application's own connection pool that gives no connection within its wait is the slug-less
  503 with ``Retry-After`` - it answered 500 as well;
- a ``lock-conflict`` is not kept for its Idempotency-Key (the database-bound witness is
  ``tests/api/test_idempotency.py``).

The 503 set itself is pinned code by code in ``test_server_unavailable.py``.
"""

from __future__ import annotations

import io
import json
from typing import Any

import psycopg
import pytest
from erev_api.api import deps
from erev_api.db import errors as db_errors
from erev_api.problems import (
    LOCK_CONFLICT_DETAIL,
    MEDIA_TYPE,
    PROBLEMS,
    SERVER_UNAVAILABLE_RETRY_AFTER_SECONDS,
    from_db_error,
    install_handlers,
)
from fastapi import FastAPI
from psycopg import errors as pg
from sqlalchemy.exc import DBAPIError
from sqlalchemy.exc import TimeoutError as PoolTimeoutError
from sqlalchemy.pool import QueuePool
from support.http import call

REQUEST_ID = "r-13572468"
STATEMENT = "SELECT 1 FROM erev.probe"
SLOW = "canceling statement due to statement timeout"
# PRD ERR-66.
TIMEOUT_TITLE = "The request took too long"
TIMEOUT_DETAIL = (
    "The server stopped this request because it ran longer than allowed, so nothing was saved. "
    "Try again in a moment."
)


class RequestIdProbe:
    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        if scope["type"] == "http":
            scope.setdefault("state", {})["request_id"] = REQUEST_ID
        await self.app(scope, receive, send)


def _raised(code: str, message: str = "probe") -> DBAPIError:
    """What SQLAlchemy raises for the driver's error of ``code``."""
    orig = pg.lookup(code)(message)
    assert orig.sqlstate == code
    wrapped = DBAPIError.instance(STATEMENT, None, orig, psycopg.Error)
    assert isinstance(wrapped, DBAPIError)
    return wrapped


class _Connection:
    """The least a pool asks of a DBAPI connection."""

    def rollback(self) -> None:
        return None

    def close(self) -> None:
        return None


def _pool_timeout() -> PoolTimeoutError:
    """The error SQLAlchemy's own pool raises: one connection, held, and a second checkout that
    waits out the pool's timeout. No database is involved - which is the point of the rule."""
    pool = QueuePool(_Connection, pool_size=1, max_overflow=0, timeout=0.01)
    held = pool.connect()
    try:
        with pytest.raises(PoolTimeoutError) as caught:
            pool.connect()
    finally:
        held.close()
        pool.dispose()
    return caught.value


def _app() -> FastAPI:
    app = FastAPI()
    install_handlers(app)
    app.add_middleware(RequestIdProbe)

    @app.post("/probe/serialization")
    def serialization() -> None:
        raise _raised("40001", "could not serialize access due to concurrent update")

    @app.post("/probe/slow")
    def slow() -> None:
        raise _raised("57014", SLOW)

    @app.post("/probe/slow-mapped")
    def slow_mapped() -> None:
        # As the commit's mapper and the other `except DBAPIError` mappers raise it.
        error = _raised("57014", SLOW)
        problem = from_db_error(error)
        assert problem is not None
        raise problem from error

    @app.post("/probe/pool")
    def pool() -> None:
        raise _pool_timeout()

    @app.get("/probe/pool-inside")
    def pool_inside() -> None:
        try:
            raise _pool_timeout()
        except PoolTimeoutError as error:
            raise RuntimeError("the coverage guard could not read") from error

    return app


def _events(log_stream: io.StringIO) -> list[dict[str, Any]]:
    return [json.loads(line) for line in log_stream.getvalue().splitlines() if line.strip()]


def test_a_serialization_failure_is_the_lock_conflict_of_the_deadlock() -> None:
    lost = from_db_error(_raised("40001"))
    deadlock = from_db_error(_raised("40P01"))
    assert lost is not None and deadlock is not None
    assert (lost.slug, lost.status, lost.detail) == ("lock-conflict", 409, LOCK_CONFLICT_DETAIL)
    assert (lost.detail, lost.errors, lost.headers) == (deadlock.detail, deadlock.errors, {})
    response = call(_app(), "POST", "/probe/serialization")
    assert response.status_code == 409, response.text
    assert response.json()["type"] == "https://erev.dev/problems/lock-conflict"
    assert "retry-after" not in response.headers


def test_a_cancelled_statement_is_the_named_503() -> None:
    spec = PROBLEMS["statement-timeout"]
    assert (spec.status, spec.title, spec.db_codes) == (503, TIMEOUT_TITLE, frozenset())
    problem = from_db_error(_raised("57014", SLOW))
    assert problem is not None
    assert (problem.slug, problem.status, problem.detail) == (
        "statement-timeout",
        503,
        TIMEOUT_DETAIL,
    )
    assert problem.headers == {"Retry-After": "30"}
    assert problem.errors == () and problem.code is None
    # Not the slug-less 503: the set of `server_unavailable` is unchanged, and 57014 is outside it.
    assert not db_errors.server_unavailable(_raised("57014"))


@pytest.mark.parametrize("path", ["/probe/slow", "/probe/slow-mapped"])
def test_the_api_answers_a_cancelled_statement_503_with_retry_after(
    path: str, log_stream: io.StringIO
) -> None:
    response = call(_app(), "POST", path)
    assert response.status_code == 503, response.text
    assert response.headers["retry-after"] == "30"
    assert response.headers["content-type"] == MEDIA_TYPE
    assert response.json() == {
        "type": "https://erev.dev/problems/statement-timeout",
        "title": TIMEOUT_TITLE,
        "status": 503,
        "detail": TIMEOUT_DETAIL,
        "instance": f"urn:erev:request:{REQUEST_ID}",
        "code": None,
        "errors": [],
    }
    (event,) = _events(log_stream)
    assert (event["event"], event["level"]) == ("http.statement_timeout", "warning")
    assert (event["request_id"], event["sqlstate"]) == (REQUEST_ID, "57014")
    assert event["driver_error_class"] == "psycopg.errors.QueryCanceled"
    # An operational condition, not a defect: no stack trace, and no driver message.
    assert "exception" not in event
    assert SLOW not in log_stream.getvalue()


def test_a_pool_timeout_is_found_as_itself_and_as_a_cause() -> None:
    timeout = _pool_timeout()
    assert db_errors.pool_timeout_in(timeout)
    try:
        try:
            raise timeout
        except PoolTimeoutError as error:
            raise RuntimeError("the datasets could not be read") from error
    except RuntimeError as caused:
        assert db_errors.pool_timeout_in(caused)
    # The builtin of the same name, a database error and an ordinary error are not one.
    assert not db_errors.pool_timeout_in(TimeoutError("a socket timed out"))
    assert not db_errors.pool_timeout_in(_raised("53200"))
    assert not db_errors.pool_timeout_in(RuntimeError("no pool at all"))
    # And it is no database error: no statement reached a server.
    assert db_errors.database_error_in(timeout) is None


@pytest.mark.parametrize(
    ("method", "path", "error_class"),
    [
        ("POST", "/probe/pool", "sqlalchemy.exc.TimeoutError"),
        ("GET", "/probe/pool-inside", "RuntimeError"),
    ],
)
def test_the_api_answers_a_pool_timeout_503_with_retry_after(
    method: str, path: str, error_class: str, log_stream: io.StringIO
) -> None:
    response = call(_app(), method, path)
    assert response.status_code == 503, response.text
    assert response.headers["retry-after"] == str(SERVER_UNAVAILABLE_RETRY_AFTER_SECONDS) == "5"
    assert response.headers["content-type"] == MEDIA_TYPE
    # The server's state, not a conflict with another command: never 409, and no slug.
    assert response.json() == {
        "type": "about:blank",
        "title": "Service Unavailable",
        "status": 503,
        "instance": f"urn:erev:request:{REQUEST_ID}",
        "code": None,
        "errors": [],
    }
    (event,) = _events(log_stream)
    assert (event["event"], event["level"]) == ("http.server_unavailable", "warning")
    assert (event["request_id"], event["error_class"]) == (REQUEST_ID, error_class)
    assert (event["driver_error_class"], event["sqlstate"]) == ("sqlalchemy.exc.TimeoutError", None)
    assert "exception" not in event


def test_two_409s_are_never_kept_and_the_rule_is_by_slug() -> None:
    """DG-KRN-IDEM-03 rev 1.127 (IDEM-LOCK-CONFLICT-1): ``lock-conflict`` and ``period-closed``
    are the refusals whose rule is "submit again". Their status, 409, is kept for every other
    slug, so the rule is a list by slug; the two 503 answers above are never kept because no 5xx
    is."""
    assert deps.UNSTORED_SLUGS == frozenset({"lock-conflict", "period-closed"})
    assert {PROBLEMS[slug].status for slug in deps.UNSTORED_SLUGS} == {409}
    assert 409 not in deps.UNSTORED_STATUSES
    assert PROBLEMS["statement-timeout"].status >= 500
