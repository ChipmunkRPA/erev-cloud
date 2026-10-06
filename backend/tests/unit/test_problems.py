"""Problem details KRN-ERR (dev-guide §5.8; 04 API-C-05, §15.2; BUILD_SPEC FND-9)."""

from __future__ import annotations

import io
import json
from typing import Any

import psycopg
import pytest
from erev_api.money import MoneyIn
from erev_api.problems import (
    LOCK_CONFLICT_DETAIL,
    LOCK_TIMEOUT_DETAIL,
    MEDIA_TYPE,
    PROBLEMS,
    RULE_LOCK_TIMEOUT,
    Problem,
    ProblemError,
    from_db_error,
    install_handlers,
    problem,
)
from fastapi import FastAPI
from sqlalchemy.exc import DBAPIError
from support.http import call

REQUEST_ID = "r-12345678"
MARKER = "FND9-PROBE-MARKER"


class RequestIdProbe:
    """Stands in for the request-id middleware of FND-10."""

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        if scope["type"] == "http":
            scope.setdefault("state", {})["request_id"] = REQUEST_ID
        await self.app(scope, receive, send)


FROZEN_MESSAGE = (
    "EREV-REF-001: functional_currency and time_zone of entity AVM-US of erev.legal_entity are "
    "frozen: a subledger line of the entity exists"
)

# DB-19 tg_app_user__erasure_guard (04 §14.1; revision 0073): the message form the trigger raises.
GUARD_MESSAGE = (
    "EREV-PRV-001: email and external_id of erev.app_user row "
    "0f7a2f6e-2f4e-4a1c-9d0e-7c3f8a1b2c3d change only in the erased form of user.anonymise"
)


def db_error(orig: Exception) -> DBAPIError:
    return DBAPIError("INSERT INTO erev.probe DEFAULT VALUES", None, orig)


def privilege_error() -> DBAPIError:
    return db_error(psycopg.errors.InsufficientPrivilege("new row violates row-level security"))


def build_app() -> FastAPI:
    app = FastAPI()
    install_handlers(app)
    app.add_middleware(RequestIdProbe)

    @app.get("/probe/db-privilege")
    def read_privilege() -> None:
        raise privilege_error()

    @app.post("/probe/db-privilege")
    def write_privilege() -> None:
        raise privilege_error()

    @app.post("/probe/db-immutable")
    def write_immutable() -> None:
        raise db_error(psycopg.errors.RaiseException("EREV-IMM-001 row is append-only"))

    @app.post("/probe/db-lock-timeout")
    def write_lock_timeout() -> None:
        raise db_error(psycopg.errors.LockNotAvailable("canceling statement due to lock timeout"))

    @app.patch("/probe/db-frozen-entity")
    def patch_frozen_entity() -> None:
        raise db_error(psycopg.errors.RaiseException(FROZEN_MESSAGE))

    @app.post("/probe/db-erasure-guard")
    def post_erasure_guard() -> None:
        raise db_error(psycopg.errors.RaiseException(GUARD_MESSAGE))

    @app.post("/probe/money")
    def post_money(body: MoneyIn) -> dict[str, str]:
        return {"currency": body.currency}

    @app.get("/probe/problem")
    def read_problem() -> None:
        raise problem("period-closed", "Sep 2026 is closed for AVM-US in book ASC606.")

    @app.post("/probe/boom")
    def boom() -> None:
        raise RuntimeError(f"probe failure {MARKER}")

    return app


def test_krn_err_01_problem_json_shape() -> None:
    body = Problem("forbidden", "You do not have permission to lock periods.").to_json(
        instance="urn:erev:request:r-12345678"
    )
    assert body == {
        "type": "https://erev.dev/problems/forbidden",
        "title": "Permission denied",
        "status": 403,
        "detail": "You do not have permission to lock periods.",
        "instance": "urn:erev:request:r-12345678",
        "code": None,
        "errors": [],
    }


def test_krn_err_01_unknown_slug_raises() -> None:
    with pytest.raises(KeyError):
        Problem("unknown-slug")


def test_problem_response_media_type_errors_and_extensions() -> None:
    response = call(build_app(), "GET", "/probe/problem")
    assert response.status_code == 409
    assert response.headers["content-type"] == MEDIA_TYPE
    assert response.json()["instance"] == f"urn:erev:request:{REQUEST_ID}"
    assert response.json()["detail"] == "Sep 2026 is closed for AVM-US in book ASC606."
    duplicate = Problem(
        "duplicate-import",
        errors=[ProblemError(sheet="SSP", row=2, rule_id="IMPORT_FILE_DUPLICATE")],
        import_no="IMP-000123",
    ).to_json(instance="urn:erev:request:r-1")
    assert duplicate["errors"] == [
        {"field": None, "sheet": "SSP", "row": 2, "rule_id": "IMPORT_FILE_DUPLICATE", "message": ""}
    ]
    assert duplicate["import_no"] == "IMP-000123"
    with pytest.raises(ValueError):
        Problem("forbidden", status=200)


def test_krn_err_02_db_error_mapping() -> None:
    immutable = from_db_error(
        db_error(psycopg.errors.RaiseException("EREV-IMM-001 row is append-only"))
    )
    assert immutable is not None
    assert (immutable.slug, immutable.status, immutable.code) == (
        "immutable-record",
        409,
        "EREV-IMM-001",
    )
    decided = from_db_error(
        db_error(psycopg.errors.RaiseException("EREV-APR-002 approver decided an earlier step"))
    )
    assert decided is not None
    assert (decided.slug, decided.status, decided.code) == (
        "approver-already-decided",
        409,
        "EREV-APR-002",
    )
    read = from_db_error(privilege_error(), method="GET")
    write = from_db_error(privilege_error(), method="POST")
    assert read is not None and (read.slug, read.status) == ("not-found", 404)
    assert write is not None and (write.slug, write.status) == ("forbidden", 403)
    assert from_db_error(db_error(psycopg.errors.RaiseException("no catalogue code"))) is None
    assert from_db_error(db_error(psycopg.errors.UniqueViolation("duplicate key"))) is None

    app = build_app()
    got = call(app, "GET", "/probe/db-privilege")
    assert got.status_code == 404
    assert got.json()["type"] == "https://erev.dev/problems/not-found"
    posted = call(app, "POST", "/probe/db-privilege")
    assert posted.status_code == 403
    assert posted.json()["type"] == "https://erev.dev/problems/forbidden"
    appended = call(app, "POST", "/probe/db-immutable")
    assert appended.status_code == 409
    assert appended.json()["code"] == "EREV-IMM-001"
    assert appended.json()["title"] == PROBLEMS["immutable-record"].title


def test_krn_err_02_deadlock_is_a_named_retryable_refusal() -> None:
    """DG-KRN-DB-08 / DG-KRN-ERR-02 (D-98 candidate 101c): SQLSTATE 40P01 is 409 ``lock-conflict``
    — the transaction rolled back, nothing was saved, the client may resubmit; never a 500."""
    mapped = from_db_error(db_error(psycopg.errors.DeadlockDetected("deadlock detected")))
    assert mapped is not None
    assert (mapped.slug, mapped.status, mapped.title) == (
        "lock-conflict",
        409,
        "Another change was in progress",
    )
    assert mapped.detail is not None and "Resubmit the request." in mapped.detail
    assert PROBLEMS["lock-conflict"].db_codes == frozenset()


def test_krn_err_02_validation_error_field_path() -> None:
    response = call(build_app(), "POST", "/probe/money", json={"currency": "USD"})
    assert response.status_code == 422
    assert response.headers["content-type"] == MEDIA_TYPE
    body = response.json()
    assert body["type"] == "https://erev.dev/problems/validation-failed"
    assert body["title"] == "Check the highlighted fields"
    assert body["detail"] == "1 field needs attention."
    assert body["errors"][0]["field"] == "amount"
    assert body["instance"] == f"urn:erev:request:{REQUEST_ID}"


def test_krn_err_03_unhandled_error_is_about_blank(log_stream: io.StringIO) -> None:
    response = call(build_app(), "POST", "/probe/boom")
    assert response.status_code == 500
    assert response.headers["content-type"] == MEDIA_TYPE
    body = response.json()
    assert body["type"] == "about:blank"
    assert body["title"] == "Internal Server Error"
    assert "detail" not in body
    assert body["instance"] == f"urn:erev:request:{REQUEST_ID}"
    assert MARKER not in response.text and "Traceback" not in response.text

    lines = [json.loads(line) for line in log_stream.getvalue().splitlines() if line.strip()]
    (event,) = [line for line in lines if line["event"] == "http.unhandled_error"]
    assert event["request_id"] == REQUEST_ID
    trace = str(event["exception"])
    assert "Traceback" in trace and MARKER in trace
    assert all(MARKER not in json.dumps(line) for line in lines if line is not event)


def test_unknown_route_is_not_found_problem() -> None:
    response = call(build_app(), "GET", "/probe/absent")
    assert response.status_code == 404
    assert response.json()["type"] == "https://erev.dev/problems/not-found"
    not_allowed = call(build_app(), "DELETE", "/probe/problem")
    assert not_allowed.status_code == 405
    assert not_allowed.json()["type"] == "about:blank"
    assert not_allowed.json()["title"] == "Method Not Allowed"


def test_krn_err_02_lock_timeout_is_the_named_lock_conflict() -> None:
    """ERR-MAP-1 (D-98 candidate 141; 04 §15.2 rev 1.71; DG-KRN-ERR-02 rev 1.61): SQLSTATE 55P03 —
    a lock wait beyond the platform's ``lock_timeout`` — is the SAME 409 ``lock-conflict`` as a
    deadlock, with rule ``LOCK_TIMEOUT`` and its own detail; never ``http.unhandled_error`` 500
    (integrated batch #6 on 9e7d1031 measured two approvals answering 500 after 10.1 s). No
    automatic retry is claimed. Fail-first: the previous mapping returned None for 55P03."""
    mapped = from_db_error(
        db_error(psycopg.errors.LockNotAvailable("canceling statement due to lock timeout"))
    )
    assert mapped is not None
    assert (mapped.slug, mapped.status, mapped.title) == (
        "lock-conflict",
        409,
        "Another change was in progress",
    )
    assert mapped.detail == LOCK_TIMEOUT_DETAIL and mapped.detail != LOCK_CONFLICT_DETAIL
    assert [(e.rule_id, e.message) for e in mapped.errors] == [
        (RULE_LOCK_TIMEOUT, LOCK_TIMEOUT_DETAIL)
    ]
    assert PROBLEMS["lock-conflict"].db_codes == frozenset()  # a SQLSTATE, not a §14.1 code
    timed_out = call(build_app(), "POST", "/probe/db-lock-timeout")
    assert timed_out.status_code == 409
    body = timed_out.json()
    assert body["type"] == "https://erev.dev/problems/lock-conflict" and body["code"] is None
    assert [e["rule_id"] for e in body["errors"]] == [RULE_LOCK_TIMEOUT]


def test_krn_err_02_frozen_entity_is_an_immutable_record_by_name() -> None:
    """ERR-MAP-1: DB-05 ``tg_legal_entity__frozen`` (EREV-REF-001 — ``functional_currency`` /
    ``time_zone`` frozen once a subledger line of the entity exists) is the existing 409
    ``immutable-record`` with ``code`` EREV-REF-001, rule ``ENTITY_FROZEN`` and the trigger's own
    message as the detail — naming the entity and the frozen fields — never a 500 (F-RPS measured
    the 500 on PATCH /api/v1/entities/{id}). Fail-first: the previous catalogue had no slug for
    EREV-REF-001."""
    mapped = from_db_error(db_error(psycopg.errors.RaiseException(FROZEN_MESSAGE)))
    assert mapped is not None
    assert (mapped.slug, mapped.status, mapped.code) == (
        "immutable-record",
        409,
        "EREV-REF-001",
    )
    assert mapped.detail is not None
    assert "AVM-US" in mapped.detail and "functional_currency" in mapped.detail
    assert "time_zone" in mapped.detail and not mapped.detail.startswith("EREV-")
    assert [(e.rule_id, e.message) for e in mapped.errors] == [("ENTITY_FROZEN", mapped.detail)]
    assert PROBLEMS["immutable-record"].db_codes == frozenset({"EREV-IMM-001", "EREV-REF-001"})
    frozen = call(build_app(), "PATCH", "/probe/db-frozen-entity")
    assert frozen.status_code == 409
    body = frozen.json()
    assert body["type"] == "https://erev.dev/problems/immutable-record"
    assert body["code"] == "EREV-REF-001" and "AVM-US" in body["detail"]
    assert [e["rule_id"] for e in body["errors"]] == ["ENTITY_FROZEN"]
    # EREV-IMM-001 keeps its plain form: no rule, no detail
    plain = from_db_error(
        db_error(psycopg.errors.RaiseException("EREV-IMM-001 row is append-only"))
    )
    assert plain is not None and plain.errors == () and plain.detail is None


def test_krn_err_02_erasure_guard_is_forbidden_by_name() -> None:
    """04 §15.2 rev 1.96 / §14.1 DB-19 (revision 0073): ``tg_app_user__erasure_guard``
    (EREV-PRV-001 — a change of ``app_user.email`` / ``external_id`` outside the PRV-07 a erased
    form) is the existing 403 ``forbidden`` with ``code`` EREV-PRV-001 and no rule or detail — the
    answer SQLSTATE 42501 gave while the column grant withheld both columns — never a 500; the
    trigger's message, which names a user row, is not surfaced. Fail-first: the catalogue bound no
    code to ``forbidden``, so the guard's P0001 had no slug (``from_db_error`` None, a 500)."""
    mapped = from_db_error(db_error(psycopg.errors.RaiseException(GUARD_MESSAGE)))
    assert mapped is not None
    assert (mapped.slug, mapped.status, mapped.code) == ("forbidden", 403, "EREV-PRV-001")
    assert mapped.detail is None and mapped.errors == ()
    assert PROBLEMS["forbidden"].db_codes == frozenset({"EREV-PRV-001"})
    refused = call(build_app(), "POST", "/probe/db-erasure-guard")
    assert refused.status_code == 403
    body = refused.json()
    assert body["type"] == "https://erev.dev/problems/forbidden"
    assert body["title"] == PROBLEMS["forbidden"].title
    assert body["code"] == "EREV-PRV-001" and body["detail"] is None and body["errors"] == []
    assert "0f7a2f6e" not in refused.text  # the row id of the message stays in the database error
    # a missing privilege keeps its plain form: the same slug without a code
    plain = from_db_error(privilege_error())
    assert plain is not None and (plain.slug, plain.code) == ("forbidden", None)
