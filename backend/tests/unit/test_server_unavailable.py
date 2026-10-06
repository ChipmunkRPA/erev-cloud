"""A database that could not do it at that moment answers 503, never 500 (04 API-C-05 rev 1.114;
PRD CPY-07 rev 1.43; dev-guide DG-KRN-ERR-03 rev 1.97; supervisor ruling R-53 (5)).

Measured in the deployment lane: SQLSTATE 53200 — out of shared memory, the lock table of 05 §2.7
— surfaced as ``http.unhandled_error`` 500. The set of codes is exact and is pinned here code by
code; the database-bound witness is ``tests/domain/contracts/test_server_unavailable_compute.py``.
"""

from __future__ import annotations

import io
import json
from typing import Any

import psycopg
import pytest
from erev_api.db import errors as db_errors
from erev_api.problems import (
    MEDIA_TYPE,
    SERVER_UNAVAILABLE_RETRY_AFTER_SECONDS,
    from_db_error,
    install_handlers,
)
from fastapi import FastAPI
from psycopg import errors as pg
from sqlalchemy.exc import DBAPIError, OperationalError
from support.http import call

REQUEST_ID = "r-87654321"
STATEMENT = "SELECT 1 FROM erev.probe"
# 04 API-C-05 rev 1.114, in the order the row names them.
UNAVAILABLE = (
    "53000",
    "53100",
    "53200",
    "53300",
    "53400",
    "08000",
    "08001",
    "08003",
    "08004",
    "08006",
    "57P01",
    "57P02",
    "57P03",
)
# Named by the row as deliberately outside the set, and neighbours that must stay where they are.
ELSEWHERE = (
    "08007",  # the outcome of a commit is unknown
    "08P01",  # a protocol violation is a defect
    "57014",  # a cancelled statement (the platform's own statement_timeout included)
    "57P04",
    "57P05",
    "58030",
    "25P03",
    "40001",
    "40P01",  # 409 lock-conflict
    "55P03",  # 409 lock-conflict, rule LOCK_TIMEOUT
    "42501",
    "23505",
    "P0001",
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


def _without_sqlstate(orig: Exception, *, invalidated: bool = False) -> DBAPIError:
    wrapped = DBAPIError.instance(
        STATEMENT, None, orig, psycopg.Error, connection_invalidated=invalidated
    )
    assert isinstance(wrapped, DBAPIError)
    assert db_errors.sqlstate(wrapped) is None
    return wrapped


@pytest.mark.parametrize("code", UNAVAILABLE)
def test_the_server_could_not_do_it_now(code: str) -> None:
    error = _raised(code)
    assert db_errors.server_unavailable(error), code
    # No catalogue slug: the command's idempotency attempt is abandoned, not stored
    # (DG-KRN-IDEM-03), and every `except DBAPIError` mapper re-raises.
    assert from_db_error(error) is None, code


@pytest.mark.parametrize("code", ELSEWHERE)
def test_every_other_code_stays_where_it_was(code: str) -> None:
    assert not db_errors.server_unavailable(_raised(code)), code


def test_the_set_is_class_53_and_eight_named_states() -> None:
    assert db_errors.SERVER_UNAVAILABLE_CLASS == "53"
    assert db_errors.SERVER_UNAVAILABLE_STATES == frozenset(UNAVAILABLE[5:])
    assert all(code.startswith("53") for code in UNAVAILABLE[:5])


def test_a_connection_lost_or_never_opened_has_no_sqlstate() -> None:
    """The driver reports no SQLSTATE when nothing came from a server: a refused or dropped
    connection is its ``OperationalError``; SQLAlchemy marks a connection it found dead."""
    refused = _without_sqlstate(psycopg.OperationalError("connection refused"))
    assert isinstance(refused, OperationalError)
    assert db_errors.server_unavailable(refused)
    dropped = _without_sqlstate(psycopg.InterfaceError("the connection is lost"), invalidated=True)
    assert db_errors.server_unavailable(dropped)
    # A driver error without a SQLSTATE that is neither is a defect, as before.
    misuse = _without_sqlstate(psycopg.ProgrammingError("the last operation didn't produce rows"))
    assert not db_errors.server_unavailable(misuse)
    # A SQLSTATE decides when there is one, even on a connection marked dead.
    idle = pg.lookup("57P05")("terminating connection due to idle-session timeout")
    marked = DBAPIError.instance(STATEMENT, None, idle, psycopg.Error, connection_invalidated=True)
    assert isinstance(marked, DBAPIError) and not db_errors.server_unavailable(marked)


def test_the_error_is_found_through_cause_and_context() -> None:
    lock_table = _raised("53200", "out of shared memory")
    assert db_errors.server_unavailable_in(lock_table)
    try:
        try:
            raise lock_table
        except DBAPIError as error:
            raise RuntimeError("the bundle could not be built") from error
    except RuntimeError as caused:
        assert db_errors.database_error_in(caused) is lock_table
        assert db_errors.server_unavailable_in(caused)
    try:
        try:
            raise lock_table
        except DBAPIError:
            raise KeyError("while handling it")  # noqa: B904 - the implicit context is the point
    except KeyError as contextual:
        assert db_errors.server_unavailable_in(contextual)
    assert not db_errors.server_unavailable_in(RuntimeError("no database error at all"))
    assert not db_errors.server_unavailable_in(_raised("40P01"))
    assert db_errors.database_error_in(ValueError("none")) is None


def _app() -> FastAPI:
    app = FastAPI()
    install_handlers(app)
    app.add_middleware(RequestIdProbe)

    @app.post("/probe/lock-table")
    def lock_table() -> None:
        raise _raised("53200", "out of shared memory")

    @app.get("/probe/starting")
    def starting() -> None:
        try:
            raise _raised("57P03", "the database system is starting up")
        except DBAPIError as error:
            raise RuntimeError("the period list could not be read") from error

    @app.post("/probe/refused")
    def refused() -> None:
        raise _without_sqlstate(psycopg.OperationalError("connection refused"))

    @app.post("/probe/commit-unknown")
    def commit_unknown() -> None:
        raise _raised("08007", "transaction resolution unknown")

    return app


@pytest.mark.parametrize(
    ("method", "path", "sqlstate", "driver"),
    [
        ("POST", "/probe/lock-table", "53200", "psycopg.errors.OutOfMemory"),
        ("GET", "/probe/starting", "57P03", "psycopg.errors.CannotConnectNow"),
        ("POST", "/probe/refused", None, "psycopg.OperationalError"),
    ],
)
def test_the_api_answers_503_with_retry_after(
    method: str, path: str, sqlstate: str | None, driver: str, log_stream: io.StringIO
) -> None:
    response = call(_app(), method, path)
    assert response.status_code == 503, response.text
    assert response.headers["retry-after"] == str(SERVER_UNAVAILABLE_RETRY_AFTER_SECONDS) == "5"
    assert response.headers["content-type"] == MEDIA_TYPE
    assert response.json() == {
        "type": "about:blank",
        "title": "Service Unavailable",
        "status": 503,
        "instance": f"urn:erev:request:{REQUEST_ID}",
        "code": None,
        "errors": [],
    }
    lines = [json.loads(line) for line in log_stream.getvalue().splitlines() if line.strip()]
    assert [line["event"] for line in lines] == ["http.server_unavailable"]
    (event,) = lines
    assert (event["level"], event["request_id"]) == ("warning", REQUEST_ID)
    assert (event["sqlstate"], event["driver_error_class"]) == (sqlstate, driver)
    # An operational condition, not a defect: no stack trace, and no driver message.
    assert "exception" not in event
    assert "out of shared memory" not in log_stream.getvalue()


def test_an_unknown_commit_outcome_is_still_a_500(log_stream: io.StringIO) -> None:
    response = call(_app(), "POST", "/probe/commit-unknown")
    assert response.status_code == 500
    assert "retry-after" not in response.headers
    assert response.json()["title"] == "Internal Server Error"
    lines = [json.loads(line) for line in log_stream.getvalue().splitlines() if line.strip()]
    assert [line["event"] for line in lines] == ["http.unhandled_error"]
    assert lines[0]["sqlstate"] == "08007"
