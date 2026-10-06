"""RFC 9457 problem details (dev-guide §5.8 KRN-ERR; 04 API-C-05, §15.2; PRD §5.5 CPY-07, ERR rows).

``PROBLEMS`` equals the 04 §15.2 catalogue: slug, status, the PRD §5.5 ERR title and the §14.1
database codes (DG-ARC-09, DG-ARC-13). Domain code raises ``Problem``; ``install_handlers`` turns
problems, request validation errors, database errors and unhandled exceptions into
``application/problem+json`` responses (DG-KRN-ERR-02, DG-KRN-ERR-03).
"""

from __future__ import annotations

import http
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from types import MappingProxyType
from typing import Any, Final

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from sqlalchemy.exc import DBAPIError
from starlette import exceptions as starlette_exceptions

from erev_api.db import errors as db_errors
from erev_api.logging import get_logger, register_logger_fields, trace_without_messages

register_logger_fields(
    __name__, ("error_class", "driver_error_class", "sqlstate", "constraint_name")
)

TYPE_BASE: Final = "https://erev.dev/problems/"
INSTANCE_BASE: Final = "urn:erev:request:"
MEDIA_TYPE: Final = "application/problem+json"
# API-S-Problem members; extensions may not shadow them.
_MEMBERS: Final = frozenset({"type", "title", "status", "detail", "instance", "code", "errors"})


@dataclass(frozen=True, slots=True)
class ProblemError:
    field: str | None = None
    sheet: str | None = None
    row: int | None = None
    rule_id: str | None = None
    message: str = ""


@dataclass(frozen=True, slots=True)
class ProblemSpec:
    slug: str
    status: int
    title: str
    db_codes: frozenset[str]


# 04 §15.2 rows in catalogue order: slug, status, PRD §5.5 ERR title, §14.1 codes.
_ROWS: Final[tuple[tuple[str, int, str, tuple[str, ...]], ...]] = (
    ("validation-failed", 422, "Check the highlighted fields", ()),
    ("unauthenticated", 401, "Sign-in required", ()),
    # 04 §15.2 rev 1.96 / §14.1 DB-19 (revision 0073): a change of app_user.email / external_id
    # outside the PRV-07 a erased form is the same refusal as the 42501 the column grant gave
    # before rev 1.86 — with the code, no rule and no detail (the message names a user row).
    ("forbidden", 403, "Permission denied", ("EREV-PRV-001",)),
    ("mfa-required", 403, "Multi-factor authentication required", ()),
    ("not-found", 404, "Not found", ()),
    ("precondition-failed", 412, "Record changed", ("EREV-EVT-001",)),
    ("precondition-required", 428, "Record version required", ()),
    ("idempotency-key-reused", 422, "Idempotency key reused", ()),
    ("idempotency-in-progress", 409, "Request still in progress", ()),
    ("immutable-record", 409, "Record cannot change", ("EREV-IMM-001", "EREV-REF-001")),
    (
        "invalid-transition",
        409,
        "Action not available in this state",
        ("EREV-TRN-001", "EREV-PER-001"),
    ),
    ("configuration-frozen", 409, "Version cannot change", ("EREV-CFG-002",)),
    ("configuration-overlap", 409, "Effective dates overlap", ("EREV-CFG-001",)),
    ("period-closed", 409, "Period closed", ("EREV-LED-003",)),
    ("ledger-unbalanced", 422, "Entries do not balance", ("EREV-LED-001", "EREV-JE-001")),
    (
        "ledger-integrity",
        500,
        "Ledger integrity check failed",
        ("EREV-LED-002", "EREV-LED-005", "EREV-JE-002", "EREV-JE-003", "EREV-AUD-001"),
    ),
    ("self-approval", 403, "Self-approval not allowed", ("EREV-APR-001",)),
    ("stale-approval", 409, "Approval voided", ("EREV-APR-003",)),
    ("sod-conflict", 409, "Separation of duties conflict", ()),
    ("sandbox-restricted", 403, "Not available in a sandbox", ("EREV-SBX-001",)),
    ("duplicate-import", 409, "Already imported", ()),
    (
        "allocation-invariant",
        422,
        "Allocation does not equal the transaction price",
        ("EREV-ALC-001",),
    ),
    ("unmapped-account-role", 422, "Account mapping missing", ()),
    ("missing-fx-rate", 422, "Exchange rate missing", ()),
    ("policy-level-not-allowed", 422, "Policy level not allowed", ()),
    ("rate-limited", 429, "Too many requests", ()),
    ("eng-trace-too-large", 422, "Calculation trace too large", ()),
    ("close-gates-failed", 409, "Period cannot be locked", ()),
    ("later-period-closed", 409, "Reopen the later period first", ()),
    ("earlier-period-open", 409, "Lock the earlier period first", ()),
    ("activation-checklist-failed", 409, "Contract cannot be activated", ()),
    ("field-locked-after-activation", 409, "Field locked", ()),
    ("option-already-exercised", 409, "Option already exercised", ()),
    ("ai-disabled", 409, "AI assistance is off", ()),
    ("production-reset-forbidden", 409, "Not available in production", ()),
    ("tenant-kind-immutable", 409, "Workspace type cannot change", ()),
    ("approver-already-decided", 409, "Approver already decided", ("EREV-APR-002",)),
    ("ssp-study-required", 422, "SSP study required", ()),
    ("eac-below-costs-incurred", 422, "Estimate below costs incurred", ()),
    ("legacy-database-unrecognized", 422, "Not a legacy eRev database", ()),
    ("scope-not-allowed", 422, "Scope not allowed", ()),
    ("password-policy", 422, "Choose another password", ()),
    ("upload-type-not-allowed", 422, "File not accepted", ()),
    ("account-locked", 423, "Account locked", ()),
    ("session-expired", 401, "Session ended", ()),
    ("mfa-step-up-required", 403, "Confirm with your authenticator", ()),
    ("job-stalled", 500, "Job stopped responding", ()),
    ("release-mismatch", 503, "Update in progress", ()),
    ("release-validation-pending", 503, "Release validation in progress", ()),
    ("lock-conflict", 409, "Another change was in progress", ()),
    # SYNC-PROBLEM-SHAPE-1 (04 rev 1.90; PRD ERR-56 / ERR-57): the stored problems of a sync run
    # and of a failed connection probe — the T-PLT-27 envelope for every FAILED sync_run.
    ("sync-objects-not-applied", 422, "Some source objects were not applied", ()),
    ("connection-test-failed", 422, "Test connection failed", ()),
    # 04 §15.2 rev 1.144 (supervisor rulings R-97 (6) and R-112 (d); PRD ERR-66): SQLSTATE 57014 -
    # PostgreSQL cancelled a statement at the platform's `statement_timeout` (or on a cancel
    # request) and the transaction rolled back. The server's state, not a fault of the request:
    # 503 with `Retry-After`, never kept for the Idempotency-Key.
    ("statement-timeout", 503, "The request took too long", ()),
)

PROBLEMS: Final[Mapping[str, ProblemSpec]] = MappingProxyType(
    {
        slug: ProblemSpec(slug, status, title, frozenset(codes))
        for slug, status, title, codes in _ROWS
    }
)
_SLUG_BY_CODE: Final[Mapping[str, str]] = MappingProxyType(
    {code: spec.slug for spec in PROBLEMS.values() for code in spec.db_codes}
)
# Starlette's own HTTP errors (unknown route, missing credentials) that have a catalogue slug.
# PRD §5.5 ERR-52: the copy of a 40P01 surfaced as `lock-conflict`.
LOCK_CONFLICT_DETAIL: Final = (
    "Another change to the same records was being saved at the same moment, so nothing was "
    "saved. Resubmit the request."
)
# 04 §15.2 rev 1.71 / DG-KRN-ERR-02 rev 1.61 (D-98 candidate 141, ERR-MAP-1): SQLSTATE 55P03 —
# a lock wait beyond the platform's `lock_timeout` (db/session.py, 10 s) — is the SAME
# `lock-conflict` refusal with its own rule and detail, distinct from 40P01's deadlock; the
# transaction rolled back, nothing was saved, the client may resubmit — no automatic retry exists.
RULE_LOCK_TIMEOUT: Final = "LOCK_TIMEOUT"
# PRD §5.5 ERR-66: the copy of a 57014 surfaced as `statement-timeout`, and the `Retry-After` it
# carries. Thirty seconds, not the five of the slug-less 503: a statement that ran into the
# platform's limit held a connection for a minute, and a retry may do so again.
STATEMENT_TIMEOUT_DETAIL: Final = (
    "The server stopped this request because it ran longer than allowed, so nothing was saved. "
    "Try again in a moment."
)
STATEMENT_TIMEOUT_RETRY_AFTER_SECONDS: Final = 30
# 04 API-C-05 rev 1.114 (ruling R-53 (5)): the `Retry-After` of the 503 a database error of
# `db_errors.server_unavailable` is answered with. A full lock table clears within seconds; a
# server that is still down answers the retry with another 503.
SERVER_UNAVAILABLE_RETRY_AFTER_SECONDS: Final = 5
# The class the `http.server_unavailable` log line names for a pool timeout (rev 1.127).
POOL_TIMEOUT_CLASS: Final = "sqlalchemy.exc.TimeoutError"
LOCK_TIMEOUT_DETAIL: Final = (
    "The records this request needed were held by another change for longer than the platform "
    "waits, so nothing was saved. Resubmit the request."
)
# PRD §5.5 ERR-72 (rev 1.86; 04 §14.1 "A command recorded before a lock" rev 1.157; supervisor
# rulings R-105 (3) and of 2026-10-01): the `lock-conflict` a computation raises itself when a
# period lock was decided between the start of the transaction that recorded its event and its
# first write (`domain.contracts.computation`). Nothing was waited for, so neither detail above
# fits. One sentence in two forms: the command's, and the one an approval's decision answers
# with, which names the act to repeat (`approvals.engine.decide`).
RULE_PERIOD_STATE_MOVED: Final = "PERIOD_STATE_MOVED"
PERIOD_STATE_MOVED_DETAIL: Final = (
    "A period of this contract was locked while the command ran. Nothing was saved. "
    "Send it again: it is then recorded after the lock."
)
PERIOD_STATE_MOVED_DECISION_DETAIL: Final = (
    "A period of this contract was locked while the command ran. Nothing was saved. "
    "Decide again: it is then recorded after the lock."
)
# PRD §5.5 ERR-98 (rev 1.187; 04 §14.1 DB-07 rev 1.229; dev-guide DG-KRN-DB-08 (1c) rev 1.218;
# finding F4 of the independent review of 2026-10-01; supervisor ruling of 2026-10-02): the
# `lock-conflict` of a transaction that holds a ledger chain head and meets a period state row a
# lock decision holds. Under a head that row is asked NOWAIT (`contracts.period_ends`), so
# nothing was waited for and the `LOCK_TIMEOUT` sentence would be untrue of it.
RULE_PERIOD_LOCK_IN_FLIGHT: Final = "PERIOD_LOCK_IN_FLIGHT"
PERIOD_LOCK_IN_FLIGHT_DETAIL: Final = (
    "A period of this contract is being locked. Nothing was saved. Send it again."
)
# §14.1 codes that carry a rule id and the trigger's own message as the detail (rev 1.71; D-98
# candidate 141 amendment 1): `EREV-REF-001` is shared by every DB-05 reference-data freeze trigger
# (legal entity, tenant identity, period, calendar, SSP book scope), so `ENTITY_FROZEN` is the
# code-wide rule and the detail — the trigger's message — names the frozen field and object.
_DB_CODE_RULES: Final[Mapping[str, str]] = MappingProxyType({"EREV-REF-001": "ENTITY_FROZEN"})

_HTTP_SLUGS: Final[Mapping[int, str]] = MappingProxyType(
    {401: "unauthenticated", 403: "forbidden", 404: "not-found"}
)


class Problem(Exception):
    """A catalogue problem; raising it from a handler produces its problem response."""

    def __init__(
        self,
        slug: str,
        detail: str | None = None,
        *,
        errors: Sequence[ProblemError] = (),
        code: str | None = None,
        headers: Mapping[str, str] | None = None,
        **extensions: Any,
    ) -> None:
        spec = PROBLEMS[slug]
        shadowed = _MEMBERS.intersection(extensions)
        if shadowed:
            raise ValueError(f"problem extensions shadow members: {sorted(shadowed)}")
        super().__init__(slug if detail is None else f"{slug}: {detail}")
        self.spec = spec
        self.slug = slug
        self.status = spec.status
        self.title = spec.title
        self.detail = detail
        self.errors = tuple(errors)
        self.code = code
        self.headers = dict(headers or {})
        self.extensions = dict(extensions)

    def to_json(self, *, instance: str) -> dict[str, Any]:
        body: dict[str, Any] = {
            "type": TYPE_BASE + self.slug,
            "title": self.title,
            "status": self.status,
            "detail": self.detail,
            "instance": instance,
            "code": self.code,
            "errors": [asdict(error) for error in self.errors],
        }
        body.update(self.extensions)
        return body


def problem(slug: str, detail: str | None = None, **kwargs: Any) -> Problem:
    return Problem(slug, detail, **kwargs)


def period_state_moved(*, deciding: bool = False) -> Problem:
    """PRD ERR-72: 409 ``lock-conflict`` under rule ``PERIOD_STATE_MOVED`` — the command's form,
    or with ``deciding`` the form an approval's decision answers with."""
    detail = PERIOD_STATE_MOVED_DECISION_DETAIL if deciding else PERIOD_STATE_MOVED_DETAIL
    refused = ProblemError(rule_id=RULE_PERIOD_STATE_MOVED, message=detail)
    return Problem("lock-conflict", detail, errors=[refused])


def is_period_state_moved(problem: Problem) -> bool:
    """Whether ``problem`` is the refusal of PRD ERR-72, in either form."""
    return problem.slug == "lock-conflict" and any(
        error.rule_id == RULE_PERIOD_STATE_MOVED for error in problem.errors
    )


def period_lock_in_flight() -> Problem:
    """PRD ERR-98: 409 ``lock-conflict`` under rule ``PERIOD_LOCK_IN_FLIGHT``."""
    refused = ProblemError(rule_id=RULE_PERIOD_LOCK_IN_FLIGHT, message=PERIOD_LOCK_IN_FLIGHT_DETAIL)
    return Problem("lock-conflict", PERIOD_LOCK_IN_FLIGHT_DETAIL, errors=[refused])


def is_lock_conflict(problem: Problem) -> bool:
    """Whether ``problem`` is a 409 ``lock-conflict`` in any of its forms: a deadlock or a
    serialization failure (PRD ERR-52), a lock wait beyond the platform's timeout, a period held
    or moved (PRD ERR-72, ERR-78, ERR-85), a computation behind its group (04 §14.1 rev 1.298).
    Every form says the same of what was asked — nothing was saved, and the same request may be
    sent again — which is what a retry predicate reads it for."""
    return problem.slug == "lock-conflict"


def from_db_error(exc: DBAPIError, *, method: str = "POST") -> Problem | None:
    """Map a database error to its problem (DG-KRN-ERR-02); None when no slug applies.

    ``P0001`` with a §14.1 code gives the slug whose ``db_codes`` holds it, with ``code`` set.
    ``42501`` (insufficient privilege, including RLS ``WITH CHECK``) gives 404 ``not-found`` for
    GET and HEAD and 403 ``forbidden`` otherwise. ``40P01`` (deadlock detected) gives 409
    ``lock-conflict`` — the transaction rolled back and nothing was saved; the client may resubmit,
    no automatic retry exists (DG-KRN-DB-08 rev 1.36; D-98 candidate 101c). ``55P03`` (a lock wait
    beyond ``lock_timeout``) gives the same 409 ``lock-conflict`` with rule ``LOCK_TIMEOUT`` and its
    own detail; a §14.1 code listed in ``_DB_CODE_RULES`` (``EREV-REF-001`` → ``ENTITY_FROZEN``)
    carries its rule and the trigger's message as the detail (04 §15.2 rev 1.71; DG-KRN-ERR-02 rev
    1.61; D-98 candidate 141).

    Rev 1.127 (04 §15.2 rev 1.144; supervisor rulings R-97 (5), (6)): ``40001`` (a serialization
    failure) is the same 409 ``lock-conflict`` as the deadlock - the transaction lost to another
    one and nothing was saved; ``57014`` (a statement PostgreSQL cancelled, at the platform's
    ``statement_timeout`` or on request) is 503 ``statement-timeout`` with ``Retry-After``.
    """
    state = db_errors.sqlstate(exc)
    if state in (db_errors.DEADLOCK_DETECTED, db_errors.SERIALIZATION_FAILURE):
        return Problem("lock-conflict", LOCK_CONFLICT_DETAIL)
    if state == db_errors.QUERY_CANCELED:
        return Problem(
            "statement-timeout",
            STATEMENT_TIMEOUT_DETAIL,
            headers={"Retry-After": str(STATEMENT_TIMEOUT_RETRY_AFTER_SECONDS)},
        )
    if state == db_errors.LOCK_NOT_AVAILABLE:  # rev 1.71: the wait outlived lock_timeout
        return Problem(
            "lock-conflict",
            LOCK_TIMEOUT_DETAIL,
            errors=[ProblemError(rule_id=RULE_LOCK_TIMEOUT, message=LOCK_TIMEOUT_DETAIL)],
        )
    if state == db_errors.RAISE_EXCEPTION:
        code = db_errors.erev_code(exc)
        slug = _SLUG_BY_CODE.get(code) if code is not None else None
        if slug is None or code is None:
            return None
        rule = _DB_CODE_RULES.get(code)
        if rule is None:
            return Problem(slug, code=code)
        # the trigger's own message, after the code, names what is frozen and for which record
        primary = db_errors.message_primary(exc).strip()
        detail = primary[len(code) :].lstrip(": ").strip() or None
        return Problem(
            slug, detail, code=code, errors=[ProblemError(rule_id=rule, message=detail or "")]
        )
    if state == db_errors.INSUFFICIENT_PRIVILEGE:
        return Problem("not-found" if method.upper() in {"GET", "HEAD"} else "forbidden")
    return None


def request_id_for(request: Request) -> str:
    """The request id set by the request middleware, or a new one stored on the request state."""
    value = getattr(request.state, "request_id", None)
    if isinstance(value, str) and value:
        return value
    generated = str(uuid.uuid4())
    request.state.request_id = generated
    return generated


def problem_response(request: Request, problem: Problem) -> Response:
    return JSONResponse(
        problem.to_json(instance=INSTANCE_BASE + request_id_for(request)),
        status_code=problem.status,
        headers=problem.headers or None,
        media_type=MEDIA_TYPE,
    )


def _about_blank(
    request: Request, status: int, headers: Mapping[str, str] | None = None
) -> Response:
    body = {
        "type": "about:blank",
        "title": http.HTTPStatus(status).phrase,
        "status": status,
        "instance": INSTANCE_BASE + request_id_for(request),
        "code": None,
        "errors": [],
    }
    return JSONResponse(body, status_code=status, headers=headers, media_type=MEDIA_TYPE)


def _fields_detail(count: int) -> str:
    return "1 field needs attention." if count == 1 else f"{count} fields need attention."


def _validation_error(item: Mapping[str, Any]) -> ProblemError:
    location = tuple(item.get("loc", ()))
    if location and location[0] == "body":
        location = location[1:]
    ctx = item.get("ctx")
    rule_id = ctx.get("rule_id") if isinstance(ctx, Mapping) else None
    return ProblemError(
        field=".".join(str(part) for part in location) or None,
        rule_id=rule_id if isinstance(rule_id, str) else None,
        message=str(item.get("msg", "")),
    )


async def _handle_problem(request: Request, exc: Exception) -> Response:
    assert isinstance(exc, Problem)
    if exc.slug == "statement-timeout":
        # Raised from the database error by a mapper - the commit's (`uow.py`) or an
        # `except DBAPIError` around a statement: the log line of `_handle_db` (rev 1.127).
        _log_statement_timeout(request, db_errors.database_error_in(exc))
    return problem_response(request, exc)


async def _handle_validation(request: Request, exc: Exception) -> Response:
    assert isinstance(exc, RequestValidationError)
    errors = [_validation_error(item) for item in exc.errors()]
    return problem_response(
        request, Problem("validation-failed", _fields_detail(len(errors)), errors=errors)
    )


async def _handle_http(request: Request, exc: Exception) -> Response:
    assert isinstance(exc, starlette_exceptions.HTTPException)
    slug = _HTTP_SLUGS.get(exc.status_code)
    if slug is not None:
        return problem_response(request, Problem(slug, headers=exc.headers))
    return _about_blank(request, exc.status_code, exc.headers)


def _qualified_name(value: object) -> str:
    kind = type(value)
    if kind.__module__ == "builtins":
        return kind.__qualname__
    return f"{kind.__module__}.{kind.__qualname__}"


def _log_statement_timeout(request: Request, database_error: DBAPIError | None) -> None:
    """The line an operator finds a cancelled statement by (DG-KRN-ERR-02 rev 1.127): WARNING with
    the SQLSTATE and the driver's error class, no stack trace and no driver message. An operational
    condition, not a defect of the request. ``database_error`` is None only for a
    ``statement-timeout`` problem that was not raised from a database error."""
    get_logger(__name__).warning(
        "http.statement_timeout",
        request_id=request_id_for(request),
        driver_error_class=None if database_error is None else _qualified_name(database_error.orig),
        sqlstate=None if database_error is None else db_errors.sqlstate(database_error),
    )


def unhandled_error_response(request: Request, exc: BaseException) -> Response:
    """500 about:blank; the stack trace goes to the log only (DG-KRN-ERR-03, DG-LOG-05).

    A database error, or an error it caused, logs its class, SQLSTATE and constraint name with a
    stack trace whose exception messages are replaced, because driver messages can quote bound
    values (DG-LOG-03; D-78).

    Rev 1.97 (04 API-C-05 rev 1.114; ruling R-53 (5)): a database error that says the server could
    not do it at that moment (``db_errors.server_unavailable``) is not a defect of the request:
    503 about:blank with ``Retry-After``, logged at WARNING with its SQLSTATE and no stack trace.

    Rev 1.127 (04 API-C-05 rev 1.144; ruling R-103 (c)): so is the application's own connection
    pool that gave no connection within its wait (``db_errors.pool_timeout_in``) - the server's
    state, not a conflict with another command; the log line carries the pool error's class in
    place of a driver error's and no SQLSTATE.
    """
    logger = get_logger(__name__)
    request_id = request_id_for(request)
    database_error = db_errors.database_error_in(exc)
    if database_error is not None and db_errors.server_unavailable(database_error):
        logger.warning(
            "http.server_unavailable",
            request_id=request_id,
            error_class=_qualified_name(exc),
            driver_error_class=_qualified_name(database_error.orig),
            sqlstate=db_errors.sqlstate(database_error),
        )
        return _about_blank(
            request, 503, {"Retry-After": str(SERVER_UNAVAILABLE_RETRY_AFTER_SECONDS)}
        )
    if database_error is None and db_errors.pool_timeout_in(exc):
        logger.warning(
            "http.server_unavailable",
            request_id=request_id,
            error_class=_qualified_name(exc),
            driver_error_class=POOL_TIMEOUT_CLASS,
            sqlstate=None,
        )
        return _about_blank(
            request, 503, {"Retry-After": str(SERVER_UNAVAILABLE_RETRY_AFTER_SECONDS)}
        )
    if database_error is None:
        logger.error(
            "http.unhandled_error",
            request_id=request_id,
            error_class=_qualified_name(exc),
            exc_info=exc,
        )
    else:
        constraint = getattr(getattr(database_error.orig, "diag", None), "constraint_name", None)
        logger.error(
            "http.unhandled_error",
            request_id=request_id,
            error_class=_qualified_name(exc),
            driver_error_class=_qualified_name(database_error.orig),
            sqlstate=db_errors.sqlstate(database_error),
            constraint_name=constraint if isinstance(constraint, str) else None,
            exception=trace_without_messages(exc),
        )
    return _about_blank(request, 500)


async def _handle_unhandled(request: Request, exc: Exception) -> Response:
    return unhandled_error_response(request, exc)


async def _handle_db(request: Request, exc: Exception) -> Response:
    assert isinstance(exc, DBAPIError)
    mapped = from_db_error(exc, method=request.method)
    if mapped is None:
        return await _handle_unhandled(request, exc)
    if mapped.slug == "statement-timeout":
        _log_statement_timeout(request, exc)
    return problem_response(request, mapped)


def install_handlers(app: FastAPI) -> None:
    app.add_exception_handler(Problem, _handle_problem)
    app.add_exception_handler(RequestValidationError, _handle_validation)
    app.add_exception_handler(starlette_exceptions.HTTPException, _handle_http)
    app.add_exception_handler(DBAPIError, _handle_db)
    app.add_exception_handler(Exception, _handle_unhandled)
